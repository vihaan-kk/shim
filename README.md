# Transtibial Prosthetic Socket Agent

An SLM-powered agent that customizes a synthetic below-knee residual limb from a short questionnaire, builds a separate demonstration socket shell, and prepares that shell for a confirmed virtual 3D print.

The model does not deform meshes or operate the printer. It chooses a tool and fills in structured arguments. Deterministic Python code checks those arguments, edits geometry, validates the result, and returns a typed result. The agent asks when a measurement is missing or inconsistent, keeps earlier confirmed values, and never starts a print without a separate human confirmation.

**Status:** design plan. This repository does not yet contain an agent, templates, geometry code, a slicer profile, or a printer integration. Nothing in this document is an implemented component.

**Dataset:** [OpenLimbTT](https://github.com/abel-research/OpenLimbTT) version `2025-07`. The STL files are not vendored here.

**Clinical boundary:** measurement-driven reconstruction is an approximation of a standardized template. It is not a reconstruction of a person's anatomy. Generated sockets are non-wearable demonstration prototypes. A passing geometry check means the mesh is closed, inside the configured wall and printer limits, and ready to slice. It does not establish fit, comfort, load transfer, or safety on a person.

The innovation this prototype is built to show is the model's ability to coordinate a multi-stage, stateful path from a transtibial questionnaire to a virtual print.

## How to read this plan

| Kind | Meaning |
|---|---|
| Verified | Checked against the OpenLimbTT paper, the GitHub file listing, or vendor documentation. |
| Proposed | A hackathon design choice. It is not implemented. |
| Unresolved | Must be settled by a proof of concept before later stages depend on it. |

## Contents

1. [Project Overview and Problem Statement](#1-project-overview-and-problem-statement)
2. [Scope and Nonclinical Demonstration Boundary](#2-scope-and-nonclinical-demonstration-boundary)
3. [Target User Experience](#3-target-user-experience)
4. [OpenLimbTT Dataset and Standardized Templates](#4-openlimbtt-dataset-and-standardized-templates)
5. [Practitioner Questionnaire and Measurement Schema](#5-practitioner-questionnaire-and-measurement-schema)
6. [Residual-Limb STL Customization Algorithm](#6-residual-limb-stl-customization-algorithm)
7. [Conversational Refinement and Version Control](#7-conversational-refinement-and-version-control)
8. [Prosthetic Socket CAD Generation](#8-prosthetic-socket-cad-generation)
9. [Geometry Validation](#9-geometry-validation)
10. [SLM Tool-Calling Architecture](#10-slm-tool-calling-architecture)
11. [Tool Registry and JSON Contracts](#11-tool-registry-and-json-contracts)
12. [Slicing and OctoPrint Integration](#12-slicing-and-octoprint-integration)
13. [Frontend Architecture](#13-frontend-architecture)
14. [End-to-End Demo Scenarios](#14-end-to-end-demo-scenarios)
15. [MVP Implementation Milestones](#15-mvp-implementation-milestones)
16. [Research References and Licenses](#16-research-references-and-licenses)
17. [Technical Risks and Limitations](#17-technical-risks-and-limitations)

## 1. Project Overview and Problem Statement

Preparing even a demonstration below-knee socket means importing a shape, deciding how large it should be, building a wall, checking the mesh, slicing, and driving printer software. Each step is a different program. The person who knows those programs becomes the bottleneck, including when the shape is only a synthetic stand-in.

This agent is that demonstration path, for transtibial geometry only:

1. The practitioner selects a standardized OpenLimbTT residual-limb template.
2. They enter geometric measurements they can collect with a tape, a ruler, and, optionally, calipers.
3. The model calls deterministic tools that copy the template, deform it, and write a new residual-limb STL.
4. They can correct a number or ask for a supported shape change in ordinary language. Each accepted change writes another limb revision and leaves other confirmed measurements unchanged.
5. The model then calls a separate CAD tool that builds a demonstration socket shell around the current limb revision. The limb STL is preserved.
6. After geometric validation, slicing, and an explicit confirmation, the agent starts a virtual print and writes a fabrication report.

Four stages stay separate.

| Stage | Question it answers | What this prototype does |
|---|---|---|
| Residual-limb geometry | What reference surface are we demonstrating? | Scale and gently reshape a synthetic transtibial template from a few measurements. Output is a limb STL. |
| Socket geometry | What closed shell surrounds that reference? | Constant clearance, constant wall, a planar proximal opening, a rounded rim. Output is a different STL. |
| Socket rectification | Where should a wearable socket load or unload tissue? | Out of scope. No patellar-tendon bar, no relief map, no pressure prediction. |
| Manufacturability | Can this shell be sliced on the configured virtual printer? | Closure, wall, self-intersection, build volume, overhangs, then a confirmed virtual job. |

## 2. Scope and Nonclinical Demonstration Boundary

The prototype customizes synthetic transtibial residual limbs and generates below-knee demonstration socket shells.

In scope:

- A library of three OpenLimbTT-derived skin templates, with two further transtibial shape variants as a stretch.
- A questionnaire whose required items are residual length and two circumferences.
- Conversational corrections that update one parameter.
- A constant-offset demonstration shell, mesh checks, one slicing profile, and a gated virtual print.
- An audit report that cites OpenLimbTT and states the nonclinical limit.

Outside this prototype:

- Identifiable scans, medical records, or any claim that the questionnaire recovers a patient.
- Clinical rectification, liner prescription, suspension, alignment, or a test-socket fitting.
- Wearable sockets and physical-printer operation.
- Any statement that a geometric clearance or a wall thickness is a validated fit.
- Decorative patterns, a general mesh editor, and biomechanical simulation.

A tape measurement is something a trained practitioner can take at the point of care. Placing that tape on the correct anatomical level is a palpation skill. The questionnaire shows a diagram and names one landmark. The system does not infer a landmark the practitioner did not identify.

## 3. Target User Experience

**User:** a prosthetics practitioner, technician, or researcher who can take a residual-limb measurement and should not have to operate CAD, a slicer, and printer software by hand.

**Session:**

1. Template cards show the available transtibial shapes. The practitioner picks one.
2. The questionnaire asks for length, proximal circumference, and distal circumference. Optional fields stay collapsed.
3. The limb viewer shows the customized residual-limb STL, labeled as the limb, not the socket.
4. Chat and the form write the same measurement document. "Change the proximal circumference to 310 mm" updates that field only.
5. A comparison view shows the previous and current limb revisions with measured differences.
6. "Generate a demonstration socket" produces a second STL. The socket viewer is a separate panel.
7. Validation cards report mesh checks. They are labeled geometric checks.
8. The practitioner approves the single print profile, then confirms the virtual print on a different button. Progress comes from the printer read-back.

The page never overlays the limb and the socket as if they were one object. Titles stay "Residual limb" and "Socket shell."

## 4. OpenLimbTT Dataset and Standardized Templates

### 4.1 Verified dataset facts

Sources: the [OpenLimbTT paper](https://doi.org/10.1017/dce.2025.10019), the [repository README](https://github.com/abel-research/OpenLimbTT), version notes for `2025-07`, the generation script, and the GitHub contents listing.

- Version `2025-07` is a statistical shape model trained on 33 transtibial limbs (4 female, 29 male). Training required amputation through the tibial diaphysis. The authors describe limited statistical generality.
- Mode 1 is amputation height, about 52.2% of variance. Table 2 labels the high percentile long and the low percentile short.
- Mode 2 is slender versus bulbous soft tissue, about 16.7% of variance. Table 2 labels the high percentile bulbous and the low percentile slender. The repository describes this axis as a bulbous-to-conical profile. "Conical" in the library below means the slender direction of mode 2, and only after the mesh is inspected.
- About 69% of variance is in the first two modes, and about 95% is in the first ten. Later modes include bone scale, distal soft-tissue coverage, and knee flexion in the scans. Those are not questionnaire parameters.
- Training limbs retained a median 36% of intact tibia length (range 18–60%).
- Shapes are normalized by estimated intact tibia length, because residual length is not a stable fraction of the intact limb. The generation script suggests 378.52 mm as the training-set average and gives a range of 313.05–466.34 mm. **Unresolved:** which published STL, if either, is already in millimetres. STL has no unit field.
- Alignment follows the International Society of Biomechanics convention used in the paper: the xz plane is transverse, yz is coronal, and xy is sagittal, so Y is longitudinal. Left limbs were mirrored. The tibia centroid was moved to the origin. The proximal boundary is an open trim, one patella height above the patella. There is no labeled mid-patellar-tendon vertex.
- Leave-one-out recreation of a left-out shape, given full surface correspondence, is 1.82–5.75 mm RMSE (median 3.40 mm). That is a lower bound for error when the whole skin is known. A tape questionnaire is coarser.
- The generation script depends on [ampscan](https://github.com/abel-research/ampscan) and on local paths, and it warns that some mode combinations are not anatomical. `Components16.npy` does not match the filenames the script comments request. The script is not a drop-in tool. Raw MRI and CT are not in the release.

Binary STL size is `84 + 50 × triangles`. These published sizes divide evenly:

| File in `version-2025-07` | Bytes | Triangles | What it is safe to say |
|---|---|---|---|
| `Mean-Skin.stl` | 958,134 | 19,161 | Skin surface. Different SHA from the full-size file. |
| `Mean-Skin-Full-Size.stl` | 958,134 | 19,161 | Same triangle count, different bytes. Filename does not prove millimetres. |
| `Mean-Limb.stl` | 1,945,584 | 38,910 | Combined limb. Same byte size as every mode file below. |
| `Mean-Limb-Full-Size.stl` | 1,945,584 | 38,910 | Combined limb, different SHA from `Mean-Limb.stl`. |
| `Mean-Bones-Full-Size.stl` | 987,534 | 19,749 | Bones. Never a socket reference. |
| `Mode1-20th-Mode2-Mean.stl` | 1,945,584 | 38,910 | Mode-combination file. Same class as the combined limb. |
| `Mode1-80th-Mode2-Mean.stl` | 1,945,584 | 38,910 | Same. |
| `Mode1-Mean-Mode2-20th.stl` | 1,945,584 | 38,910 | Same. |
| `Mode1-Mean-Mode2-80th.stl` | 1,945,584 | 38,910 | Same. |
| Four corner files, `Mode1-{20th,80th}-Mode2-{20th,80th}.stl` | 1,945,584 each | 38,910 each | Length and profile vary together. Not used as templates. |

**Unresolved:** whether each mode file is one body or several. The byte size matches `Mean-Limb.stl`, which is strong evidence that bones are included. A mode file becomes a skin template only after a component split isolates one open skin surface.

**Unresolved:** whether `Mean-Skin-Full-Size.stl` is a uniformly scaled copy of `Mean-Skin.stl`. Same triangle count is compatible with a scale and also with a re-export. The first experiment measures both bounding boxes.

### 4.2 Recommended templates

Use files that change one mode at a time. Do not invent intermediate shapes, and do not treat a corner file as a pure short or pure conical limb.

| ID | Intended demonstration shape | Published file | MVP |
|---|---|---|---|
| `tt_mean` | Average transtibial skin | `version-2025-07/Mean-Skin.stl` | Required. The demo runs on this file alone. |
| `tt_short` | Shorter residual limb, mean soft-tissue profile | `version-2025-07/Mode1-20th-Mode2-Mean.stl` | Third template, only after a clean skin split. Paper: low mode 1 is the short direction. |
| `tt_long` | Longer residual limb, mean soft-tissue profile | `version-2025-07/Mode1-80th-Mode2-Mean.stl` | Third template, same condition. Paper: high mode 1 is the long direction. |
| `tt_conical` | Mean length, more slender profile | `version-2025-07/Mode1-Mean-Mode2-20th.stl` | Stretch. Confirm visually before the card says "conical." |
| `tt_bulbous` | Mean length, fuller profile | `version-2025-07/Mode1-Mean-Mode2-80th.stl` | Stretch. Confirm visually before the card says "bulbous." |

The published percentiles are 20th and 80th, not the 2.5th and 97.5th extremes plotted in the paper. The sign convention is supported by Table 2 and still has to be checked on the actual meshes.

`Mean-Skin-Full-Size.stl` is a unit candidate for `tt_mean`, not a sixth anatomy. Bones files and combined `Mean-Limb` files are never offset into a socket. If the skin split fails, the library is `tt_mean` only, and length and circumference stay inside the clamps in [section 6](#6-residual-limb-stl-customization-algorithm).

### 4.3 Template sidecar

Each accepted template gets a hand-authored sidecar after inspection. The sidecar is data. It is not a landmark detector.

```yaml
template_id: tt_mean
source_repo: abel-research/OpenLimbTT
source_version: "2025-07"
source_file: Mean-Skin.stl
source_sha256: <filled when vendored>
license: CC-BY-SA-4.0
units_status: unconfirmed   # mm only after the bounding-box check
axis: [0, 1, 0]
proximal_end: open_boundary
distal_end: closed_tip
reference_station_fraction: <annotated>  # demo station, not a detected tendon
reference_to_distal_mm: <measured after scaling>
```

The original file is stored unchanged. Customization always copies it. Derived meshes stay under CC BY-SA 4.0, and the fabrication report cites the paper.

## 5. Practitioner Questionnaire and Measurement Schema

### 5.1 What measurements can support

Published practice collects a dense series, and even that series is a weak shape record.

- ISO 8548-2:2020 defines how to describe a lower-limb amputation stump. A secondary summary of Table 8 lists transtibial team measurements as L3, L6, and C4, and prosthetist-only measurements as C6x, W4, W5, and A2. The full figures were not re-derived from the paid standard. The standard also records skin, circulation, pain, and joint function. Those items describe the person. They do not define a mesh.
- Casting guides ask for circumferences about every 2 cm, plus the patella, patellar tendon, tibial crest, and fibular head ([Össur notes](https://cdn.ortoped.ca/Assets/PDFs/ossur_icerossoriginallockingliner_instructions.pdf); [Blatchford guide](https://www.blatchfordmobility.com/media/wffjvrsq/936570-liner-casting-guide_web.pdf)).
- Seminati et al. found tape volume ICCs above 0.9, with shape error above 10% for cross-sectional area and above 5% for perimeter ([2022](https://doi.org/10.1097/pxr.0000000000000105)).
- Geil found ordinary transtibial measurements usable on foam models, and found the VAPC caliper in that study inaccurate ([2005](https://doi.org/10.1682/jrrd.2004.05.0054)).
- On 67 UK scans, Dickinson et al. reported mean length from patellar tendon to distal tip of 156 mm (SD 29) and mean patellar-tendon perimeter of 383 mm (SD 40) ([2021](https://doi.org/10.3390/prosthesis3040027)).
- A volume review reports a 55-person series with mean residual length 11.08 cm (SD 2.81, range 6–18), measured from the tibial tubercle rather than the patellar tendon ([Sanders and Fatone, 2011](https://pmc.ncbi.nlm.nih.gov/articles/PMC4423813/)). Landmark choice changes the number.

US 7,617,072 describes rescaling cross-sections of a reference limb from a height and a few circumferences. That is prior art for the algorithm in section 6. The result is a scaled reference, not imaged anatomy. This project implements its own vertex update for a synthetic demo.

Clinical fitting still needs tissue tolerance, scars, pain, joint range, volume state, liner, suspension, alignment, and a test fitting. The geometry engine does not accept those fields.

### 5.2 Stations

Stations are distances along the residual limb, not fractions of intact tibia length.

| Station | Definition shown to the user | Role |
|---|---|---|
| Length | Knee extended. Mid-patellar tendon to the distal end. | Required. Axial warp. |
| P | Circumference perpendicular to the long axis, 40 mm distal to the mid-patellar tendon. | Required. Proximal radial scale. |
| D | Circumference perpendicular to the long axis, 40 mm proximal to the distal end. | Required. Distal radial scale. |
| M | Circumference halfway between P and D. | Optional. One extra interpolation knot. |
| Section at P | Anterior-posterior depth and medial-lateral width, same level as P. | Optional. Section aspect ratio. |
| Distal end | Template, slightly rounder, or slightly more tapered. | Optional. Local cap blend. |

The 40 mm offset follows the 4 cm interval used in measurement studies. It is a demo convention, not an ISO reference level. The mid-patellar tendon is the midpoint of the tendon between origin and insertion. The Össur guide's "distal edge of the patella" is a different landmark and is not accepted as an alias.

Posture may be recorded as `supine`, `sitting`, or `standing`. OpenLimbTT scans were supine. The demo does not correct for posture. A non-supine choice is copied into the report.

Form ranges are what the page accepts. Each template then applies a tighter window from its own mesh. A typed number can be in range and still be outside that template.

### 5.3 Fields

#### Length — required

- **Question:** "With the knee extended, what is the length from the mid-patellar tendon to the distal end?"
- **Input:** millimetres, form range 50–300, field `length_mm`.
- **Collected with:** a tape or ruler between those two points, shown on the form diagram.
- **Controls:** axial scale of vertices distal to the annotated reference station. Proximal vertices stay fixed. Circumferences are not changed by this step.
- **If missing:** customization does not run.
- **If outside 0.70–1.40 times that template's reference-to-distal length:** `outside_template`. The agent may name a closer template (`tt_short` or `tt_long`) and waits for a yes. It does not extrapolate.

#### Proximal circumference — required

- **Question:** "What is the circumference 40 mm below the mid-patellar tendon, perpendicular to the long axis?"
- **Input:** millimetres, form range 150–550, station `P`.
- **Collected with:** a tape, snug, without compressing tissue. Default condition `bare`, because the templates are skin. `over_liner` is recorded and does not change the mesh rule.
- **Controls:** uniform radial scale of the cross-section at P. The section outline is preserved.
- **If the implied scale is outside 0.75–1.35 of the template perimeter at P:** `outside_template`. The agent reports the template perimeter and does not apply the scale.

#### Distal circumference — required

- **Question:** "What is the circumference 40 mm above the distal end, perpendicular to the long axis?"
- **Input:** millimetres, form range 100–500, station `D`.
- **Collected with:** the same tape method. Support the limb so the tape does not pull the tip into a cone.
- **Controls:** radial scale at D. Scales between P and D are interpolated. The distal cap uses the D scale.
- **If D exceeds P by more than 15%:** `inconsistent_taper`. The agent asks which value to correct.
- **If the scale is outside 0.75–1.35:** `outside_template`.

#### Mid circumference — optional

- **Question:** "Optional: circumference halfway between the proximal and distal levels?"
- **Input:** millimetres, form range 100–550, station `M`.
- **Controls:** one interpolation knot. It cannot create a bulge away from the station.
- **If missing:** the midpoint scale is interpolated from P and D, and the result says so.
- **If M falls outside the P–D band by more than 20 mm:** `inconsistent_profile`.

#### Anterior-posterior and medial-lateral widths — optional

- **Question:** "Optional: at the proximal circumference level, what are the anterior-posterior depth and the medial-lateral width?"
- **Input:** two millimetre values, each 40–200. Both or neither.
- **Collected with:** calipers in the sagittal and frontal directions. Geil's results favor an ordinary caliper.
- **Controls:** AP/ML sets anisotropic scale in the section plane, then the circumference restores overall size. Circumference wins if they disagree.
- **MVP:** off until the isotropic path remeasures within tolerance.
- **If the ellipse and the tape disagree by more than 15%:** `inconsistent_section`.

#### Distal-end shape — optional

- **Question:** "Optional: should the distal end stay like the template, look slightly rounder, or look slightly more tapered?"
- **Input:** `template`, `rounder`, or `more_tapered`, mapped to `distal_roundness` 0, +0.15, or −0.15, clamped to [−0.30, +0.30].
- **Controls:** a blend of the last 8% of length toward a hemisphere whose radius is the last stable cross-section. It does not reconstruct the surgical end.
- **MVP:** conversation only, after the radial-scale experiment passes.
- **Other tip descriptions** return `unsupported_shape`. The agent names the three choices.

#### Side — optional

- **Input:** `left` or `right`. Default `right`, matching the mirrored OpenLimbTT orientation.
- **Controls:** a mirror. If omitted, the view is labeled with the template side.

#### Ignored if the user types them

Scars, pain, skin condition, knee contracture, strength, liner model, body weight, and activity level can be stored in the session note. They are `unsupported_field` on a geometry call. Knee flexion is visible in OpenLimbTT mode 4 as a scan artifact; the template is not bent to match a contracture. Wall thickness is chosen later as a socket argument, not from body weight.

### 5.4 Minimum questionnaire

The live demo asks length, station P, and station D. Mid circumference, AP/ML, distal shape, and side are accepted when volunteered. The form states that these numbers move a synthetic template and do not reconstruct a residual limb.

Natural language fills the same document. "About 15 cm long, 30 cm near the top and 24 cm near the end" becomes `length_mm: 150`, P `300`, D `240`, with `precision: approximate`. The agent repeats the numbers before the first customization.

## 6. Residual-Limb STL Customization Algorithm

### 6.1 Options

| Approach | Fit to OpenLimbTT and this questionnaire | Decision |
|---|---|---|
| Axial warp, then cross-sectional radial scale with monotone interpolation | Uses length and circumferences directly. Moves existing vertices, so face count stays constant. One deterministic tool. | **MVP.** |
| Global uniform scale | One factor cannot meet a length and two circumferences. | Labeled fallback only. |
| PCA score fitting | OpenLimbTT is a PCA model. The published mode STLs match the combined limb, not a skin-only mode matrix. Two circumferences do not identify mode scores. The authors warn that some combinations are not anatomical. Full-surface recreation error is already several millimetres. | Not the MVP. |
| Non-rigid registration | Needs a target surface. Circumferences are not a surface. | Not used. |
| Automatic landmarks | The release has no labeled tendon, crest, or fibular head. | One reference station is annotated by hand in the sidecar. |
| Blender sculpt | Hard to expose as a pure function. Interactive add-on code is not copied. | Fallback for the socket solid only. |

Libraries: [trimesh](https://trimsh.org/) to load, slice, and export; NumPy for vertex updates; SciPy `PchipInterpolator` for the scale curve. [manifold3d](https://github.com/elalish/manifold) is for the socket solid, not the limb edit.

### 6.2 Steps

`customize_residual_limb` copies the template and writes `limbs/<limb_id>/<revision>/limb.stl`. It never edits the template.

1. Require one open skin surface. A combined mesh returns `combined_mesh`.
2. Refuse unless the sidecar says `units_status: mm`.
3. Use the sidecar axis, and check that it is still the longest skin dimension. Distal is the closed tip. Proximal is the open boundary.
4. **Length.** Let `s = 0` at the annotated reference station and `s = 1` at the tip. Vertices with `s < 0` stay fixed. Vertices with `s ≥ 0` move along the axis by `s' = s × (length_target / length_template)`. Clamp the ratio to 0.70–1.40. This does not change section size.
5. Measure perimeters at P, M, and D on the warped copy, on planes perpendicular to the axis. A station with more than one loop is shifted by 2% of length, up to three times, then `unstable_station` if it is still ambiguous.
6. At each provided station, `scale = target_perimeter / measured_perimeter`. Clamp each knot to 0.75–1.35. Interpolate with a monotone cubic. Missing optional stations add no knot.
7. Move each vertex: `position' = centroid(s) + scale(s) × (position − centroid(s))`. Centroids are sampled and interpolated. The template's oval or irregular section is kept. The limb is not rebuilt as stacked circles.
8. If AP and ML were accepted, apply that ratio in the plane first, then the uniform scale that restores the target perimeter.
9. On the last 8% of length, hold the station-D scale. If requested, blend toward a hemisphere of the last stable radius by `distal_roundness`.
10. Remeasure. Keep the revision only if length is within 2 mm and every targeted perimeter is within 3 mm or 2%, whichever is larger. Otherwise `target_not_met`, and the failed file is deleted.
11. Face count must equal the template. The proximal boundary must still be one loop. Vertices must be finite. A self-intersection test runs when the build has one; if it does not, the result says the test was skipped.

This leaves the tibial crest, fibular head, and muscle bulk between stations as they were on the template. Error against a real limb is unknown.

### 6.3 Fallback

If step 10 fails twice, one retry may write `method: coarse_uniform_scale`, using the mean of the accepted station scales. The agent says the stations were not matched independently. If that fails, the tool exports the unedited template in millimetres and records the measurements as requested and not applied.

## 7. Conversational Refinement and Version Control

The transcript is not the measurement record. The session document is.

```json
{
  "limb_id": "limb_01",
  "template_id": "tt_mean",
  "revision_id": "r3",
  "parent_revision_id": "r2",
  "confirmed": {
    "length_mm": 135,
    "stations": [
      {"id": "P", "circumference_mm": 310},
      {"id": "D", "circumference_mm": 240}
    ],
    "distal_roundness": 0.15
  },
  "locks": ["length_mm", "P", "D"]
}
```

`locks` are fields the user has confirmed and has not since corrected. The model proposes a patch. The tool applies it.

| Utterance | Patch | Behavior |
|---|---|---|
| "15 cm long, 30 cm at the top, 24 cm at the end." | Sets length, P, and D. | Repeat the numbers. `validate_measurements`, then `customize_residual_limb`. |
| "Change the proximal circumference to 310 mm." | Correction of P only. | `correction: true` on P. Length and D stay locked. New revision. Remeasure. |
| "The residual limb should be 15 mm shorter." | `length_mm` becomes the locked length minus 15. | Requires a locked length. Otherwise ask. Does not change circumferences. Revalidate against the template window. |
| "Make the distal shape slightly more rounded." | `distal_roundness` +0.15 if still inside range. | "Slightly" is defined as 0.15. State the value used. "Much rounder" asks for a supported step. |
| "A bit longer." | No number. | Ask for a length in millimetres. |
| "Relieve the fibular head." | Unsupported. | Say that local relief is outside this demonstration. Write nothing. |
| "Make the wall 5 mm" while a limb is current. | Socket parameter. | Do not edit the limb. Call `modify_socket_geometry` if a socket exists; otherwise ask to generate one. |

Tool rules:

- A locked field that changes without `correction: true` returns `unconfirmed_overwrite` and writes nothing.
- Every success creates a new revision. Parents remain.
- The tool remeasures and returns station errors.
- `compare_limb_versions` returns length delta, perimeter deltas, bounding-box delta, and mean and max radial difference.
- Two failures on the same patch stop the loop. The last good revision stays current.

Limb revisions are `r1`, `r2`, … Socket revisions are a separate series and point at the limb revision they used. A new limb revision invalidates the socket certificate and both print confirmations.

## 8. Prosthetic Socket CAD Generation

The socket tool reads a limb revision and writes a new mesh. It does not read the questionnaire and it does not rectify. The limb STL stays on disk.

Geometric precedents, not fit rules:

- Facoetti, Colombo, Rizzi, and colleagues offset a stump surface and thicken outward, with a shop thickness range of about 2–6 mm ([2010](https://doi.org/10.3722/cadaps.2010.723-737)).
- Published fused-filament transtibial sockets are often printed near 4 mm, with local reinforcement treated as its own design problem ([van der Stelt et al., 2022](https://doi.org/10.3390/prosthesis4040048)).

Clearance here is an air gap in the mesh. Wall thickness is a solid thickness. Neither is a liner specification or a load rating.

[uFit](https://github.com/ortigital/ufit-blender) sequences import, thickness, trim, and STL export for transtibial sockets inside Blender. A current public tree is [Ugani-Prosthetics/ufit-blender](https://github.com/Ugani-Prosthetics/ufit-blender). It is interactive and is not called. If manifold3d cannot close a shell, the fallback is a Blender subprocess with our own Solidify script.

Proposed procedure for `generate_socket_shell`:

1. Copy the limb revision. Orient the long axis to printer Z, distal tip at minimum Z, proximal opening toward +Z.
2. Cut a proximal opening at `trim_fraction` of the reference-to-distal segment. Default 0.15, allowed 0.05–0.35. This is a plane. It is not a clinical trimline.
3. Offset outward by `clearance_mm` (0–3, default 1.5). Zero follows the limb surface.
4. Thicken outward by `wall_thickness_mm` (2.0–6.0, default 4.0).
5. Close inner wall, outer wall, and a rim annulus into one watertight solid. The cavity is inside the solid. The mesh sent to the slicer has no open boundary.
6. Round the rim by `rim_radius_mm` 0–3 without dropping the local wall below 2.0 mm.
7. Write `sockets/<socket_id>/<revision>/socket.stl`. Leave the limb file untouched.

`modify_socket_geometry` regenerates from the same limb revision. Fields omitted from the call are copied from the parent socket. A locked socket field changes only with `correction: true`.

If the offset fails, the limb revision is kept and nothing is uploaded. One retry may set `rim_radius_mm` to 0. A second failure stops. The last-resort stand-in is a pre-authored closed shell around unedited `tt_mean` at the default wall, labeled as a stand-in that does not reflect the questionnaire. It exists so the print path can be shown. The report says the measurements were not applied to the shell.

## 9. Geometry Validation

Validation is a manufacturability check. It is not a clinical certification.

Limb revision acceptance, inside `customize_residual_limb`:

| Check | Pass |
|---|---|
| Input | One open skin surface. |
| Units | Sidecar says `mm`. |
| Targets | Length within 2 mm. Each targeted perimeter within 3 mm or 2%. |
| Topology | Face count unchanged. One proximal boundary loop. |
| Clamps | Length ratio 0.70–1.40. Section scale 0.75–1.35. |

Socket certificate, inside `validate_socket_geometry`. A failed check is `status: success` with `data.passed: false`, so the model can read the numbers. `certificate_id` is minted only when every required check passes.

| Check | Pass | Certainty |
|---|---|---|
| Watertight, consistent winding, one component | trimesh flags | Straightforward. |
| Sampled wall thickness | At least 2.0 mm unless a stricter argument is set | Straightforward to sample; a full field is unnecessary for the demo. |
| Self-intersection | None reported | Uncertain. Run it if the library call is reliable; otherwise record `not_run`. |
| Build volume | Bounding box inside `tt_draft_028` | Straightforward once the profile bed is fixed. |
| Overhang | No face steeper than 55° from +Z | Straightforward. |

The agent may, after a failed certificate:

- raise wall thickness by at most 1.0 mm, staying inside 2.0–6.0 mm, through `modify_socket_geometry`
- retry once with rim radius 0
- try four fixed rotations if only the overhang check failed

Length, circumferences, template choice, and edits outside those bands require `ask_user`. After two unsuccessful repairs, the agent stops and reports the measurements. The limb file is not rewritten to hide a socket failure.

Safety rules enforced in tool code:

- Arguments are checked before any mesh or network call.
- Template files and earlier revisions are immutable.
- A new limb revision invalidates the socket certificate and both confirmations.
- `slice_model` requires a current certificate and a matching slice confirmation.
- `start_print` requires a different confirmation, a ready virtual printer, and a ledger check.
- The agent never reports a part printed because a command was accepted.
- The fabrication report states that the limb is a scaled OpenLimbTT template, the socket is a demonstration shell, and the checks are geometric.

## 10. SLM Tool-Calling Architecture

```text
Browser
  template cards, questionnaire, chat
  limb viewer, comparison, socket viewer
  validation cards, two confirmation buttons
        |
        v
Python agent
  measurement document, phase filter, confirmation store, audit log
        |
        +-- Nemotron 3.5 Lightning through Red Hat vLLM
        |
        +-- Geometry functions, in process
        |     OpenLimbTT sidecars, limb deformation, socket shell
        |     trimesh, NumPy, SciPy, manifold3d
        |
        +-- Manufacturing functions, in process
              PrusaSlicer CLI, OctoPrint Virtual Printer
              SQLite for revisions, jobs, confirmations, audit
```

Direct Python functions are the MVP. vLLM already returns OpenAI-style tool calls. MCP servers are a later split, not a weekend dependency.

The model never receives the OctoPrint API key, a filesystem path, or a raw G-code channel. Tools accept ids. The server resolves them.

| Model | Code |
|---|---|
| Understand the request, notice missing fields, choose a tool, fill arguments, explain the result, recover from a typed error. | Measure, deform, offset, validate, slice, and talk to the printer. |

Serving, proposed, on the project GPU:

| Piece | Role |
|---|---|
| NVIDIA Nemotron 3.5 Lightning, 30B total, about 3B active per token | The only generative model. Checkpoint `NVIDIA-Nemotron-3.5-Lightning-30B-A3B`. |
| Red Hat vLLM | OpenAI-compatible tool calling. |

Verified flags from the [model card](https://huggingface.co/nvidia/NVIDIA-Nemotron-3.5-Lightning-30B-A3B-BF16) and the [NIM guide](https://docs.nvidia.com/nim/large-language-models/2.0.10/get-started/advanced/get-started-nemotron-3-5-lightning.html):

- `--enable-auto-tool-choice`
- `--tool-call-parser qwen3_coder`
- `--reasoning-parser nemotron_v3`

When reasoning and tool calls are both on, send `chat_template_kwargs.force_nonempty_content: true`. Red Hat documents these vLLM flags as passthrough on its inference stack ([llm-d tool calling](https://docs.redhat.com/en/documentation/red_hat_openshift_ai_self-managed/3.5/html/deploy_models_using_distributed_inference_with_llm-d/tool-calling-through-llmd_distributed-inference)). The hackathon use is that serving path on the team GPU. An OpenShift cluster is not part of the build.

**Unresolved:** the GPU, whether this image contains `qwen3_coder` and `nemotron_v3`, and whether the weights are BF16 or NVFP4.

NeMo Gym is how NVIDIA scores this model's general benchmarks. Those recipes do not know this tool registry. A custom environment is out of the MVP. Scripted traces can be scored without it.

### Result envelope

| Status | Meaning | Model behavior |
|---|---|---|
| `success` | The call ran. A failed validation is still `success` when `data.passed` is false. | Read the data and take the next legal step. |
| `fixable` | Arguments or the mesh can be corrected inside a known range. | Fix and retry, at most twice. |
| `fatal` | The same call will not succeed. | Stop, keep the last good revision, tell the user. |

```json
{
  "status": "success",
  "message": "Limb revision r2 written. Station errors are within tolerance.",
  "data": {},
  "error": null
}
```

A `fixable` error includes `error.code`, `error.reason`, and `error.valid`.

### Phases

```text
empty
  → template_selected
  → measurements_ready
  → limb_current
  → socket_current
  → socket_validated
  → slice_approved
  → sliced
  → print_approved
  → printing
  → paused | completed | unknown
```

A failed limb edit stays on the previous `limb_current`. A lost printer link moves the job to `unknown`. The model only sees the tools legal for the phase.

| Phase | Tools offered |
|---|---|
| `empty` | `list_limb_templates`, `inspect_limb_template`, `get_required_measurements`, `ask_user` |
| `template_selected` | `validate_measurements`, `ask_user` |
| `measurements_ready` | `customize_residual_limb` |
| `limb_current` | `measure_customized_limb`, `compare_limb_versions`, `export_customized_limb_stl`, `validate_measurements`, `customize_residual_limb`, `generate_socket_shell` |
| `socket_current` | `modify_socket_geometry`, `validate_socket_geometry`, `export_socket_stl` |
| `socket_validated` | `list_print_profiles`, `request_confirmation` for slice, then `slice_model` |
| `sliced`, printer ready, unused print confirmation | `get_printer_status`, `check_printer_readiness`, `start_print` |
| `printing` or `unknown` | `get_printer_status`, `reconcile_printer_state`, `request_safe_pause` |

`start_print` is omitted while the phase is `unknown`.

## 11. Tool Registry and JSON Contracts

Groups A–D are the registry. Names match the workflow. Thin tools stay because the model should not invent a file URL, a profile id, or a printer state.

Every object schema sets `additionalProperties: false`.

### A. Template and measurement tools

#### `list_limb_templates`

List transtibial templates the library can deform. **Straightforward.** Precondition: sidecar directory readable.

Inputs: none.

```json
{"type": "object", "additionalProperties": false, "properties": {}}
```

Example: `{"name": "list_limb_templates", "arguments": {}}`

Output: `{templates: [{template_id, label, units_status, available, source_file}]}`. `available` is false when units are unconfirmed or the skin split failed.

Errors: none in the happy path. An empty available list is still `success`.

Library: filesystem sidecars.

#### `inspect_limb_template`

Report axis, length, and station perimeters for one template. **Straightforward** after the unit experiment; **uncertain** until bounding boxes are measured.

Precondition: `template_id` exists.

```json
{
  "type": "object",
  "additionalProperties": false,
  "required": ["template_id"],
  "properties": {
    "template_id": {"type": "string", "enum": ["tt_mean", "tt_short", "tt_long", "tt_conical", "tt_bulbous"]}
  }
}
```

Example: `{"name": "inspect_limb_template", "arguments": {"template_id": "tt_mean"}}`

Output: bounds in mm, `reference_to_distal_mm`, perimeters at P, M, and D, open-boundary flag.

Errors: `unknown_template`, `units_unconfirmed`, `combined_mesh`.

Library: trimesh, or the sidecar when its hash matches.

#### `get_required_measurements`

Return the questionnaire contract for that template, including station definitions and the template's acceptance window. **Straightforward.** This is the step between template selection and validation. It does not measure the mesh again.

Precondition: template exists.

```json
{
  "type": "object",
  "additionalProperties": false,
  "required": ["template_id"],
  "properties": {
    "template_id": {"type": "string"}
  }
}
```

Example: `{"name": "get_required_measurements", "arguments": {"template_id": "tt_mean"}}`

Output: `{required: ["length_mm", "P", "D"], optional: ["M", "section_p", "distal_roundness", "side"], stations: [...], acceptance: {...}}`.

Errors: `unknown_template`.

Library: sidecar JSON. No mesh write.

#### `validate_measurements`

Accept or reject a measurement document before any vertex moves. **Straightforward.**

Precondition: template units are `mm`. If `parent_revision_id` is set, locks are enforced.

Required inputs: `template_id`, `measurements.length_mm`, stations P and D. Optional: `parent_revision_id`, M, `section_p`, `distal_roundness`, `side`, `posture`, per-field `correction`.

```json
{
  "type": "object",
  "additionalProperties": false,
  "required": ["template_id", "measurements"],
  "properties": {
    "template_id": {"type": "string"},
    "parent_revision_id": {"type": "string"},
    "measurements": {
      "type": "object",
      "additionalProperties": false,
      "required": ["length_mm", "stations"],
      "properties": {
        "length_mm": {"type": "number", "minimum": 50, "maximum": 300},
        "length_correction": {"type": "boolean"},
        "posture": {"type": "string", "enum": ["supine", "sitting", "standing"]},
        "side": {"type": "string", "enum": ["left", "right"]},
        "distal_roundness": {"type": "number", "minimum": -0.3, "maximum": 0.3},
        "stations": {
          "type": "array",
          "minItems": 2,
          "maxItems": 3,
          "items": {
            "type": "object",
            "additionalProperties": false,
            "required": ["id", "circumference_mm"],
            "properties": {
              "id": {"type": "string", "enum": ["P", "M", "D"]},
              "circumference_mm": {"type": "number", "minimum": 100, "maximum": 550},
              "correction": {"type": "boolean"}
            }
          }
        },
        "section_p": {
          "type": "object",
          "additionalProperties": false,
          "required": ["ap_mm", "ml_mm"],
          "properties": {
            "ap_mm": {"type": "number", "minimum": 40, "maximum": 200},
            "ml_mm": {"type": "number", "minimum": 40, "maximum": 200}
          }
        }
      }
    }
  }
}
```

Example:

```json
{
  "name": "validate_measurements",
  "arguments": {
    "template_id": "tt_mean",
    "measurements": {
      "length_mm": 150,
      "posture": "supine",
      "stations": [
        {"id": "P", "circumference_mm": 300},
        {"id": "D", "circumference_mm": 240}
      ]
    }
  }
}
```

Output: `{validation_id, accepted, normalized, warnings}`. The server mints `validation_id`.

Errors: `missing_required`, `outside_template`, `inconsistent_taper`, `inconsistent_profile`, `inconsistent_section`, `unconfirmed_overwrite`, `unsupported_field`.

Library: Python against the sidecar and the parent locks.

### B. Residual-limb customization tools

#### `customize_residual_limb`

Run section 6 and write a new limb STL. **Uncertain** until the two-station remeasure passes. This is the critical geometry experiment.

Precondition: `validation_id` matches this measurement document and has not been consumed.

Required: `template_id`, `validation_id`, `measurements`. Optional: `limb_id`, `parent_revision_id`, `allow_coarse`.

```json
{
  "type": "object",
  "additionalProperties": false,
  "required": ["template_id", "measurements", "validation_id"],
  "properties": {
    "template_id": {"type": "string"},
    "limb_id": {"type": "string"},
    "parent_revision_id": {"type": "string"},
    "validation_id": {"type": "string"},
    "allow_coarse": {"type": "boolean"},
    "measurements": {"type": "object"}
  }
}
```

Example:

```json
{
  "name": "customize_residual_limb",
  "arguments": {
    "template_id": "tt_mean",
    "validation_id": "val_01",
    "measurements": {
      "length_mm": 150,
      "stations": [
        {"id": "P", "circumference_mm": 300},
        {"id": "D", "circumference_mm": 240}
      ]
    }
  }
}
```

Output: `{limb_id, revision_id, parent_revision_id, method, measured_length_mm, stations: [{id, target_mm, measured_mm, error_mm}], face_count}`. The STL path is server-side. The viewer URL comes from `export_customized_limb_stl`.

Errors: `validation_mismatch`, `combined_mesh`, `unstable_station`, `target_not_met`, `self_intersection`. `target_not_met` may set `coarse_available: true` once.

Library: trimesh, NumPy, SciPy.

#### `measure_customized_limb`

Remeasure a stored limb revision. **Straightforward** if sectioning the mean skin works; the same station code as customization.

Precondition: revision exists.

```json
{
  "type": "object",
  "additionalProperties": false,
  "required": ["limb_id", "revision_id"],
  "properties": {
    "limb_id": {"type": "string"},
    "revision_id": {"type": "string"},
    "stations": {
      "type": "array",
      "minItems": 1,
      "maxItems": 3,
      "items": {"type": "string", "enum": ["P", "M", "D"]}
    }
  }
}
```

Example: `{"name": "measure_customized_limb", "arguments": {"limb_id": "limb_01", "revision_id": "r1"}}`

Output: length, perimeters, and whether each station was a single loop.

Errors: `unknown_revision`, `unstable_station`.

Library: trimesh.

#### `compare_limb_versions`

Quantify two revisions of one limb. **Straightforward** when face counts match.

Precondition: both revisions exist and share a template.

```json
{
  "type": "object",
  "additionalProperties": false,
  "required": ["limb_id", "revision_a", "revision_b"],
  "properties": {
    "limb_id": {"type": "string"},
    "revision_a": {"type": "string"},
    "revision_b": {"type": "string"}
  }
}
```

Example: `{"name": "compare_limb_versions", "arguments": {"limb_id": "limb_01", "revision_a": "r1", "revision_b": "r2"}}`

Output: perimeter deltas, length delta, bounding-box delta, mean and max radial difference in mm, and which fields changed in the measurement document.

Errors: `unknown_revision`, `topology_mismatch`.

Library: NumPy on the two vertex arrays.

#### `export_customized_limb_stl`

Return a viewer URL for an existing limb revision. **Straightforward.** Export does not mean the socket is printable. The limb mesh is not a socket.

Precondition: revision exists.

```json
{
  "type": "object",
  "additionalProperties": false,
  "required": ["limb_id", "revision_id"],
  "properties": {
    "limb_id": {"type": "string"},
    "revision_id": {"type": "string"}
  }
}
```

Example: `{"name": "export_customized_limb_stl", "arguments": {"limb_id": "limb_01", "revision_id": "r2"}}`

Output: `{stl_url, sha256, role: "residual_limb"}`.

Errors: `unknown_revision`.

Library: filesystem.

### C. Prosthetic socket CAD tools

#### `generate_socket_shell`

Build the first demonstration shell from a limb revision. **Uncertain.** Offset of this open skin is the main CAD risk.

Precondition: limb revision passed its own measurement check. No socket parameter is taken from the questionnaire.

Required: `limb_id`, `revision_id`. Optional: `clearance_mm` 0–3 default 1.5, `wall_thickness_mm` 2–6 default 4, `trim_fraction` 0.05–0.35 default 0.15, `rim_radius_mm` 0–3 default 1.

```json
{
  "type": "object",
  "additionalProperties": false,
  "required": ["limb_id", "revision_id"],
  "properties": {
    "limb_id": {"type": "string"},
    "revision_id": {"type": "string"},
    "clearance_mm": {"type": "number", "minimum": 0, "maximum": 3},
    "wall_thickness_mm": {"type": "number", "minimum": 2, "maximum": 6},
    "trim_fraction": {"type": "number", "minimum": 0.05, "maximum": 0.35},
    "rim_radius_mm": {"type": "number", "minimum": 0, "maximum": 3}
  }
}
```

Example:

```json
{
  "name": "generate_socket_shell",
  "arguments": {
    "limb_id": "limb_01",
    "revision_id": "r2",
    "clearance_mm": 1.5,
    "wall_thickness_mm": 4,
    "trim_fraction": 0.15,
    "rim_radius_mm": 1
  }
}
```

Output: `{socket_id, revision_id, source_limb_revision, watertight, stale_limb}`. `stale_limb` is true when a newer limb revision exists. The limb STL is not modified.

Errors: `unknown_revision`, `offset_failed`, `not_closed`.

Library: trimesh and manifold3d. Blender Solidify subprocess only after the offset experiment fails.

#### `modify_socket_geometry`

Regenerate a socket revision from the same limb, changing only the named parameters. **Same uncertainty as the shell.** Unspecified parameters are copied.

Precondition: a parent socket revision exists. Locked parameters need `correction: true`.

```json
{
  "type": "object",
  "additionalProperties": false,
  "required": ["socket_id", "parent_revision_id"],
  "properties": {
    "socket_id": {"type": "string"},
    "parent_revision_id": {"type": "string"},
    "clearance_mm": {"type": "number", "minimum": 0, "maximum": 3},
    "wall_thickness_mm": {"type": "number", "minimum": 2, "maximum": 6},
    "trim_fraction": {"type": "number", "minimum": 0.05, "maximum": 0.35},
    "rim_radius_mm": {"type": "number", "minimum": 0, "maximum": 3},
    "correction": {"type": "boolean"}
  }
}
```

Example: `{"name": "modify_socket_geometry", "arguments": {"socket_id": "sock_01", "parent_revision_id": "s1", "wall_thickness_mm": 5, "correction": true}}`

Output: a new socket revision id and the full parameter set actually used. Previous certificate is void.

Errors: `unconfirmed_overwrite`, `offset_failed`, `not_closed`.

Library: same as `generate_socket_shell`.

#### `validate_socket_geometry`

Certificate for closure, wall, self-intersection, build volume, and overhangs. **Mostly straightforward.** Self-intersection is the uncertain check.

Precondition: socket revision exists. Profile must be the approved one.

```json
{
  "type": "object",
  "additionalProperties": false,
  "required": ["socket_id", "revision_id", "printer_profile_id"],
  "properties": {
    "socket_id": {"type": "string"},
    "revision_id": {"type": "string"},
    "printer_profile_id": {"type": "string", "enum": ["tt_draft_028"]},
    "min_wall_mm": {"type": "number", "minimum": 2, "maximum": 6},
    "max_overhang_deg": {"type": "number", "minimum": 30, "maximum": 70}
  }
}
```

Example: `{"name": "validate_socket_geometry", "arguments": {"socket_id": "sock_01", "revision_id": "s1", "printer_profile_id": "tt_draft_028"}}`

Output: each check, sampled minimum wall, bounding box, `passed`, and `certificate_id` only on a full pass.

Errors: `unknown_revision`, `unknown_profile`. A failed check is not an error status.

Library: trimesh. Build volume comes from the profile INI.

#### `export_socket_stl`

Viewer URL for a socket revision. **Straightforward.** Export is not a certificate.

```json
{
  "type": "object",
  "additionalProperties": false,
  "required": ["socket_id", "revision_id"],
  "properties": {
    "socket_id": {"type": "string"},
    "revision_id": {"type": "string"}
  }
}
```

Example: `{"name": "export_socket_stl", "arguments": {"socket_id": "sock_01", "revision_id": "s1"}}`

Output: `{stl_url, sha256, role: "socket_shell", certified}`.

Errors: `unknown_revision`.

Library: filesystem.

### D. Manufacturing tools

#### `list_print_profiles`

Return the only approved profile so the model cannot invent one. **Straightforward.**

Inputs: none.

```json
{"type": "object", "additionalProperties": false, "properties": {}}
```

Example: `{"name": "list_print_profiles", "arguments": {}}`

Output: `{profiles: [{profile_id: "tt_draft_028", layer_height_mm: 0.28, approved: true}]}`.

Errors: `profile_missing` if the INI file is absent.

Library: local INI directory. PrusaSlicer has no profile-list API.

#### `slice_model`

Slice one certified socket revision. **Straightforward** once a closed STL exists. The slicer process itself is well documented.

Precondition: certificate names this revision and this profile; `confirmation_id` is a single-use slice approval for this revision.

```json
{
  "type": "object",
  "additionalProperties": false,
  "required": ["socket_id", "revision_id", "profile_id", "confirmation_id", "certificate_id"],
  "properties": {
    "socket_id": {"type": "string"},
    "revision_id": {"type": "string"},
    "profile_id": {"type": "string", "enum": ["tt_draft_028"]},
    "confirmation_id": {"type": "string"},
    "certificate_id": {"type": "string"}
  }
}
```

Example:

```json
{
  "name": "slice_model",
  "arguments": {
    "socket_id": "sock_01",
    "revision_id": "s1",
    "profile_id": "tt_draft_028",
    "confirmation_id": "conf_slice_01",
    "certificate_id": "cert_01"
  }
}
```

Output: `{job_id, estimated_seconds, filament_mm, filament_g, gcode_sha256}`.

Errors: `certificate_stale`, `confirmation_mismatch`, `outside_volume`, `slicer_failed`.

Library: PrusaSlicer CLI `--export-gcode`. Time and filament are parsed from its output.

#### `get_printer_status`

Read connection, printer, and job. **Straightforward.** This does not decide whether a start is allowed.

Inputs: none.

```json
{"type": "object", "additionalProperties": false, "properties": {}}
```

Example: `{"name": "get_printer_status", "arguments": {}}`

Output: `{connection, printer, job}` summaries from the three GET endpoints.

Errors: `printer_unreachable`.

Library: OctoPrint REST.

#### `check_printer_readiness`

Decide whether a start may be offered. **Straightforward.**

Optional input: `expected_port`, default `VIRTUAL`.

```json
{
  "type": "object",
  "additionalProperties": false,
  "properties": {
    "expected_port": {"type": "string"}
  }
}
```

Example: `{"name": "check_printer_readiness", "arguments": {"expected_port": "VIRTUAL"}}`

Output: `{ready, reason}`. Ready only when OctoPrint is operational, the port is virtual, and the state is not printing, paused, or error.

Errors: `printer_unreachable`. A busy printer is `success` with `ready: false`.

Library: the same three GET endpoints.

#### `start_print`

Upload, select, start, and read the job back. **Straightforward** against the Virtual Printer. The safety checks are the important part.

Precondition: job exists, printer is ready, `confirmation_id` is a single-use print approval for this job, and the ledger has no open start for it.

```json
{
  "type": "object",
  "additionalProperties": false,
  "required": ["job_id", "confirmation_id"],
  "properties": {
    "job_id": {"type": "string"},
    "confirmation_id": {"type": "string"}
  }
}
```

Example: `{"name": "start_print", "arguments": {"job_id": "job_01", "confirmation_id": "conf_print_01"}}`

Output: `{state, verified}` from `GET /api/job` after the start. A 204 is not success by itself.

Errors: `not_ready`, `confirmation_mismatch`, `already_started`, `unverified`.

Library: OctoPrint file upload, select with `print: false`, job start, then job GET.

#### `reconcile_printer_state`

Compare the command ledger with the live printer. **Straightforward.**

Inputs: none.

```json
{"type": "object", "additionalProperties": false, "properties": {}}
```

Example: `{"name": "reconcile_printer_state", "arguments": {}}`

Output: `verified`, `mismatch`, or `unknown`, plus the last ledger row and the last successful job GET.

Errors: none beyond `unknown`, which is a normal result when the link is down.

Library: SQLite ledger and OctoPrint.

#### `request_safe_pause`

Pause a job that is printing, and record the attempt when the link is down. **Straightforward.** Kept so a disconnect has a recovery other than a second start.

```json
{
  "type": "object",
  "additionalProperties": false,
  "required": ["job_id", "reason"],
  "properties": {
    "job_id": {"type": "string"},
    "reason": {"type": "string", "maxLength": 200}
  }
}
```

Example: `{"name": "request_safe_pause", "arguments": {"job_id": "job_01", "reason": "link lost after start"}}`

Output: `paused` only after a confirming read, otherwise `pause_not_delivered`.

Errors: `job_not_printing` when the printer is idle. That is not a reason to start again.

Library: OctoPrint pause, then job GET.

### Loop tools

#### `ask_user`

Ask for a missing measurement, a relative edit with no baseline, or an unsupported request. **Straightforward.** Ends the model turn. The model does not invent a limb.

```json
{
  "type": "object",
  "additionalProperties": false,
  "required": ["question_id", "prompt"],
  "properties": {
    "question_id": {"type": "string"},
    "prompt": {"type": "string", "maxLength": 500},
    "expects": {"type": "string", "enum": ["number_mm", "enum", "confirmation", "free_text"]}
  }
}
```

Example: `{"name": "ask_user", "arguments": {"question_id": "length_delta_baseline", "prompt": "Shorter than which length, in millimetres?", "expects": "number_mm"}}`

Output: the UI's answer on the next turn, not in this call.

#### `request_confirmation`

Ask the UI to mint a one-time id. **Straightforward.** The model cannot invent the id. Slice approval does not authorize a print.

```json
{
  "type": "object",
  "additionalProperties": false,
  "required": ["action", "target_id"],
  "properties": {
    "action": {"type": "string", "enum": ["slice", "start_print"]},
    "target_id": {"type": "string"}
  }
}
```

Example: `{"name": "request_confirmation", "arguments": {"action": "start_print", "target_id": "job_01"}}`

Output: `{confirmation_id}` only after the person approves.

## 12. Slicing and OctoPrint Integration

```text
customized limb STL
  → socket STL
  → validate_socket_geometry
  → slice confirmation
  → slice_model
  → print confirmation
  → start_print
  → get_printer_status
  → reconcile or request_safe_pause
  → fabrication report
```

| Piece | Choice |
|---|---|
| Profile | One INI, `tt_draft_028`, 0.28 mm layers. A second profile is out of the MVP. |
| Slicer | [PrusaSlicer](https://github.com/prusa3d/PrusaSlicer) CLI `--export-gcode`. |
| Printer | [OctoPrint](https://docs.octoprint.org/en/main/api/) [Virtual Printer](https://docs.octoprint.org/en/main/development/virtual_printer.html) only. |
| Start sequence | Upload, select with `print: false`, POST start, then `GET /api/job`. |
| HTTP | 204 with an empty body means accepted. 409 means the state refused the command. Neither proves the job is printing. |
| Progress | `get_printer_status` quotes completion and state from `GET /api/job`. |
| Ledger | Every start and pause is stored by `job_id`. A second start is refused while the first is `sent`, `verified_printing`, or `unknown`. |
| API key | `STATUS`, `FILES_UPLOAD`, `FILES_SELECT`, and `PRINT`. No `CONTROL`, so the model cannot send arbitrary G-code, jog, or set temperatures. |
| Fault injector | `!!DEBUG:action_disconnect` uses a separate key. It is not an agent tool. |
| Report | Dataset citation, template hash, measurement document, revision ids, certificate, profile, time, filament, printer observations, nonclinical statement. Written from the log. |

A physical serial port fails `check_printer_readiness`. Firmware limits stay in firmware. This software does not disable them, and the virtual printer does not test them.

## 13. Frontend Architecture

One page. No CAD editor.

| Region | Behavior |
|---|---|
| Template cards | `tt_mean`, and short and long when available. Stretch cards stay disabled until their sidecars say `available`. |
| Questionnaire | Length, P, and D visible. M, AP/ML, distal shape, and side behind "more detail." Millimetres, with centimetres shown beside the field. |
| Limb viewer | Title "Residual limb." Loads `role: residual_limb` only. |
| Chat | Writes the same locks as the form. |
| Comparison | Side-by-side limb revisions plus the `compare_limb_versions` table. |
| Socket viewer | Title "Socket shell." Separate component, separate URL, `role: socket_shell`. |
| Validation | Certificate checks, each named as a geometric check. |
| Print bar | Slice confirmation and print confirmation are different buttons. Print stays disabled until readiness is true and a slice exists. |
| Report | Download at the end. |

The browser displays STL URLs. It does not recompute geometry. Proposed stack: a small Python app and [three.js](https://threejs.org/). The measurement document and the phase live on the server.

## 14. End-to-End Demo Scenarios

Target length 4–6 minutes for the happy path. One recovery can be live. The others can be recorded.

### 14.1 Happy path

1. The user selects `tt_mean`.
2. `get_required_measurements` returns length, P, and D.
3. The user enters 150 mm, 300 mm, and 240 mm.
4. `validate_measurements` then `customize_residual_limb`.
5. `export_customized_limb_stl` feeds the limb viewer. `measure_customized_limb` is read back in chat.
6. "Change the proximal circumference to 310 mm." Validation sets `correction` on P only. Revision `r2`.
7. `compare_limb_versions` shows P changed and D unchanged.
8. "The residual limb should be 15 mm shorter." New length 135 mm. Revision `r3`. Circumferences stay locked.
9. The user asks for a demonstration socket.
10. `generate_socket_shell` writes a socket STL. The limb file remains.
11. `validate_socket_geometry` returns a certificate.
12. The user approves `tt_draft_028`.
13. `slice_model` reports time and filament.
14. The user presses the print confirmation.
15. `start_print` then `get_printer_status`.
16. The report is saved.

Proximal correction:

```json
{
  "name": "validate_measurements",
  "arguments": {
    "template_id": "tt_mean",
    "parent_revision_id": "r1",
    "measurements": {
      "length_mm": 150,
      "stations": [
        {"id": "P", "circumference_mm": 310, "correction": true},
        {"id": "D", "circumference_mm": 240}
      ]
    }
  }
}
```

Relative length correction, after the user has a locked length of 150:

```json
{
  "name": "validate_measurements",
  "arguments": {
    "template_id": "tt_mean",
    "parent_revision_id": "r2",
    "measurements": {
      "length_mm": 135,
      "length_correction": true,
      "stations": [
        {"id": "P", "circumference_mm": 310},
        {"id": "D", "circumference_mm": 240}
      ]
    }
  }
}
```

### 14.2 Inconsistent circumferences

Distal 360 mm with proximal 300 mm. `validate_measurements` returns `fixable` / `inconsistent_taper`. The agent asks which number to correct. `customize_residual_limb` is not called. A value that also implies a section scale outside 0.75–1.35 stays refused. The unedited template can be shown. The mesh is not stretched to force the number.

### 14.3 Socket validation failure

`generate_socket_shell` returns `offset_failed`, or `validate_socket_geometry` returns `passed: false` because the sampled wall is under 2.0 mm. The agent may call `modify_socket_geometry` once to raise thickness by at most 1.0 mm, then validate again. The limb revision is unchanged. A second failure stops the path. Nothing is sliced.

### 14.4 Printer disconnect

After a verified start, the injector sends `!!DEBUG:action_disconnect` with the injector key. The next `get_printer_status` fails. `reconcile_printer_state` returns `unknown`. `request_safe_pause` records `pause_not_delivered` if the pause cannot be read back. A second `start_print` is rejected from the ledger.

### 14.5 Distal shape, if that parameter is on

"Make the distal shape slightly more rounded" writes a limb revision with `distal_roundness` 0.15 and the same locked length and circumferences. The comparison shows a small tip change and no change at P. A request to fit around the fibular head calls `ask_user` and writes nothing.

## 15. MVP Implementation Milestones

| Choice | MVP | Later |
|---|---|---|
| Templates | `tt_mean`. Add `tt_short` and `tt_long` if the skin split is clean. | `tt_conical`, `tt_bulbous`. |
| Questionnaire | Length, P, D. | M, AP/ML, distal shape, side. |
| Deformation | Axial warp plus two-station radial scale. | Anisotropy, distal roundness, PCA scores. |
| Socket | One offset shell. `modify_socket_geometry` for wall and rim. | Variable thickness, rectification. |
| Print | `tt_draft_028` and one virtual start. | A second profile, a physical printer. |
| Model | Nemotron tool loop on vLLM. | MCP, NeMo Gym. |

Do not simulate the tool trace, the measurement check, or the printer read-back. The stand-in shell in section 8 is allowed only after the offset experiment fails, and it must be labeled.

### Proofs of concept, in order

1. **Units and stations on the mean skin.** Load `Mean-Skin.stl` and `Mean-Skin-Full-Size.stl`. Record bounding boxes, longest axis, whether the surface is open, and perimeters on three planes. Mark the sidecar `mm` only for the file that is a plausible transtibial size under one documented scale. Annotate the reference station by looking at the mesh. Pass: planes at P and D each return one loop.
2. **Skin split, then a two-station edit.** Try to separate skin from `Mode1-20th-Mode2-Mean.stl` and `Mode1-80th-Mode2-Mean.stl`. If that fails, ship `tt_mean` only. On `tt_mean`, apply length 150 mm, P 300 mm, and D 240 mm. Pass: targeted perimeters within 3 mm or 2%, face count unchanged, and a later edit of P leaves D at its target.
3. **Closed shell.** Offset that limb with manifold3d at 1.5 mm clearance and 4 mm wall, trim the proximal end, and export a watertight STL. Run `validate_socket_geometry` and one PrusaSlicer dry run on `tt_draft_028`. Pass: one component, watertight, minimum wall at least 2 mm, slicer accepts the mesh. If manifold3d fails, try one Blender Solidify subprocess before changing the tool schema.

| Person | Owns |
|---|---|
| 1 | vLLM flags, agent loop, measurement document, phase filter, confirmations, audit log. Starts against stub tools. |
| 2 | Experiments 1–3, sidecars, limb deformation, socket shell, certificates. Critical path. |
| 3 | The one INI, OctoPrint Virtual Printer, fault injection, the page, the report. A closed box can prove the printer gate before experiment 3 finishes. |

| When | Milestone |
|---|---|
| First hours | Experiment 1 done. Nemotron returns a tool call. Virtual printer answers `GET /api/job`. |
| Next block | Experiment 2 done, or the library is explicitly one template. Experiment 3 attempted. |
| Evening | One limb revision on the page. One shell certified, or the stand-in decision written down. |
| Night | Slice, both confirmations, verified virtual start. |
| Following morning | The three failure cases have been run. README matches what ran. |

**Do not cut:** the unit check, a real limb deformation or an honest coarse fallback, a real shell or the labeled stand-in, structured tool errors, the Nemotron loop, and the confirmation gate.

**Cut first:** the conical and bulbous templates, AP/ML, distal roundness, rim decoration, color-map diffs, MCP, Blender as the primary kernel, and NeMo Gym.

## 16. Research References and Licenses

### Dataset

- Sunderland, F. E., Sobey, A. J., Bramley, J. L., Steer, J. W., Al-Dirini, R., Metcalf, C. D., Toderita, D., Bull, A., Ding, Z., Henson, D., Worsley, P. R., Dickinson, A. S., and the OpenLimb Group (2025). OpenLimbTT, a transtibial residual limb shape model for prosthetics simulation and design. *Data-Centric Engineering*, 6, e39. https://doi.org/10.1017/dce.2025.10019
- OpenLimbTT files. Data: CC BY-SA 4.0. Generation code: MIT. https://github.com/abel-research/OpenLimbTT
- Study record: https://doi.org/10.5258/SOTON/D2895
- ampscan, used by the dataset authors and not required for the MVP vertex update: https://github.com/abel-research/ampscan

Share-alike applies to meshes derived from OpenLimbTT. Cite the paper in the repository and in every fabrication report.

### Measurements

- ISO 8548-2:2020. Prosthetics and orthotics — Limb deficiencies — Part 2: Method of describing lower limb amputation stumps. https://www.iso.org/standard/76809.html
- Dickinson, A., Diment, L., Morris, R., Pearson, E., Hannett, D., and Steer, J. (2021). Characterising residual limb morphology and prosthetic socket design based on expert clinician practice. *Prosthesis*, 3(4), 280–299. https://doi.org/10.3390/prosthesis3040027
- Seminati, E., Young, M., Canepa Talamas, D., Twiste, M., Dhokia, V., and Bilzon, J. (2022). Reliability of three methods for assessing amputee residuum shape and volume. *Prosthetics and Orthotics International*. https://doi.org/10.1097/pxr.0000000000000105
- Geil, M. D. (2005). Consistency and accuracy of measurement of lower extremity amputee anthropometrics. *Journal of Rehabilitation Research and Development*, 42(2), 131–140. https://doi.org/10.1682/jrrd.2004.05.0054
- Sanders, J. E., and Fatone, S. (2011). Residual limb volume change: systematic review of measurement and management. https://pmc.ncbi.nlm.nih.gov/articles/PMC4423813/
- US 7,617,072. Prior art for cross-section scaling of a reference mesh. Not a software dependency.

### Socket geometry and fabrication

- Facoetti, G., Gabbiadini, S., Colombo, G., and Rizzi, C. (2010). Knowledge-based system for guided modeling of sockets for lower limb prostheses. *Computer-Aided Design and Applications*, 7(5), 723–737. https://doi.org/10.3722/cadaps.2010.723-737
- van der Stelt, M., Stenveld, F., Bitter, T., Maal, T. J. J., and Janssen, D. (2022). Design evaluation of FFF-printed transtibial prosthetic sockets. *Prosthesis*, 4(4), 589–599. https://doi.org/10.3390/prosthesis4040048
- uFit, reviewed and not wrapped: https://github.com/ortigital/ufit-blender and https://github.com/Ugani-Prosthetics/ufit-blender
- trimesh: https://trimsh.org/
- manifold3d: https://github.com/elalish/manifold
- PrusaSlicer: https://github.com/prusa3d/PrusaSlicer
- OctoPrint API: https://docs.octoprint.org/en/main/api/
- OctoPrint Virtual Printer: https://docs.octoprint.org/en/main/development/virtual_printer.html

### Model serving

- Nemotron 3.5 Lightning model card: https://huggingface.co/nvidia/NVIDIA-Nemotron-3.5-Lightning-30B-A3B-BF16
- NIM tool-calling guide: https://docs.nvidia.com/nim/large-language-models/2.0.10/get-started/advanced/get-started-nemotron-3-5-lightning.html
- vLLM write-up: https://vllm.ai/blog/2026-08-10-nemotron-3-5-lightning-vllm
- Red Hat tool-calling passthrough: https://docs.redhat.com/en/documentation/red_hat_openshift_ai_self-managed/3.5/html/deploy_models_using_distributed_inference_with_llm-d/tool-calling-through-llmd_distributed-inference

Pin the license of trimesh, manifold3d, SciPy, PrusaSlicer, and OctoPrint in the commit that installs them. PrusaSlicer and OctoPrint are AGPL; call them as separate processes.

## 17. Technical Risks and Limitations

The three largest implementation risks:

1. **Units and skin extraction.** `Mean-Skin.stl` and `Mean-Skin-Full-Size.stl` share a triangle count and differ in content, and STL stores no units. Every mode file matches the combined limb's byte size, so short, long, conical, and bulbous templates do not exist as skin files until a split succeeds. If the split fails, the honest library is one template.
2. **Two-station deformation that remeasures.** Planes near an open boundary or a distal cap can return the wrong loop. A non-monotone scale curve can miss the targets. The reference station is a hand annotation, not a palpated tendon. Tape perimeter error in Seminati et al. is already above 5%, and OpenLimbTT's own full-surface recreation error has a median of 3.40 mm. The algorithm copies template shape between stations. It does not recover patient anatomy.
3. **A closed socket from an open skin.** manifold3d may fail to offset and close `Mean-Skin`. Until experiment 3 passes, slicing and printing have no real input. The labeled stand-in shell is the fallback, and it must not be described as the customized socket.

Further limits, after those three:

- The training set is 33 limbs and is described as preliminary. The 20th and 80th files are samples of that model, not clinical categories.
- A locked-field bug in the agent is contained only if `validate_measurements` enforces `correction`. Prompt text is not the control.
- The Red Hat vLLM image may lack the Nemotron parsers. Confirm that before writing the client against them.
- The workflow resembles a fitting workflow. Questionnaire copy, tool descriptions, and the report have to keep saying "demonstration" and cite OpenLimbTT.

The report sentence is fixed: the limb is a synthetic OpenLimbTT template adjusted to the entered measurements, the socket is a demonstration shell, and the print is virtual.
