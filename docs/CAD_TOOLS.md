# CAD tools

Deterministic Python functions for one synthetic transtibial residual-limb solid. They do not call Nemotron, and a passing check is not a statement about fit, pressure, or wearable safety.

Units are millimetres. X is medial-lateral, Y is anterior-posterior, and Z is longitudinal. The proximal plane is z = 0. Distal is +Z.

Cross-sections are ellipses. `ap_over_ml` is the AP axis divided by the ML axis, and it is the same at every station (0.85 on the standard model). Circumference is the elliptic integral, not π times a diameter.

Station positions are **fractions of total length**:

```text
z_mm = length_fraction * total_length_mm
```

The standard stations are 0, 0.25, 0.50, 0.75, and 0.90. The 0.90 station is the distal circumference. The tip is a point at fraction 1 and has no circumference. A length change keeps the fractions and the circumference values, then recomputes `z_mm` and the cap.

Tolerances on the standard profile:

| Check | Tolerance | Why |
|---|---:|---|
| Circumference | 1 mm | About 0.3–0.4% of these perimeters. The inputs are exact numbers, so this is tighter than physical tape error. |
| Length | 0.05 mm | Cutting planes must find the proximal face at z = 0 and the tip at the total length. The last plane that still cuts a curve sits just short of the point tip. A pass is `abs(error) <= tolerance`, rounded to 1e-9 mm so a decimal boundary is not tripped by binary noise. |

A percent edit uses the **measured** base circumference. A configured value of 275 mm is not assumed.

## Public functions

```python
generate_limb(parameters: LimbParameters) -> cadquery.Shape
measure_limb(source, profile=None, *, length_fraction=None, z_mm=None) -> dict
validate_limb(shape, profile: dict) -> dict
modify_limb(request: dict) -> dict
compare_limb_versions(original, modified, *, original_profile=None, modified_profile=None, targets=None, tolerances=None) -> dict
```

`source`, `original`, and `modified` are a STEP path or the standard model id `synthetic-transtibial-standard`.

`parameters_from_profile`, `load_profile`, `profile_with_total_length`, and `updated_profile` update or read the JSON profile. They do not write the reference files.

## Modifications

| `operation` | Required fields | Effect |
|---|---|---|
| `set_section_circumference` | `section_fraction` or `section_id`, `circumference_mm` | Set that station's target, in mm. |
| `change_section_circumference_percent` | `section_fraction` or `section_id`, `change_percent` | New target = measured circumference × (1 + change_percent/100). |
| `set_total_length` | `total_length_mm` | Keep fractions and circumferences. Recompute z and the cap. |

`preserve` may list `total_length` and `proximal_circumference`. A request that both changes and preserves the same quantity is rejected before a solid is built.

`output_dir` is required. The reference JSON and STEP are never overwritten.

### Request

```json
{
  "base_model_id": "synthetic-transtibial-standard",
  "operation": "change_section_circumference_percent",
  "section_fraction": 0.5,
  "change_percent": 5.0,
  "preserve": ["total_length", "proximal_circumference"],
  "output_dir": "/tmp/limb-edit"
}
```

### Result

`ok` is true only when the rebuilt solid meets the new targets and the preservation constraints. `requested_target` is the number sent to the generator. `measurements` are taken from the STEP file after it is read back in.

```json
{
  "ok": true,
  "error": null,
  "clinical_use": false,
  "operation": "change_section_circumference_percent",
  "requested_target": 288.75,
  "requested_target_units": "mm",
  "base_measured_value": 275.0,
  "measured_from": "reimported_step",
  "measurements": {
    "units": "mm",
    "sections": [
      {
        "id": "q50",
        "measured_circumference_mm": 288.75,
        "target_circumference_mm": 288.75
      }
    ]
  },
  "files": {
    "step": "/tmp/limb-edit/candidate.step",
    "profile": "/tmp/limb-edit/candidate.json"
  }
}
```

The numbers above show the shape of the result. A real run fills them from the solid. The measured field is not a copy of the target; both are reported because they are different steps.

## Comparison

```python
compare_limb_versions(
    "data/reference/standardized_limb.step",
    "/tmp/limb-edit/candidate.step",
    original_profile=original_profile,
    modified_profile=modified_profile,
    targets={"circumference_50_percent_mm": 288.75, "total_length_mm": 140},
)
```

`middle_circumference_mm` is accepted as an alias for `circumference_50_percent_mm` in `targets`.

Each numeric row contains `before`, `after`, `absolute_change`, `percent_change`, `target`, `deviation_from_target`, and `within_tolerance`. `percent_change` is `null` when `before` is 0. A missing station has `"status": "missing"`. `within_tolerance` is `null` when no target was supplied.

Compared quantities: total length, circumferences at 0, 25%, 50%, 75%, and the distal reference (90%), volume, bounding-box widths, and solid validity.

Default comparison tolerances are 1 mm (circumference), 0.05 mm (length), 1000 mm³ (volume, only when a volume target is set), and 0.5 mm (bounding box, only when a box target is set).

## Error codes

| Code | When |
|---|---|
| `unknown_model` | Model id is not the standard id and no profile path was given. |
| `missing_file` | Profile or STEP path does not exist. |
| `invalid_step` | STEP file cannot be read. |
| `unsupported_operation` | Operation name is not one of the three above. |
| `invalid_section` | Fraction or id is not a station, or a query fraction is outside 0–1. |
| `invalid_value` | Wrong type, unsupported field, or a non-positive target. |
| `non_finite` | `NaN` or infinity. |
| `constraint_conflict` | The edit changes a quantity the request also preserves. |
| `protected_output` | Output would write the reference profile, STEP, or their directories. |
| `geometry_failed` | The new numbers do not make a monotone solid. |
| `export_failed` | STEP write failed. |
| `target_not_met` | Reimported solid missed a geometric check. |
| `constraint_violated` | A preserved measurement moved by more than its tolerance. |
| `no_intersection` | The cutting plane does not meet the solid. The tip is this case. |
| `invalid_geometry` | The shape is not one valid solid. |

## Known limitations

- Every station must share one `ap_over_ml`. The solid is a revolution scaled once along Y.
- The radius must not increase toward the tip. A distal circumference larger than the one proximal to it is rejected.
- The 6 mm cap blend is an absolute length. A very short total length, such as 20 mm, overlaps the previous station and is rejected.
- The in-memory kernel bounding box can extend past the trimmed tip. Length checks use cutting planes. After STEP reimport the box ends on the tip.
- The proximal end is a closed planar ellipse, not an open skin surface.
- Socket generation is a separate solid. See `SOCKET_CAD_DESIGN.md`. Comparing a limb with a socket is a separate step. See `LIMB_SOCKET_INTEGRATION.md`. These limb tools do not call a printer or Nemotron.

## Example

```python
from tools.cad.generate_limb import load_profile, parameters_from_profile, generate_limb
from tools.cad.measure_limb import measure_shape, section_circumference
from tools.cad.modify_limb import modify_limb
from tools.cad.validate_limb import validate_limb
from tools.cad.compare_limb_versions import compare_limb_versions

profile = load_profile()
shape = generate_limb(parameters_from_profile(profile))
before = section_circumference(shape, 70.0)[0]
report = validate_limb(shape, profile)

edited = modify_limb({
    "base_model_id": profile["model_id"],
    "operation": "change_section_circumference_percent",
    "section_fraction": 0.5,
    "change_percent": 5.0,
    "preserve": ["total_length", "proximal_circumference"],
    "output_dir": "/tmp/limb-edit",
})
compared = compare_limb_versions(
    "data/reference/standardized_limb.step",
    edited["files"]["step"],
    original_profile=profile,
    modified_profile=edited["profile"],
    targets={"circumference_50_percent_mm": edited["requested_target"]},
)
```

## Tests

```bash
uv run pytest
```

CAD tests import the reference STEP and rebuild a solid only when an edit or a reproducibility check needs one. They write candidates under pytest's temporary directories.
