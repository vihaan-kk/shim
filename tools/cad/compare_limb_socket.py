"""Measure how a limb sits relative to a socket cavity.

Sections are cut in the socket frame after the limb copy has been rigidly
moved. The limb perimeter is compared with the socket's inner curve, never
with the outer shell.

Clearance at an angle is the socket inner radius minus the limb radius,
both measured from the shared Z axis along the same ray:

- positive: the limb boundary is inside the cavity
- zero: the two boundaries meet at that ray
- negative: the limb boundary is outside the cavity

This is not a circumference subtraction. A section that is not a single
star-shaped curve about the Z axis is reported as unsupported.

Material intersection is the Boolean common of the limb solid and the socket
solid. The hollow cavity is not socket material, so a limb sitting in the
cavity is not an intersection by itself.
"""

from __future__ import annotations

import hashlib
import json
import math
from typing import Any

import numpy as np
from OCP.BRepAlgoAPI import BRepAlgoAPI_Common
from OCP.BRepBuilderAPI import BRepBuilderAPI_Copy

from tools.cad.align_limb_socket import prepare_aligned_pair, relationship_record
from tools.cad.generate_socket import limb_geometry_hash
from tools.cad.measure_limb import occ_shape, signed_volume_mm3
from tools.cad.measure_socket import section_polylines
from tools.cad.compare_limb_versions import percent_change
from tools.cad.modify_limb import _finite

_INTERSECTION_TOLERANCE_MM3 = 1.0
_SAMPLE_COUNT = 72
_POLYLINE_SAMPLES = 720
_RADIUS_WINDOW_RAD = math.radians(3.0)
_AMBIGUOUS_SPREAD_MM = 1.5
_LIMB_HASHES: dict[tuple, str] = {}

_AXES = (
    ("plus_x", 0.0, "+X"),
    ("minus_x", math.pi, "-X"),
    ("plus_y", math.pi / 2.0, "+Y"),
    ("minus_y", -math.pi / 2.0, "-Y"),
)


def _failure(code: str, message: str, **details: Any) -> dict:
    error: dict[str, Any] = {"code": code, "message": message}
    if details:
        error["details"] = details
    return {"ok": False, "error": error, "clinical_use": False}


def _evaluated_limb_hash(shape, profile: dict, step, sections: list[dict]) -> str:
    """Hash the limb solid.

    Full limb profiles use the same measurement hash the socket records.
    Fixture profiles that are not limb schemas are hashed from volume and the
    sections already cut, so a missing ``length_fraction`` is not an error.
    """
    stations = profile.get("sections")
    complete = (
        isinstance(stations, list)
        and stations
        and all(isinstance(section, dict) and "length_fraction" in section for section in stations)
        and "total_length_mm" in profile
    )
    if complete:
        return _limb_hash(shape, profile, step)
    payload = {
        "volume_mm3": round(abs(signed_volume_mm3(shape)), 3),
        "sections": [
            [
                row.get("id"),
                round(float(row["z_mm"]), 4),
                None if row.get("limb_perimeter_mm") is None else round(float(row["limb_perimeter_mm"]), 4),
            ]
            for row in sections
        ],
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()


def _limb_hash(shape, profile: dict, step) -> str:
    stat = step.stat()
    key = (str(step.resolve()), stat.st_mtime_ns, stat.st_size, profile.get("model_id"), profile.get("model_version"))
    if key not in _LIMB_HASHES:
        _LIMB_HASHES[key] = limb_geometry_hash(shape, profile)
    return _LIMB_HASHES[key]


def _socket_hash(volume_mm3: float, sections: list[dict]) -> str:
    payload = {
        "volume_mm3": round(float(volume_mm3), 3),
        "sections": [
            [
                row.get("id"),
                round(float(row["z_mm"]), 4),
                None if row.get("socket_inner_perimeter_mm") is None else round(float(row["socket_inner_perimeter_mm"]), 4),
                None if row.get("socket_outer_perimeter_mm") is None else round(float(row["socket_outer_perimeter_mm"]), 4),
            ]
            for row in sections
        ],
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()


def _angular_distance(left: float, right: float) -> float:
    return abs((left - right + math.pi) % (2.0 * math.pi) - math.pi)


def _radius_at(points: list[list[float]], theta: float) -> tuple[float | None, str]:
    near: list[float] = []
    for x_mm, y_mm in points:
        radius = math.hypot(x_mm, y_mm)
        if radius < 1e-6:
            continue
        if _angular_distance(math.atan2(y_mm, x_mm), theta) <= _RADIUS_WINDOW_RAD:
            near.append(radius)
    if len(near) < 2:
        return None, "missing"
    if max(near) - min(near) > _AMBIGUOUS_SPREAD_MM:
        return None, "ambiguous"
    return float(np.median(near)), "ok"


def _star_radii(points: list[list[float]], angles: list[float]) -> tuple[list[float] | None, str]:
    values = []
    problems = 0
    for theta in angles:
        radius, status = _radius_at(points, theta)
        if radius is None:
            problems += 1
            values.append(None)
        else:
            values.append(radius)
    if problems:
        return None, "unsupported" if problems > max(2, len(angles) // 10) else "partial"
    return [float(value) for value in values if value is not None], "ok"


def _angle_name(theta: float) -> str:
    for _key, axis, label in _AXES:
        if _angular_distance(theta, axis) <= math.radians(8.0):
            return label
    return f"{math.degrees(theta):.0f} deg from +X toward +Y"


def material_intersection(limb, socket, tolerance_mm3: float = _INTERSECTION_TOLERANCE_MM3) -> dict:
    """Volume of limb material that occupies socket material.

    A failure of the Boolean operation is indeterminate. No volume is invented.
    """
    method = (
        "BRepAlgoAPI_Common of the transformed limb solid and the socket solid. "
        "Only the overlapping material counts. The cavity is empty space."
    )
    try:
        limb_copy = BRepBuilderAPI_Copy(occ_shape(limb)).Shape()
        socket_copy = BRepBuilderAPI_Copy(occ_shape(socket)).Shape()
        operation = BRepAlgoAPI_Common(limb_copy, socket_copy)
        if hasattr(operation, "SetNonDestructive"):
            operation.SetNonDestructive(True)
        if hasattr(operation, "SetFuzzyValue"):
            operation.SetFuzzyValue(1e-4)
        operation.Build()
        if not operation.IsDone():
            return {
                "status": "INDETERMINATE",
                "intersects": None,
                "volume_mm3": None,
                "tolerance_mm3": tolerance_mm3,
                "method": method,
                "error": "The Boolean common did not finish",
            }
        volume = abs(signed_volume_mm3(operation.Shape()))
    except Exception as exc:
        return {
            "status": "INDETERMINATE",
            "intersects": None,
            "volume_mm3": None,
            "tolerance_mm3": tolerance_mm3,
            "method": method,
            "error": str(exc),
        }
    if not math.isfinite(volume):
        return {
            "status": "INDETERMINATE",
            "intersects": None,
            "volume_mm3": None,
            "tolerance_mm3": tolerance_mm3,
            "method": method,
            "error": "The intersection volume was not finite",
        }
    return {
        "status": "PASS",
        "intersects": bool(volume > tolerance_mm3),
        "volume_mm3": volume,
        "tolerance_mm3": tolerance_mm3,
        "method": method,
        "error": None,
    }


def _section_report(limb_shape, socket_shape, section_id: str, z_mm: float) -> dict:
    angles = [(-math.pi + (index + 0.5) * (2.0 * math.pi / _SAMPLE_COUNT)) for index in range(_SAMPLE_COUNT)]
    for _key, axis, _label in _AXES:
        if all(abs(_angular_distance(axis, theta)) > 1e-9 for theta in angles):
            angles.append(axis)
    limb_curves = section_polylines(limb_shape, z_mm, samples=_POLYLINE_SAMPLES)
    socket_curves = section_polylines(socket_shape, z_mm, samples=_POLYLINE_SAMPLES)
    report: dict[str, Any] = {
        "id": section_id,
        "z_mm": z_mm,
        "status": "measured",
        "limb_contour_count": len(limb_curves),
        "socket_contour_count": len(socket_curves),
        "limb_perimeter_mm": None,
        "socket_inner_perimeter_mm": None,
        "socket_outer_perimeter_mm": None,
        "limb_area_mm2": None,
        "socket_inner_area_mm2": None,
        "socket_outer_area_mm2": None,
        "limb_ml_diameter_mm": None,
        "limb_ap_diameter_mm": None,
        "socket_inner_ml_diameter_mm": None,
        "socket_inner_ap_diameter_mm": None,
        "perimeter_difference_mm": None,
        "perimeter_percent_difference": None,
        "area_difference_mm2": None,
        "clearance": {
            "status": "unsupported",
            "sign_convention": "socket_inner_radius - limb_radius, from the Z axis",
            "minimum_mm": None,
            "maximum_mm": None,
            "mean_mm": None,
            "minimum_location": None,
            "axes_mm": None,
            "samples": None,
        },
    }
    if not limb_curves or not socket_curves:
        report["status"] = "no_intersection"
        report["clearance"]["status"] = "unsupported"
        report["clearance"]["reason"] = "The plane missed the limb or the socket"
        return report
    if len(limb_curves) != 1:
        report["status"] = "ambiguous"
        report["clearance"]["reason"] = "The limb section does not have one closed curve"
        return report
    if len(socket_curves) != 2:
        report["status"] = "ambiguous" if len(socket_curves) > 2 else "outer_only"
        report["clearance"]["reason"] = "The socket section does not have a distinct inner cavity curve"
        if len(socket_curves) == 1:
            report["socket_outer_perimeter_mm"] = socket_curves[0]["perimeter_mm"]
        return report

    limb = limb_curves[0]
    inner, outer = socket_curves
    report["limb_perimeter_mm"] = limb["perimeter_mm"]
    report["socket_inner_perimeter_mm"] = inner["perimeter_mm"]
    report["socket_outer_perimeter_mm"] = outer["perimeter_mm"]
    report["limb_area_mm2"] = limb["area_mm2"]
    report["socket_inner_area_mm2"] = inner["area_mm2"]
    report["socket_outer_area_mm2"] = outer["area_mm2"]
    report["limb_ml_diameter_mm"] = limb["ml_diameter_mm"]
    report["limb_ap_diameter_mm"] = limb["ap_diameter_mm"]
    report["socket_inner_ml_diameter_mm"] = inner["ml_diameter_mm"]
    report["socket_inner_ap_diameter_mm"] = inner["ap_diameter_mm"]
    report["perimeter_difference_mm"] = inner["perimeter_mm"] - limb["perimeter_mm"]
    report["perimeter_percent_difference"] = percent_change(limb["perimeter_mm"], inner["perimeter_mm"])
    if limb["area_mm2"] is not None and inner["area_mm2"] is not None:
        report["area_difference_mm2"] = inner["area_mm2"] - limb["area_mm2"]

    limb_radii, limb_state = _star_radii(limb["points_xy"], angles)
    inner_radii, inner_state = _star_radii(inner["points_xy"], angles)
    if limb_radii is None or inner_radii is None:
        report["clearance"]["status"] = "unsupported"
        report["clearance"]["reason"] = (
            "A boundary is not a single star-shaped curve about the Z axis "
            f"(limb {limb_state}, socket inner {inner_state})"
        )
        return report
    samples = []
    for theta, limb_radius, socket_radius in zip(angles, limb_radii, inner_radii):
        samples.append(
            {
                "angle_deg": math.degrees(theta),
                "limb_radius_mm": limb_radius,
                "socket_inner_radius_mm": socket_radius,
                "clearance_mm": socket_radius - limb_radius,
            }
        )
    clearances = [sample["clearance_mm"] for sample in samples]
    minimum = min(clearances)
    location = samples[clearances.index(minimum)]
    axes = {}
    for key, axis, _label in _AXES:
        match = min(samples, key=lambda sample: _angular_distance(math.radians(sample["angle_deg"]), axis))
        axes[key] = match["clearance_mm"]
    report["clearance"] = {
        "status": "measured",
        "sign_convention": "positive separation, zero contact, negative overlap along the ray",
        "sample_count": len(samples),
        "minimum_mm": minimum,
        "maximum_mm": max(clearances),
        "mean_mm": float(sum(clearances) / len(clearances)),
        "minimum_location": {
            "angle_deg": location["angle_deg"],
            "label": _angle_name(math.radians(location["angle_deg"])),
            "clearance_mm": location["clearance_mm"],
        },
        "axes_mm": axes,
        "samples": samples,
    }
    return report


def compare_prepared(prepared: dict, request: dict) -> dict:
    """Compare solids already loaded by ``prepare_aligned_pair``."""
    loaded = prepared["_loaded"]
    limb = prepared["_moved_limb"]
    socket = loaded["socket_shape"]
    explicit_z, error = (None, None)
    if "z_mm" in request:
        explicit_z, error = _finite(request.get("z_mm"), "z_mm")
        if error:
            return error
    if explicit_z is not None:
        stations = [("query", explicit_z)]
    else:
        stations = [(section["id"], float(section["z_mm"])) for section in loaded["limb_profile"]["sections"]]

    # Hash the untouched limb before section or Boolean operations. Those
    # algorithms can rewrite shared topology on the solid they are given.
    limb_hash = _evaluated_limb_hash(loaded["limb_shape"], loaded["limb_profile"], loaded["limb_step"], [])
    sections = [_section_report(limb, socket, section_id, z_mm) for section_id, z_mm in stations]
    if explicit_z is not None and sections[0]["status"] == "no_intersection":
        return _failure("no_intersection", f"No limb and socket section at z = {explicit_z} mm", section=sections[0])

    intersection = material_intersection(limb, socket)
    profile = loaded["limb_profile"]
    profile_sections = profile.get("sections")
    full_limb = (
        isinstance(profile_sections, list)
        and profile_sections
        and all(isinstance(section, dict) and "length_fraction" in section for section in profile_sections)
        and "total_length_mm" in profile
    )
    if not full_limb:
        limb_hash = _evaluated_limb_hash(loaded["limb_shape"], profile, loaded["limb_step"], sections)
    socket_hash = _socket_hash(abs(signed_volume_mm3(socket)), sections)
    relationship = relationship_record(
        loaded["limb_profile"],
        loaded["socket_profile"],
        prepared["transformation"],
        limb_hash=limb_hash,
        socket_hash=socket_hash,
    )
    limitations = [
        "Clearance rays start on the shared Z axis. A section that is not star-shaped about that axis is unsupported.",
        "Medial-lateral and anterior-posterior diameters are axis-aligned extents in the socket frame.",
        "Intersection volume below 1 mm3 is treated as Boolean dust, not as contact.",
        "A geometric gap is not a liner thickness or a clinical clearance.",
    ]
    return {
        "ok": True,
        "error": None,
        "clinical_use": False,
        "disclaimer": "Geometric comparison does not establish fit, comfort, or safety.",
        "relationship": relationship,
        "transformation": prepared["transformation"],
        "sections": [{key: value for key, value in section.items()} for section in sections],
        "material_intersection": intersection,
        "measurement_limitations": limitations,
    }


def compare_limb_socket(request: dict) -> dict:
    """Compare one limb solid with one socket solid in the socket frame."""
    if not isinstance(request, dict):
        return _failure("invalid_value", "The comparison request must be an object")
    prepared = prepare_aligned_pair(request)
    if not prepared.get("ok"):
        return {key: value for key, value in prepared.items() if not str(key).startswith("_")}
    return compare_prepared(prepared, request)


def pair_version_summary(pairs: list[dict]) -> dict:
    """Compact measured differences across pair comparisons.

    ``pairs`` is a list of ``compare_limb_socket`` results. Missing fields stay
    null instead of being copied from another pair.
    """
    rows = []
    for pair in pairs:
        if not pair.get("ok"):
            rows.append({"ok": False, "error": pair.get("error")})
            continue
        q50 = next((section for section in pair.get("sections", []) if section.get("id") == "q50"), None)
        clearance = None if q50 is None else q50.get("clearance", {})
        rows.append(
            {
                "ok": True,
                "limb_model_id": pair["relationship"]["limb_model_id"],
                "limb_version": pair["relationship"]["limb_version"],
                "socket_model_id": pair["relationship"]["socket_model_id"],
                "socket_version": pair["relationship"]["socket_version"],
                "socket_reference_limb_version": pair["relationship"]["socket_reference_limb_version"],
                "reference_status": pair["relationship"]["reference_status"],
                "q50_limb_perimeter_mm": None if q50 is None else q50.get("limb_perimeter_mm"),
                "q50_socket_inner_perimeter_mm": None if q50 is None else q50.get("socket_inner_perimeter_mm"),
                "q50_perimeter_difference_mm": None if q50 is None else q50.get("perimeter_difference_mm"),
                "q50_clearance_min_mm": None if not clearance else clearance.get("minimum_mm"),
                "q50_clearance_mean_mm": None if not clearance else clearance.get("mean_mm"),
                "q50_clearance_status": None if not clearance else clearance.get("status"),
                "intersection_volume_mm3": pair["material_intersection"].get("volume_mm3"),
                "material_intersects": pair["material_intersection"].get("intersects"),
                "intersection_status": pair["material_intersection"].get("status"),
            }
        )
    return {"clinical_use": False, "pairs": rows}
