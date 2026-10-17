"""Place a limb and a socket in one frame with an explicit rigid motion.

The default is the shared design frame: both solids are already built with
X medial-lateral, Y anterior-posterior, and +Z distal. The opening plane and
the limb proximal plane are z = 0. This function does not search for a best
fit and does not deform either solid.

A requested motion is applied to a copy of the limb. The formula is

    p_socket = R @ p_limb + translation

R is an active 3x3 rotation matrix. The translation is millimetres in the
socket frame. Reflections, scales, and shears are rejected.

Original STEP files are not written. A transformed limb copy is written only
when ``output_dir`` is set.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
from OCP.BRepBuilderAPI import BRepBuilderAPI_Copy, BRepBuilderAPI_Transform
from OCP.BRepGProp import BRepGProp
from OCP.GProp import GProp_GProps
from OCP.gp import gp_Trsf

from tools.cad.generate_limb import (
    PROFILE_PATH,
    REFERENCE_DIR,
    REFERENCE_STEP,
    SOCKET_PROFILE_PATH,
    SOCKET_STEP,
    load_profile,
)
from tools.cad.generate_socket import load_socket_profile
from tools.cad.measure_limb import StepLoadError, load_step_shape, occ_shape, signed_volume_mm3
from tools.cad.modify_limb import _finite, value_within_tolerance

_VOLUME_TOLERANCE_MM3 = 1.0
_AREA_RELATIVE = 1e-4


def _failure(code: str, message: str, **details: Any) -> dict:
    error: dict[str, Any] = {"code": code, "message": message}
    if details:
        error["details"] = details
    return {"ok": False, "error": error, "clinical_use": False}


def _surface_area_mm2(shape) -> float:
    props = GProp_GProps()
    BRepGProp.SurfaceProperties_s(occ_shape(shape), props)
    return float(props.Mass())


def _frame_problem(profile: dict, name: str) -> str | None:
    if profile.get("units") != "mm":
        return f"{name} units are {profile.get('units')!r}, not mm"
    frame = profile.get("coordinate_frame")
    if not isinstance(frame, dict):
        return f"{name} has no coordinate_frame"
    expected = {
        "longitudinal_axis": "Z",
        "ml_axis": "X",
        "ap_axis": "Y",
        "distal_direction": "+Z",
        "proximal_plane_z_mm": 0,
    }
    for key, value in expected.items():
        if frame.get(key) != value:
            return f"{name} coordinate_frame.{key} is {frame.get(key)!r}, expected {value!r}"
    return None


def _matrix(value) -> tuple[np.ndarray | None, dict | None]:
    if value is None:
        return np.eye(3), None
    if not isinstance(value, list) or len(value) != 3 or not all(isinstance(row, list) and len(row) == 3 for row in value):
        return None, _failure("invalid_rotation", "rotation_matrix must be a 3x3 list")
    numbers = []
    for row_index, row in enumerate(value):
        parsed = []
        for column_index, item in enumerate(row):
            number, error = _finite(item, f"rotation_matrix[{row_index}][{column_index}]")
            if error:
                return None, error
            parsed.append(number)
        numbers.append(parsed)
    matrix = np.array(numbers, dtype=float)
    if not np.isfinite(matrix).all():
        return None, _failure("non_finite", "rotation_matrix must be finite")
    product = matrix.T @ matrix
    if float(np.max(np.abs(product - np.eye(3)))) > 1e-6:
        return None, _failure("invalid_rotation", "rotation_matrix is not orthonormal")
    determinant = float(np.linalg.det(matrix))
    if abs(determinant - 1.0) > 1e-6:
        return None, _failure(
            "invalid_rotation",
            "rotation_matrix must have determinant 1. Reflections and scales are rejected.",
            determinant=determinant,
        )
    return matrix, None


def _translation(value) -> tuple[np.ndarray | None, dict | None]:
    if value is None:
        return np.zeros(3), None
    if not isinstance(value, list) or len(value) != 3:
        return None, _failure("invalid_value", "translation_mm must be a list of three numbers")
    numbers = []
    for index, item in enumerate(value):
        number, error = _finite(item, f"translation_mm[{index}]")
        if error:
            return None, error
        numbers.append(number)
    return np.array(numbers, dtype=float), None


def _is_identity(matrix: np.ndarray, translation: np.ndarray) -> bool:
    return float(np.max(np.abs(matrix - np.eye(3)))) <= 1e-9 and float(np.max(np.abs(translation))) <= 1e-9


def parse_transform(payload: dict | None, mode: str) -> tuple[dict | None, dict | None]:
    """Return the rigid motion, or an error dict.

    ``shared_frame`` allows only the identity. ``explicit`` requires a matrix
    and a translation. Euler angles and scale factors are rejected.
    """
    if mode not in {"shared_frame", "explicit"}:
        return None, _failure("unsupported_alignment", f"Unsupported alignment_mode {mode!r}")
    if payload is None:
        payload = {}
    if not isinstance(payload, dict):
        return None, _failure("invalid_value", "transformation must be an object")
    if "scale" in payload or "shear" in payload:
        return None, _failure("unsupported_transform", "Scaling and shearing are not rigid motions")
    if "euler_deg" in payload or "euler_rad" in payload:
        return None, _failure(
            "unsupported_transform",
            "Pass rotation_matrix. Euler angles are not accepted, so the axis order cannot be guessed.",
        )
    matrix, error = _matrix(payload.get("rotation_matrix"))
    if error:
        return None, error
    translation, error = _translation(payload.get("translation_mm"))
    if error:
        return None, error
    assert matrix is not None and translation is not None
    identity = _is_identity(matrix, translation)
    if mode == "shared_frame" and not identity:
        return None, _failure(
            "invalid_value",
            "shared_frame does not move the models. Use alignment_mode explicit to apply a motion.",
        )
    if mode == "explicit" and "rotation_matrix" not in payload and "translation_mm" not in payload:
        return None, _failure("invalid_value", "explicit alignment requires rotation_matrix or translation_mm")
    source = payload.get("source_frame", "limb")
    target = payload.get("target_frame", "socket")
    if source != "limb" or target != "socket":
        return None, _failure(
            "unsupported_transform",
            "The motion maps the limb frame into the socket frame.",
        )
    return {
        "convention": "active_matrix",
        "formula": "p_socket = R @ p_limb + translation_mm",
        "rotation_matrix": matrix.tolist(),
        "translation_mm": translation.tolist(),
        "source_frame": "limb",
        "target_frame": "socket",
        "mode": mode,
        "identity": identity,
    }, None


def apply_rigid_transform(shape, rotation_matrix: list, translation_mm: list):
    """Return a transformed copy. The input shape is not modified."""
    matrix, error = _matrix(rotation_matrix)
    if error:
        raise ValueError(error["error"]["message"])
    translation, error = _translation(translation_mm)
    if error:
        raise ValueError(error["error"]["message"])
    assert matrix is not None and translation is not None
    import cadquery as cq

    if _is_identity(matrix, translation):
        copied = BRepBuilderAPI_Copy(occ_shape(shape))
        return cq.Shape.cast(copied.Shape())
    trsf = gp_Trsf()
    trsf.SetValues(
        float(matrix[0, 0]),
        float(matrix[0, 1]),
        float(matrix[0, 2]),
        float(translation[0]),
        float(matrix[1, 0]),
        float(matrix[1, 1]),
        float(matrix[1, 2]),
        float(translation[1]),
        float(matrix[2, 0]),
        float(matrix[2, 1]),
        float(matrix[2, 2]),
        float(translation[2]),
    )
    moved = BRepBuilderAPI_Transform(occ_shape(shape), trsf, True)
    if not moved.IsDone():
        raise RuntimeError("The rigid transformation could not be applied")
    return cq.Shape.cast(moved.Shape())


def _protected(path: Path) -> bool:
    resolved = path.resolve()
    blocked = {REFERENCE_DIR.resolve(), PROFILE_PATH.parent.resolve(), REFERENCE_STEP.resolve(), SOCKET_STEP.resolve()}
    return resolved in blocked or any(parent in blocked for parent in resolved.parents)


def _load_pair(request: dict) -> tuple[dict | None, dict | None]:
    limb_profile, limb_path, error = _load_model(
        request,
        id_key="limb_model_id",
        path_key="limb_step",
        profile_key="limb_profile_path",
        standard_id="synthetic-transtibial-standard",
        standard_step=REFERENCE_STEP,
        standard_profile=PROFILE_PATH,
        loader=load_profile,
    )
    if error:
        return None, error
    socket_profile, socket_path, error = _load_model(
        request,
        id_key="socket_model_id",
        path_key="socket_step",
        profile_key="socket_profile_path",
        standard_id="synthetic-transtibial-socket-standard",
        standard_step=SOCKET_STEP,
        standard_profile=SOCKET_PROFILE_PATH,
        loader=load_socket_profile,
    )
    if error:
        return None, error
    assert limb_profile is not None and socket_profile is not None and limb_path is not None and socket_path is not None
    try:
        limb_shape = load_step_shape(limb_path[0])
        socket_shape = load_step_shape(socket_path[0])
    except StepLoadError as exc:
        return None, _failure(exc.code, str(exc))
    return {
        "limb_profile": limb_profile,
        "limb_step": limb_path[0],
        "limb_shape": limb_shape,
        "socket_profile": socket_profile,
        "socket_step": socket_path[0],
        "socket_shape": socket_shape,
    }, None


def _load_model(
    request: dict,
    *,
    id_key: str,
    path_key: str,
    profile_key: str,
    standard_id: str,
    standard_step: Path,
    standard_profile: Path,
    loader,
) -> tuple[dict | None, tuple[Path, Path] | None, dict | None]:
    raw_step = request.get(path_key)
    raw_profile = request.get(profile_key)
    model_id = request.get(id_key)
    if raw_step is None and model_id is None:
        return None, None, _failure("unknown_model", f"Pass {id_key} or {path_key}")
    if raw_step is not None:
        step = Path(raw_step)
        if raw_profile is None:
            return None, None, _failure("invalid_value", f"{path_key} requires {profile_key}")
        profile_path = Path(raw_profile)
        if not step.is_file():
            return None, None, _failure("missing_file", f"No STEP file at {step}")
        if not profile_path.is_file():
            return None, None, _failure("missing_file", f"No profile at {profile_path}")
        try:
            profile = loader(profile_path)
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            return None, None, _failure("invalid_value", f"Could not read {profile_path}: {exc}")
        return profile, (step, profile_path), None
    if model_id != standard_id:
        return None, None, _failure(
            "unknown_model",
            f"Unknown model {model_id!r}. Pass a STEP path and a profile path.",
        )
    if not standard_step.is_file():
        return None, None, _failure("missing_file", f"No reference STEP at {standard_step}")
    return loader(standard_profile), (standard_step, standard_profile), None


def relationship_record(limb_profile: dict, socket_profile: dict, transform: dict, *, limb_hash: str, socket_hash: str) -> dict:
    """Design reference and evaluated limb are separate fields."""
    design_id = socket_profile.get("reference_limb_model_id")
    design_version = socket_profile.get("reference_limb_version")
    evaluated_id = limb_profile.get("model_id")
    evaluated_version = limb_profile.get("model_version")
    recorded = socket_profile.get("reference_limb_geometry_hash")
    ids_match = design_id == evaluated_id and design_version == evaluated_version
    if not isinstance(recorded, str) or len(recorded) != 64:
        reference_status = "hash_not_recorded"
    elif ids_match and recorded == limb_hash:
        reference_status = "current"
    elif ids_match:
        reference_status = "hash_mismatch"
    else:
        reference_status = "stale_reference"
    return {
        "limb_model_id": evaluated_id,
        "limb_version": evaluated_version,
        "socket_model_id": socket_profile.get("socket_model_id"),
        "socket_version": socket_profile.get("model_version"),
        "socket_reference_limb_model_id": design_id,
        "socket_reference_limb_version": design_version,
        "evaluated_limb_matches_design_reference": ids_match and reference_status == "current",
        "limb_geometry_hash": limb_hash,
        "recorded_limb_geometry_hash": recorded,
        "socket_geometry_hash": socket_hash,
        "units": "mm",
        "coordinate_system": {
            "ml_axis": "X",
            "ap_axis": "Y",
            "distal": "+Z",
            "proximal_plane_z_mm": 0,
            "side": None,
        },
        "relative_transformation": {
            "convention": transform["convention"],
            "formula": transform["formula"],
            "rotation_matrix": transform["rotation_matrix"],
            "translation_mm": transform["translation_mm"],
            "source_frame": transform["source_frame"],
            "target_frame": transform["target_frame"],
            "mode": transform["mode"],
        },
        "reference_status": reference_status,
        "clinical_use": False,
    }


def prepare_aligned_pair(request: dict) -> dict:
    """Load, check, and transform a limb copy.

    The returned dict includes ``_moved_limb`` and ``_loaded`` for other CAD
    tools in this process. ``align_limb_socket`` removes those before returning.
    """
    if not isinstance(request, dict):
        return _failure("invalid_value", "The alignment request must be an object")
    mode = request.get("alignment_mode", "shared_frame")
    if not isinstance(mode, str):
        return _failure("invalid_value", "alignment_mode must be a string")
    transform, error = parse_transform(request.get("transformation"), mode)
    if error:
        return error
    assert transform is not None
    loaded, error = _load_pair(request)
    if error:
        return error
    assert loaded is not None
    for name, profile in (("limb", loaded["limb_profile"]), ("socket", loaded["socket_profile"])):
        problem = _frame_problem(profile, name)
        if problem:
            return _failure("incompatible_frame", problem)

    before_volume = signed_volume_mm3(loaded["limb_shape"])
    before_area = _surface_area_mm2(loaded["limb_shape"])
    try:
        moved = apply_rigid_transform(
            loaded["limb_shape"],
            transform["rotation_matrix"],
            transform["translation_mm"],
        )
    except (RuntimeError, ValueError) as exc:
        return _failure("transform_failed", str(exc))
    after_volume = signed_volume_mm3(moved)
    after_area = _surface_area_mm2(moved)
    volume_ok = value_within_tolerance(after_volume - before_volume, max(_VOLUME_TOLERANCE_MM3, abs(before_volume) * 1e-5))
    area_ok = abs(after_area - before_area) <= max(1.0, abs(before_area) * _AREA_RELATIVE)
    if not volume_ok or not area_ok:
        return _failure(
            "transform_failed",
            "The motion changed the limb volume or surface area, so it is not a rigid motion of this solid.",
            volume_before_mm3=before_volume,
            volume_after_mm3=after_volume,
            surface_area_before_mm2=before_area,
            surface_area_after_mm2=after_area,
        )

    files = None
    output_dir = request.get("output_dir")
    if output_dir is not None:
        if not isinstance(output_dir, (str, Path)) or str(output_dir) == "":
            return _failure("invalid_value", "output_dir must be a directory path")
        output = Path(output_dir)
        if _protected(output):
            return _failure("protected_output", "Refusing to write a transformed copy into a reference directory")
        output.mkdir(parents=True, exist_ok=True)
        step_path = output / "aligned-limb.step"
        if _protected(step_path):
            return _failure("protected_output", "Refusing to overwrite a reference STEP file")
        from tools.cad.generate_limb import export_solid

        try:
            export_solid(moved, step_path)
        except Exception as exc:
            return _failure("export_failed", f"Could not write the transformed limb: {exc}")
        files = {"aligned_limb_step": str(step_path)}

    transform_report = {
        **transform,
        "volume_before_mm3": before_volume,
        "volume_after_mm3": after_volume,
        "surface_area_before_mm2": before_area,
        "surface_area_after_mm2": after_area,
        "intrinsic_geometry_preserved": True,
        "volume_tolerance_mm3": max(_VOLUME_TOLERANCE_MM3, abs(before_volume) * 1e-5),
    }
    return {
        "ok": True,
        "error": None,
        "clinical_use": False,
        "disclaimer": (
            "The solids share a coordinate frame. That is not a statement about insertion, contact, or safety."
        ),
        "limb_model_id": loaded["limb_profile"].get("model_id"),
        "limb_version": loaded["limb_profile"].get("model_version"),
        "socket_model_id": loaded["socket_profile"].get("socket_model_id"),
        "socket_version": loaded["socket_profile"].get("model_version"),
        "socket_reference_limb_model_id": loaded["socket_profile"].get("reference_limb_model_id"),
        "socket_reference_limb_version": loaded["socket_profile"].get("reference_limb_version"),
        "transformation": transform_report,
        "files": files,
        "_moved_limb": moved,
        "_loaded": loaded,
    }


def align_limb_socket(request: dict) -> dict:
    """Load both solids and record the rigid motion into the socket frame.

    The result is JSON-compatible. It does not include the OpenCascade shape.
    Volume and surface area of the limb are compared before and after the motion.
    """
    prepared = prepare_aligned_pair(request)
    return {key: value for key, value in prepared.items() if not key.startswith("_")}
