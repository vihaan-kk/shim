"""Structured edits of the socket. Reference limb and socket files stay put."""

from pathlib import Path

import pytest

from tools.cad.generate_limb import PROFILE_PATH, REFERENCE_DIR, REFERENCE_STEP, SOCKET_PROFILE_PATH, SOCKET_STEP
from tools.cad.modify_socket import _changes, modify_socket


def _bytes() -> dict[str, bytes]:
    return {
        "limb_step": REFERENCE_STEP.read_bytes(),
        "limb_profile": Path(PROFILE_PATH).read_bytes(),
        "socket_profile": Path(SOCKET_PROFILE_PATH).read_bytes(),
        "socket_step": SOCKET_STEP.read_bytes() if SOCKET_STEP.is_file() else b"",
    }


def _request(operation: str, output: Path, **fields) -> dict:
    return {
        "base_socket_id": "synthetic-transtibial-socket-standard",
        "operation": operation,
        "output_dir": str(output),
        **fields,
    }


def test_percent_change_allows_a_zero_baseline():
    before = {
        "depth_mm": 0.0,
        "volume_mm3": 0.0,
        "proximal_opening": {"inner_ml_diameter_mm": 0.0},
        "sections": [
            {
                "id": "q50",
                "ml_wall_thickness_mm": 0.0,
                "inner_perimeter_mm": 0.0,
            }
        ],
    }
    after = {
        "depth_mm": 1.0,
        "volume_mm3": 5.0,
        "proximal_opening": {"inner_ml_diameter_mm": 2.0},
        "sections": [
            {
                "id": "q50",
                "ml_wall_thickness_mm": 1.0,
                "inner_perimeter_mm": 3.0,
            }
        ],
    }
    rows = _changes(before, after)
    assert rows["socket_depth"]["percent_change"] is None
    assert rows["volume_mm3"]["percent_change"] is None
    assert rows["socket_depth"]["absolute_change"] == 1.0


def test_increase_wall_preserves_depth_opening_and_cavity(tmp_path):
    before = _bytes()
    result = modify_socket(
        _request(
            "set_nominal_wall_thickness",
            tmp_path,
            wall_thickness_mm=7.0,
            preserve=["socket_depth", "proximal_opening_ml", "inner_circumference_q50"],
        )
    )
    assert result["ok"] is True, result.get("error")
    wall = result["changes"]["wall_thickness"]
    assert abs(wall["after"] - 7.0) < 0.2
    assert abs(wall["absolute_change"] - (wall["after"] - wall["before"])) < 1e-6
    assert wall["before"] != 0
    assert abs(wall["percent_change"] - (wall["absolute_change"] / wall["before"] * 100.0)) < 1e-6
    assert abs(result["changes"]["socket_depth"]["absolute_change"]) < 0.15
    assert abs(result["changes"]["proximal_opening_ml"]["absolute_change"]) < 0.3
    assert abs(result["changes"]["inner_circumference_q50"]["absolute_change"]) < 1.0
    assert _bytes() == before


def test_opening_depth_and_inner_circumference(tmp_path, standard_socket):
    opening = standard_socket["measured"]["proximal_opening"]["inner_ml_diameter_mm"]
    widened = modify_socket(
        _request(
            "set_proximal_opening_ml_diameter",
            tmp_path / "open",
            opening_ml_diameter_mm=opening + 4.0,
            preserve=["socket_depth", "wall_thickness", "inner_circumference_q50"],
        )
    )
    assert widened["ok"] is True, widened.get("error")
    assert abs(widened["changes"]["proximal_opening_ml"]["after"] - (opening + 4.0)) < 0.3
    assert abs(widened["changes"]["wall_thickness"]["absolute_change"]) < 0.2

    inner = standard_socket["measured"]["sections"]
    q50 = next(row["inner_perimeter_mm"] for row in inner if row["id"] == "q50")
    edited = modify_socket(
        _request(
            "set_inner_section_circumference",
            tmp_path / "inner",
            section_id="q50",
            circumference_mm=q50 + 2.0,
            preserve=["socket_depth", "wall_thickness", "proximal_opening_ml"],
        )
    )
    assert edited["ok"] is True, edited.get("error")
    assert abs(edited["changes"]["inner_circumference_q50"]["after"] - edited["requested_target"]) < 1.0
    assert abs(edited["changes"]["socket_depth"]["absolute_change"]) < 0.15

    deeper = modify_socket(
        _request(
            "set_socket_depth",
            tmp_path / "depth",
            socket_depth_mm=165.0,
            preserve=["wall_thickness", "proximal_opening_ml", "inner_circumference_q50"],
        )
    )
    assert deeper["ok"] is True, deeper.get("error")
    assert abs(deeper["changes"]["socket_depth"]["after"] - 165.0) < 0.15
    assert abs(deeper["changes"]["inner_circumference_q50"]["absolute_change"]) < 1.0


def test_clearance_and_section_wall(tmp_path):
    clearance = modify_socket(
        _request(
            "set_inner_radial_clearance",
            tmp_path / "gap",
            inner_radial_clearance_mm=3.0,
            preserve=["socket_depth", "wall_thickness"],
        )
    )
    assert clearance["ok"] is True, clearance.get("error")
    assert clearance["changes"]["inner_circumference_q50"]["absolute_change"] > 1.0
    extra = modify_socket(
        _request(
            "set_section_wall_extra",
            tmp_path / "extra",
            section_id="q75",
            wall_extra_mm=0.8,
            preserve=["socket_depth", "proximal_opening_ml", "inner_circumference_q50"],
        )
    )
    assert extra["ok"] is True, extra.get("error")
    samples = {row["id"]: row for row in extra["measurements"]["wall_thickness_samples"]}
    assert abs(samples["q75"]["ml_mm"] - 5.8) < 0.2
    assert abs(samples["q50"]["ml_mm"] - 5.0) < 0.2


@pytest.mark.parametrize(
    ("fields", "code"),
    [
        ({"operation": "set_nominal_wall_thickness", "wall_thickness_mm": 0}, "invalid_value"),
        ({"operation": "set_nominal_wall_thickness", "wall_thickness_mm": -2}, "invalid_value"),
        ({"operation": "set_nominal_wall_thickness", "wall_thickness_mm": "7"}, "invalid_value"),
        ({"operation": "set_nominal_wall_thickness", "wall_thickness_mm": float("nan")}, "non_finite"),
        ({"operation": "set_nominal_wall_thickness", "wall_thickness_mm": True}, "invalid_value"),
        ({"operation": "set_socket_depth", "socket_depth_mm": 100}, "invalid_value"),
        ({"operation": "set_socket_depth", "socket_depth_mm": float("inf")}, "non_finite"),
        ({"operation": "add_patellar_bar"}, "unsupported_operation"),
        ({"operation": "set_proximal_opening_ml_diameter", "opening_ml_diameter_mm": 10}, "invalid_value"),
        ({"operation": "set_inner_section_circumference", "section_fraction": 0.33, "circumference_mm": 280}, "invalid_section"),
        ({"operation": "set_inner_section_circumference", "section_id": "q50", "circumference_mm": -5}, "invalid_value"),
        (
            {
                "operation": "set_socket_depth",
                "socket_depth_mm": 165,
                "preserve": ["socket_depth"],
            },
            "constraint_conflict",
        ),
        ({"operation": "set_nominal_wall_thickness", "wall_thickness_mm": 7, "circumference_mm": 10}, "invalid_value"),
    ],
)
def test_rejected_edits_do_not_touch_reference_files(tmp_path, fields, code):
    before = _bytes()
    request = {
        "base_socket_id": "synthetic-transtibial-socket-standard",
        "output_dir": str(tmp_path),
        "preserve": fields.get("preserve", []),
        **fields,
    }
    result = modify_socket(request)
    assert result["ok"] is False
    assert result["error"]["code"] == code
    assert _bytes() == before


def test_folded_cavity_is_a_geometry_failure(tmp_path):
    before = _bytes()
    result = modify_socket(
        _request(
            "set_inner_section_circumference",
            tmp_path,
            section_id="q50",
            circumference_mm=400,
        )
    )
    assert result["ok"] is False
    assert result["error"]["code"] == "geometry_failed"
    assert list(tmp_path.iterdir()) == []
    assert _bytes() == before


def test_thin_wall_fails_the_demo_floor(tmp_path):
    before = _bytes()
    result = modify_socket(
        _request("set_nominal_wall_thickness", tmp_path, wall_thickness_mm=1.2)
    )
    assert result["ok"] is False
    assert result["error"]["code"] == "wall_too_thin"
    assert _bytes() == before


def test_reference_directory_is_protected(tmp_path):
    result = modify_socket(_request("set_socket_depth", REFERENCE_DIR, socket_depth_mm=165))
    assert result["error"]["code"] == "protected_output"
    missing = modify_socket(
        {
            "base_socket_id": "missing-socket",
            "operation": "set_socket_depth",
            "socket_depth_mm": 165,
            "output_dir": str(tmp_path),
        }
    )
    assert missing["error"]["code"] == "unknown_model"
    absent = tmp_path / "no-profile.json"
    bad_path = modify_socket(
        {
            "base_socket_path": str(absent),
            "operation": "set_socket_depth",
            "socket_depth_mm": 165,
            "output_dir": str(tmp_path),
        }
    )
    assert bad_path["error"]["code"] == "missing_file"
