"""CAD checks for the synthetic socket.

A passing report means the STEP solid matches this file's geometry rules.
It does not mean the socket is wearable, comfortable, or safe to load.
"""

from __future__ import annotations

from pathlib import Path

from tools.cad.generate_limb import REFERENCE_STEP, load_profile
from tools.cad.generate_socket import (
    compile_socket,
    construction_targets,
    limb_geometry_hash,
)
from tools.cad.measure_limb import StepLoadError, load_step_shape, signed_volume_mm3
from tools.cad.measure_socket import measure_socket, section_value
from tools.cad.modify_limb import value_within_tolerance
from tools.cad.validate_limb import _stl_triangle_count

_DISCLAIMER = (
    "A passing result is a CAD check of a synthetic solid. "
    "It is not a clearance to manufacture or wear a socket."
)
_HASH_CACHE: dict[tuple, str] = {}


def _check(name: str, passed: bool, detail: str) -> dict:
    return {"name": name, "passed": bool(passed), "detail": detail}


def _cached_limb_hash(limb_profile: dict) -> str:
    stat = REFERENCE_STEP.stat()
    key = (
        str(REFERENCE_STEP.resolve()),
        stat.st_mtime_ns,
        stat.st_size,
        limb_profile.get("model_version"),
        float(limb_profile["total_length_mm"]),
    )
    if key not in _HASH_CACHE:
        _HASH_CACHE[key] = limb_geometry_hash(load_step_shape(REFERENCE_STEP), limb_profile)
    return _HASH_CACHE[key]


def _reference_checks(socket_profile: dict, limb_profile: dict) -> list[dict]:
    checks = [
        _check(
            "limb_model_id",
            socket_profile.get("reference_limb_model_id") == limb_profile.get("model_id"),
            f"{socket_profile.get('reference_limb_model_id')} vs {limb_profile.get('model_id')}",
        ),
        _check(
            "limb_model_version",
            socket_profile.get("reference_limb_version") == limb_profile.get("model_version"),
            f"{socket_profile.get('reference_limb_version')} vs {limb_profile.get('model_version')}",
        ),
        _check(
            "units",
            socket_profile.get("units") == "mm" and limb_profile.get("units") == "mm",
            "Both profiles must use millimetres",
        ),
        _check(
            "clinical_use_false",
            socket_profile.get("clinical_use") is False,
            "clinical_use must stay false",
        ),
    ]
    frame = socket_profile.get("coordinate_frame", {})
    frame_ok = (
        frame.get("ml_axis") == "X"
        and frame.get("ap_axis") == "Y"
        and frame.get("distal_direction") == "+Z"
        and frame.get("proximal_plane_z_mm") == 0
    )
    checks.append(_check("coordinate_frame", frame_ok, "X is ML, Y is AP, distal is +Z, opening at z = 0"))
    stored = socket_profile.get("reference_limb_geometry_hash")
    if not isinstance(stored, str) or len(stored) != 64:
        checks.append(_check("geometry_hash", False, "reference_limb_geometry_hash is missing"))
    elif not REFERENCE_STEP.is_file():
        checks.append(_check("geometry_hash", False, f"No limb STEP at {REFERENCE_STEP}"))
    else:
        try:
            actual = _cached_limb_hash(limb_profile)
        except (OSError, StepLoadError, KeyError, ValueError) as exc:
            checks.append(_check("geometry_hash", False, f"Could not hash the limb: {exc}"))
        else:
            checks.append(
                _check(
                    "geometry_hash",
                    actual == stored,
                    "Limb measurements still match the hash stored on the socket",
                )
            )
    derived = socket_profile.get("derived")
    if not isinstance(derived, dict):
        checks.append(_check("derived_cache", False, "The derived block is missing"))
        return checks
    try:
        fresh = construction_targets(compile_socket(limb_profile, socket_profile))
    except (ValueError, KeyError, TypeError, RuntimeError) as exc:
        checks.append(_check("derived_cache", False, f"Could not recompute derived values: {exc}"))
        return checks
    mismatches = []
    for key in ("inner_tip_z_mm", "outer_tip_z_mm", "opening_ml_diameter_mm", "opening_ap_diameter_mm"):
        if abs(float(derived.get(key, 0.0)) - float(fresh[key])) > 1e-4:
            mismatches.append(key)
    cached_rows = {row["id"]: row for row in derived.get("stations", []) if isinstance(row, dict)}
    for row in fresh["stations"]:
        cached = cached_rows.get(row["id"])
        if cached is None or abs(float(cached.get("inner_circumference_mm", 0.0)) - row["inner_circumference_mm"]) > 1e-4:
            mismatches.append(row["id"])
    checks.append(
        _check(
            "derived_cache",
            not mismatches,
            "Derived cache matches the editable parameters" if not mismatches else f"Stale derived fields: {mismatches}",
        )
    )
    return checks


def _dimension_checks(measured: dict, tolerances: dict) -> list[dict]:
    targets = measured["constructed_targets"]
    checks = [
        _check(
            "socket_depth",
            value_within_tolerance(measured["depth_mm"] - targets["socket_depth_mm"], tolerances["depth_mm"]),
            f"measured {measured['depth_mm']:.4f} mm, target {targets['socket_depth_mm']:.4f} mm",
        ),
        _check(
            "rim_crest",
            value_within_tolerance(
                measured["rim_crest_z_mm"] - targets["rim_crest_z_mm"],
                tolerances["depth_mm"],
            ),
            f"measured {measured['rim_crest_z_mm']:.4f} mm, target {targets['rim_crest_z_mm']:.4f} mm",
        ),
    ]
    opening = measured["proximal_opening"]
    for key, target_key in (
        ("inner_ml_diameter_mm", "opening_ml_diameter_mm"),
        ("inner_ap_diameter_mm", "opening_ap_diameter_mm"),
    ):
        measured_value = opening.get(key)
        target = targets[target_key]
        passed = measured_value is not None and value_within_tolerance(
            float(measured_value) - target,
            tolerances["opening_diameter_mm"],
        )
        checks.append(
            _check(
                key,
                passed,
                f"measured {measured_value} mm, target {target:.4f} mm",
            )
        )
    axial = measured["distal_end"].get("axial_wall_mm")
    checks.append(
        _check(
            "distal_axial_wall",
            axial is not None
            and value_within_tolerance(float(axial) - targets["distal_axial_wall_mm"], tolerances["wall_thickness_mm"]),
            f"measured {axial} mm, target {targets['distal_axial_wall_mm']:.4f} mm",
        )
    )
    target_rows = {row["id"]: row for row in targets["stations"]}
    for row in measured["sections"]:
        target = target_rows[row["id"]]
        for field, tolerance_key in (
            ("inner_perimeter_mm", "circumference_mm"),
            ("outer_perimeter_mm", "circumference_mm"),
        ):
            expected = target["inner_circumference_mm" if field.startswith("inner") else "outer_circumference_mm"]
            value = row.get(field)
            passed = value is not None and value_within_tolerance(float(value) - expected, tolerances[tolerance_key])
            checks.append(
                _check(
                    f"{row['id']}_{field}",
                    passed,
                    f"measured {value} mm, constructed {expected:.4f} mm",
                )
            )
        for field, expected_key in (
            ("ml_wall_thickness_mm", "ml_wall_thickness_mm"),
            ("ap_wall_thickness_mm", "ap_wall_thickness_mm"),
        ):
            value = row.get(field)
            expected = target[expected_key]
            passed = value is not None and value_within_tolerance(
                float(value) - expected,
                tolerances["wall_thickness_mm"],
            )
            checks.append(
                _check(
                    f"{row['id']}_{field}",
                    passed,
                    f"measured {value} mm, constructed {expected:.4f} mm",
                )
            )
        area = row.get("inner_area_mm2")
        expected_area = target["inner_area_mm2"]
        if area is None or expected_area <= 0:
            area_ok = False
        else:
            area_ok = abs(float(area) - expected_area) / expected_area <= float(tolerances["area_relative"])
        checks.append(
            _check(
                f"{row['id']}_inner_area",
                area_ok,
                f"measured {area} mm2, ellipse {expected_area:.2f} mm2",
            )
        )
    return checks


def _structure_checks(measured: dict, socket_profile: dict) -> list[dict]:
    minimum = float(socket_profile["minimum_wall_thickness_mm"])
    cavity = measured["cavity"]
    distal = measured["distal_end"]
    checks = [
        _check(
            "proximal_opening_open",
            bool(cavity["proximal_opening_open"]),
            "A ray from the cavity toward -Z does not hit a lid",
        ),
        _check(
            "distal_end_closed",
            bool(cavity["distal_end_closed"]),
            "A ray from the cavity toward +Z hits the distal wall",
        ),
        _check(
            "distal_plug_single_contour",
            distal["plug_contour_count"] == 1 and distal["plug_section_status"] == "outer_only",
            f"{distal['plug_contour_count']} curves, status {distal['plug_section_status']}",
        ),
        _check(
            "no_contour_beyond_tip",
            distal["beyond_tip_contour_count"] == 0,
            f"{distal['beyond_tip_contour_count']} curves past the outer tip",
        ),
    ]
    thicknesses = []
    if distal.get("axial_wall_mm") is not None:
        thicknesses.append(float(distal["axial_wall_mm"]))
    for row in measured["sections"]:
        if row["id"] in {"q25", "q50", "q75"}:
            checks.append(
                _check(
                    f"{row['id']}_two_contours",
                    row["status"] == "measured" and row["contour_count"] == 2,
                    f"status {row['status']}, curves {row['contour_count']}",
                )
            )
        inner = row.get("inner_perimeter_mm")
        outer = row.get("outer_perimeter_mm")
        if inner is not None and outer is not None:
            checks.append(
                _check(
                    f"{row['id']}_inner_inside_outer",
                    float(inner) < float(outer),
                    f"inner {inner:.3f} mm, outer {outer:.3f} mm",
                )
            )
        for key in ("ml_wall_thickness_mm", "ap_wall_thickness_mm"):
            if row.get(key) is not None:
                thicknesses.append(float(row[key]))
    thinnest = min(thicknesses) if thicknesses else None
    checks.append(
        _check(
            "minimum_wall_thickness",
            thinnest is not None and thinnest + 1e-9 >= minimum,
            f"thinnest sample {thinnest} mm, demo floor {minimum} mm",
        )
    )
    return checks


def _error_for(categories: dict) -> dict | None:
    failed = [item for category in categories.values() for item in category["checks"] if not item["passed"]]
    if not failed:
        return None
    names = {item["name"] for item in failed}
    if "step_readable" in names or "step_reimport" in names:
        code = "invalid_step"
    elif "valid_solid" in names or "one_solid" in names or "positive_volume" in names:
        code = "invalid_geometry"
    elif "geometry_hash" in names:
        code = "stale_reference"
    elif "limb_model_id" in names or "limb_model_version" in names or "derived_cache" in names:
        code = "reference_mismatch"
    elif "minimum_wall_thickness" in names:
        code = "wall_too_thin"
    elif "proximal_opening_open" in names:
        code = "opening_closed"
    elif "distal_end_closed" in names or "distal_plug_single_contour" in names:
        code = "distal_open"
    else:
        code = "target_not_met"
    return {
        "code": code,
        "message": "Socket validation failed",
        "details": {"checks": failed},
    }


def validate_socket(
    source,
    socket_profile: dict | None = None,
    limb_profile: dict | None = None,
    *,
    step_path: Path | None = None,
    stl_path: Path | None = None,
) -> dict:
    """Validate a socket shape or STEP file against its parameter profile.

    Reference, CAD, dimension, and structure checks are reported separately.
    """
    if socket_profile is None:
        from tools.cad.generate_socket import load_socket_profile

        socket_profile = load_socket_profile()
    if limb_profile is None:
        limb_profile = load_profile()

    reference = _reference_checks(socket_profile, limb_profile)
    cad: list[dict] = []
    shape = source
    if isinstance(source, (str, Path)):
        try:
            shape = load_step_shape(Path(source))
            cad.append(_check("step_readable", True, str(source)))
        except StepLoadError as exc:
            cad.append(_check("step_readable", False, str(exc)))
            categories = {
                "cad_validity": {"passed": False, "checks": cad},
                "dimensions": {"passed": False, "checks": []},
                "structure": {"passed": False, "checks": []},
                "reference_integrity": {"passed": all(item["passed"] for item in reference), "checks": reference},
            }
            return {
                "passed": False,
                "clinical_use": False,
                "disclaimer": _DISCLAIMER,
                "error": {"code": exc.code, "message": str(exc)},
                "categories": categories,
            }

    try:
        from tools.cad.measure_limb import is_valid, solid_count

        valid = is_valid(shape)
        solids = solid_count(shape)
        volume = signed_volume_mm3(shape)
    except Exception as exc:
        valid, solids, volume = False, 0, 0.0
        cad.append(_check("inspection", False, str(exc)))
    cad.append(_check("valid_solid", valid, "BRepCheck_Analyzer"))
    cad.append(_check("one_solid", solids == 1, f"{solids} solids"))
    cad.append(_check("positive_volume", volume > 0, f"{volume:.3f} mm3"))

    if step_path is not None:
        try:
            imported = load_step_shape(Path(step_path))
            imported_volume = signed_volume_mm3(imported)
            close = abs(imported_volume - volume) <= max(1.0, abs(volume) * 1e-4)
            cad.append(
                _check(
                    "step_reimport",
                    close,
                    f"reimported volume {imported_volume:.3f} mm3",
                )
            )
        except StepLoadError as exc:
            cad.append(_check("step_reimport", False, str(exc)))
    if stl_path is not None:
        stl = Path(stl_path)
        if not stl.is_file():
            cad.append(_check("stl_mesh", False, f"No STL at {stl}"))
        else:
            triangles = _stl_triangle_count(stl)
            cad.append(_check("stl_mesh", triangles > 0, f"{triangles} triangles"))

    measured = None
    dimension_checks: list[dict] = []
    structure_checks: list[dict] = []
    if valid and solids == 1 and volume > 0:
        measured = measure_socket(shape, socket_profile, limb_profile)
        if not measured.get("ok"):
            detail = measured.get("error", {}).get("message", "measurement failed")
            dimension_checks.append(_check("measurements", False, detail))
            structure_checks.append(_check("measurements", False, detail))
        else:
            tolerances = socket_profile["tolerances"]
            dimension_checks = _dimension_checks(measured, tolerances)
            structure_checks = _structure_checks(measured, socket_profile)
    else:
        dimension_checks.append(_check("measurements", False, "Skipped because the solid is not valid"))
        structure_checks.append(_check("measurements", False, "Skipped because the solid is not valid"))

    categories = {
        "cad_validity": {"passed": all(item["passed"] for item in cad), "checks": cad},
        "dimensions": {"passed": all(item["passed"] for item in dimension_checks), "checks": dimension_checks},
        "structure": {"passed": all(item["passed"] for item in structure_checks), "checks": structure_checks},
        "reference_integrity": {
            "passed": all(item["passed"] for item in reference),
            "checks": reference,
        },
    }
    passed = all(category["passed"] for category in categories.values())
    result = {
        "passed": passed,
        "clinical_use": False,
        "disclaimer": _DISCLAIMER,
        "socket_model_id": socket_profile.get("socket_model_id"),
        "reference_limb_model_id": socket_profile.get("reference_limb_model_id"),
        "error": None if passed else _error_for(categories),
        "categories": categories,
    }
    if measured and measured.get("ok"):
        result["measurements"] = {
            "units": "mm",
            "depth_mm": measured["depth_mm"],
            "volume_mm3": measured["volume_mm3"],
            "proximal_opening": measured["proximal_opening"],
            "wall_thickness_samples": measured["wall_thickness_samples"],
            "distal_end": measured["distal_end"],
            "cavity": measured["cavity"],
            "sections": [
                {
                    "id": row["id"],
                    "z_mm": row["z_mm"],
                    "status": row["status"],
                    "inner_perimeter_mm": row["inner_perimeter_mm"],
                    "outer_perimeter_mm": row["outer_perimeter_mm"],
                    "ml_wall_thickness_mm": row["ml_wall_thickness_mm"],
                    "ap_wall_thickness_mm": row["ap_wall_thickness_mm"],
                }
                for row in measured["sections"]
            ],
        }
    return result


def wall_sample(measured: dict, section_id: str) -> float | None:
    """Measured medial-lateral wall at one station, or None if that contour is missing."""
    return section_value(measured, section_id, "ml_wall_thickness_mm")
