"""Parametric hollow socket around the synthetic transtibial limb.

The limb profile supplies the taper and the shared AP/ML ratio. This module
builds a different solid: a wall with an open proximal brim and a closed
distal cup. It does not scale the limb and it does not boolean-cut the limb.

Every thickness, flare, and depth is a computational geometry parameter.
Nothing here is a fit, a liner gap, or a clinical recommendation.
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
from dataclasses import dataclass
from pathlib import Path

import cadquery as cq
import numpy as np
from OCP.BRepBuilderAPI import (
    BRepBuilderAPI_GTransform,
    BRepBuilderAPI_MakeEdge,
    BRepBuilderAPI_MakeFace,
    BRepBuilderAPI_MakeWire,
)
from OCP.BRepClass3d import BRepClass3d_SolidClassifier
from OCP.BRepPrimAPI import BRepPrimAPI_MakeRevol
from OCP.GC import GC_MakeArcOfCircle
from OCP.GeomAPI import GeomAPI_PointsToBSpline
from OCP.TColgp import TColgp_Array1OfPnt
from OCP.TopAbs import TopAbs_IN, TopAbs_OUT
from OCP.gp import gp_Ax1, gp_Dir, gp_GTrsf, gp_Mat, gp_Pnt
from scipy.interpolate import PchipInterpolator

from tools.cad.generate_limb import (
    SOCKET_PROFILE_PATH,
    SOCKET_REPORT,
    SOCKET_STEP,
    SOCKET_STL,
    LimbParameters,
    _cap_edge,
    _ml_radius,
    _orient_edge,
    _signed_volume,
    ellipse_circumference,
    load_profile,
    parameters_from_profile,
)
from tools.cad.measure_limb import (
    is_valid,
    material_z_extent_mm,
    measure_shape,
    signed_volume_mm3,
    solid_count,
)


@dataclass(frozen=True)
class SocketSpec:
    """Numbers the builder uses. Derived fields are computed, not read back."""

    socket_model_id: str
    model_version: str
    limb: LimbParameters
    nominal_wall_thickness_mm: float
    socket_depth_mm: float
    inner_radial_clearance_mm: float
    brim_flare_mm: float
    brim_flare_length_mm: float
    distal_wall_thickness_mm: float
    minimum_wall_thickness_mm: float
    opening_plane_z_mm: float
    inner_tip_z_mm: float
    outer_tip_z_mm: float
    rim_radius_mm: float
    inner_offset_at: object
    wall_extra_at: object


def load_socket_profile(path: Path | None = None) -> dict:
    """Read a socket parameter file. The derived cache is not required."""
    profile_path = Path(path) if path is not None else SOCKET_PROFILE_PATH
    with profile_path.open() as handle:
        profile = json.load(handle)
    if not isinstance(profile, dict):
        raise ValueError("Socket profile must be a JSON object")
    return profile


def _stable_mm(value: float, digits: int) -> float:
    """Round a measurement and collapse negative zero.

    ``json.dumps`` writes ``-0.0`` and ``0.0`` as different text, so a cutting
    plane that lands on the opening from either side would otherwise change
    the geometry hash without changing the solid.
    """
    number = round(float(value), digits)
    if number == 0.0:
        return 0.0
    return number


def limb_geometry_hash(shape, limb_profile: dict) -> str:
    """Stable id for the limb solid.

    STEP text changes when OpenCascade rewrites entity ids or the timestamp,
    so the hash is taken from rounded measurements instead. Volume is rounded
    to 0.001 mm³. Station circumferences and the cutting-plane extent are
    rounded to 0.0001 mm. Negative zero is stored as zero.
    """
    measured = measure_shape(shape, limb_profile)
    extent = material_z_extent_mm(shape, 0.0, float(limb_profile["total_length_mm"]))
    payload = {
        "volume_mm3": _stable_mm(signed_volume_mm3(shape), 3),
        "sections": [
            [
                row["id"],
                _stable_mm(row["z_mm"], 4),
                _stable_mm(row["measured_circumference_mm"], 4),
            ]
            for row in measured["sections"]
        ],
        "zmin": _stable_mm(extent["zmin_mm"], 4),
        "zmax": _stable_mm(extent["zmax_mm"], 4),
    }
    raw = json.dumps(payload, sort_keys=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _number(value, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a number")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"{name} must be a finite number")
    return number


def _offset_function(limb: LimbParameters, values: dict) -> object:
    if not isinstance(values, dict):
        raise ValueError("Radius offsets must be an object keyed by section id")
    known = [spec.id for spec in limb.sections]
    unknown = sorted(set(values) - set(known))
    if unknown:
        raise ValueError(f"Unknown section ids {unknown}. Known sections: {known}")
    stations = [spec.z_mm for spec in limb.sections]
    samples = [_number(values.get(spec.id, 0.0), f"offset {spec.id}") for spec in limb.sections]
    if all(abs(sample) <= 1e-12 for sample in samples):
        return lambda _z: 0.0
    curve = PchipInterpolator(stations, samples)

    def at(z: float) -> float:
        return float(curve(float(z)))

    return at


def _require_identity(profile: dict) -> None:
    alignment = profile.get("alignment_transform")
    if not isinstance(alignment, dict) or alignment.get("type") != "identity":
        raise ValueError("Only an identity alignment transform is supported")
    translation = alignment.get("translation_mm", [0, 0, 0])
    if list(translation) != [0, 0, 0]:
        raise ValueError("Only an identity alignment transform is supported")


def compile_socket(limb_profile: dict, socket_profile: dict) -> SocketSpec:
    """Check both profiles and compute the derived cup, rim, and wall.

    ``derived`` in the socket file is ignored. The limb file is not modified.
    """
    if socket_profile.get("clinical_use") is not False:
        raise ValueError("clinical_use must be false")
    if socket_profile.get("units") != "mm" or limb_profile.get("units") != "mm":
        raise ValueError("units must be mm")
    if socket_profile.get("reference_limb_model_id") != limb_profile.get("model_id"):
        raise ValueError("Socket reference_limb_model_id does not match the limb profile")
    if socket_profile.get("reference_limb_version") != limb_profile.get("model_version"):
        raise ValueError("Socket reference_limb_version does not match the limb profile")
    frame = socket_profile.get("coordinate_frame", {})
    if frame.get("longitudinal_axis") != "Z" or frame.get("distal_direction") != "+Z":
        raise ValueError("The socket longitudinal axis is +Z")
    if frame.get("proximal_plane_z_mm") != 0:
        raise ValueError("The socket opening plane is z = 0")
    if frame.get("ml_axis") != "X" or frame.get("ap_axis") != "Y":
        raise ValueError("X is medial-lateral and Y is anterior-posterior")
    if socket_profile.get("geometry_generation_method") != "wall_profile_revolution_then_y_scale":
        raise ValueError("Unsupported socket construction method")
    _require_identity(socket_profile)

    limb = parameters_from_profile(limb_profile)
    wall = _number(socket_profile["nominal_wall_thickness_mm"], "nominal_wall_thickness_mm")
    depth = _number(socket_profile["socket_depth_mm"], "socket_depth_mm")
    clearance = _number(socket_profile["inner_radial_clearance_mm"], "inner_radial_clearance_mm")
    flare = _number(socket_profile["brim_flare_mm"], "brim_flare_mm")
    flare_length = _number(socket_profile["brim_flare_length_mm"], "brim_flare_length_mm")
    distal_wall = _number(socket_profile["distal_wall_thickness_mm"], "distal_wall_thickness_mm")
    minimum_wall = _number(socket_profile["minimum_wall_thickness_mm"], "minimum_wall_thickness_mm")
    if wall <= 0 or distal_wall <= 0 or minimum_wall <= 0:
        raise ValueError("Wall thickness must be positive")
    if wall < 0.4:
        raise ValueError("nominal_wall_thickness_mm must be at least 0.4 mm to form a rim")
    if clearance < 0:
        raise ValueError("inner_radial_clearance_mm cannot be negative")
    if flare < 0 or flare > 25:
        raise ValueError("brim_flare_mm must be from 0 to 25")
    if not 8 <= flare_length <= 30:
        raise ValueError("brim_flare_length_mm must be from 8 to 30 so the flare stays on the brim")
    if depth <= distal_wall:
        raise ValueError("socket_depth_mm must be longer than the distal wall")
    if depth > 300:
        raise ValueError("socket_depth_mm must be at most 300")

    opening = 0.0
    outer_tip = opening + depth
    inner_tip = outer_tip - distal_wall
    if inner_tip < limb.total_length_mm + 0.5:
        raise ValueError(
            "socket_depth_mm is too small. The inner cup would reach the limb tip. "
            f"Need inner tip >= {limb.total_length_mm + 0.5:.1f} mm; got {inner_tip:.3f} mm."
        )
    if inner_tip < limb.cap_start_z_mm + 3.0:
        raise ValueError("The distal cap is too short to close")

    inner_offset_at = _offset_function(limb, socket_profile.get("inner_radius_offset_mm", {}))
    wall_extra_at = _offset_function(limb, socket_profile.get("section_wall_extra_mm", {}))
    proximal_wall = wall + float(wall_extra_at(0.0))
    if proximal_wall < 0.4:
        raise ValueError("Wall thickness at the brim must be at least 0.4 mm")

    return SocketSpec(
        socket_model_id=str(socket_profile["socket_model_id"]),
        model_version=str(socket_profile["model_version"]),
        limb=limb,
        nominal_wall_thickness_mm=wall,
        socket_depth_mm=depth,
        inner_radial_clearance_mm=clearance,
        brim_flare_mm=flare,
        brim_flare_length_mm=flare_length,
        distal_wall_thickness_mm=distal_wall,
        minimum_wall_thickness_mm=minimum_wall,
        opening_plane_z_mm=opening,
        inner_tip_z_mm=inner_tip,
        outer_tip_z_mm=outer_tip,
        rim_radius_mm=proximal_wall / 2.0,
        inner_offset_at=inner_offset_at,
        wall_extra_at=wall_extra_at,
    )


def _flare(spec: SocketSpec, z_mm: float) -> float:
    length = spec.brim_flare_length_mm
    if z_mm <= 0:
        return spec.brim_flare_mm
    if z_mm >= length:
        return 0.0
    u = 1.0 - (z_mm / length)
    smooth = u * u * (3.0 - 2.0 * u)
    return spec.brim_flare_mm * smooth


def _wall_at(spec: SocketSpec, z_mm: float) -> float:
    return spec.nominal_wall_thickness_mm + float(spec.wall_extra_at(z_mm))


def inner_ml_radius(spec: SocketSpec, limb_radius, z_mm: float) -> float:
    """Medial-lateral inner semi-axis before the Y scale."""
    return (
        float(limb_radius(z_mm))
        + spec.inner_radial_clearance_mm
        + _flare(spec, z_mm)
        + float(spec.inner_offset_at(z_mm))
    )


def outer_ml_radius(spec: SocketSpec, limb_radius, z_mm: float) -> float:
    return inner_ml_radius(spec, limb_radius, z_mm) + _wall_at(spec, z_mm)


def _check_radius_profile(spec: SocketSpec, limb_radius) -> None:
    zs = np.linspace(0.0, spec.limb.cap_start_z_mm, 500)
    inner = np.array([inner_ml_radius(spec, limb_radius, float(z)) for z in zs])
    outer = np.array([outer_ml_radius(spec, limb_radius, float(z)) for z in zs])
    if np.any(inner <= 1.0):
        raise RuntimeError("Inner radius collapsed. Reduce the clearance offset or the section cut.")
    growth = np.diff(inner)
    if np.any(growth > 1e-6):
        index = int(np.argmax(growth))
        raise RuntimeError(
            "Inner ML radius increases toward the tip, between "
            f"z={zs[index]:.2f} and z={zs[index + 1]:.2f} mm "
            f"({inner[index]:.3f} to {inner[index + 1]:.3f}). "
            "The cavity would fold. Use a smaller section change."
        )
    if np.any(outer - inner < 0.4):
        raise RuntimeError("Local wall thickness dropped below 0.4 mm")
    outer_growth = np.diff(outer)
    if np.any(outer_growth > 1e-6):
        index = int(np.argmax(outer_growth))
        raise RuntimeError(
            "Outer ML radius increases toward the tip near "
            f"z={zs[index]:.2f} mm. Reduce the section wall extra."
        )


def _radius_samples(radius_at, z_start: float, z_end: float, step: float) -> list[tuple[float, float]]:
    direction = 1.0 if z_end > z_start else -1.0
    zs = [z_start]
    z = z_start
    while (z_end - z) * direction > 1e-9:
        nxt = z + direction * step
        if (z_end - nxt) * direction < 0:
            nxt = z_end
        zs.append(nxt)
        z = nxt
    ordered: list[float] = []
    for z in zs:
        rounded = round(float(z), 6)
        if not ordered or abs(ordered[-1] - rounded) > 1e-6:
            ordered.append(rounded)
    ordered[0] = float(z_start)
    ordered[-1] = float(z_end)
    return [(z, float(radius_at(z))) for z in ordered]


def _spline_edge(samples: list[tuple[float, float]]):
    points = TColgp_Array1OfPnt(1, len(samples))
    for index, (z, radius) in enumerate(samples, start=1):
        points.SetValue(index, gp_Pnt(radius, 0.0, z))
    approximated = GeomAPI_PointsToBSpline(points, 3, 8, Tol3D=1e-7)
    if not approximated.IsDone():
        raise RuntimeError("A socket wall curve could not be approximated within 1e-7 mm")
    return BRepBuilderAPI_MakeEdge(approximated.Curve()).Edge()


def _rim_edge(inner_radius: float, outer_radius: float, opening_z: float, rim_radius: float):
    mid = inner_radius + rim_radius
    arc = GC_MakeArcOfCircle(
        gp_Pnt(outer_radius, 0.0, opening_z),
        gp_Pnt(mid, 0.0, opening_z - rim_radius),
        gp_Pnt(inner_radius, 0.0, opening_z),
    )
    if not arc.IsDone():
        raise RuntimeError("The proximal rim arc could not be built")
    return BRepBuilderAPI_MakeEdge(arc.Value()).Edge()


def _wall_wire(spec: SocketSpec, limb_radius):
    step = spec.limb.sample_step_mm
    cap_z = spec.limb.cap_start_z_mm
    inner_cap_r = inner_ml_radius(spec, limb_radius, cap_z)
    outer_cap_r = outer_ml_radius(spec, limb_radius, cap_z)
    inner_open_r = inner_ml_radius(spec, limb_radius, spec.opening_plane_z_mm)
    outer_open_r = outer_ml_radius(spec, limb_radius, spec.opening_plane_z_mm)

    def inner_at(z: float) -> float:
        if abs(z - cap_z) <= 1e-6:
            return inner_cap_r
        if abs(z - spec.opening_plane_z_mm) <= 1e-6:
            return inner_open_r
        return inner_ml_radius(spec, limb_radius, z)

    def outer_at(z: float) -> float:
        if abs(z - cap_z) <= 1e-6:
            return outer_cap_r
        if abs(z - spec.opening_plane_z_mm) <= 1e-6:
            return outer_open_r
        return outer_ml_radius(spec, limb_radius, z)

    axis = BRepBuilderAPI_MakeEdge(
        gp_Pnt(0.0, 0.0, spec.inner_tip_z_mm),
        gp_Pnt(0.0, 0.0, spec.outer_tip_z_mm),
    ).Edge()
    outer_cap = _cap_edge(outer_cap_r, cap_z, spec.outer_tip_z_mm)
    outer_side = _spline_edge(_radius_samples(outer_at, cap_z, spec.opening_plane_z_mm, step))
    rim = _rim_edge(inner_open_r, outer_open_r, spec.opening_plane_z_mm, spec.rim_radius_mm)
    inner_side = _spline_edge(_radius_samples(inner_at, spec.opening_plane_z_mm, cap_z, step))
    inner_cap = _cap_edge(inner_cap_r, cap_z, spec.inner_tip_z_mm)

    cursor = gp_Pnt(0.0, 0.0, spec.inner_tip_z_mm)
    ordered = []
    for edge in (axis, outer_cap, outer_side, rim, inner_side, inner_cap):
        oriented, cursor = _orient_edge(edge, cursor)
        ordered.append(oriented)
    if cursor.Distance(gp_Pnt(0.0, 0.0, spec.inner_tip_z_mm)) > 1e-4:
        raise RuntimeError("The socket wall profile does not close")

    wire = BRepBuilderAPI_MakeWire()
    for edge in ordered:
        wire.Add(edge)
    if not wire.IsDone():
        raise RuntimeError(f"Socket wall wire failed: {wire.Error()}")
    return wire.Wire()


def _assert_hollow(shape, spec: SocketSpec) -> None:
    """Fail if the revolution filled the cup or left the distal end open."""
    classifier = BRepClass3d_SolidClassifier(shape)
    cavity_z = spec.limb.total_length_mm * 0.5
    classifier.Perform(gp_Pnt(0.0, 0.0, cavity_z), 1e-6)
    if classifier.State() != TopAbs_OUT:
        raise RuntimeError(
            "The socket cavity is solid material. The wall profile did not leave a hollow cup."
        )
    plug_z = (spec.inner_tip_z_mm + spec.outer_tip_z_mm) / 2.0
    classifier.Perform(gp_Pnt(0.0, 0.0, plug_z), 1e-6)
    if classifier.State() != TopAbs_IN:
        raise RuntimeError("The distal end is not closed by wall material.")
    wall_r = (
        inner_ml_radius(spec, _ml_radius(spec.limb), cavity_z)
        + outer_ml_radius(spec, _ml_radius(spec.limb), cavity_z)
    ) / 2.0
    classifier.Perform(gp_Pnt(wall_r, 0.0, cavity_z), 1e-6)
    if classifier.State() != TopAbs_IN:
        raise RuntimeError("A point inside the designed wall is not inside the solid.")


def generate_socket(limb_profile: dict, socket_profile: dict) -> cq.Shape:
    """Build one hollow socket solid. Does not write files or modify the limb."""
    spec = compile_socket(limb_profile, socket_profile)
    limb_radius = _ml_radius(spec.limb)
    _check_radius_profile(spec, limb_radius)
    wire = _wall_wire(spec, limb_radius)
    face = BRepBuilderAPI_MakeFace(wire)
    if not face.IsDone():
        raise RuntimeError("The socket wall profile did not make a face")
    revolved = BRepPrimAPI_MakeRevol(
        face.Face(),
        gp_Ax1(gp_Pnt(0.0, 0.0, 0.0), gp_Dir(0.0, 0.0, 1.0)),
        2.0 * math.pi,
    )
    if not revolved.IsDone():
        raise RuntimeError("Revolution of the socket wall failed")

    transform = gp_GTrsf()
    ratio = spec.limb.ap_over_ml
    transform.SetVectorialPart(gp_Mat(1.0, 0.0, 0.0, 0.0, ratio, 0.0, 0.0, 0.0, 1.0))
    scaled = BRepBuilderAPI_GTransform(revolved.Shape(), transform, True)
    if not scaled.IsDone():
        raise RuntimeError("Y scale of the revolved socket failed")
    shape = scaled.Shape()
    if _signed_volume(shape) < 0:
        shape = shape.Reversed()
    if not is_valid(shape) or solid_count(shape) != 1 or _signed_volume(shape) <= 0:
        raise RuntimeError("The socket solid is invalid, empty, or not a single solid")
    _assert_hollow(shape, spec)
    return cq.Shape.cast(shape)


def construction_targets(spec: SocketSpec) -> dict:
    """Ellipse targets implied by the parameters, before any STEP measurement."""
    limb_radius = _ml_radius(spec.limb)
    ratio = spec.limb.ap_over_ml
    rows = []
    for section in spec.limb.sections:
        z = section.z_mm
        inner_ml = inner_ml_radius(spec, limb_radius, z)
        outer_ml = outer_ml_radius(spec, limb_radius, z)
        inner_ap = inner_ml * ratio
        outer_ap = outer_ml * ratio
        rows.append(
            {
                "id": section.id,
                "z_mm": z,
                "role": "opening" if section.id == "proximal" else "cavity",
                "inner_ml_semi_mm": inner_ml,
                "inner_ap_semi_mm": inner_ap,
                "outer_ml_semi_mm": outer_ml,
                "outer_ap_semi_mm": outer_ap,
                "inner_circumference_mm": ellipse_circumference(inner_ap, inner_ml),
                "outer_circumference_mm": ellipse_circumference(outer_ap, outer_ml),
                "inner_area_mm2": math.pi * inner_ap * inner_ml,
                "outer_area_mm2": math.pi * outer_ap * outer_ml,
                "ml_wall_thickness_mm": outer_ml - inner_ml,
                "ap_wall_thickness_mm": outer_ap - inner_ap,
            }
        )
    opening = rows[0]
    return {
        "units": "mm",
        "socket_depth_mm": spec.socket_depth_mm,
        "opening_plane_z_mm": spec.opening_plane_z_mm,
        "inner_tip_z_mm": spec.inner_tip_z_mm,
        "outer_tip_z_mm": spec.outer_tip_z_mm,
        "rim_crest_z_mm": spec.opening_plane_z_mm - spec.rim_radius_mm,
        "rim_radius_mm": spec.rim_radius_mm,
        "opening_ml_diameter_mm": 2.0 * opening["inner_ml_semi_mm"],
        "opening_ap_diameter_mm": 2.0 * opening["inner_ap_semi_mm"],
        "distal_axial_wall_mm": spec.distal_wall_thickness_mm,
        "ap_over_ml": ratio,
        "stations": rows,
        "source": "constructed_ellipses",
    }


def derived_cache(spec: SocketSpec) -> dict:
    """Documentation cache. ``generate_socket`` does not read it."""
    targets = construction_targets(spec)
    return {
        "note": "Recomputed from the editable parameters and the limb. Do not edit this block.",
        "clinical_recommendation": False,
        "inner_tip_z_mm": spec.inner_tip_z_mm,
        "outer_tip_z_mm": spec.outer_tip_z_mm,
        "rim_radius_mm": spec.rim_radius_mm,
        "rim_crest_z_mm": targets["rim_crest_z_mm"],
        "opening_ml_diameter_mm": targets["opening_ml_diameter_mm"],
        "opening_ap_diameter_mm": targets["opening_ap_diameter_mm"],
        "ap_over_ml": spec.limb.ap_over_ml,
        "stations": targets["stations"],
    }


def with_derived(limb_profile: dict, socket_profile: dict) -> dict:
    """Return a copy whose ``derived`` block matches the editable parameters."""
    revised = copy.deepcopy(socket_profile)
    revised["derived"] = derived_cache(compile_socket(limb_profile, socket_profile))
    return revised


def _reject_socket_reference(path: Path, *, overwrite_reference: bool) -> None:
    if overwrite_reference:
        return
    resolved = path.resolve()
    protected = {
        SOCKET_STEP.resolve(),
        SOCKET_STL.resolve(),
        SOCKET_PROFILE_PATH.resolve(),
        SOCKET_REPORT.resolve(),
    }
    if resolved in protected:
        raise ValueError(f"Refusing to overwrite the reference socket at {path}")


def export_socket(
    shape: cq.Shape,
    step_path: Path,
    stl_path: Path | None = None,
    *,
    overwrite_reference: bool = False,
) -> None:
    """Write STEP and, when asked, STL. Reference limb and socket files stay put."""
    step_path = Path(step_path)
    _reject_socket_reference(step_path, overwrite_reference=overwrite_reference)
    step_path.parent.mkdir(parents=True, exist_ok=True)
    cq.exporters.export(shape, str(step_path), exportType="STEP")
    if stl_path is None:
        return
    stl_path = Path(stl_path)
    _reject_socket_reference(stl_path, overwrite_reference=overwrite_reference)
    cq.exporters.export(
        shape,
        str(stl_path),
        exportType="STL",
        tolerance=0.15,
        angularTolerance=0.2,
    )


def write_standard_socket(*, write_stl: bool = True) -> dict:
    """Rebuild the reference socket from the two profile files."""
    from tools.cad.generate_limb import REFERENCE_STEP
    from tools.cad.measure_limb import load_step_shape
    from tools.cad.validate_socket import validate_socket

    limb_profile = load_profile()
    limb_shape = load_step_shape(REFERENCE_STEP)
    socket_profile = copy.deepcopy(load_socket_profile())
    socket_profile["reference_limb_geometry_hash"] = limb_geometry_hash(limb_shape, limb_profile)
    shape = generate_socket(limb_profile, socket_profile)
    profile = with_derived(limb_profile, socket_profile)
    export_socket(
        shape,
        SOCKET_STEP,
        SOCKET_STL if write_stl else None,
        overwrite_reference=True,
    )
    imported = load_step_shape(SOCKET_STEP)
    report = validate_socket(
        imported,
        profile,
        limb_profile,
        step_path=SOCKET_STEP,
        stl_path=SOCKET_STL if write_stl else None,
    )
    SOCKET_REPORT.write_text(json.dumps(report, indent=2) + "\n")
    SOCKET_PROFILE_PATH.write_text(json.dumps(profile, indent=2) + "\n")
    if not report.get("passed"):
        raise RuntimeError(f"Reference socket validation failed. See {SOCKET_REPORT}")
    return report


if __name__ == "__main__":
    written = write_standard_socket()
    print(json.dumps({"passed": written["passed"], "report": str(SOCKET_REPORT)}, indent=2))
