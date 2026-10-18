"""Features cut into a finished socket: for now, engraved labels.

The socket library builds a socket from its parameters and knows nothing about
features, so they are a separate layer:

- A socket revision lists its features in meta.json and keeps the library's own
  solid as base.step. part.step is that base with every feature cut into it.
- Rebuilding a socket (modify_socket, fit_socket_to_limb) re-cuts the parent's
  features into the new base, so an edit never drops a label.
- validate_part checks base.step with the library and the cut solid here.

Socket frame (data/profiles/standard_socket.json): the opening is at z = 0, the
closed end at +Z, +Y is the anterior (front) label and X the two sides.
"""

from __future__ import annotations

import re

import cadquery as cq


# Face name -> rotation about Z that turns the front (+Y) onto that face.
FACES = {"front": 0.0, "back": 180.0, "left": 90.0, "right": -90.0}

LABEL_TEXT = re.compile(r"[A-Za-z0-9 .\-_#/]{1,20}")
TEXT_HEIGHT_MM = (4.0, 20.0)
LABEL_DEPTH_MM = (0.4, 1.5)
MAX_LABEL_WIDTH_MM = 60.0
WALL_LEFT_MM = 2.5  # wall that must remain under an engraving
EDGE_MARGIN_MM = 5.0  # clear space between a feature and the brim or the rounded end
END_ROUNDING_MM = 20.0  # above the end wall, the side wall curves into the closed end
MAX_FEATURES = 6


class FeatureError(ValueError):
    """A feature that cannot be cut, with the code and range the model can act on."""

    def __init__(self, code: str, reason: str, valid_range=None):
        super().__init__(reason)
        self.code = code
        self.reason = reason
        self.valid_range = valid_range


def side_wall_range(profile: dict, half_height_mm: float) -> tuple[float, float]:
    """Heights (mm below the opening) where a feature of this half-height sits on the straight wall."""
    low = float(profile["brim_flare_length_mm"]) + EDGE_MARGIN_MM + half_height_mm
    high = (
        float(profile["socket_depth_mm"]) - float(profile["distal_wall_thickness_mm"])
        - END_ROUNDING_MM - EDGE_MARGIN_MM - half_height_mm
    )
    return round(low, 1), round(high, 1)


def default_height(profile: dict) -> float:
    low, high = side_wall_range(profile, 0.0)
    return round((low + high) / 2, 1)


def _check_height(profile: dict, height_mm: float, half_height_mm: float, what: str) -> None:
    low, high = side_wall_range(profile, half_height_mm)
    if low > high:
        raise FeatureError("no_room", f"This socket has no straight wall tall enough for {what}.")
    if not low <= height_mm <= high:
        raise FeatureError(
            "out_of_range",
            f"{what} at {height_mm:g} mm below the opening would reach the brim or the rounded end; "
            f"its centre must be {low:g} to {high:g} mm below the opening.",
            {"height_mm": [low, high]},
        )


def _text_solid(text: str, text_height_mm: float):
    """Text on the front face: reads left to right seen from the front, upright toward the opening."""
    plane = cq.Plane(origin=(0, 0, 0), xDir=(1, 0, 0), normal=(0, 1, 0))  # up on the page is -Z
    return cq.Workplane(plane).text(text, text_height_mm, 200.0, halign="center", valign="center").val()


def check_label(params: dict, profile: dict) -> None:
    text = params["text"]
    if not LABEL_TEXT.fullmatch(text):
        raise FeatureError(
            "invalid_text",
            "Label text must be 1 to 20 characters: letters, digits, spaces and . - _ # /.",
        )
    if params["face"] not in FACES:
        raise FeatureError("invalid_face", f"Unknown face {params['face']!r}.", list(FACES))
    size = params["text_height_mm"]
    if not TEXT_HEIGHT_MM[0] <= size <= TEXT_HEIGHT_MM[1]:
        raise FeatureError("out_of_range", f"Text height must be {TEXT_HEIGHT_MM[0]:g} to {TEXT_HEIGHT_MM[1]:g} mm.",
                           {"text_height_mm": list(TEXT_HEIGHT_MM)})
    wall = float(profile["nominal_wall_thickness_mm"])
    deepest = round(min(LABEL_DEPTH_MM[1], wall - WALL_LEFT_MM), 2)
    if deepest < LABEL_DEPTH_MM[0]:
        raise FeatureError("wall_too_thin", f"The {wall:g} mm wall is too thin to engrave and keep {WALL_LEFT_MM:g} mm.")
    if not LABEL_DEPTH_MM[0] <= params["depth_mm"] <= deepest:
        raise FeatureError(
            "out_of_range",
            f"Engraving depth must be {LABEL_DEPTH_MM[0]:g} to {deepest:g} mm so at least "
            f"{WALL_LEFT_MM:g} mm of the {wall:g} mm wall is left.",
            {"depth_mm": [LABEL_DEPTH_MM[0], deepest]},
        )
    width = _text_solid(text, size).BoundingBox().xlen
    if width > MAX_LABEL_WIDTH_MM:
        raise FeatureError(
            "too_wide",
            f"'{text}' is {width:.0f} mm wide at {size:g} mm text height; a label can be at most "
            f"{MAX_LABEL_WIDTH_MM:g} mm wide. Use shorter text or a smaller text height.",
            {"width_mm": [0, MAX_LABEL_WIDTH_MM]},
        )
    _check_height(profile, params["height_mm"], size / 2, "the label")


def check(feature: dict, profile: dict) -> None:
    if feature["type"] != "label":
        raise FeatureError("unsupported_feature", f"Unknown feature type {feature['type']!r}.")
    check_label(feature, profile)


def _outer_half_widths(base, z: float) -> tuple[float, float]:
    """The outer wall's ML (X) and AP (Y) half-widths at height z, from thin slices of the solid."""
    along_x = base.intersect(cq.Solid.makeBox(400, 0.2, 0.2, cq.Vector(-200, -0.1, z - 0.1))).BoundingBox()
    along_y = base.intersect(cq.Solid.makeBox(0.2, 400, 0.2, cq.Vector(-0.1, -200, z - 0.1))).BoundingBox()
    return max(abs(along_x.xmin), along_x.xmax), max(abs(along_y.ymin), along_y.ymax)


def _depth_envelope(base, z_low: float, z_high: float, depth_mm: float):
    """A solid filling the socket out to depth_mm inside its outer wall, from z_low to z_high.

    Lofted through the outer ellipse measured at three heights, each shrunk by depth_mm.
    Cutting text minus this solid removes only the outer depth_mm of the wall. (An earlier
    version subtracted a thinner library socket; its inner surface coincides with the
    socket's, and OpenCascade's boolean then fails quietly on some sockets.)
    """
    heights = [z_low, (z_low + z_high) / 2, z_high]
    sketch = cq.Workplane("XY", origin=(0, 0, heights[0]))
    for index, z in enumerate(heights):
        if index:
            sketch = sketch.workplane(offset=z - heights[index - 1])
        ml, ap = _outer_half_widths(base, z)
        sketch = sketch.ellipse(ml - depth_mm, ap - depth_mm)
    return sketch.loft(ruled=False).val()


def _cutter(feature: dict, socket_profile: dict, limb_profile: dict, base):
    if feature["type"] == "label":
        half = feature["text_height_mm"] / 2
        z = feature["height_mm"]
        text = _text_solid(feature["text"], feature["text_height_mm"]).translate(cq.Vector(0, 0, z))
        text = text.rotate(cq.Vector(0, 0, 0), cq.Vector(0, 0, 1), FACES[feature["face"]])
        # The envelope runs past the text so no faces of the two solids coincide.
        return text.cut(_depth_envelope(base, z - half - 3.0, z + half + 3.0, feature["depth_mm"]))
    raise FeatureError("unsupported_feature", f"Unknown feature type {feature['type']!r}.")


def apply(base, socket_profile: dict, limb_profile: dict, features: list[dict]):
    """Cut every feature into the base socket. Returns (shape, removed_mm3 per feature).

    Raises FeatureError when a feature is out of range for this socket or cuts nothing.
    """
    if len(features) > MAX_FEATURES:
        raise FeatureError("too_many_features", f"A socket can have at most {MAX_FEATURES} features.")
    shape, removed = base, []
    for index, feature in enumerate(features, 1):
        check(feature, socket_profile)
        try:
            cut = shape.cut(_cutter(feature, socket_profile, limb_profile, shape))
        except Exception as exc:  # OpenCascade failures arrive as several exception types
            raise FeatureError("geometry_failed", f"Feature {index} ({describe(feature)}) could not be cut: {exc}") from exc
        volume = shape.Volume() - cut.Volume()
        if volume <= 0.01 or not cut.isValid() or len(cut.Solids()) != 1:
            raise FeatureError(
                "geometry_failed",
                f"Feature {index} ({describe(feature)}) did not cut cleanly into the wall "
                f"(removed {volume:.2f} mm3, {len(cut.Solids())} solid(s)).",
            )
        shape = cut
        removed.append(round(volume, 2))
    return shape, removed


def checks(final, base, features: list[dict], removed: list[float]) -> dict:
    """The validation category for a socket's features, shaped like the library's categories."""
    rows = [
        {"name": "valid_solid", "passed": bool(final.isValid()), "detail": "the cut socket is a valid solid"},
        {"name": "one_solid", "passed": len(final.Solids()) == 1, "detail": f"{len(final.Solids())} solid(s) after the cuts"},
    ]
    for feature, volume in zip(features, removed):
        rows.append({"name": describe(feature), "passed": volume > 0.01, "detail": f"removed {volume:g} mm3"})
    return {"passed": all(r["passed"] for r in rows), "checks": rows}


def describe(feature: dict) -> str:
    if feature["type"] == "label":
        return f"label '{feature['text']}' on the {feature['face']}, {feature['depth_mm']:g} mm deep"
    return feature["type"]
