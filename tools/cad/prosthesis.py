"""Parametric parts below the socket: socket adapter, pylon and foot.

A transtibial prosthesis stacks, top to bottom:

    socket            (tools/cad, Yutian's) opening at z = 0, closed end at z = depth
    socket adapter    plate under the socket, pyramid connector pointing down
    pylon             tube with a receiver collar at each end
    foot              sole on the floor, pyramid connector pointing up

The pyramid connector here is a demonstration shape (a square, tapered plug and a
matching square pocket), not an industry-standard dimension. Every part is a
non-wearable demonstration model.

Each builder takes a parameter dict and returns one CadQuery solid in its print
orientation: Z up, flat face on the bed at z = 0. assemble() places the parts in
the socket's frame (+Z toward the floor) for viewing and checks.
"""

from __future__ import annotations

import math

import cadquery as cq

# Connector taper: the pyramid's top is this fraction of its base.
PYRAMID_TOP_RATIO = 0.7
# Extra room in a receiver pocket so a printed pyramid fits.
POCKET_CLEARANCE_MM = 0.4

# name -> (default, minimum, maximum), all in mm
PARAMETERS: dict[str, dict[str, tuple[float, float, float]]] = {
    "adapter": {
        "plate_diameter_mm": (60.0, 40.0, 90.0),
        "plate_thickness_mm": (8.0, 4.0, 15.0),
        "bolt_circle_mm": (40.0, 20.0, 76.0),
        "bolt_hole_diameter_mm": (5.0, 3.0, 8.0),
        "connector_size_mm": (24.0, 16.0, 30.0),
        "connector_height_mm": (10.0, 6.0, 15.0),
    },
    "pylon": {
        "length_mm": (150.0, 60.0, 400.0),
        "outer_diameter_mm": (30.0, 20.0, 40.0),
        "wall_thickness_mm": (3.0, 1.5, 8.0),
        "collar_diameter_mm": (44.0, 36.0, 60.0),
        "collar_height_mm": (18.0, 12.0, 30.0),
        "connector_size_mm": (24.0, 16.0, 30.0),
        "connector_height_mm": (10.0, 6.0, 15.0),
    },
    "foot": {
        "length_mm": (170.0, 120.0, 300.0),
        "width_mm": (70.0, 50.0, 110.0),
        "heel_height_mm": (30.0, 15.0, 60.0),
        "toe_thickness_mm": (10.0, 6.0, 25.0),
        "connector_size_mm": (24.0, 16.0, 30.0),
        "connector_height_mm": (10.0, 6.0, 15.0),
    },
}
COMPONENT_TYPES = list(PARAMETERS)


def defaults(part_type: str) -> dict:
    return {name: spec[0] for name, spec in PARAMETERS[part_type].items()}


def check_parameters(part_type: str, params: dict) -> None:
    """Raise ValueError naming the first parameter that is unknown, missing or out of range,
    or a combination of values that cannot be built."""
    specs = PARAMETERS[part_type]
    for name in params:
        if name not in specs:
            raise ValueError(f"{name} is not a {part_type} parameter. Known: {', '.join(specs)}")
    for name, (_, low, high) in specs.items():
        value = params.get(name)
        if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value):
            raise ValueError(f"{name} must be a number")
        if not low <= value <= high:
            raise ValueError(f"{name} = {value} is outside {low}-{high} mm")

    p = params
    if part_type == "adapter":
        if p["bolt_circle_mm"] + p["bolt_hole_diameter_mm"] + 4 > p["plate_diameter_mm"]:
            raise ValueError("bolt_circle_mm + bolt_hole_diameter_mm leaves less than 2 mm of plate at the edge")
        # Holes sit on the X and Y axes, where the square connector is size/2 wide.
        if p["connector_size_mm"] + p["bolt_hole_diameter_mm"] + 2 > p["bolt_circle_mm"]:
            raise ValueError("the connector overlaps the bolt holes; use a larger bolt_circle_mm or a smaller connector")
    if part_type == "pylon":
        if p["outer_diameter_mm"] - 2 * p["wall_thickness_mm"] < 6:
            raise ValueError("wall_thickness_mm leaves a bore under 6 mm")
        if p["connector_size_mm"] * math.sqrt(2) + 4 > p["collar_diameter_mm"]:
            raise ValueError("the connector pocket does not fit inside the collar; use a larger collar_diameter_mm")
        if p["collar_diameter_mm"] < p["outer_diameter_mm"]:
            raise ValueError("collar_diameter_mm must be at least outer_diameter_mm")
        if 2 * p["collar_height_mm"] + 10 > p["length_mm"]:
            raise ValueError("length_mm must exceed both collars plus 10 mm of tube")
        if p["connector_height_mm"] + 2 > p["collar_height_mm"]:
            raise ValueError("connector_height_mm must be at least 2 mm less than collar_height_mm")
    if part_type == "foot":
        if p["toe_thickness_mm"] >= p["heel_height_mm"]:
            raise ValueError("toe_thickness_mm must be less than heel_height_mm")
        if p["connector_size_mm"] * math.sqrt(2) + 8 > p["width_mm"]:
            raise ValueError("the ankle connector is wider than the foot; use a larger width_mm")


# ---------------------------------------------------------------------------
# Shared shapes
# ---------------------------------------------------------------------------


def pyramid(size: float, height: float) -> cq.Workplane:
    """Square tapered plug, base on z = 0, pointing +Z."""
    return (
        cq.Workplane("XY")
        .rect(size, size)
        .workplane(offset=height)
        .rect(size * PYRAMID_TOP_RATIO, size * PYRAMID_TOP_RATIO)
        .loft(combine=True)
    )


def pocket(size: float, height: float) -> cq.Workplane:
    """The matching receiver cavity: the pyramid plus clearance, 0.5 mm deeper."""
    return pyramid(size + POCKET_CLEARANCE_MM, height + 0.5)


# ---------------------------------------------------------------------------
# Builders (print orientation: Z up, base on the bed)
# ---------------------------------------------------------------------------


def build_adapter(p: dict) -> cq.Shape:
    """Plate with four bolt holes and a pyramid on top.

    In the assembly it is flipped: the plate sits under the socket and the pyramid
    points down into the pylon.
    """
    check_parameters("adapter", p)
    t, d = p["plate_thickness_mm"], p["plate_diameter_mm"]
    plate = cq.Workplane("XY").circle(d / 2).extrude(t).edges(">Z or <Z").chamfer(min(1.0, t / 4))
    r = p["bolt_circle_mm"] / 2
    holes = (
        cq.Workplane("XY")
        .pushPoints([(r, 0), (0, r), (-r, 0), (0, -r)])
        .circle(p["bolt_hole_diameter_mm"] / 2)
        .extrude(t)
    )
    plug = pyramid(p["connector_size_mm"], p["connector_height_mm"]).translate((0, 0, t))
    return plate.cut(holes).union(plug).val()


def build_pylon(p: dict) -> cq.Shape:
    """Tube with a receiver collar at each end. Built standing; length_mm is end to end."""
    check_parameters("pylon", p)
    length, collar_h = p["length_mm"], p["collar_height_mm"]
    outer, bore = p["outer_diameter_mm"] / 2, p["outer_diameter_mm"] / 2 - p["wall_thickness_mm"]
    tube = (
        cq.Workplane("XY")
        .circle(outer)
        .circle(bore)
        .extrude(length - 2 * collar_h)
        .translate((0, 0, collar_h))
    )
    collar = cq.Workplane("XY").circle(p["collar_diameter_mm"] / 2).extrude(collar_h).edges(">Z or <Z").chamfer(1.0)
    size, height = p["connector_size_mm"], p["connector_height_mm"]
    # Each collar's pocket is widest at its open end face.
    # Bottom collar opens at z = 0; the top collar is the same collar mirrored to open at z = length.
    bottom = collar.cut(pocket(size, height))
    top = bottom.mirror("XY").translate((0, 0, length))
    return tube.union(bottom).union(top).val()


def _foot_outline(length: float, width: float) -> list[tuple[float, float]]:
    """Closed sole outline: heel at x = 0, toes at x = length, symmetric about y = 0."""
    half = width / 2
    upper = [
        (0.03, 0.62), (0.12, 0.80), (0.28, 0.74), (0.45, 0.70),
        (0.62, 0.90), (0.78, 1.00), (0.90, 0.88), (0.97, 0.55),
    ]
    pts = [(0.0, 0.0)] + [(x * length, y * half) for x, y in upper] + [(length, 0.0)]
    pts += [(x * length, -y * half) for x, y in reversed(upper)]
    return pts


def build_foot(p: dict) -> cq.Shape:
    """Foot-shaped sole, thick at the heel and thin at the toe, with an ankle boss and pyramid.

    The ankle sits at 30% of the length from the heel.
    """
    check_parameters("foot", p)
    length, width = p["length_mm"], p["width_mm"]
    heel, toe = p["heel_height_mm"], p["toe_thickness_mm"]
    sole = cq.Workplane("XY").spline(_foot_outline(length, width), periodic=True).close().extrude(heel)
    # Cut the top down from heel height at the heel to toe thickness at the toe.
    slope = (heel - toe) / length
    cutter = (
        cq.Workplane("XZ")
        .polyline([(-20, heel + 20 * slope), (length + 20, toe - 20 * slope), (length + 20, heel + 100), (-20, heel + 100)])
        .close()
        .extrude(width, both=True)
    )
    foot = sole.cut(cutter)
    ankle_x = 0.30 * length
    top_at_ankle = heel - slope * ankle_x
    size, height = p["connector_size_mm"], p["connector_height_mm"]
    boss_r = size * 0.75
    boss = cq.Workplane("XY").circle(boss_r).extrude(top_at_ankle + 8).translate((ankle_x, 0, 0))
    plug = pyramid(size, height).translate((ankle_x, 0, top_at_ankle + 8))
    return foot.union(boss).union(plug).val()


BUILDERS = {"adapter": build_adapter, "pylon": build_pylon, "foot": build_foot}


def build(part_type: str, params: dict) -> cq.Shape:
    return BUILDERS[part_type](params)


# ---------------------------------------------------------------------------
# Assembly in the socket frame (+Z toward the floor)
# ---------------------------------------------------------------------------


def _flip(shape: cq.Shape) -> cq.Shape:
    """Turn a part over (180 degrees about X): its local +Z then points toward the socket.

    In the socket frame +Z points toward the floor, so a part built Z-up whose top
    should face the floor (adapter pyramid, pylon) is placed unflipped. The foot's
    sole must face the floor and its pyramid the socket, so only the foot is flipped.
    """
    return shape.rotate((0, 0, 0), (1, 0, 0), 180)


def assemble(socket_shape: cq.Shape, socket_depth_mm: float, parts: dict[str, tuple[cq.Shape, dict]]) -> dict:
    """Place adapter, pylon and foot under the socket.

    parts maps "adapter", "pylon", "foot" to (shape, params). Raises ValueError if
    the connectors do not match. Returns the compound and the key heights.
    """
    adapter_p, pylon_p, foot_p = parts["adapter"][1], parts["pylon"][1], parts["foot"][1]
    for upper, lower in (("adapter", "pylon"), ("pylon", "foot")):
        a, b = parts[upper][1]["connector_size_mm"], parts[lower][1]["connector_size_mm"]
        ha, hb = parts[upper][1]["connector_height_mm"], parts[lower][1]["connector_height_mm"]
        if a != b or ha != hb:
            raise ValueError(
                f"connector mismatch: {upper} connector {a} x {ha} mm, {lower} connector {b} x {hb} mm; "
                "they must be equal"
            )

    # Adapter: plate top against the socket's closed end, pyramid pointing down.
    plate_top = socket_depth_mm
    adapter = parts["adapter"][0].translate((0, 0, plate_top))
    plate_bottom = plate_top + adapter_p["plate_thickness_mm"]
    # Pylon: its upper collar receives the adapter pyramid.
    pylon_top = plate_bottom
    pylon = parts["pylon"][0].translate((0, 0, pylon_top))
    pylon_bottom = pylon_top + pylon_p["length_mm"]
    # Foot: its pyramid points up into the pylon's bottom collar; the sole is the floor.
    heel, toe, length = foot_p["heel_height_mm"], foot_p["toe_thickness_mm"], foot_p["length_mm"]
    ankle_x = 0.30 * length
    pyramid_tip = heel - (heel - toe) / length * ankle_x + 8 + foot_p["connector_height_mm"]
    floor = pylon_bottom - foot_p["connector_height_mm"] + pyramid_tip
    foot = _flip(parts["foot"][0]).translate((-ankle_x, 0, floor))

    compound = cq.Compound.makeCompound([socket_shape, adapter, pylon, foot])
    return {
        "compound": compound,
        "opening_to_floor_mm": round(floor, 2),
        "socket_end_to_floor_mm": round(floor - socket_depth_mm, 2),
        "pylon_length_mm": pylon_p["length_mm"],
    }
