"""Measurements of a hollow socket solid.

A plane through the wall usually cuts two closed curves. The inner curve is
the one with the smaller mean radius. Wall thickness is the difference of
those semi-axes at the same z. It is not the nominal thickness copied out of
the profile, and it is not a surface-normal caliper reading.

Socket depth is the cutting-plane outer tip minus the opening plane z = 0.
The rolled brim sits at negative z and is not part of that depth.
"""

from __future__ import annotations

import math
from pathlib import Path

from OCP.BRepAdaptor import BRepAdaptor_Curve
from OCP.BRepAlgoAPI import BRepAlgoAPI_Section
from OCP.BRepBndLib import BRepBndLib
from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace, BRepBuilderAPI_MakeWire
from OCP.BRepGProp import BRepGProp
from OCP.BRepIntCurveSurface import BRepIntCurveSurface_Inter
from OCP.Bnd import Bnd_Box
from OCP.GCPnts import GCPnts_AbscissaPoint
from OCP.GProp import GProp_GProps
from OCP.TopAbs import TopAbs_EDGE, TopAbs_SHELL
from OCP.TopExp import TopExp_Explorer
from OCP.TopoDS import TopoDS
from OCP.gp import gp_Dir, gp_Lin, gp_Pln, gp_Pnt

from tools.cad.generate_limb import SOCKET_STEP
from tools.cad.generate_socket import compile_socket, construction_targets, load_socket_profile
from tools.cad.measure_limb import (
    StepLoadError,
    bounding_box_mm,
    is_valid,
    load_step_shape,
    material_z_extent_mm,
    occ_shape,
    signed_volume_mm3,
    solid_count,
)

_MIN_EDGE_MM = 0.5


def _failure(code: str, message: str, **extra) -> dict:
    body = {
        "ok": False,
        "units": "mm",
        "clinical_use": False,
        "error": {"code": code, "message": message},
    }
    body.update(extra)
    return body


def _finite_number(value, name: str) -> tuple[float | None, dict | None]:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None, _failure("invalid_value", f"{name} must be a number")
    number = float(value)
    if not math.isfinite(number):
        return None, _failure("non_finite", f"{name} must be a finite number")
    return number, None


def _edge_record(edge) -> dict | None:
    curve = BRepAdaptor_Curve(edge)
    length = float(GCPnts_AbscissaPoint.Length_s(curve))
    if length < _MIN_EDGE_MM:
        return None
    box = Bnd_Box()
    BRepBndLib.AddOptimal_s(edge, box)
    xmin, ymin, _zmin, xmax, ymax, _zmax = box.Get()
    count = 16
    first = curve.FirstParameter()
    last = curve.LastParameter()
    radii = []
    for index in range(count):
        point = curve.Value(first + (last - first) * index / (count - 1))
        radii.append(math.hypot(point.X(), point.Y()))
    area = _face_area(edge)
    return {
        "perimeter_mm": length,
        "mean_radius_mm": sum(radii) / len(radii),
        "ml_diameter_mm": float(xmax - xmin),
        "ap_diameter_mm": float(ymax - ymin),
        "area_mm2": area,
    }


def _face_area(edge) -> float | None:
    """Area of the planar face bounded by one closed section edge."""
    wire = BRepBuilderAPI_MakeWire(edge)
    if not wire.IsDone():
        return None
    face = BRepBuilderAPI_MakeFace(wire.Wire(), True)
    if not face.IsDone():
        return None
    props = GProp_GProps()
    BRepGProp.SurfaceProperties_s(face.Face(), props)
    return float(props.Mass())


def _sample_xy(edge, samples: int) -> list[list[float]]:
    curve = BRepAdaptor_Curve(edge)
    first = curve.FirstParameter()
    last = curve.LastParameter()
    count = max(int(samples), 8)
    points = []
    for index in range(count):
        point = curve.Value(first + (last - first) * index / (count - 1))
        points.append([float(point.X()), float(point.Y())])
    return points


def section_polylines(shape, z_mm: float, samples: int = 360) -> list[dict]:
    """Closed section curves at z, sorted from the axis outward, with XY samples.

    Edges shorter than 0.5 mm are dropped. Each row includes ``points_xy``.
    """
    section = BRepAlgoAPI_Section(
        occ_shape(shape),
        gp_Pln(gp_Pnt(0.0, 0.0, float(z_mm)), gp_Dir(0.0, 0.0, 1.0)),
        False,
    )
    if hasattr(section, "SetNonDestructive"):
        section.SetNonDestructive(True)
    section.Build()
    rows = []
    explorer = TopExp_Explorer(section.Shape(), TopAbs_EDGE)
    while explorer.More():
        edge = TopoDS.Edge_s(explorer.Current())
        record = _edge_record(edge)
        if record is not None:
            record["points_xy"] = _sample_xy(edge, samples)
            rows.append(record)
        explorer.Next()
    rows.sort(key=lambda row: row["mean_radius_mm"])
    return rows


def section_contours(shape, z_mm: float) -> list[dict]:
    """Closed section curves at z, sorted from the axis outward.

    Edges shorter than 0.5 mm are dropped. A tangent cut, such as the exact
    crest of the rolled brim, can still return several fragments; callers
    treat more than two curves as ambiguous.
    """
    rows = section_polylines(shape, z_mm, samples=16)
    for row in rows:
        row.pop("points_xy", None)
    return rows


def ray_hits(shape, origin: tuple[float, float, float], direction: tuple[float, float, float]) -> list[float]:
    """Parameters W > 0 where the ray meets the solid, nearest first.

    ``gp_Lin`` is infinite, so hits behind the origin are discarded. Duplicate
    face hits within 0.05 mm are collapsed.
    """
    inter = BRepIntCurveSurface_Inter()
    inter.Init(
        occ_shape(shape),
        gp_Lin(gp_Pnt(*origin), gp_Dir(*direction)),
        1e-7,
    )
    distances: list[float] = []
    guard = 0
    while inter.More():
        if inter.W() > 1e-4:
            distances.append(float(inter.W()))
        inter.Next()
        guard += 1
        if guard > 400:
            break
    distances.sort()
    unique: list[float] = []
    for distance in distances:
        if not unique or abs(distance - unique[-1]) > 0.05:
            unique.append(distance)
    return unique


def _shell_count(shape) -> int:
    count = 0
    explorer = TopExp_Explorer(occ_shape(shape), TopAbs_SHELL)
    while explorer.More():
        count += 1
        explorer.Next()
    return count


def _pair_contours(contours: list[dict], z_mm: float) -> dict:
    """Label the inner and outer curves. Measured numbers are not targets."""
    base = {
        "z_mm": z_mm,
        "contour_count": len(contours),
        "status": "measured",
        "inner_perimeter_mm": None,
        "outer_perimeter_mm": None,
        "inner_ml_diameter_mm": None,
        "inner_ap_diameter_mm": None,
        "outer_ml_diameter_mm": None,
        "outer_ap_diameter_mm": None,
        "inner_area_mm2": None,
        "outer_area_mm2": None,
        "ml_wall_thickness_mm": None,
        "ap_wall_thickness_mm": None,
    }
    if not contours:
        base["status"] = "no_intersection"
        return base
    if len(contours) > 2:
        base["status"] = "ambiguous"
        return base
    if len(contours) == 1:
        outer = contours[0]
        base["status"] = "outer_only"
        base["outer_perimeter_mm"] = outer["perimeter_mm"]
        base["outer_ml_diameter_mm"] = outer["ml_diameter_mm"]
        base["outer_ap_diameter_mm"] = outer["ap_diameter_mm"]
        base["outer_area_mm2"] = outer["area_mm2"]
        return base
    inner, outer = contours
    base["inner_perimeter_mm"] = inner["perimeter_mm"]
    base["outer_perimeter_mm"] = outer["perimeter_mm"]
    base["inner_ml_diameter_mm"] = inner["ml_diameter_mm"]
    base["inner_ap_diameter_mm"] = inner["ap_diameter_mm"]
    base["outer_ml_diameter_mm"] = outer["ml_diameter_mm"]
    base["outer_ap_diameter_mm"] = outer["ap_diameter_mm"]
    base["inner_area_mm2"] = inner["area_mm2"]
    base["outer_area_mm2"] = outer["area_mm2"]
    base["ml_wall_thickness_mm"] = (outer["ml_diameter_mm"] - inner["ml_diameter_mm"]) / 2.0
    base["ap_wall_thickness_mm"] = (outer["ap_diameter_mm"] - inner["ap_diameter_mm"]) / 2.0
    return base


def _resolve_shape(source, socket_profile: dict):
    if not isinstance(source, (str, Path)):
        return source
    text = str(source)
    looks_like_path = isinstance(source, Path) or text.endswith(".step") or "/" in text or "\\" in text
    if looks_like_path:
        return load_step_shape(Path(text))
    if text == socket_profile.get("socket_model_id"):
        return load_step_shape(SOCKET_STEP)
    raise StepLoadError("unknown_model", f"Unknown socket model {text!r}")


def measure_socket(
    source,
    socket_profile: dict | None = None,
    limb_profile: dict | None = None,
    *,
    z_mm: float | None = None,
    length_fraction: float | None = None,
) -> dict:
    """Measure a socket shape or STEP file.

    ``length_fraction`` is a fraction of ``socket_depth_mm`` from the opening
    plane toward the outer tip. It is not a fraction of the limb length.
    """
    if socket_profile is None:
        try:
            socket_profile = load_socket_profile()
        except (OSError, ValueError) as exc:
            return _failure("missing_file", f"Could not read the socket profile: {exc}")
    if limb_profile is None:
        from tools.cad.generate_limb import load_profile

        try:
            limb_profile = load_profile()
        except (OSError, ValueError) as exc:
            return _failure("missing_file", f"Could not read the limb profile: {exc}")

    try:
        spec = compile_socket(limb_profile, socket_profile)
    except (ValueError, KeyError, TypeError) as exc:
        return _failure("invalid_value", str(exc))

    if z_mm is not None and length_fraction is not None:
        return _failure("invalid_value", "Pass z_mm or length_fraction, not both")
    if length_fraction is not None:
        fraction, error = _finite_number(length_fraction, "length_fraction")
        if error:
            return error
        assert fraction is not None
        if fraction < 0.0 or fraction > 1.0:
            return _failure("invalid_section", "length_fraction must be from 0 to 1")
        z_mm = spec.opening_plane_z_mm + fraction * spec.socket_depth_mm
    if z_mm is not None:
        z_value, error = _finite_number(z_mm, "z_mm")
        if error:
            return error
        z_mm = z_value

    try:
        shape = _resolve_shape(source, socket_profile)
    except StepLoadError as exc:
        return _failure(exc.code, str(exc))

    if z_mm is not None:
        contours = section_contours(shape, z_mm)
        row = _pair_contours(contours, z_mm)
        if row["status"] == "no_intersection":
            return _failure(
                "no_intersection",
                f"No section curve at z = {z_mm} mm",
                section=row,
            )
        return {
            "ok": True,
            "clinical_use": False,
            "units": "mm",
            "section": row,
            "note": "Inner and outer are separated by mean radius. A single curve is outer_only.",
        }

    targets = construction_targets(spec)
    extent = material_z_extent_mm(shape, spec.opening_plane_z_mm - spec.rim_radius_mm - 1.0, spec.outer_tip_z_mm)
    sections = []
    for station in targets["stations"]:
        row = _pair_contours(section_contours(shape, station["z_mm"]), station["z_mm"])
        row["id"] = station["id"]
        row["role"] = station["role"]
        sections.append(row)

    opening = next(row for row in sections if row["id"] == "proximal")
    cavity_z = spec.limb.total_length_mm * 0.5
    proximal_hits = ray_hits(shape, (0.0, 0.0, cavity_z), (0.0, 0.0, -1.0))
    distal_hits = ray_hits(shape, (0.0, 0.0, cavity_z), (0.0, 0.0, 1.0))
    outer_tip = float(extent["zmax_mm"])
    inner_hit = None if not distal_hits else cavity_z + distal_hits[0]
    axial_wall = None if inner_hit is None else outer_tip - inner_hit
    plug = _pair_contours(
        section_contours(shape, (spec.inner_tip_z_mm + spec.outer_tip_z_mm) / 2.0),
        (spec.inner_tip_z_mm + spec.outer_tip_z_mm) / 2.0,
    )
    beyond = section_contours(shape, spec.outer_tip_z_mm + 2.0)

    return {
        "ok": True,
        "clinical_use": False,
        "units": "mm",
        "socket_model_id": spec.socket_model_id,
        "coordinate_frame": {
            "ml_axis": "X",
            "ap_axis": "Y",
            "distal": "+Z",
            "opening_plane_z_mm": spec.opening_plane_z_mm,
            "side": None,
        },
        "method": {
            "inner_outer": "The inner contour is the section curve with the smaller mean radius.",
            "wall_thickness": (
                "Medial-lateral and anterior-posterior thickness are half the difference of the "
                "outer and inner section diameters at the same z. This is an axis-aligned chord, "
                "not a surface-normal thickness, and it is not the nominal parameter."
            ),
            "depth": "Cutting-plane outer tip minus the opening plane. The brim above z = 0 is excluded.",
            "distal_axial_wall": "Outer tip minus the nearest axis hit distal of the cavity sample.",
            "area": "Planar face area of each closed section edge.",
            "uncertainty": (
                "Station perimeters on this construction match the elliptic integral to well under "
                "0.05 mm. The outer tip search can stop a few thousandths of a millimetre short of "
                "a point. Acceptance tolerances are on the socket profile."
            ),
        },
        "depth_mm": outer_tip - spec.opening_plane_z_mm,
        "outer_tip_z_mm": outer_tip,
        "rim_crest_z_mm": float(extent["zmin_mm"]),
        "overall_extent_mm": extent,
        "bounding_box_mm": bounding_box_mm(shape),
        "volume_mm3": signed_volume_mm3(shape),
        "topology": {
            "valid": is_valid(shape),
            "solid_count": solid_count(shape),
            "shell_count": _shell_count(shape),
        },
        "proximal_opening": {
            "z_mm": opening["z_mm"],
            "status": opening["status"],
            "inner_perimeter_mm": opening["inner_perimeter_mm"],
            "outer_perimeter_mm": opening["outer_perimeter_mm"],
            "inner_ml_diameter_mm": opening["inner_ml_diameter_mm"],
            "inner_ap_diameter_mm": opening["inner_ap_diameter_mm"],
            "outer_ml_diameter_mm": opening["outer_ml_diameter_mm"],
            "outer_ap_diameter_mm": opening["outer_ap_diameter_mm"],
            "inner_area_mm2": opening["inner_area_mm2"],
            "outer_area_mm2": opening["outer_area_mm2"],
        },
        "sections": sections,
        "wall_thickness_samples": [
            {
                "id": row["id"],
                "z_mm": row["z_mm"],
                "ml_mm": row["ml_wall_thickness_mm"],
                "ap_mm": row["ap_wall_thickness_mm"],
                "status": row["status"],
                "method": "semi_axis_difference",
            }
            for row in sections
        ],
        "distal_end": {
            "inner_surface_z_mm": inner_hit,
            "outer_tip_z_mm": outer_tip,
            "axial_wall_mm": axial_wall,
            "plug_section_status": plug["status"],
            "plug_contour_count": plug["contour_count"],
            "beyond_tip_contour_count": len(beyond),
        },
        "cavity": {
            "proximal_opening_open": len(proximal_hits) == 0,
            "distal_end_closed": inner_hit is not None and axial_wall is not None and axial_wall > 0.5,
            "sample_z_mm": cavity_z,
        },
        "constructed_targets": targets,
    }


def section_value(measured: dict, section_id: str, field: str) -> float | None:
    """Read one measured field. Returns None when that contour was not found."""
    for row in measured.get("sections", []):
        if row.get("id") == section_id:
            value = row.get(field)
            return None if value is None else float(value)
    return None
