"""Independent measurements of the socket solid."""

from tools.cad.measure_socket import measure_socket, section_value


def test_stations_distinguish_inner_and_outer(standard_socket):
    measured = standard_socket["measured"]
    assert measured["units"] == "mm"
    targets = {row["id"]: row for row in measured["constructed_targets"]["stations"]}
    assert set(targets) == {"proximal", "q25", "q50", "q75", "distal_reference"}
    for row in measured["sections"]:
        assert row["status"] == "measured"
        assert row["contour_count"] == 2
        inner = row["inner_perimeter_mm"]
        outer = row["outer_perimeter_mm"]
        assert inner < outer
        expected = targets[row["id"]]["inner_circumference_mm"]
        assert abs(inner - expected) < 0.05
        assert abs(outer - targets[row["id"]]["outer_circumference_mm"]) < 0.05
        assert abs(row["ml_wall_thickness_mm"] - targets[row["id"]]["ml_wall_thickness_mm"]) < 0.05
        assert abs(row["ap_wall_thickness_mm"] - targets[row["id"]]["ap_wall_thickness_mm"]) < 0.05
        assert row["ap_wall_thickness_mm"] < row["ml_wall_thickness_mm"]


def test_depth_and_opening(standard_socket):
    measured = standard_socket["measured"]
    targets = measured["constructed_targets"]
    assert abs(measured["depth_mm"] - targets["socket_depth_mm"]) < 0.05
    opening = measured["proximal_opening"]
    assert abs(opening["inner_ml_diameter_mm"] - targets["opening_ml_diameter_mm"]) < 0.05
    assert abs(opening["inner_ap_diameter_mm"] - targets["opening_ap_diameter_mm"]) < 0.05
    assert opening["inner_area_mm2"] > 0
    assert abs(measured["distal_end"]["axial_wall_mm"] - targets["distal_axial_wall_mm"]) < 0.05
    assert measured["coordinate_frame"]["side"] is None


def test_rejects_invalid_section_queries(standard_socket):
    shape = standard_socket["shape"]
    profile = standard_socket["profile"]
    limb = standard_socket["limb"]
    outside = measure_socket(shape, profile, limb, length_fraction=1.5)
    assert outside["ok"] is False
    assert outside["error"]["code"] == "invalid_section"
    missing = measure_socket(shape, profile, limb, z_mm=500)
    assert missing["error"]["code"] == "no_intersection"
    tip = measure_socket(shape, profile, limb, length_fraction=1)
    assert tip["error"]["code"] == "no_intersection"
    both = measure_socket(shape, profile, limb, z_mm=70, length_fraction=0.5)
    assert both["error"]["code"] == "invalid_value"
    assert measure_socket(shape, profile, limb, z_mm=float("nan"))["error"]["code"] == "non_finite"
    assert measure_socket(shape, profile, limb, z_mm=True)["error"]["code"] == "invalid_value"


def test_missing_and_corrupt_step(standard_socket, tmp_path):
    profile = standard_socket["profile"]
    limb = standard_socket["limb"]
    missing = measure_socket(tmp_path / "absent.step", profile, limb)
    assert missing["error"]["code"] == "missing_file"
    corrupt = tmp_path / "corrupt.step"
    corrupt.write_bytes(b"ISO-10303-21;\n" + b"not a solid" * 5)
    broken = measure_socket(corrupt, profile, limb)
    assert broken["error"]["code"] == "invalid_step"
    assert measure_socket("not-a-real-socket", profile, limb)["error"]["code"] == "unknown_model"


def test_opening_inner_is_not_the_outer_perimeter(standard_socket):
    opening = standard_socket["measured"]["proximal_opening"]
    assert opening["inner_perimeter_mm"] != opening["outer_perimeter_mm"]
    q50 = section_value(standard_socket["measured"], "q50", "inner_perimeter_mm")
    outer = section_value(standard_socket["measured"], "q50", "outer_perimeter_mm")
    assert q50 is not None and outer is not None
    assert outer - q50 > 10
