"""Full path: measure, modify, reimport, measure, compare.

``plus_five`` is the ``modify_limb`` call. This test checks that result and
compares the original STEP with the new STEP.
"""

from pathlib import Path

import pytest

from tools.cad.compare_limb_versions import compare_limb_versions
from tools.cad.generate_limb import PROFILE_PATH, REFERENCE_STEP
from tools.cad.measure_limb import load_step_shape, section_circumference


def test_five_percent_workflow(plus_five, standard_model):
    assert plus_five["ok"] is True, plus_five.get("error")
    assert REFERENCE_STEP.read_bytes() == plus_five["original_bytes"]["step"]
    assert PROFILE_PATH.read_bytes() == plus_five["original_bytes"]["profile"]

    base = plus_five["base_measured_value"]
    target = base * 1.05
    assert plus_five["requested_target"] == pytest.approx(target)
    measured = next(row for row in plus_five["measurements"]["sections"] if row["id"] == "q50")
    assert measured["measured_circumference_mm"] == pytest.approx(target, abs=1.0)
    assert plus_five["measured_from"] == "reimported_step"

    reimported = load_step_shape(plus_five["files"]["step"])
    again, edges = section_circumference(reimported, 70.0)
    assert edges == 1
    assert again == pytest.approx(measured["measured_circumference_mm"], abs=0.05)

    base_length = plus_five["base_measurements"]["material_extent_mm"]["length_mm"]
    new_length = plus_five["measurements"]["material_extent_mm"]["length_mm"]
    assert new_length == pytest.approx(base_length, abs=0.05)
    base_proximal = next(
        row for row in plus_five["base_measurements"]["sections"] if row["id"] == "proximal"
    )
    new_proximal = next(row for row in plus_five["measurements"]["sections"] if row["id"] == "proximal")
    assert new_proximal["measured_circumference_mm"] == pytest.approx(
        base_proximal["measured_circumference_mm"], abs=1.0
    )

    report = compare_limb_versions(
        standard_model["step"],
        plus_five["files"]["step"],
        original_profile=standard_model["profile"],
        modified_profile=plus_five["profile"],
        targets={"circumference_50_percent_mm": target, "total_length_mm": 140},
    )
    assert report["geometry_valid"] is True
    middle = report["comparison"]["circumference_50_percent_mm"]
    assert middle["before"] == pytest.approx(base)
    assert middle["after"] == pytest.approx(measured["measured_circumference_mm"])
    assert middle["absolute_change"] == pytest.approx(middle["after"] - middle["before"])
    assert middle["percent_change"] == pytest.approx(middle["absolute_change"] / abs(middle["before"]) * 100.0)
    assert middle["target"] == target
    assert middle["deviation_from_target"] == pytest.approx(middle["after"] - target)
    assert middle["within_tolerance"] is True
    assert report["comparison"]["total_length_mm"]["within_tolerance"] is True
    assert report["comparison"]["proximal_circumference_mm"]["absolute_change"] == pytest.approx(0.0, abs=1.0)
    assert Path(plus_five["files"]["step"]).read_bytes() != plus_five["original_bytes"]["step"]
