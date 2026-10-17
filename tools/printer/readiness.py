"""check_printer_readiness (README section 8.4).

Ready only when OctoPrint is operational, the port is the virtual port, and the
state is not printing, paused, or error. A physical serial port fails readiness.
"""
from __future__ import annotations

from common.result import ToolResult, fatal, fixable, success
from tools.printer.octoprint_client import OctoPrintClient, OctoPrintError

BLOCKING_STATES = ("printing", "paused", "error", "cancelling", "pausing")


def check_printer_readiness(client: OctoPrintClient, expected_port: str = "VIRTUAL") -> ToolResult:
    if not isinstance(expected_port, str) or not expected_port:
        return fixable("bad_argument", "expected_port must be a non-empty string", valid="VIRTUAL")
    try:
        conn = client.connection()
        printer = client.printer()
        job = client.job()
    except OctoPrintError as e:
        # A 409 from /api/printer means the printer is not operational.
        if e.status == 409:
            return success("Printer is not operational.", ready=False, reasons=["not_operational"])
        return fatal("printer_unreachable", str(e))

    current = (conn or {}).get("current", {})
    state = str(current.get("state", "")).lower()
    port = current.get("port")
    flags = ((printer or {}).get("state") or {}).get("flags", {})
    job_state = (job or {}).get("state", "")

    reasons = []
    if not flags.get("operational", False):
        reasons.append("not_operational")
    if port != expected_port:
        reasons.append("port_mismatch")
    if any(s in state for s in BLOCKING_STATES) or any(
        flags.get(k) for k in ("printing", "paused", "error", "closedOrError")
    ):
        reasons.append("busy_or_error")

    ready = not reasons
    summary = {
        "connection": {"state": current.get("state"), "port": port},
        "printer": {"flags": flags},
        "job": {"state": job_state, "completion": ((job or {}).get("progress") or {}).get("completion")},
    }
    msg = "Virtual printer is ready." if ready else "Printer is not ready: " + ", ".join(reasons)
    return success(msg, ready=ready, reasons=reasons, **summary)
