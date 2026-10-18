"""CAD tool wrappers: revision folders, result shapes, and the hand-off to the printer tools.

These run the real CadQuery library, so each test takes a few seconds.
"""

import json

import pytest

from tools.cad import tools as cad
from tests.real_printer import pt


@pytest.fixture(autouse=True)
def workspace(tmp_path, monkeypatch):
    monkeypatch.setattr(cad, "WORKSPACE", tmp_path)
    monkeypatch.setattr(pt, "WORKSPACE", tmp_path)
    return tmp_path


def test_create_and_inspect_socket(workspace):
    created = cad.create_part("socket")
    assert created.ok and created.data["revision_id"] == "socket-1"
    assert json.loads((workspace / "revisions/socket-1/meta.json").read_text())["part_type"] == "socket"

    inspected = cad.inspect_part("socket-1")
    assert inspected.ok
    assert inspected.data["depth_mm"] == 152.0
    assert inspected.data["wall_thickness_q50_mm"] == 5.0


def test_unknown_revision_and_missing_section_are_fixable():
    cad.create_part("socket")
    unknown = cad.inspect_part("socket-9")
    assert unknown.status == "fixable" and unknown.error.code == "unknown_revision"
    assert unknown.error.valid_range == ["socket-1"]

    no_section = cad.modify_socket("socket-1", "add_wall_at_section", 2.0)
    assert no_section.status == "fixable" and no_section.error.code == "missing_argument"


def test_too_thin_wall_is_fixable_and_makes_no_revision(workspace):
    cad.create_part("socket")
    thin = cad.modify_socket("socket-1", "set_wall_thickness", 0.5)
    assert thin.status == "fixable" and thin.error.code == "wall_too_thin"
    assert [m["revision_id"] for m in cad._all_meta()] == ["socket-1"]


def test_validated_socket_is_visible_to_prepare_print(workspace):
    cad.create_part("socket")
    edited = cad.modify_socket("socket-1", "set_wall_thickness", 6.0)
    assert edited.ok and edited.data["revision_id"] == "socket-2"
    assert edited.data["changes"]["wall_thickness"] == {"before": 5.0, "after": 6.0}

    assert "socket-2" not in pt._printable_revisions()
    validated = cad.validate_part("socket-2")
    assert validated.ok
    assert (workspace / "revisions/socket-2/part.stl").is_file()
    assert pt._printable_revisions() == ["socket-2"]


def test_changed_limb_stops_fitting_until_socket_is_refit():
    cad.create_part("socket")
    cad.create_part("limb")
    assert cad.modify_limb("limb-1", "change_circumference_percent", 5.0, "q50").ok

    stale = cad.check_fit("socket-1", "limb-2")
    assert stale.ok and stale.data["fits"] is False
    assert stale.data["reference_status"] == "stale_reference"

    refit = cad.fit_socket_to_limb("socket-1", "limb-2")
    assert refit.ok and refit.data["revision_id"] == "socket-2"
    fits = cad.check_fit("socket-2", "limb-2")
    assert fits.data["fits"] is True and fits.data["reference_status"] == "current"
    assert cad.validate_part("socket-2").ok


def test_components_assemble_and_report_height():
    for part_type in ("socket", "adapter", "pylon", "foot"):
        assert cad.create_part(part_type).ok
    first = cad.assemble_prosthesis("socket-1", "adapter-1", "pylon-1", "foot-1")
    assert first.ok and first.data["opening_to_floor_mm"] == 342.0

    longer = cad.modify_component("pylon-1", "length_mm", 170)
    assert longer.ok and longer.data["revision_id"] == "pylon-2"
    second = cad.assemble_prosthesis("socket-1", "adapter-1", "pylon-2", "foot-1")
    assert second.data["opening_to_floor_mm"] == 362.0


def test_component_errors_are_fixable():
    cad.create_part("adapter")
    cad.create_part("pylon")
    cad.create_part("foot")
    cad.create_part("socket")
    assert cad.modify_component("pylon-1", "plate_diameter_mm", 50).error.code == "unknown_parameter"
    assert cad.modify_component("foot-1", "toe_thickness_mm", 40).error.code == "invalid_value"
    assert cad.modify_component("socket-1", "length_mm", 100).error.code == "unknown_revision"

    cad.modify_component("adapter-1", "connector_size_mm", 20)
    mismatch = cad.assemble_prosthesis("socket-1", "adapter-2", "pylon-1", "foot-1")
    assert mismatch.status == "fixable" and mismatch.error.code == "connector_mismatch"


def test_component_print_checks(workspace):
    cad.create_part("foot")
    assert cad.validate_part("foot-1").ok
    assert "foot-1" in pt._printable_revisions()

    cad.modify_component("foot-1", "length_mm", 250)
    too_big = cad.validate_part("foot-2")
    assert too_big.error.code == "too_large_for_printer"
    assert not (workspace / "revisions/foot-2/part.stl").exists()


def test_unedited_dimensions_rebuild_the_standard_limb():
    from tools import registry
    from tools.cad.generate_limb import load_profile

    accepted = registry.call("validate_measurements", {})
    assert accepted.ok and accepted.data["edited"] == {}
    built = cad.customize_residual_limb(accepted.data["validation_id"])
    assert built.ok and built.data["measured_length_mm"] == 140.0
    standard = {s["id"]: s["circumference_mm"] for s in load_profile()["sections"]}
    got = {s["id"]: s["measured_mm"] for s in built.data["stations"]}
    for sid in ("proximal", "q50", "distal_reference"):
        assert abs(got[sid] - standard[sid]) < 0.05


def test_edited_dimensions_build_and_fit_a_socket():
    from tools import registry

    accepted = registry.call("validate_measurements", {"length_mm": 150, "distal_circumference_mm": 240})
    assert set(accepted.data["edited"]) == {"length_mm", "distal_circumference_mm"}
    limb = cad.customize_residual_limb(accepted.data["validation_id"])
    assert limb.ok and limb.data["measured_length_mm"] == 150.0
    assert cad.customize_residual_limb(accepted.data["validation_id"]).error.code == "validation_mismatch"

    cad.create_part("socket")
    assert cad.fit_socket_to_limb("socket-1", "limb-1").ok
    assert cad.check_fit("socket-2", "limb-1").data["fits"] is True
    assert cad.validate_part("socket-2").ok


def test_inconsistent_dimensions_are_fixable():
    from tools import registry

    assert registry.call("validate_measurements", {"distal_circumference_mm": 300}).error.code == "inconsistent_taper"
    assert registry.call("validate_measurements", {"length_mm": 250}).error.code == "outside_template"
    assert registry.call("validate_measurements", {"ap_mm": 80}).error.code == "invalid_value"


def test_engraved_label_survives_an_edit_and_is_checked(workspace):
    cad.create_part("socket")
    labelled = cad.engrave_label("socket-1", "SHIM S-2", "front")
    assert labelled.ok and labelled.data["revision_id"] == "socket-2"
    assert (workspace / "revisions/socket-2/base.step").is_file()

    too_deep = cad.engrave_label("socket-1", "X", "front", depth_mm=4)
    assert too_deep.status == "fixable" and too_deep.error.valid_range == {"depth_mm": [0.4, 1.5]}
    on_brim = cad.engrave_label("socket-1", "X", "back", height_mm=5)
    assert on_brim.status == "fixable" and "height_mm" in on_brim.error.valid_range

    edited = cad.modify_socket("socket-2", "set_wall_thickness", 6.0)
    assert edited.ok
    socket_id = edited.data["revision_id"]
    assert cad.inspect_part(socket_id).data["features"] == ["label 'SHIM S-2' on the front, 1.2 mm deep"]
    assert cad.validate_part(socket_id).ok
    report = json.loads((workspace / f"revisions/{socket_id}/validation.json").read_text())
    assert report["categories"]["features"]["passed"]


def test_preview_is_a_labelled_scaled_copy_of_a_validated_part(workspace):
    cad.create_part("socket")
    not_checked = cad.make_preview_print("socket-1", 50)
    assert not_checked.status == "fixable" and not_checked.error.code == "not_validated"
    assert cad.validate_part("socket-1").ok

    too_small = cad.make_preview_print("socket-1", 15)
    assert too_small.status == "fixable" and too_small.error.valid_range == [25, 75]

    preview = cad.make_preview_print("socket-1", 40)
    assert preview.ok and preview.data == {
        "revision_id": "preview-1", "preview_of": "socket-1", "scale_percent": 40,
        "not_to_size": True, "printable": True,
    }
    assert "NOT TO SIZE" in preview.message
    assert "preview-1" in pt._printable_revisions()
    listed = {r["revision_id"]: r for r in cad.list_parts().data["revisions"]}
    assert listed["preview-1"]["not_to_size"] and listed["preview-1"]["scale_percent"] == 40
