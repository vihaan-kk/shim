"""Real printer tools. Registered under the same names as tools/fakes/printer_fakes.py."""

import os

from common.result import fatal, success
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
