"""Fake printer tools with the agreed names, arguments and result shapes.

They let the agent loop be built and tested before the real printer tools
exist. Behaviour copies what we verified on OctoPrint 1.11.8:

- slice refuses a revision that has not passed validation
- start_print needs a confirmation_id for that job, and refuses a second start
- get_job_progress reports "estimating" until a time estimate exists
- FAKE_PRINTER_FAULT=drop simulates a connection drop mid-print

Revision ids starting with "unvalidated" stand for revisions that did not pass
validate_geometry.
"""

import os
import secrets

from common import confirmations
from common.result import fatal, fixable, success
from tools.registry import tool

PROFILES = ["draft_028", "demo_020"]

_printer = {"connection": "Operational", "busy_job": None}
_jobs: dict[str, dict] = {}


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
    busy = _printer["busy_job"]
    return success(
        f"Printer is {_printer['connection']}" + (f", printing {busy}." if busy else ", idle."),
        {"connection": _printer["connection"], "printing_job_id": busy},
    )


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
    if revision_id.startswith("unvalidated"):
        return fixable(
            code="not_validated",
            reason=f"Revision {revision_id} has not passed validate_geometry.",
            message="Validate this revision before slicing.",
            hint="Call validate_geometry on this revision first.",
        )
    job_id = "job_" + secrets.token_hex(3)
    minutes = 42 if profile_id == "draft_028" else 71
    _jobs[job_id] = {"revision_id": revision_id, "state": "sliced", "progress": 0}
    return success(
        f"Sliced {revision_id} with {profile_id}: about {minutes} min, 18.4 m of filament.",
        {
            "job_id": job_id,
            "revision_id": revision_id,
            "profile_id": profile_id,
            "estimated_seconds": minutes * 60,
            "filament_m": 18.4,
        },
    )


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
def prepare_print(profile_id: str, revision_id: str = "r1"):
    for job_id, job in _jobs.items():
        if job["revision_id"] == revision_id and job["state"] == "sliced":
            return success(
                f"Reusing the existing slice of {revision_id}. Next: request_confirmation for start_print.",
                {"job_id": job_id, "revision_id": revision_id, "profile_id": profile_id, "reused": True},
            )
    return slice_revision(revision_id, profile_id)


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
        return fixable(
            code="unknown_job",
            reason=f"No sliced job {job_id}.",
            message="Use a job_id returned by slice.",
            valid_range=sorted(_jobs),
        )
    if _printer["busy_job"] or job["state"] in ("printing", "completed"):
        return fatal(
            code="duplicate_start",
            reason=f"Job {job_id} is {job['state']}; the printer is busy with {_printer['busy_job']}.",
            message="Do not start again. Report the current job state to the user.",
        )
    if _printer["connection"] != "Operational":
        return fatal(
            code="printer_not_operational",
            reason=f"Printer connection is {_printer['connection']}.",
            message="The printer is not available. Tell the user.",
        )
    problem = confirmations.consume(confirmation_id, "start_print", job_id)
    if problem:
        return fixable(
            code="confirmation_invalid",
            reason=problem,
            message="Ask the user to approve this print with request_confirmation.",
        )
    job["state"] = "printing"
    _printer["busy_job"] = job_id
    return success(
        f"Print command accepted for {job_id}. Printing has not been verified yet; check get_job_progress.",
        {"job_id": job_id, "state": "Printing", "verified": False},
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
        return fixable(
            code="unknown_job",
            reason=f"No job {job_id}.",
            message="Use a job_id returned by slice.",
            valid_range=sorted(_jobs),
        )
    if job["state"] == "printing" and os.environ.get("FAKE_PRINTER_FAULT") == "drop" and job["progress"] >= 25:
        job["state"] = "failed"
        _printer["connection"] = "Closed"
        _printer["busy_job"] = None
        return fatal(
            code="connection_lost",
            reason="Offline after error: the printer connection dropped mid-print.",
            message="The print failed and cannot resume. Tell the user and ask before reprinting.",
            data={"job_id": job_id, "state": "Offline after error", "completion": job["progress"]},
        )
    if job["state"] == "printing":
        job["progress"] = min(100, job["progress"] + 25)
        if job["progress"] == 100:
            job["state"] = "completed"
            _printer["busy_job"] = None
    time_left = None if job["progress"] <= 25 else (100 - job["progress"]) * 30
    return success(
        f"Job {job_id}: {job['state']}, {job['progress']}% done"
        + (", time left estimating." if time_left is None and job["state"] == "printing" else "."),
        {
            "job_id": job_id,
            "state": job["state"],
            "completion": job["progress"],
            "time_left_s": time_left if time_left is not None else "estimating",
            "next_check_after_s": 30,
        },
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
    if job is None or job["state"] != "printing":
        return fixable(
            code="no_active_job",
            reason=f"{job_id} is not printing.",
            message="There is nothing to cancel. Check get_printer_status.",
        )
    job["state"] = "cancelled"
    _printer["busy_job"] = None
    return success(f"Cancelled {job_id}.", {"job_id": job_id, "state": "cancelled"})


def reset() -> None:
    """Return the fake printer to idle. Used by tests."""
    _printer.update(connection="Operational", busy_job=None)
    _jobs.clear()
