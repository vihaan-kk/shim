"""Checks for the synthetic transtibial solid. These tests build real CAD geometry."""

import math
from pathlib import Path

import pytest

from tools.cad.generate_limb import (
    REFERENCE_STEP,
    ellipse_circumference,
    export_solid,
    load_profile,
    parameters_from_profile,
    semi_axes_for_circumference,
)
from tools.cad.validate_limb import revise_section, validate_and_write_reference


@pytest.fixture(scope="module")
def reference_report():
    return validate_and_write_reference()


def test_circle_uses_the_elliptic_integral():
    perimeter = ellipse_circumference(10.0, 10.0)
    assert perimeter == pytest.approx(2.0 * math.pi * 10.0, abs=1e-6)


def test_semi_axes_recover_the_requested_perimeter():
    ap_semi, ml_semi = semi_axes_for_circumference(300.0, 0.85)
    assert ap_semi / ml_semi == pytest.approx(0.85, abs=1e-12)
    assert ellipse_circumference(ap_semi, ml_semi) == pytest.approx(300.0, abs=1e-6)
    # A circle of diameter 300/pi would be the wrong reading of an ellipse.
    circle_diameter = 300.0 / math.pi
    assert ml_semi * 2 != pytest.approx(circle_diameter, abs=0.5)


def test_profile_holds_the_demonstration_numbers():
    profile = load_profile()
    assert profile["units"] == "mm"
    assert profile["clinical_use"] is False
    assert profile["total_length_mm"] == 140
    assert profile["coordinate_frame"]["longitudinal_axis"] == "Z"
    assert profile["distal_cap"]["start_z_mm"] == 126
    assert profile["distal_cap"]["length_mm"] == 14
    assert profile["tolerances"]["circumference_mm"] == 1
    by_id = {section["id"]: section for section in profile["sections"]}
    assert [(section["z_mm"], section["circumference_mm"]) for section in profile["sections"]] == [
        (0, 300),
        (35, 290),
        (70, 275),
        (105, 255),
        (126, 235),
    ]
    assert all(section["ap_over_ml"] == 0.85 for section in by_id.values())
    parameters_from_profile(profile)


def test_different_aspect_ratios_are_rejected():
    profile = load_profile()
    profile["sections"][1]["ap_over_ml"] = 0.7
    with pytest.raises(ValueError, match="ap_over_ml"):
        parameters_from_profile(profile)


def test_reference_solid_passes_and_is_exported(reference_report):
    assert reference_report["passed"] is True
    built = reference_report["built_solid"]
    assert built["material_extent_mm"]["length_mm"] == pytest.approx(140.0, abs=0.05)
    for row in built["measurements"]:
        assert abs(row["error_mm"]) <= 1.0
    reimport = reference_report["exports"]["step_reimport"]
    assert reimport["passed"] is True
    for original, again in zip(built["measurements"], reimport["measurements"]):
        assert again["measured_circumference_mm"] == pytest.approx(
            original["measured_circumference_mm"], abs=0.05
        )
    assert Path(reference_report["files"]["step"]).is_file()
    assert Path(reference_report["files"]["stl"]).is_file()
    assert reference_report["exports"]["stl"]["passed"] is True


def test_revision_keeps_proximal_circumference_and_length(reference_report, tmp_path):
    before = REFERENCE_STEP.read_bytes()
    revised = revise_section(load_profile(), "q50", tmp_path, scale=1.05)
    assert REFERENCE_STEP.read_bytes() == before
    assert revised["passed"] is True
    preserved = revised["preserved_constraints"]
    assert preserved["proximal_within_tolerance"] is True
    assert preserved["length_within_tolerance"] is True
    assert preserved["revised_target_circumference_mm"] == pytest.approx(275.0 * 1.05)
    assert preserved["revised_measured_circumference_mm"] == pytest.approx(275.0 * 1.05, abs=1.0)
    assert preserved["revised_measured_circumference_mm"] > 275.0 + 5.0
    version_step = Path(revised["files"]["step"])
    assert version_step.is_file()
    assert version_step.resolve() != REFERENCE_STEP.resolve()


def test_reference_export_is_refused_without_the_flag():
    with pytest.raises(ValueError, match="Refusing to overwrite"):
        export_solid(None, REFERENCE_STEP, overwrite_reference=False)
