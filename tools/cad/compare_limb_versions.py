"""Compare two limb STEP files by measuring each solid.

Targets are never copied into the measured fields. A zero original value
leaves ``percent_change`` unset instead of dividing by zero.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from tools.cad.generate_limb import PROFILE_PATH, REFERENCE_STEP, load_profile
from tools.cad.measure_limb import STANDARD_STATIONS, measure_limb
from tools.cad.modify_limb import value_within_tolerance

TARGET_ALIASES = {"middle_circumference_mm": "circumference_50_percent_mm"}
CIRCUMFERENCE_KEYS = {
    "proximal": "proximal_circumference_mm",
    "q25": "circumference_25_percent_mm",
    "q50": "circumference_50_percent_mm",
    "q75": "circumference_75_percent_mm",
    "distal_reference": "distal_reference_circumference_mm",
}


def percent_change(before: float, after: float) -> float | None:
    """Percent change from ``before`` to ``after``. ``None`` when ``before`` is 0."""
    if before == 0:
        return None
    return (after - before) / abs(before) * 100.0


def _failure(code: str, message: str, **details: Any) -> dict:
    error: dict[str, Any] = {"code": code, "message": message}
    if details:
        error["details"] = details
    return {
        "ok": False,
        "error": error,
        "geometry_valid": False,
        "comparison": {},
        "clinical_use": False,
    }


def _resolve(spec: str | Path, profile: dict | None) -> tuple[Path | None, dict | None, str, dict | None]:
    """Return ``(step_path, profile, model_id, error)``."""
    if isinstance(spec, Path) or (isinstance(spec, str) and (spec.endswith(".step") or "/" in spec or "\\" in spec)):
        path = Path(spec)
        model_id = profile["model_id"] if profile and "model_id" in profile else path.stem
        if not path.is_file():
            return None, None, model_id, _failure("missing_file", f"No STEP file at {path}")
        return path, profile, model_id, None
    if not isinstance(spec, str):
        return None, None, "", _failure("unknown_model", "A model id or a STEP path is required")
    standard = load_profile(PROFILE_PATH)
    if spec == standard["model_id"]:
        if not REFERENCE_STEP.is_file():
            return None, None, spec, _failure("missing_file", f"No reference STEP at {REFERENCE_STEP}")
        return REFERENCE_STEP, profile or standard, spec, None
    return None, None, spec, _failure(
        "unknown_model",
        f"Unknown model id {spec!r}. Pass a STEP path, or {standard['model_id']!r}.",
    )


def _section_map(measured: dict) -> dict[str, dict]:
    return {row["id"]: row for row in measured.get("sections", [])}


def _metric(
    before: float | None,
    after: float | None,
    target: float | None,
    tolerance: float | None,
) -> dict:
    if before is None or after is None:
        return {
            "status": "missing",
            "before": before,
            "after": after,
            "absolute_change": None,
            "percent_change": None,
            "target": target,
            "deviation_from_target": None,
            "within_tolerance": None,
        }
    absolute = after - before
    deviation = None if target is None else after - target
    within = None
    if target is not None and tolerance is not None:
        within = value_within_tolerance(deviation, tolerance)
    return {
        "status": "measured",
        "before": before,
        "after": after,
        "absolute_change": absolute,
        "percent_change": percent_change(before, after),
        "target": target,
        "deviation_from_target": deviation,
        "within_tolerance": within,
    }


def _lookup_target(targets: dict, key: str) -> float | None:
    if key in targets:
        return None if targets[key] is None else float(targets[key])
    for alias, canonical in TARGET_ALIASES.items():
        if canonical == key and alias in targets:
            return float(targets[alias])
    return None


def compare_limb_versions(
    original: str | Path,
    modified: str | Path,
    *,
    original_profile: dict | None = None,
    modified_profile: dict | None = None,
    targets: dict | None = None,
    tolerances: dict | None = None,
) -> dict:
    """Measure both STEP files and report original, modified, and differences.

    ``original`` and ``modified`` are STEP paths or the standard model id.
    Optional profiles supply the station positions for each solid.
    """
    original_path, original_profile, original_id, error = _resolve(original, original_profile)
    if error:
        return error
    modified_path, modified_profile, modified_id, error = _resolve(modified, modified_profile)
    if error:
        return error
    assert original_path is not None and modified_path is not None

    before = measure_limb(original_path, original_profile)
    if not before.get("ok") and before.get("error", {}).get("code") in {"missing_file", "invalid_step"}:
        failed = dict(before)
        failed["geometry_valid"] = False
        failed["comparison"] = {}
        failed["original_model_id"] = original_id
        failed["modified_model_id"] = modified_id
        return failed
    after = measure_limb(modified_path, modified_profile)
    if not after.get("ok") and after.get("error", {}).get("code") in {"missing_file", "invalid_step"}:
        failed = dict(after)
        failed["geometry_valid"] = False
        failed["comparison"] = {}
        failed["original_model_id"] = original_id
        failed["modified_model_id"] = modified_id
        return failed

    standard = load_profile(PROFILE_PATH)
    tolerances = dict(tolerances or {})
    circumference_tol = float(tolerances.get("circumference_mm", standard["tolerances"]["circumference_mm"]))
    length_tol = float(tolerances.get("length_mm", standard["tolerances"]["length_mm"]))
    volume_tol = tolerances.get("volume_mm3", 1000.0)
    bbox_tol = float(tolerances.get("bounding_box_mm", 0.5))
    target_map = dict(targets or {})

    comparison: dict[str, Any] = {}
    before_sections = _section_map(before)
    after_sections = _section_map(after)
    station_ids = [name for name, _fraction in STANDARD_STATIONS]
    if original_profile is not None:
        station_ids = [section["id"] for section in original_profile["sections"]]

    length_before = (before.get("material_extent_mm") or {}).get("length_mm")
    length_after = (after.get("material_extent_mm") or {}).get("length_mm")
    comparison["total_length_mm"] = _metric(
        length_before,
        length_after,
        _lookup_target(target_map, "total_length_mm"),
        length_tol,
    )

    for section_id in station_ids:
        key = CIRCUMFERENCE_KEYS.get(section_id, f"{section_id}_circumference_mm")
        left = before_sections.get(section_id)
        right = after_sections.get(section_id)
        left_value = None if left is None or left.get("status") != "measured" else left["measured_circumference_mm"]
        right_value = None if right is None or right.get("status") != "measured" else right["measured_circumference_mm"]
        comparison[key] = _metric(
            left_value,
            right_value,
            _lookup_target(target_map, key),
            circumference_tol,
        )

    comparison["volume_mm3"] = _metric(
        before.get("volume_mm3"),
        after.get("volume_mm3"),
        _lookup_target(target_map, "volume_mm3"),
        None if volume_tol is None else float(volume_tol),
    )

    for axis, size_name in (("x", "bounding_box_x_mm"), ("y", "bounding_box_y_mm"), ("z", "bounding_box_z_mm")):
        comparison[size_name] = _metric(
            _box_size(before, axis),
            _box_size(after, axis),
            _lookup_target(target_map, size_name),
            bbox_tol,
        )

    geometry_valid = bool(
        before.get("valid_solid")
        and after.get("valid_solid")
        and before.get("solid_count") == 1
        and after.get("solid_count") == 1
    )
    undefined = [
        key
        for key, row in comparison.items()
        if row.get("status") == "measured" and row.get("percent_change") is None and row.get("before") == 0
    ]
    return {
        "ok": True,
        "error": None,
        "clinical_use": False,
        "original_model_id": original_id,
        "modified_model_id": modified_id,
        "units": "mm",
        "geometry_valid": geometry_valid,
        "comparison": comparison,
        "undefined_percent_change": undefined,
        "tolerances": {
            "circumference_mm": circumference_tol,
            "length_mm": length_tol,
            "volume_mm3": volume_tol,
            "bounding_box_mm": bbox_tol,
        },
    }


def _box_size(measured: dict, axis: str) -> float | None:
    box = measured.get("bounding_box_mm") or {}
    try:
        if axis == "x":
            return float(box["xmax_mm"]) - float(box["xmin_mm"])
        if axis == "y":
            return float(box["ymax_mm"]) - float(box["ymin_mm"])
        return float(box["zmax_mm"]) - float(box["zmin_mm"])
    except (KeyError, TypeError):
        return None

