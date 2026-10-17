"""Independent measurements of a generated limb solid.

Section length is the curve length of the intersection with a plane z = constant.
It does not read the circumference stored in the profile.
"""

from __future__ import annotations

import math
from pathlib import Path

from OCP.BRepAdaptor import BRepAdaptor_Curve
from OCP.BRepAlgoAPI import BRepAlgoAPI_Section
from OCP.BRepBndLib import BRepBndLib
from OCP.BRepCheck import BRepCheck_Analyzer
from OCP.BRepGProp import BRepGProp
from OCP.Bnd import Bnd_Box
from OCP.GCPnts import GCPnts_AbscissaPoint
from OCP.GProp import GProp_GProps
from OCP.TopAbs import TopAbs_EDGE, TopAbs_SOLID
from OCP.TopExp import TopExp_Explorer
from OCP.TopoDS import TopoDS
from OCP.gp import gp_Dir, gp_Pln, gp_Pnt


def occ_shape(shape):
    """Accept a CadQuery shape or a raw OpenCascade shape."""
    return shape.wrapped if hasattr(shape, "wrapped") else shape


def is_valid(shape) -> bool:
    return bool(BRepCheck_Analyzer(occ_shape(shape)).IsValid())


def solid_count(shape) -> int:
    count = 0
    explorer = TopExp_Explorer(occ_shape(shape), TopAbs_SOLID)
    while explorer.More():
        count += 1
        explorer.Next()
    return count


def signed_volume_mm3(shape) -> float:
    props = GProp_GProps()
    BRepGProp.VolumeProperties_s(occ_shape(shape), props)
    return props.Mass()


def _plane_cuts_solid(shape, z_mm: float) -> bool:
    _length, count = section_circumference(shape, z_mm)
    return count > 0


def material_z_extent_mm(shape, nominal_min_mm: float, nominal_max_mm: float) -> dict:
    """Z range of planes that actually cut the solid.

    A point tip does not produce an edge, so the last cut sits just short of
    the tip. A scaled OpenCascade surface box can also include poles past the
    trimmed solid; this search does not use that box.
    """

    def locate_occupied_near(start: float, toward: float) -> float:
        if _plane_cuts_solid(shape, start):
            return start
        step = 0.5 if toward > start else -0.5
        z = start
        for _ in range(40):
            z += step
            if (toward - z) * step < 0:
                break
            if _plane_cuts_solid(shape, z):
                return z
        raise RuntimeError("No cross-section found near the expected end of the limb")

    def empty_outside(occupied: float, direction: float) -> float:
        z = occupied
        for _ in range(8):
            z += direction
            if not _plane_cuts_solid(shape, z):
                return z
        return z

    low_in = locate_occupied_near(nominal_min_mm, nominal_max_mm)
    high_in = locate_occupied_near(nominal_max_mm, nominal_min_mm)
    low_out = empty_outside(low_in, -5.0)
    high_out = empty_outside(high_in, 5.0)

    for _ in range(30):
        mid = (low_out + low_in) / 2.0
        if _plane_cuts_solid(shape, mid):
            low_in = mid
        else:
            low_out = mid
    for _ in range(30):
        mid = (high_in + high_out) / 2.0
        if _plane_cuts_solid(shape, mid):
            high_in = mid
        else:
            high_out = mid

    return {
        "zmin_mm": low_in,
        "zmax_mm": high_in,
        "length_mm": high_in - low_in,
    }


def bounding_box_mm(shape) -> dict:
    box = Bnd_Box()
    # AddOptimal follows the trimmed solid. The plain bounding box includes
    # untrimmed surface poles and can extend past the proximal face and the tip.
    BRepBndLib.AddOptimal_s(occ_shape(shape), box)
    xmin, ymin, zmin, xmax, ymax, zmax = box.Get()
    return {
        "xmin_mm": xmin,
        "ymin_mm": ymin,
        "zmin_mm": zmin,
        "xmax_mm": xmax,
        "ymax_mm": ymax,
        "zmax_mm": zmax,
        "length_mm": zmax - zmin,
    }


def section_circumference(shape, z_mm: float) -> tuple[float, int]:
    """Return (perimeter mm, edge count) of the cross-section at z_mm.

    The perimeter is the sum of the exact edge lengths on the cutting plane.
    A miss returns (0.0, 0).
    """
    section = BRepAlgoAPI_Section(
        occ_shape(shape),
        gp_Pln(gp_Pnt(0.0, 0.0, float(z_mm)), gp_Dir(0.0, 0.0, 1.0)),
        False,
    )
    section.Build()
    total = 0.0
    count = 0
    explorer = TopExp_Explorer(section.Shape(), TopAbs_EDGE)
    while explorer.More():
        curve = BRepAdaptor_Curve(TopoDS.Edge_s(explorer.Current()))
        total += GCPnts_AbscissaPoint.Length_s(curve)
        count += 1
        explorer.Next()
    return total, count


def measure_sections(shape, profile: dict) -> list[dict]:
    """Measure every configured station. Targets are copied in for the report only."""
    rows = []
    for section in profile["sections"]:
        measured, edges = section_circumference(shape, section["z_mm"])
        target = float(section["circumference_mm"])
        rows.append(
            {
                "id": section["id"],
                "z_mm": float(section["z_mm"]),
                "target_circumference_mm": target,
                "measured_circumference_mm": measured,
                "error_mm": measured - target,
            "edge_count": edges,
        }
    )
    return rows


# Stations used when a profile is not supplied. 0.9 is the standard model's
# distal reference, the last plane that has a circumference. Fraction 1 is the tip.
STANDARD_STATIONS: tuple[tuple[str, float], ...] = (
    ("proximal", 0.0),
    ("q25", 0.25),
    ("q50", 0.5),
    ("q75", 0.75),
    ("distal_reference", 0.9),
)


class StepLoadError(Exception):
    """A STEP path could not be read as a solid."""

    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(message)


def load_step_shape(path: Path):
    """Import a STEP file. Missing and unreadable files raise ``StepLoadError``."""
    import cadquery as cq

    step_path = Path(path)
    if not step_path.is_file():
        raise StepLoadError("missing_file", f"No STEP file at {step_path}")
    if step_path.stat().st_size < 20:
        raise StepLoadError("invalid_step", f"{step_path} is too small to be a STEP file")
    try:
        return cq.importers.importStep(str(step_path)).val()
    except Exception as exc:
        raise StepLoadError("invalid_step", f"Could not read {step_path}: {exc}") from exc


def _failure(code: str, message: str, **extra) -> dict:
    body = {
        "ok": False,
        "units": "mm",
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


def measure_shape(
    shape,
    profile: dict | None = None,
    *,
    length_fraction: float | None = None,
    z_mm: float | None = None,
) -> dict:
    """Measure a solid that is already loaded.

    With neither ``length_fraction`` nor ``z_mm``, every documented station is
    measured. A fraction of 1 is the tip point and has no circumference.
    Fractions outside ``[0, 1]`` are rejected.
    """
    if length_fraction is not None and z_mm is not None:
        return _failure("invalid_value", "Pass length_fraction or z_mm, not both")

    query_z: float | None = None
    query_fraction: float | None = None
    if length_fraction is not None:
        query_fraction, error = _finite_number(length_fraction, "length_fraction")
        if error:
            return error
        assert query_fraction is not None
        if query_fraction < 0 or query_fraction > 1:
            return _failure(
                "invalid_section",
                "length_fraction must be from 0 to 1 inclusive",
                valid_range={"min": 0, "max": 1},
            )
        total = float(profile["total_length_mm"]) if profile is not None else None
        if total is None:
            extent_hint = bounding_box_mm(shape)
            total = max(extent_hint["zmax_mm"], 0.0)
        query_z = query_fraction * total
    elif z_mm is not None:
        query_z, error = _finite_number(z_mm, "z_mm")
        if error:
            return error

    valid = is_valid(shape)
    count = solid_count(shape)
    try:
        volume = signed_volume_mm3(shape)
        box = bounding_box_mm(shape)
        nominal_max = float(profile["total_length_mm"]) if profile is not None else max(box["zmax_mm"], 1.0)
        extent = material_z_extent_mm(shape, 0.0, nominal_max)
    except RuntimeError as exc:
        return _failure(
            "invalid_geometry",
            str(exc),
            valid_solid=valid,
            solid_count=count,
        )

    if query_z is not None:
        if query_fraction == 1:
            measured, edges = 0.0, 0
        else:
            measured, edges = section_circumference(shape, query_z)
        row = {
            "id": "query",
            "length_fraction": query_fraction,
            "z_mm": query_z,
            "measured_circumference_mm": measured,
            "edge_count": edges,
            "status": "measured" if edges else "no_intersection",
        }
        if edges == 0:
            return _failure(
                "no_intersection",
                f"No closed cross-section at z = {query_z} mm",
                query=row,
                valid_solid=valid,
                solid_count=count,
                material_extent_mm=extent,
            )
        return {
            "ok": True,
            "units": "mm",
            "error": None,
            "valid_solid": valid,
            "solid_count": count,
            "volume_mm3": volume,
            "material_extent_mm": extent,
            "bounding_box_mm": box,
            "sections": [row],
        }

    if profile is not None:
        stations = [
            (section["id"], float(section["length_fraction"]), float(section["z_mm"]))
            for section in profile["sections"]
        ]
    else:
        length = extent["length_mm"]
        stations = [(name, fraction, fraction * length) for name, fraction in STANDARD_STATIONS]

    sections = []
    for name, fraction, z in stations:
        measured, edges = section_circumference(shape, z)
        sections.append(
            {
                "id": name,
                "length_fraction": fraction,
                "z_mm": z,
                "measured_circumference_mm": measured,
                "edge_count": edges,
                "status": "measured" if edges else "no_intersection",
            }
        )
    missing = [row["id"] for row in sections if row["status"] != "measured"]
    result = {
        "ok": not missing and valid and count == 1,
        "units": "mm",
        "error": None
        if not missing
        else {
            "code": "no_intersection",
            "message": f"No cross-section at {missing}",
        },
        "valid_solid": valid,
        "solid_count": count,
        "volume_mm3": volume,
        "material_extent_mm": extent,
        "bounding_box_mm": box,
        "sections": sections,
    }
    if not valid or count != 1:
        result["ok"] = False
        result["error"] = {
            "code": "invalid_geometry",
            "message": f"Expected one valid solid, found {count} (valid={valid})",
        }
    return result


def measure_limb(
    source,
    profile: dict | None = None,
    *,
    length_fraction: float | None = None,
    z_mm: float | None = None,
) -> dict:
    """Measure a STEP file or a loaded solid.

    ``source`` is a STEP path or an in-memory CadQuery/OpenCascade shape.
    Returned lengths are millimetres. Circumferences are measured from the
    solid; they are not copied from the profile.
    """
    if isinstance(source, (str, Path)):
        try:
            shape = load_step_shape(Path(source))
        except StepLoadError as exc:
            return _failure(exc.code, str(exc))
    else:
        shape = source
    measured = measure_shape(shape, profile, length_fraction=length_fraction, z_mm=z_mm)
    if profile is not None and measured.get("ok"):
        measured["model_id"] = profile.get("model_id")
    return measured
