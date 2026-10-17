import subprocess

import pytest

from common import confirmations
from tests.real_printer import pt
from tools.printer.octoprint_client import OctoPrintError

GCODE = "G1 X1\n; filament used [mm] = 18400.0\n; estimated printing time (normal mode) = 1h 10m 5s\n"


class FakeOcto:
    def __init__(self):
        self.calls = []
        self.job_state = {"state": "Operational", "job": {"file": {"name": None}}, "progress": {"completion": None}}
        self.flags = {"operational": True}
        self.port = "VIRTUAL"
        self.fail_on = None

    def _do(self, name):
        self.calls.append(name)
        if self.fail_on == name:
            raise OctoPrintError(f"{name} failed")

    def connection(self):
        self._do("connection")
        return {"current": {"state": "Operational", "port": self.port}}

    def printer(self):
        return {"state": {"flags": self.flags}}

    def job(self):
        self._do("job")
        return self.job_state

    def upload_file(self, name, content):
        self._do("upload")
        self.uploaded = name

    def select_file(self, loc, name):
        self._do("select")

    def start_job(self):
        self._do("start")
        self.job_state = {"state": "Printing", "job": {"file": {"name": self.uploaded}},
                          "progress": {"completion": 10.2, "printTimeLeft": 600}}

    def cancel_job(self):
        self._do("cancel")
        self.job_state = {"state": "Cancelling", "job": {}, "progress": {}}


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(pt, "WORKSPACE", tmp_path)
    prof = tmp_path / "profiles"
    prof.mkdir()
    for p in pt.PROFILES:
        (prof / f"{p}.ini").write_text("")
    monkeypatch.setattr(pt, "PROFILE_DIR", prof)
    rev = tmp_path / "revisions" / "r1"
    rev.mkdir(parents=True)
    (rev / "part.stl").write_text("solid")
    (rev / "validated").write_text("")

    def fake_slicer(stl, profile, gcode):
        gcode.write_text(GCODE)
        return subprocess.CompletedProcess([], 0, "", "")

    monkeypatch.setattr(pt, "_run_slicer", fake_slicer)
    octo = FakeOcto()
    monkeypatch.setattr(pt, "_client", lambda: octo)
    pt._jobs.clear()
    confirmations.reset()
    return octo


def sliced_job():
    r = pt.slice_revision("r1", "draft_028")
    assert r.ok, r.to_dict()
    return r.data["job_id"]


def test_slice_parses_stats(env):
    r = pt.slice_revision("r1", "demo_020")
    assert r.data["estimated_seconds"] == 4205 and r.data["filament_m"] == 18.4


def test_slice_refuses_unvalidated_and_unknown(env, tmp_path):
    (tmp_path / "revisions" / "r1" / "validated").unlink()
    assert pt.slice_revision("r1", "draft_028").error.code == "not_validated"
    assert pt.slice_revision("r9", "draft_028").error.code == "unknown_revision"
    assert pt.slice_revision("../x", "draft_028").error.code == "unknown_revision"


def test_slice_missing_profile_and_slicer(env, tmp_path, monkeypatch):
    (tmp_path / "profiles" / "draft_028.ini").unlink()
    one = pt.slice_revision("r1", "draft_028")  # only demo_020 is left
    assert one.status == "fixable" and one.error.valid_range == ["demo_020"]
    (tmp_path / "profiles" / "demo_020.ini").unlink()
    none = pt.slice_revision("r1", "draft_028")  # nothing installed: not retryable
    assert none.status == "fatal" and none.error.code == "profile_missing"
    (tmp_path / "profiles" / "demo_020.ini").write_text("")

    def boom(*a):
        raise FileNotFoundError

    monkeypatch.setattr(pt, "_run_slicer", boom)
    assert pt.slice_revision("r1", "demo_020").error.code == "slicer_missing"


def test_start_needs_valid_confirmation(env):
    job = sliced_job()
    assert pt.start_print(job, "conf_nope").error.code == "confirmation_invalid"
    other = confirmations.create("start_print", "job_other", "x")
    assert pt.start_print(job, other).error.code == "confirmation_invalid"
    assert "upload" not in env.calls


def test_start_verified_then_second_start_refused(env):
    job = sliced_job()
    conf = confirmations.create("start_print", job, "print")
    r = pt.start_print(job, conf)
    assert r.ok and r.data["verified"] is True
    assert env.calls.index("upload") < env.calls.index("select") < env.calls.index("start")
    conf2 = confirmations.create("start_print", job, "again")
    assert pt.start_print(job, conf2).error.code == "duplicate_start"


def test_start_blocked_when_printer_not_ready(env):
    env.port = "/dev/ttyUSB0"
    job = sliced_job()
    r = pt.start_print(job, confirmations.create("start_print", job, "p"))
    assert r.error.code == "printer_not_ready" and "upload" not in env.calls


def test_start_failure_midway_is_unverified_and_not_retryable(env):
    job = sliced_job()
    env.fail_on = "start"
    r = pt.start_print(job, confirmations.create("start_print", job, "p"))
    assert r.error.code == "unverified"
    env.fail_on = None
    assert pt.start_print(job, confirmations.create("start_print", job, "p")).error.code == "duplicate_start"


def test_progress_and_connection_loss(env):
    job = sliced_job()
    pt.start_print(job, confirmations.create("start_print", job, "p"))
    r = pt.get_job_progress(job)
    assert r.ok and r.data["completion"] == 10 and r.data["time_left_s"] == 600
    env.fail_on = "job"
    r = pt.get_job_progress(job)
    assert r.error.code == "connection_lost" and r.data["state"] == "unknown"


def test_progress_completed(env):
    job = sliced_job()
    pt.start_print(job, confirmations.create("start_print", job, "p"))
    env.job_state = {"state": "Operational", "progress": {"completion": 100.0}}
    assert pt.get_job_progress(job).data["state"] == "completed"


def test_cancel_reads_back(env):
    job = sliced_job()
    pt.start_print(job, confirmations.create("start_print", job, "p"))
    assert pt.cancel_print(job).data["state"] == "cancelled"
    assert pt.cancel_print(job).error.code == "no_active_job"


def test_cancel_unconfirmed(env):
    job = sliced_job()
    pt.start_print(job, confirmations.create("start_print", job, "p"))
    env.cancel_job = lambda: None  # printer ignores it, still Printing
    assert pt.cancel_print(job).error.code == "cancel_not_delivered"


# ----- prepare_print -----

def add_revision(tmp_path, name, validated=True):
    d = tmp_path / "revisions" / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "part.stl").write_text("solid")
    if validated:
        (d / "validated").write_text("")


def test_prepare_uses_only_ready_part_and_slices(env):
    r = pt.prepare_print("draft_028")
    assert r.ok and r.data["reused"] is False and r.data["job_id"] in pt._jobs
    assert "request_confirmation" in r.message


def test_prepare_reuses_existing_slice(env):
    first = pt.prepare_print("draft_028", "r1")
    again = pt.prepare_print("draft_028", "r1")
    assert again.data["reused"] is True and again.data["job_id"] == first.data["job_id"]
    other_profile = pt.prepare_print("demo_020", "r1")
    assert other_profile.data["reused"] is False


def test_prepare_reslices_when_part_changed(env, tmp_path):
    import os
    first = pt.prepare_print("draft_028", "r1")
    stl = tmp_path / "revisions" / "r1" / "part.stl"
    os.utime(stl, (stl.stat().st_atime, pt._jobs[first.data["job_id"]]["gcode"].stat().st_mtime + 10))
    assert pt.prepare_print("draft_028", "r1").data["reused"] is False


def test_prepare_ambiguous_lists_options(env, tmp_path):
    add_revision(tmp_path, "r2")
    r = pt.prepare_print("draft_028")
    assert r.error.code == "ambiguous_part" and r.error.valid_range == ["r1", "r2"]


def test_prepare_nothing_ready(env, tmp_path):
    (tmp_path / "revisions" / "r1" / "validated").unlink()
    assert pt.prepare_print("draft_028").error.code == "no_printable_part"


def test_prepare_passes_slice_errors_through(env, tmp_path):
    add_revision(tmp_path, "r3", validated=False)
    assert pt.prepare_print("draft_028", "r3").error.code == "not_validated"
    assert pt.prepare_print("draft_028", "nope").error.code == "unknown_revision"


def test_prepare_then_start_needs_confirmation(env):
    job = pt.prepare_print("draft_028").data["job_id"]
    assert pt.start_print(job, "conf_x").error.code == "confirmation_invalid"
    assert "upload" not in env.calls
