"""Structured edits. Invalid requests do not build a solid."""

import math
from pathlib import Path

import pytest

from tools.cad.generate_limb import (
    PROFILE_PATH,
    REFERENCE_DIR,
    REFERENCE_STEP,
    load_profile,
    parameters_from_profile,
    profile_with_total_length,
)
from tools.cad.modify_limb import modify_limb, new_candidate_id, value_within_tolerance


def _request(output, **extra):
    body = {
        "base_model_id": "synthetic-transtibial-standard",
        "output_dir": str(output),
    }
    body.update(extra)
    return body


def _unchanged(before_step: bytes, before_profile: bytes):
    assert REFERENCE_STEP.read_bytes() == before_step
    assert PROFILE_PATH.read_bytes() == before_profile


def test_length_fractions_are_recomputed_and_circumferences_stay():
    revised = profile_with_total_length(load_profile(), 150)
    by_id = {section["id"]: section for section in revised["sections"]}
    assert by_id["q50"]["length_fraction"] == 0.5
    assert by_id["q50"]["z_mm"] == pytest.approx(75.0)
    assert by_id["q50"]["circumference_mm"] == 275
    assert by_id["proximal"]["z_mm"] == 0
    assert revised["distal_cap"]["start_z_mm"] == pytest.approx(135.0)
    assert revised["distal_cap"]["tip_z_mm"] == 150
    assert revised["distal_cap"]["length_mm"] == pytest.approx(15.0)
    parameters_from_profile(revised)


def test_candidate_ids_are_unique():
    assert new_candidate_id("limb", "edit") != new_candidate_id("limb", "edit")


def test_tolerance_boundary():
    assert value_within_tolerance(1.0, 1.0) is True
    assert value_within_tolerance(-1.0, 1.0) is True
    assert value_within_tolerance(1.001, 1.0) is False


def test_increase_middle_circumference_by_five_percent(plus_five):
    assert plus_five["ok"] is True
    assert plus_five["error"] is None
    _unchanged(plus_five["original_bytes"]["step"], plus_five["original_bytes"]["profile"])
    base = next(row for row in plus_five["base_measurements"]["sections"] if row["id"] == "q50")
    measured = next(row for row in plus_five["measurements"]["sections"] if row["id"] == "q50")
    assert plus_five["requested_target"] == pytest.approx(base["measured_circumference_mm"] * 1.05)
    assert measured["measured_circumference_mm"] == pytest.approx(plus_five["requested_target"], abs=1.0)
    assert measured["target_circumference_mm"] == plus_five["requested_target"]
    assert plus_five["measured_from"] == "reimported_step"
    assert Path(plus_five["files"]["step"]).is_file()
    assert Path(plus_five["files"]["step"]).resolve() != REFERENCE_STEP.resolve()
    assert plus_five["preserved"]["passed"] is True


def test_decrease_middle_circumference(tmp_path):
    before_step = REFERENCE_STEP.read_bytes()
    before_profile = PROFILE_PATH.read_bytes()
    result = modify_limb(
        _request(
            tmp_path,
            operation="change_section_circumference_percent",
            section_fraction=0.5,
            change_percent=-5,
        )
    )
    assert result["ok"] is True
    _unchanged(before_step, before_profile)
    base = next(row for row in result["base_measurements"]["sections"] if row["id"] == "q50")
    measured = next(row for row in result["measurements"]["sections"] if row["id"] == "q50")
    assert measured["measured_circumference_mm"] < base["measured_circumference_mm"]
    assert measured["measured_circumference_mm"] == pytest.approx(result["requested_target"], abs=1.0)


def test_set_explicit_circumference(tmp_path):
    before_step = REFERENCE_STEP.read_bytes()
    before_profile = PROFILE_PATH.read_bytes()
    result = modify_limb(
        _request(
            tmp_path,
            operation="set_section_circumference",
            section_id="q50",
            circumference_mm=280,
            preserve=["total_length", "proximal_circumference"],
        )
    )
    assert result["ok"] is True
    _unchanged(before_step, before_profile)
    measured = next(row for row in result["measurements"]["sections"] if row["id"] == "q50")
    assert result["requested_target"] == 280
    assert measured["measured_circumference_mm"] == pytest.approx(280, abs=1.0)
    assert result["preserved"]["passed"] is True


def test_change_total_length(tmp_path):
    before_step = REFERENCE_STEP.read_bytes()
    before_profile = PROFILE_PATH.read_bytes()
    result = modify_limb(
        _request(
            tmp_path,
            operation="set_total_length",
            total_length_mm=150,
            preserve=["proximal_circumference"],
        )
    )
    assert result["ok"] is True, result.get("error")
    _unchanged(before_step, before_profile)
    assert result["profile"]["total_length_mm"] == 150
    assert result["profile"]["section_position_convention"] == "length_fraction"
    q50 = next(section for section in result["profile"]["sections"] if section["id"] == "q50")
    assert q50["z_mm"] == pytest.approx(75.0)
    assert q50["circumference_mm"] == 275
    assert result["measurements"]["material_extent_mm"]["length_mm"] == pytest.approx(150.0, abs=0.05)
    proximal = next(row for row in result["measurements"]["sections"] if row["id"] == "proximal")
    assert proximal["measured_circumference_mm"] == pytest.approx(300.0, abs=1.0)
    assert REFERENCE_STEP.read_bytes() != Path(result["files"]["step"]).read_bytes()


@pytest.mark.parametrize(
    "extra, code",
    [
        ({"operation": "set_section_circumference", "section_fraction": 0.5, "circumference_mm": 0}, "invalid_value"),
        ({"operation": "set_section_circumference", "section_fraction": 0.5, "circumference_mm": -10}, "invalid_value"),
        ({"operation": "set_section_circumference", "section_fraction": 0.33, "circumference_mm": 280}, "invalid_section"),
        ({"operation": "twist_limb"}, "unsupported_operation"),
        ({"operation": "set_section_circumference", "section_fraction": 0.5, "circumference_mm": "290"}, "invalid_value"),
        ({"operation": "set_section_circumference", "section_fraction": 0.5, "circumference_mm": math.nan}, "non_finite"),
        ({"operation": "set_total_length", "total_length_mm": math.inf}, "non_finite"),
        ({"operation": "set_section_circumference", "section_fraction": 0.5, "circumference_mm": True}, "invalid_value"),
        (
            {
                "operation": "set_total_length",
                "total_length_mm": 150,
                "preserve": ["total_length"],
            },
            "constraint_conflict",
        ),
        ({"operation": "set_total_length", "total_length_mm": 20}, "geometry_failed"),
    ],
)
def test_rejected_modifications_leave_the_reference_untouched(tmp_path, extra, code):
    before_step = REFERENCE_STEP.read_bytes()
    before_profile = PROFILE_PATH.read_bytes()
    result = modify_limb(_request(tmp_path, **extra))
    assert result["ok"] is False
    assert result["error"]["code"] == code
    _unchanged(before_step, before_profile)


def test_reference_directory_is_protected():
    before_step = REFERENCE_STEP.read_bytes()
    before_profile = PROFILE_PATH.read_bytes()
    result = modify_limb(
        _request(
            REFERENCE_DIR,
            operation="set_section_circumference",
            section_fraction=0.5,
            circumference_mm=280,
        )
    )
    assert result["ok"] is False
    assert result["error"]["code"] == "protected_output"
    assert REFERENCE_STEP.read_bytes() == before_step
    assert PROFILE_PATH.read_bytes() == before_profile
