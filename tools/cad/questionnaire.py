"""Editable limb dimensions (README section 5): defaults, checks, and the limb profile they make.

The page shows the standard demonstration limb's dimensions (data/profiles/standard_limb.json)
as editable values. Any value the user does not edit keeps the standard value, so an
unedited set rebuilds the standard limb. That limb is a parametric ellipse model, not the
OpenLimbTT mesh; README section 6's mesh deformation is not implemented here.

Stations (README 5.2), measured along the limb from the mid-patellar tendon (z = 0):
    P   40 mm below the tendon
    M   halfway between P and D
    D   40 mm above the distal end

How edits change the shape (the README 6.2 idea, applied to the parametric limb):
    1. Length scales the standard limb along its axis.
    2. Each circumference sets a scale factor at its station: edited value divided by the
       standard limb's circumference at the matching point. Between stations the factor is
       interpolated; above P and below D it is held.
    3. Every station of the new profile is the standard circumference there times that factor,
       so the standard limb's taper and rounded end are kept, only resized.
The profile keeps the station names the socket code looks up (proximal, q25, q50, q75,
distal_reference) and adds P and D.
"""

from __future__ import annotations

import copy
import math

from tools.cad.generate_limb import semi_axes_for_circumference

STATION_OFFSET_MM = 40.0
# The rounded end starts at this fraction of length, as on the standard limb (126 / 140).
CAP_START_FRACTION = 0.9

EDITABLE = [
    "length_mm",
    "proximal_circumference_mm",
    "mid_circumference_mm",
    "distal_circumference_mm",
    "ap_mm",
    "ml_mm",
    "distal_shape",
    "side",
    "posture",
]
LABELS = {
    "length_mm": "Length, mid-patellar tendon to distal end (knee extended)",
    "proximal_circumference_mm": "Circumference P, 40 mm below the mid-patellar tendon",
    "mid_circumference_mm": "Circumference M, halfway between P and D",
    "distal_circumference_mm": "Circumference D, 40 mm above the distal end",
    "ap_mm": "Anterior-posterior depth at P",
    "ml_mm": "Medial-lateral width at P",
    "distal_shape": "Distal-end shape",
    "side": "Side",
    "posture": "Posture when measured",
}

# Form ranges (README 5.3), in mm.
FORM_RANGES = {
    "length_mm": (50.0, 300.0),
    "proximal_circumference_mm": (150.0, 550.0),
    "distal_circumference_mm": (100.0, 500.0),
    "mid_circumference_mm": (100.0, 550.0),
    "ap_mm": (40.0, 200.0),
    "ml_mm": (40.0, 200.0),
}
CHOICES = {
    "distal_shape": ["template", "rounder", "more_tapered"],
    "side": ["left", "right"],
    "posture": ["supine", "sitting", "standing"],
}
LENGTH_WINDOW = (0.70, 1.40)
CIRCUMFERENCE_WINDOW = (0.75, 1.35)


class MeasurementError(ValueError):
    """A set of dimensions the tools must not build from. code is a README 5.3 error code."""

    def __init__(self, code: str, reason: str, valid_range=None):
        super().__init__(reason)
        self.code = code
        self.reason = reason
        self.valid_range = valid_range


# ---------------------------------------------------------------------------
# The standard limb's values
# ---------------------------------------------------------------------------


def template_circumference(template: dict, z_mm: float) -> float:
    """Circumference of the standard limb at z, linear between its stations, held past the last."""
    sections = template["sections"]
    if z_mm <= sections[0]["z_mm"]:
        return float(sections[0]["circumference_mm"])
    for a, b in zip(sections, sections[1:]):
        if a["z_mm"] <= z_mm <= b["z_mm"]:
            t = (z_mm - a["z_mm"]) / (b["z_mm"] - a["z_mm"])
            return a["circumference_mm"] + t * (b["circumference_mm"] - a["circumference_mm"])
    return float(sections[-1]["circumference_mm"])


def defaults(template: dict) -> dict:
    """The values the page shows before any edit: the standard limb's own dimensions."""
    length = float(template["total_length_mm"])
    p = template_circumference(template, STATION_OFFSET_MM)
    ap_semi, ml_semi = semi_axes_for_circumference(p, template["sections"][0]["ap_over_ml"])
    return {
        "length_mm": length,
        "proximal_circumference_mm": round(p, 2),
        "mid_circumference_mm": round(template_circumference(template, length / 2), 2),
        "distal_circumference_mm": round(template_circumference(template, length - STATION_OFFSET_MM), 2),
        "ap_mm": round(2 * ap_semi, 2),
        "ml_mm": round(2 * ml_semi, 2),
        "distal_shape": "template",
        "side": "right",
        "posture": "supine",
    }


# ---------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------


def ellipse_perimeter(ap_mm: float, ml_mm: float) -> float:
    """Ramanujan's approximation for an ellipse with these full widths."""
    a, b = ap_mm / 2, ml_mm / 2
    return math.pi * (3 * (a + b) - math.sqrt((3 * a + b) * (a + 3 * b)))


def validate(edits: dict, template: dict) -> tuple[dict, list[str], list[str]]:
    """Fill unedited values from the standard limb and check the result.

    Returns (dimensions, edited field names, warnings) or raises MeasurementError.
    """
    edits = {k: v for k, v in edits.items() if v is not None}
    unknown = sorted(set(edits) - set(EDITABLE))
    if unknown:
        raise MeasurementError("unsupported_field", f"Not a limb dimension: {', '.join(unknown)}.", valid_range=EDITABLE)
    for name, (low, high) in FORM_RANGES.items():
        if name in edits:
            value = edits[name]
            if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value):
                raise MeasurementError("invalid_value", f"{name} must be a number in mm.")
            if not low <= value <= high:
                raise MeasurementError("invalid_value", f"{name} = {value} is outside the form range.",
                                       valid_range={"min": low, "max": high})
    for name, allowed in CHOICES.items():
        if name in edits and edits[name] not in allowed:
            code = "unsupported_shape" if name == "distal_shape" else "invalid_value"
            raise MeasurementError(code, f"{name} must be one of {allowed}.", valid_range=allowed)
    if ("ap_mm" in edits) != ("ml_mm" in edits):
        raise MeasurementError("invalid_value", "ap_mm and ml_mm are edited together: set both or neither.")

    base = defaults(template)
    dims = {**base, **edits}
    edited = [name for name in EDITABLE if name in edits and edits[name] != base[name]]

    # Values the user did not edit follow the edited ones, so the shape stays consistent.
    if "mid_circumference_mm" not in edits:
        dims["mid_circumference_mm"] = None  # follows P and D (see to_limb_profile)
    if "ap_mm" not in edits:
        dims["ap_mm"] = dims["ml_mm"] = None  # standard section shape at the new size

    tl = float(template["total_length_mm"])
    length, p, d = dims["length_mm"], dims["proximal_circumference_mm"], dims["distal_circumference_mm"]
    lo, hi = LENGTH_WINDOW
    if not lo * tl <= length <= hi * tl:
        raise MeasurementError(
            "outside_template",
            f"length_mm {length} is outside {lo}-{hi} times the standard length {tl} mm.",
            valid_range={"min": round(lo * tl, 1), "max": round(hi * tl, 1)},
        )
    lo, hi = CIRCUMFERENCE_WINDOW
    for field, value in (("proximal_circumference_mm", p), ("distal_circumference_mm", d)):
        standard = base[field]
        if not lo * standard <= value <= hi * standard:
            raise MeasurementError(
                "outside_template",
                f"{field} {value} is outside {lo}-{hi} times the standard {standard} mm.",
                valid_range={"min": round(lo * standard, 1), "max": round(hi * standard, 1)},
            )
    # README 5.3 allows D up to 15% above P, but the demo limb is built from radii that
    # may not increase toward the distal end (generate_limb refuses a folded solid).
    if d > p:
        raise MeasurementError(
            "inconsistent_taper",
            f"D ({d} mm) is larger than P ({p} mm). The demo limb can only stay the same or "
            "narrow toward the distal end. Check whether one value is mistyped.",
            valid_range={"max_distal_circumference_mm": p},
        )
    m = dims["mid_circumference_mm"]
    if m is not None and not d <= m <= p:
        raise MeasurementError(
            "inconsistent_profile",
            f"M ({m} mm) must lie between D ({d} mm) and P ({p} mm) for the demo limb.",
            valid_range={"min": d, "max": p},
        )
    if dims["ap_mm"] is not None:
        ellipse = ellipse_perimeter(dims["ap_mm"], dims["ml_mm"])
        if abs(ellipse - p) / p > 0.15:
            raise MeasurementError(
                "inconsistent_section",
                f"AP {dims['ap_mm']} x ML {dims['ml_mm']} mm implies a {ellipse:.0f} mm perimeter, "
                f"more than 15% from P ({p} mm).",
            )
    # The whole profile must narrow (or stay level) toward the distal end.
    radii_increase = _increasing_station(to_limb_profile(dims, template, "check"))
    if radii_increase:
        raise MeasurementError(
            "inconsistent_profile",
            f"These values make the limb wider toward the distal end at {radii_increase}. "
            "Lower the distal values or raise the proximal ones.",
        )

    warnings = []
    if dims["distal_shape"] != "template":
        warnings.append("distal_shape is recorded but not applied to the demo limb yet.")
    if "side" in edited:
        warnings.append("side is recorded; the demo limb's oval section is the same on both sides.")
    if dims["posture"] != "supine":
        warnings.append("posture is recorded; the limb is not corrected for posture.")
    return dims, edited, warnings


def _increasing_station(profile: dict) -> str | None:
    sections = profile["sections"]
    for a, b in zip(sections, sections[1:]):
        if b["circumference_mm"] > a["circumference_mm"] + 1e-6:
            return f"{b['id']} ({b['circumference_mm']:.1f} mm after {a['id']} {a['circumference_mm']:.1f} mm)"
    return None


# ---------------------------------------------------------------------------
# Building the profile
# ---------------------------------------------------------------------------


def to_limb_profile(dims: dict, template: dict, model_id: str) -> dict:
    """A limb profile for tools/cad/generate_limb.py: the standard limb, resized to dims."""
    length = float(dims["length_mm"])
    axial = float(template["total_length_mm"]) / length  # new z -> standard z

    def standard_at(z: float) -> float:
        return template_circumference(template, z * axial)

    p_z, mid_z, d_z = STATION_OFFSET_MM, length / 2, length - STATION_OFFSET_MM
    knots = [(p_z, dims["proximal_circumference_mm"] / standard_at(p_z))]
    if dims.get("mid_circumference_mm") is not None:
        knots.append((mid_z, dims["mid_circumference_mm"] / standard_at(mid_z)))
    knots.append((d_z, dims["distal_circumference_mm"] / standard_at(d_z)))

    def scale(z: float) -> float:
        if z <= knots[0][0]:
            return knots[0][1]
        for (za, sa), (zb, sb) in zip(knots, knots[1:]):
            if za <= z <= zb:
                return sa + (sb - sa) * (z - za) / (zb - za)
        return knots[-1][1]

    cap_start = CAP_START_FRACTION * length
    station_z = [("proximal", 0.0), ("P", p_z)]
    if p_z + 1 < 0.25 * length < mid_z - 1:
        station_z.append(("q25", 0.25 * length))
    station_z.append(("q50", mid_z))
    if mid_z + 1 < 0.75 * length < d_z - 1:
        station_z.append(("q75", 0.75 * length))
    station_z += [("D", d_z), ("distal_reference", cap_start)]

    if dims.get("ap_mm") is not None:
        ratio = dims["ap_mm"] / dims["ml_mm"]
    else:
        ratio = template["sections"][0]["ap_over_ml"]

    profile = copy.deepcopy(template)
    profile["model_id"] = model_id
    profile["model_version"] = "1.0.0+dimensions"
    profile["total_length_mm"] = length
    profile["sections"] = [
        {
            "id": sid,
            "length_fraction": z / length,
            "z_mm": z,
            "circumference_mm": round(standard_at(z) * scale(z), 4),
            "ap_over_ml": ratio,
        }
        for sid, z in station_z
    ]
    profile["distal_cap"] = {
        **template["distal_cap"],
        "reference_section_id": "distal_reference",
        "start_z_mm": cap_start,
        "tip_z_mm": length,
        "length_mm": length - cap_start,
    }
    profile["dimensions"] = {k: v for k, v in dims.items() if v is not None}
    return profile
