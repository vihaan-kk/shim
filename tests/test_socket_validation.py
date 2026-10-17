"""Validation categories for the socket solid."""

import copy

import cadquery as cq
from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeEdge
from OCP.gp import gp_Pnt

from tools.cad.generate_limb import SOCKET_STEP, SOCKET_STL, load_profile
from tools.cad.generate_socket import SOCKET_PROFILE_PATH, load_socket_profile, with_derived
from tools.cad.validate_socket import validate_socket


def _failed_names(report: dict) -> set[str]:
    names = set()
    for category in report["categories"].values():
        for check in category["checks"]:
            if not check["passed"]:
                names.add(check["name"])
    return names


def test_standard_socket_passes(standard_socket):
    report = validate_socket(standard_socket["shape"], standard_socket["profile"], standard_socket["limb"])
    assert report["passed"] is True
    assert report["clinical_use"] is False
    assert "wear" in report["disclaimer"]


def test_reference_step_and_stl_pass():
    profile = load_socket_profile(SOCKET_PROFILE_PATH)
    report = validate_socket(
        SOCKET_STEP,
        profile,
        load_profile(),
        step_path=SOCKET_STEP,
        stl_path=SOCKET_STL,
    )
    assert report["passed"] is True, report.get("error")
    assert SOCKET_STL.is_file()
    assert SOCKET_STL.stat().st_size > 84


def test_malformed_step_is_rejected(standard_socket, tmp_path):
    broken = tmp_path / "broken.step"
    broken.write_bytes(b"ISO-10303-21;\n" + b"garbage" * 8)
    report = validate_socket(broken, standard_socket["profile"], standard_socket["limb"])
    assert report["passed"] is False
    assert report["error"]["code"] == "invalid_step"


def test_non_solid_and_disconnected_geometry(standard_socket):
    edge = BRepBuilderAPI_MakeEdge(gp_Pnt(0, 0, 0), gp_Pnt(12, 0, 0)).Edge()
    edge_report = validate_socket(edge, standard_socket["profile"], standard_socket["limb"])
    assert edge_report["passed"] is False
    assert edge_report["error"]["code"] == "invalid_geometry"

    first = cq.Solid.makeBox(6, 6, 6)
    second = cq.Solid.makeBox(6, 6, 6).move(cq.Location(cq.Vector(20, 0, 0)))
    compound = cq.Compound.makeCompound([first, second])
    split = validate_socket(compound, standard_socket["profile"], standard_socket["limb"])
    assert split["passed"] is False
    assert "one_solid" in _failed_names(split)


def test_closed_limb_is_not_an_open_socket(standard_model, standard_socket):
    report = validate_socket(standard_model["shape"], standard_socket["profile"], standard_socket["limb"])
    assert report["passed"] is False
    assert "proximal_opening_open" in _failed_names(report)


def test_thin_wall_and_wrong_depth(standard_socket, tmp_path):
    from tools.cad.generate_socket import generate_socket

    thin_profile = copy.deepcopy(standard_socket["profile"])
    thin_profile["nominal_wall_thickness_mm"] = 1.2
    thin_profile = with_derived(standard_socket["limb"], thin_profile)
    thin = generate_socket(standard_socket["limb"], thin_profile)
    thin_report = validate_socket(thin, thin_profile, standard_socket["limb"])
    assert thin_report["passed"] is False
    assert thin_report["error"]["code"] == "wall_too_thin"

    shifted = copy.deepcopy(standard_socket["profile"])
    shifted["socket_depth_mm"] = 170.0
    shifted = with_derived(standard_socket["limb"], shifted)
    report = validate_socket(standard_socket["shape"], shifted, standard_socket["limb"])
    assert "socket_depth" in _failed_names(report)


def test_stale_limb_hash_and_version(standard_socket):
    stale = copy.deepcopy(standard_socket["profile"])
    stale["reference_limb_geometry_hash"] = "0" * 64
    stale_report = validate_socket(standard_socket["shape"], stale, standard_socket["limb"])
    assert stale_report["error"]["code"] == "stale_reference"

    renamed = copy.deepcopy(standard_socket["profile"])
    renamed["reference_limb_version"] = "9.9.9"
    renamed_report = validate_socket(standard_socket["shape"], renamed, standard_socket["limb"])
    assert renamed_report["passed"] is False
    assert "limb_model_version" in _failed_names(renamed_report)
    assert renamed_report["error"]["code"] == "reference_mismatch"
