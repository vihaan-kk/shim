"""Cross-sections, radial clearance, and material intersection on simple solids."""

import math

from tools.cad.compare_limb_socket import compare_limb_socket, material_intersection

from tests.pair_fixtures import cylinder, elliptic_tube, export_pair, tube


def _compare(tmp_path, limb, socket, radius):
    request = export_pair(tmp_path, limb=limb, socket=socket, limb_radius=radius)
    return compare_limb_socket(request)


def _q50(result):
    assert result["ok"] is True, result
    return result["sections"][0]


def test_positive_clearance_uses_inner_cavity(tmp_path):
    section = _q50(_compare(tmp_path, cylinder(10), tube(16, 12), 10))
    assert section["status"] == "measured"
    assert section["socket_contour_count"] == 2
    assert section["socket_inner_perimeter_mm"] < section["socket_outer_perimeter_mm"]
    assert abs(section["limb_perimeter_mm"] - 2.0 * math.pi * 10.0) < 0.2
    assert abs(section["socket_inner_perimeter_mm"] - 2.0 * math.pi * 12.0) < 0.2
    assert abs(section["perimeter_percent_difference"] - 20.0) < 0.5
    clearance = section["clearance"]
    assert clearance["status"] == "measured"
    assert abs(clearance["minimum_mm"] - 2.0) < 0.1
    assert abs(clearance["maximum_mm"] - 2.0) < 0.1
    assert result_intersection_clear(section)


def result_intersection_clear(section):
    return section["socket_inner_perimeter_mm"] != section["socket_outer_perimeter_mm"]


def test_zero_clearance(tmp_path):
    result = _compare(tmp_path, cylinder(10), tube(14, 10), 10)
    section = _q50(result)
    assert abs(section["clearance"]["mean_mm"]) < 0.15
    assert abs(section["clearance"]["minimum_mm"]) < 0.15
    intersection = result["material_intersection"]
    assert intersection["status"] == "PASS"
    assert intersection["volume_mm3"] <= 1.0
    assert intersection["intersects"] is False


def test_negative_clearance_and_intersection_volume(tmp_path):
    result = _compare(tmp_path, cylinder(14), tube(16, 12), 14)
    section = _q50(result)
    assert section["clearance"]["minimum_mm"] < -1.5
    assert abs(section["clearance"]["mean_mm"] + 2.0) < 0.15
    intersection = result["material_intersection"]
    expected = math.pi * (14.0**2 - 12.0**2) * 40.0
    assert intersection["status"] == "PASS"
    assert intersection["intersects"] is True
    assert abs(intersection["volume_mm3"] - expected) / expected < 0.02


def test_no_material_intersection(tmp_path):
    result = _compare(tmp_path, cylinder(10), tube(16, 12), 10)
    intersection = result["material_intersection"]
    assert intersection["status"] == "PASS"
    assert intersection["intersects"] is False
    assert intersection["volume_mm3"] <= 1.0


def test_ellipse_ap_and_ml_differ_and_clearance_is_not_a_perimeter_delta(tmp_path):
    limb = __import__("cadquery").Workplane("XY").ellipse(20, 12).extrude(40)
    socket = elliptic_tube((30, 22), (24, 16))
    section = _q50(_compare(tmp_path, limb, socket, 20))
    assert section["limb_ml_diameter_mm"] > section["limb_ap_diameter_mm"] + 5.0
    assert section["socket_inner_ml_diameter_mm"] > section["socket_inner_ap_diameter_mm"] + 5.0
    assert section["socket_inner_perimeter_mm"] < section["socket_outer_perimeter_mm"]
    clearance = section["clearance"]
    assert clearance["status"] == "measured"
    assert clearance["maximum_mm"] - clearance["minimum_mm"] > 0.2
    perimeter_gap = section["perimeter_difference_mm"]
    assert abs(clearance["mean_mm"] - perimeter_gap) > 1.0


def test_off_axis_section_is_unsupported(tmp_path):
    limb = cylinder(10, center_xy=(30.0, 0.0))
    section = _q50(_compare(tmp_path, limb, tube(16, 12), 10))
    assert section["limb_contour_count"] == 1
    assert section["clearance"]["status"] == "unsupported"
    assert section["clearance"]["minimum_mm"] is None


def test_two_limb_contours_are_ambiguous(tmp_path):
    limb = tube(14, 8)
    section = _q50(_compare(tmp_path, limb, tube(20, 16), 14))
    assert section["status"] == "ambiguous"
    assert section["limb_contour_count"] == 2
    assert section["clearance"]["minimum_mm"] is None


def test_invalid_section_position(tmp_path):
    request = export_pair(tmp_path, limb=cylinder(10), socket=tube(16, 12), limb_radius=10)
    result = compare_limb_socket({**request, "z_mm": 500.0})
    assert result["ok"] is False
    assert result["error"]["code"] == "no_intersection"


def test_boolean_failure_is_indeterminate():
    from OCP.TopoDS import TopoDS_Shape

    result = material_intersection(TopoDS_Shape(), TopoDS_Shape())
    assert result["status"] == "INDETERMINATE"
    assert result["volume_mm3"] is None
    assert result["intersects"] is None
