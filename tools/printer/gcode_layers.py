"""Layer index of a sliced G-code file, for the printer page's live layer view.

Not a model tool. The web API uses it to turn OctoPrint's reported file
position (progress.filepos, the bytes of the file the printer has used) into
the layer being printed. That is a lookup in the file OctoPrint was sent, not
an estimate.

PrusaSlicer marks each layer with ";LAYER_CHANGE" and ";Z:<height>" and each
extrusion section with ";TYPE:<role>". Only the outer wall is kept for
drawing: it shows the part's shape at a fraction of the file's size. Where the
wall overhangs (a socket's rounded end, printed closed end down) PrusaSlicer
calls it "Overhang perimeter". Support-only layers have no wall to draw.
"""

from __future__ import annotations

import bisect
import re
from pathlib import Path

MAX_POINTS = 200_000  # across all layers; longer files are thinned evenly
OUTER_WALL = {b";TYPE:External perimeter", b";TYPE:Overhang perimeter"}
_MOVE = re.compile(rb"^G[01]\s")
_AXIS = re.compile(rb"([XYZEF])(-?\d*\.?\d+)")

_cache: dict[tuple[str, float], dict] = {}


def index_layers(path: Path) -> dict:
    """{"layers": [{"z", "offset", "paths"}]} for a G-code file, cached by path and mtime.

    offset is the byte position of the layer's ";LAYER_CHANGE" line. paths is a list of
    polylines, each a flat [x0, y0, x1, y1, ...] list in mm (printer bed frame).
    """
    key = (str(path), path.stat().st_mtime)
    if key not in _cache:
        _cache.clear()  # one job is shown at a time
        _cache[key] = _parse(path.read_bytes())
    return _cache[key]


def _parse(data: bytes) -> dict:
    layers: list[dict] = []
    x = y = e = 0.0
    absolute_xy = absolute_e = True
    outer_wall = False
    line_path: list[float] | None = None
    offset = 0
    pending_layer: int | None = None  # offset of a ;LAYER_CHANGE waiting for its ;Z:

    def close_path():
        nonlocal line_path
        if line_path and len(line_path) >= 4 and layers:
            layers[-1]["paths"].append(line_path)
        line_path = None

    for raw in data.splitlines(keepends=True):
        line = raw.strip()
        start, offset = offset, offset + len(raw)
        if line.startswith(b";"):
            if line == b";LAYER_CHANGE":
                close_path()
                pending_layer = start
            elif line.startswith(b";Z:") and pending_layer is not None:
                layers.append({"z": round(float(line[3:]), 3), "offset": pending_layer, "paths": []})
                pending_layer = None
            elif line.startswith(b";TYPE:"):
                close_path()
                outer_wall = line in OUTER_WALL
            continue
        code = line.split(b";", 1)[0].strip()
        if code in (b"G90", b"G91"):
            absolute_xy = code == b"G90"
        elif code in (b"M82", b"M83"):
            absolute_e = code == b"M82"
        elif code.startswith(b"G92"):
            for axis, value in _AXIS.findall(code):
                if axis == b"E":
                    e = float(value)
        elif _MOVE.match(code):
            axes = {a: float(v) for a, v in _AXIS.findall(code)}
            nx = axes.get(b"X", x if absolute_xy else 0.0) + (0.0 if absolute_xy else x)
            ny = axes.get(b"Y", y if absolute_xy else 0.0) + (0.0 if absolute_xy else y)
            extruding = False
            if b"E" in axes:
                extruding = axes[b"E"] > e if absolute_e else axes[b"E"] > 0
                e = axes[b"E"] if absolute_e else e + axes[b"E"]
            moved = (nx, ny) != (x, y)
            if extruding and moved and outer_wall:
                if line_path is None:
                    line_path = [round(x, 1), round(y, 1)]
                line_path += [round(nx, 1), round(ny, 1)]
            elif moved:
                close_path()
            x, y = nx, ny
    close_path()
    _thin(layers)
    return {"layers": layers}


def _thin(layers: list[dict]) -> None:
    """Keep every n-th point (and each path's last) so the drawing stays small."""
    total = sum(len(p) // 2 for layer in layers for p in layer["paths"])
    step = -(-total // MAX_POINTS)  # ceiling division
    if step <= 1:
        return
    for layer in layers:
        thinned = []
        for path in layer["paths"]:
            points = [path[i:i + 2] for i in range(0, len(path), 2)]
            kept = points[::step] + ([points[-1]] if (len(points) - 1) % step else [])
            if len(kept) >= 2:
                thinned.append([c for point in kept for c in point])
        layer["paths"] = thinned


def layer_at(index: dict, filepos: int | None) -> int | None:
    """The 1-based number of the layer containing byte filepos, or None before the first layer."""
    if filepos is None:
        return None
    offsets = [layer["offset"] for layer in index["layers"]]
    position = bisect.bisect_right(offsets, filepos)
    return position or None
