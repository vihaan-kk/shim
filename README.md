# Measurement-Driven Prosthetic Socket Agent

An SLM-powered agent that turns a short point-of-care questionnaire into a customized synthetic residual-limb model, a demonstration socket shell, and a confirmed virtual 3D print.

The model does not deform meshes or operate the printer. It chooses a tool and fills in structured arguments. Deterministic Python code checks those arguments, edits geometry, validates the result, and returns a typed result. The agent asks when a measurement is missing or inconsistent, keeps earlier confirmed values, and never starts a print without a separate human confirmation.

**Status:** design plan. This repository does not yet contain an agent, templates, geometry code, a slicer profile, or a printer integration. Nothing in this document is an implemented component.

**Dataset candidate:** [OpenLimbTT](https://github.com/abel-research/OpenLimbTT) version `2025-07`, synthetic transtibial residual-limb surfaces. The files are not vendored here.

**Clinical boundary:** measurement-driven reconstruction is an approximation of a standardized template. It is not a reconstruction of a person's anatomy. Generated sockets are non-wearable demonstration prototypes. A passing geometry check means the mesh is closed, inside the configured wall and printer limits, and ready to slice. It does not establish fit, comfort, load transfer, or safety on a person.

The innovation this prototype is built to show is the model's ability to coordinate a multi-stage, stateful, iterative path from questionnaire to virtual print. It is not a new clinical fitting method.

## How to read this plan

Each major claim is one of three kinds:

| Kind | Meaning |
|---|---|
| Verified | Checked against a paper, a dataset repository, or vendor documentation during this replan. |
| Proposed | A design choice for this hackathon. It is not implemented. |
| Unresolved | A fact or technical risk that has to be settled by an early proof of concept before the rest of the plan depends on it. |

## Contents

1. [Product vision and problem statement](#1-product-vision-and-problem-statement)
2. [Target users and intended nonclinical use](#2-target-users-and-intended-nonclinical-use)
3. [Dataset and standardized template library](#3-dataset-and-standardized-template-library)
4. [Practitioner questionnaire and required measurements](#4-practitioner-questionnaire-and-required-measurements)
5. [Measurement-driven residual-limb customization](#5-measurement-driven-residual-limb-customization)
6. [Conversational editing and version management](#6-conversational-editing-and-version-management)
7. [Prosthetic socket CAD generation](#7-prosthetic-socket-cad-generation)
8. [Tool-calling architecture and function registry](#8-tool-calling-architecture-and-function-registry)
9. [Geometry validation and safety boundaries](#9-geometry-validation-and-safety-boundaries)
10. [Slicing and virtual printer integration](#10-slicing-and-virtual-printer-integration)
11. [Frontend experience](#11-frontend-experience)
12. [Technology stack and sponsor integration](#12-technology-stack-and-sponsor-integration)
13. [End-to-end demonstration scenarios](#13-end-to-end-demonstration-scenarios)
14. [MVP milestones and team responsibilities](#14-mvp-milestones-and-team-responsibilities)
15. [Research references, datasets, and licenses](#15-research-references-datasets-and-licenses)
16. [Technical limitations and future work](#16-technical-limitations-and-future-work)

## 1. Product vision and problem statement

Producing a demonstration socket currently means importing a shape, deciding how large it should be, building a wall, checking the mesh, slicing, and driving printer software. Each step is a different program. The person who knows those programs becomes the bottleneck, including when the shape itself is only a synthetic stand-in.

This agent is for that demonstration path:

1. The practitioner picks a standardized transtibial residual-limb template.
2. They enter measurements and observations they can collect with a tape, a ruler, and, optionally, calipers.
3. The model calls a geometry tool that deforms a copy of the template and writes a new limb revision.
4. They can correct a number or ask for a supported shape change in ordinary language. Each accepted change writes another revision.
5. The model then calls a separate CAD tool that builds a demonstration socket shell around that limb revision.
6. After validation, slicing, and an explicit confirmation, the agent starts a virtual print and writes a fabrication report.

Four stages stay separate. Mixing them up is the main way a demo starts to sound like a medical device.

| Stage | What it answers | What this prototype does |
|---|---|---|
| Residual-limb geometry | What reference surface are we demonstrating? | Scale and gently reshape a synthetic template from a few measurements. |
| Socket geometry | What closed shell surrounds that reference? | Constant clearance, constant wall, geometric trim, rounded rim. |
| Socket rectification | Where should a wearable socket load or unload tissue? | Out of scope. No patellar-tendon bar, no relief map, no pressure prediction. |
| Manufacturability | Can this mesh be sliced on the configured virtual printer? | Closure, wall thickness, build volume, overhangs, then a confirmed virtual job. |

## 2. Target users and intended nonclinical use

**Intended user of the demo:** a prosthetics practitioner, technician, or researcher who can take a residual-limb measurement and should not have to operate CAD, a slicer, and printer software by hand.

**Intended use:** prepare and virtually print a non-wearable demonstration socket from synthetic anatomy and practitioner-entered numbers.

In scope:

- A small library of transtibial skin templates derived from OpenLimbTT.
- A structured questionnaire whose essential items are amputation level, residual length, and two circumferences.
- Conversational corrections that update one parameter and leave the others fixed.
- A constant-offset demonstration shell, mesh checks, slicing, and a gated virtual print.
- An audit report that cites the dataset and states the nonclinical limit.

Out of scope:

- Ankle disarticulation, partial foot, knee disarticulation, and transfemoral sockets in the MVP.
- Wrist-hand orthoses, ankle-foot orthoses, and other device types.
- Identifiable scans, medical records, or any claim that the questionnaire recovers a patient.
- Clinical rectification, liner prescription, suspension choice, alignment, or dynamic test-socket fitting.
- Wearable sockets and physical-printer operation.
- Any statement that a geometric clearance or a wall thickness is a validated fit.

A tape measurement is something a trained practitioner can take at the point of care. Placing that tape on the correct anatomical level is a palpation skill. The questionnaire therefore shows a diagram and names one landmark. The system does not infer a landmark the practitioner did not identify.

## 3. Dataset and standardized template library

### 3.1 What was reviewed

| Source | Region | What the files are | License as stated by the publisher | MVP decision |
|---|---|---|---|---|
| [OpenLimbTT](https://github.com/abel-research/OpenLimbTT) `2025-07` | Transtibial, through the tibial diaphysis. Syme amputations were excluded from training. | Mean skin, mean bones, mean combined limb, and mode-combination STLs. PCA components and a generation script are also published. | Data: CC BY-SA 4.0. Generation code: MIT. Derived meshes we redistribute stay under CC BY-SA 4.0. | Primary template source. |
| [OpenLimbTF](https://github.com/abel-research/OpenLimbTF) `2025-05` | Transfemoral. Skin, residual femur, and hemipelvis. | One mean limb STL and four mode STLs. No separate skin file in the repository listing. | Data: CC BY-SA 4.0. The authors say the model is not yet published. | Recorded as future work. Too small and too different for this hackathon. |
| [OpenHands](https://github.com/abel-research/OpenHands) | Finger bones. | Not a residual limb. | Separate dataset. | Irrelevant to socket templates. |
| Southampton deposit [10.5258/SOTON/D2895](https://doi.org/10.5258/SOTON/D2895) | Study record for the OpenLimbTT paper. | A small text file and a spreadsheet, not the STL library. | The medRxiv preprint described this deposit as CC BY 4.0. Confirm the live record before citing that license. | Citation and provenance only. |
| Ankle-level / Syme | Bulbous distal end, retained heel pad, malleolar flare. | No open residual-limb STL library of comparable scope was found. | — | Unsupported. Different socket problem. |

Verified details for OpenLimbTT, from the [paper](https://doi.org/10.1017/dce.2025.10019), the repository README, the version notes, and the GitHub file listing:

- Version `2025-07` is trained on 33 limbs (4 female, 29 male). The authors describe limited statistical generality.
- Mode 1 is amputation height, about 52.2% of variance. In the paper's Table 2, the high percentile of mode 1 is the long extreme and the low percentile is the short extreme.
- Mode 2 is slender versus bulbous soft tissue, about 16.7% of variance. Table 2 labels the high percentile bulbous and the low percentile slender.
- Training limbs retained a median 36% of intact tibia length, with a range of 18% to 60%.
- Shapes are normalized by estimated intact tibia length because residual length is not a consistent fraction of the intact limb. The generation script suggests 378.52 mm as the training-set average and gives a range of 313.05–466.34 mm.
- Alignment follows the International Society of Biomechanics convention used in the paper: the xz plane is transverse, yz is coronal, and xy is sagittal. Left limbs were mirrored. The tibia centroid was moved to the origin, and the mesh was rotated about the vertical axis so the posterior femoral condyles lie on a medial-lateral axis. Y is the longitudinal axis of that convention.
- The proximal boundary is an open trim, one patella height above the patella, so the mesh includes supracondylar geometry. There is no labeled mid-patellar-tendon vertex.
- Raw MRI and CT are not in the GitHub release and are not used.
- The generation script calls [ampscan](https://github.com/abel-research/ampscan), expects local paths, and warns that some mode combinations are not anatomically possible. It is not a drop-in tool for this prototype. The published `Components16.npy` also does not match the filenames the script comments ask for.

Verified file-size facts for `version-2025-07`, from the GitHub contents API. Binary STL byte size is `84 + 50 × triangles`, and these sizes divide evenly, so the triangle counts below are the binary-STL counts:

| File | Bytes | Triangles | Role |
|---|---|---|---|
| `Mean-Skin.stl` | 958,134 | 19,161 | Skin surface. Different SHA from the full-size file. |
| `Mean-Skin-Full-Size.stl` | 958,134 | 19,161 | Same triangle count, different content. Scale is not proven by the filename. |
| `Mean-Limb.stl` | 1,945,584 | 38,910 | Skin plus bones. |
| `Mean-Limb-Full-Size.stl` | 1,945,584 | 38,910 | Same triangle count as `Mean-Limb.stl`, different SHA. |
| `Mode1-*-Mode2-*.stl` (nine files) | 1,945,584 each | 38,910 each | Same class of mesh as the combined limb. |
| `Mean-Bones-Full-Size.stl` | 987,534 | — | Bones. Do not build a socket on this. |

**Unresolved:** whether `*-Full-Size.stl` is the millimetre-scaled twin of the normalized file. Same triangle count is compatible with a uniform scale, and it is also compatible with a re-export. The first proof of concept measures both bounding boxes. Until that measurement, generation treats units as unconfirmed.

**Unresolved:** whether each mode STL is one mesh or several bodies. The byte size matches the combined limb, which is strong evidence that these files include bones. A skin template is created from one only after a component split isolates a single open skin surface. If that split is ambiguous, that file is not a template.

### 3.2 Why the MVP stays inside transtibial variation

Ankle-level amputation is a different geometry and a different socket. A Syme residual limb is typically bulbous distally, can be end-bearing, and often needs a window or an expandable section so the bulb can pass a narrower proximal region. OpenLimbTT excluded Syme amputations by design. No compatible open STL set and no shared shell workflow were found. Ankle-level is unsupported for this prototype.

Transfemoral sockets differ again: the brim, ischial loading, and hip-flexion pose are not a longer version of a transtibial shell. OpenLimbTF version `2025-05` has seven training cases, is unpublished, is normalized to intact femur length, and ships combined limb files rather than a skin file. Supporting it would add a second template family and a second shell strategy.

The demonstration value we can actually earn is visible change within one level: a shorter transtibial limb, a longer one, and a more tapered or more bulbous profile. Those are the two modes the OpenLimbTT paper already interprets, and they reuse one socket pipeline.

Proposed library, in priority order:

| ID | Intended shape | Source, if the proof of concept succeeds | MVP |
|---|---|---|---|
| `tt_mean` | Mean transtibial skin | `Mean-Skin.stl`, after the unit check | Required. The demo runs with this file alone. |
| `tt_short` | Shorter residual limb, mean soft-tissue profile | Skin body of `Mode1-20th-Mode2-Mean.stl` | Required only if the skin split is clean. |
| `tt_long` | Longer residual limb, mean soft-tissue profile | Skin body of `Mode1-80th-Mode2-Mean.stl` | Same condition. |
| `tt_slender` | Mean length, more tapered soft tissue | Skin body of `Mode1-Mean-Mode2-20th.stl` | Stretch, after the sign of mode 2 is confirmed on the mesh. |
| `tt_bulbous` | Mean length, fuller soft tissue | Skin body of `Mode1-Mean-Mode2-80th.stl` | Stretch, same condition. |

The paper's percentile labels support that mapping, and the file names are 20th and 80th rather than the 2.5th and 97.5th extremes. Confirm the visual direction before the user interface calls a file "short" or "bulbous."

Do not synthesize a template by typing new diameters into an empty mesh. If the mode files cannot donate a clean skin surface, the library is one template, `tt_mean`, and length and circumference are applied only inside the clamps in [section 5](#5-measurement-driven-residual-limb-customization).

### 3.3 Template metadata

Every accepted template gets a hand-authored sidecar, written once after inspection. The sidecar is data, not a clinical landmark detector.

```yaml
template_id: tt_mean
source_repo: abel-research/OpenLimbTT
source_version: "2025-07"
source_file: Mean-Skin.stl
source_sha256: <filled when vendored>
license: CC-BY-SA-4.0
units_status: unconfirmed   # becomes mm only after the bounding-box check
axis: [0, 1, 0]             # confirmed against the longest open-surface axis
proximal_end: open_boundary
distal_end: closed_tip
# Approximate demo station, chosen by looking at the mesh.
# This is not a detected mid-patellar tendon.
reference_station_fraction: <annotated>
reference_to_distal_mm: <measured after scaling>
perimeter_mm_at_stations: {}
```

The original file is stored unchanged. Customization always copies it.

## 4. Practitioner questionnaire and required measurements

### 4.1 What a questionnaire can and cannot do

Published practice collects more than three numbers, and even a dense tape series is a weak shape record.

- ISO 8548-2:2020 defines how to describe a lower-limb amputation stump and which measurements to record for a prosthesis. A secondary summary of Table 8 lists transtibial team measurements as L3, L6, and C4, and prosthetist-only measurements as C6x, W4, W5, and A2. The full figures and definitions are in the paid standard and were not re-derived here. The standard also records skin, circulation, pain, phantom sensation, and joint function. Those items describe the person and the stump. They do not define a mesh.
- Manufacturer casting guides ask for circumferences about every 2 cm, plus landmarks such as the patella, patellar tendon, tibial crest, and fibular head ([Össur hand-casting notes](https://cdn.ortoped.ca/Assets/PDFs/ossur_icerossoriginallockingliner_instructions.pdf); [Blatchford liner casting guide](https://www.blatchfordmobility.com/media/wffjvrsq/936570-liner-casting-guide_web.pdf)). A fabrication form used by Hanger asks for measurements at 1 inch intervals and for the mid-patellar tendon, fibular head, and distal tibia to be located on the cast or scan.
- Seminati and colleagues found that tape methods can track volume with intra- and inter-rater ICCs above 0.9, while shape error for circumferential measurement exceeded 10% for cross-sectional area and 5% for perimeter, worse than the structured-light scanners in that study ([Seminati et al., 2022](https://doi.org/10.1097/pxr.0000000000000105)).
- Geil found that common prosthetist measurements on transtibial foam models are usable, and that the particular VAPC caliper in that study was inaccurate ([Geil, 2005](https://doi.org/10.1682/jrrd.2004.05.0054)).
- Dickinson and colleagues, on 67 UK residual-limb scans, reported mean length from patellar tendon to distal tip of 156 mm (SD 29) and mean patellar-tendon perimeter of 383 mm (SD 40) ([Dickinson et al., 2021](https://doi.org/10.3390/prosthesis3040027)).
- A volume-measurement review reports a 55-person transtibial series with mean residual length 11.08 cm (SD 2.81, range 6–18), measured against the tibial tubercle rather than the patellar tendon ([Sanders and Fatone, 2011](https://pmc.ncbi.nlm.nih.gov/articles/PMC4423813/)). Landmark choice changes the number. The questionnaire must not mix landmarks.

A US patent describes rebuilding a limb mesh from a height and a few circumferences by rescaling the cross-sections of a reference shape (US 7,617,072). That prior art is one reason the algorithm in section 5 is plausible. It is also a reminder that the result is a scaled reference, not imaged anatomy. This project implements its own mesh operation for a synthetic demo. It does not reproduce a commercial measuring device.

**Demo reconstruction uses length and two circumferences to move an existing template. Clinical socket fitting additionally requires tissue tolerance, scars, pain, joint range, volume state, liner and suspension choice, alignment, and a test fitting.** The questionnaire may display the clinical items so a user understands the boundary. The geometry engine rejects them.

### 4.2 Station convention used by the MVP

One landmark, three possible stations. Stations are distances along the residual limb, not fractions of intact tibia length.

| Station | Definition shown to the user | Role |
|---|---|---|
| Length | Straight-line soft-tissue length from the mid-patellar tendon to the distal end, knee extended. | Essential. Sets the axial warp. |
| P | Circumference in a plane perpendicular to the long axis, 40 mm distal to the mid-patellar tendon. | Essential. Sets the proximal radial scale. |
| D | Circumference in a plane perpendicular to the long axis, 40 mm proximal to the distal end. | Essential. Sets the distal radial scale. |
| M | Circumference halfway between P and D. | Optional. Adds one interpolation knot. |

The 40 mm offset follows the 4 cm interval used in several measurement studies. It avoids the tendon flare and the unstable tip. It is a demo convention, not an ISO reference level. ISO's mid-patellar-tendon, inflection, and stump-end levels remain the right vocabulary for a later clinical description.

Posture is recorded as `supine`, `sitting`, or `standing`. OpenLimbTT scans were taken supine. The demo does not attempt to correct for posture. If the user selects a posture other than supine, the report says the template pose and the measurement pose differ.

### 4.3 Questions

Input ranges below are what the form accepts. The template's own acceptance window is tighter and is computed from that template. A number can be valid as a typed measurement and still be outside the template.

#### Q1. Amputation level

1. **Question:** "Which amputation level is this demonstration for?"
2. **Input:** enum `transtibial`. No other value is accepted. Unitless.
3. **How it is obtained:** the practitioner selects the surgical level they intend to demonstrate.
4. **Point of care:** yes, as a classification. The demo does not infer level from measurements.
5. **Geometry:** selects the template family. Only `transtibial` has templates.
6. **MVP:** essential.
7. **Sources:** ISO 8548-2 distinguishes transtibial, transfemoral, ankle disarticulation, and partial foot because their reference levels differ. OpenLimbTT included only tibial-diaphysis amputations.
8. **If missing or unsupported:** the agent asks. `transfemoral`, `ankle_disarticulation`, `knee_disarticulation`, and `partial_foot` return `unsupported_level` and do not load a template. The agent explains that those levels need a different template and a different shell, which this demo does not have.

#### Q2. Residual-limb length

1. **Question:** "With the knee extended, what is the length from the mid-patellar tendon to the distal end of the residual limb?"
2. **Input:** number, millimetres. Form range 50–300. Stored as `length_mm`.
3. **How it is obtained:** a tape or ruler between those two points. The form shows the mid-patellar tendon, which is the midpoint of the tendon between its origin and insertion, matching the ISO definition of that level.
4. **Point of care:** a practitioner who can palpate the tendon can take it. Someone who cannot identify the tendon should stop. The Össur guide measures from the distal edge of the patella instead. That is a different landmark and is not an alias for this field.
5. **Geometry:** axial scale of the mesh distal to the template's annotated reference station. Proximal vertices stay put. Circumferences are not changed by this step.
6. **MVP:** essential.
7. **Sources:** ISO 8548-2 mid-patellar tendon and stump end; Dickinson et al. 2021 mean 156 mm (SD 29) from patellar tendon to tip; Sanders and Fatone 2011 review of the 6–18 cm tubercle-referenced series.
8. **If missing:** customization does not run. **If outside 50–300:** the form rejects it. **If inside the form range but outside 0.70–1.40 times that template's reference-to-distal length:** `validate_measurements` returns `outside_template` and names a closer template when one exists. The agent asks before switching templates. It does not extrapolate.

#### Q3. Proximal circumference

1. **Question:** "What is the circumference 40 mm below the mid-patellar tendon, measured perpendicular to the long axis of the residual limb?"
2. **Input:** number, millimetres. Form range 150–550. Stored as station `P`.
3. **How it is obtained:** a tape (a Gulick tape if one is available) around the limb at that level, snug, without compressing the soft tissue. Measure over the same condition the user states: `bare` or `over_liner`. The demo default is `bare`, because the templates are skin surfaces.
4. **Point of care:** yes for a practitioner, with the landmark caveat above. Seminati et al. report perimeter disagreement above 5% for tape measurement, so the tool's success tolerance is coarser than a scanner.
5. **Geometry:** radial scale of the cross-section at the proximal control station. Section shape is preserved; the section is not forced to a circle.
6. **MVP:** essential.
7. **Sources:** 2–4 cm clinical intervals in the casting guides and in Seminati et al.; Dickinson et al. 2021 patellar-tendon perimeter mean 383 mm (SD 40). Commercial liner charts list distal circumferences roughly 18–40 cm, which is a product envelope, not a population distribution.
8. **If missing:** customization does not run. **If the implied scale is outside 0.75–1.35 of the template perimeter at that station:** `outside_template`. The agent reports the template's own perimeter and asks whether to keep the template shape or pick another template. It does not apply the out-of-range scale.

#### Q4. Distal circumference

1. **Question:** "What is the circumference 40 mm above the distal end, measured perpendicular to the long axis?"
2. **Input:** number, millimetres. Form range 100–500. Stored as station `D`.
3. **How it is obtained:** the same tape method. The limb is supported and the soft tissue is not pulled into a false cone.
4. **Point of care:** yes, and less dependent on palpation than station P, provided the distal end is identifiable. The last few centimetres of a residual limb are soft and easy to deform with the tape.
5. **Geometry:** radial scale at the distal control station. Between P and D the scale is interpolated. The distal cap uses the station-D scale and does not invent a new tip outline.
6. **MVP:** essential.
7. **Sources:** same interval literature as Q3. A small published case series of experienced transtibial prosthesis users reported distal circumferences of about 23–29 cm and proximal circumferences of about 30–38 cm ([Kwon et al. participant table](https://www.nature.com/articles/s41598-021-87657-2/tables/1)). That is an illustration of magnitude, not a normal range.
8. **If missing:** customization does not run. **If `D` exceeds `P` by more than 15%:** `inconsistent_taper`. Some fullness is plausible, and a larger inversion usually means a landmark or a tape error. The agent shows both numbers and asks which one to correct. **If the scale is outside 0.75–1.35:** same `outside_template` path as Q3.

#### Q5. Mid circumference

1. **Question:** "Optional: what is the circumference halfway between the proximal and distal measurement levels?"
2. **Input:** number, millimetres. Form range 100–550. Stored as station `M`.
3. **How it is obtained:** the same tape method at the midpoint.
4. **Point of care:** yes.
5. **Geometry:** one extra interpolation knot. It cannot create a local bulge away from the station.
6. **MVP:** optional.
7. **Sources:** denser 2 cm series are standard in casting practice. One midpoint is the most this deformation can honestly use.
8. **If missing:** scale at the midpoint is interpolated from P and D, and the result says so. **If M is outside the band between P and D by more than 20 mm:** `inconsistent_profile`. The agent asks whether the mid measurement is intentional. A bulbous template does not by itself authorize an arbitrary mid-limb spike.

#### Q6. Medial-lateral and anterior-posterior widths

1. **Question:** "Optional: at the same level as the proximal circumference, what are the medial-lateral width and the anterior-posterior depth?"
2. **Input:** two numbers, millimetres. Each form range 40–200. Both must be present together.
3. **How it is obtained:** calipers at the proximal station, in the frontal and sagittal directions. Geil's results argue for an ordinary caliper rather than an uncalibrated specialty gauge.
4. **Point of care:** possible, less repeatable than a circumference, and easy to take at the wrong height.
5. **Geometry:** the ratio AP/ML sets an anisotropic scale in the section plane. The circumference, if present, then sets the overall size. Circumference wins when the ellipse implied by AP and ML disagrees with it.
6. **MVP:** optional. Drop it if the isotropic path is not yet remeasuring within tolerance.
7. **Sources:** ISO 8548-2 includes width and anteroposterior measurements among prosthetist measurements. Geil 2005 studied exactly these linear dimensions.
8. **If one of the pair is missing:** ignore both and tell the user. **If the ellipse perimeter and the tape circumference disagree by more than 15%:** `inconsistent_section`. The agent asks which measurement to keep. **If absent:** the template's own section shape is preserved and only uniformly scaled.

#### Q7. Distal-end description

1. **Question:** "Optional: how should the distal end look in this demonstration: like the template, slightly rounder, or slightly more tapered?"
2. **Input:** enum `template`, `rounder`, `more_tapered`.
3. **How it is obtained:** the practitioner looks at the residual limb. This is an observation, not a reconstructed surgical end.
4. **Point of care:** yes, as a coarse description.
5. **Geometry:** `distal_roundness` of 0, +0.15, or −0.15 on a 0–1 parameter. Zero keeps the template tip. The cap radius cannot exceed the last stable cross-section.
6. **MVP:** optional. Supported in conversation only after the radial-scale proof of concept passes.
7. **Sources:** OpenLimbTT mode 2 and modes 5–6 describe distal soft-tissue coverage, which a single adjective does not identify. The parameter is a local blend, not a mode score.
8. **If the user asks for a Syme bulb, a squared surgical end, or a bone bridge:** `unsupported_shape`. The agent names the supported adjectives and does not edit the mesh.

#### Q8. Side

1. **Question:** "Is this a left or a right residual limb?"
2. **Input:** enum `left`, `right`.
3. **How it is obtained:** observation.
4. **Point of care:** yes.
5. **Geometry:** a mirror of the template. OpenLimbTT already mirrored training limbs to one side.
6. **MVP:** optional. Default `right` to match the published orientation, and say so.
7. **Sources:** OpenLimbTT alignment methods.
8. **If missing:** keep the template side and label the view. Do not ask if the rest of the demo is blocked on it.

#### Q9. Items the form can show and the geometry must ignore

| Item | Why a clinician records it | MVP class | What the system does |
|---|---|---|---|
| Scars, grafts, neuromas, pain sites | Rectification and relief. | Unsupported for geometry. | Stored in the session note if the user types them. Never sent as a mesh argument. |
| Skin condition and circulation | ISO stump description. | Unsupported. | Same. |
| Knee range and flexion contracture | Changes shape and alignment. OpenLimbTT mode 4 includes scan flexion. | Unsupported. | If the user reports a contracture, the agent says the template is an extended supine shape and will not bend it. |
| Muscle strength, phantom pain | Clinical description. | Unsupported. | Not parsed into tools. |
| Liner model and ply | Changes the shape a socket is built over. | Unsupported as a prescription. | Socket clearance is a separate demonstration number, chosen later, and labeled as geometric clearance. |
| Body weight and activity | Used in some shops to choose wall thickness. | Unsupported as a design rule. | Wall thickness is a manufacturing argument in the socket tool, 2–6 mm, chosen explicitly. |
| Contralateral limb length | ISO asks for it so the stump can be related to the person. | Unsupported. | Intact tibia length is not asked. The template scale is confirmed once, from the file's bounding box, not from a patient height formula. |

### 4.4 Minimum viable questionnaire

The live demo asks Q1, Q2, Q3, and Q4, plus the print questions later. Q5–Q8 are accepted if the user volunteers them. Q9 is visible as a "not used for shape" note so the audience hears the boundary.

Natural language can fill the same four fields. "The residual limb is about 15 cm long, 30 cm near the top and 24 cm near the distal end" becomes `length_mm: 150`, station P `300`, station D `240`, with `source: conversation` and `precision: approximate`. The agent repeats the parsed numbers before the first customization. An approximate value is still a measurement, and it is still checked against the template window.

## 5. Measurement-driven residual-limb customization

### 5.1 Algorithms considered

| Approach | Fit to this project | Decision |
|---|---|---|
| Cross-sectional radial scaling with monotone interpolation | Uses the measurements we actually have. Moves existing vertices, so face count stays constant. Direct to expose as one tool. | **MVP algorithm.** |
| Axial warp for length, separate from radial scale | Stops a length change from also inflating every circumference. | **Part of the MVP algorithm.** |
| Global uniform scale | One number cannot meet two circumferences and a length. | Fallback only, and it must be labeled coarse. |
| PCA / statistical shape model fit | OpenLimbTT is already a PCA model, which is attractive. The published mode STLs match the combined limb, not the skin. Fitting two circumferences to mode scores is underdetermined. The authors warn that some score combinations are not anatomical. Leave-one-out recreation with full surface correspondence is already 1.82–5.75 mm RMSE (median 3.40 mm). Sparse tapes would be worse. | Not the MVP. Revisit only with a skin-only mode matrix and dense data. |
| Non-rigid registration | Needs a target surface. A handful of circumferences is not a target surface. | Rejected for the MVP. |
| Landmark-constrained deformation | Right idea clinically, and the templates have no labeled patellar tendon, tibial crest, or fibular head. | The single reference station is hand-annotated metadata. Automatic landmarks are out of scope. |
| Blender sculpt or armature | Possible, and slow to wrap as a pure function. GPL code from an interactive add-on should not be copied in. | Fallback shell kernel only, as a subprocess. |
| FreeCAD loft from profile sketches | Builds a new solid from silhouettes and throws away the template. | Rejected as the primary path. |

Libraries for the MVP path: [trimesh](https://trimsh.org/) for load, section, bounds, and export; NumPy for vertex updates; SciPy `PchipInterpolator` for monotone scale curves. [manifold3d](https://github.com/elalish/manifold) is reserved for the socket solid, not for the limb edit. ampscan is a useful Prosthetics and Orthotics analysis package and is not required to move vertices.

### 5.2 Proposed MVP algorithm

The tool never edits the template file. It copies the mesh, applies the steps below, and writes `limbs/<limb_id>/<revision>/limb.stl`.

1. **Load and classify.** Require one open skin surface. A combined skin-and-bone mesh returns `combined_mesh` and is not deformed.
2. **Units.** Read the sidecar. If `units_status` is not `mm`, refuse. The unit proof of concept is what sets that flag.
3. **Axis.** Use the sidecar axis, then check that it is still the longest dimension of the skin. Distal is the closed tip. Proximal is the open boundary.
4. **Length warp.** Let `s = 0` at the annotated reference station and `s = 1` at the distal tip. Vertices with `s < 0` stay fixed. Vertices with `s ≥ 0` move along the axis by `s' = s × (length_target / length_template)`. This changes length and leaves section size unchanged. Clamp the ratio to 0.70–1.40.
5. **Measure current perimeters** at P, M, and D on the length-warped copy, with planes perpendicular to the axis. A station that returns more than one loop is moved by 2% of length, up to three times. If it is still ambiguous, return `unstable_station`.
6. **Radial scales.** At each provided station, `scale = target_perimeter / measured_perimeter`. Missing optional stations do not create a knot. Interpolate scale along `s` with a monotone cubic. Clamp each knot to 0.75–1.35 before interpolation.
7. **Move vertices.** For a vertex at station `s`, `position' = centroid(s) + scale(s) × (position − centroid(s))`. Centroids are sampled on planes and interpolated. This keeps the template's oval or irregular section. It does not turn the limb into a stack of circles.
8. **Optional anisotropy.** If AP and ML were accepted, apply that ratio in the section plane first, then apply the uniform scale that restores the target perimeter.
9. **Distal cap.** Planes near the tip are unstable. On the last 8% of length, hold the station-D scale and, if requested, blend toward a hemisphere whose radius is the last stable section radius, by `distal_roundness` in [−0.30, +0.30]. Default 0.
10. **Remeasure.** Slice the same stations. Accept the revision only if every targeted perimeter is within 3 mm or 2%, whichever is larger, and the length is within 2 mm. Otherwise return `target_not_met` and delete the failed output.
11. **Topology checks.** Face count equals the template. The proximal boundary is still one loop. No non-finite vertex. A self-intersection check runs if the implementation has one; if the check is unavailable, the report says it was not run.

What this algorithm cannot do, and must not be described as doing:

- It cannot recover the tibial crest, fibular head, or muscle bulk between stations.
- It cannot turn a transtibial template into another amputation level.
- It cannot apply a different scale on the front of a section from the back, except for the single optional AP/ML ratio.
- Error against a real limb is unknown. The relevant published errors are for scan-to-scan SSM reconstruction, which had full surfaces. Tape error is larger than that.

### 5.3 Coarse fallback

If step 10 fails twice, the tool can write a revision with one uniform radial scale equal to the mean of the accepted station scales, and `method: coarse_uniform_scale`. The agent tells the user the stations were not matched independently. If that also fails, it exports the unedited template in millimetres and records the measurements as requested and not applied.

## 6. Conversational editing and version management

The chat transcript is not the measurement record. A session document is.

```json
{
  "limb_id": "limb_01",
  "template_id": "tt_mean",
  "revision_id": "r3",
  "parent_revision_id": "r2",
  "confirmed": {
    "length_mm": 150,
    "stations": [
      {"id": "P", "circumference_mm": 300},
      {"id": "D", "circumference_mm": 260}
    ],
    "distal_roundness": 0.15
  },
  "locks": ["length_mm", "P"]
}
```

`locks` lists fields the user has confirmed and has not since corrected.

The agent interprets an utterance into a patch. Code applies the patch.

| Utterance | Patch | Agent behavior |
|---|---|---|
| "15 cm long, 30 cm at the top, 24 cm at the end." | Sets length, P, and D. | Repeat the numbers. Call `validate_measurements`, then `customize_residual_limb`. |
| "Actually the distal circumference should be 26 cm." | Correction of D only. | Set `correction: true` on D. Leave length and P locked. New revision. |
| "Make the distal end slightly more rounded." | `distal_roundness` +0.15, if inside range. | Apply it, state the value, and show the comparison. "Slightly" and "a bit" are defined as 0.15 so the demo does not stall. "Much rounder" asks for one of the supported steps. |
| "A bit longer." | Not a number. | Ask for a length. Do not add a hidden 10 mm. |
| "Relieve the fibular head." | Unsupported. | Explain that relief is a fitting operation this demo does not perform. |
| "Change the socket wall" while a limb is current and no socket exists. | Different object. | Ask whether to generate a socket, and do not edit the limb. |

Rules enforced in the tool, not only in the prompt:

- A locked field that changes without `correction: true` returns `unconfirmed_overwrite` and writes nothing.
- Every successful customize creates a new revision. The parent file remains.
- After each revision the tool remeasures and returns the station errors.
- `compare_limb_versions` reports length delta, perimeter delta at each station, bounding-box delta, and mean and max radial difference. The viewer uses those numbers. A color map is a stretch goal.
- Two failed customizations on the same patch stop the loop. The last good revision stays current.

Revision ids are `r1`, `r2`, … within a limb. Socket revisions are a separate series, each pointing at the limb revision they were built from. A new limb revision invalidates the current socket certificate and any slice approval.

## 7. Prosthetic socket CAD generation

### 7.1 What the socket tool is

The socket tool consumes a **validated limb revision** and produces a new closed triangle mesh. It does not read the questionnaire and it does not rectify.

Published CAD workflows that this design borrows from, as geometry rather than as fit:

- Facoetti, Colombo, Rizzi, and colleagues generate a socket reference by a constant offset from the prepared stump, then thicken outward. Their paper gives a shop range of about 2–6 mm for that thickness ([Facoetti et al., 2010](https://cad-journal.net/files/vol_7/CAD_7(5)_2010_723-737.pdf)).
- Fused-filament transtibial demonstration sockets in the literature are often printed around 4 mm, with local reinforcement treated as a separate design problem ([van der Stelt et al., 2022](https://doi.org/10.3390/prosthesis4040048)).
- A low-cost CAD note builds the socket by extracting the positive, offsetting about 3 mm, and orienting the distal end toward the printer bed so supports stay off the inner surface.

Those numbers are manufacturing precedents for a demo. They are not a prescription. Clearance in this project is an air gap in the mesh. Wall thickness is a solid thickness. Neither is a liner specification or a load rating.

[uFit](https://github.com/Ugani-Prosthetics/ufit-blender) already sequences import, thickness, trim, flare, and STL export for transtibial sockets. It is an interactive Blender add-on and requires an account. Its operators are not called. The order of operations is the useful part. If manifold3d cannot close a shell, the fallback is a Blender subprocess running our own Solidify script, not a copy of uFit.

### 7.2 Proposed shell procedure

1. Copy the limb revision. Orient the long axis to printer Z, distal tip toward minimum Z, proximal opening toward +Z.
2. Cut a proximal opening at `trim_fraction` of the reference-to-distal segment. Default 0.15, meaning the opening sits a short distance proximal to station P. Allowed range 0.05–0.35. This is a planar geometric trim. It is not a hamstring relief or a patellar-tendon-bearing trimline.
3. Offset the remaining surface outward by `clearance_mm` (0–3, default 1.5). Zero means the inner wall follows the limb reference.
4. Thicken outward by `wall_thickness_mm` (2.0–6.0, default 4.0).
5. Close the inner wall, the outer wall, and a rim annulus into one watertight shell. The cavity is inside the solid. The triangle mesh that goes to the slicer has no open boundary.
6. Optionally round the rim with `rim_radius_mm` 0–3, without reducing the local wall below 2.0 mm.
7. Export `sockets/<socket_id>/<revision>/socket.stl`.

Decorative relief on the outer wall is a stretch goal: depth 0.2–0.8 mm and under 25% of the wall, distal half only, no through-holes. It is off until the plain shell slices.

User input at this stage is the three numbers above, or acceptance of the defaults. The limb measurements are not asked again. Changing a limb measurement after a socket exists requires a new limb revision and a new shell. The old shell is kept and marked stale.

### 7.3 Fallback if the shell fails

If the offset or the boolean fails, keep the limb revision, report the failure, and do not upload anything. The second attempt may drop rim rounding and set clearance to 0, still inside the argument ranges. A third failure stops. The coarse fallback is a pre-authored closed shell around the unedited `tt_mean` template at the default wall, clearly labeled as a stand-in that does not reflect the questionnaire. That stand-in exists only so the print half of the demo can be shown. The report says the questionnaire was not applied to the shell.

## 8. Tool-calling architecture and function registry

### 8.1 Processes

```text
Browser
  questionnaire, chat, limb viewer, socket viewer, comparison, confirmations
        |
        v
Python agent
  measurement document, phase filter, argument checks, confirmation store, audit log
        |
        +-- Nemotron 3.5 Lightning through Red Hat vLLM
        |
        +-- Geometry functions, in process
        |     templates, measurements, limb deformation, socket shell, certificates
        |     trimesh, NumPy, SciPy, manifold3d
        |
        +-- Manufacturing functions, in process
              PrusaSlicer CLI, OctoPrint Virtual Printer
              SQLite for revisions, jobs, confirmations, audit
```

Direct Python functions are the MVP. vLLM already returns OpenAI-style tool calls, so a second transport does not make the demo more reliable. Two MCP servers, one for geometry and one for manufacturing, are a later split once the in-process loop is boringly repeatable.

The model never receives the OctoPrint API key, a filesystem path, or a raw G-code channel. Tools accept ids. The server resolves them.

### 8.2 Result envelope

Every tool returns:

| Status | Meaning | What the model should do |
|---|---|---|
| `success` | The call ran. A validation that fails is still `success` when `data.passed` is false. | Read the data and choose the next legal step. |
| `fixable` | The arguments or the mesh can be corrected inside a known range. | Correct the arguments and retry, at most twice. |
| `fatal` | The same call will not succeed. | Stop that path, keep the last good revision, and tell the user. |

```json
{
  "status": "success",
  "message": "Limb revision r2 written. Station errors are within tolerance.",
  "data": {},
  "error": null
}
```

A `fixable` error includes `error.code`, `error.reason`, and `error.valid`.

### 8.3 Phases

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

A failed limb edit stays on the previous `limb_current`. A failed socket validation returns to `socket_current` only if a prior certificate existed; otherwise it stays designed and uncertified. A lost printer connection moves the job to `unknown`. The tool list sent to the model is the legal set for the phase.

| Phase | Tools the model can see |
|---|---|
| `empty` | `list_limb_templates`, `inspect_limb_template`, `ask_user` |
| `template_selected` | `validate_measurements`, `ask_user` |
| `measurements_ready` | `customize_residual_limb` |
| `limb_current` | `measure_customized_limb`, `compare_limb_versions`, `validate_measurements`, `customize_residual_limb`, `generate_socket_shell` |
| `socket_current` | `validate_socket_geometry` |
| `socket_validated` | `request_confirmation` for slice, then `slice_model` |
| `sliced`, printer ready, unused print confirmation | `start_print` |
| `printing` or `unknown` | `reconcile_printer_state`, `request_safe_pause` |

`start_print` is omitted while the phase is `unknown`.

### 8.4 Recommended tools

Fourteen model-callable tools. Several names from the design discussion are folded into these so the model has fewer chances to update one number and forget to regenerate.

Folded on purpose:

- `get_required_measurements` is the `required_measurements` field of `inspect_limb_template`.
- `export_customized_limb_stl` and `export_socket_stl` are URLs in the success payload. Export is not a separate permission.
- `set_socket_clearance`, `set_wall_thickness`, and `modify_socket_rim` are arguments of `generate_socket_shell`. A change calls that tool again and writes a new socket revision.
- `get_printer_status` is part of `check_printer_readiness` and `reconcile_printer_state`.

#### `list_limb_templates`

Purpose: list templates the library can actually deform. Priority: required.

```json
{
  "type": "object",
  "additionalProperties": false,
  "properties": {
    "level": {
      "type": "string",
      "enum": ["transtibial"]
    }
  }
}
```

Returns `{templates: [{template_id, label, level, units_status, available}]}`. A template with `units_status != "mm"` or a failed skin split has `available: false`. Error `unsupported_level` for any other level.

Implementation: read the sidecar directory.

#### `inspect_limb_template`

Purpose: report the template's axis, length, station perimeters, and the questionnaire fields still required. Priority: required.

```json
{
  "type": "object",
  "additionalProperties": false,
  "required": ["template_id"],
  "properties": {
    "template_id": {"type": "string", "enum": ["tt_mean", "tt_short", "tt_long", "tt_slender", "tt_bulbous"]}
  }
}
```

Returns bounds in mm, `reference_to_distal_mm`, perimeters at P, M, and D, `required_measurements`, and `optional_measurements`. Error `unknown_template`, or `units_unconfirmed` if the sidecar is not yet marked `mm`.

Implementation: trimesh load of the cached skin, or the precomputed sidecar if the hash matches.

#### `validate_measurements`

Purpose: accept or reject a measurement document before any vertex moves. Priority: required.

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

Returns `{accepted, normalized, warnings}`. Codes: `missing_required`, `outside_template`, `inconsistent_taper`, `inconsistent_profile`, `inconsistent_section`, `unconfirmed_overwrite`, `unsupported_field`. An unexpected JSON field is `unsupported_field`. Clinical notes in Q9 are unsupported fields.

Implementation: pure Python against the sidecar ranges and the parent revision's locks. No mesh write.

#### `customize_residual_limb`

Purpose: run the algorithm in section 5 and write a revision. Priority: required.

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
    "measurements": {"type": "object"}
  }
}
```

`validation_id` must be a passing result for this exact measurement document. The model cannot skip validation by inventing an id; the server issued it.

Returns `{limb_id, revision_id, parent_revision_id, method, stl_url, measured_length_mm, stations: [{id, target_mm, measured_mm, error_mm}], face_count}`.

Errors: `validation_mismatch`, `combined_mesh`, `unstable_station`, `target_not_met`, `self_intersection`. `target_not_met` may include `coarse_available: true` once, and only the server may set `method` to `coarse_uniform_scale` on an explicit retry flag `allow_coarse: true`.

Implementation: section 5. trimesh, NumPy, SciPy.

#### `measure_customized_limb`

Purpose: remeasure a stored revision, including stations the user did not target. Priority: required.

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
      "items": {"type": "string", "enum": ["P", "M", "D"]},
      "minItems": 1,
      "maxItems": 3
    }
  }
}
```

Returns length, perimeters, and whether each station was a single loop. This is the check the agent reads back to the user after a conversational edit.

#### `compare_limb_versions`

Purpose: quantify two revisions of the same limb for the viewer and the chat. Priority: required.

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

Returns per-station perimeter deltas, length delta, bounding-box delta, and mean and max radial difference in mm. Error `topology_mismatch` if face counts differ, because the radial difference is then not vertex-wise. The frontend places the two STLs side by side and prints this table. A vertex-color overlay is optional.

#### `generate_socket_shell`

Purpose: build a demonstration shell from one limb revision. Priority: required.

```json
{
  "type": "object",
  "additionalProperties": false,
  "required": ["limb_id", "revision_id"],
  "properties": {
    "limb_id": {"type": "string"},
    "revision_id": {"type": "string"},
    "clearance_mm": {"type": "number", "minimum": 0, "maximum": 3, "default": 1.5},
    "wall_thickness_mm": {"type": "number", "minimum": 2, "maximum": 6, "default": 4},
    "trim_fraction": {"type": "number", "minimum": 0.05, "maximum": 0.35, "default": 0.15},
    "rim_radius_mm": {"type": "number", "minimum": 0, "maximum": 3, "default": 1}
  }
}
```

Returns `{socket_id, revision_id, source_limb_revision, stl_url, watertight}`. Errors: `limb_not_current`, `offset_failed`, `not_closed`. A new limb revision makes an older socket stale; the tool will still build from an explicit older revision if asked, and marks `stale_limb: true` when a newer limb exists.

Implementation: trimesh and manifold3d. Blender Solidify subprocess only after the offset proof of concept fails.

#### `validate_socket_geometry`

Purpose: one certificate for closure, wall, build volume, and overhangs. Priority: required.

```json
{
  "type": "object",
  "additionalProperties": false,
  "required": ["socket_id", "revision_id", "printer_profile_id"],
  "properties": {
    "socket_id": {"type": "string"},
    "revision_id": {"type": "string"},
    "printer_profile_id": {"type": "string", "enum": ["draft_028", "demo_020"]},
    "min_wall_mm": {"type": "number", "minimum": 2, "maximum": 6, "default": 2},
    "max_overhang_deg": {"type": "number", "minimum": 30, "maximum": 70, "default": 55}
  }
}
```

Returns each check, the measured minimum wall, the bounding box, and `certificate_id` only when all required checks pass. A failed check is `status: success` with `passed: false`, so the model can read the numbers. `certificate_id` is server-minted.

Implementation: trimesh watertight and component tests, sampled thickness, profile build volume, overhang versus +Z.

#### `slice_model`

Purpose: slice one certified socket revision. Priority: required.

```json
{
  "type": "object",
  "additionalProperties": false,
  "required": ["socket_id", "revision_id", "profile_id", "confirmation_id", "certificate_id"],
  "properties": {
    "socket_id": {"type": "string"},
    "revision_id": {"type": "string"},
    "profile_id": {"type": "string", "enum": ["draft_028", "demo_020"]},
    "confirmation_id": {"type": "string"},
    "certificate_id": {"type": "string"}
  }
}
```

The confirmation must name this revision. The certificate must be newer than the revision and must name the same profile family. Returns `{job_id, estimated_seconds, filament_mm, filament_g, gcode_sha256}`. Errors: `certificate_stale`, `confirmation_mismatch`, `outside_volume`, `slicer_failed`.

Implementation: PrusaSlicer CLI `--export-gcode` with a pinned INI. Time and filament are parsed from the slicer output. There is no separate estimate tool.

#### `check_printer_readiness`

Purpose: decide whether a start is even offerable. Priority: required.

```json
{
  "type": "object",
  "additionalProperties": false,
  "properties": {
    "expected_port": {"type": "string", "default": "VIRTUAL"}
  }
}
```

Ready only when OctoPrint is operational, the port is the virtual port, and the state is not printing, paused, or error. Returns the three upstream payloads in summary form: connection, printer, and job.

Implementation: `GET /api/connection`, `GET /api/printer`, `GET /api/job`.

#### `start_print`

Purpose: upload, select, start, and read the job back. Priority: required.

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

Slice confirmation and print confirmation are different ids. Returns `{state, verified}` after `GET /api/job`. A 204 from the start command is not success by itself. Errors: `not_ready`, `confirmation_mismatch`, `already_started`, `unverified`.

#### `reconcile_printer_state`

Purpose: compare the command ledger with the live printer. Priority: required.

No arguments. Returns `verified`, `mismatch`, or `unknown`, plus the last ledger row and the last successful `GET /api/job`.

#### `request_safe_pause`

Purpose: pause a job that is actually printing, and record the attempt when the link is down. Priority: required.

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

Returns `paused` only after a confirming read. If the link is down, returns `pause_not_delivered`.

#### `ask_user`

Purpose: ask for a missing template, landmark, measurement, or an explicit choice. Priority: required. The model does not invent a limb.

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

This call ends the model turn. The UI collects the answer.

#### `request_confirmation`

Purpose: the UI mints a one-time id. The model may request that the UI do so. The model cannot invent the id. Priority: required.

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

Returns `{confirmation_id}` only after the person approves. A slice id does not authorize a start.

### 8.5 Repairs the agent may attempt

After a failed socket certificate, the agent may:

- raise wall thickness by at most 1.0 mm, staying inside 2.0–6.0 mm
- retry the shell once with `rim_radius_mm` 0 and `clearance_mm` unchanged
- try four fixed rotations at the same scale if only the overhang check failed

Length, circumferences, template choice, and anything outside those bands require `ask_user`. After two unsuccessful repairs, the agent stops and reports the failing measurements.

## 9. Geometry validation and safety boundaries

These rules live in tool code.

- Typed arguments are checked before a mesh or a network call.
- The template file and every earlier revision are immutable.
- Limb customization and socket generation write new revisions.
- A limb edit invalidates the socket certificate and both confirmations.
- `slice_model` refuses a revision without a current certificate and a matching slice confirmation.
- `start_print` requires a different confirmation, a ready virtual printer, and a ledger check that this job is not already `sent`, `verified_printing`, or `unknown`.
- The demo instance is configured with the OctoPrint Virtual Printer only. A physical serial port fails readiness.
- The agent never reports a part printed because a command was accepted.
- Ambiguous printer results call `reconcile_printer_state`. They do not call `start_print` again.
- Virtual Printer debug commands such as `!!DEBUG:action_disconnect` belong to the demo fault injector, on a separate key. They are not agent tools.
- The OctoPrint key used by the agent has `STATUS`, `FILES_UPLOAD`, `FILES_SELECT`, and `PRINT`. It does not have `CONTROL`, so the model cannot send arbitrary G-code, jog the head, or set temperatures.
- Firmware thermal limits and endstops stay in firmware. This software does not disable them. The virtual printer does not test them.
- Fabrication reports state that the object is a nonclinical demonstration, that the limb is a scaled synthetic template, and that the checks are geometric and process checks.

Limb acceptance checks, in addition to the socket certificate:

| Check | Pass condition |
|---|---|
| Input class | One open skin surface. |
| Units | Sidecar says `mm`. |
| Length and perimeter errors | Within 2 mm, and within 3 mm or 2% for each targeted perimeter. |
| Topology | Face count unchanged. One proximal boundary loop. |
| Scale clamps | Length ratio 0.70–1.40. Section scale 0.75–1.35. |

Socket certificate checks:

| Check | Pass condition |
|---|---|
| Closure | Watertight, consistent winding, one component. |
| Wall | Sampled thickness at least `min_wall_mm` (default 2.0). |
| Build volume | Bounding box inside the selected profile. |
| Overhang | Faces steeper than `max_overhang_deg` from +Z fail, default 55°. |

## 10. Slicing and virtual printer integration

The manufacturing path from the previous plan stays, with the socket revision as its input.

```text
customized limb STL
  → socket STL
  → validate_socket_geometry
  → slice_model
  → user print confirmation
  → start_print
  → monitor GET /api/job
  → reconcile or pause
  → fabrication report
```

| Piece | Choice | Notes |
|---|---|---|
| Slicer | [PrusaSlicer](https://github.com/prusa3d/PrusaSlicer) CLI | Two INI profiles, `draft_028` and `demo_020`. No profile-list API, so the enum is the API. |
| Printer | [OctoPrint](https://docs.octoprint.org/en/main/api/) [Virtual Printer](https://docs.octoprint.org/en/main/development/virtual_printer.html) | Upload, select with `print: false`, `POST` start, then `GET /api/job`. |
| Command result | 204 with an empty body means the command was accepted. 409 means the state refused it. | Neither is proof of printing. The following GET is the proof. |
| Progress | `GET /api/job` completion and state. | The agent quotes the read state. |
| Recovery | Ledger plus reconcile plus safe pause. | A dropped link becomes `unknown`. A second start is refused. |
| Report | Dataset citation, template hash, measurement document, revision ids, certificate, profile, time, filament, printer observations, nonclinical statement. | Written from the log, not from the model's memory. |

Profiles are chosen by the user. If both have been sliced, the agent may recommend the one whose estimate finishes inside the demonstration window. It may not switch profiles silently.

## 11. Frontend experience

A single thin page is enough. A CAD viewport is a stretch goal.

| Region | Behavior |
|---|---|
| Template cards | The available sidecars. Unavailable templates are visible and disabled, with the reason. |
| Questionnaire | Q1–Q4 required. Q5–Q8 behind "more detail." Q9 as a static boundary note. Units are millimetres, with a centimetre display beside the field. |
| Chat | Same measurement document as the form. The form and the chat write the same locks. |
| Limb viewer | Current limb STL. Template shown ghosted if that is cheap to do. |
| Socket viewer | Current socket STL, separate from the limb. |
| Comparison | Side-by-side revisions plus the `compare_limb_versions` table. |
| Phase and checks | Current phase, last tool status, certificate card. |
| Print bar | Slice confirmation and print confirmation are different buttons. The print button is disabled until readiness is true and a slice exists. |
| Report | Download the fabrication report at the end. |

The viewer loads STL URLs the tools return. It does not recompute geometry in the browser.

Stack proposal: a small Python web app serving the page, and [three.js](https://threejs.org/) for the meshes. The exact web framework is unimportant. The measurement document and the phase live on the server.

## 12. Technology stack and sponsor integration

| Piece | Role in this prototype | Status |
|---|---|---|
| NVIDIA Nemotron 3.5 Lightning, 30B total, 3B active | The only generative model. It selects tools, fills arguments, and explains results. It does not perform the geometry. | Proposed. Checkpoint `NVIDIA-Nemotron-3.5-Lightning-30B-A3B`. |
| Red Hat vLLM | Serves that checkpoint with tool calling enabled, behind an OpenAI-compatible API, on the project GPU. | Proposed. Confirm the image on the instance. |
| NVIDIA NeMo Gym | The published way NVIDIA evaluates this model, and part of how it was trained. | Not in the MVP architecture. |

Verified serving flags, from the [Hugging Face model card](https://huggingface.co/nvidia/NVIDIA-Nemotron-3.5-Lightning-30B-A3B-BF16) and NVIDIA's [NIM guide for this model](https://docs.nvidia.com/nim/large-language-models/2.0.10/get-started/advanced/get-started-nemotron-3-5-lightning.html):

- `--enable-auto-tool-choice`
- `--tool-call-parser qwen3_coder`
- `--reasoning-parser nemotron_v3`

When reasoning and tool calls are both on, send `chat_template_kwargs.force_nonempty_content: true`. Without it, the content beside a tool call can come back empty.

Red Hat documents the same vLLM flags as passthrough on OpenShift AI and on Distributed Inference with llm-d ([tool calling through llm-d](https://docs.redhat.com/en/documentation/red_hat_openshift_ai_self-managed/3.5/html/deploy_models_using_distributed_inference_with_llm-d/tool-calling-through-llmd_distributed-inference)). The meaningful sponsor use on a weekend GPU instance is: run the Red Hat vLLM build, enable those parsers, and point the agent at `/v1/chat/completions`. An OpenShift cluster is not required for that and should not be built during the hackathon.

**Unresolved on the instance:** the GPU from `nvidia-smi`, whether this Red Hat build contains `qwen3_coder` and `nemotron_v3`, and whether the weekend image is BF16 or NVFP4.

NeMo Gym is how NVIDIA reproduces the model's general benchmark scores ([evaluation guide](https://docs.nvidia.com/nemotron/nightly/nemotron/lightning35/evaluate.html), [recipes](https://github.com/NVIDIA-NeMo/Gym/blob/main/nemotron_recipes/lightning-3.5/reproducibility.md)). Those recipes do not know about sockets. A custom Gym environment would need a task definition, rewards, and rollouts, which is a project of its own. It does not make the live demo more reliable. Leave it out. A later evaluation can score scripted traces without Gym: correct tool, valid arguments, completion, and whether the agent asked instead of inventing a measurement.

Why this model for the demo: only about 3B parameters are active per token, so a multi-step tool loop can stay responsive, and the server turns the output into structured tool calls. The instance is ours, so meshes and measurements are not sent to an outside model API.

## 13. End-to-end demonstration scenarios

Target length 4–6 minutes for the happy path. One recovery can be shown live. The others are recorded.

### 13.1 Happy path

1. The user selects `tt_mean`.
2. The form asks for level, length, station P, and station D.
3. The user enters transtibial, 150 mm, 300 mm, and 240 mm.
4. The model validates and customizes.
5. The limb viewer shows revision `r1`, and the chat reads back the measured stations.
6. The user says the distal circumference should be 260 mm.
7. The model corrects only that field and writes `r2`.
8. The comparison view shows `r1` and `r2`.
9. The user asks for a demonstration socket.
10. The model calls the shell tool with the defaults.
11. Validation returns a certificate.
12. The user approves profile `draft_028`.
13. The model slices and reports time and filament.
14. The user presses the print confirmation.
15. The model starts the virtual printer and quotes `GET /api/job`.
16. The report is saved.

Example calls, abbreviated to the fields that matter.

Select and inspect:

```json
{"name": "inspect_limb_template", "arguments": {"template_id": "tt_mean"}}
```

Validate the first questionnaire:

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

Customize, using the server-issued validation id:

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

Correct the distal station:

```json
{
  "name": "validate_measurements",
  "arguments": {
    "template_id": "tt_mean",
    "parent_revision_id": "r1",
    "measurements": {
      "length_mm": 150,
      "stations": [
        {"id": "P", "circumference_mm": 300},
        {"id": "D", "circumference_mm": 260, "correction": true}
      ]
    }
  }
}
```

Compare and shell:

```json
{"name": "compare_limb_versions", "arguments": {"limb_id": "limb_01", "revision_a": "r1", "revision_b": "r2"}}
```

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

Certify, slice, and start:

```json
{
  "name": "validate_socket_geometry",
  "arguments": {"socket_id": "sock_01", "revision_id": "s1", "printer_profile_id": "draft_028"}
}
```

```json
{
  "name": "slice_model",
  "arguments": {
    "socket_id": "sock_01",
    "revision_id": "s1",
    "profile_id": "draft_028",
    "confirmation_id": "conf_slice_01",
    "certificate_id": "cert_01"
  }
}
```

```json
{
  "name": "start_print",
  "arguments": {"job_id": "job_01", "confirmation_id": "conf_print_01"}
}
```

### 13.2 Inconsistent circumferences

User: distal circumference 360 mm, proximal 300 mm.

`validate_measurements` returns `fixable` / `inconsistent_taper`, with both values and the 15% rule. The agent asks which number to correct. `customize_residual_limb` is not called. If the user confirms they want the larger distal value, the agent still refuses while the implied section scale is outside 0.75–1.35, and offers the unedited template as a display. It does not stretch the mesh to force the number.

### 13.3 Shell or wall failure

`generate_socket_shell` returns `offset_failed`, or `validate_socket_geometry` returns `passed: false` because the sampled wall is under 2.0 mm. The agent may raise thickness once, by at most 1.0 mm, and validate again. The limb revision is unchanged. If the second certificate fails, the agent stops and shows the measurements. Nothing is sliced.

### 13.4 Printer disconnect

After a verified start, the injector sends `!!DEBUG:action_disconnect` with the injector key. The next read fails. The agent calls `reconcile_printer_state`, gets `unknown`, calls `request_safe_pause`, and records `pause_not_delivered` if the pause cannot be read back. A second `start_print` is rejected from the ledger. The report lists the last verified state.

### 13.5 A fourth scripted case, if time allows

"Make the distal end slightly more rounded" on `r2` writes `r3` with `distal_roundness` 0.15 and the same locked length and circumferences. The comparison table shows a small radial change at the tip and no change at station P. "Fit it properly around the fibular head" hits `ask_user` with an unsupported-operation explanation and writes nothing.

## 14. MVP milestones and team responsibilities

### 14.1 What is required for a credible demo

| Choice | MVP | Later |
|---|---|---|
| Questionnaire | Level, length, P, D. | M, AP/ML, distal adjective, side. |
| Templates | `tt_mean` for certain. `tt_short` and `tt_long` if the skin split works. | `tt_slender`, `tt_bulbous`, any other level. |
| Deformation | Axial warp plus two-station radial scale. | Anisotropy, distal roundness, PCA scores. |
| Tools | The fourteen in section 8. | MCP, decorative pattern, color-map diff, Gym. |
| Socket | One offset shell at default clearance and wall. | Rim flare, variable thickness, rectification. |
| Print | One virtual start with a real confirmation gate. | Physical printer, multi-profile optimization. |

Simulate only the stand-in shell in section 7.3, and only if shell generation fails. Do not simulate the tool trace, the measurement check, or the printer readback. Those are the demo.

### 14.2 First three proof-of-concept experiments

These happen before feature work. Each one can fail the plan in a way that the fallback already names.

1. **Units and stations on `Mean-Skin`.** Load `Mean-Skin.stl` and `Mean-Skin-Full-Size.stl`. Record bounding boxes, the longest axis, whether the surface is open, and the perimeter at three planes. Decide which file is millimetres. Annotate the reference station by inspection and store it in the sidecar. Pass: one file is an open skin whose longest dimension is a plausible transtibial length after a single documented scale, and planes at P and D each return one loop.
2. **Skin split, then a two-station edit.** Attempt to separate a skin body from `Mode1-20th-Mode2-Mean.stl` and `Mode1-80th-Mode2-Mean.stl`. If that fails, stop the multi-template path. On `tt_mean`, apply length 150 mm and two perimeters, remeasure, and confirm the face count is unchanged and the untouched station did not move except through interpolation. Pass: targeted perimeters within 3 mm or 2%, and a locked proximal edit does not require regenerating from scratch.
3. **Closed shell.** Offset the customized skin with manifold3d at 1.5 mm clearance and 4 mm wall, trim the proximal end, and export a watertight STL. Run the socket checks and one PrusaSlicer dry run. Pass: one component, watertight, minimum wall at least 2 mm, slicer accepts the mesh. If manifold3d fails, repeat once with a Blender Solidify subprocess before changing the tool schema.

### 14.3 Parallel work

| Person | Owns | Depends on |
|---|---|---|
| 1 | vLLM flags, the agent loop, the measurement document, phase filter, confirmations, audit log. | A stub tool that returns the envelope, so this starts immediately. |
| 2 | Experiments 1–3, sidecars, limb deformation, socket shell, certificates. | Nothing else. This is the critical path. |
| 3 | PrusaSlicer INI files, OctoPrint Virtual Printer, fault injection, the page, the report. | A watertight STL from experiment 3 for the real slice. Until then, a hand-made closed box proves the printer gate. |

| When | Milestone |
|---|---|
| Saturday, first hours | Experiment 1 done. Nemotron returns a tool call. Virtual printer answers `GET /api/job`. |
| Saturday, midday | Experiment 2 done, or the plan is explicitly one template. Experiment 3 attempted. |
| Saturday evening | One limb revision shown in the page. One shell certified, or the stand-in shell decision recorded. |
| Saturday night | Slice, both confirmations, verified virtual start. |
| Sunday early | The three failure cases have been run. |
| Sunday morning | README matches what actually ran. Demo and video. |

**Do not cut:** an explicit unit check, a real mesh deformation or an honest coarse fallback, a real shell or the labeled stand-in, structured tool errors, the Nemotron tool loop, and the confirmation gate before a virtual print.

**Cut first:** extra templates, AP/ML, distal roundness, rim decoration, revision color maps, MCP, transfemoral or ankle support, Blender as the primary kernel, and NeMo Gym.

### 14.4 Risks

| Risk | Why it is real | What we do |
|---|---|---|
| Full-size and normalized STLs are the same physical size, or neither is millimetres. | Same triangle count, different hashes, and STL has no units. | Experiment 1. Refuse generation until the sidecar says `mm`. |
| Mode STLs cannot yield a skin. | Their byte size matches the combined limb. | Demo uses `tt_mean` only. |
| Two circumferences do not remeasure within tolerance. | Open surfaces and distal caps slice badly. Interpolation can overshoot if it is not monotone. | PCHIP and clamps. Then the coarse uniform fallback. |
| The reference station is not the mid-patellar tendon. | The dataset has no labeled tendon. | The sidecar says the station is annotated for the demo. The report repeats that. |
| manifold3d cannot offset this open surface. | Offset of an open residual-limb mesh is the known geometric risk. | Experiment 3, then Blender subprocess, then the labeled stand-in shell. |
| The model overwrites a confirmed measurement. | Conversational edits are ambiguous. | Locks and `correction: true` in the tool, not only in the prompt. |
| The Red Hat vLLM image lacks the Nemotron parsers. | Parser names are version-specific. | Confirm on the instance before writing the agent against them. |
| The demo is heard as a clinical device. | The workflow looks like a fitting workflow. | Questionnaire copy, tool descriptions, and the report all use "demonstration" and cite the dataset. |

## 15. Research references, datasets, and licenses

### Datasets

- Sunderland, F. E., Sobey, A. J., Bramley, J. L., Steer, J. W., Al-Dirini, R., Metcalf, C. D., Toderita, D., Bull, A., Ding, Z., Henson, D., Worsley, P. R., Dickinson, A. S., and the OpenLimb Group (2025). OpenLimbTT, a transtibial residual limb shape model for prosthetics simulation and design. *Data-Centric Engineering*, 6, e39. https://doi.org/10.1017/dce.2025.10019
- OpenLimbTT files, data CC BY-SA 4.0, generation code MIT: https://github.com/abel-research/OpenLimbTT
- Study record: https://doi.org/10.5258/SOTON/D2895
- Pasternak, K., Sunderland, F. E., Sobey, A. J., the OpenLimb Group, Worsley, P. R., and Dickinson, A. S. (2025). OpenLimbTF. Unpublished model, data CC BY-SA 4.0 as stated in the repository. https://github.com/abel-research/OpenLimbTF
- Alignment toolbox used by the dataset authors: https://github.com/abel-research/ampscan

Share-alike applies to meshes we derive from OpenLimbTT or OpenLimbTF. Cite the paper in the repository and in every fabrication report.

### Measurements and shape

- ISO 8548-2:2020. Prosthetics and orthotics — Limb deficiencies — Part 2: Method of describing lower limb amputation stumps. https://www.iso.org/standard/76809.html
- Dickinson, A., Diment, L., Morris, R., Pearson, E., Hannett, D., and Steer, J. (2021). Characterising residual limb morphology and prosthetic socket design based on expert clinician practice. *Prosthesis*, 3(4), 280–299. https://doi.org/10.3390/prosthesis3040027
- Seminati, E., Young, M., Canepa Talamas, D., Twiste, M., Dhokia, V., and Bilzon, J. (2022). Reliability of three methods for assessing amputee residuum shape and volume. *Prosthetics and Orthotics International*. https://doi.org/10.1097/pxr.0000000000000105
- Geil, M. D. (2005). Consistency and accuracy of measurement of lower extremity amputee anthropometrics. *Journal of Rehabilitation Research and Development*, 42(2), 131–140. https://doi.org/10.1682/jrrd.2004.05.0054
- Sanders, J. E., and Fatone, S. (2011). Residual limb volume change: systematic review of measurement and management. *Journal of Rehabilitation Research and Development*. https://pmc.ncbi.nlm.nih.gov/articles/PMC4423813/
- Wu and colleagues, as cited by the OpenLimbTT paper, for the International Society of Biomechanics axis convention used to align the training meshes.
- US 7,617,072. Device for creating a three-dimensional representation of a limb from a reduced number of measurements. Prior art for cross-section scaling of a reference mesh. Not a dependency of this prototype.

### Socket geometry and printing

- Facoetti, G., Gabbiadini, S., Colombo, G., and Rizzi, C. (2010). Knowledge-based system for guided modeling of sockets for lower limb prostheses. *Computer-Aided Design and Applications*, 7(5), 723–737. https://doi.org/10.3722/cadaps.2010.723-737
- van der Stelt, M., et al. (2022). Design evaluation of FFF-printed transtibial prosthetic sockets. *Prosthesis*, 4(4). https://doi.org/10.3390/prosthesis4040048
- uFit Blender, reviewed and not wrapped: https://github.com/Ugani-Prosthetics/ufit-blender
- PrusaSlicer: https://github.com/prusa3d/PrusaSlicer
- OctoPrint REST API: https://docs.octoprint.org/en/main/api/
- OctoPrint Virtual Printer: https://docs.octoprint.org/en/main/development/virtual_printer.html
- trimesh: https://trimsh.org/
- manifold3d: https://github.com/elalish/manifold

### Model serving

- Nemotron 3.5 Lightning model card: https://huggingface.co/nvidia/NVIDIA-Nemotron-3.5-Lightning-30B-A3B-BF16
- NVIDIA NIM guide for tool calling with this model: https://docs.nvidia.com/nim/large-language-models/2.0.10/get-started/advanced/get-started-nemotron-3-5-lightning.html
- vLLM write-up: https://vllm.ai/blog/2026-08-10-nemotron-3-5-lightning-vllm
- Red Hat tool-calling passthrough for llm-d: https://docs.redhat.com/en/documentation/red_hat_openshift_ai_self-managed/3.5/html/deploy_models_using_distributed_inference_with_llm-d/tool-calling-through-llmd_distributed-inference
- NeMo Gym evaluation of this model, not used in the MVP: https://docs.nvidia.com/nemotron/nightly/nemotron/lightning35/evaluate.html

Pin the license of trimesh, manifold3d, SciPy, PrusaSlicer, and OctoPrint in the commit that installs them. PrusaSlicer and OctoPrint are AGPL; calling them as separate processes is the intended integration.

## 16. Technical limitations and future work

This plan produces a scaled synthetic residual limb and a constant-offset shell. Leave-one-out errors in OpenLimbTT already reach several millimetres when the full skin surface is known. A tape adds its own perimeter error, above 5% in Seminati et al. Local anatomy between the stations is copied from the template. The annotated reference station is not a palpated mid-patellar tendon until someone labels it that way, and even then it is an annotation on a statistical mean, not on a person.

The training population is 33 limbs, mostly male, and the authors call the model preliminary. Mode files, if they become templates, are samples of that same model. They are not a catalogue of clinical categories such as "short" in the Persson and Liedberg sense.

Future work, after a reliable tool loop exists:

- A skin-only PCA matrix, so a later version can fit mode scores instead of scaling sections, with the authors' anatomical-combination checks.
- Denser stations, still reported with tape uncertainty rather than hidden inside a smooth mesh.
- Transfemoral support only after a skin file and a brim strategy exist.
- Ankle-level support only after a dataset that actually contains those shapes.
- Rectification as an explicit, literature-cited operation with its own tool, never as a silent step inside shell generation.
- A scripted evaluation set of measurement utterances. NeMo Gym is optional there, and only if wrapping that set is cheaper than a plain scorer.

The fabrication report carries this limitation in one sentence: the limb is a synthetic OpenLimbTT template adjusted to the entered measurements, the socket is a demonstration shell, and the print is virtual.
