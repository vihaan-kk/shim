# Shim synthetic limb and socket dataset

Shim runs on **synthetic data generated for this hackathon**, published here with its methodology under the hackathon's open-data rule ("Synthetic Data: teams may generate synthetic datasets during the hackathon, provided they publish the resulting data and methodology openly").

**No patient data was used, collected or derived.** The limb is a fully synthetic shape for nonclinical software demonstration. It is not a reconstruction of anyone's anatomy, and nothing here is for fitting, wear or clinical use.

## What's in the dataset

| File | What it is |
|---|---|
| [`profiles/standard_limb.json`](profiles/standard_limb.json) | The **standard residual limb** (`synthetic-transtibial-standard` v1.0.0) as parameters: length, five elliptical cross-sections, distal cap, coordinate frame, tolerances. |
| [`profiles/standard_socket.json`](profiles/standard_socket.json) | The **standard socket** (`synthetic-transtibial-socket-standard` v1.0.0) as parameters built around that limb: clearance, wall, depth, brim, tolerances. |
| [`reference/standardized_limb.step`](reference/standardized_limb.step), [`.stl`](reference/standardized_limb.stl) | The limb solid generated from its profile. |
| [`reference/standardized_limb_validation.json`](reference/standardized_limb_validation.json) | Its validation report: target vs measured circumference at every section, length, solid checks. |
| [`reference/standardized_socket.step`](reference/standardized_socket.step), [`.stl`](reference/standardized_socket.stl) | The socket solid generated from its profile and the limb. |
| [`reference/standardized_socket_report.json`](reference/standardized_socket_report.json) | Its validation report: solid, dimensions, wall thickness, opening, closed end, reference to the limb. |

Units are millimetres. The frame: the proximal (open) end is at z = 0, distal is +Z, X is medial-lateral, Y is anterior-posterior.

### The standard limb

| Section | z (mm) | Circumference (mm) | AP / ML ratio |
|---|---|---|---|
| `proximal` | 0 | 300 | 0.85 |
| `q25` | 35 | 290 | 0.85 |
| `q50` | 70 | 275 | 0.85 |
| `q75` | 105 | 255 | 0.85 |
| `distal_reference` | 126 | 235 | 0.85 |

The length is 140 mm, with an ellipsoidal cap from z = 126 to the tip at z = 140. These are round demonstration values chosen by the team to give a plausible, smoothly tapering below-knee shape. They are **not** measured from people or taken from another dataset.

### The standard socket

- Built around the limb, with 2 mm inner clearance, a 5 mm wall (1.5 mm minimum), an 8 mm closed end, 152 mm depth, and an 8 mm brim flare over 22 mm.
- The inner surface follows the limb, and the wall is added outward.

## How it is generated (methodology)

1. **Limb solid** ([`tools/cad/generate_limb.py`](../tools/cad/generate_limb.py), CadQuery / OpenCascade):
   - Each section is an ellipse whose medial-lateral semi-axis is solved from the target circumference (complete elliptic integral) and the shared AP/ML ratio.
   - The medial-lateral radius profile, including the rounded cap, is revolved about Z, then scaled along Y by the AP/ML ratio.
   - A planar ellipse closes the proximal end, so the result is one watertight solid.
2. **Limb validation** ([`tools/cad/validate_limb.py`](../tools/cad/validate_limb.py)): the solid is cut at every section and the measured circumference is compared with the target. The tolerance is 1 mm; the reference limb lands within 0.001 mm. Length, validity and single-solid checks also run.
3. **Socket solid** ([`tools/cad/generate_socket.py`](../tools/cad/generate_socket.py)): a wall cross-section is built from the limb's sections. Its inner edge is offset by the clearance, its outer edge adds the wall, and it includes the brim and the closed distal end. The cross-section is revolved and scaled the same way as the limb.
4. **Socket validation** ([`tools/cad/validate_socket.py`](../tools/cad/validate_socket.py)): checks four groups:
   - **CAD validity:** a valid, single solid with positive volume;
   - **dimensions:** depth, opening and circumferences against the profile;
   - **structure:** minimum wall, opening open, closed end closed;
   - **reference integrity:** the socket's geometry hash of the limb it was built for.

### Variants generated during use

- **Every request makes new synthetic data from this base.** When a user (through the agent) changes the limb's length or circumferences, [`tools/cad/questionnaire.py`](../tools/cad/questionnaire.py) resizes the standard limb's sections:
  - axially, for length;
  - by per-station factors, for the proximal, mid and distal circumferences;
  - it rejects inconsistent inputs, such as a distal circumference larger than the proximal.
- **The tools then rebuild and re-measure the solid,** and refuse it if it misses the requested values (2 mm in length, max(3 mm, 2%) in circumference).
- **Sockets are re-fitted, edited** (wall, depth, opening, clearance, engraved labels) **and re-validated the same way.**
- **Each variant is saved as a revision** (profile, STEP, metadata and validation report) under `workspace/revisions/`, so any variant can be regenerated exactly from its parameters.

## Reproduce it

Regenerate the reference set from the two profiles (about 30 s). This rewrites the files in `data/reference/`:

```bash
uv run python -m tools.cad.generate_limb
```

```bash
uv run python -m tools.cad.generate_socket
```

Both print or write a report with `"passed": true`. The validation JSON records absolute file paths, so those two fields differ between machines; the geometry does not.

## Provenance and license

- **Created by:** the Shim team (CAD and data by Yutian Gong), October 2026, for the NVIDIA x Red Hat Small Models Hack.
- **Sources:** none external. The data is hand-authored parameters plus deterministic CAD generation. The original design plan considered the open [OpenLimbTT](https://github.com/abel-research/OpenLimbTT) dataset as a starting shape (see [`docs/README_LONG.md`](../docs/README_LONG.md)). It is **not** used in this dataset or the running system.
- **Publication:** this folder, the generator code and this methodology are the published dataset. The repository must be public (or this folder published separately) for it to be open, and no license is set yet; the team should add one.
