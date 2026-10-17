"""Shared CAD fixtures. The reference STEP is imported once per session."""

from pathlib import Path

import pytest

from tools.cad.generate_limb import PROFILE_PATH, REFERENCE_STEP, load_profile
from tools.cad.measure_limb import load_step_shape, measure_shape
from tools.cad.generate_socket import generate_socket, load_socket_profile, with_derived
from tools.cad.measure_socket import measure_socket
from tools.cad.modify_limb import modify_limb


@pytest.fixture(scope="session")
def standard_model():
    profile = load_profile()
    shape = load_step_shape(REFERENCE_STEP)
    return {
        "profile": profile,
        "shape": shape,
        "step": REFERENCE_STEP,
        "profile_path": PROFILE_PATH,
        "measured": measure_shape(shape, profile),
    }


@pytest.fixture(scope="session")
def plus_five(tmp_path_factory, standard_model):
    """One real +5% rebuild at 50% length, shared by the modification and end-to-end tests."""
    output = tmp_path_factory.mktemp("plus5")
    before = {
        "step": REFERENCE_STEP.read_bytes(),
        "profile": Path(PROFILE_PATH).read_bytes(),
    }
    result = modify_limb(
        {
            "base_model_id": standard_model["profile"]["model_id"],
            "operation": "change_section_circumference_percent",
            "section_fraction": 0.5,
            "change_percent": 5.0,
            "preserve": ["total_length", "proximal_circumference"],
            "output_dir": str(output),
        }
    )
    result["original_bytes"] = before
    return result


@pytest.fixture(scope="session")
def standard_socket(standard_model):
    """One hollow socket built from the standard profiles."""
    import copy

    from tools.cad.generate_socket import limb_geometry_hash

    limb = standard_model["profile"]
    profile = copy.deepcopy(load_socket_profile())
    stored = profile.get("reference_limb_geometry_hash")
    if not isinstance(stored, str) or len(stored) != 64:
        profile["reference_limb_geometry_hash"] = limb_geometry_hash(standard_model["shape"], limb)
    profile = with_derived(limb, profile)
    shape = generate_socket(limb, profile)
    measured = measure_socket(shape, profile, limb)
    return {
        "limb": limb,
        "profile": profile,
        "shape": shape,
        "measured": measured,
    }
