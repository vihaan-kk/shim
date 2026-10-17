"""Computational checks for one limb solid and one socket solid.

A passing geometric status means the configured CAD checks succeeded. It does
not mean the socket fits, is comfortable, or is safe to load. A stale design
reference is reported on its own and does not by itself fail the geometry.
"""

from __future__ import annotations

from typing import Any

from tools.cad.align_limb_socket import prepare_aligned_pair
from tools.cad.compare_limb_socket import compare_prepared
from tools.cad.generate_limb import REFERENCE_STEP, load_profile
from tools.cad.measure_limb import is_valid, load_step_shape, signed_volume_mm3, solid_count
from tools.cad.modify_limb import value_within_tolerance
from tools.cad.validate_limb import validate_limb
from tools.cad.validate_socket import validate_socket

_DEFAULT_SECTIONS = ("q25", "q50", "q75")
_DISCLAIMER = (
    "These checks compare synthetic CAD solids. "
    "They do not establish clinical fit, comfort, load distribution, or prosthetic safety."
)


def _check(
    name: str,
    category: str,
    status: str,
    detail: str,
    *,
    measured: Any = None,
    tolerance: Any = None,
) -> dict:
    return {
        "name": name,
        "category": category,
        "status": status,
        "detail": detail,
        "measured": measured,
        "tolerance": tolerance,
    }


def _rollup(checks: list[dict]) -> str:
    statuses = [item["status"] for item in checks]
    if any(status == "FAIL" for status in statuses):
        return "FAIL"
    if any(status == "INDETERMINATE" for status in statuses):
        return "INDETERMINATE"
    return "PASS"


def _failed_names(validation: dict) -> list[str]:
    names = []
    categories = validation.get("categories")
    if isinstance(categories, dict):
        for category in categories.values():
            for item in category.get("checks", []):
                if not item.get("passed"):
                    names.append(item.get("name", "check"))
        return names
    for item in validation.get("checks", []):
        if not item.get("passed"):
            names.append(item.get("name", "check"))
    return names


def _design_profile(socket_profile: dict, evaluated_profile: dict) -> tuple[dict | None, str]:
    same_id = socket_profile.get("reference_limb_model_id") == evaluated_profile.get("model_id")
    same_version = socket_profile.get("reference_limb_version") == evaluated_profile.get("model_version")
    if same_id and same_version:
        return evaluated_profile, "evaluated_limb"
    try:
        standard = load_profile()
    except (OSError, ValueError):
        return None, "unavailable"
    if (
        socket_profile.get("reference_limb_model_id") == standard.get("model_id")
        and socket_profile.get("reference_limb_version") == standard.get("model_version")
    ):
        return standard, "standard_limb_file"
    return None, "unavailable"


def _reference_hash_status(
    socket_profile: dict,
    evaluated_profile: dict,
    evaluated_hash: str | None,
    design_kind: str,
) -> str:
    recorded = socket_profile.get("reference_limb_geometry_hash")
    if not isinstance(recorded, str) or len(recorded) != 64:
        return "hash_not_recorded"
    same = (
        socket_profile.get("reference_limb_model_id") == evaluated_profile.get("model_id")
        and socket_profile.get("reference_limb_version") == evaluated_profile.get("model_version")
    )
    if same:
        if not evaluated_hash:
            return "hash_not_recorded"
        return "current" if evaluated_hash == recorded else "hash_mismatch"
    if design_kind == "standard_limb_file" and REFERENCE_STEP.is_file():
        from tools.cad.validate_socket import _cached_limb_hash

        actual = _cached_limb_hash(load_profile())
        if actual != recorded:
            return "hash_mismatch"
        return "stale_reference"
    return "stale_reference"


def _model_checks(prepared: dict) -> tuple[list[dict], dict | None]:
    loaded = prepared["_loaded"]
    checks: list[dict] = []
    limb_shape = loaded["limb_shape"]
    socket_shape = loaded["socket_shape"]
    limb_profile = loaded["limb_profile"]
    socket_profile = loaded["socket_profile"]

    limb_report = validate_limb(limb_shape, limb_profile)
    limb_failed = _failed_names(limb_report)
    checks.append(
        _check(
            "limb_model",
            "individual_model",
            "PASS" if limb_report.get("passed") else "FAIL",
            "Limb solid matches its profile" if limb_report.get("passed") else f"Failed: {limb_failed}",
            measured=limb_report.get("signed_volume_mm3"),
        )
    )
    checks.append(_reimport_check("limb_reimport", loaded["limb_step"], limb_shape))
    checks.append(
        _check(
            "limb_units",
            "individual_model",
            "PASS" if limb_profile.get("units") == "mm" else "FAIL",
            f"units {limb_profile.get('units')!r}",
        )
    )

    design_profile, design_kind = _design_profile(socket_profile, limb_profile)
    socket_report = None
    if design_profile is None:
        valid = is_valid(socket_shape)
        solids = solid_count(socket_shape)
        volume = signed_volume_mm3(socket_shape)
        cad_ok = valid and solids == 1 and volume > 0
        checks.append(
            _check(
                "socket_model",
                "individual_model",
                "PASS" if cad_ok else "FAIL",
                f"valid {valid}, solids {solids}, volume {volume:.3f} mm3. "
                "Dimension checks need the design-reference limb profile, which was not available.",
                measured=volume,
            )
        )
        checks.append(
            _check(
                "socket_dimensions",
                "individual_model",
                "INDETERMINATE",
                "The socket design-reference limb profile is not the evaluated limb and is not the standard limb file.",
            )
        )
    else:
        socket_report = validate_socket(socket_shape, socket_profile, design_profile)
        categories = socket_report.get("categories", {})
        geometry_names = ("cad_validity", "dimensions", "structure")
        geometry_ok = all(categories.get(name, {}).get("passed") for name in geometry_names)
        failed = [
            item["name"]
            for name in geometry_names
            for item in categories.get(name, {}).get("checks", [])
            if not item.get("passed")
        ]
        checks.append(
            _check(
                "socket_model",
                "individual_model",
                "PASS" if geometry_ok else "FAIL",
                "Socket solid matches its design profile"
                if geometry_ok
                else f"Failed: {failed}. The design-reference limb is {design_kind}.",
                measured=socket_report.get("measurements", {}).get("volume_mm3"),
            )
        )
    checks.append(_reimport_check("socket_reimport", loaded["socket_step"], socket_shape))
    checks.append(
        _check(
            "socket_units",
            "individual_model",
            "PASS" if socket_profile.get("units") == "mm" else "FAIL",
            f"units {socket_profile.get('units')!r}",
        )
    )
    return checks, socket_report


def _reimport_check(name: str, path, shape) -> dict:
    try:
        imported = load_step_shape(path)
        original = signed_volume_mm3(shape)
        again = signed_volume_mm3(imported)
        close = value_within_tolerance(again - original, max(1.0, abs(original) * 1e-4))
    except Exception as exc:
        return _check(name, "individual_model", "FAIL", str(exc))
    return _check(
        name,
        "individual_model",
        "PASS" if close else "FAIL",
        f"volume {original:.3f} mm3, reimported {again:.3f} mm3",
        measured=again,
        tolerance=max(1.0, abs(original) * 1e-4),
    )


def _alignment_checks(prepared: dict) -> list[dict]:
    transform = prepared.get("transformation") or {}
    preserved = bool(transform.get("intrinsic_geometry_preserved"))
    identity = bool(transform.get("identity"))
    mode = transform.get("mode")
    shared = mode == "shared_frame" and identity
    explicit = mode == "explicit" and transform.get("convention") == "active_matrix"
    ok = preserved and (shared or explicit)
    return [
        _check(
            "rigid_transform",
            "alignment",
            "PASS" if ok else "FAIL",
            (
                f"mode {mode}, identity {identity}, "
                f"volume {transform.get('volume_before_mm3')} -> {transform.get('volume_after_mm3')} mm3"
            ),
            measured=transform.get("rotation_matrix"),
            tolerance=transform.get("volume_tolerance_mm3"),
        ),
        _check(
            "shared_coordinate_frame",
            "alignment",
            "PASS" if ok else "FAIL",
            "Both solids are evaluated in the socket frame after the recorded rigid motion.",
        ),
    ]


def _geometry_checks(comparison: dict, constraints: dict) -> list[dict]:
    checks = []
    required = constraints.get("required_sections", list(_DEFAULT_SECTIONS))
    if not isinstance(required, list) or not all(isinstance(item, str) for item in required):
        return [
            _check(
                "required_sections",
                "geometric_relationship",
                "FAIL",
                "constraints.required_sections must be a list of section ids",
            )
        ]
    by_id = {section.get("id"): section for section in comparison.get("sections", [])}
    for section_id in required:
        section = by_id.get(section_id)
        if section is None:
            checks.append(
                _check(
                    f"section_{section_id}",
                    "geometric_relationship",
                    "INDETERMINATE",
                    "The comparison did not include this section",
                )
            )
            continue
        status = section.get("status")
        clearance = section.get("clearance", {}).get("status")
        if status == "measured" and clearance == "measured":
            state = "PASS"
            detail = (
                f"inner perimeter {section.get('socket_inner_perimeter_mm')} mm, "
                f"limb perimeter {section.get('limb_perimeter_mm')} mm, "
                f"min clearance {section.get('clearance', {}).get('minimum_mm')} mm"
            )
        elif status in {"ambiguous", "outer_only"} or clearance == "unsupported":
            state = "INDETERMINATE"
            detail = section.get("clearance", {}).get("reason") or status
        else:
            state = "FAIL"
            detail = f"section status {status}"
        checks.append(
            _check(
                f"section_{section_id}",
                "geometric_relationship",
                state,
                detail,
                measured=None if not section.get("clearance") else section["clearance"].get("minimum_mm"),
            )
        )

    floor = constraints.get("min_clearance_mm")
    if floor is not None:
        if isinstance(floor, bool) or not isinstance(floor, (int, float)):
            checks.append(
                _check(
                    "clearance_threshold",
                    "geometric_relationship",
                    "FAIL",
                    "constraints.min_clearance_mm must be a number",
                )
            )
        else:
            measured_values = []
            blocked = False
            for section_id in required:
                section = by_id.get(section_id) or {}
                clearance = (section.get("clearance") or {}).get("minimum_mm")
                if clearance is None:
                    blocked = True
                else:
                    measured_values.append(clearance)
            if blocked or not measured_values:
                checks.append(
                    _check(
                        "clearance_threshold",
                        "geometric_relationship",
                        "INDETERMINATE",
                        "A requested clearance floor cannot be applied because a required section has no clearance",
                        tolerance=floor,
                    )
                )
            else:
                lowest = min(measured_values)
                checks.append(
                    _check(
                        "clearance_threshold",
                        "geometric_relationship",
                        "PASS" if lowest + 1e-9 >= float(floor) else "FAIL",
                        f"lowest required-section clearance {lowest} mm, configured floor {floor} mm",
                        measured=lowest,
                        tolerance=floor,
                    )
                )

    intersection = comparison.get("material_intersection") or {}
    cap = constraints.get("max_intersection_volume_mm3")
    if intersection.get("status") != "PASS":
        checks.append(
            _check(
                "material_intersection",
                "geometric_relationship",
                "INDETERMINATE",
                intersection.get("error") or "The Boolean common did not return a volume",
                tolerance=cap,
            )
        )
    elif cap is None:
        intersects = bool(intersection.get("intersects"))
        checks.append(
            _check(
                "material_intersection",
                "geometric_relationship",
                "WARNING" if intersects else "PASS",
                (
                    f"Intersection volume {intersection.get('volume_mm3')} mm3. "
                    "No maximum was configured, so the volume is reported and does not fail the pair."
                ),
                measured=intersection.get("volume_mm3"),
                tolerance=intersection.get("tolerance_mm3"),
            )
        )
    elif isinstance(cap, bool) or not isinstance(cap, (int, float)):
        checks.append(
            _check(
                "material_intersection",
                "geometric_relationship",
                "FAIL",
                "constraints.max_intersection_volume_mm3 must be a number",
            )
        )
    else:
        volume = float(intersection["volume_mm3"])
        checks.append(
            _check(
                "material_intersection",
                "geometric_relationship",
                "PASS" if volume <= float(cap) + 1e-9 else "FAIL",
                f"intersection volume {volume} mm3, configured maximum {cap} mm3",
                measured=volume,
                tolerance=cap,
            )
        )
    return checks


def _version_checks(prepared: dict, comparison: dict, hash_status: str) -> list[dict]:
    relationship = comparison.get("relationship") or {}
    loaded = prepared["_loaded"]
    checks = []
    ids = [
        relationship.get("limb_model_id"),
        relationship.get("limb_version"),
        relationship.get("socket_model_id"),
        relationship.get("socket_version"),
    ]
    ids_ok = all(isinstance(item, str) and bool(item) for item in ids)
    checks.append(
        _check(
            "model_ids",
            "version_integrity",
            "PASS" if ids_ok else "FAIL",
            f"limb {ids[0]} {ids[1]}, socket {ids[2]} {ids[3]}",
        )
    )
    missing = [
        str(path)
        for path in (loaded["limb_step"], loaded["socket_step"])
        if not path.is_file()
    ]
    checks.append(
        _check(
            "geometry_files",
            "version_integrity",
            "FAIL" if missing else "PASS",
            "Both STEP files exist" if not missing else f"Missing: {missing}",
        )
    )
    design_id = relationship.get("socket_reference_limb_model_id")
    design_version = relationship.get("socket_reference_limb_version")
    checks.append(
        _check(
            "design_reference_identified",
            "version_integrity",
            "PASS" if isinstance(design_id, str) and design_id and isinstance(design_version, str) and design_version else "FAIL",
            f"socket design reference {design_id} {design_version}",
        )
    )
    if hash_status == "current":
        state, detail = "PASS", "The evaluated limb is the socket's design reference and the geometry hash matches."
    elif hash_status == "stale_reference":
        state = "WARNING"
        detail = (
            f"The socket was designed against {design_id} {design_version}. "
            f"This comparison evaluates {relationship.get('limb_model_id')} {relationship.get('limb_version')}."
        )
    elif hash_status == "hash_mismatch":
        state = "FAIL"
        detail = "The recorded limb geometry hash does not match the limb file for that reference."
    elif hash_status == "hash_not_recorded":
        state = "WARNING"
        detail = "The socket profile has no reference_limb_geometry_hash."
    else:
        state, detail = "INDETERMINATE", hash_status
    checks.append(
        _check(
            "design_reference_consistency",
            "version_integrity",
            state,
            detail,
            measured={
                "evaluated_limb_geometry_hash": relationship.get("limb_geometry_hash"),
                "recorded_limb_geometry_hash": relationship.get("recorded_limb_geometry_hash"),
            },
        )
    )
    return checks


def validate_pair(request: dict) -> dict:
    """Run model, alignment, geometry, and version checks for one pair.

    ``constraints`` may set ``max_intersection_volume_mm3``, ``min_clearance_mm``,
    and ``required_sections``. Omitted thresholds are not invented.

    ``overall_status`` rolls up model, alignment, and geometric checks.
    Version findings stay in ``version_status`` and ``reference_status``.
    A stale design reference is a warning there, including when the geometry passes.
    """
    if not isinstance(request, dict):
        return {
            "ok": False,
            "overall_status": "FAIL",
            "clinical_use": False,
            "error": {"code": "invalid_value", "message": "The validation request must be an object"},
        }
    constraints = request.get("constraints") or {}
    if not isinstance(constraints, dict):
        return {
            "ok": False,
            "overall_status": "FAIL",
            "clinical_use": False,
            "error": {"code": "invalid_value", "message": "constraints must be an object"},
        }
    prepared = prepare_aligned_pair(request)
    if not prepared.get("ok"):
        error = prepared.get("error") or {}
        return {
            "ok": False,
            "overall_status": "FAIL",
            "geometry_status": "FAIL",
            "version_status": "INDETERMINATE",
            "reference_status": "missing" if error.get("code") in {"missing_file", "unknown_model"} else "not_evaluated",
            "clinical_use": False,
            "disclaimer": _DISCLAIMER,
            "error": error,
            "checks": [
                _check(
                    "pair_loaded",
                    "individual_model",
                    "FAIL",
                    error.get("message", "The pair could not be loaded"),
                )
            ],
            "warnings": [],
            "errors": [error],
        }

    comparison = compare_prepared(prepared, request)
    if not comparison.get("ok"):
        return {
            "ok": False,
            "overall_status": "INDETERMINATE",
            "geometry_status": "INDETERMINATE",
            "version_status": "INDETERMINATE",
            "reference_status": "not_evaluated",
            "clinical_use": False,
            "disclaimer": _DISCLAIMER,
            "error": comparison.get("error"),
            "checks": [
                _check(
                    "comparison",
                    "geometric_relationship",
                    "INDETERMINATE",
                    (comparison.get("error") or {}).get("message", "Comparison failed"),
                )
            ],
            "warnings": [],
            "errors": [comparison.get("error")],
            "comparison": comparison,
        }

    design_profile, design_kind = _design_profile(
        prepared["_loaded"]["socket_profile"],
        prepared["_loaded"]["limb_profile"],
    )
    hash_status = _reference_hash_status(
        prepared["_loaded"]["socket_profile"],
        prepared["_loaded"]["limb_profile"],
        (comparison.get("relationship") or {}).get("limb_geometry_hash"),
        design_kind if design_profile is not None else "unavailable",
    )
    checks = []
    checks.extend(_model_checks(prepared)[0])
    checks.extend(_alignment_checks(prepared))
    checks.extend(_geometry_checks(comparison, constraints))
    checks.extend(_version_checks(prepared, comparison, hash_status))

    geometry = [item for item in checks if item["category"] != "version_integrity"]
    version = [item for item in checks if item["category"] == "version_integrity"]
    # A warning does not fail the rollup. FAIL and INDETERMINATE do.
    geometry_status = _rollup([item for item in geometry if item["status"] != "WARNING"])
    version_status = _rollup([item for item in version if item["status"] != "WARNING"])
    if any(item["status"] == "WARNING" for item in version) and version_status == "PASS":
        version_status = "WARNING"
    return {
        "ok": True,
        "overall_status": geometry_status,
        "geometry_status": geometry_status,
        "version_status": version_status,
        "reference_status": hash_status,
        "clinical_use": False,
        "disclaimer": _DISCLAIMER,
        "error": None,
        "constraints": constraints,
        "checks": checks,
        "warnings": [item for item in checks if item["status"] == "WARNING"],
        "errors": [item for item in checks if item["status"] == "FAIL"],
        "indeterminate": [item for item in checks if item["status"] == "INDETERMINATE"],
        "comparison": comparison,
        "note": (
            "validate_socket hashes the standard limb STEP. "
            "This pair check hashes the design-reference limb that the socket names."
        ),
    }
