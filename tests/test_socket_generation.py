"""Generation of the standard hollow socket."""

from pathlib import Path

from tools.cad.generate_limb import REFERENCE_STEP, PROFILE_PATH
from tools.cad.generate_socket import export_socket, generate_socket
from tools.cad.measure_limb import is_valid, load_step_shape, solid_count
from tools.cad.measure_socket import measure_socket, section_value


def test_socket_is_one_hollow_solid(standard_socket):
    shape = standard_socket["shape"]
    measured = standard_socket["measured"]
    assert is_valid(shape)
    assert solid_count(shape) == 1
    assert measured["ok"] is True
    assert measured["volume_mm3"] > 0
    assert measured["cavity"]["proximal_opening_open"] is True
    assert measured["cavity"]["distal_end_closed"] is True
    assert measured["distal_end"]["plug_contour_count"] == 1
    assert measured["distal_end"]["beyond_tip_contour_count"] == 0


def test_step_reimport_matches_the_built_solid(standard_socket, tmp_path):
    step = tmp_path / "socket.step"
    export_socket(standard_socket["shape"], step)
    assert step.is_file()
    imported = load_step_shape(step)
    assert is_valid(imported)
    assert solid_count(imported) == 1
    again = measure_socket(imported, standard_socket["profile"], standard_socket["limb"])
    built = section_value(standard_socket["measured"], "q50", "inner_perimeter_mm")
    imported_value = section_value(again, "q50", "inner_perimeter_mm")
    assert built is not None and imported_value is not None
    assert abs(imported_value - built) < 0.05
    assert abs(again["depth_mm"] - standard_socket["measured"]["depth_mm"]) < 0.05


def test_generation_is_reproducible(standard_socket):
    second = generate_socket(standard_socket["limb"], standard_socket["profile"])
    again = measure_socket(second, standard_socket["profile"], standard_socket["limb"])
    for section_id in ("proximal", "q50", "distal_reference"):
        first = section_value(standard_socket["measured"], section_id, "inner_perimeter_mm")
        other = section_value(again, section_id, "inner_perimeter_mm")
        assert first is not None and other is not None
        assert abs(first - other) < 0.05


def test_limb_files_stay_untouched(standard_socket):
    before_step = REFERENCE_STEP.read_bytes()
    before_profile = Path(PROFILE_PATH).read_bytes()
    generate_socket(standard_socket["limb"], standard_socket["profile"])
    assert REFERENCE_STEP.read_bytes() == before_step
    assert Path(PROFILE_PATH).read_bytes() == before_profile
