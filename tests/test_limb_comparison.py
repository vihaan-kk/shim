"""Comparison of measured STEP solids."""

import pytest

from tools.cad.compare_limb_versions import compare_limb_versions, percent_change
from tools.cad.generate_limb import REFERENCE_STEP


def test_percent_change_and_a_zero_denominator():
    assert percent_change(200.0, 210.0) == pytest.approx(5.0)
    assert percent_change(0.0, 5.0) is None
    assert percent_change(-10.0, -5.0) == pytest.approx(50.0)


def test_identical_models_have_near_zero_differences(standard_model):
    report = compare_limb_versions(
        standard_model["step"],
        standard_model["step"],
        original_profile=standard_model["profile"],
        modified_profile=standard_model["profile"],
    )
    assert report["ok"] is True
    assert report["geometry_valid"] is True
    for row in report["comparison"].values():
        assert row["status"] == "measured"
        assert row["absolute_change"] == pytest.approx(0.0, abs=1e-6)
        assert row["percent_change"] == pytest.approx(0.0, abs=1e-6)


def test_modified_model_reports_measured_change_and_target(plus_five, standard_model):
    target = plus_five["requested_target"]
    report = compare_limb_versions(
        standard_model["step"],
        plus_five["files"]["step"],
        original_profile=standard_model["profile"],
        modified_profile=plus_five["profile"],
        targets={"middle_circumference_mm": target, "total_length_mm": 140},
    )
    assert report["ok"] is True
    assert report["geometry_valid"] is True
    middle = report["comparison"]["circumference_50_percent_mm"]
    assert middle["before"] == pytest.approx(plus_five["base_measured_value"])
    assert middle["after"] == pytest.approx(target, abs=1.0)
    assert middle["absolute_change"] == pytest.approx(middle["after"] - middle["before"])
    assert middle["percent_change"] == pytest.approx(
        (middle["after"] - middle["before"]) / abs(middle["before"]) * 100.0
    )
    assert middle["target"] == target
    assert middle["deviation_from_target"] == pytest.approx(middle["after"] - target)
    assert middle["within_tolerance"] is True
    assert middle["before"] != middle["target"]
    length = report["comparison"]["total_length_mm"]
    assert length["within_tolerance"] is True
    assert length["absolute_change"] == pytest.approx(0.0, abs=0.05)


def test_a_missed_target_is_not_within_tolerance(standard_model):
    report = compare_limb_versions(
        standard_model["step"],
        standard_model["step"],
        original_profile=standard_model["profile"],
        modified_profile=standard_model["profile"],
        targets={"circumference_50_percent_mm": 1.0},
    )
    middle = report["comparison"]["circumference_50_percent_mm"]
    assert middle["within_tolerance"] is False
    assert middle["after"] != 1.0


def test_missing_and_invalid_step_files(tmp_path, standard_model):
    missing = compare_limb_versions(standard_model["step"], tmp_path / "missing.step")
    assert missing["ok"] is False
    assert missing["error"]["code"] == "missing_file"
    assert missing["geometry_valid"] is False

    bogus = tmp_path / "bad.step"
    bogus.write_bytes(b"ISO-10303-21;\n" + b"not a solid\n" * 4)
    invalid = compare_limb_versions(standard_model["step"], bogus)
    assert invalid["ok"] is False
    assert invalid["error"]["code"] == "invalid_step"
    assert REFERENCE_STEP.is_file()
