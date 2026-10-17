"""Validation reports for sound solids, broken geometry, and missed constraints."""

import copy

import cadquery as cq

from tools.cad.modify_limb import preservation_report
from tools.cad.validate_limb import validate_limb


def test_reference_geometry_passes(standard_model):
    report = validate_limb(standard_model["shape"], standard_model["profile"])
    assert report["passed"] is True
    assert report["measurements"]
    assert all(check["passed"] for check in report["checks"])


def test_non_solid_geometry_is_rejected(standard_model):
    edge = cq.Workplane("XY").circle(5).val()
    report = validate_limb(edge, standard_model["profile"])
    assert report["passed"] is False
    assert any(check["detail"] for check in report["checks"])


def test_target_deviation_is_reported(standard_model):
    profile = copy.deepcopy(standard_model["profile"])
    for section in profile["sections"]:
        if section["id"] == "q50":
            section["circumference_mm"] = 400
    report = validate_limb(standard_model["shape"], profile)
    assert report["passed"] is False
    failed = [check for check in report["checks"] if not check["passed"]]
    assert any("q50" in check["name"] for check in failed)
    assert any("400" in check["detail"] or "145" in check["detail"] for check in failed)


def test_preservation_tolerance_boundary():
    base = {
        "material_extent_mm": {"length_mm": 140.0},
        "sections": [{"id": "proximal", "status": "measured", "measured_circumference_mm": 300.0}],
    }
    at_limit = {
        "material_extent_mm": {"length_mm": 140.05},
        "sections": [{"id": "proximal", "status": "measured", "measured_circumference_mm": 301.0}],
    }
    past_limit = {
        "material_extent_mm": {"length_mm": 140.06},
        "sections": [{"id": "proximal", "status": "measured", "measured_circumference_mm": 301.1}],
    }
    tolerances = {"length_mm": 0.05, "circumference_mm": 1.0}
    assert preservation_report(
        base, at_limit, ["total_length", "proximal_circumference"], tolerances
    )["passed"]
    length_fail = preservation_report(base, past_limit, ["total_length"], tolerances)
    circumference_fail = preservation_report(base, past_limit, ["proximal_circumference"], tolerances)
    assert length_fail["passed"] is False
    assert length_fail["checks"][0]["absolute_change"] > 0.05
    assert circumference_fail["passed"] is False
    assert circumference_fail["checks"][0]["absolute_change"] > 1.0
