"""Real printer tools. Registered under the same names as tools/fakes/printer_fakes.py."""

import os
import re
import secrets
import shutil
import subprocess
from pathlib import Path

from common import confirmations
from common.result import SUCCESS, fatal, fixable, success
from tools.printer.octoprint_client import OctoPrintClient, OctoPrintError
from tools.registry import tool

EXPECTED_PORT = "VIRTUAL"
BUSY_FLAGS = ("printing", "paused", "error", "closedOrError", "cancelling", "pausing")


def _client() -> OctoPrintClient:
    return OctoPrintClient(
        os.environ.get("OCTOPRINT_URL", "http://localhost:5001"),
        os.environ.get("OCTOPRINT_API_KEY", ""),
    )


def read_printer_status(client: OctoPrintClient, expected_port: str = EXPECTED_PORT):
    """Ready only when operational, on the virtual port, and not printing, paused or in error."""
    try:
        conn = client.connection()
        job = client.job()
        try:
            flags = (client.printer().get("state") or {}).get("flags", {})
        except OctoPrintError as e:
            if e.status != 409:  # 409 means the printer is not operational
                raise
            flags = {"operational": False}
    except OctoPrintError as e:
        return fatal(
            code="printer_unreachable",
            reason=str(e),
            message="Could not read the printer. Do not assume it is idle or printing.",
            hint="Tell the user the printer link is down; do not call start_print.",
        )

    current = (conn or {}).get("current", {})
    port = current.get("port")
    reasons = []
    if not flags.get("operational", False):
        reasons.append("not_operational")
    if port != expected_port:
        reasons.append("port_mismatch")
    if any(flags.get(f) for f in BUSY_FLAGS):
        reasons.append("busy_or_error")

    state = current.get("state")
    ready = not reasons
    return success(
        f"Printer is {state}, " + ("ready." if ready else "not ready: " + ", ".join(reasons) + "."),
        {
            "connection": state,
            "port": port,
            "ready": ready,
            "reasons": reasons,
            "job_state": (job or {}).get("state"),
            "completion": ((job or {}).get("progress") or {}).get("completion"),
        },
    )


@tool(
    name="get_printer_status",
    description=(
        "Read the virtual printer's connection and state. Use before start_print, "
        "and whenever the printer state is unclear. To see how far a running job "
        "has got, use get_job_progress instead."
    ),
    parameters={"type": "object", "properties": {}, "required": []},
)
def get_printer_status():
    return read_printer_status(_client())


# ---------------------------------------------------------------------------
# Slicing, starting, monitoring and cancelling a job
# ---------------------------------------------------------------------------

PROFILES = ["draft_028", "demo_020"]
REPO_ROOT = Path(__file__).resolve().parents[2]
WORKSPACE = Path(os.environ.get("WORKSPACE_DIR", REPO_ROOT / "workspace"))
PROFILE_DIR = Path(__file__).resolve().parent / "profiles"
MACOS_SLICER = "/Applications/PrusaSlicer.app/Contents/MacOS/PrusaSlicer"
SLICER_BIN = os.environ.get("PRUSASLICER_BIN") or shutil.which("prusa-slicer") or MACOS_SLICER

# Job ledger: what this process has sliced and sent. Printer state is always
# read back from OctoPrint; the ledger only stops a second start.
# states: sliced -> sent -> printing | unknown -> completed | cancelled | failed
_jobs: dict = {}


def _revision_stl(revision_id: str) -> Path:
    """workspace/revisions/<revision_id>/part.stl (layout to be confirmed with the CAD tools)."""
    return WORKSPACE / "revisions" / revision_id / "part.stl"


def _is_validated(revision_id: str) -> bool:
    """validate_geometry is expected to leave workspace/revisions/<id>/validated when it passes."""
    return (WORKSPACE / "revisions" / revision_id / "validated").exists()


def _run_slicer(stl: Path, profile: Path, gcode: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [SLICER_BIN, "--export-gcode", "--load", str(profile), "--output", str(gcode), str(stl)],
        capture_output=True,
        text=True,
        timeout=300,
    )


_DURATION = re.compile(r"(\d+)\s*([dhms])")
_UNIT_S = {"d": 86400, "h": 3600, "m": 60, "s": 1}


def parse_gcode_stats(gcode_text: str) -> dict:
    """Read time and filament from PrusaSlicer's trailing comments. Missing values are None."""
    stats = {"estimated_seconds": None, "filament_m": None}
    m = re.search(r"; estimated printing time \(normal mode\) = (.+)", gcode_text)
    if m:
        stats["estimated_seconds"] = sum(int(n) * _UNIT_S[u] for n, u in _DURATION.findall(m.group(1)))
    m = re.search(r"; filament used \[mm\] = ([\d.]+)", gcode_text)
    if m:
        stats["filament_m"] = round(float(m.group(1)) / 1000, 2)
    return stats


@tool(
    name="slice",
    description=(
        "Turn a validated part revision into G-code and report estimated print "
        "time and filament. Use only after validate_geometry passed for this "
        "revision. Slicing does not start a print; use start_print for that."
    ),
    parameters={
        "type": "object",
        "properties": {
            "revision_id": {"type": "string", "description": "Revision that passed validate_geometry."},
            "profile_id": {
                "type": "string",
                "enum": PROFILES,
                "description": "draft_028 is faster; demo_020 is finer.",
            },
        },
        "required": ["revision_id", "profile_id"],
    },
)
def slice_revision(revision_id: str, profile_id: str):
    if profile_id not in PROFILES:
        return fixable(
            code="unknown_profile",
            reason=f"No profile {profile_id!r}.",
            message="Use one of the listed profiles.",
            valid_range=PROFILES,
        )
    # revision_id comes from the model: keep it a plain name before it touches a path
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", revision_id) or revision_id.startswith("."):
        return fixable(
            code="unknown_revision",
            reason="revision_id must be an id returned by a CAD tool.",
            message="Use a revision_id returned by a CAD tool.",
        )
    stl = _revision_stl(revision_id)
    if not stl.is_file():
        return fixable(
            code="unknown_revision",
            reason=f"No exported part for revision {revision_id}.",
            message="Use a revision_id returned by export_part.",
        )
    if not _is_validated(revision_id):
        return fixable(
            code="not_validated",
            reason=f"Revision {revision_id} has not passed validate_geometry.",
            message="Validate this revision before slicing.",
            hint="Call validate_geometry on this revision first.",
        )
    profile = PROFILE_DIR / f"{profile_id}.ini"
    if not profile.is_file():
        installed = [p for p in PROFILES if (PROFILE_DIR / f"{p}.ini").is_file()]
        if installed:
            return fixable(
                code="profile_missing",
                reason=f"Profile {profile_id} is not installed.",
                message="Use an installed profile.",
                valid_range=installed,
            )
        return fatal(
            code="profile_missing",
            reason="No slicer profiles are installed, so no profile can be used.",
            message="Slicing is not set up on this machine, so nothing can be sliced or printed. "
                    "Tell the user this; do not offer another profile.",
        )

    job_id = "job_" + secrets.token_hex(3)
    gcode = WORKSPACE / "gcode" / f"{job_id}.gcode"
    gcode.parent.mkdir(parents=True, exist_ok=True)
    try:
        proc = _run_slicer(stl, profile, gcode)
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        code = "slicer_missing" if isinstance(e, FileNotFoundError) else "slicer_timeout"
        return fatal(code=code, reason=f"{type(e).__name__} running {SLICER_BIN}.",
                     message="The slicer could not run. Tell the user.")
    if proc.returncode != 0 or not gcode.is_file():
        tail = (proc.stderr or proc.stdout or "").strip()[-300:]
        return fatal(code="slicer_failed", reason=tail or f"slicer exited {proc.returncode}",
                     message="The slicer rejected this part. Tell the user; do not retry unchanged.")

    stats = parse_gcode_stats(gcode.read_text(errors="replace")[-300000:])
    _jobs[job_id] = {"revision_id": revision_id, "profile_id": profile_id, "gcode": gcode, "state": "sliced"}
    est = stats["estimated_seconds"]
    return success(
        f"Sliced {revision_id} with {profile_id}"
        + (f": about {round(est / 60)} min" if est else ": time estimate unavailable")
        + (f", {stats['filament_m']} m of filament." if stats["filament_m"] is not None else "."),
        {"job_id": job_id, "revision_id": revision_id, "profile_id": profile_id,
         "estimated_seconds": est, "filament_m": stats["filament_m"]},
    )


def _unknown_job(job_id: str):
    return fixable(
        code="unknown_job",
        reason=f"No sliced job {job_id}.",
        message="Use a job_id returned by slice.",
        valid_range=sorted(_jobs),
    )


@tool(
    name="start_print",
    description=(
        "Upload a sliced job to the printer and start it. Requires a confirmation_id "
        "from request_confirmation for this job_id; never call it without one. If a "
        "print failed, ask the user and get a new confirmation before printing again."
    ),
    parameters={
        "type": "object",
        "properties": {
            "job_id": {"type": "string", "description": "job_id returned by slice."},
            "confirmation_id": {"type": "string", "description": "Returned by request_confirmation."},
        },
        "required": ["job_id", "confirmation_id"],
    },
)
def start_print(job_id: str, confirmation_id: str):
    job = _jobs.get(job_id)
    if job is None:
        return _unknown_job(job_id)
    if job["state"] != "sliced":
        return fatal(
            code="duplicate_start",
            reason=f"Job {job_id} is {job['state']}.",
            message="Do not start again. Report the current job state to the user.",
        )
    problem = confirmations.check(confirmation_id, "start_print", job_id)
    if problem:
        return fixable(
            code="confirmation_invalid",
            reason=problem,
            message="Ask the user to approve this print with request_confirmation.",
        )

    client = _client()
    status = read_printer_status(client)
    if status.status != "success":
        return fatal(code="printer_unreachable", reason=status.error.reason,
                     message="The printer could not be read. Tell the user; do not retry.")
    if not status.data["ready"]:
        return fatal(
            code="printer_not_ready",
            reason="Printer is not ready: " + ", ".join(status.data["reasons"]) + ".",
            message="The printer is not available. Tell the user.",
        )

    confirmations.consume(confirmation_id, "start_print", job_id)
    job["state"] = "sent"  # from here on a second start is refused, whatever happens next
    name = f"{job_id}.gcode"
    try:
        client.upload_file(name, job["gcode"].read_bytes())
        client.select_file("local", name)
        client.start_job()
        observed = client.job()
    except (OctoPrintError, OSError) as e:
        job["state"] = "unknown"
        return fatal(
            code="unverified",
            reason=str(e),
            message="The start command may or may not have reached the printer. Do not start again; "
                    "check get_printer_status and tell the user.",
        )

    state = str((observed or {}).get("state", ""))
    file_name = (((observed or {}).get("job") or {}).get("file") or {}).get("name")
    if state.lower() in ("printing", "starting") and file_name == name:
        job["state"] = "printing"
        return success(
            f"Print of {job_id} started and confirmed by the printer ({state}).",
            {"job_id": job_id, "state": state, "verified": True},
        )
    job["state"] = "unknown"
    return fatal(
        code="unverified",
        reason=f"Start was sent but the printer reports state {state!r} for file {file_name!r}.",
        message="Printing is not confirmed. Do not start again; tell the user.",
    )


@tool(
    name="get_job_progress",
    description=(
        "Read a print job's state and completion. Use after start_print and when "
        "the user asks how a print is going. A job is only finished when this "
        "reports completed."
    ),
    parameters={
        "type": "object",
        "properties": {"job_id": {"type": "string"}},
        "required": ["job_id"],
    },
)
def get_job_progress(job_id: str):
    job = _jobs.get(job_id)
    if job is None:
        return _unknown_job(job_id)
    if job["state"] == "sliced":
        return success(f"Job {job_id} is sliced and has not been started.",
                       {"job_id": job_id, "state": "sliced", "completion": 0})
    try:
        observed = _client().job()
    except OctoPrintError as e:
        job["state"] = "unknown"
        return fatal(
            code="connection_lost",
            reason=str(e),
            message="The printer could not be read, so the job state is unknown. Tell the user; "
                    "do not assume it finished or failed.",
            data={"job_id": job_id, "state": "unknown"},
        )

    state = str((observed or {}).get("state", ""))
    progress = (observed or {}).get("progress") or {}
    completion = progress.get("completion")
    completion = None if completion is None else round(completion)
    low = state.lower()
    if "offline" in low or "error" in low:
        job["state"] = "failed"
        return fatal(
            code="connection_lost",
            reason=state,
            message="The print failed and cannot resume. Tell the user and ask before reprinting.",
            data={"job_id": job_id, "state": state, "completion": completion},
        )
    if low == "printing":
        job["state"] = "printing"
    elif low == "operational" and job["state"] == "printing":
        job["state"] = "completed" if completion == 100 else "unknown"
    left = progress.get("printTimeLeft")
    return success(
        f"Job {job_id}: {job['state']}" + (f", {completion}% done." if completion is not None else "."),
        {"job_id": job_id, "state": job["state"], "printer_state": state, "completion": completion,
         "time_left_s": left if left is not None else "estimating", "next_check_after_s": 30},
    )


@tool(
    name="cancel_print",
    description=(
        "Cancel the job that is printing. Use only when the user asks to stop. "
        "To check on a job without stopping it, use get_job_progress."
    ),
    parameters={
        "type": "object",
        "properties": {"job_id": {"type": "string"}},
        "required": ["job_id"],
    },
)
def cancel_print(job_id: str):
    job = _jobs.get(job_id)
    if job is None or job["state"] not in ("printing", "sent", "unknown"):
        return fixable(
            code="no_active_job",
            reason=f"{job_id} is not printing.",
            message="There is nothing to cancel. Check get_printer_status.",
        )
    client = _client()
    try:
        client.cancel_job()
        observed = client.job()
    except OctoPrintError as e:
        return fatal(
            code="cancel_not_delivered",
            reason=str(e),
            message="The cancel could not be confirmed; the print may still be running. Tell the user.",
        )
    state = str((observed or {}).get("state", ""))
    if state.lower() in ("cancelling", "operational"):
        job["state"] = "cancelled"
        return success(f"Cancelled {job_id} (printer reports {state}).", {"job_id": job_id, "state": "cancelled"})
    return fatal(
        code="cancel_not_delivered",
        reason=f"Printer still reports {state!r} after cancel.",
        message="The cancel is not confirmed; the print may still be running. Tell the user.",
    )


# ---------------------------------------------------------------------------
# prepare_print: find the part's file, slice if needed, stop before the print
# ---------------------------------------------------------------------------


def _printable_revisions() -> list:
    """Revisions that have an exported part and passed validation."""
    root = WORKSPACE / "revisions"
    if not root.is_dir():
        return []
    return sorted(
        d.name for d in root.iterdir() if (d / "part.stl").is_file() and (d / "validated").exists()
    )


def _reusable_job(revision_id: str, profile_id: str):
    """A job already sliced from this revision and profile, with G-code newer than the part."""
    stl = _revision_stl(revision_id)
    for job_id, job in _jobs.items():
        if (
            job["revision_id"] == revision_id
            and job["profile_id"] == profile_id
            and job["state"] == "sliced"
            and job["gcode"].is_file()
            and job["gcode"].stat().st_mtime >= stl.stat().st_mtime
        ):
            return job_id, job
    return None, None


@tool(
    name="prepare_print",
    description=(
        "Get a part ready to print: find its exported file, slice it if it has not "
        "been sliced yet, and return a job_id with estimated time and filament. Use "
        "this when the user asks to print a part. It does not start the print: next "
        "call request_confirmation for start_print with the returned job_id, then "
        "start_print. If revision_id is left out, the one validated part is used; "
        "if several exist, ask the user which."
    ),
    parameters={
        "type": "object",
        "properties": {
            "revision_id": {"type": "string", "description": "Part revision to print. Optional if only one is ready."},
            "profile_id": {
                "type": "string",
                "enum": PROFILES,
                "description": "draft_028 is faster; demo_020 is finer. Ask the user; do not choose for them.",
            },
        },
        "required": ["profile_id"],
    },
)
def prepare_print(profile_id: str, revision_id: str = ""):
    ready = _printable_revisions()
    if not revision_id:
        if not ready:
            return fixable(
                code="no_printable_part",
                reason="No exported, validated part was found.",
                message="There is nothing ready to print. Tell the user a part must be created, "
                        "validated and exported first.",
            )
        if len(ready) > 1:
            return fixable(
                code="ambiguous_part",
                reason="More than one part is ready to print.",
                message="Ask the user which revision to print.",
                valid_range=ready,
            )
        revision_id = ready[0]

    job_id, job = _reusable_job(revision_id, profile_id)
    if job is not None:
        return success(
            f"Reusing the existing slice of {revision_id} ({profile_id}). "
            "Next: request_confirmation for start_print with this job_id.",
            {"job_id": job_id, "revision_id": revision_id, "profile_id": profile_id, "reused": True},
        )

    sliced = slice_revision(revision_id, profile_id)
    if sliced.status != SUCCESS:
        return sliced
    sliced.data["reused"] = False
    return success(
        sliced.message + " Next: request_confirmation for start_print with this job_id.",
        sliced.data,
    )
