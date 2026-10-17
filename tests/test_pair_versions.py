"""Version relationship between a socket's design limb and the limb being compared."""

from tools.cad.align_limb_socket import align_limb_socket, relationship_record
from tools.cad.validate_pair import validate_pair

from tests.pair_fixtures import cylinder, export_pair, tube


def _transform():
    return {
        "convention": "active_matrix",
        "formula": "p_socket = R @ p_limb + translation_mm",
        "rotation_matrix": [[1, 0, 0], [0, 1, 0], [0, 0, 1]],
        "translation_mm": [0, 0, 0],
        "source_frame": "limb",
        "target_frame": "socket",
        "mode": "shared_frame",
    }


def _profiles(limb_version="1.0.0", reference_version="1.0.0", recorded="a" * 64, limb_id="limb-a"):
    limb = {"model_id": limb_id, "model_version": limb_version}
    socket = {
        "socket_model_id": "socket-a",
        "model_version": "1.0.0",
        "reference_limb_model_id": "limb-a",
        "reference_limb_version": reference_version,
        "reference_limb_geometry_hash": recorded,
    }
    return limb, socket


def test_matching_reference():
    limb, socket = _profiles()
    record = relationship_record(limb, socket, _transform(), limb_hash="a" * 64, socket_hash="b" * 64)
    assert record["reference_status"] == "current"
    assert record["evaluated_limb_matches_design_reference"] is True
    assert record["socket_reference_limb_version"] == "1.0.0"
    assert record["limb_version"] == "1.0.0"


def test_stale_reference_is_not_called_a_hash_mismatch():
    limb, socket = _profiles(limb_version="1.0.0+q50", reference_version="1.0.0")
    record = relationship_record(limb, socket, _transform(), limb_hash="c" * 64, socket_hash="b" * 64)
    assert record["reference_status"] == "stale_reference"
    assert record["evaluated_limb_matches_design_reference"] is False
    assert record["limb_version"] != record["socket_reference_limb_version"]


def test_hash_mismatch_when_ids_match():
    limb, socket = _profiles(recorded="a" * 64)
    record = relationship_record(limb, socket, _transform(), limb_hash="d" * 64, socket_hash="b" * 64)
    assert record["reference_status"] == "hash_mismatch"


def test_missing_hash_is_recorded_as_missing():
    limb, socket = _profiles(recorded=None)
    socket["reference_limb_geometry_hash"] = None
    record = relationship_record(limb, socket, _transform(), limb_hash="a" * 64, socket_hash="b" * 64)
    assert record["reference_status"] == "hash_not_recorded"


def test_missing_step_file(tmp_path):
    request = export_pair(tmp_path, limb=cylinder(10), socket=tube(16, 12), limb_radius=10)
    (tmp_path / "limb.step").unlink()
    aligned = align_limb_socket(request)
    assert aligned["ok"] is False
    assert aligned["error"]["code"] == "missing_file"
    validated = validate_pair(request)
    assert validated["overall_status"] == "FAIL"
    assert validated["reference_status"] == "missing"
    assert validated["checks"][0]["status"] == "FAIL"
