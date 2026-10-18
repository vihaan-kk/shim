"""CAD tools the model can call: thin wrappers around the limb and socket library.

The library in tools/cad/*.py takes file paths and large request objects and
returns long reports. This module is the layer the model sees:

- Parts are identified by short revision ids such as "socket-2" or "limb-1".
  The model never sees a file path.
- Each revision is a folder under workspace/revisions/<revision_id>/ holding
  meta.json, part.step and profile.json. Revisions are never changed after
  they are written; every edit makes a new one.
- validate_part writes part.stl and a "validated" marker when the part passes.
  That is what the printer tools (prepare_print, slice) look for.
- Every tool returns the shared ToolResult with a short summary, not the full
  library report.

Reference files in data/ are never written; the library refuses that anyway.
"""

from __future__ import annotations

import json
import math
import os
import re
import shutil
import tempfile
from contextlib import contextmanager
from pathlib import Path

import cadquery as cq

from common.result import fatal, fixable, success
from tools.cad import prosthesis, questionnaire, socket_features
from tools.cad.socket_features import FeatureError
from tools.cad.generate_limb import (
    PROFILE_PATH,
    REFERENCE_STEP,
    SOCKET_PROFILE_PATH,
    SOCKET_STEP,
    export_solid,
    generate_limb,
    load_profile,
    parameters_from_profile,
)
from tools.cad.generate_socket import (
    export_socket,
    generate_socket,
    limb_geometry_hash,
    load_socket_profile,
    with_derived,
)
from tools.cad.measure_limb import load_step_shape, measure_limb
from tools.cad.measure_socket import measure_socket, section_value
from tools.cad.modify_limb import modify_limb as lib_modify_limb
from tools.cad.modify_socket import modify_socket as lib_modify_socket
from tools.cad.validate_limb import validate_limb
from tools.cad.compare_limb_socket import compare_limb_socket
from tools.cad import validate_socket as validate_socket_module
from tools.cad.validate_socket import validate_socket
from tools.registry import tool

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKSPACE = Path(os.environ.get("WORKSPACE_DIR", REPO_ROOT / "workspace"))
DISCLAIMER = "Demonstration geometry only. Not a clinical fit or safety check; not for wearing."

COMPONENT_TYPES = prosthesis.COMPONENT_TYPES  # adapter, pylon, foot
PART_TYPES = ["socket", "limb"] + COMPONENT_TYPES
# Build volume of the slicer profiles in tools/printer/profiles (x, y, z in mm).
PRINTER_BED_MM = (180.0, 180.0, 180.0)
LIMB_SECTIONS = ["proximal", "q25", "q50", "q75", "distal_reference"]

# Our tool's operation name -> (library operation, library field for the value)
SOCKET_OPERATIONS = {
    "set_wall_thickness": ("set_nominal_wall_thickness", "wall_thickness_mm"),
    "set_depth": ("set_socket_depth", "socket_depth_mm"),
    "set_opening_diameter": ("set_proximal_opening_ml_diameter", "opening_ml_diameter_mm"),
    "set_inner_clearance": ("set_inner_radial_clearance", "inner_radial_clearance_mm"),
    "set_inner_circumference": ("set_inner_section_circumference", "circumference_mm"),
    "add_wall_at_section": ("set_section_wall_extra", "wall_extra_mm"),
}
SOCKET_SECTION_OPERATIONS = {"set_inner_circumference", "add_wall_at_section"}

LIMB_OPERATIONS = {
    "set_circumference": ("set_section_circumference", "circumference_mm"),
    "change_circumference_percent": ("change_section_circumference_percent", "change_percent"),
    "set_length": ("set_total_length", "total_length_mm"),
}
LIMB_SECTION_OPERATIONS = {"set_circumference", "change_circumference_percent"}

# Library error codes where a different value or a question to the user can help.
FIXABLE_CODES = {
    "invalid_value",
    "invalid_section",
    "unsupported_operation",
    "non_finite",
    "constraint_conflict",
    "wall_too_thin",
    "geometry_failed",
    "target_not_met",
    "opening_closed",
    "distal_open",
    "constraint_violated",
}


# ---------------------------------------------------------------------------
# Revision folders
# ---------------------------------------------------------------------------


def _revisions_dir() -> Path:
    return WORKSPACE / "revisions"


def _revision_dir(revision_id: str) -> Path:
    return _revisions_dir() / revision_id


def _scratch_dir():
    """Temporary build folder inside the workspace; a failed edit leaves nothing behind."""
    WORKSPACE.mkdir(parents=True, exist_ok=True)
    return tempfile.TemporaryDirectory(dir=WORKSPACE)


def _read_meta(revision_id: str) -> dict | None:
    """Metadata for a CAD revision, or None if it does not exist or is not a CAD revision."""
    if not re.fullmatch(r"(socket|limb|adapter|pylon|foot|assembly|preview)-\d+", revision_id or ""):
        return None
    path = _revision_dir(revision_id) / "meta.json"
    if not path.is_file():
        return None
    return json.loads(path.read_text())


def _all_meta() -> list[dict]:
    root = _revisions_dir()
    if not root.is_dir():
        return []
    metas = [_read_meta(d.name) for d in root.iterdir() if d.is_dir()]
    return sorted((m for m in metas if m), key=lambda m: (m["part_type"], int(m["revision_id"].split("-")[1])))


def _next_id(part_type: str) -> str:
    numbers = [int(m["revision_id"].split("-")[1]) for m in _all_meta() if m["part_type"] == part_type]
    return f"{part_type}-{max(numbers, default=0) + 1}"


def _save_revision(part_type: str, step_src: Path, profile: dict, **meta) -> str:
    """Copy a built STEP and its profile into a new revision folder. Returns the revision id."""
    revision_id = _next_id(part_type)
    folder = _revision_dir(revision_id)
    folder.mkdir(parents=True)
    shutil.copyfile(step_src, folder / "part.step")
    (folder / "profile.json").write_text(json.dumps(profile, indent=2) + "\n")
    record = {"revision_id": revision_id, "part_type": part_type, **meta}
    (folder / "meta.json").write_text(json.dumps(record, indent=2) + "\n")
    return revision_id


def _base_step(revision_id: str) -> Path:
    """The library's own solid for a revision: base.step when features were cut, else part.step."""
    folder = _revision_dir(revision_id)
    base = folder / "base.step"
    return base if base.is_file() else folder / "part.step"


def _save_socket(base_step: Path, profile: dict, limb_profile: dict, features: list[dict], **meta) -> str:
    """Save a socket revision, cutting its features into the library's solid.

    With features, the revision keeps the library solid as base.step and the cut solid
    as part.step. Raises FeatureError when a feature does not fit this socket.
    """
    if not features:
        return _save_revision("socket", base_step, profile, **meta)
    shape, removed, pieces = socket_features.apply(load_step_shape(base_step), profile, limb_profile, features)
    with _scratch_dir() as out:
        final = Path(out) / "part.step"
        cq.exporters.export(shape, str(final), exportType="STEP")
        revision_id = _save_revision(
            "socket", final, profile, features=features, feature_removed_mm3=removed, **meta,
        )
    folder = _revision_dir(revision_id)
    shutil.copyfile(base_step, folder / "base.step")
    # The cut-away letters, for the viewer to highlight; never printed.
    cq.exporters.export(cq.Compound.makeCompound(pieces), str(folder / "engraving.stl"),
                        exportType="STL", tolerance=0.05, angularTolerance=0.1)
    return revision_id


def _feature_refused(exc: FeatureError, action: str):
    return fixable(
        code=exc.code,
        reason=exc.reason,
        message=f"{action} was refused. Use values in the valid range, or ask the user.",
        valid_range=exc.valid_range,
    )


def _save_component(part_type: str, params: dict, **meta) -> str:
    """Build an adapter, pylon or foot from its parameters and save it as a new revision.

    Raises ValueError when the parameters cannot be built.
    """
    shape = prosthesis.build(part_type, params)
    with _scratch_dir() as out:
        step = Path(out) / "part.step"
        cq.exporters.export(shape, str(step), exportType="STEP")
        return _save_revision(part_type, step, params, **meta)


@contextmanager
def _socket_limb_reference(limb_revision_id: str | None):
    """Make validate_socket check a socket against its own limb.

    validate_socket hashes the module-level REFERENCE_STEP (the standard limb) to check
    which limb a socket was built for (a known limitation in LIMB_SOCKET_INTEGRATION.md).
    For a socket built for another limb that reads as stale, and for a limb much longer
    than 140 mm it throws. While this is active, REFERENCE_STEP is that limb's STEP.
    Its hash cache is keyed by path, so cached values cannot leak between limbs.
    """
    if limb_revision_id is None:
        yield
        return
    original = validate_socket_module.REFERENCE_STEP
    validate_socket_module.REFERENCE_STEP = _revision_dir(limb_revision_id) / "part.step"
    try:
        yield
    finally:
        validate_socket_module.REFERENCE_STEP = original


def _limb_profile_path(limb_revision_id: str | None) -> Path:
    """Profile of the limb a socket is linked to. None means the standard limb."""
    if limb_revision_id is None:
        return PROFILE_PATH
    return _revision_dir(limb_revision_id) / "profile.json"


def _unknown_revision(revision_id: str, part_type: str | None = None):
    known = [m["revision_id"] for m in _all_meta() if part_type is None or m["part_type"] == part_type]
    kind = f"{part_type} " if part_type else ""
    return fixable(
        code="unknown_revision",
        reason=f"No {kind}revision named {revision_id!r}.",
        message=f"Use a {kind}revision id from list_parts, or create one with create_part.",
        valid_range=known,
    )


def _library_failure(report: dict, action: str):
    """Turn a library failure report into fixable or fatal."""
    error = report.get("error") or {}
    code = error.get("code", "unknown_error")
    reason = error.get("message", f"{action} failed")
    details = error.get("details")
    if details:
        reason += f" Details: {json.dumps(details)[:400]}"
    if code in FIXABLE_CODES:
        return fixable(
            code=code,
            reason=reason,
            message=f"{action} was refused. Use a different value, or ask the user what they want.",
        )
    return fatal(code=code, reason=reason, message=f"{action} failed. Tell the user; do not retry.")


def _r(value, digits: int = 2):
    return None if value is None else round(float(value), digits)


# ---------------------------------------------------------------------------
# Summaries the model reads instead of the full library reports
# ---------------------------------------------------------------------------


def _socket_summary(measured: dict) -> dict:
    return {
        "depth_mm": _r(measured.get("depth_mm")),
        "wall_thickness_q50_mm": _r(section_value(measured, "q50", "ml_wall_thickness_mm")),
        "opening_inner_ml_diameter_mm": _r((measured.get("proximal_opening") or {}).get("inner_ml_diameter_mm")),
        "inner_circumference_q50_mm": _r(section_value(measured, "q50", "inner_perimeter_mm")),
    }


def _limb_summary(measured: dict) -> dict:
    sections = measured.get("sections") or []
    return {
        "total_length_mm": _r((measured.get("material_extent_mm") or {}).get("length_mm")),
        "circumference_mm": {
            s.get("id"): _r(s.get("measured_circumference_mm") or s.get("circumference_mm")) for s in sections
        },
    }


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


@tool(
    name="list_parts",
    description=(
        "List the parts that exist: the standard parts (socket, limb, adapter, pylon, foot), "
        "every revision made from them and every assembly, with whether each one has passed "
        "validation. Use this when the user "
        "refers to a part and you do not have its revision id. To get dimensions of one "
        "part, use inspect_part instead."
    ),
    parameters={"type": "object", "properties": {}, "required": []},
)
def list_parts():
    revisions = []
    for m in _all_meta():
        folder = _revision_dir(m["revision_id"])
        entry = {
            "revision_id": m["revision_id"],
            "part_type": m["part_type"],
            "made_by": m.get("made_by"),
            "parent": m.get("parent"),
            "validated": (folder / "validated").exists(),
        }
        if m["part_type"] == "socket":
            entry["fitted_to_limb"] = m.get("limb_revision_id") or "standard limb"
            if m.get("features"):
                entry["features"] = [socket_features.describe(f) for f in m["features"]]
        if m["part_type"] == "preview":
            entry["preview_of"] = m["preview_of"]
            entry["scale_percent"] = m["scale_percent"]
            entry["not_to_size"] = True
        revisions.append(entry)
    return success(
        f"{len(revisions)} revision(s). Standard parts: {', '.join(PART_TYPES)}.",
        {"standard_parts": PART_TYPES, "revisions": revisions},
    )


@tool(
    name="create_part",
    description=(
        "Start a new part from its standard demonstration model: socket (transtibial socket), "
        "limb (the matching synthetic residual limb), adapter (plate under the socket with a "
        "connector), pylon (the tube that sets the leg's height) or foot. Returns a revision "
        "id such as pylon-1. To change an existing revision use modify_socket, validate_measurements or "
        "modify_component instead; to put the parts together use assemble_prosthesis."
    ),
    parameters={
        "type": "object",
        "properties": {"part_type": {"type": "string", "enum": PART_TYPES}},
        "required": ["part_type"],
    },
)
def create_part(part_type: str):
    if part_type == "socket":
        revision_id = _save_revision(
            "socket", SOCKET_STEP, load_socket_profile(SOCKET_PROFILE_PATH),
            made_by="create_part", parent=None, limb_revision_id=None,
        )
    elif part_type == "limb":
        revision_id = _save_revision(
            "limb", REFERENCE_STEP, load_profile(PROFILE_PATH), made_by="create_part", parent=None,
        )
    else:
        params = prosthesis.defaults(part_type)
        revision_id = _save_component(part_type, params, made_by="create_part", parent=None)
    return success(
        f"Created {revision_id} from the standard {part_type}. {DISCLAIMER}",
        {"revision_id": revision_id, "part_type": part_type},
    )


@tool(
    name="inspect_part",
    description=(
        "Measure a part revision and return its main dimensions in mm: for a socket the "
        "depth, wall thickness, opening diameter and inner circumference; for a limb the "
        "length and the circumference at each station; for an adapter, pylon or foot all its "
        "editable parameters and its size; for an assembly its parts and heights. Use before "
        "changing a dimension so you know the current value."
    ),
    parameters={
        "type": "object",
        "properties": {"revision_id": {"type": "string", "description": "For example socket-1 or limb-1."}},
        "required": ["revision_id"],
    },
)
def inspect_part(revision_id: str):
    meta = _read_meta(revision_id)
    if meta is None:
        return _unknown_revision(revision_id)
    folder = _revision_dir(revision_id)
    profile = json.loads((folder / "profile.json").read_text())
    if meta["part_type"] in COMPONENT_TYPES + ["assembly"]:
        summary = dict(profile)
        if meta["part_type"] in COMPONENT_TYPES:
            bb = load_step_shape(folder / "part.step").BoundingBox()
            summary["size_mm"] = [_r(bb.xlen), _r(bb.ylen), _r(bb.zlen)]
        measured = {"ok": True}
    elif meta["part_type"] == "socket":
        limb_profile = load_profile(_limb_profile_path(meta.get("limb_revision_id")))
        measured = measure_socket(_base_step(revision_id), profile, limb_profile)
        summary = _socket_summary(measured)
        if meta.get("features"):
            summary["features"] = [socket_features.describe(f) for f in meta["features"]]
    elif meta["part_type"] == "preview":
        return success(
            f"{revision_id} is a {meta['scale_percent']}% preview of {meta['preview_of']}, NOT TO SIZE.",
            {"revision_id": revision_id, "part_type": "preview", "preview_of": meta["preview_of"],
             "scale_percent": meta["scale_percent"], "not_to_size": True},
        )
    else:
        measured = measure_limb(folder / "part.step", profile)
        summary = _limb_summary(measured)
        if "dimensions" in profile:
            summary["edits"] = _read_meta(revision_id).get("edits", {})
            summary["dimensions"] = profile["dimensions"]
    if not measured.get("ok", True):
        return _library_failure(measured, "Measuring the part")
    return success(
        f"{revision_id} ({meta['part_type']}): " + ", ".join(f"{k}={v}" for k, v in summary.items()),
        {"revision_id": revision_id, "part_type": meta["part_type"], "units": "mm", **summary},
    )


@tool(
    name="modify_socket",
    description=(
        "Change one dimension of a socket revision and save the result as a new revision. "
        "Operations: set_wall_thickness, set_depth, set_opening_diameter, "
        "set_inner_clearance (gap between limb and inner wall), set_inner_circumference "
        "and add_wall_at_section (these two also need section_id). value_mm is the new "
        "value in millimetres, not a change. set_depth must leave room for the limb: depth "
        "minus the 8 mm end wall must be at least the limb length plus 0.5 mm (148.5 mm "
        "for the 140 mm standard limb). If the user gives a change or no number, "
        "inspect_part first or ask the user. To refit a socket to a changed limb, use "
        "fit_socket_to_limb instead."
    ),
    parameters={
        "type": "object",
        "properties": {
            "revision_id": {"type": "string", "description": "Socket revision to start from."},
            "operation": {"type": "string", "enum": list(SOCKET_OPERATIONS)},
            "value_mm": {"type": "number", "minimum": 0, "maximum": 500},
            "section_id": {
                "type": "string",
                "enum": LIMB_SECTIONS,
                "description": "Only for set_inner_circumference and add_wall_at_section.",
            },
        },
        "required": ["revision_id", "operation", "value_mm"],
    },
)
def modify_socket(revision_id: str, operation: str, value_mm: float, section_id: str = ""):
    meta = _read_meta(revision_id)
    if meta is None or meta["part_type"] != "socket":
        return _unknown_revision(revision_id, "socket")
    if operation in SOCKET_SECTION_OPERATIONS and not section_id:
        return fixable(
            code="missing_argument",
            reason=f"{operation} needs section_id.",
            message="Call again with section_id, or ask the user which station.",
            valid_range=LIMB_SECTIONS,
        )
    lib_operation, field = SOCKET_OPERATIONS[operation]
    folder = _revision_dir(revision_id)
    with _scratch_dir() as out:
        request = {
            "base_socket_path": str(folder / "profile.json"),
            "limb_profile_path": str(_limb_profile_path(meta.get("limb_revision_id"))),
            "operation": lib_operation,
            field: value_mm,
            "output_dir": out,
        }
        if operation in SOCKET_SECTION_OPERATIONS:
            request["section_id"] = section_id
        with _socket_limb_reference(meta.get("limb_revision_id")):
            report = lib_modify_socket(request)
        if not report.get("ok"):
            return _library_failure(report, f"{operation} on {revision_id}")
        profile = json.loads(Path(report["files"]["profile"]).read_text())
        limb_profile = load_profile(_limb_profile_path(meta.get("limb_revision_id")))
        try:
            new_id = _save_socket(
                Path(report["files"]["step"]), profile, limb_profile, meta.get("features") or [],
                made_by=f"modify_socket {operation}={value_mm}", parent=revision_id,
                limb_revision_id=meta.get("limb_revision_id"),
            )
        except FeatureError as exc:
            return _feature_refused(exc, f"{operation} on {revision_id} (its label no longer fits)")
    changes = {
        name: {"before": _r(c.get("before")), "after": _r(c.get("after"))}
        for name, c in (report.get("changes") or {}).items()
        if c.get("before") != c.get("after")
    }
    return success(
        f"Created {new_id} from {revision_id} ({operation} = {value_mm} mm). It is not validated yet.",
        {"revision_id": new_id, "parent": revision_id, "changes": changes},
    )


# Not registered as a tool: limbs are edited through validate_measurements and
# customize_residual_limb. Two ways to edit the limb confused the model (it called both).
# Kept as a plain function for tests and scripts.
def modify_limb(revision_id: str, operation: str, value: float, section_id: str = ""):
    meta = _read_meta(revision_id)
    if meta is None or meta["part_type"] != "limb":
        return _unknown_revision(revision_id, "limb")
    if operation in LIMB_SECTION_OPERATIONS and not section_id:
        return fixable(
            code="missing_argument",
            reason=f"{operation} needs section_id.",
            message="Call again with section_id, or ask the user which station.",
            valid_range=LIMB_SECTIONS,
        )
    lib_operation, field = LIMB_OPERATIONS[operation]
    with _scratch_dir() as out:
        request = {
            "base_model_path": str(_revision_dir(revision_id) / "profile.json"),
            "operation": lib_operation,
            field: value,
            "output_dir": out,
        }
        if operation in LIMB_SECTION_OPERATIONS:
            request["section_id"] = section_id
        report = lib_modify_limb(request)
        if not report.get("ok"):
            return _library_failure(report, f"{operation} on {revision_id}")
        new_id = _save_revision(
            "limb", Path(report["files"]["step"]), report["profile"],
            made_by=f"modify_limb {operation}={value}", parent=revision_id,
        )
    unit = "%" if operation == "change_circumference_percent" else " mm"
    return success(
        f"Created {new_id} from {revision_id} ({operation} = {value}{unit}). "
        "Existing sockets are unchanged; use check_fit to see whether they still fit.",
        {"revision_id": new_id, "parent": revision_id, "requested_target_mm": _r(report.get("requested_target"))},
    )


def _pair_paths(socket_revision_id: str, limb_revision_id: str):
    """Look up both revisions. Returns (socket_meta, limb_meta, problem)."""
    socket_meta = _read_meta(socket_revision_id)
    if socket_meta is None or socket_meta["part_type"] != "socket":
        return None, None, _unknown_revision(socket_revision_id, "socket")
    limb_meta = _read_meta(limb_revision_id)
    if limb_meta is None or limb_meta["part_type"] != "limb":
        return None, None, _unknown_revision(limb_revision_id, "limb")
    return socket_meta, limb_meta, None


@tool(
    name="check_fit",
    description=(
        "Check a socket revision against a limb revision: the smallest gap between the limb "
        "and the inner wall, whether the limb overlaps the socket wall, and whether the "
        "socket was built for this limb. Use after a limb changes, or when the user asks if "
        "a socket fits. This is a geometry check only, not a clinical fit."
    ),
    parameters={
        "type": "object",
        "properties": {
            "socket_revision_id": {"type": "string"},
            "limb_revision_id": {"type": "string"},
        },
        "required": ["socket_revision_id", "limb_revision_id"],
    },
)
def check_fit(socket_revision_id: str, limb_revision_id: str):
    socket_meta, limb_meta, problem = _pair_paths(socket_revision_id, limb_revision_id)
    if problem:
        return problem
    socket_dir, limb_dir = _revision_dir(socket_revision_id), _revision_dir(limb_revision_id)
    # compare_limb_socket gives the clearance, overlap and reference status we report.
    # validate_pair would add per-part model checks we do not report.
    try:
        comparison = compare_limb_socket({
            "limb_step": str(limb_dir / "part.step"),
            "limb_profile_path": str(limb_dir / "profile.json"),
            "socket_step": str(_base_step(socket_revision_id)),
            "socket_profile_path": str(socket_dir / "profile.json"),
            "alignment_mode": "shared_frame",
        })
    except Exception as exc:
        comparison = {"ok": False, "error": {"message": f"{type(exc).__name__}: {exc}"}}
    report = comparison
    if not comparison.get("ok"):
        return fatal(
            code="fit_indeterminate",
            reason=json.dumps(comparison.get("error"))[:400],
            message="The fit could not be measured. Tell the user; do not claim it fits.",
        )
    clearances = [
        s["clearance"]["minimum_mm"]
        for s in comparison.get("sections", [])
        if (s.get("clearance") or {}).get("status") == "measured"
    ]
    overlap = comparison.get("material_intersection") or {}
    min_gap = min(clearances) if clearances else None
    overlaps = bool(overlap.get("intersects"))
    built_for = (report.get("relationship") or comparison.get("relationship") or {}).get("reference_status")
    fits = (min_gap is not None and min_gap > 0) and not overlaps
    verdict = "fits" if fits else "does not fit"
    next_step = "" if fits else (
        " Stop here: tell the user these numbers and ask what they want. Do not change the "
        "limb or socket to make it fit unless the user asks. fit_socket_to_limb builds a "
        "socket for this limb if they want one."
    )
    return success(
        f"{socket_revision_id} {verdict} {limb_revision_id}: smallest gap {_r(min_gap)} mm, "
        f"overlap {_r(overlap.get('volume_mm3'), 1)} mm3, socket built for this limb: {built_for}.{next_step} {DISCLAIMER}",
        {
            "fits": fits,
            "min_clearance_mm": _r(min_gap),
            "overlap_volume_mm3": _r(overlap.get("volume_mm3"), 1),
            "reference_status": built_for,
            "socket_revision_id": socket_revision_id,
            "limb_revision_id": limb_revision_id,
        },
    )


@tool(
    name="fit_socket_to_limb",
    description=(
        "Build a new socket revision for a limb revision, keeping the socket's wall "
        "thickness, depth and clearance settings. Use when check_fit says a socket no "
        "longer fits a changed limb and the user wants a socket for that limb. It makes a "
        "new socket; the old one is kept."
    ),
    parameters={
        "type": "object",
        "properties": {
            "socket_revision_id": {"type": "string", "description": "Socket whose settings to keep."},
            "limb_revision_id": {"type": "string", "description": "Limb to build the socket for."},
        },
        "required": ["socket_revision_id", "limb_revision_id"],
    },
)
def fit_socket_to_limb(socket_revision_id: str, limb_revision_id: str):
    socket_meta, limb_meta, problem = _pair_paths(socket_revision_id, limb_revision_id)
    if problem:
        return problem
    limb_dir = _revision_dir(limb_revision_id)
    limb_profile = load_profile(limb_dir / "profile.json")
    profile = json.loads((_revision_dir(socket_revision_id) / "profile.json").read_text())
    profile.pop("derived", None)
    # Keep the gap below the limb tip: a longer limb needs a deeper socket.
    old_limb = load_profile(_limb_profile_path(socket_meta.get("limb_revision_id")))
    length_change = float(limb_profile["total_length_mm"]) - float(old_limb["total_length_mm"])
    old_depth = float(profile["socket_depth_mm"])
    profile["socket_depth_mm"] = round(old_depth + length_change, 3)
    # Per-station socket settings are keyed by the limb's station names; a questionnaire
    # limb can have different stations (P, no q25/q75). Keep values by name, 0 for new ones.
    station_ids = [s["id"] for s in limb_profile["sections"]]
    for key in ("inner_radius_offset_mm", "section_wall_extra_mm"):
        old = profile.get(key) or {}
        profile[key] = {sid: old.get(sid, 0.0) for sid in station_ids}
    profile["reference_limb_model_id"] = limb_profile["model_id"]
    profile["reference_limb_version"] = limb_profile["model_version"]
    try:
        profile["reference_limb_geometry_hash"] = limb_geometry_hash(load_step_shape(limb_dir / "part.step"), limb_profile)
        profile = with_derived(limb_profile, profile)
        shape = generate_socket(limb_profile, profile)
    except (RuntimeError, ValueError, TypeError, KeyError) as exc:
        return fatal(
            code="geometry_failed",
            reason=f"{type(exc).__name__}: {exc}",
            message="A socket could not be built for this limb. Tell the user.",
        )
    with _scratch_dir() as out:
        step = Path(out) / "part.step"
        export_socket(shape, step)
        try:
            new_id = _save_socket(
                step, profile, limb_profile, socket_meta.get("features") or [],
                made_by=f"fit_socket_to_limb {limb_revision_id}", parent=socket_revision_id,
                limb_revision_id=limb_revision_id,
            )
        except FeatureError as exc:
            return _feature_refused(exc, f"Fitting {socket_revision_id} to {limb_revision_id} (its label no longer fits)")
    depth_note = (
        f" Depth changed {old_depth:g} -> {profile['socket_depth_mm']:g} mm to follow the limb length."
        if length_change else ""
    )
    return success(
        f"Created {new_id}: {socket_revision_id}'s settings rebuilt for {limb_revision_id}.{depth_note} "
        "It is not validated yet; check_fit can confirm the fit.",
        {"revision_id": new_id, "parent": socket_revision_id, "limb_revision_id": limb_revision_id,
         "socket_depth_mm": profile["socket_depth_mm"]},
    )


# Accepted questionnaire answers, by validation_id. One use each (README 11.A).
_validations: dict[str, dict] = {}

_MEASUREMENT_PROPERTIES = {
    "length_mm": {"type": "number", "description": "Knee extended: mid-patellar tendon to the distal end."},
    "proximal_circumference_mm": {"type": "number", "description": "Circumference P, 40 mm below the mid-patellar tendon."},
    "mid_circumference_mm": {"type": "number", "description": "Circumference M, halfway between P and D."},
    "distal_circumference_mm": {"type": "number", "description": "Circumference D, 40 mm above the distal end."},
    "ap_mm": {"type": "number", "description": "With ml_mm: anterior-posterior depth at P."},
    "ml_mm": {"type": "number", "description": "With ap_mm: medial-lateral width at P."},
    "distal_shape": {"type": "string", "enum": questionnaire.CHOICES["distal_shape"]},
    "side": {"type": "string", "enum": questionnaire.CHOICES["side"]},
    "posture": {"type": "string", "enum": questionnaire.CHOICES["posture"]},
    "parent_revision_id": {"type": "string", "description": "The limb revision these values update, if any."},
}


@tool(
    name="inspect_limb_template",
    description=(
        "Show the standard limb's dimensions: the default value of every editable limb "
        "dimension (length, circumferences P, M and D, AP and ML widths, distal shape, side, "
        "posture), in mm. Use when the user asks what the defaults are or before suggesting a "
        "change. To build a limb from edited values use validate_measurements."
    ),
    parameters={"type": "object", "properties": {}, "required": []},
)
def inspect_limb_template():
    values = questionnaire.defaults(load_profile(PROFILE_PATH))
    return success(
        "Standard limb dimensions: " + ", ".join(f"{k}={v}" for k, v in values.items())
        + ". Any value the user does not change keeps this default.",
        {"defaults": values, "labels": questionnaire.LABELS, "units": "mm"},
    )


@tool(
    name="validate_measurements",
    description=(
        "Check edited limb dimensions before a limb is built. Pass only the values the user "
        "changed, in mm (convert cm: 15 cm = 150); every value left out keeps the standard "
        "limb's default, so calling it with nothing gives the standard limb. Returns a "
        "validation_id for customize_residual_limb. To change one value later, call it again "
        "with the earlier edits plus that change (inspect_part on the limb lists them)."
    ),
    parameters={"type": "object", "properties": _MEASUREMENT_PROPERTIES, "required": []},
)
def validate_measurements(**edits):
    parent = edits.pop("parent_revision_id", None)
    if parent is not None and (_read_meta(parent) or {}).get("part_type") != "limb":
        return _unknown_revision(parent, "limb")
    try:
        dims, edited, warnings = questionnaire.validate(edits, load_profile(PROFILE_PATH))
    except questionnaire.MeasurementError as exc:
        return fixable(
            code=exc.code, reason=exc.reason, valid_range=exc.valid_range,
            message="Tell the user which value is the problem and ask for a corrected one.",
        )
    validation_id = "val_" + os.urandom(3).hex()
    _validations[validation_id] = {"dims": dims, "edits": edits, "parent": parent}
    changed = ", ".join(f"{k}={dims[k]}" for k in edited) or "none (standard limb)"
    return success(
        f"Dimensions accepted. Changed from the standard limb: {changed}. Every other value "
        f"keeps its default. Call customize_residual_limb with validation_id {validation_id}."
        + (" Notes: " + " ".join(warnings) if warnings else ""),
        {"validation_id": validation_id, "accepted": True, "edited": {k: dims[k] for k in edited},
         "dimensions": {k: v for k, v in dims.items() if v is not None}, "warnings": warnings},
    )


@tool(
    name="customize_residual_limb",
    description=(
        "Build a new residual-limb revision from dimensions that validate_measurements "
        "accepted. Needs that validation_id; each one is used once. The result re-measures the "
        "built limb and reports target and measured values. The limb is a non-wearable "
        "demonstration model, not a reconstruction of the patient's limb. To build a socket "
        "for it afterwards use fit_socket_to_limb."
    ),
    parameters={
        "type": "object",
        "properties": {"validation_id": {"type": "string", "description": "From validate_measurements."}},
        "required": ["validation_id"],
    },
)
def customize_residual_limb(validation_id: str):
    accepted = _validations.get(validation_id)
    if accepted is None:
        return fixable(
            code="validation_mismatch",
            reason=f"No unused validation {validation_id!r}.",
            message="Call validate_measurements with the user's measurements first and use its validation_id.",
        )
    dims = accepted["dims"]
    template = load_profile(PROFILE_PATH)
    revision_id = _next_id("limb")
    profile = questionnaire.to_limb_profile(dims, template, model_id=f"dimensions-{revision_id}")
    try:
        shape = generate_limb(parameters_from_profile(profile))
    except (RuntimeError, ValueError) as exc:
        return fatal(code="geometry_failed", reason=str(exc),
                     message="The limb could not be built from these measurements. Tell the user.")
    with _scratch_dir() as out:
        step = Path(out) / "part.step"
        export_solid(shape, step)
        measured = measure_limb(step, profile)
        length = (measured.get("material_extent_mm") or {}).get("length_mm")
        stations = []
        for target, row in zip(profile["sections"], measured.get("sections") or []):
            got = row.get("measured_circumference_mm")
            stations.append({"id": target["id"], "target_mm": _r(target["circumference_mm"]),
                             "measured_mm": _r(got), "error_mm": _r(None if got is None else got - target["circumference_mm"])})
        off = [s for s in stations if s["error_mm"] is None
               or abs(s["error_mm"]) > max(3.0, 0.02 * s["target_mm"])]
        if length is None or abs(length - dims["length_mm"]) > 2.0 or off:
            return fixable(
                code="target_not_met",
                reason=f"Built limb missed its targets: length {_r(length)} vs {dims['length_mm']} mm; stations {off}.",
                message="The limb was not saved. Tell the user which measurement could not be met.",
            )
        del _validations[validation_id]  # used once, and only after a limb was built
        new_id = _save_revision(
            "limb", step, profile, made_by="customize_residual_limb", parent=accepted["parent"],
            edits=accepted["edits"],
        )
    return success(
        f"Created {new_id} from the dimensions: length {_r(length)} mm; "
        + ", ".join(f"{s['id']} {s['measured_mm']} mm" for s in stations)
        + f". {DISCLAIMER}",
        {"revision_id": new_id, "parent_revision_id": accepted["parent"], "measured_length_mm": _r(length),
         "stations": stations, "edits": accepted["edits"]},
    )


@tool(
    name="modify_component",
    description=(
        "Change one parameter of an adapter, pylon or foot revision and save the result as "
        "a new revision. Parameters, all in mm: adapter: plate_diameter_mm, "
        "plate_thickness_mm, bolt_circle_mm, bolt_hole_diameter_mm, connector_size_mm, "
        "connector_height_mm. pylon: length_mm (end to end; sets the leg's height), "
        "outer_diameter_mm, wall_thickness_mm, collar_diameter_mm, collar_height_mm, "
        "connector_size_mm, connector_height_mm. foot: length_mm, width_mm, heel_height_mm, "
        "toe_thickness_mm, connector_size_mm, connector_height_mm. value is the new value, "
        "not a change. Connected parts must keep equal connector sizes. For sockets use "
        "modify_socket; for the limb use validate_measurements."
    ),
    parameters={
        "type": "object",
        "properties": {
            "revision_id": {"type": "string", "description": "An adapter, pylon or foot revision, e.g. pylon-1."},
            "parameter": {
                "type": "string",
                "enum": sorted({name for specs in prosthesis.PARAMETERS.values() for name in specs}),
            },
            "value": {"type": "number", "minimum": 0, "maximum": 1000},
        },
        "required": ["revision_id", "parameter", "value"],
    },
)
def modify_component(revision_id: str, parameter: str, value: float):
    meta = _read_meta(revision_id)
    if meta is None or meta["part_type"] not in COMPONENT_TYPES:
        return fixable(
            code="unknown_revision",
            reason=f"{revision_id!r} is not an adapter, pylon or foot revision.",
            message="Use an adapter, pylon or foot revision id from list_parts. Sockets use "
                    "modify_socket and limbs use validate_measurements.",
            valid_range=[m["revision_id"] for m in _all_meta() if m["part_type"] in COMPONENT_TYPES],
        )
    part_type = meta["part_type"]
    specs = prosthesis.PARAMETERS[part_type]
    if parameter not in specs:
        return fixable(
            code="unknown_parameter",
            reason=f"A {part_type} has no parameter {parameter!r}.",
            message=f"Use one of the {part_type} parameters.",
            valid_range=list(specs),
        )
    params = json.loads((_revision_dir(revision_id) / "profile.json").read_text())
    before = params[parameter]
    params[parameter] = value
    try:
        new_id = _save_component(
            part_type, params, made_by=f"modify_component {parameter}={value}", parent=revision_id,
        )
    except ValueError as exc:
        _, low, high = specs[parameter]
        return fixable(
            code="invalid_value",
            reason=str(exc),
            message="That value cannot be built. Use a value that satisfies the reason, or ask the user.",
            valid_range={"min": low, "max": high},
        )
    return success(
        f"Created {new_id} from {revision_id}: {parameter} {before} -> {value} mm. It is not validated yet.",
        {"revision_id": new_id, "parent": revision_id, "changes": {parameter: {"before": before, "after": value}}},
    )


@tool(
    name="assemble_prosthesis",
    description=(
        "Put a socket, adapter, pylon and foot together as one prosthesis and report its "
        "height from the socket opening to the floor. Use after creating or changing the "
        "parts, or when the user asks how tall the leg is. It checks that the connectors "
        "match. To change the height, change the pylon's length_mm with modify_component and "
        "assemble again. An assembly is for checking and viewing; each part is printed "
        "separately."
    ),
    parameters={
        "type": "object",
        "properties": {
            "socket_revision_id": {"type": "string"},
            "adapter_revision_id": {"type": "string"},
            "pylon_revision_id": {"type": "string"},
            "foot_revision_id": {"type": "string"},
        },
        "required": ["socket_revision_id", "adapter_revision_id", "pylon_revision_id", "foot_revision_id"],
    },
)
def assemble_prosthesis(socket_revision_id: str, adapter_revision_id: str, pylon_revision_id: str, foot_revision_id: str):
    ids = {"socket": socket_revision_id, "adapter": adapter_revision_id, "pylon": pylon_revision_id, "foot": foot_revision_id}
    for part_type, revision_id in ids.items():
        meta = _read_meta(revision_id)
        if meta is None or meta["part_type"] != part_type:
            return _unknown_revision(revision_id, part_type)
    socket_dir = _revision_dir(socket_revision_id)
    socket_profile = json.loads((socket_dir / "profile.json").read_text())
    parts = {}
    for part_type in COMPONENT_TYPES:
        folder = _revision_dir(ids[part_type])
        parts[part_type] = (load_step_shape(folder / "part.step"), json.loads((folder / "profile.json").read_text()))
    try:
        result = prosthesis.assemble(load_step_shape(socket_dir / "part.step"), float(socket_profile["socket_depth_mm"]), parts)
    except ValueError as exc:
        return fixable(
            code="connector_mismatch",
            reason=str(exc),
            message="The parts do not connect. Ask the user which part to change, then set the "
                    "connector sizes equal with modify_component.",
        )
    heights = {k: v for k, v in result.items() if k != "compound"}
    with _scratch_dir() as out:
        step = Path(out) / "part.step"
        cq.exporters.export(result["compound"], str(step), exportType="STEP")
        new_id = _save_revision("assembly", step, {"parts": ids, **heights}, made_by="assemble_prosthesis", parent=None)
    return success(
        f"Assembled {new_id}: socket opening to floor {heights['opening_to_floor_mm']} mm "
        f"(socket end to floor {heights['socket_end_to_floor_mm']} mm). Each part is printed "
        f"separately. {DISCLAIMER}",
        {"revision_id": new_id, "parts": ids, **heights},
    )


def _validate_component(shape, part_type: str, params: dict) -> dict:
    """Geometry checks for an adapter, pylon or foot, in the same shape as the library reports."""
    checks = []
    try:
        prosthesis.check_parameters(part_type, params)
        checks.append({"name": "parameters", "passed": True, "detail": "all parameters in range"})
    except ValueError as exc:
        checks.append({"name": "parameters", "passed": False, "detail": str(exc)})
    checks.append({"name": "valid_solid", "passed": bool(shape.isValid()), "detail": "OpenCascade validity"})
    checks.append({"name": "one_solid", "passed": len(shape.Solids()) == 1, "detail": f"{len(shape.Solids())} solid(s)"})
    checks.append({"name": "positive_volume", "passed": shape.Volume() > 0, "detail": f"{shape.Volume():.0f} mm3"})
    failed = [c for c in checks if not c["passed"]]
    return {
        "passed": not failed,
        "checks": checks,
        "error": None if not failed else {"code": "invalid_geometry", "message": "; ".join(c["detail"] for c in failed)},
    }


def _too_big_for_printer(stl_path: Path) -> str | None:
    """The part's size as 'x x y x z' if its STL does not fit the printer, else None."""
    import numpy as np  # local: only needed here

    data = stl_path.read_bytes()
    if data[:5] == b"solid" and b"facet" in data[:400]:
        values = re.findall(rb"vertex\s+(\S+)\s+(\S+)\s+(\S+)", data)
        points = np.array(values, dtype=float)
    else:
        count = int.from_bytes(data[80:84], "little")
        rows = np.frombuffer(data[84:84 + count * 50], dtype=np.dtype([("n", "<3f4"), ("v", "<9f4"), ("a", "<u2")]))
        points = rows["v"].reshape(-1, 3)
    size = points.max(axis=0) - points.min(axis=0)
    if all(s <= limit for s, limit in zip(size, PRINTER_BED_MM)):
        return None
    return " x ".join(f"{s:.1f}" for s in size)


def _export_socket_for_printing(shape, stl_path: Path) -> None:
    """Write the socket STL the slicer gets: a finer mesh, turned opening-up.

    export_socket's mesh (0.15 mm, 0.2 rad) leaves about 25 flat facets around the
    wall. 0.05 mm / 0.1 rad is smooth and still exports in about 12 s.
    The socket's frame has the opening at z = 0 and the closed end at +Z, so the
    slicer would print it opening-down, with the inside of the closed end as an
    unsupported ceiling. Turning it 180 degrees about X puts the closed end on the
    bed; the build-plate supports in the slicer profiles hold the rounded end.
    Only this STL is turned. part.step stays in the design frame.
    """
    turned = shape.rotate((0, 0, 0), (1, 0, 0), 180)
    cq.exporters.export(turned, str(stl_path), exportType="STL", tolerance=0.05, angularTolerance=0.1)


@tool(
    name="validate_part",
    description=(
        "Run the geometry checks on a revision (one valid solid, dimensions on target, "
        "walls thick enough, opening open) and, if it passes, export the STL so it can be "
        "printed. A part must pass this before prepare_print can print it. Passing is a "
        "geometry check only; never call a part clinically approved or safe to wear."
    ),
    parameters={
        "type": "object",
        "properties": {"revision_id": {"type": "string"}},
        "required": ["revision_id"],
    },
)
def validate_part(revision_id: str):
    meta = _read_meta(revision_id)
    if meta is None:
        return _unknown_revision(revision_id)
    if meta["part_type"] == "preview":
        return success(
            f"{revision_id} was checked when make_preview_print made it; it is a "
            f"{meta['scale_percent']}% copy of {meta['preview_of']}, NOT TO SIZE.",
            {"revision_id": revision_id, "validated": True, "printable": True, "not_to_size": True},
        )
    if meta["part_type"] == "assembly":
        return fixable(
            code="assembly_not_printable",
            reason="An assembly is several parts; parts are printed one at a time.",
            message="Validate and print each part of the assembly (socket, adapter, pylon, foot) separately.",
            valid_range=list(json.loads((_revision_dir(revision_id) / "profile.json").read_text())["parts"].values()),
        )
    folder = _revision_dir(revision_id)
    step, stl = folder / "part.step", folder / "part.stl"
    profile = json.loads((folder / "profile.json").read_text())
    shape = load_step_shape(step)
    if meta["part_type"] in COMPONENT_TYPES:
        report = _validate_component(shape, meta["part_type"], profile)
        if report["passed"]:
            cq.exporters.export(shape, str(stl), exportType="STL", tolerance=0.05, angularTolerance=0.1)
    elif meta["part_type"] == "socket":
        limb_profile = load_profile(_limb_profile_path(meta.get("limb_revision_id")))
        _export_socket_for_printing(shape, stl)
        # The library checks its own solid; a distal vent would fail its closed-end check.
        base_step = _base_step(revision_id)
        base = shape if base_step == step else load_step_shape(base_step)
        with _socket_limb_reference(meta.get("limb_revision_id")):
            report = validate_socket(base, profile, limb_profile, step_path=base_step, stl_path=stl)
        if meta.get("features"):
            category = socket_features.checks(shape, base, meta["features"], meta.get("feature_removed_mm3") or [])
            report["categories"]["features"] = category
            if not category["passed"]:
                report["passed"] = False
                failed = [c for c in category["checks"] if not c["passed"]]
                report["error"] = report.get("error") or {
                    "code": "invalid_geometry", "message": "A cut feature failed its check",
                    "details": {"checks": failed},
                }
    else:
        export_solid(shape, folder / "check.step", stl)
        (folder / "check.step").unlink(missing_ok=True)
        report = validate_limb(shape, profile)
    (folder / "validation.json").write_text(json.dumps(report, indent=2, default=str) + "\n")
    if not report.get("passed"):
        stl.unlink(missing_ok=True)
        failed = report.get("error") or {"code": "validation_failed", "message": "A geometry check failed."}
        return fixable(
            code=failed.get("code", "validation_failed"),
            reason=failed.get("message", "A geometry check failed."),
            message=f"{revision_id} did not pass. Tell the user what failed and ask how to change it.",
        )
    too_big = _too_big_for_printer(stl)
    if too_big:
        stl.unlink(missing_ok=True)
        return fixable(
            code="too_large_for_printer",
            reason=f"{revision_id} is {too_big} mm in its print orientation; the printer holds "
                   f"{' x '.join(f'{v:g}' for v in PRINTER_BED_MM)} mm.",
            message="The part is valid but does not fit the printer. Tell the user and ask "
                    "whether to make it smaller.",
            valid_range={"max_x_mm": PRINTER_BED_MM[0], "max_y_mm": PRINTER_BED_MM[1], "max_z_mm": PRINTER_BED_MM[2]},
        )
    (folder / "validated").write_text("Written by validate_part after all geometry checks passed.\n")
    return success(
        f"{revision_id} passed the geometry checks and is ready to print. {DISCLAIMER}",
        {"revision_id": revision_id, "validated": True, "printable": True},
    )


# ---------------------------------------------------------------------------
# Labels engraved into a socket, and scaled previews
# ---------------------------------------------------------------------------


def _add_socket_feature(revision_id: str, feature: dict, action: str):
    """Make a new socket revision with one more feature cut into it."""
    meta = _read_meta(revision_id)
    if meta is None or meta["part_type"] != "socket":
        return _unknown_revision(revision_id, "socket")
    folder = _revision_dir(revision_id)
    profile = json.loads((folder / "profile.json").read_text())
    limb_profile = load_profile(_limb_profile_path(meta.get("limb_revision_id")))
    features = [*(meta.get("features") or []), feature]
    try:
        socket_features.check(feature, profile)  # range errors before any geometry work
        new_id = _save_socket(
            _base_step(revision_id), profile, limb_profile, features,
            made_by=f"{action} {socket_features.describe(feature)}", parent=revision_id,
            limb_revision_id=meta.get("limb_revision_id"),
        )
    except FeatureError as exc:
        return _feature_refused(exc, f"{action} on {revision_id}")
    return success(
        f"Created {new_id} from {revision_id} with a {socket_features.describe(feature)}. "
        "It is not validated yet.",
        {"revision_id": new_id, "parent": revision_id, "feature": feature,
         "features": [socket_features.describe(f) for f in features]},
    )


@tool(
    name="engrave_label",
    description=(
        "Engrave text into the outer wall of a socket revision, for example its revision id "
        "or a date, and save the result as a new revision. face is front, back, left or "
        "right (left and right as seen from the front). height_mm is how far below the "
        "opening the centre of the text sits; leave it out for the middle of the wall. "
        "The text keeps through later socket edits. Refused if the text is too wide or deep "
        "for the wall; the result gives the valid range."
    ),
    parameters={
        "type": "object",
        "properties": {
            "revision_id": {"type": "string", "description": "Socket revision to engrave."},
            "text": {"type": "string", "description": "1-20 characters: letters, digits, spaces, . - _ # /"},
            "face": {"type": "string", "enum": list(socket_features.FACES)},
            "height_mm": {"type": "number", "description": "Centre of the text, mm below the opening."},
            "text_height_mm": {"type": "number", "description": "Letter height, 4-20 mm. Default 10."},
            "depth_mm": {"type": "number", "description": "Engraving depth, 0.4-1.5 mm. Default 1.2."},
        },
        "required": ["revision_id", "text", "face"],
    },
)
def engrave_label(revision_id: str, text: str, face: str, height_mm: float | None = None,
                  text_height_mm: float = 10.0, depth_mm: float = 1.2):
    meta = _read_meta(revision_id)
    if meta is None or meta["part_type"] != "socket":
        return _unknown_revision(revision_id, "socket")
    if height_mm is None:
        height_mm = socket_features.default_height(json.loads((_revision_dir(revision_id) / "profile.json").read_text()))
    feature = {"type": "label", "text": text.strip(), "face": face, "height_mm": float(height_mm),
               "text_height_mm": float(text_height_mm), "depth_mm": float(depth_mm)}
    return _add_socket_feature(revision_id, feature, "engrave_label")


PREVIEW_SCALE_PERCENT = (25, 75)
PREVIEW_MIN_WALL_MM = 1.2  # three 0.4 mm nozzle widths


def _thinnest_wall_mm(meta: dict, profile: dict) -> float | None:
    if meta["part_type"] == "socket":
        extras = [v for v in (profile.get("section_wall_extra_mm") or {}).values() if v < 0]
        return float(profile["nominal_wall_thickness_mm"]) + min(extras, default=0.0)
    if meta["part_type"] == "pylon":
        return float(profile["wall_mm"])
    return None


@tool(
    name="make_preview_print",
    description=(
        "Make a scaled-down preview of a validated part for a quick test print, as a new "
        "revision such as preview-1. It is NOT TO SIZE: only use it when the user asks for a "
        "small, test or preview print, and always tell them the scale. scale_percent is 25 to "
        "75. The preview is ready to print with prepare_print; the full-size part is unchanged."
    ),
    parameters={
        "type": "object",
        "properties": {
            "revision_id": {"type": "string", "description": "A part that passed validate_part."},
            "scale_percent": {"type": "number", "description": "25 to 75."},
        },
        "required": ["revision_id", "scale_percent"],
    },
)
def make_preview_print(revision_id: str, scale_percent: float):
    meta = _read_meta(revision_id)
    if meta is None:
        return _unknown_revision(revision_id)
    if meta["part_type"] in ("assembly", "preview"):
        return fixable(
            code="not_previewable",
            reason=f"{revision_id} is {'an assembly' if meta['part_type'] == 'assembly' else 'already a preview'}.",
            message="Make a preview of one full-size part.",
        )
    folder = _revision_dir(revision_id)
    if not (folder / "validated").exists():
        return fixable(
            code="not_validated",
            reason=f"{revision_id} has not passed validate_part; a preview is only made of a checked part.",
            message=f"Call validate_part on {revision_id} first.",
        )
    low, high = PREVIEW_SCALE_PERCENT
    if not low <= scale_percent <= high:
        return fixable(
            code="out_of_range", reason=f"scale_percent must be {low} to {high}.",
            message="Ask the user which scale they want.", valid_range=[low, high],
        )
    profile = json.loads((folder / "profile.json").read_text())
    factor = scale_percent / 100
    wall = _thinnest_wall_mm(meta, profile)
    if wall is not None and wall * factor < PREVIEW_MIN_WALL_MM:
        smallest = math.ceil(PREVIEW_MIN_WALL_MM / wall * 100)
        return fixable(
            code="wall_too_thin",
            reason=f"At {scale_percent:g}% the {wall:g} mm wall would be {wall * factor:.2f} mm; "
                   f"a print needs at least {PREVIEW_MIN_WALL_MM:g} mm.",
            message="Ask the user for a larger scale.",
            valid_range=[max(low, smallest), high],
        )
    shape = load_step_shape(folder / "part.step").scale(factor)
    if not shape.isValid() or len(shape.Solids()) != 1:
        return fatal(code="geometry_failed", reason="The scaled part is not one valid solid.",
                     message="Tell the user the preview could not be made.")
    with _scratch_dir() as out:
        step = Path(out) / "part.step"
        cq.exporters.export(shape, str(step), exportType="STEP")
        new_id = _save_revision(
            "preview", step, {"preview_of": revision_id, "scale_percent": scale_percent},
            made_by=f"make_preview_print {scale_percent:g}%", parent=revision_id,
            preview_of=revision_id, scale_percent=scale_percent, source_part_type=meta["part_type"],
        )
    new_folder = _revision_dir(new_id)
    stl = new_folder / "part.stl"
    if meta["part_type"] == "socket":
        _export_socket_for_printing(shape, stl)
    else:
        cq.exporters.export(shape, str(stl), exportType="STL", tolerance=0.05, angularTolerance=0.1)
    (new_folder / "validated").write_text(
        f"Written by make_preview_print: a {scale_percent:g}% copy of {revision_id}, which passed "
        "validate_part. NOT TO SIZE.\n"
    )
    return success(
        f"Created {new_id}: a {scale_percent:g}% preview of {revision_id}, NOT TO SIZE. Tell the user "
        f"the scale; it is ready for prepare_print. {revision_id} itself is unchanged. {DISCLAIMER}",
        {"revision_id": new_id, "preview_of": revision_id, "scale_percent": scale_percent,
         "not_to_size": True, "printable": True},
    )
