"""Checks for the synthetic limb solid, including a STEP round trip.

``passed`` is true only when every check below succeeds on the built solid
and again on the solid read back from STEP. A failed check stays in the report.
"""

from __future__ import annotations

import json
from pathlib import Path

import cadquery as cq

from tools.cad.generate_limb import (
    REFERENCE_REPORT,
    REFERENCE_STEP,
    REFERENCE_STL,
    derived_section_axes,
    export_solid,
    generate_limb,
    load_profile,
    parameters_from_profile,
    updated_profile,
)
from tools.cad.measure_limb import (
    bounding_box_mm,
    is_valid,
    material_z_extent_mm,
    measure_sections,
    section_circumference,
    signed_volume_mm3,
    solid_count,
)


def _round(value: float, digits: int = 6) -> float:
    return round(float(value), digits)


def _check(name: str, passed: bool, detail: str) -> dict:
    return {"name": name, "passed": bool(passed), "detail": detail}


def _section_checks(measurements: list[dict], tolerance_mm: float) -> list[dict]:
    checks = []
    for row in measurements:
        ok = abs(row["error_mm"]) <= tolerance_mm and row["edge_count"] == 1
        checks.append(
            _check(
                f"circumference_{row['id']}",
                ok,
                (
                    f"z={row['z_mm']} mm, measured {_round(row['measured_circumference_mm'])} mm, "
                    f"target {_round(row['target_circumference_mm'])} mm, "
                    f"error {_round(row['error_mm'])} mm, edges {row['edge_count']}"
                ),
            )
        )
    return checks


def geometric_checks(shape, profile: dict) -> dict:
    """Validate one in-memory solid against the profile. Does not export."""
    parameters = parameters_from_profile(profile)
    box = bounding_box_mm(shape)
    extent = material_z_extent_mm(shape, 0.0, parameters.cap_tip_z_mm)
    measurements = measure_sections(shape, profile)
    volume = signed_volume_mm3(shape)
    valid = is_valid(shape)
    count = solid_count(shape)
    length_error = extent["length_mm"] - parameters.total_length_mm
    zmin_error = extent["zmin_mm"] - 0.0
    zmax_error = extent["zmax_mm"] - parameters.cap_tip_z_mm
    length_tol = parameters.length_tolerance_mm

    near_tip, near_tip_edges = section_circumference(shape, parameters.cap_tip_z_mm - 0.5)
    beyond_tip, beyond_tip_edges = section_circumference(shape, parameters.cap_tip_z_mm + 1.0)
    distal_closed = (
        valid
        and count == 1
        and volume > 0
        and near_tip_edges == 1
        and near_tip > 1.0
        and beyond_tip_edges == 0
    )

    checks = [
        _check("valid_solid", valid, "BRepCheck_Analyzer.IsValid"),
        _check("one_solid", count == 1, f"solid count {count}"),
        _check("positive_volume", volume > 0, f"signed volume {_round(volume, 3)} mm^3"),
        _check(
            "longitudinal_extent",
            abs(length_error) <= length_tol and abs(zmin_error) <= length_tol and abs(zmax_error) <= length_tol,
            (
                f"cutting planes from {_round(extent['zmin_mm'])} to {_round(extent['zmax_mm'])} mm, "
                f"length {_round(extent['length_mm'])} mm, target {parameters.total_length_mm} mm"
            ),
        ),
        _check(
            "distal_closed",
            distal_closed,
            (
                f"section at z={parameters.cap_tip_z_mm - 0.5} mm is {_round(near_tip)} mm "
                f"({near_tip_edges} edges); section past the tip has {beyond_tip_edges} edges"
            ),
        ),
    ]
    checks.extend(_section_checks(measurements, parameters.circumference_tolerance_mm))
    return {
        "passed": all(item["passed"] for item in checks),
        "checks": checks,
        "material_extent_mm": {key: _round(value) for key, value in extent.items()},
        "kernel_bounding_box_mm": {key: _round(value) for key, value in box.items()},
        "signed_volume_mm3": _round(volume, 3),
        "measurements": [
            {
                **row,
                "measured_circumference_mm": _round(row["measured_circumference_mm"]),
                "error_mm": _round(row["error_mm"]),
            }
            for row in measurements
        ],
    }


def _stl_triangle_count(path: Path) -> int:
    data = path.read_bytes()
    if len(data) < 84:
        return 0
    if data[:5].lower() == b"solid" and b"facet" in data[:1000]:
        return data.count(b"facet normal")
    import struct

    count = struct.unpack_from("<I", data, 80)[0]
    expected = 84 + count * 50
    if expected != len(data):
        return 0
    return count


def validate_exports(shape, profile: dict, step_path: Path, stl_path: Path) -> dict:
    """Reimport STEP and repeat the geometric checks. Also check that the STL is a mesh."""
    imported = cq.importers.importStep(str(step_path)).val()
    reimport = geometric_checks(imported, profile)
    triangles = _stl_triangle_count(Path(stl_path))
    stl_check = _check(
        "stl_mesh",
        Path(stl_path).stat().st_size > 84 and triangles > 0,
        f"{triangles} triangles, {Path(stl_path).stat().st_size} bytes",
    )
    reimport_passed = reimport["passed"] and stl_check["passed"]
    return {
        "passed": reimport_passed,
        "step_reimport": reimport,
        "stl": stl_check,
    }


def full_report(shape, profile: dict, step_path: Path, stl_path: Path) -> dict:
    parameters = parameters_from_profile(profile)
    built = geometric_checks(shape, profile)
    exported = validate_exports(shape, profile, step_path, stl_path)
    passed = built["passed"] and exported["passed"]
    return {
        "model_id": parameters.model_id,
        "model_version": parameters.model_version,
        "clinical_use": False,
        "passed": passed,
        "tolerances_mm": {
            "circumference": parameters.circumference_tolerance_mm,
            "length": parameters.length_tolerance_mm,
            "circumference_rationale": profile["tolerances"]["circumference_rationale"],
            "length_rationale": profile["tolerances"]["length_rationale"],
        },
        "derived_semi_axes": derived_section_axes(parameters),
        "built_solid": built,
        "exports": exported,
        "files": {"step": str(step_path), "stl": str(stl_path)},
        "statement": (
            "Synthetic demonstration solid. Measurements below are CAD section lengths, "
            "not anatomical or clinical measurements."
        ),
    }


def validate_limb(shape, profile: dict) -> dict:
    """Validate one solid against a profile.

    A broken solid or a profile the builder rejects comes back as a failed
    report with a message, rather than an uncaught exception.
    """
    try:
        return geometric_checks(shape, profile)
    except (RuntimeError, ValueError, TypeError) as exc:
        return {
            "passed": False,
            "checks": [{"name": "geometry", "passed": False, "detail": str(exc)}],
            "measurements": [],
            "error": {"code": "invalid_geometry", "message": str(exc)},
        }


def validate_and_write_reference() -> dict:
    """Rebuild the reference solid from the JSON profile and write the report."""
    profile = load_profile()
    shape = generate_limb(parameters_from_profile(profile))
    export_solid(shape, REFERENCE_STEP, REFERENCE_STL, overwrite_reference=True)
    report = full_report(shape, profile, REFERENCE_STEP, REFERENCE_STL)
    REFERENCE_REPORT.parent.mkdir(parents=True, exist_ok=True)
    REFERENCE_REPORT.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"passed": report["passed"], "report": str(REFERENCE_REPORT)}, indent=2))
    for row in report["built_solid"]["measurements"]:
        print(
            f"{row['id']}: measured {row['measured_circumference_mm']} mm, "
            f"error {row['error_mm']} mm"
        )
    return report


def revise_section(
    profile: dict,
    section_id: str,
    output_dir: Path,
    *,
    scale: float | None = None,
    circumference_mm: float | None = None,
) -> dict:
    """Change one target, rebuild, validate, and write a new version.

    The reference STEP and STL are not overwritten. Proximal circumference and
    total length are reported against the original profile so a caller can see
    whether those constraints held.
    """
    output_dir = Path(output_dir)
    revised = updated_profile(
        profile,
        section_id,
        scale=scale,
        circumference_mm=circumference_mm,
    )
    shape = generate_limb(parameters_from_profile(revised))
    step_path = output_dir / f"{revised['model_id']}-{section_id}.step"
    stl_path = output_dir / f"{revised['model_id']}-{section_id}.stl"
    export_solid(shape, step_path, stl_path, overwrite_reference=False)
    report = full_report(shape, revised, step_path, stl_path)

    original_parameters = parameters_from_profile(profile)
    built = report["built_solid"]
    by_id = {row["id"]: row for row in built["measurements"]}
    proximal = by_id["proximal"]
    edited = by_id[section_id]
    original_target = next(spec.circumference_mm for spec in original_parameters.sections if spec.id == section_id)
    preserved = {
        "proximal_within_tolerance": abs(proximal["error_mm"]) <= original_parameters.circumference_tolerance_mm,
        "length_within_tolerance": next(
            item["passed"] for item in built["checks"] if item["name"] == "longitudinal_extent"
        ),
        "edited_section_id": section_id,
        "original_circumference_mm": original_target,
        "revised_target_circumference_mm": edited["target_circumference_mm"],
        "revised_measured_circumference_mm": edited["measured_circumference_mm"],
    }
    report_path = output_dir / f"{revised['model_id']}-{section_id}_validation.json"
    report["files"]["validation"] = str(report_path)
    report["preserved_constraints"] = preserved
    report_path.write_text(json.dumps(report, indent=2) + "\n")
    return report
