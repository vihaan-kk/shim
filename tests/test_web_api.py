"""Workbench stage flow in agent/web_api.py: the tool guard and move_to_stage.

These call the session helpers directly, with no model, server or CAD build.
"""

import json

import pytest

from agent import web_api as w
from tools.cad import tools as cad


class Events:
    def __init__(self):
        self.seen = []

    def on_event(self, kind, payload):
        self.seen.append((kind, payload))


@pytest.fixture(autouse=True)
def workspace(tmp_path, monkeypatch):
    monkeypatch.setattr(cad, "WORKSPACE", tmp_path)
    return tmp_path


def make_session(limb_id="limb-1"):
    return w.Session(id="test", agent=Events(), measurements={}, limb={"revision_id": limb_id})


def write_meta(workspace, revision_id, **meta):
    folder = workspace / "revisions" / revision_id
    folder.mkdir(parents=True)
    (folder / "meta.json").write_text(json.dumps({"revision_id": revision_id, **meta}))


def confirmed_session():
    session = make_session()
    session.socket = {"socket": {"socket_id": "socket-2", "limb_revision_id": "limb-1"}, "validation": {"passed": True}}
    session.socket_confirmed = True
    return session


def test_prepare_print_without_revision_id_is_fixable():
    session = confirmed_session()
    # prepare_print's schema makes revision_id optional, so leaving it out is a retry, not a dead end.
    missing = w._stage_guard(session, "prepare_print", {"profile_id": "draft_028"})
    assert missing.status == "fixable" and missing.error.code == "missing_argument"
    assert "socket-2" in missing.message

    other = w._stage_guard(session, "prepare_print", {"revision_id": "socket-1", "profile_id": "draft_028"})
    assert other.status == "fatal" and other.error.code == "off_flow"

    assert w._stage_guard(session, "prepare_print", {"revision_id": "socket-2", "profile_id": "draft_028"}) is None


def test_chat_socket_edit_records_its_limb_and_moving_stage_does_not_crash(workspace, monkeypatch):
    # modify_socket's result has no limb_revision_id; the revision's meta does.
    write_meta(workspace, "socket-2", part_type="socket", limb_revision_id="limb-1")
    session = make_session()
    w._enrich(session, "modify_socket", {"status": "success", "data": {"revision_id": "socket-2"}})
    assert session.socket["socket"]["limb_revision_id"] == "limb-1"

    def no_rebuild(*args, **kwargs):
        raise AssertionError("the socket is already built for the current limb")

    monkeypatch.setattr(w, "_build_socket", no_rebuild)
    moved = w._stage_handler(session, "socket")
    assert moved.ok and moved.data["socket_id"] == "socket-2"


def test_socket_with_unknown_limb_is_rebuilt_not_a_crash(monkeypatch):
    session = make_session()
    session.socket = {"socket": {"socket_id": "socket-1"}, "validation": {"passed": False}}
    built = []

    def fake_build(session, limb_id, by):
        built.append(limb_id)
        session.socket = {"socket": {"socket_id": "socket-3", "limb_revision_id": limb_id}, "validation": {}}
        return None, None

    monkeypatch.setattr(w, "_build_socket", fake_build)
    moved = w._stage_handler(session, "socket")
    assert built == ["limb-1"]
    assert moved.ok and moved.data["socket_id"] == "socket-3"


def test_a_preview_of_the_confirmed_socket_may_be_printed(workspace):
    write_meta(workspace, "preview-1", part_type="preview", preview_of="socket-2", scale_percent=40)
    write_meta(workspace, "preview-2", part_type="preview", preview_of="socket-1", scale_percent=40)
    session = confirmed_session()
    assert w._stage_guard(session, "prepare_print", {"revision_id": "preview-1", "profile_id": "draft_028"}) is None
    stale = w._stage_guard(session, "prepare_print", {"revision_id": "preview-2", "profile_id": "draft_028"})
    assert stale.status == "fatal" and stale.error.code == "off_flow"

    session.job = {"job_id": "job_1", "revision_id": "preview-1"}
    assert w._stage_guard(session, "start_print", {"job_id": "job_1", "confirmation_id": "c"}) is None


def test_snapshot_layer_only_for_the_jobs_own_file(workspace):
    gcode = workspace / "gcode" / "job_1.gcode"
    gcode.parent.mkdir()
    gcode.write_bytes(b";LAYER_CHANGE\n;Z:0.2\nG1 X1 Y1 E1\n;LAYER_CHANGE\n;Z:0.4\nG1 X2 Y2 E2\n")
    session = confirmed_session()
    session.job = {"job_id": "job_1", "revision_id": "socket-2"}
    snap = w._add_layer(session, {"file": {"name": "job_1.gcode"}, "filepos": 40})
    assert (snap["layer"], snap["layer_count"], snap["layer_z"]) == (2, 2, 0.4)
    other = w._add_layer(session, {"file": {"name": "something_else.gcode"}, "filepos": 40})
    assert (other["layer"], other["layer_count"]) == (None, None)


def test_a_stopped_print_shows_cancelled_not_finished():
    session = confirmed_session()
    session.job = {"job_id": "job_1", "revision_id": "socket-2"}
    assert w._step({"printing": True}, "Printing", session, 30.0) == "Printing"
    assert w._step({"cancelling": True}, "Cancelling", session, 30.0) == "Cancelled"
    # Cancelled from OctoPrint's own page: idle again at 31%.
    assert w._step({"operational": True}, "Operational", session, 31.0) == "Cancelled"
    assert w._step({"operational": True}, "Operational", session, 100.0) == "Finished"

    by_agent = confirmed_session()
    by_agent.job = {"job_id": "job_2", "revision_id": "socket-2"}
    w._enrich(by_agent, "cancel_print", {"status": "success", "data": {"job_id": "job_2", "state": "cancelled"}})
    assert w._step({"operational": True}, "Operational", by_agent, None) == "Cancelled"


def test_sockets_are_fitted_to_the_current_limb_only():
    session = make_session("limb-50")
    stale = w._stage_guard(session, "fit_socket_to_limb", {"socket_revision_id": "socket-36", "limb_revision_id": "limb-49"})
    assert stale.status == "fixable" and stale.error.code == "not_current_limb"
    assert stale.error.valid_range == ["limb-50"]
    assert w._stage_guard(session, "fit_socket_to_limb", {"socket_revision_id": "socket-36", "limb_revision_id": "limb-50"}) is None
    assert w._stage_guard(session, "check_fit", {"socket_revision_id": "socket-36", "limb_revision_id": "limb-49"}).status == "fixable"


def test_each_turn_names_the_sessions_own_parts():
    session = confirmed_session()
    session.measurements = {"length_mm": 140, "proximal_circumference_mm": 287.86, "mid_circumference_mm": None,
                            "distal_circumference_mm": 257.86}
    note = w._state_note(session)
    assert note.startswith("[workbench state] Current limb limb-1 (length 140 mm, P 287.86 mm, D 257.86 mm)")
    assert "current socket socket-2 (built for limb-1, confirmed)" in note
    assert "no socket yet" in w._state_note(make_session())


def test_a_session_whose_files_were_deleted_is_replaced(workspace, monkeypatch):
    class Cookies:
        cookies = {w.COOKIE: "old"}

    write_meta(workspace, "limb-1", part_type="limb")
    kept = make_session("limb-1")
    monkeypatch.setitem(w._sessions, "old", kept)
    assert w._session(Cookies()) == (kept, False)

    gone = make_session("limb-9")  # its revision folder no longer exists
    monkeypatch.setitem(w._sessions, "old", gone)
    fresh = make_session("limb-2")
    monkeypatch.setattr(w, "_new_session", lambda: fresh)
    assert w._session(Cookies()) == (fresh, True)
    assert "old" not in w._sessions


def test_lower_leg_hangs_under_the_socket_for_display(workspace):
    socket_id = cad.create_part("socket").data["revision_id"]
    path = workspace / "lower_leg.stl"
    w._write_lower_leg(socket_id, path)
    data = path.read_bytes()
    count = int.from_bytes(data[80:84], "little")
    assert count > 0
    import numpy as np

    rows = np.frombuffer(data[84:84 + count * 50], dtype=np.dtype([("n", "<3f4"), ("v", "<9f4"), ("a", "<u2")]))
    points = rows["v"].reshape(-1, 3)
    # From the socket's closed end (152 mm) to the floor (342 mm), toe pointing anterior (+Y).
    assert round(float(points[:, 2].min())) == 152 and round(float(points[:, 2].max())) == 342
    assert points[:, 1].max() > abs(points[:, 1].min())
    # Display only: no revision was made for it.
    assert [m["revision_id"] for m in cad._all_meta()] == [socket_id]
