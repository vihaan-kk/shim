"""Parametric solid for one synthetic transtibial residual limb.

The JSON profile is the source of the numbers. ``generate_limb`` rebuilds the
solid from those numbers. A later Nemotron tool can call these functions.
Nothing here talks to a model, and nothing here is a medical device.

Construction: revolve the medial-lateral radius profile around Z, then scale
Y by the AP/ML ratio. A ThruSections loft that ended on a tip vertex produced
a valid solid whose bounding box left the station planes, so that loft is not
used. Revolution keeps every station on its ellipse and closes a rounded tip.
"""

from __future__ import annotations

import copy
import json
import math
from dataclasses import dataclass
from pathlib import Path

import cadquery as cq
import numpy as np
from OCP.BRepAdaptor import BRepAdaptor_Curve
from OCP.BRepBuilderAPI import (
    BRepBuilderAPI_GTransform,
    BRepBuilderAPI_MakeEdge,
    BRepBuilderAPI_MakeFace,
    BRepBuilderAPI_MakeWire,
)
from OCP.BRepGProp import BRepGProp
from OCP.BRepPrimAPI import BRepPrimAPI_MakeRevol
from OCP.GC import GC_MakeArcOfEllipse
from OCP.GProp import GProp_GProps
from OCP.GeomAPI import GeomAPI_PointsToBSpline
from OCP.TopoDS import TopoDS
from OCP.TColgp import TColgp_Array1OfPnt
from OCP.gp import gp_Ax1, gp_Ax2, gp_Dir, gp_Elips, gp_GTrsf, gp_Mat, gp_Pnt
from scipy.integrate import quad
from scipy.interpolate import PchipInterpolator

REPO_ROOT = Path(__file__).resolve().parents[2]
PROFILE_PATH = REPO_ROOT / "data" / "profiles" / "standard_limb.json"
REFERENCE_DIR = REPO_ROOT / "data" / "reference"
REFERENCE_STEP = REFERENCE_DIR / "standardized_limb.step"
REFERENCE_STL = REFERENCE_DIR / "standardized_limb.stl"
REFERENCE_REPORT = REFERENCE_DIR / "standardized_limb_validation.json"
SOCKET_PROFILE_PATH = REPO_ROOT / "data" / "profiles" / "standard_socket.json"
SOCKET_STEP = REFERENCE_DIR / "standardized_socket.step"
SOCKET_STL = REFERENCE_DIR / "standardized_socket.stl"
SOCKET_REPORT = REFERENCE_DIR / "standardized_socket_report.json"

# Future tool names, not registered with the agent yet:
# inspect_cad, measure_section, update_measurement_profile, propose_modification,
# modify_cad, validate_cad, compare_versions, restore_version.


@dataclass(frozen=True)
class SectionSpec:
    id: str
    z_mm: float
    circumference_mm: float
    ap_over_ml: float


@dataclass(frozen=True)
class LimbParameters:
    """Numerical definition of the solid. Built only from a profile dict."""

    model_id: str
    model_version: str
    units: str
    total_length_mm: float
    sections: tuple[SectionSpec, ...]
    cap_start_z_mm: float
    cap_tip_z_mm: float
    cap_length_mm: float
    sample_step_mm: float
    cap_tangent_blend_mm: float
    circumference_tolerance_mm: float
    length_tolerance_mm: float

    @property
    def ap_over_ml(self) -> float:
        return self.sections[0].ap_over_ml


def load_profile(path: Path | None = None) -> dict:
    """Read the authoritative parameter file."""
    profile_path = Path(path) if path is not None else PROFILE_PATH
    with profile_path.open() as handle:
        profile = json.load(handle)
    if not isinstance(profile, dict):
        raise ValueError("Limb profile must be a JSON object")
    return profile


def ellipse_circumference(ap_semi_mm: float, ml_semi_mm: float) -> float:
    """Perimeter of an ellipse from the complete elliptic integral.

    C = 4 ∫_0^(π/2) sqrt((ap sin θ)^2 + (ml cos θ)^2) dθ.
    The arguments are semi-axes, not diameters. A circle is the special case
    ap == ml, and then C = 2 π r.
    """
    ap = float(ap_semi_mm)
    ml = float(ml_semi_mm)
    if ap <= 0 or ml <= 0:
        raise ValueError("Ellipse semi-axes must be positive")
    value, _error = quad(
        lambda theta: math.sqrt((ap * math.sin(theta)) ** 2 + (ml * math.cos(theta)) ** 2),
        0.0,
        math.pi / 2,
        epsabs=1e-12,
    )
    return 4.0 * value


def ramanujan_circumference(ap_semi_mm: float, ml_semi_mm: float) -> float:
    """Ramanujan's second approximation, used only as a cross-check."""
    ap = float(ap_semi_mm)
    ml = float(ml_semi_mm)
    total = ap + ml
    h = ((ap - ml) / total) ** 2
    return math.pi * total * (1.0 + (3.0 * h) / (10.0 + math.sqrt(4.0 - 3.0 * h)))


def semi_axes_for_circumference(circumference_mm: float, ap_over_ml: float) -> tuple[float, float]:
    """Return (ap_semi, ml_semi) whose elliptic perimeter equals the target.

    The perimeter scales with the size of the ellipse, so one integral at
    AP/ML = ap_over_ml and ML = 1 determines both semi-axes.
    """
    if circumference_mm <= 0:
        raise ValueError("Circumference must be positive")
    if ap_over_ml <= 0:
        raise ValueError("ap_over_ml must be positive")
    unit_perimeter = ellipse_circumference(ap_over_ml, 1.0)
    ml_semi = circumference_mm / unit_perimeter
    ap_semi = ap_over_ml * ml_semi
    recovered = ellipse_circumference(ap_semi, ml_semi)
    if abs(recovered - circumference_mm) > 1e-6:
        raise RuntimeError(
            f"Ellipse sizing missed {circumference_mm} mm by {recovered - circumference_mm} mm"
        )
    return ap_semi, ml_semi


def parameters_from_profile(profile: dict) -> LimbParameters:
    """Check the profile and return the numbers the builder uses."""
    frame = profile["coordinate_frame"]
    if profile["units"] != "mm":
        raise ValueError("units must be mm")
    if frame["longitudinal_axis"] != "Z" or frame["distal_direction"] != "+Z":
        raise ValueError("The longitudinal axis is +Z, with the proximal plane at z = 0")
    if frame["proximal_plane_z_mm"] != 0:
        raise ValueError("The proximal plane is z = 0")
    if frame["ml_axis"] != "X" or frame["ap_axis"] != "Y":
        raise ValueError("X is medial-lateral and Y is anterior-posterior")

    total_length = float(profile["total_length_mm"])
    sections = tuple(
        SectionSpec(
            id=item["id"],
            z_mm=float(item["z_mm"]),
            circumference_mm=float(item["circumference_mm"]),
            ap_over_ml=float(item["ap_over_ml"]),
        )
        for item in profile["sections"]
    )
    if len(sections) < 2:
        raise ValueError("At least two cross-sections are required")
    if sections[0].z_mm != 0:
        raise ValueError("The first section is the proximal plane at z = 0")
    for earlier, later in zip(sections, sections[1:]):
        if later.z_mm <= earlier.z_mm:
            raise ValueError("Section positions must increase along +Z")
    for item, spec in zip(profile["sections"], sections):
        expected_z = float(item["length_fraction"]) * total_length
        if abs(expected_z - spec.z_mm) > 1e-6:
            raise ValueError(f"Section {spec.id} z does not match its length fraction")

    ratios = {spec.ap_over_ml for spec in sections}
    if len(ratios) != 1:
        raise ValueError(
            "Every section must use the same ap_over_ml. "
            "This solid is a revolution scaled once along Y."
        )

    cap = profile["distal_cap"]
    cap_start = float(cap["start_z_mm"])
    cap_tip = float(cap["tip_z_mm"])
    cap_length = float(cap["length_mm"])
    if sections[-1].id != cap["reference_section_id"] or sections[-1].z_mm != cap_start:
        raise ValueError("The distal circumference is the section where the cap starts")
    if abs((cap_start + cap_length) - cap_tip) > 1e-6 or abs(cap_tip - total_length) > 1e-6:
        raise ValueError("The cap must run from the distal section to the total length")
    if cap_length <= 0:
        raise ValueError("The distal cap length must be positive")

    tolerances = profile["tolerances"]
    return LimbParameters(
        model_id=profile["model_id"],
        model_version=profile["model_version"],
        units="mm",
        total_length_mm=total_length,
        sections=sections,
        cap_start_z_mm=cap_start,
        cap_tip_z_mm=cap_tip,
        cap_length_mm=cap_length,
        sample_step_mm=float(profile["interpolation"]["profile_sample_step_mm"]),
        cap_tangent_blend_mm=float(profile["interpolation"]["cap_tangent_blend_mm"]),
        circumference_tolerance_mm=float(tolerances["circumference_mm"]),
        length_tolerance_mm=float(tolerances["length_mm"]),
    )


def profile_with_total_length(profile: dict, total_length_mm: float) -> dict:
    """Return a new profile with a new total length. The input is not mutated.

    Stations keep their ``length_fraction``. Absolute ``z_mm`` values and the
    distal cap are recomputed from that fraction times the new length.
    Circumferences stay in millimetres and are not scaled.
    """
    if isinstance(total_length_mm, bool) or not isinstance(total_length_mm, (int, float)):
        raise TypeError("total_length_mm must be a number")
    length = float(total_length_mm)
    if not math.isfinite(length) or length <= 0:
        raise ValueError("total_length_mm must be a positive finite number")
    revised = copy.deepcopy(profile)
    revised["total_length_mm"] = length
    revised["section_position_convention"] = "length_fraction"
    for section in revised["sections"]:
        section["z_mm"] = float(section["length_fraction"]) * length
    cap = revised["distal_cap"]
    start = next(
        section["z_mm"]
        for section in revised["sections"]
        if section["id"] == cap["reference_section_id"]
    )
    cap["start_z_mm"] = start
    cap["tip_z_mm"] = length
    cap["length_mm"] = length - start
    revised["model_version"] = f"{profile['model_version']}+length"
    return revised


def updated_profile(
    profile: dict,
    section_id: str,
    *,
    circumference_mm: float | None = None,
    scale: float | None = None,
) -> dict:
    """Return a new profile with one circumference changed. The input is not mutated."""
    if (circumference_mm is None) == (scale is None):
        raise ValueError("Pass circumference_mm or scale, not both")
    revised = copy.deepcopy(profile)
    found = False
    for section in revised["sections"]:
        if section["id"] != section_id:
            continue
        found = True
        if scale is not None:
            if scale <= 0:
                raise ValueError("scale must be positive")
            section["circumference_mm"] = section["circumference_mm"] * scale
        else:
            if circumference_mm <= 0:
                raise ValueError("circumference_mm must be positive")
            section["circumference_mm"] = circumference_mm
    if not found:
        known = [section["id"] for section in profile["sections"]]
        raise KeyError(f"No section {section_id!r}. Known sections: {known}")
    revised["model_version"] = f"{profile['model_version']}+{section_id}"
    return revised


def _ml_radius(parameters: LimbParameters):
    """ML semi-axis versus z. Stations stay on a monotone PCHIP.

    The last few millimetres ease to a zero slope so the revolved side meets
    the ellipsoidal cap. A single clamped cubic through every station was not
    monotone for a small edit of the middle circumference, so that spline is
    not used.
    """
    positions = [spec.z_mm for spec in parameters.sections]
    radii = [
        semi_axes_for_circumference(spec.circumference_mm, parameters.ap_over_ml)[1]
        for spec in parameters.sections
    ]
    for earlier, later in zip(radii, radii[1:]):
        if later > earlier + 1e-8:
            raise RuntimeError(
                "Section radii increase along +Z. Refusing to build a folded solid."
            )
    pchip = PchipInterpolator(positions, radii)
    z1 = parameters.cap_start_z_mm
    z0 = z1 - parameters.cap_tangent_blend_mm
    if parameters.cap_tangent_blend_mm <= 0 or z0 <= positions[-2]:
        raise RuntimeError("The cap tangent blend overlaps a measurement station")
    p0 = float(pchip(z0))
    slope = float(pchip(z0, 1))
    p1 = radii[-1]
    delta = (p1 - p0) / (z1 - z0)
    if delta == 0 or slope * delta <= 0:
        slope = 0.0
    else:
        slope = math.copysign(min(abs(slope), 3.0 * abs(delta)), slope)

    def radius(z: float) -> float:
        z = float(z)
        if z <= z0:
            return float(pchip(z))
        u = (z - z0) / (z1 - z0)
        h00 = (2.0 * u**3) - (3.0 * u**2) + 1.0
        h10 = u**3 - (2.0 * u**2) + u
        h01 = (-2.0 * u**3) + (3.0 * u**2)
        h11 = u**3 - u**2
        return (h00 * p0) + (h10 * (z1 - z0) * slope) + (h01 * p1) + (h11 * (z1 - z0) * 0.0)

    samples = np.linspace(positions[0], z1, 500)
    values = np.array([radius(z) for z in samples])
    if np.any(values <= 0) or np.any(np.diff(values) > 1e-7):
        raise RuntimeError("The radius profile is not a positive decreasing curve")
    return radius


def _edge_endpoints(edge) -> tuple[gp_Pnt, gp_Pnt]:
    curve = BRepAdaptor_Curve(edge)
    return curve.Value(curve.FirstParameter()), curve.Value(curve.LastParameter())


def _orient_edge(edge, start: gp_Pnt):
    """Return the edge running away from ``start``, and its far endpoint."""
    first, last = _edge_endpoints(edge)
    if first.Distance(start) <= 1e-5:
        return edge, last
    if last.Distance(start) <= 1e-5:
        return TopoDS.Edge_s(edge.Reversed()), first
    raise RuntimeError(
        "Profile edges do not meet. "
        f"Wanted ({start.X():.4f}, {start.Z():.4f}), "
        f"got ({first.X():.4f}, {first.Z():.4f}) and ({last.X():.4f}, {last.Z():.4f})."
    )


def _cap_edge(ml_semi: float, z_start: float, z_tip: float):
    """Quarter-ellipse from (ml_semi, z_start) to the axis point (0, z_tip)."""
    height = z_tip - z_start
    origin = gp_Pnt(0.0, 0.0, z_start)
    # Normal -Y puts the ellipse in the XZ plane with its second axis along +Z.
    if ml_semi >= height:
        axes = gp_Ax2(origin, gp_Dir(0.0, -1.0, 0.0), gp_Dir(1.0, 0.0, 0.0))
        ellipse = gp_Elips(axes, ml_semi, height)
        arc = GC_MakeArcOfEllipse(ellipse, 0.0, math.pi / 2, True).Value()
    else:
        axes = gp_Ax2(origin, gp_Dir(0.0, -1.0, 0.0), gp_Dir(0.0, 0.0, 1.0))
        ellipse = gp_Elips(axes, height, ml_semi)
        arc = GC_MakeArcOfEllipse(ellipse, -math.pi / 2, 0.0, True).Value()
    return BRepBuilderAPI_MakeEdge(arc).Edge()


def _profile_wire(parameters: LimbParameters, radius_at):
    ml_start = float(radius_at(0.0))
    ml_cap = float(radius_at(parameters.cap_start_z_mm))
    positions = [0.0]
    z = 0.0
    while z < parameters.cap_start_z_mm - 1e-9:
        z = min(parameters.cap_start_z_mm, z + parameters.sample_step_mm)
        positions.append(z)
    for spec in parameters.sections:
        positions.append(spec.z_mm)
    positions = sorted(set(round(z, 6) for z in positions))

    points = TColgp_Array1OfPnt(1, len(positions))
    for index, z in enumerate(positions, start=1):
        radius = ml_cap if abs(z - parameters.cap_start_z_mm) <= 1e-6 else float(radius_at(z))
        if abs(z) <= 1e-6:
            radius = ml_start
        points.SetValue(index, gp_Pnt(radius, 0.0, z))

    approximated = GeomAPI_PointsToBSpline(points, 3, 8, Tol3D=1e-7)
    if not approximated.IsDone():
        raise RuntimeError("The radius profile could not be approximated within 1e-7 mm")
    side_curve = approximated.Curve()
    side = BRepBuilderAPI_MakeEdge(side_curve).Edge()
    proximal = BRepBuilderAPI_MakeEdge(gp_Pnt(0.0, 0.0, 0.0), gp_Pnt(ml_start, 0.0, 0.0)).Edge()
    cap = _cap_edge(ml_cap, parameters.cap_start_z_mm, parameters.cap_tip_z_mm)
    axis = BRepBuilderAPI_MakeEdge(
        gp_Pnt(0.0, 0.0, parameters.cap_tip_z_mm),
        gp_Pnt(0.0, 0.0, 0.0),
    ).Edge()

    cursor = gp_Pnt(0.0, 0.0, 0.0)
    ordered = []
    for edge in (proximal, side, cap, axis):
        oriented, cursor = _orient_edge(edge, cursor)
        ordered.append(oriented)
    if cursor.Distance(gp_Pnt(0.0, 0.0, 0.0)) > 1e-5:
        raise RuntimeError("The profile wire does not close")

    wire = BRepBuilderAPI_MakeWire()
    for edge in ordered:
        wire.Add(edge)
    if not wire.IsDone():
        raise RuntimeError(f"Profile wire failed: {wire.Error()}")
    return wire.Wire()


def _signed_volume(shape) -> float:
    props = GProp_GProps()
    BRepGProp.VolumeProperties_s(shape, props)
    return props.Mass()


def generate_limb(parameters: LimbParameters) -> cq.Shape:
    """Build one closed solid from the numerical parameters."""
    radius_at = _ml_radius(parameters)
    wire = _profile_wire(parameters, radius_at)
    face = BRepBuilderAPI_MakeFace(wire)
    if not face.IsDone():
        raise RuntimeError("The profile did not make a face")
    revolved = BRepPrimAPI_MakeRevol(
        face.Face(),
        gp_Ax1(gp_Pnt(0.0, 0.0, 0.0), gp_Dir(0.0, 0.0, 1.0)),
        2.0 * math.pi,
    )
    if not revolved.IsDone():
        raise RuntimeError("Revolution of the limb profile failed")

    transform = gp_GTrsf()
    ratio = parameters.ap_over_ml
    transform.SetVectorialPart(gp_Mat(1.0, 0.0, 0.0, 0.0, ratio, 0.0, 0.0, 0.0, 1.0))
    scaled = BRepBuilderAPI_GTransform(revolved.Shape(), transform, True)
    if not scaled.IsDone():
        raise RuntimeError("Y scale of the revolved limb failed")
    shape = scaled.Shape()
    if _signed_volume(shape) < 0:
        shape = shape.Reversed()
    return cq.Shape.cast(shape)


def _reject_reference(path: Path, *, overwrite_reference: bool) -> None:
    if overwrite_reference:
        return
    resolved = path.resolve()
    protected = {
        REFERENCE_STEP.resolve(),
        REFERENCE_STL.resolve(),
        SOCKET_STEP.resolve(),
        SOCKET_STL.resolve(),
    }
    if resolved in protected:
        raise ValueError(f"Refusing to overwrite the reference model at {path}")


def export_solid(
    shape: cq.Shape,
    step_path: Path,
    stl_path: Path | None = None,
    *,
    overwrite_reference: bool = False,
) -> None:
    """Write STEP and, when asked, an STL mesh. The reference files are protected."""
    step_path = Path(step_path)
    _reject_reference(step_path, overwrite_reference=overwrite_reference)
    step_path.parent.mkdir(parents=True, exist_ok=True)
    cq.exporters.export(shape, str(step_path), exportType="STEP")
    if stl_path is None:
        return
    stl_path = Path(stl_path)
    _reject_reference(stl_path, overwrite_reference=overwrite_reference)
    stl_path.parent.mkdir(parents=True, exist_ok=True)
    cq.exporters.export(
        shape,
        str(stl_path),
        exportType="STL",
        tolerance=0.05,
        angularTolerance=0.05,
    )


def derived_section_axes(parameters: LimbParameters) -> list[dict]:
    """Semi-axes implied by the profile, before the solid is measured."""
    rows = []
    for spec in parameters.sections:
        ap_semi, ml_semi = semi_axes_for_circumference(spec.circumference_mm, spec.ap_over_ml)
        rows.append(
            {
                "id": spec.id,
                "z_mm": spec.z_mm,
                "target_circumference_mm": spec.circumference_mm,
                "ap_over_ml": spec.ap_over_ml,
                "ap_semi_axis_mm": ap_semi,
                "ml_semi_axis_mm": ml_semi,
                "integral_circumference_mm": ellipse_circumference(ap_semi, ml_semi),
                "ramanujan_circumference_mm": ramanujan_circumference(ap_semi, ml_semi),
            }
        )
    return rows


def main() -> None:
    from tools.cad.validate_limb import validate_and_write_reference

    validate_and_write_reference()


if __name__ == "__main__":
    main()
