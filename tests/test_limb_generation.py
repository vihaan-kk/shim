"""Generation of the standardized limb."""

import pytest

from tools.cad.generate_limb import generate_limb, parameters_from_profile
from tools.cad.measure_limb import is_valid, load_step_shape, section_circumference, solid_count


def test_reference_step_reimports_as_one_valid_solid(standard_model):
    shape = load_step_shape(standard_model["step"])
    assert standard_model["step"].is_file()
    assert is_valid(shape)
    assert solid_count(shape) == 1
    assert standard_model["measured"]["solid_count"] == 1
    assert standard_model["measured"]["valid_solid"] is True


def test_generation_matches_the_reference_step(standard_model):
    fresh = generate_limb(parameters_from_profile(standard_model["profile"]))
    fresh_length, fresh_edges = section_circumference(fresh, 70.0)
    stored_length, stored_edges = section_circumference(standard_model["shape"], 70.0)
    assert fresh_edges == 1
    assert stored_edges == 1
    assert fresh_length == pytest.approx(stored_length, abs=0.05)
