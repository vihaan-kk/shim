"""Change numerical limb parameters and rebuild a new STEP file.

The original profile and the reference STEP are never written. Circumference
edits use ``generate_limb``. A percent change is applied to the measured
circumference of the base solid, not to a guessed example value.

Section positions follow ``length_fraction``. Changing total length keeps
those fractions and the circumference numbers, then recomputes ``z_mm`` and
the distal cap.
"""

from __future__ import annotations

import json
import math
import re
import uuid
from pathlib import Path
from typing import Any

from tools.cad.generate_limb import (
    PROFILE_PATH,
    REFERENCE_DIR,
    REFERENCE_REPORT,
    REFERENCE_STEP,
    REFERENCE_STL,
    SOCKET_PROFILE_PATH,
    SOCKET_REPORT,
    SOCKET_STEP,
    SOCKET_STL,
    export_solid,
    generate_limb,
    load_profile,
    parameters_from_profile,
    profile_with_total_length,
    updated_profile,
)
from tools.cad.measure_limb import load_step_shape, measure_shape, section_circumference
from tools.cad.validate_limb import validate_limb

OPERATIONS = (
    "set_section_circumference",
    "change_section_circumference_percent",
    "set_total_length",
)
PRESERVE_KEYS = ("total_length", "proximal_circumference")
REQUEST_FIELDS = {
    "base_model_id",
    "base_model_path",
    "operation",
    "section_fraction",
    "section_id",
    "circumference_mm",
    "change_percent",
    "total_length_mm",
    "preserve",
    "output_dir",
    "candidate_id",
}
_CANDIDATE_ID = re.compile(r"[A-Za-z0-9._-]{1,80}")


def _failure(code: str, message: str, **details: Any) -> dict:
    error: dict[str, Any] = {"code": code, "message": message}
    if details:
        error["details"] = details
    return {"ok": False, "error": error, "clinical_use": False}


def _finite(value: Any, name: str) -> tuple[float | None, dict | None]:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None, _failure("invalid_value", f"{name} must be a number")
    number = float(value)
    if not math.isfinite(number):
        return None, _failure("non_finite", f"{name} must be a finite number")
    return number, None


def value_within_tolerance(deviation: float, tolerance: float) -> bool:
    """True when ``abs(deviation)`` is within ``tolerance``.

    The comparison is rounded to 1e-9 mm so a decimal tolerance such as 0.05
    is not rejected by binary floating-point noise.
    """
    return round(abs(deviation) - tolerance, 9) <= 0.0


def new_candidate_id(model_id: str, operation: str, explicit: str | None = None) -> str:
    """File-safe id. An omitted id includes a unique suffix."""
    if explicit is not None:
        if not isinstance(explicit, str) or _CANDIDATE_ID.fullmatch(explicit) is None:
            raise ValueError("candidate_id must be a short file-safe token")
        return explicit
    return f"{model_id}-{operation}-{uuid.uuid4().hex[:8]}"


def _protected(path: Path) -> bool:
    resolved = path.resolve()
    blocked = {
        PROFILE_PATH.resolve(),
        REFERENCE_STEP.resolve(),
        REFERENCE_STL.resolve(),
        REFERENCE_REPORT.resolve(),
        REFERENCE_DIR.resolve(),
        PROFILE_PATH.parent.resolve(),
        SOCKET_PROFILE_PATH.resolve(),
        SOCKET_STEP.resolve(),
        SOCKET_STL.resolve(),
        SOCKET_REPORT.resolve(),
    }
    return resolved in blocked


def _load_base(request: dict) -> tuple[dict | None, Path | None, dict | None]:
    raw_path = request.get("base_model_path")
    model_id = request.get("base_model_id")
    if raw_path is None and model_id is None:
        return None, None, _failure("unknown_model", "Pass base_model_id or base_model_path")
    if raw_path is not None:
        path = Path(raw_path)
        if not path.is_file():
            return None, None, _failure("missing_file", f"No profile at {path}")
        try:
            profile = load_profile(path)
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            return None, None, _failure("invalid_value", f"Could not read the profile: {exc}")
        return profile, path, None
    standard = load_profile(PROFILE_PATH)
    if model_id != standard["model_id"]:
        return None, None, _failure(
            "unknown_model",
            f"Unknown base_model_id {model_id!r}. Known id: {standard['model_id']!r}.",
            known_model_id=standard["model_id"],
        )
    return standard, PROFILE_PATH, None


def _find_section(profile: dict, request: dict) -> tuple[dict | None, dict | None]:
    section_id = request.get("section_id")
    fraction = request.get("section_fraction")
    if section_id is None and fraction is None:
        return None, _failure("invalid_section", "Pass section_id or section_fraction")
    if fraction is not None:
        number, error = _finite(fraction, "section_fraction")
        if error:
            return None, error
        fraction = number
    matches = []
    for section in profile["sections"]:
        if section_id is not None and section["id"] != section_id:
            continue
        if fraction is not None and abs(float(section["length_fraction"]) - float(fraction)) > 1e-6:
            continue
        matches.append(section)
    if len(matches) != 1:
        known = [
            {"id": section["id"], "length_fraction": section["length_fraction"]}
            for section in profile["sections"]
        ]
        return None, _failure(
            "invalid_section",
            "The section does not match a station on this limb",
            known_sections=known,
        )
    return matches[0], None


def preservation_report(
    base: dict,
    candidate: dict,
    preserve: list[str],
    tolerances: dict,
) -> dict:
    """Compare preserved measurements. Values are the measured numbers, not targets."""
    checks = []
    for name in preserve:
        if name == "total_length":
            before = base["material_extent_mm"]["length_mm"]
            after = candidate["material_extent_mm"]["length_mm"]
            tolerance = float(tolerances["length_mm"])
            unit = "mm"
        elif name == "proximal_circumference":
            before = _circumference(base, "proximal")
            after = _circumference(candidate, "proximal")
            tolerance = float(tolerances["circumference_mm"])
            unit = "mm"
        else:
            checks.append(
                {
                    "name": name,
                    "passed": False,
                    "detail": f"Unsupported preservation constraint {name!r}",
                }
            )
            continue
        if before is None or after is None:
            checks.append(
                {
                    "name": name,
                    "passed": False,
                    "detail": "Measurement missing",
                    "before": before,
                    "after": after,
                }
            )
            continue
        change = after - before
        checks.append(
            {
                "name": name,
                "passed": value_within_tolerance(change, tolerance),
                "before": before,
                "after": after,
                "absolute_change": change,
                "tolerance": tolerance,
                "units": unit,
            }
        )
    return {"passed": all(item["passed"] for item in checks), "checks": checks}


def _circumference(measured: dict, section_id: str) -> float | None:
    for row in measured.get("sections", []):
        if row.get("id") == section_id and row.get("status", "measured") == "measured":
            return float(row["measured_circumference_mm"])
    return None


def _measurements_from_validation(validation: dict, profile: dict) -> dict:
    by_id = {section["id"]: section for section in profile["sections"]}
    sections = []
    for row in validation.get("measurements", []):
        source = by_id.get(row["id"], {})
        sections.append(
            {
                "id": row["id"],
                "length_fraction": source.get("length_fraction"),
                "z_mm": row["z_mm"],
                "measured_circumference_mm": row["measured_circumference_mm"],
                "target_circumference_mm": row["target_circumference_mm"],
                "error_mm": row["error_mm"],
                "edge_count": row["edge_count"],
                "status": "measured" if row["edge_count"] else "no_intersection",
            }
        )
    return {
        "ok": validation.get("passed", False),
        "units": "mm",
        "measured_from": "reimported_step",
        "material_extent_mm": validation.get("material_extent_mm"),
        "bounding_box_mm": validation.get("kernel_bounding_box_mm"),
        "volume_mm3": validation.get("signed_volume_mm3"),
        "sections": sections,
    }


def _base_shape(profile: dict, profile_path: Path | None):
    if (
        profile_path is not None
        and profile_path.resolve() == PROFILE_PATH.resolve()
        and REFERENCE_STEP.is_file()
    ):
        return load_step_shape(REFERENCE_STEP)
    return generate_limb(parameters_from_profile(profile))


def modify_limb(request: dict) -> dict:
    """Apply one structured edit and write a new profile and STEP file.

    The result is JSON-compatible. ``ok`` is true only when the rebuilt solid
    meets the requested target and every preservation constraint.
    """
    if not isinstance(request, dict):
        return _failure("invalid_value", "The modification request must be an object")
    unknown = sorted(set(request) - REQUEST_FIELDS)
    if unknown:
        return _failure("invalid_value", "The request contains unsupported fields", fields=unknown)

    operation = request.get("operation")
    if operation not in OPERATIONS:
        return _failure(
            "unsupported_operation",
            f"Unsupported operation {operation!r}",
            supported_operations=list(OPERATIONS),
        )
    output_dir = request.get("output_dir")
    if not isinstance(output_dir, (str, Path)) or str(output_dir) == "":
        return _failure("invalid_value", "output_dir is required")
    output_path = Path(output_dir)
    if _protected(output_path):
        return _failure("protected_output", "Refusing to write into the reference model directory")

    preserve = request.get("preserve", [])
    if not isinstance(preserve, list) or not all(isinstance(item, str) for item in preserve):
        return _failure("invalid_value", "preserve must be a list of constraint names")
    bad_constraints = sorted(set(preserve) - set(PRESERVE_KEYS))
    if bad_constraints:
        return _failure(
            "invalid_value",
            "Unsupported preservation constraint",
            constraints=bad_constraints,
            supported=list(PRESERVE_KEYS),
        )

    profile, profile_path, error = _load_base(request)
    if error:
        return error
    assert profile is not None

    try:
        candidate_id = new_candidate_id(
            profile["model_id"],
            operation,
            request.get("candidate_id"),
        )
    except ValueError as exc:
        return _failure("invalid_value", str(exc))

    step_path = output_path / f"{candidate_id}.step"
    json_path = output_path / f"{candidate_id}.json"
    if _protected(step_path) or _protected(json_path):
        return _failure("protected_output", "Refusing to overwrite the reference model")

    section = None
    requested_target: float | None = None
    base_measured_value: float | None = None
    if operation == "set_total_length":
        if any(key in request for key in ("section_id", "section_fraction", "circumference_mm", "change_percent")):
            return _failure("invalid_value", "set_total_length does not take section fields")
        if "total_length" in preserve:
            return _failure(
                "constraint_conflict",
                "Cannot change total length and preserve total_length",
            )
        length, error = _finite(request.get("total_length_mm"), "total_length_mm")
        if error:
            return error
        assert length is not None
        if length <= 0:
            return _failure("invalid_value", "total_length_mm must be positive")
        revised = profile_with_total_length(profile, length)
        requested_target = length
    else:
        if "total_length_mm" in request:
            return _failure("invalid_value", f"{operation} does not take total_length_mm")
        section, error = _find_section(profile, request)
        if error:
            return error
        assert section is not None
        if section["id"] == "proximal" and "proximal_circumference" in preserve:
            return _failure(
                "constraint_conflict",
                "Cannot change the proximal circumference and preserve it",
            )
        if operation == "set_section_circumference":
            if "change_percent" in request:
                return _failure("invalid_value", "Pass circumference_mm, not change_percent")
            target, error = _finite(request.get("circumference_mm"), "circumference_mm")
            if error:
                return error
            assert target is not None
            if target <= 0:
                return _failure("invalid_value", "circumference_mm must be positive")
            requested_target = target
        else:
            if "circumference_mm" in request:
                return _failure("invalid_value", "Pass change_percent, not circumference_mm")
            change, error = _finite(request.get("change_percent"), "change_percent")
            if error:
                return error
            assert change is not None
            if change <= -100:
                return _failure("invalid_value", "change_percent must be greater than -100")
            try:
                base_shape = _base_shape(profile, profile_path)
                measured, edges = section_circumference(base_shape, float(section["z_mm"]))
            except Exception as exc:
                return _failure("geometry_failed", f"Could not measure the base model: {exc}")
            if edges != 1:
                return _failure(
                    "geometry_failed",
                    f"The base section at z = {section['z_mm']} mm has {edges} curves",
                )
            base_measured_value = float(measured)
            requested_target = base_measured_value * (1.0 + change / 100.0)
        revised = updated_profile(profile, section["id"], circumference_mm=requested_target)

    revised["model_id"] = candidate_id
    revised["base_model_id"] = profile["model_id"]
    revised["modification"] = {
        "operation": operation,
        "section_id": None if section is None else section["id"],
        "requested_target": requested_target,
        "units": "mm",
    }

    try:
        parameters = parameters_from_profile(revised)
        shape = generate_limb(parameters)
    except (RuntimeError, ValueError, TypeError) as exc:
        return _failure("geometry_failed", str(exc), candidate_id=candidate_id)

    output_path.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(revised, indent=2) + "\n")
    try:
        export_solid(shape, step_path, overwrite_reference=False)
    except Exception as exc:
        return _failure("export_failed", f"STEP export failed: {exc}", candidate_id=candidate_id)

    try:
        imported_shape = load_step_shape(step_path)
    except Exception as exc:
        return _failure("invalid_step", f"Reimport failed: {exc}", files={"step": str(step_path)})
    validation = validate_limb(imported_shape, revised)

    candidate_measurements = _measurements_from_validation(validation, revised)
    try:
        base_shape = _base_shape(profile, profile_path)
        base_measurements = measure_shape(base_shape, profile)
    except Exception as exc:
        return _failure("geometry_failed", f"Could not measure the base model: {exc}")

    preserved = preservation_report(
        base_measurements,
        candidate_measurements,
        preserve,
        revised["tolerances"],
    )
    geometry_ok = bool(validation.get("passed"))
    constraints_ok = bool(preserved["passed"])
    ok = geometry_ok and constraints_ok
    error = None
    if not constraints_ok:
        error = {
            "code": "constraint_violated",
            "message": "A preserved measurement changed by more than its tolerance",
            "details": {"checks": preserved["checks"]},
        }
    elif not geometry_ok:
        failed = [item for item in validation.get("checks", []) if not item.get("passed")]
        error = {
            "code": "target_not_met",
            "message": "The rebuilt solid missed a geometric check",
            "details": {"checks": failed},
        }

    return {
        "ok": ok,
        "error": error,
        "clinical_use": False,
        "candidate_id": candidate_id,
        "base_model_id": profile["model_id"],
        "operation": operation,
        "requested_target": requested_target,
        "requested_target_units": "mm",
        "base_measured_value": base_measured_value,
        "profile": revised,
        "measurements": candidate_measurements,
        "base_measurements": {
            "units": "mm",
            "material_extent_mm": base_measurements.get("material_extent_mm"),
            "sections": base_measurements.get("sections"),
        },
        "validation": validation,
        "preserved": preserved,
        "files": {"step": str(step_path), "profile": str(json_path)},
        "measured_from": "reimported_step",
    }
