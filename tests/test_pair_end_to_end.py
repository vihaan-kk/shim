"""Limb v1 + socket v1, then limb v2 against the same socket, then socket v2.

The solids are the generated STEP models. No measurement is taken from the
parameter JSON alone.
"""

import json
from pathlib import Path

from tools.cad.compare_limb_socket import compare_limb_socket, pair_version_summary
from tools.cad.generate_limb import (
    PROFILE_PATH,
    REFERENCE_STEP,
    SOCKET_PROFILE_PATH,
    SOCKET_STEP,
    load_profile,
)
from tools.cad.generate_socket import (
    export_socket,
    generate_socket,
    limb_geometry_hash,
    load_socket_profile,
    with_derived,
)
from tools.cad.measure_limb import load_step_shape
from tools.cad.validate_pair import validate_pair


def _q50(report):
    return next(section for section in report["sections"] if section["id"] == "q50")


def test_versioned_limb_socket_workflow(tmp_path, plus_five):
    originals = {
        "limb_step": REFERENCE_STEP.read_bytes(),
        "limb_profile": Path(PROFILE_PATH).read_bytes(),
        "socket_step": SOCKET_STEP.read_bytes(),
        "socket_profile": Path(SOCKET_PROFILE_PATH).read_bytes(),
    }
    assert plus_five["ok"] is True

    baseline_request = {
        "limb_model_id": "synthetic-transtibial-standard",
        "socket_model_id": "synthetic-transtibial-socket-standard",
        "alignment_mode": "shared_frame",
    }
    baseline = compare_limb_socket(baseline_request)
    baseline_validation = validate_pair(baseline_request)
    assert baseline["ok"] is True
    assert baseline["relationship"]["reference_status"] == "current", (
        baseline["relationship"]["limb_geometry_hash"],
        baseline["relationship"]["recorded_limb_geometry_hash"],
    )
    assert baseline["transformation"]["identity"] is True
    base_q50 = _q50(baseline)
    assert base_q50["status"] == "measured"
    assert base_q50["socket_inner_perimeter_mm"] < base_q50["socket_outer_perimeter_mm"]
    assert base_q50["clearance"]["status"] == "measured"
    assert base_q50["clearance"]["minimum_mm"] > 0.5
    assert baseline["material_intersection"]["status"] == "PASS"
    assert baseline["material_intersection"]["volume_mm3"] <= 1.0
    assert baseline_validation["overall_status"] == "PASS"
    assert baseline_validation["reference_status"] == "current"
    assert baseline_validation["version_status"] == "PASS"
    again = _q50(baseline_validation["comparison"])
    assert abs(again["clearance"]["minimum_mm"] - base_q50["clearance"]["minimum_mm"]) < 1e-6

    stale_request = {
        "limb_step": plus_five["files"]["step"],
        "limb_profile_path": plus_five["files"]["profile"],
        "socket_model_id": "synthetic-transtibial-socket-standard",
        "alignment_mode": "shared_frame",
    }
    stale = compare_limb_socket(stale_request)
    stale_validation = validate_pair(stale_request)
    assert stale["ok"] is True
    assert stale["relationship"]["reference_status"] == "stale_reference"
    assert stale["relationship"]["socket_reference_limb_version"] == "1.0.0"
    assert stale["relationship"]["limb_version"] == "1.0.0+q50"
    stale_q50 = _q50(stale)
    assert stale_q50["limb_perimeter_mm"] > base_q50["limb_perimeter_mm"] * 1.04
    assert stale_q50["clearance"]["minimum_mm"] < base_q50["clearance"]["minimum_mm"] - 1.0
    assert stale["material_intersection"]["status"] == "PASS"
    assert stale["material_intersection"]["intersects"] is True
    assert stale["material_intersection"]["volume_mm3"] > 1.0
    assert stale_validation["overall_status"] == "PASS"
    assert stale_validation["geometry_status"] == "PASS"
    assert stale_validation["reference_status"] == "stale_reference"
    assert stale_validation["version_status"] == "WARNING"
    assert SOCKET_STEP.read_bytes() == originals["socket_step"]

    limb_profile = plus_five["profile"]
    limb_shape = load_step_shape(plus_five["files"]["step"])
    socket_profile = load_socket_profile()
    socket_profile["socket_model_id"] = "synthetic-transtibial-socket-v2"
    socket_profile["model_version"] = "2.0.0"
    socket_profile["reference_limb_model_id"] = limb_profile["model_id"]
    socket_profile["reference_limb_version"] = limb_profile["model_version"]
    socket_profile["reference_limb_geometry_hash"] = limb_geometry_hash(limb_shape, limb_profile)
    socket_profile = with_derived(limb_profile, socket_profile)
    socket_v2 = generate_socket(limb_profile, socket_profile)
    socket_step = tmp_path / "socket-v2.step"
    socket_profile_path = tmp_path / "socket-v2.json"
    export_socket(socket_v2, socket_step)
    socket_profile_path.write_text(json.dumps(socket_profile, indent=2) + "\n")

    refreshed_request = {
        "limb_step": plus_five["files"]["step"],
        "limb_profile_path": plus_five["files"]["profile"],
        "socket_step": str(socket_step),
        "socket_profile_path": str(socket_profile_path),
        "alignment_mode": "shared_frame",
    }
    refreshed = compare_limb_socket(refreshed_request)
    refreshed_validation = validate_pair(refreshed_request)
    assert refreshed["ok"] is True
    assert refreshed["relationship"]["reference_status"] == "current"
    assert refreshed["relationship"]["socket_version"] == "2.0.0"
    assert refreshed["relationship"]["socket_reference_limb_version"] == limb_profile["model_version"]
    refreshed_q50 = _q50(refreshed)
    assert refreshed_q50["clearance"]["status"] == "measured"
    assert refreshed_q50["clearance"]["minimum_mm"] > 0.5
    assert refreshed["material_intersection"]["status"] == "PASS"
    assert refreshed_validation["overall_status"] == "PASS"
    assert refreshed_validation["reference_status"] == "current"
    reimported = load_step_shape(socket_step)
    from tools.cad.measure_limb import is_valid, solid_count, signed_volume_mm3

    assert is_valid(reimported)
    assert solid_count(reimported) == 1
    assert signed_volume_mm3(reimported) > 0

    summary = pair_version_summary([baseline, stale, refreshed])
    assert [row["reference_status"] for row in summary["pairs"]] == [
        "current",
        "stale_reference",
        "current",
    ]
    assert summary["pairs"][1]["q50_limb_perimeter_mm"] > summary["pairs"][0]["q50_limb_perimeter_mm"]
    assert summary["pairs"][2]["q50_clearance_min_mm"] > summary["pairs"][1]["q50_clearance_min_mm"]
    (tmp_path / "pair-summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))

    assert REFERENCE_STEP.read_bytes() == originals["limb_step"]
    assert Path(PROFILE_PATH).read_bytes() == originals["limb_profile"]
    assert SOCKET_STEP.read_bytes() == originals["socket_step"]
    assert Path(SOCKET_PROFILE_PATH).read_bytes() == originals["socket_profile"]
    assert Path(plus_five["files"]["step"]).is_file()
    assert socket_step.is_file()
    assert Path(plus_five["files"]["step"]).read_bytes() != originals["limb_step"]
    assert socket_step.read_bytes() != originals["socket_step"]
    assert load_profile()["model_version"] == "1.0.0"
