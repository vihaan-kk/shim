"""HTTP API for the web workbench (agent/ui/web), following docs/FRONTEND_API.md.

    uv run uvicorn agent.web_api:app --port 8001

This layer adds no tool logic. Every action goes through the same registered tools
the model calls (tools.registry.call), so the same checks and gates apply:
- one Agent per browser session (cookie), shared by the three pages;
- chat, answer and confirm stream the agent's tool events as server-sent events,
  ending with exactly one pause; /api/confirm is the only way a confirmation is made;
- the form's limb dimensions go through validate_measurements and
  customize_residual_limb; "Confirm limb" builds the socket with fit_socket_to_limb
  and validate_part;
- the print monitor only reads OctoPrint (README section 12); it never sends a job command.
- stages are enforced in this layer, not by the pages: a per-session tool guard
  locks the printing tools (stage_gate) until the session's socket has been
  confirmed, and the agent's move_to_stage builtin performs stage changes here
  (building the socket from the current limb, or confirming it, as needed) and
  emits a navigate event the page follows.
The browser sends revision ids, never file paths.
"""

from __future__ import annotations

import json
import os
import queue
import re
import secrets
import threading
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import cadquery as cq
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse

from agent.llm import VllmClient
from agent.loop import Agent, Pause
from agent.ui.cli import load_env
from common.result import fatal, fixable, success
from tools import registry

load_env()
registry.load_tools()
FAKE_PRINTER = os.environ.get("FAKE_TOOLS", "0") == "1"

from tools.cad import questionnaire  # noqa: E402  (after load_env: reads WORKSPACE_DIR)
from tools.cad import tools as cad  # noqa: E402
from tools.printer import gcode_layers  # noqa: E402

API_BASE = os.environ.get("API_PUBLIC_BASE", "http://localhost:8001/api")
ORIGINS = os.environ.get("WEB_ORIGINS", "http://localhost:3000,http://localhost:3001").split(",")
COOKIE = "shim_session"

app = FastAPI(title="Shim workbench API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type"],
)

# Frontend measurement field -> validate_measurements argument (lib/types.ts Measurements).
FIELD_TO_TOOL = {
    "length_mm": "length_mm",
    "proximal_circumference_mm": "proximal_circumference_mm",
    "distal_circumference_mm": "distal_circumference_mm",
    "mid_circumference_mm": "mid_circumference_mm",
    "ap_depth_mm": "ap_mm",
    "ml_width_mm": "ml_mm",
    "distal_shape": "distal_shape",
    "side": "side",
}
TOOL_TO_FIELD = {v: k for k, v in FIELD_TO_TOOL.items()}


def _form_defaults() -> dict:
    """What the form shows before any edit: length, P and D from the standard limb;
    optional fields empty, which means they follow the standard shape."""
    d = questionnaire.defaults(cad.load_profile(cad.PROFILE_PATH))
    return {
        "length_mm": d["length_mm"],
        "proximal_circumference_mm": d["proximal_circumference_mm"],
        "distal_circumference_mm": d["distal_circumference_mm"],
        "mid_circumference_mm": None,
        "ap_depth_mm": None,
        "ml_width_mm": None,
        "distal_shape": "template",
        "side": "template",
    }


def _stl_url(revision_id: str, role: str) -> str:
    return f"{API_BASE}/files/{revision_id}/{role}.stl"


# ---------------------------------------------------------------------------
# Sessions
# ---------------------------------------------------------------------------


@dataclass
class Session:
    id: str
    agent: Agent
    measurements: dict
    limb: dict
    socket: dict | None = None  # SocketBundle: {"socket": SocketRevision, "validation": report}
    socket_confirmed: bool = False
    job: dict | None = None
    started: bool = False
    started_jobs: set = field(default_factory=set)  # job_ids with a verified start_print
    cancelled_jobs: set = field(default_factory=set)  # job_ids cancel_print stopped
    pending: dict | None = None
    seen_printing: bool = False
    last_snapshot: dict | None = None
    log: list = field(default_factory=list)  # audit trail for the report
    lock: threading.Lock = field(default_factory=threading.Lock)

    def snapshot(self) -> dict:
        return {
            "measurements": self.measurements,
            "limb": self.limb,
            "socket": self.socket,
            "socket_confirmed": self.socket_confirmed,
            "job": self.job,
            "started": self.started,
            "pending": self.pending,
        }

    def note(self, event: str, **details) -> None:
        self.log.append({"at": _now(), "event": event, **details})


_sessions: dict[str, Session] = {}
_sessions_lock = threading.Lock()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _new_session() -> Session:
    limb = cad.create_part("limb")  # r0: an unedited copy of the standard limb
    revision_id = limb.data["revision_id"]
    session = Session(
        id=secrets.token_urlsafe(16),
        agent=Agent(VllmClient()),
        measurements=_form_defaults(),
        limb={"revision_id": revision_id, "parent_revision_id": None, "stl_url": _stl_url(revision_id, "residual_limb")},
    )
    session.agent.tool_guard = lambda name, args: _stage_guard(session, name, args)
    session.agent.stage_handler = lambda stage: _stage_handler(session, stage)
    session.note("session_started", limb=revision_id)
    return session


def _session(request: Request) -> tuple[Session, bool]:
    """The browser's session, created on first use. Returns (session, is_new)."""
    sid = request.cookies.get(COOKIE)
    with _sessions_lock:
        if sid in _sessions:
            # A session whose limb files were deleted (workspace cleared while running)
            # would only serve 404s; start a fresh one instead.
            if cad._revision_dir(_sessions[sid].limb["revision_id"]).is_dir():
                return _sessions[sid], False
            del _sessions[sid]
        session = _new_session()
        _sessions[session.id] = session
        return session, True


def _respond(session: Session, is_new: bool, response):
    if is_new:
        response.set_cookie(COOKIE, session.id, httponly=True, samesite="lax")
    return response


def _build_socket(session: Session, limb_id: str, by: str) -> tuple[dict | None, str | None]:
    """Build and validate the socket for a limb, storing it on the session.

    Returns (error, validate_status): a ToolResult dict describing the
    failure, or (None, validate_part's status) on success.
    Assumes the caller holds session.lock.
    """
    base = registry.call("create_part", {"part_type": "socket"})
    if not base.ok:
        return base.to_dict(), None
    fitted = registry.call("fit_socket_to_limb", {"socket_revision_id": base.data["revision_id"], "limb_revision_id": limb_id})
    if not fitted.ok:
        return fitted.to_dict(), None
    socket_id = fitted.data["revision_id"]
    checked = registry.call("validate_part", {"revision_id": socket_id})
    validation = _validation_report(socket_id) or {"passed": False, "error": checked.to_dict()["error"], "categories": {}}
    if checked.status != "success":
        validation = {**validation, "printable": False, "print_check": checked.to_dict()}
    session.socket = {
        "socket": {"socket_id": socket_id, "limb_revision_id": limb_id, "stl_url": _stl_url(socket_id, "socket_shell")},
        "validation": validation,
    }
    session.socket_confirmed = False
    session.note("socket_built", socket=socket_id, limb=limb_id, by=by, validated=checked.ok)
    return None, checked.status


# Tools that move a print forward. Locked until the socket stage is complete,
# no matter which page the user asks from or how they phrase it.
PRINT_STAGE_TOOLS = {"prepare_print", "slice", "start_print"}

# Part types outside the fixed workbench flow (residual limb -> its socket ->
# print that socket). The agent cannot mint them in the web app at all.
OFF_FLOW_PARTS = {"foot", "adapter", "pylon", "assembly"}


def _preview_of(revision_id: str | None) -> str | None:
    """The part a preview-N revision is a scaled copy of, or None for anything else."""
    meta = cad._read_meta(revision_id) if revision_id else None
    return meta.get("preview_of") if meta and meta["part_type"] == "preview" else None


def _in_flow(revision_id: str | None, socket_id: str) -> bool:
    """The confirmed socket, or a scaled preview made from it, may be printed."""
    return revision_id == socket_id or _preview_of(revision_id) == socket_id


def _stage_guard(session: Session, name: str, args: dict):
    """Agent tool_guard for this session: the flow is fixed.

    Residual limb, then the socket fitted to it, then printing that socket -
    nothing else. Other part types cannot be created, only the confirmed
    socket (built for the current limb) can be prepared, sliced or printed,
    and a job that has already started can never be started or re-confirmed.
    """
    # A socket is built and checked against the session's current limb only. Older limb
    # revisions on disk (an earlier session's, or before an edit) are not the patient's limb now.
    current_limb = session.limb["revision_id"]
    if name in ("fit_socket_to_limb", "check_fit") and args.get("limb_revision_id") not in (None, current_limb):
        return fixable(
            code="not_current_limb",
            reason=f"The workbench's current limb is {current_limb}; {args['limb_revision_id']} is not it.",
            message=(
                f"Call {name} again with limb_revision_id {current_limb}, the current limb. Do not "
                "change the limb to match another revision; only change it when the user asks."
            ),
            valid_range=[current_limb],
        )
    if name == "create_part" and args.get("part_type") in OFF_FLOW_PARTS:
        return fatal(
            code="off_flow",
            reason=(
                f"This workbench only builds a residual limb and its socket; it cannot create "
                f"a {args.get('part_type')}. The fixed flow is: residual limb, then the socket "
                "fitted to it, then printing that socket."
            ),
            message=(
                "Do not create other part types. Continue the limb -> socket -> print flow, "
                "or explain that flow to the user."
            ),
        )
    wants_print = name in PRINT_STAGE_TOOLS or (
        name == "request_confirmation" and args.get("action") == "start_print"
    )
    if not wants_print:
        return None
    socket = (session.socket or {}).get("socket") or {}
    socket_id = socket.get("socket_id")
    if not session.socket_confirmed or socket_id is None:
        return fatal(
            code="stage_gate",
            reason=(
                "Printing is locked until the socket stage is complete: no socket has been "
                "confirmed in this session. The user must review the socket on the socket "
                "page and confirm it there before anything can be prepared, sliced or printed."
            ),
            message=(
                "Do not retry printing tools. Explain the stage order (limb, then socket, "
                "then printer) and offer to take the user to the socket stage."
            ),
        )
    if socket.get("limb_revision_id") != session.limb["revision_id"]:
        return fatal(
            code="stage_gate",
            reason=(
                "The confirmed socket was built for an earlier limb revision and the limb "
                "has changed since, so it is no longer the socket for the current limb."
            ),
            message=(
                "Do not print the stale socket. Take the user back to the socket stage "
                "(move_to_stage) so a socket is built and confirmed for the current limb."
            ),
        )
    if name in ("prepare_print", "slice"):
        if not args.get("revision_id"):
            # prepare_print's revision_id is optional; here it must name the socket.
            return fixable(
                code="missing_argument",
                reason=f"In this flow, prepare_print and slice must name the confirmed socket ({socket_id}).",
                message=f"Call {name} again with revision_id {socket_id}.",
            )
        if not _in_flow(args["revision_id"], socket_id):
            return fatal(
                code="off_flow",
                reason=(
                    f"Only the confirmed socket ({socket_id}) or a preview of it can be prepared or sliced in "
                    f"this flow; {args.get('revision_id') or 'an unspecified part'} is not it."
                ),
                message="Do not prepare or slice other parts. Print the confirmed socket, or go back a stage with move_to_stage.",
            )
        return None
    # start_print itself, or a request to confirm one: the job must be the
    # sliced job for the confirmed socket, and never one already started.
    job_id = args.get("job_id") or args.get("subject")
    if job_id in session.started_jobs:
        return fatal(
            code="already_started",
            reason=f"Job {job_id} has already been started; a print can only be started once.",
            message=(
                "Do not call start_print or request another confirmation for this job. "
                "Report its current state to the user (get_job_progress / get_printer_status)."
            ),
        )
    job = session.job or {}
    if job_id != job.get("job_id") or not _in_flow(job.get("revision_id"), socket_id):
        return fatal(
            code="off_flow",
            reason=(
                f"Only the sliced job for the confirmed socket ({socket_id}) can be started "
                "in this flow. Slice the confirmed socket first if no such job exists."
            ),
            message="Do not start or confirm prints for other parts or stale jobs.",
        )
    return None


def _stage_handler(session: Session, stage: str):
    """Perform a move_to_stage call. Runs inside an agent turn (lock held)."""
    if stage == "limb":
        session.agent.on_event("navigate", {"stage": "limb"})
        return success("Moved to the limb stage.", {"stage": "limb"})
    if stage == "socket":
        # Build when there is no socket yet, or the limb changed after the
        # existing socket was built for an earlier limb.
        if session.socket is None or session.socket["socket"].get("limb_revision_id") != session.limb["revision_id"]:
            error, _ = _build_socket(session, session.limb["revision_id"], by="chat_stage")
            if error is not None:
                reason = (error.get("error") or {}).get("reason") or error.get("message") or "unknown error"
                return fatal(
                    code="stage_failed",
                    reason=f"The socket could not be built for the current limb: {reason}",
                    message="Tell the user why the socket could not be built; stay on this stage.",
                )
        socket_id = session.socket["socket"]["socket_id"]
        session.agent.on_event("navigate", {"stage": "socket"})
        return success(f"Moved to the socket stage with socket {socket_id}.", {"stage": "socket", "socket_id": socket_id})
    # stage == "printer"
    if session.socket is None:
        return fatal(
            code="stage_gate",
            reason="There is no socket yet, so there is nothing to print.",
            message="Offer to take the user to the socket stage first, which builds the socket.",
        )
    if not session.socket["validation"].get("passed"):
        return fatal(
            code="stage_gate",
            reason="The current socket has not passed its geometric checks, so it cannot be confirmed for printing.",
            message="Direct the user to the socket stage to review the checks.",
        )
    if not session.socket_confirmed:
        session.socket_confirmed = True
        session.note("socket_confirmed", socket=session.socket["socket"]["socket_id"], by="chat_stage")
    session.agent.on_event("navigate", {"stage": "printer"})
    return success("Moved to the printer stage; the socket is confirmed.", {"stage": "printer"})


# ---------------------------------------------------------------------------
# Session state
# ---------------------------------------------------------------------------


@app.get("/api/session")
def get_session(request: Request):
    session, is_new = _session(request)
    return _respond(session, is_new, JSONResponse(session.snapshot()))


# ---------------------------------------------------------------------------
# Agent turns (server-sent events)
# ---------------------------------------------------------------------------


def _not_validated(socket_id: str) -> dict:
    """SocketValidation for a socket revision no check has run on yet."""
    return {
        "passed": False,
        "clinical_use": False,
        "disclaimer": "A passing result is a CAD check of a synthetic solid, not a fit or safety check.",
        "socket_model_id": socket_id,
        "reference_limb_model_id": None,
        "error": {"code": "not_validated", "message": f"{socket_id} has not been validated yet. Ask the agent to validate it."},
        "categories": {},
    }


def _socket_measurements(socket_id: str) -> dict | None:
    """Measurements of a socket revision for the 3D labels, in validate_socket's shape.

    Measuring is not validating: the revision still shows as not validated, but the
    viewer keeps its section rings and labels. None if the measurement fails.
    """
    from tools.cad.measure_socket import measure_socket
    from tools.cad.generate_limb import load_profile

    meta = cad._read_meta(socket_id)
    if meta is None:
        return None
    try:
        profile = json.loads((cad._revision_dir(socket_id) / "profile.json").read_text())
        limb = load_profile(cad._limb_profile_path(meta.get("limb_revision_id")))
        measured = measure_socket(cad._base_step(socket_id), profile, limb)
    except Exception:
        return None
    if not measured.get("ok"):
        return None
    keys = ("depth_mm", "volume_mm3", "proximal_opening", "wall_thickness_samples", "distal_end", "cavity")
    sections = ("id", "z_mm", "status", "inner_perimeter_mm", "outer_perimeter_mm", "ml_wall_thickness_mm", "ap_wall_thickness_mm")
    return {
        "units": "mm",
        **{k: measured[k] for k in keys},
        "sections": [{k: row[k] for k in sections} for row in measured["sections"]],
    }


def _enrich(session: Session, name: str, result: dict) -> dict:
    """Add the fields the page needs to a tool result, and track session state."""
    data = dict(result.get("data") or {})
    if name == "validate_part":
        # Pass or fail, the page shows the latest report for the current socket.
        sid = data.get("revision_id") or (result.get("error") or {}).get("revision_id")
        current = (session.socket or {}).get("socket", {}).get("socket_id")
        report = _validation_report(current) if current else None
        if report is not None and (sid in (None, current)):
            if result.get("status") != "success":
                report = {**report, "passed": False, "error": result.get("error")}
            data["revision_id"] = current
            data["validation"] = report
            session.socket = {**session.socket, "validation": report}
        return {**result, "data": data}
    if result.get("status") != "success":
        return result
    if name == "customize_residual_limb":
        rid = data["revision_id"]
        data["stl_url"] = _stl_url(rid, "residual_limb")
        edits = data.get("edits") or {}
        data["measurements"] = {TOOL_TO_FIELD[k]: v for k, v in edits.items() if k in TOOL_TO_FIELD}
        session.limb = {"revision_id": rid, "parent_revision_id": data.get("parent_revision_id"), "stl_url": data["stl_url"]}
        session.measurements = {**_form_defaults(), **data["measurements"]}
        session.note("limb_built", limb=rid, edits=edits, by="agent")
    elif name in ("fit_socket_to_limb", "modify_socket", "engrave_label"):
        sid = data["revision_id"]
        data["socket_id"] = sid
        data["stl_url"] = _stl_url(sid, "socket_shell")
        data["validation"] = _not_validated(sid)  # a new revision has no checks yet
        measurements = _socket_measurements(sid)
        if measurements:
            data["validation"]["measurements"] = measurements
        # Record which limb this revision was built for, or the stage gate reads
        # a fresh socket as stale and rebuilds it. The revision's meta is the
        # source (modify_socket inherits it from its parent; None means the
        # standard limb). A chat-first socket with no page-built one yet still
        # opens the session bundle so the stage flow can see it.
        meta = cad._read_meta(sid) or {}
        socket_info = {
            **(session.socket or {}).get("socket", {}),
            "socket_id": sid,
            "stl_url": data["stl_url"],
            "limb_revision_id": meta.get("limb_revision_id", data.get("limb_revision_id")),
        }
        session.socket = {"socket": socket_info, "validation": data["validation"]}
        session.socket_confirmed = False
        session.note("socket_built", socket=sid, by=name)
    elif name in ("prepare_print", "slice"):
        session.job = data
        session.note("sliced", job=data.get("job_id"), profile=data.get("profile_id"))
    elif name == "cancel_print":
        session.cancelled_jobs.add(data.get("job_id") or (session.job or {}).get("job_id"))
        session.note("print_cancelled", job=data.get("job_id"))
    elif name == "start_print" and data.get("verified"):
        session.started = True
        session.started_jobs.add(data.get("job_id"))
        session.seen_printing = False
        session.last_snapshot = None
        session.note("print_started", job=data.get("job_id"))
    return {**result, "data": data}


def _turn(session: Session, run) -> StreamingResponse:
    """Run one agent turn in a worker thread and stream its events."""
    events: queue.Queue = queue.Queue()

    def on_event(kind: str, payload: dict) -> None:
        if kind == "tool_call":
            events.put({"type": "tool_call", "name": payload["name"], "args": payload["args"]})
        elif kind == "navigate":
            events.put({"type": "navigate", "stage": payload["stage"]})
        else:
            events.put({"type": "tool_result", "name": payload["name"], "result": _enrich(session, payload["name"], payload["result"])})

    def worker() -> None:
        with session.lock:
            session.agent.on_event = on_event
            try:
                pause = run()
            except Exception as exc:  # the model endpoint is down, or a bug: end the turn cleanly
                pause = Pause("stopped", f"The agent could not finish this turn: {type(exc).__name__}: {exc}")
            finally:
                session.agent.on_event = lambda *_: None
            pause_dict = asdict(pause)
            if pause.kind == "confirmation":
                # Scale never changes silently: a preview's confirmation says so, whatever the model wrote.
                job = session.job or {}
                source = _preview_of(job.get("revision_id")) if job.get("job_id") == pause.details.get("subject") else None
                if source:
                    scale = cad._read_meta(job["revision_id"])["scale_percent"]
                    pause_dict["text"] = (
                        f"PREVIEW at {scale:g}% of {source}, NOT TO SIZE. {pause_dict['text']}"
                    )
            session.pending = pause_dict if pause.kind in ("question", "confirmation") else None
            if pause.kind == "confirmation":
                session.note("confirmation_requested", **pause.details)
            events.put({"type": "pause", "pause": pause_dict})
            events.put(None)

    threading.Thread(target=worker, daemon=True).start()

    def stream():
        while (item := events.get()) is not None:
            yield f"data: {json.dumps(item, default=str)}\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})


def _conflict(message: str) -> JSONResponse:
    return JSONResponse({"error": message}, status_code=409)


@app.post("/api/chat")
async def chat(request: Request):
    session, is_new = _session(request)
    body = await request.json()
    if session.pending:
        return _respond(session, is_new, _conflict("Answer the pending question or confirmation first."))
    text = str(body.get("text", "")).strip()

    def run():
        # Every request starts from the session's real state (see _state_note).
        session.agent.messages.append({"role": "user", "content": _state_note(session)})
        return session.agent.send(text)

    return _respond(session, is_new, _turn(session, run))


@app.post("/api/answer")
async def answer(request: Request):
    session, is_new = _session(request)
    body = await request.json()
    if not session.pending or session.pending["kind"] != "question":
        return _respond(session, is_new, _conflict("There is no pending question."))
    text = str(body.get("answer", "")).strip()
    return _respond(session, is_new, _turn(session, lambda: session.agent.answer_question(text)))


@app.post("/api/confirm")
async def confirm(request: Request):
    session, is_new = _session(request)
    body = await request.json()
    if not session.pending or session.pending["kind"] != "confirmation":
        return _respond(session, is_new, _conflict("There is no pending confirmation."))
    approved = body.get("approved") is True
    session.note("confirmation_answered", approved=approved, **(session.pending.get("details") or {}))
    return _respond(session, is_new, _turn(session, lambda: session.agent.resolve_confirmation(approved)))


# ---------------------------------------------------------------------------
# Page 1: residual limb
# ---------------------------------------------------------------------------


def _form_edits(form: dict) -> dict:
    """The form values that differ from the standard limb, as validate_measurements arguments."""
    defaults = _form_defaults()
    edits = {}
    for name, tool_name in FIELD_TO_TOOL.items():
        value = form.get(name)
        if value is None or value == "" or (name == "side" and value == "template"):
            continue
        if isinstance(defaults.get(name), (int, float)) and isinstance(value, (int, float)):
            if abs(value - defaults[name]) < 1e-6:
                continue
        if name == "distal_shape" and value == "template":
            continue
        edits[tool_name] = value
    return edits


def _state_note(session: Session) -> str:
    """The session's current parts, so the model never picks another session's revisions."""
    m = session.measurements
    dims = ", ".join(
        f"{label} {m[key]:g} mm"
        for key, label in (("length_mm", "length"), ("proximal_circumference_mm", "P"),
                           ("mid_circumference_mm", "M"), ("distal_circumference_mm", "D"))
        if m.get(key) is not None
    )
    socket = (session.socket or {}).get("socket") or {}
    if socket.get("socket_id"):
        status = "confirmed" if session.socket_confirmed else (
            "validated" if session.socket["validation"].get("passed") else "not validated")
        socket_text = f"current socket {socket['socket_id']} (built for {socket.get('limb_revision_id')}, {status})"
    else:
        socket_text = "no socket yet"
    return (
        f"[workbench state] Current limb {session.limb['revision_id']} ({dims}); {socket_text}. "
        "Use these ids. Other revisions in list_parts are earlier work, not this patient's parts."
    )


def _tell_agent(session: Session, text: str) -> None:
    """Let the model know what the page changed outside the chat."""
    if session.agent.pending is None:
        session.agent.messages.append({"role": "user", "content": f"[workbench page] {text}"})


@app.post("/api/measurements")
async def measurements(request: Request):
    session, is_new = _session(request)
    form = await request.json()
    edits = _form_edits(form)
    with session.lock:
        checked = registry.call("validate_measurements", {**edits, "parent_revision_id": session.limb["revision_id"]})
        if not checked.ok:
            return _respond(session, is_new, JSONResponse(checked.to_dict(), status_code=422))
        built = registry.call("customize_residual_limb", {"validation_id": checked.data["validation_id"]})
        if not built.ok:
            return _respond(session, is_new, JSONResponse(built.to_dict(), status_code=422))
        rid = built.data["revision_id"]
        session.limb = {
            "revision_id": rid,
            "parent_revision_id": built.data.get("parent_revision_id"),
            "stl_url": _stl_url(rid, "residual_limb"),
        }
        session.measurements = {**_form_defaults(), **{k: v for k, v in form.items() if k in FIELD_TO_TOOL}}
        session.note("limb_built", limb=rid, edits=edits, by="form")
        _tell_agent(session, f"The measurement form built limb {rid} with these changes from the standard limb: {edits or 'none'}.")
    return _respond(session, is_new, JSONResponse({"revision": session.limb}))


def _validation_report(revision_id: str) -> dict | None:
    path = cad._revision_dir(revision_id) / "validation.json"
    return json.loads(path.read_text()) if path.is_file() else None


@app.post("/api/limb/confirm")
async def confirm_limb(request: Request):
    session, is_new = _session(request)
    body = await request.json()
    limb_id = body.get("revision_id")
    with session.lock:
        error, checked_status = _build_socket(session, limb_id, by="limb_confirm")
        if error is not None:
            return _respond(session, is_new, JSONResponse(error, status_code=422))
        socket_id = session.socket["socket"]["socket_id"]
        _tell_agent(session, f"The page confirmed limb {limb_id} and built socket {socket_id} for it "
                             f"(validate_part: {checked_status}).")
    return _respond(session, is_new, JSONResponse(session.socket))


# ---------------------------------------------------------------------------
# Page 2: socket
# ---------------------------------------------------------------------------


@app.post("/api/socket/confirm")
async def confirm_socket(request: Request):
    session, is_new = _session(request)
    body = await request.json()
    socket_id = body.get("socket_id")
    if not session.socket or session.socket["socket"]["socket_id"] != socket_id:
        return _respond(session, is_new, _conflict("That is not the current socket."))
    if not session.socket["validation"].get("passed"):
        return _respond(session, is_new, _conflict("The current socket has not passed its geometric checks."))
    session.socket_confirmed = True
    session.note("socket_confirmed", socket=socket_id)
    _tell_agent(session, f"The person accepted socket {socket_id} for printing.")
    return _respond(session, is_new, JSONResponse({}))


# ---------------------------------------------------------------------------
# Page 3: printer (read only)
# ---------------------------------------------------------------------------


@app.get("/api/printer")
def printer(request: Request):
    session, is_new = _session(request)
    return _respond(session, is_new, JSONResponse(registry.call("get_printer_status", {}).to_dict()))


def _step(flags: dict, state_text: str, session: Session, completion) -> str:
    """README section 12: printer flags first, job state text when flags are absent."""
    text = (state_text or "").lower()
    if flags.get("error") or flags.get("closedOrError") or "error" in text:
        return "Error"
    if flags.get("pausing") or text == "pausing":
        return "Pausing"
    if flags.get("paused") or text == "paused":
        return "Paused"
    if flags.get("cancelling") or text == "cancelling":
        return "Cancelled"
    if flags.get("printing"):
        session.seen_printing = True
        return "Printing"
    # A job that stopped short of 100% was cancelled (here or in OctoPrint), never finished.
    job_id = (session.job or {}).get("job_id")
    if job_id in session.cancelled_jobs or (session.seen_printing and completion is not None and completion < 100):
        return "Cancelled"
    if session.seen_printing or (completion is not None and completion >= 100):
        return "Finished"
    return "Starting"


def _read_octoprint(session: Session) -> dict:
    from tools.printer.tools import _client  # real printer only

    client = _client()
    job, conn = client.job(), client.connection()
    try:
        printer_state = client.printer()
    except Exception:
        printer_state = {}
    progress, job_info = job.get("progress") or {}, job.get("job") or {}
    flags = (printer_state.get("state") or {}).get("flags", {})
    temps = printer_state.get("temperature") or {}
    completion = progress.get("completion")
    filament = (job_info.get("filament") or {}).get("tool0") or {}
    return {
        "job_id": session.job.get("job_id") if session.job else None,
        "step": _step(flags, job.get("state"), session, completion),
        "observed_at": _now(),
        "stale": False,
        "completion": completion,
        "filepos": progress.get("filepos"),
        "print_time_s": progress.get("printTime"),
        "print_time_left_s": progress.get("printTimeLeft"),
        "file": {"name": (job_info.get("file") or {}).get("name"), "size": (job_info.get("file") or {}).get("size")}
        if (job_info.get("file") or {}).get("name") else None,
        "filament_mm": filament.get("length"),
        "port": (conn.get("current") or {}).get("port"),
        "temperatures": {k: {"actual": v.get("actual"), "target": v.get("target")} for k, v in temps.items() if k in ("tool0", "bed")} or None,
        "error": job.get("error"),
    }


def _read_fake(session: Session) -> dict:
    from tools.fakes import printer_fakes

    job = printer_fakes._jobs.get((session.job or {}).get("job_id"), {})
    state = job.get("state", "")
    if state == "failed":
        raise ConnectionError("fake printer link dropped")
    flags = {"printing": state == "printing"}
    if state == "printing" and job.get("progress", 0) < 100:
        job["progress"] = min(100, job.get("progress", 0) + 2)  # the fake advances as it is read
        if job["progress"] == 100:
            job["state"] = "completed"
    return {
        "job_id": (session.job or {}).get("job_id"),
        "step": _step(flags, state, session, job.get("progress")),
        "observed_at": _now(),
        "stale": False,
        "completion": job.get("progress"),
        "filepos": None,
        "print_time_s": None,
        "print_time_left_s": None,
        "file": None,
        "filament_mm": None,
        "port": "VIRTUAL",
        "temperatures": None,
        "error": None,
    }


def _job_gcode(session: Session) -> Path | None:
    """The G-code the slicer wrote for the session's job; real slicing only."""
    job_id = (session.job or {}).get("job_id")
    path = cad.WORKSPACE / "gcode" / f"{job_id}.gcode"
    return path if job_id and path.is_file() else None


def _add_layer(session: Session, snap: dict) -> dict:
    """Layer fields from OctoPrint's filepos, when the printer is printing this job's file."""
    snap.update(layer=None, layer_count=None, layer_z=None)
    gcode = _job_gcode(session)
    if gcode is None or (snap.get("file") or {}).get("name") != gcode.name:
        return snap
    index = gcode_layers.index_layers(gcode)
    number = gcode_layers.layer_at(index, snap.get("filepos"))
    snap["layer_count"] = len(index["layers"])
    if number is not None:
        snap["layer"], snap["layer_z"] = number, index["layers"][number - 1]["z"]
    return snap


@app.get("/api/print/layers")
def print_layers(request: Request):
    """Outer-wall paths of every layer of the started job, for the live layer view. null without G-code."""
    session, is_new = _session(request)
    gcode = _job_gcode(session) if session.started else None
    if gcode is None:
        return _respond(session, is_new, JSONResponse(None))
    index = gcode_layers.index_layers(gcode)
    body = {
        "job_id": session.job["job_id"],
        "layer_count": len(index["layers"]),
        "layers": [{"z": layer["z"], "paths": layer["paths"]} for layer in index["layers"]],
    }
    return _respond(session, is_new, JSONResponse(body))


@app.get("/api/print/snapshot")
def print_snapshot(request: Request):
    session, is_new = _session(request)
    if not session.started:
        return _respond(session, is_new, JSONResponse(None))
    try:
        snap = _add_layer(session, _read_fake(session) if FAKE_PRINTER else _read_octoprint(session))
        session.last_snapshot = snap
    except Exception as exc:
        last = session.last_snapshot or {"job_id": (session.job or {}).get("job_id"), "completion": None, "filepos": None,
                                         "print_time_s": None, "print_time_left_s": None, "file": None,
                                         "filament_mm": None, "port": None, "temperatures": None,
                                         "observed_at": None, "layer": None, "layer_count": None, "layer_z": None}
        snap = {**last, "step": "Link lost", "stale": True, "error": f"{type(exc).__name__}"}
    if snap["step"] != (session.log[-1].get("step") if session.log and session.log[-1]["event"] == "print_step" else None):
        session.note("print_step", step=snap["step"], completion=snap.get("completion"))
    return _respond(session, is_new, JSONResponse(snap))


@app.get("/api/report")
def report(request: Request):
    session, is_new = _session(request)
    limb_dims = None
    meta = cad._read_meta(session.limb["revision_id"]) or {}
    if session.limb:
        profile_path = cad._revision_dir(session.limb["revision_id"]) / "profile.json"
        if profile_path.is_file():
            limb_dims = json.loads(profile_path.read_text()).get("dimensions")
    body = {
        "clinical_use": False,
        "statement": "Nonclinical demonstration. A synthetic parametric limb resized from the "
                     "standard limb, and a socket built around it; checks are geometric and "
                     "process checks only. Not for wearing.",
        "limb": {"revision_id": session.limb["revision_id"], "edits": meta.get("edits", {}), "dimensions": limb_dims},
        "socket": session.socket["socket"] if session.socket else None,
        "socket_validation_passed": (session.socket or {}).get("validation", {}).get("passed"),
        "socket_confirmed": session.socket_confirmed,
        "job": session.job,
        "print_started": session.started,
        "last_observed_step": (session.last_snapshot or {}).get("step"),
        "last_observed_at": (session.last_snapshot or {}).get("observed_at"),
        "log": session.log,
    }
    return _respond(session, is_new, JSONResponse(body))


# ---------------------------------------------------------------------------
# Files
# ---------------------------------------------------------------------------

ROLE_TYPES = {"residual_limb": "limb", "socket_shell": "socket", "lower_leg": "socket", "engraving": "socket"}
EMPTY_STL = b"\0" * 80 + (0).to_bytes(4, "little")  # a valid binary STL with no triangles


def _write_lower_leg(socket_id: str, path: Path) -> None:
    """The standard adapter, pylon and foot under this socket, for display only.

    Not a revision: never validated, sliced or printed. Built from prosthesis defaults
    at the socket's depth, in the socket's design frame like view.stl.
    """
    from tools.cad import prosthesis

    depth = float(json.loads((cad._revision_dir(socket_id) / "profile.json").read_text())["socket_depth_mm"])
    parts = {kind: (prosthesis.build(kind, prosthesis.defaults(kind)), prosthesis.defaults(kind))
             for kind in ("adapter", "pylon", "foot")}
    placed = prosthesis.place_lower_leg(depth, parts)
    leg = cq.Compound.makeCompound([placed["adapter"], placed["pylon"], placed["foot"]])
    cq.exporters.export(leg, str(path), exportType="STL", tolerance=0.1, angularTolerance=0.15)


@app.get("/api/files/{revision_id}/{role}.stl")
def stl_file(revision_id: str, role: str):
    if role not in ROLE_TYPES or not re.fullmatch(r"[a-z]+-\d+", revision_id):
        return JSONResponse({"error": "unknown file"}, status_code=404)
    meta = cad._read_meta(revision_id)
    if meta is None or meta["part_type"] != ROLE_TYPES[role]:
        return JSONResponse({"error": "unknown file"}, status_code=404)
    folder = cad._revision_dir(revision_id)
    if role == "engraving":
        # The cut-away letters, saved when a label was engraved; empty for a plain socket.
        path = folder / "engraving.stl"
        if not path.is_file():
            return Response(EMPTY_STL, media_type="model/stl")
        return FileResponse(path, media_type="model/stl", filename=f"{revision_id}-{role}.stl")
    if role == "lower_leg":
        view = folder / "lower_leg.stl"
        if not view.is_file():
            _write_lower_leg(revision_id, view)
        return FileResponse(view, media_type="model/stl", filename=f"{revision_id}-{role}.stl")
    view = folder / "view.stl"  # design orientation; part.stl is turned for printing
    if not view.is_file():
        shape = cad.load_step_shape(folder / "part.step")
        cq.exporters.export(shape, str(view), exportType="STL", tolerance=0.1, angularTolerance=0.15)
    return FileResponse(view, media_type="model/stl", filename=f"{revision_id}-{role}.stl")
