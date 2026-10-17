"""Rigid alignment of a limb copy into the socket frame."""

import math

from tools.cad.align_limb_socket import align_limb_socket
from tools.cad.measure_limb import bounding_box_mm, load_step_shape, signed_volume_mm3

from tests.pair_fixtures import cylinder, export_pair


def _pair(tmp_path):
    limb = cylinder(10.0)
    socket = cylinder(16.0).cut(cylinder(12.0))
    return export_pair(tmp_path, limb=limb, socket=socket, limb_radius=10.0)


def test_identity_keeps_volume_and_does_not_touch_source_step(tmp_path):
    request = _pair(tmp_path)
    before = open(request["limb_step"], "rb").read()
    result = align_limb_socket(request)
    assert result["ok"] is True
    assert result["transformation"]["identity"] is True
    assert result["transformation"]["intrinsic_geometry_preserved"] is True
    assert result["files"] is None
    assert open(request["limb_step"], "rb").read() == before
    assert "_moved_limb" not in result


def test_translation_moves_a_copy_and_preserves_volume(tmp_path):
    request = _pair(tmp_path)
    before = open(request["limb_step"], "rb").read()
    request["alignment_mode"] = "explicit"
    request["output_dir"] = str(tmp_path / "moved")
    request["transformation"] = {
        "rotation_matrix": [[1, 0, 0], [0, 1, 0], [0, 0, 1]],
        "translation_mm": [5.0, -3.0, 2.0],
        "source_frame": "limb",
        "target_frame": "socket",
    }
    result = align_limb_socket(request)
    assert result["ok"] is True
    assert result["transformation"]["intrinsic_geometry_preserved"] is True
    moved = load_step_shape(result["files"]["aligned_limb_step"])
    box = bounding_box_mm(moved)
    assert abs(box["xmin_mm"] - (-5.0)) < 0.05
    assert abs(box["ymin_mm"] - (-13.0)) < 0.05
    assert abs(box["zmin_mm"] - 2.0) < 0.05
    original = load_step_shape(request["limb_step"])
    assert abs(signed_volume_mm3(original) - math.pi * 100.0 * 40.0) / (math.pi * 4000.0) < 0.01
    assert open(request["limb_step"], "rb").read() == before


def test_rotation_about_z(tmp_path):
    from tests.pair_fixtures import export_pair as export
    import cadquery as cq

    box = cq.Workplane("XY").moveTo(10, 5).rect(20, 10).extrude(8)
    socket = cylinder(16.0)
    request = export(tmp_path, limb=box, socket=socket, limb_radius=10.0)
    request["alignment_mode"] = "explicit"
    request["transformation"] = {
        "rotation_matrix": [[0.0, -1.0, 0.0], [1.0, 0.0, 0.0], [0.0, 0.0, 1.0]],
        "translation_mm": [0.0, 0.0, 0.0],
    }
    result = align_limb_socket({**request, "output_dir": str(tmp_path / "rotated")})
    assert result["ok"] is True, result
    moved = load_step_shape(result["files"]["aligned_limb_step"])
    box_mm = bounding_box_mm(moved)
    assert box_mm["xmin_mm"] < -5.0
    assert box_mm["xmax_mm"] < 1.0
    assert box_mm["ymax_mm"] > 15.0
    assert abs(result["transformation"]["volume_after_mm3"] - 1600.0) < 1.0


def test_rejects_reflection_scale_euler_and_nonfinite(tmp_path):
    request = _pair(tmp_path)
    request["alignment_mode"] = "explicit"
    reflection = align_limb_socket(
        {**request, "transformation": {"rotation_matrix": [[1, 0, 0], [0, 1, 0], [0, 0, -1]], "translation_mm": [0, 0, 0]}}
    )
    assert reflection["ok"] is False
    assert reflection["error"]["code"] == "invalid_rotation"
    scaled = align_limb_socket(
        {**request, "transformation": {"rotation_matrix": [[2, 0, 0], [0, 1, 0], [0, 0, 1]], "translation_mm": [0, 0, 0]}}
    )
    assert scaled["error"]["code"] == "invalid_rotation"
    euler = align_limb_socket({**request, "transformation": {"euler_deg": [0, 0, 90], "translation_mm": [0, 0, 0]}})
    assert euler["error"]["code"] == "unsupported_transform"
    shear = align_limb_socket({**request, "transformation": {"scale": 2, "translation_mm": [0, 0, 0]}})
    assert shear["error"]["code"] == "unsupported_transform"
    nonfinite = align_limb_socket(
        {**request, "transformation": {"translation_mm": [float("nan"), 0.0, 0.0]}}
    )
    assert nonfinite["error"]["code"] == "non_finite"
    moved = align_limb_socket(
        {
            **request,
            "alignment_mode": "shared_frame",
            "transformation": {"translation_mm": [1.0, 0.0, 0.0]},
        }
    )
    assert moved["ok"] is False
    assert moved["error"]["code"] == "invalid_value"


def test_rejects_incompatible_units(tmp_path):
    request = _pair(tmp_path)
    profile = tmp_path / "limb.json"
    text = profile.read_text().replace('"units": "mm"', '"units": "inch"')
    profile.write_text(text)
    result = align_limb_socket(request)
    assert result["ok"] is False
    assert result["error"]["code"] == "incompatible_frame"
