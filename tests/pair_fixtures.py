"""Cylinder and ellipse fixtures for pair tests. These are not the limb models."""

from __future__ import annotations

import json
import math
from pathlib import Path

import cadquery as cq

FRAME = {
    "longitudinal_axis": "Z",
    "ml_axis": "X",
    "ap_axis": "Y",
    "distal_direction": "+Z",
    "proximal_plane_z_mm": 0,
}


def _profile(model_id: str, version: str, *, socket: bool, reference_id: str, reference_version: str, hash_value: str | None, radius: float, height: float) -> dict:
    shared = {
        "model_version": version,
        "units": "mm",
        "clinical_use": False,
        "coordinate_frame": FRAME,
    }
    if socket:
        shared.update(
            {
                "socket_model_id": model_id,
                "reference_limb_model_id": reference_id,
                "reference_limb_version": reference_version,
            }
        )
        if hash_value is not None:
            shared["reference_limb_geometry_hash"] = hash_value
        return shared
    shared.update(
        {
            "model_id": model_id,
            "total_length_mm": height,
            "sections": [
                {
                    "id": "q50",
                    "z_mm": height / 2.0,
                    "circumference_mm": 2.0 * math.pi * radius,
                }
            ],
        }
    )
    return shared


def export_pair(
    directory: Path,
    *,
    limb,
    socket,
    limb_radius: float,
    height: float = 40.0,
    limb_id: str = "cylinder-limb",
    limb_version: str = "1.0.0",
    socket_id: str = "cylinder-socket",
    socket_version: str = "1.0.0",
    reference_id: str = "cylinder-limb",
    reference_version: str = "1.0.0",
    recorded_hash: str | None = None,
    units: str = "mm",
) -> dict:
    """Write two STEP files and the profiles align_limb_socket can read."""
    directory.mkdir(parents=True, exist_ok=True)
    limb_step = directory / "limb.step"
    socket_step = directory / "socket.step"
    limb_profile_path = directory / "limb.json"
    socket_profile_path = directory / "socket.json"
    cq.exporters.export(limb, str(limb_step))
    cq.exporters.export(socket, str(socket_step))
    limb_profile = _profile(
        limb_id,
        limb_version,
        socket=False,
        reference_id=reference_id,
        reference_version=reference_version,
        hash_value=None,
        radius=limb_radius,
        height=height,
    )
    socket_profile = _profile(
        socket_id,
        socket_version,
        socket=True,
        reference_id=reference_id,
        reference_version=reference_version,
        hash_value=recorded_hash,
        radius=limb_radius,
        height=height,
    )
    limb_profile["units"] = units
    socket_profile["units"] = units
    limb_profile_path.write_text(json.dumps(limb_profile))
    socket_profile_path.write_text(json.dumps(socket_profile))
    return {
        "limb_step": str(limb_step),
        "limb_profile_path": str(limb_profile_path),
        "socket_step": str(socket_step),
        "socket_profile_path": str(socket_profile_path),
        "alignment_mode": "shared_frame",
    }


def tube(outer_radius: float, inner_radius: float, height: float = 40.0):
    outer = cq.Workplane("XY").circle(outer_radius).extrude(height)
    inner = cq.Workplane("XY").circle(inner_radius).extrude(height)
    return outer.cut(inner)


def cylinder(radius: float, height: float = 40.0, center_xy: tuple[float, float] = (0.0, 0.0)):
    return cq.Workplane("XY").center(*center_xy).circle(radius).extrude(height)


def elliptic_tube(outer_xy: tuple[float, float], inner_xy: tuple[float, float], height: float = 40.0):
    outer = cq.Workplane("XY").ellipse(*outer_xy).extrude(height)
    inner = cq.Workplane("XY").ellipse(*inner_xy).extrude(height)
    return outer.cut(inner)
