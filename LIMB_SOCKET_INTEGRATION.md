# Limb–socket integration

This document describes how a synthetic residual-limb solid and a synthetic socket solid are aligned, measured against each other, and checked as a pair.

The functions are ordinary Python. They do not call Nemotron, and they are not MCP tools. A later agent can call the three public functions below because their requests and reports are JSON-compatible.

**A passing geometric check is not clinical socket fit.** It does not establish comfort, pressure, load transfer, suspension, donning, or prosthetic safety. The clearance numbers are demo geometry parameters, not a liner specification and not a clinical recommendation.

## 1. Architecture

Each solid keeps its own identity.

| Object | Model id | Version | Parameter file | STEP |
| --- | --- | --- | --- | --- |
| Limb v1 | `synthetic-transtibial-standard` | `1.0.0` | `data/profiles/standard_limb.json` | `data/reference/standardized_limb.step` |
| Socket v1 | `synthetic-transtibial-socket-standard` | `1.0.0` | `data/profiles/standard_socket.json` | `data/reference/standardized_socket.step` |

A modified limb is a new profile and a new STEP file. `modify_limb` never overwrites the reference limb. A new socket is built only when a caller asks for one, and it records the limb id, version, and geometry hash it was built from. Changing the limb does not change an existing socket.

The pair tools are:

| Function | Module | Role |
| --- | --- | --- |
| `align_limb_socket` | `tools/cad/align_limb_socket.py` | Load both STEP solids, check the frame, apply an explicit rigid motion to a limb copy |
| `compare_limb_socket` | `tools/cad/compare_limb_socket.py` | Section, radial clearance, and material intersection |
| `validate_pair` | `tools/cad/validate_pair.py` | Model, alignment, geometry, and version checks |

They reuse `measure_socket.section_polylines`, `measure_limb` (volume, validity, STEP load), `validate_limb`, `validate_socket`, and `limb_geometry_hash`. They do not contain a second limb or socket builder.

`validate_socket` always hashes `data/reference/standardized_limb.step`. That is correct for the standard socket and wrong for a socket whose design limb is a later version. `validate_pair` does not treat that hard-wired hash as the pair result. It hashes the limb the socket profile names.

## 2. Coordinate frame

Both solids use one frame. Units are millimetres.

| Axis | Meaning |
| --- | --- |
| +X | Medial-lateral. +X and −X are the two sides of a mirror-symmetric ellipse. The model does not assign medial to a sign, and it has no left or right. |
| +Y | Anterior, as a frame label only. The ellipse is symmetric. |
| +Z | Distal. |
| z = 0 | Limb proximal plane and socket opening plane. The socket brim extends to negative z and is not part of socket depth. |

`align_limb_socket` rejects a profile whose units are not `mm` or whose axis names differ from this frame.

## 3. Transformation

One convention is accepted:

```text
p_socket = R @ p_limb + translation_mm
```

`R` is an active 3×3 rotation matrix. `translation_mm` is a 3-vector in the socket frame. The motion is applied to a copy of the limb. The socket is not moved. The original STEP files are not written. A transformed limb STEP is written only when `output_dir` is set, and that directory cannot be a reference directory.

`alignment_mode` is `shared_frame` or `explicit`.

- `shared_frame` requires the identity. The models are already built in the frame above. This is not a best-fit search.
- `explicit` requires `rotation_matrix` or `translation_mm`.

Rejected inputs: Euler angles, scale, shear, a reflection (`det` −1), a matrix that is not orthonormal within 1e-6, a non-finite component, and a non-identity motion under `shared_frame`.

After the motion, limb volume must match within `max(1 mm³, 1e-5 × |volume|)` and surface area within `max(1 mm², 1e-4 × area)`. The identity path still copies the solid, because a later Boolean or section on the working copy must not rewrite the loaded STEP solid.

## 4. Relationship record

`relationship_record` keeps the design limb and the evaluated limb in different fields.

| Field | Meaning |
| --- | --- |
| `limb_model_id`, `limb_version` | Limb being evaluated |
| `socket_model_id`, `socket_version` | Socket being evaluated |
| `socket_reference_limb_model_id`, `socket_reference_limb_version` | Limb the socket was designed against |
| `limb_geometry_hash` | Hash of the evaluated limb solid |
| `recorded_limb_geometry_hash` | Hash stored on the socket profile |
| `socket_geometry_hash` | Hash of this comparison's socket volume and section perimeters |
| `relative_transformation` | The rigid motion above |
| `reference_status` | `current`, `stale_reference`, `hash_mismatch`, or `hash_not_recorded` |

`current` means the ids, versions, and limb hash all match. `stale_reference` means the socket names a different limb version. That pair can still be measured. `hash_mismatch` means the ids match but the solid does not match the recorded hash. Those are different findings.

The limb hash is SHA-256 of JSON: volume to 0.001 mm³, station z and circumference to 0.0001 mm, and the cutting-plane z extent to 0.0001 mm. Negative zero is written as `0.0`. STEP text is not hashed.

## 5. Cross-sections

Sections are planes of constant z in the socket frame, after the limb copy has been moved. Positions come from the limb profile (`z_mm = length_fraction × total_length`). An explicit `z_mm` replaces that list with one query plane.

At a plane that cuts the socket wall, OpenCascade returns two closed curves. The inner curve is the one with the smaller mean radius. The limb perimeter is compared with that inner curve. The outer perimeter is reported as `socket_outer_perimeter_mm` and is not used as the limb's counterpart.

For each measured section the report includes limb perimeter, socket inner and outer perimeters, limb and socket-inner areas, axis-aligned medial-lateral and anterior-posterior diameters, and the inner-minus-limb perimeter difference in millimetres and percent. Those diameters are the bounding box of the curve in the socket frame. After a rotation they are not the limb's own X and Y axes.

A plane with no curve is `no_intersection`. An explicit query that misses returns `ok: false` and does not invent a measurement. More than one limb curve, or any socket count other than two, is `ambiguous` or `outer_only`. The distal plug is one outer curve. That is not an inner-cavity measurement.

## 6. Clearance sign

Clearance is not a circumference subtraction.

Rays start on the shared Z axis. At each of 72 angles, plus the four axis directions, the signed clearance is

```text
socket inner radius − limb radius
```

along that ray. Both radii are the median of polyline samples inside a 3° window.

| Sign | Meaning |
| --- | --- |
| Positive | Limb boundary is inside the cavity along that ray |
| Zero | The boundaries meet, within sampling noise |
| Negative | Limb boundary is outside the cavity along that ray |

The section report includes the minimum, maximum, mean, the four axis values, and the angle of the minimum.

If a window contains radii that span more than 1.5 mm, or too many angles miss the curve, the section is `unsupported` and the clearance numbers are null. That covers a non-star-shaped section and a limb whose section is not one curve about the Z axis. No average is invented for those sections.

On the standard pair at 50% of limb length, the minimum is 1.700 mm, on the anterior-posterior rays. That is the 2 mm demo radial clearance multiplied by `ap_over_ml` 0.85. The mean of the rays is 1.841 mm. The medial-lateral gap is the 2 mm parameter. These are construction dimensions, not a recommended fit gap.

## 7. Material intersection

Material intersection is the Boolean common of the transformed limb solid and the socket solid (`BRepAlgoAPI_Common`). The cavity is empty. A limb sitting in the cavity is not an intersection.

| Result | Meaning |
| --- | --- |
| Volume ≤ 1 mm³ | `intersects` is false. The 1 mm³ tolerance is Boolean dust, not a fit allowance. |
| Volume > 1 mm³ | `intersects` is true. The volume is the overlapping material in mm³. |
| Boolean did not finish, or the volume is not finite | `status` is `INDETERMINATE`, and `volume_mm3` is null. |

The inputs are copied before the Boolean so a kernel rewrite cannot change the loaded solids. There is no automatic penetration solve and no claim that zero intersection means the limb can be inserted.

## 8. Validation

`validate_pair` returns `PASS`, `FAIL`, `WARNING`, or `INDETERMINATE` on each check. A check that did not run is not `PASS`.

`overall_status` and `geometry_status` roll up model, alignment, and geometric checks. `FAIL` wins, then `INDETERMINATE`. A warning does not fail that rollup.

`version_status` and `reference_status` are separate. A stale design reference is a warning. The geometry can pass while the reference is stale.

Configured constraints, all optional:

| Key | Effect when set |
| --- | --- |
| `required_sections` | Section ids that must be measurable. Default `q25`, `q50`, `q75`. |
| `min_clearance_mm` | Lowest clearance on those sections must be at least this value. |
| `max_intersection_volume_mm3` | Intersection volume must be at or below this value. |

If `min_clearance_mm` is omitted, a measured clearance is `PASS` at any value, including negative. If `max_intersection_volume_mm3` is omitted, a computed intersection is `PASS`, or `WARNING` when the volume is above 1 mm³. The warning reports the volume. It does not invent a clinical limit.

Individual model checks call `validate_limb` on the evaluated limb and `validate_socket` on the socket against its design-reference limb, then keep CAD, dimension, and structure results. Both STEP files are reimported and their volumes are compared.

## 9. Versions and hashes

| Pair | Reference status | What it means |
| --- | --- | --- |
| Limb v1 + socket v1 | `current` | Socket v1 names limb v1 and the hash matches |
| Limb v2 + socket v1 | `stale_reference` | Socket v1 still names limb v1. Limb v2 is only the solid being measured. |
| Limb v2 + socket v2 | `current` | Socket v2 was built from limb v2 with the same demo wall, depth, and 2 mm radial clearance |

Limb v2 is `modify_limb` with `change_section_circumference_percent` +5 at length fraction 0.5. Its version string is `1.0.0+q50`. Its model id is the candidate id. Socket v1 is not rebuilt. Socket v2 is a new STEP file whose profile points at that candidate id, version, and hash.

`hash_mismatch` is reserved for the case where those ids match and the hash does not. A missing STEP file fails before a geometric comparison and sets `reference_status` to `missing`.

## 10. Limitations

- Clearance rays assume a single star-shaped curve about the Z axis. Other sections are unsupported.
- There is no best-fit, ICP, or automatic alignment.
- Axis-aligned diameters after a rotation are extents in the socket frame.
- The 1 mm³ intersection tolerance is numerical dust.
- Boolean volume depends on the OpenCascade kernel. A failed Boolean is indeterminate rather than zero.
- `validate_socket` still hashes the standard limb STEP when it is called on its own. Pair validation does not use that result as the design-limb hash.
- Geometric agreement is not clinical fit, comfort, or safety. Socket v2 uses the same demo parameters as socket v1. It is not a refit.

## 11. Public signatures

```python
def align_limb_socket(request: dict) -> dict: ...
def compare_limb_socket(request: dict) -> dict: ...
def validate_pair(request: dict) -> dict: ...
```

`request` may contain `limb_model_id` or `limb_step` plus `limb_profile_path`, and `socket_model_id` or `socket_step` plus `socket_profile_path`. The standard ids load the reference STEP files. Any other id needs a STEP path and a profile path. `validate_pair` also accepts `constraints`.

These three functions are the ones to expose to Nemotron later. Do not expose the OpenCascade shapes. `prepare_aligned_pair` keeps those shapes in-process and is not a JSON tool.

## 12. Example request and response

Request for the baseline pair:

```json
{
  "limb_model_id": "synthetic-transtibial-standard",
  "socket_model_id": "synthetic-transtibial-socket-standard",
  "alignment_mode": "shared_frame"
}
```

Measured at 50% of limb length (z = 70 mm), from `compare_limb_socket` on the reference STEP files:

```json
{
  "limb_perimeter_mm": 274.99953792286726,
  "socket_inner_perimeter_mm": 286.6425233198637,
  "socket_outer_perimeter_mm": 315.750,
  "perimeter_difference_mm": 11.642985396996437,
  "clearance": {
    "status": "measured",
    "minimum_mm": 1.700156308799322,
    "mean_mm": 1.8414932414781684
  },
  "material_intersection": {
    "status": "PASS",
    "intersects": false,
    "volume_mm3": 0.0,
    "tolerance_mm3": 1.0
  },
  "reference_status": "current"
}
```

The outer perimeter is about 315.75 mm and is not the curve compared with the limb. The full report also contains the other limb stations, the 72 clearance samples, the rotation matrix, and both hashes. `clinical_use` is false.

An explicit motion:

```json
{
  "limb_step": "candidate/limb.step",
  "limb_profile_path": "candidate/limb.json",
  "socket_step": "candidate/socket.step",
  "socket_profile_path": "candidate/socket.json",
  "alignment_mode": "explicit",
  "transformation": {
    "rotation_matrix": [[1, 0, 0], [0, 1, 0], [0, 0, 1]],
    "translation_mm": [5.0, -3.0, 2.0],
    "source_frame": "limb",
    "target_frame": "socket"
  }
}
```

## 13. End-to-end workflow

The workflow is `tests/test_pair_end_to_end.py`. It uses the real STEP solids in a temporary directory.

1. Load limb v1 and socket v1. Align with `shared_frame`. Compare and validate.
2. Build limb v2 by increasing the measured 50% circumference by 5%. Limb v1 and socket v1 stay on disk.
3. Compare limb v2 with the unchanged socket v1. The reference is stale. Clearance at 50% length becomes negative and the solids intersect.
4. Build socket v2 from the limb v2 profile with the same demo clearance, wall, and depth. Export a new STEP file.
5. Align, compare, and validate limb v2 with socket v2. The reference is current. The 50% gap matches the baseline demo gap. Intersection volume is 0.
6. Read the original limb and socket bytes again. They match the bytes from the start of the test.

Measured pairs:

| Pair | q50 limb (mm) | q50 socket inner (mm) | Difference (mm) | Min clearance (mm) | Mean clearance (mm) | Intersection (mm³) | Reference |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Limb v1 + socket v1 | 274.9995 | 286.6425 | +11.6430 | +1.7002 | +1.8415 | 0 | current |
| Limb v2 + socket v1 | 288.7490 | 286.6425 | −2.1065 | −0.3618 | −0.3332 | 1656.37 | stale_reference |
| Limb v2 + socket v2 | 288.7490 | 300.3920 | +11.6430 | +1.7002 | +1.8415 | 0 | current |

Limb v2's 50% circumference is 5% above the measured v1 value (274.9995 × 1.05 = 288.7495; the rebuilt solid measured 288.7490). Socket v2 was not inferred as a clinical fit. It uses the same 2 mm radial clearance, 5 mm wall, and 152 mm depth. The negative clearance and the 1656 mm³ intersection are geometric overlap of limb v2 with the socket v1 wall. They are not a clinical failure mode and not a safety conclusion.

No required check was indeterminate on these three pairs. Limb v2 against socket v1 passes `geometry_status` because no intersection cap was configured. The overlap is a `WARNING` on the material-intersection check. The stale design reference is a separate `WARNING` on `version_status`.

## 14. Tests

Fast geometry tests use cylinders and elliptical tubes, not mocks of the limb. The integration test uses the generated STEP files.

```bash
uv run pytest -q --tb=line
```

Alignment coverage: identity, translation, 90° rotation about Z, reflection, scale, Euler angles, non-finite translation, incompatible units, volume preservation, and unchanged source STEP bytes.

Clearance coverage: inner versus outer curve, +2 mm, 0 mm, −2 mm with intersection volume within 2% of π(14²−12²)×40, no intersection, unequal AP and ML diameters, an off-axis section, two limb curves, a plane at z = 500 mm, and a Boolean that does not return a volume.

Version coverage: matching ids and hash, stale version, hash mismatch with matching ids, missing hash, and a missing STEP file.

`uv run pytest -q --tb=line` completed with 109 passed, 0 failed, and 0 skipped in 210.73 s. That run includes the limb tests, the socket tests, and the pair tests above. `tests/test_standard_limb.py` rewrites the reference limb STEP timestamp when it regenerates the file. The geometry hash does not use that timestamp. If the only diff afterward is `FILE_NAME` and the translator counter, restore that STEP so the baseline text stays the geometry of record.
