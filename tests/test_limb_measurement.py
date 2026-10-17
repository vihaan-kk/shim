"""Measurement of the standardized limb and of bad inputs."""

import pytest

from tools.cad.generate_limb import ellipse_circumference, semi_axes_for_circumference
from tools.cad.measure_limb import measure_limb


def _section(measured, section_id):
    return next(row for row in measured["sections"] if row["id"] == section_id)


def test_all_stations_are_millimetres(standard_model):
    measured = standard_model["measured"]
    assert measured["ok"] is True
    assert measured["units"] == "mm"
    assert [row["id"] for row in measured["sections"]] == [
        "proximal",
        "q25",
        "q50",
        "q75",
        "distal_reference",
    ]
    for row in measured["sections"]:
        assert row["status"] == "measured"
        assert row["edge_count"] == 1
        assert row["measured_circumference_mm"] > 0


def test_measurements_match_the_elliptic_integral(standard_model):
    measured = standard_model["measured"]
    for section in standard_model["profile"]["sections"]:
        ap_semi, ml_semi = semi_axes_for_circumference(
            section["circumference_mm"],
            section["ap_over_ml"],
        )
        reference = ellipse_circumference(ap_semi, ml_semi)
        row = _section(measured, section["id"])
        assert row["measured_circumference_mm"] == pytest.approx(reference, abs=1.0)


def test_invalid_section_fraction_is_rejected(standard_model):
    result = measure_limb(standard_model["step"], standard_model["profile"], length_fraction=1.5)
    assert result["ok"] is False
    assert result["error"]["code"] == "invalid_section"


def test_missing_step_file(tmp_path):
    result = measure_limb(tmp_path / "absent.step")
    assert result["ok"] is False
    assert result["error"]["code"] == "missing_file"


def test_corrupted_step_file(tmp_path):
    bogus = tmp_path / "corrupt.step"
    bogus.write_bytes(b"ISO-10303-21;\n" + b"not geometry\n" * 5)
    result = measure_limb(bogus)
    assert result["ok"] is False
    assert result["error"]["code"] == "invalid_step"


def test_section_with_no_intersection(standard_model):
    past_tip = measure_limb(standard_model["step"], standard_model["profile"], z_mm=500)
    assert past_tip["ok"] is False
    assert past_tip["error"]["code"] == "no_intersection"
    at_tip = measure_limb(standard_model["step"], standard_model["profile"], length_fraction=1)
    assert at_tip["ok"] is False
    assert at_tip["error"]["code"] == "no_intersection"
