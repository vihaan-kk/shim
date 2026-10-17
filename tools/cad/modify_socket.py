"""Change socket parameters and rebuild a new STEP file.

The reference socket, its JSON, and the referenced limb are never written.
A percent-style edit is not used here. Each operation sets one explicit number.
Inner circumference edits are applied to the measured station only through a
radius offset on the socket profile. The limb profile is not changed.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

from tools.cad.compare_limb_versions import percent_change
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
    ellipse_circumference,
    load_profile,
)
from tools.cad.generate_socket import (
    _ml_radius,
    compile_socket,
    export_socket,
    generate_socket,
    inner_ml_radius,
    load_socket_profile,
    with_derived,
)
from tools.cad.measure_limb import load_step_shape
from tools.cad.measure_socket import measure_socket, section_value
from tools.cad.modify_limb import _finite, new_candidate_id, value_within_tolerance
from tools.cad.validate_socket import validate_socket

OPERATIONS = (
    "set_nominal_wall_thickness",
    "set_socket_depth",
    "set_proximal_opening_ml_diameter",
    "set_inner_section_circumference",
    "set_inner_radial_clearance",
    "set_section_wall_extra",
)
PRESERVE_KEYS = (
    "socket_depth",
    "wall_thickness",
    "proximal_opening_ml",
    "inner_circumference_q50",
)
REQUEST_FIELDS = {
    "base_socket_id",
    "base_socket_path",
    "limb_profile_path",
    "operation",
    "section_id",
    "section_fraction",
    "wall_thickness_mm",
    "socket_depth_mm",
    "opening_ml_diameter_mm",
    "circumference_mm",
    "inner_radial_clearance_mm",
    "wall_extra_mm",
    "preserve",
    "output_dir",
    "candidate_id",
}
_CONFLICTS = {
    "set_nominal_wall_thickness": {"wall_thickness"},
    "set_socket_depth": {"socket_depth"},
    "set_proximal_opening_ml_diameter": {"proximal_opening_ml"},
    "set_inner_radial_clearance": {"inner_circumference_q50"},
}
_COMMON_FIELDS = {
    "base_socket_id",
    "base_socket_path",
    "limb_profile_path",
    "operation",
    "preserve",
    "output_dir",
    "candidate_id",
}
_OPERATION_FIELDS = {
    "set_nominal_wall_thickness": {"wall_thickness_mm"},
    "set_socket_depth": {"socket_depth_mm"},
    "set_proximal_opening_ml_diameter": {"opening_ml_diameter_mm"},
    "set_inner_radial_clearance": {"inner_radial_clearance_mm"},
    "set_inner_section_circumference": {"section_id", "section_fraction", "circumference_mm"},
    "set_section_wall_extra": {"section_id", "section_fraction", "wall_extra_mm"},
}


def _failure(code: str, message: str, **details: Any) -> dict:
    error: dict[str, Any] = {"code": code, "message": message}
    if details:
        error["details"] = details
    return {"ok": False, "error": error, "clinical_use": False}


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
    return resolved in blocked or REFERENCE_DIR.resolve() in resolved.parents or PROFILE_PATH.parent.resolve() in resolved.parents


def _load_socket(request: dict) -> tuple[dict | None, Path | None, dict | None]:
    raw_path = request.get("base_socket_path")
    model_id = request.get("base_socket_id")
    if raw_path is None and model_id is None:
        return None, None, _failure("unknown_model", "Pass base_socket_id or base_socket_path")
    if raw_path is not None:
        path = Path(raw_path)
        if not path.is_file():
            return None, None, _failure("missing_file", f"No socket profile at {path}")
        try:
            profile = load_socket_profile(path)
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            return None, None, _failure("invalid_value", f"Could not read the socket profile: {exc}")
        return profile, path, None
    standard = load_socket_profile(SOCKET_PROFILE_PATH)
    if model_id != standard["socket_model_id"]:
        return None, None, _failure(
            "unknown_model",
            f"Unknown socket id {model_id!r}. Pass base_socket_path for another profile.",
        )
    return standard, SOCKET_PROFILE_PATH, None


def _load_limb(request: dict) -> tuple[dict | None, dict | None]:
    raw = request.get("limb_profile_path")
    if raw is None:
        return load_profile(PROFILE_PATH), None
    path = Path(raw)
    if not path.is_file():
        return None, _failure("missing_file", f"No limb profile at {path}")
    try:
        return load_profile(path), None
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        return None, _failure("invalid_value", f"Could not read the limb profile: {exc}")


def _find_section(limb_profile: dict, request: dict) -> tuple[dict | None, dict | None]:
    if "section_id" in request and "section_fraction" in request:
        return None, _failure("invalid_value", "Pass section_id or section_fraction, not both")
    sections = limb_profile["sections"]
    if "section_id" in request:
        matches = [section for section in sections if section["id"] == request["section_id"]]
    elif "section_fraction" in request:
        fraction, error = _finite(request["section_fraction"], "section_fraction")
        if error:
            return None, error
        matches = [section for section in sections if abs(float(section["length_fraction"]) - fraction) <= 1e-6]
    else:
        return None, _failure("invalid_section", "Pass section_id or section_fraction")
    if len(matches) != 1:
        return None, _failure(
            "invalid_section",
            "The section does not match a limb station",
            known_sections=[section["id"] for section in sections],
        )
    return matches[0], None


def _base_shape(profile: dict, profile_path: Path | None, limb_profile: dict):
    if (
        profile_path is not None
        and profile_path.resolve() == SOCKET_PROFILE_PATH.resolve()
        and SOCKET_STEP.is_file()
    ):
        return load_step_shape(SOCKET_STEP)
    return generate_socket(limb_profile, profile)


def _metric(measured: dict, name: str) -> float | None:
    if name == "socket_depth":
        value = measured.get("depth_mm")
        return None if value is None else float(value)
    if name == "wall_thickness":
        return section_value(measured, "q50", "ml_wall_thickness_mm")
    if name == "proximal_opening_ml":
        value = measured.get("proximal_opening", {}).get("inner_ml_diameter_mm")
        return None if value is None else float(value)
    if name == "inner_circumference_q50":
        return section_value(measured, "q50", "inner_perimeter_mm")
    return None


def _preservation(before: dict, after: dict, preserve: list[str], tolerances: dict) -> dict:
    tolerance_for = {
        "socket_depth": float(tolerances["depth_mm"]),
        "wall_thickness": float(tolerances["wall_thickness_mm"]),
        "proximal_opening_ml": float(tolerances["opening_diameter_mm"]),
        "inner_circumference_q50": float(tolerances["circumference_mm"]),
    }
    checks = []
    for name in preserve:
        earlier = _metric(before, name)
        later = _metric(after, name)
        if earlier is None or later is None:
            checks.append(
                {
                    "name": name,
                    "passed": False,
                    "before": earlier,
                    "after": later,
                    "detail": "Measurement missing",
                }
            )
            continue
        change = later - earlier
        checks.append(
            {
                "name": name,
                "passed": value_within_tolerance(change, tolerance_for[name]),
                "before": earlier,
                "after": later,
                "absolute_change": change,
                "tolerance": tolerance_for[name],
                "units": "mm",
            }
        )
    return {"passed": all(item["passed"] for item in checks) if checks else True, "checks": checks}


def _changes(before: dict, after: dict) -> dict:
    rows = {}
    for name in PRESERVE_KEYS:
        earlier = _metric(before, name)
        later = _metric(after, name)
        if earlier is None or later is None:
            rows[name] = {"status": "missing", "before": earlier, "after": later}
            continue
        rows[name] = {
            "before": earlier,
            "after": later,
            "absolute_change": later - earlier,
            "percent_change": percent_change(earlier, later),
        }
    earlier_volume = float(before["volume_mm3"])
    later_volume = float(after["volume_mm3"])
    rows["volume_mm3"] = {
        "before": earlier_volume,
        "after": later_volume,
        "absolute_change": later_volume - earlier_volume,
        "percent_change": percent_change(earlier_volume, later_volume),
    }
    return rows


def _apply(operation: str, request: dict, profile: dict, limb_profile: dict, spec) -> tuple[dict | None, float | None, dict | None]:
    revised = copy.deepcopy(profile)
    limb_radius = _ml_radius(spec.limb)
    if operation == "set_nominal_wall_thickness":
        wall, error = _finite(request.get("wall_thickness_mm"), "wall_thickness_mm")
        if error:
            return None, None, error
        assert wall is not None
        if wall <= 0:
            return None, None, _failure("invalid_value", "wall_thickness_mm must be positive")
        revised["nominal_wall_thickness_mm"] = wall
        return revised, wall, None
    if operation == "set_socket_depth":
        depth, error = _finite(request.get("socket_depth_mm"), "socket_depth_mm")
        if error:
            return None, None, error
        assert depth is not None
        if depth <= 0:
            return None, None, _failure("invalid_value", "socket_depth_mm must be positive")
        revised["socket_depth_mm"] = depth
        return revised, depth, None
    if operation == "set_proximal_opening_ml_diameter":
        diameter, error = _finite(request.get("opening_ml_diameter_mm"), "opening_ml_diameter_mm")
        if error:
            return None, None, error
        assert diameter is not None
        if diameter <= 0:
            return None, None, _failure("invalid_value", "opening_ml_diameter_mm must be positive")
        without_flare = inner_ml_radius(spec, limb_radius, 0.0) - spec.brim_flare_mm
        flare = diameter / 2.0 - without_flare
        if flare < 0 or flare > 25:
            return None, None, _failure(
                "invalid_value",
                "That opening does not fit this brim. The flare would leave the 0 to 25 mm range.",
                brim_flare_mm=flare,
            )
        revised["brim_flare_mm"] = flare
        return revised, diameter, None
    if operation == "set_inner_radial_clearance":
        clearance, error = _finite(request.get("inner_radial_clearance_mm"), "inner_radial_clearance_mm")
        if error:
            return None, None, error
        assert clearance is not None
        if clearance < 0:
            return None, None, _failure("invalid_value", "inner_radial_clearance_mm cannot be negative")
        revised["inner_radial_clearance_mm"] = clearance
        return revised, clearance, None
    section, error = _find_section(limb_profile, request)
    if error:
        return None, None, error
    assert section is not None
    if operation == "set_inner_section_circumference":
        circumference, error = _finite(request.get("circumference_mm"), "circumference_mm")
        if error:
            return None, None, error
        assert circumference is not None
        if circumference <= 0:
            return None, None, _failure("invalid_value", "circumference_mm must be positive")
        unit = ellipse_circumference(spec.limb.ap_over_ml, 1.0)
        ml_semi = circumference / unit
        z = float(section["z_mm"])
        without_offset = inner_ml_radius(spec, limb_radius, z) - float(spec.inner_offset_at(z))
        revised["inner_radius_offset_mm"] = dict(revised.get("inner_radius_offset_mm", {}))
        revised["inner_radius_offset_mm"][section["id"]] = ml_semi - without_offset
        return revised, circumference, None
    extra, error = _finite(request.get("wall_extra_mm"), "wall_extra_mm")
    if error:
        return None, None, error
    assert extra is not None
    if spec.nominal_wall_thickness_mm + extra < 0.4:
        return None, None, _failure("invalid_value", "That extra would make the local wall thinner than 0.4 mm")
    revised["section_wall_extra_mm"] = dict(revised.get("section_wall_extra_mm", {}))
    revised["section_wall_extra_mm"][section["id"]] = extra
    return revised, extra, None


def modify_socket(request: dict) -> dict:
    """Apply one socket edit and write a new profile and STEP file.

    ``ok`` is true only when the reimported solid passes validation and every
    preservation constraint. Requested targets and measured values are separate
    fields.
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
    unused = sorted(set(request) - _COMMON_FIELDS - _OPERATION_FIELDS[operation])
    if unused:
        return _failure("invalid_value", "The request contains fields this operation does not use", fields=unused)
    output_dir = request.get("output_dir")
    if not isinstance(output_dir, (str, Path)) or str(output_dir) == "":
        return _failure("invalid_value", "output_dir is required")
    output_path = Path(output_dir)
    if _protected(output_path):
        return _failure("protected_output", "Refusing to write into a reference directory")

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
    conflicts = set(_CONFLICTS.get(operation, ()))
    if operation in {"set_inner_section_circumference", "set_section_wall_extra"}:
        section_id = request.get("section_id")
        fraction = request.get("section_fraction")
        edits_q50 = section_id == "q50" or fraction == 0.5
        if edits_q50 and operation == "set_inner_section_circumference":
            conflicts.add("inner_circumference_q50")
        if edits_q50 and operation == "set_section_wall_extra":
            conflicts.add("wall_thickness")
    hit = sorted(conflicts & set(preserve))
    if hit:
        return _failure("constraint_conflict", "Cannot change a measurement the request also preserves", constraints=hit)

    profile, profile_path, error = _load_socket(request)
    if error:
        return error
    assert profile is not None
    limb_profile, error = _load_limb(request)
    if error:
        return error
    assert limb_profile is not None
    try:
        spec = compile_socket(limb_profile, profile)
    except (ValueError, KeyError, TypeError) as exc:
        return _failure("invalid_value", str(exc))

    try:
        candidate_id = new_candidate_id(profile["socket_model_id"], operation, request.get("candidate_id"))
    except ValueError as exc:
        return _failure("invalid_value", str(exc))
    step_path = output_path / f"{candidate_id}.step"
    json_path = output_path / f"{candidate_id}.json"
    if _protected(step_path) or _protected(json_path):
        return _failure("protected_output", "Refusing to overwrite a reference file")

    revised, requested, error = _apply(operation, request, profile, limb_profile, spec)
    if error:
        return error
    assert revised is not None and requested is not None
    revised["socket_model_id"] = candidate_id
    revised["model_version"] = f"{profile['model_version']}+{operation}"
    revised["base_socket_id"] = profile["socket_model_id"]
    revised["modification"] = {
        "operation": operation,
        "requested_target": requested,
        "units": "mm",
    }
    revised["clinical_use"] = False
    try:
        revised = with_derived(limb_profile, revised)
        shape = generate_socket(limb_profile, revised)
    except (RuntimeError, ValueError, TypeError) as exc:
        code = "invalid_value" if isinstance(exc, ValueError) else "geometry_failed"
        return _failure(code, str(exc), candidate_id=candidate_id)

    output_path.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(revised, indent=2) + "\n")
    try:
        export_socket(shape, step_path)
    except Exception as exc:
        return _failure("export_failed", f"STEP export failed: {exc}", candidate_id=candidate_id)
    try:
        imported = load_step_shape(step_path)
    except Exception as exc:
        return _failure("invalid_step", f"Reimport failed: {exc}", files={"step": str(step_path)})

    validation = validate_socket(imported, revised, limb_profile, step_path=step_path)
    try:
        base_shape = _base_shape(profile, profile_path, limb_profile)
        before = measure_socket(base_shape, profile, limb_profile)
        after = measure_socket(imported, revised, limb_profile)
    except Exception as exc:
        return _failure("geometry_failed", f"Could not measure the socket: {exc}")
    if not before.get("ok") or not after.get("ok"):
        return _failure("geometry_failed", "Measurement of the base or candidate socket failed")

    preserved = _preservation(before, after, preserve, revised["tolerances"])
    geometry_ok = bool(validation.get("passed"))
    constraints_ok = bool(preserved["passed"])
    ok = geometry_ok and constraints_ok
    error_body = None
    if not constraints_ok:
        error_body = {
            "code": "constraint_violated",
            "message": "A preserved measurement changed by more than its tolerance",
            "details": {"checks": preserved["checks"]},
        }
    elif not geometry_ok:
        error_body = validation.get("error") or {
            "code": "target_not_met",
            "message": "The rebuilt socket missed a geometric check",
        }
    return {
        "ok": ok,
        "error": error_body,
        "clinical_use": False,
        "candidate_id": candidate_id,
        "base_socket_id": profile["socket_model_id"],
        "reference_limb_model_id": profile.get("reference_limb_model_id"),
        "operation": operation,
        "requested_target": requested,
        "requested_target_units": "mm",
        "measured_from": "reimported_step",
        "changes": _changes(before, after),
        "preserved": preserved,
        "validation": {
            "passed": validation.get("passed"),
            "error": validation.get("error"),
            "disclaimer": validation.get("disclaimer"),
        },
        "measurements": validation.get("measurements"),
        "files": {"step": str(step_path), "profile": str(json_path)},
    }
