# Socket CAD design

Synthetic transtibial socket shell for a software demonstration. The numbers below are computational geometry parameters. They are not a liner gap, a pressure model, or a clinical recommendation. A valid STEP file is not evidence that a socket is wearable or safe.

The limb tools are documented in `CAD_TOOLS.md`. This socket is a separate solid. It uses the limb's coordinate frame and the limb's medial-lateral radius profile. It does not modify the limb.

## Design goal

Build one hollow, open-proximal, closed-distal shell that is recognizably a transtibial socket: a noncircular taper, a rolled brim, and a rounded cup. Patellar-tendon bearing (PTB) sockets and total-surface bearing (TSB) sockets are different clinical design families. This model implements neither. Relief pockets, a patellar-tendon bar, supracondylar wings, and trimlines are not generated. If a later tool needs them, they have to be supplied as explicit inputs. They are not inferred from the synthetic limb.

## Coordinate frame

Units are millimetres.

| Axis | Meaning |
|---|---|
| +Z | Distal, the same direction as the limb |
| z = 0 | Opening plane, coincident with the limb proximal plane |
| −Z | Proximal. The rolled brim extends above the opening plane |
| X | Medial-lateral. The ellipse is mirror-symmetric, so +X is not assigned to medial or lateral, and the model does not encode a left or right limb |
| +Y | Anterior, as a frame label only |
| −Y | Posterior, as a frame label only |

`alignment_transform` is identity. Any other transform is rejected. `side` is null.

## Construction

Method: `wall_profile_revolution_then_y_scale`.

The limb is not scaled, and it is not subtracted from a larger copy of itself. The socket wall is one closed curve in the medial-lateral plane:

1. Inner cavity, from the opening to the start of the distal cap.
2. Inner quarter-ellipse cap, ending on the axis.
3. A segment along the axis through the distal end wall.
4. Outer quarter-ellipse cap.
5. Outer wall back to the opening.
6. A semicircular brim whose diameter is the local wall thickness.

That curve is revolved about Z, then scaled along Y by the limb `ap_over_ml` (0.85 on the standard model). The same scale is what makes every cross-section an ellipse. Anterior-posterior wall thickness is the medial-lateral thickness times `ap_over_ml`. It is not a surface-normal offset of the limb, and a single nominal thickness is not the thickness in every direction.

Inner medial-lateral radius at height z:

```text
limb ML radius(z) + inner_radial_clearance_mm + brim flare(z) + section offset(z)
```

The flare is a smoothstep over `brim_flare_length_mm` at the opening and is zero after that. Outer radius is the inner radius plus the local wall. Local wall is `nominal_wall_thickness_mm` plus `section_wall_extra_mm`.

Socket depth is the outer tip minus the opening plane. The inner tip is `distal_wall_thickness_mm` short of the outer tip, which closes the cup. Depth must leave the inner tip at least 0.5 mm distal of the limb tip. That keeps this construction from driving the cup through the limb point. It is not a fit rule.

`derived` in the JSON is a cache rewritten by the generator. The builder does not read it. Validation fails if the cache disagrees with the editable numbers.

### What is editable, derived, or measured

| Parameter | Role |
|---|---|
| Nominal wall, depth, clearance, brim flare and its length, distal wall, section radius offsets, section wall extras, minimum wall | Editable geometry inputs |
| Limb radius profile, `ap_over_ml`, station z, cap start | Taken from the limb profile |
| Inner and outer radii, opening diameters, tip positions, rim radius | Computed from the inputs above |
| Perimeters, areas, sampled thickness, volume, depth | Measured from the STEP solid |

The standard editable values are wall 5 mm, depth 152 mm, radial clearance 2 mm, brim flare 8 mm over 22 mm, and distal wall 8 mm. `minimum_wall_thickness_mm` is 1.5 mm. That floor is an engineering-demo threshold for this file, not a structural allow-able.

## Standard solid, measured

These are measurements of the generated solid, not copies of the inputs. Medial-lateral wall is 5 mm at every documented station. Anterior-posterior wall is 4.25 mm, which is 5 × 0.85.

| Quantity | Measured |
|---|---:|
| Socket depth | 152.000 mm |
| Brim crest | −2.500 mm |
| Opening, medial-lateral inner diameter | 123.066 mm |
| Opening, anterior-posterior inner diameter | 104.606 mm |
| Opening inner perimeter | 358.215 mm |
| Inner perimeter at 25% of limb length | 301.642 mm |
| Inner perimeter at 50% | 286.643 mm |
| Inner perimeter at 75% | 266.643 mm |
| Inner perimeter at the limb distal reference | 246.643 mm |
| Distal wall along the axis | 8.000 mm |
| Solid volume | 227420 mm³ |

The kernel reports one valid solid. A proximal ray from the cavity does not hit a lid. A distal ray hits the cup. A section through the distal plug is a single outer curve, and a plane past the tip hits nothing.

`reference_limb_geometry_hash` is a SHA-256 of rounded limb measurements (volume to 0.001 mm³, station circumferences and cutting-plane extent to 0.0001 mm). Negative zero is stored as zero. STEP text is not hashed. OpenCascade rewrites the timestamp and entity ids on export, so a text hash would change when the geometry had not.

## Measurement

`measure_socket` cuts the solid with a plane of constant z.

A cut through the wall returns two closed curves. The inner curve is the one with the smaller mean radius. Reporting only the sum would mix the cavity perimeter with the outside. A cut through the distal plug returns one curve and is labeled `outer_only`. No curve is `no_intersection`. More than two significant curves is `ambiguous` and is not labeled inner or outer.

Wall thickness at a station is half the difference of the outer and inner diameters, separately in X and in Y. Distal thickness is the outer tip minus the first axis hit on the way out of the cavity. Area is the planar face bounded by the section edge. Depth is the cutting-plane outer tip minus z = 0. The brim above the opening is not included in the depth.

On this model the station perimeters match the elliptic integral of the constructed semi-axes to well under 0.05 mm. The documented acceptance band is wider than that, so a kernel change of a few tenths of a millimetre is still distinguished from a missed target.

## Validation

`validate_socket` reports four groups:

- CAD: readable STEP, one valid solid, positive volume, reimport, STL triangle count when a mesh path is given.
- Dimensions: depth, opening diameters, inner and outer perimeters, both wall directions, section area, distal axial wall, brim crest.
- Structure: proximal ray clear, distal ray blocked, one curve in the plug, no curve past the tip, two curves at 25%, 50%, and 75%, inner perimeter smaller than outer, thinnest sample at or above the demo floor.
- Reference: limb id, version, units, coordinate frame, geometry hash, `clinical_use` false, derived cache.

Tolerances on the standard profile: circumference 1 mm, depth 0.15 mm, wall 0.2 mm, opening diameter 0.3 mm, area 2%. A pass is `abs(error) <= tolerance`, rounded to 1e-9 mm so a decimal boundary is not tripped by binary noise.

Sampled stations do not prove there is no pinhole somewhere else. The kernel validity check is `BRepCheck_Analyzer`.

## Modifications

`modify_socket` writes a new JSON and STEP under `output_dir`. It does not write the reference socket, the reference limb, or their directories.

| Operation | Field | Effect |
|---|---|---|
| `set_nominal_wall_thickness` | `wall_thickness_mm` | Set the nominal wall. The rim diameter follows it. |
| `set_socket_depth` | `socket_depth_mm` | Move the outer tip. Distal wall thickness is unchanged, so the inner tip moves with it. |
| `set_proximal_opening_ml_diameter` | `opening_ml_diameter_mm` | Set the inner medial-lateral opening. Anterior-posterior size stays on `ap_over_ml`. The flare must stay between 0 and 25 mm. |
| `set_inner_section_circumference` | `section_id` or `section_fraction`, `circumference_mm` | Set the inner perimeter at one limb station by a radius offset. The limb file is not edited. |
| `set_inner_radial_clearance` | `inner_radial_clearance_mm` | Set the radial clearance added to the limb profile. |
| `set_section_wall_extra` | `section_id` or `section_fraction`, `wall_extra_mm` | Add thickness at one station. |

`preserve` may list `socket_depth`, `wall_thickness` (medial-lateral thickness at 50%), `proximal_opening_ml`, and `inner_circumference_q50`. Asking to change and preserve the same quantity is rejected before a solid is built. `wall_thickness` means the 50% station, so an extra on another station can preserve it.

`ok` is true only when the reimported solid passes validation and the preserved measurements stay inside tolerance. `requested_target` is the number sent in. `changes.*.after` is measured from the new STEP.

### Request

```json
{
  "base_socket_id": "synthetic-transtibial-socket-standard",
  "operation": "set_nominal_wall_thickness",
  "wall_thickness_mm": 7.0,
  "preserve": ["socket_depth", "proximal_opening_ml", "inner_circumference_q50"],
  "output_dir": "/tmp/socket-edit"
}
```

### Result

`changes` holds the measured before and after values. A real run fills them. The shape of the object is:

```json
{
  "ok": true,
  "clinical_use": false,
  "operation": "set_nominal_wall_thickness",
  "requested_target": 7.0,
  "requested_target_units": "mm",
  "measured_from": "reimported_step",
  "changes": {
    "wall_thickness": {
      "before": 5.0,
      "after": 7.0,
      "absolute_change": 2.0,
      "percent_change": 40.0
    }
  },
  "files": {
    "step": "/tmp/socket-edit/candidate.step",
    "profile": "/tmp/socket-edit/candidate.json"
  }
}
```

## Error codes

| Code | When |
|---|---|
| `unknown_model` | Socket id is not the standard id and no profile path was given |
| `missing_file` | Profile or STEP path does not exist |
| `invalid_step` | STEP file cannot be read, or reimport failed |
| `unsupported_operation` | Operation name is not in the table above |
| `invalid_section` | Fraction or id is not a limb station, or a query fraction is outside 0–1 |
| `invalid_value` | Wrong type, unused field, non-positive wall or circumference, depth the cup cannot build, opening the brim cannot build |
| `non_finite` | `NaN` or infinity |
| `constraint_conflict` | The edit changes a quantity the request also preserves |
| `protected_output` | Output would write a reference profile, STEP, STL, or their directories |
| `geometry_failed` | The new radii fold toward the tip, or the solid does not build |
| `export_failed` | STEP write failed |
| `invalid_geometry` | The shape is not one valid solid |
| `target_not_met` | A measured dimension missed its constructed target |
| `wall_too_thin` | A sampled thickness is below `minimum_wall_thickness_mm` |
| `opening_closed` | The proximal ray hits a lid |
| `distal_open` | The distal ray does not hit a closed cup |
| `constraint_violated` | A preserved measurement moved by more than its tolerance |
| `stale_reference` | The limb STEP no longer matches `reference_limb_geometry_hash` |
| `reference_mismatch` | Limb id, version, or the derived cache does not match |
| `no_intersection` | The cutting plane misses the solid. The outer tip is this case |

## Public functions

```python
generate_socket(limb_profile: dict, socket_profile: dict) -> cadquery.Shape
measure_socket(source, socket_profile=None, limb_profile=None, *, z_mm=None, length_fraction=None) -> dict
validate_socket(source, socket_profile=None, limb_profile=None, *, step_path=None, stl_path=None) -> dict
modify_socket(request: dict) -> dict
```

`source` is a shape, a STEP path, or the socket id `synthetic-transtibial-socket-standard`. `length_fraction` is a fraction of socket depth from the opening toward the outer tip, not a fraction of limb length.

`compile_socket`, `construction_targets`, and `with_derived` compute the derived geometry without writing files. `write_standard_socket` rebuilds `data/reference/standardized_socket.step`, the STL, and the validation report.

## Example

```python
from tools.cad.generate_limb import load_profile
from tools.cad.generate_socket import generate_socket, load_socket_profile, with_derived
from tools.cad.measure_socket import measure_socket
from tools.cad.modify_socket import modify_socket
from tools.cad.validate_socket import validate_socket

limb = load_profile()
socket = with_derived(limb, load_socket_profile())
shape = generate_socket(limb, socket)
measured = measure_socket(shape, socket, limb)
report = validate_socket(shape, socket, limb)

edited = modify_socket({
    "base_socket_id": socket["socket_model_id"],
    "operation": "set_nominal_wall_thickness",
    "wall_thickness_mm": 7.0,
    "preserve": ["socket_depth", "proximal_opening_ml", "inner_circumference_q50"],
    "output_dir": "/tmp/socket-edit",
})
```

## Known limitations

- One `ap_over_ml` for every station. Anterior-posterior thickness is that ratio times the medial-lateral thickness.
- The inner radius must keep decreasing toward the tip. A large local circumference edit is rejected instead of folding the cavity.
- Brim flare length must stay between 8 and 30 mm so the flare remains a brim, not a reshape of the whole limb.
- The radial clearance is a demo offset in the medial-lateral profile before the Y scale. It is not a normal offset and not a socket-to-limb interference check. Comparing the socket cavity against the limb solid is Phase 4.
- The in-memory kernel bounding box can extend past the trimmed tip. Depth uses cutting planes.
- The exact crest plane of the brim is tangent and can fragment into several short edges. Depth uses a search, not that single plane.
- Section checks are samples. They do not certify the absence of a hole between stations.
- These functions are not registered with the agent, and they do not build a printer file.

## Tests

```bash
uv run pytest
```

The last full run reported 89 passed, 0 failed, and 0 skipped. The socket tests generate the standard solid once per session and write edits under pytest's temporary directories. Reference limb and socket files are not outputs of those tests.

The visualization STL is meshed at 0.15 mm linear tolerance and 0.2 radian angular tolerance. The STEP file is the geometry those tests measure.
