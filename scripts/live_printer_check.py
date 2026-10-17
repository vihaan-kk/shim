"""Run the real printer tools against a running OctoPrint Virtual Printer.

Usage: set -a && . ./.env && set +a && uv run python scripts/live_printer_check.py

Slicing is skipped: a tiny hand-made G-code file is registered as a sliced job.
This prints on the virtual printer only; readiness refuses any other port.
"""
import tempfile
import time
from pathlib import Path

from common import confirmations
from tools.printer import tools as pt

GCODE = "\n".join(["G28", "G90"] + [f"G1 X{i} Y{i} F3000\nG4 P500" for i in range(1, 400)]) + "\n"


def show(label, result):
    d = result.to_dict()
    print(f"{label:<22} {d['status']:<8} {d['message']}")
    if d["error"]:
        print(f"{'':<22} error: {d['error']['code']}")
    return result


show("get_printer_status", pt.get_printer_status())

path = Path(tempfile.mkdtemp()) / "job_live.gcode"
path.write_text(GCODE)
pt._jobs["job_live"] = {"revision_id": "live", "profile_id": "draft_028", "gcode": path, "state": "sliced"}

show("start (no confirm)", pt.start_print("job_live", "conf_fake"))
conf = confirmations.create("start_print", "job_live", "live test")
show("start_print", pt.start_print("job_live", conf))
show("start again", pt.start_print("job_live", confirmations.create("start_print", "job_live", "again")))
for _ in range(3):
    time.sleep(2)
    show("get_job_progress", pt.get_job_progress("job_live"))
show("cancel_print", pt.cancel_print("job_live"))
time.sleep(2)
show("get_printer_status", pt.get_printer_status())
