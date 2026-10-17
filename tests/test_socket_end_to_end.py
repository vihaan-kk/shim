"""Full limb-to-socket edit without mock geometry."""

from pathlib import Path

from tools.cad.generate_limb import PROFILE_PATH, REFERENCE_STEP, SOCKET_PROFILE_PATH, SOCKET_STEP
from tools.cad.generate_socket import load_socket_profile
from tools.cad.measure_limb import load_step_shape
from tools.cad.measure_socket import measure_socket
from tools.cad.modify_socket import modify_socket
from tools.cad.validate_socket import validate_socket


def test_generate_measure_validate_modify_and_compare(standard_model, standard_socket, tmp_path):
    originals = {
        "limb_step": REFERENCE_STEP.read_bytes(),
        "limb_profile": Path(PROFILE_PATH).read_bytes(),
        "socket_profile": Path(SOCKET_PROFILE_PATH).read_bytes(),
        "socket_step": SOCKET_STEP.read_bytes(),
    }
    limb = standard_model["measured"]
    assert limb["units"] == "mm"
    assert any(row["id"] == "q50" for row in limb["sections"])

    socket = standard_socket["measured"]
    assert socket["cavity"]["proximal_opening_open"] is True
    assert socket["cavity"]["distal_end_closed"] is True
    report = validate_socket(standard_socket["shape"], standard_socket["profile"], standard_socket["limb"])
    assert report["passed"] is True

    edited = modify_socket(
        {
            "base_socket_id": "synthetic-transtibial-socket-standard",
            "operation": "set_nominal_wall_thickness",
            "wall_thickness_mm": 7.0,
            "preserve": ["socket_depth", "proximal_opening_ml", "inner_circumference_q50"],
            "output_dir": str(tmp_path),
        }
    )
    assert edited["ok"] is True, edited.get("error")
    imported = load_step_shape(edited["files"]["step"])
    candidate = load_socket_profile(edited["files"]["profile"])
    candidate_report = validate_socket(imported, candidate, standard_socket["limb"])
    assert candidate_report["passed"] is True
    again = measure_socket(imported, candidate, standard_socket["limb"])
    q50 = next(row for row in again["sections"] if row["id"] == "q50")
    wall = edited["changes"]["wall_thickness"]
    assert abs(q50["ml_wall_thickness_mm"] - wall["after"]) < 0.05
    assert abs(wall["after"] - wall["before"] - wall["absolute_change"]) < 1e-6
    assert wall["percent_change"] is not None
    assert abs(wall["percent_change"] - (100.0 * wall["absolute_change"] / wall["before"])) < 1e-6
    assert abs(edited["changes"]["socket_depth"]["absolute_change"]) < 0.15
    assert abs(edited["changes"]["proximal_opening_ml"]["absolute_change"]) < 0.3
    assert abs(edited["changes"]["inner_circumference_q50"]["absolute_change"]) < 1.0
    assert candidate["reference_limb_model_id"] == standard_model["profile"]["model_id"]
    assert {
        "limb_step": REFERENCE_STEP.read_bytes(),
        "limb_profile": Path(PROFILE_PATH).read_bytes(),
        "socket_profile": Path(SOCKET_PROFILE_PATH).read_bytes(),
        "socket_step": SOCKET_STEP.read_bytes(),
    } == originals
