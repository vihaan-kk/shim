# CAD-to-Print Agent

A small language model that turns a plain-language request into a measured, checked demonstration prosthetic socket and a confirmed virtual 3D print.

The model does not run geometry or printer code itself. It chooses a tool, our Python agent runs that tool, and the result goes back to the model. The agent asks when information is missing, recovers from structured errors, and never starts a print without a person's confirmation.

**Status:** design outline. This repository does not yet contain the agent, geometry tools, or printer integration.

**Dataset:** [OpenLimbTT](https://github.com/abel-research/OpenLimbTT), synthetic transtibial residual-limb surfaces.

## Contents

1. [Scope](#1-scope)
2. [Problem and user](#2-problem-and-user)
3. [Demo workflow](#3-demo-workflow)
4. [How tool calling works](#4-how-tool-calling-works)
5. [Model and serving](#5-model-and-serving)
6. [Architecture](#6-architecture)
7. [Dataset and units](#7-dataset-and-units)
8. [Geometry approach](#8-geometry-approach)
9. [Tools](#9-tools)
10. [State, phases, and confirmations](#10-state-phases-and-confirmations)
11. [Safety](#11-safety)
12. [Failures and recovery](#12-failures-and-recovery)
13. [Demo script](#13-demo-script)
14. [Evaluation](#14-evaluation)
15. [Team and timeline](#15-team-and-timeline)
16. [References](#16-references)

## 1. Scope

This hackathon prototype builds **non-wearable demonstration socket shells** from synthetic residual-limb meshes.

A passing geometry check means the mesh is closed, within the configured wall and printer limits, and ready to slice. It does not establish clinical fit, comfort, load-bearing strength, or patient safety. The agent must not describe a result as clinically approved.

In scope:

- Load a synthetic OpenLimbTT skin STL.
- Measure the mesh and generate a constant-offset demonstration shell.
- Edit the rim, validate the solid, and slice it.
- Start a virtual print only after a person confirms, then recover if the connection drops.
- Write an auditable fabrication report.

Out of scope for this prototype:

- Wrist-hand orthoses, ankle-foot orthoses, and other device types.
- Clinical rectification, pressure-relief maps, and patient-specific trimlines.
- Identifiable patient scans or medical records.
- Wearable sockets and physical-printer operation.
- Claims that a geometric check approves a device for use on a person.

## 2. Problem and user

**User:** a prosthetics engineer, technician, or researcher who needs a demonstration socket prepared and printed, and who should not have to drive CAD, a slicer, and printer software by hand.

**Problem:** producing even a demonstration shell currently means importing a scan, shaping a wall, checking the mesh, slicing, and operating the printer. Each step uses a different program. The person who knows those programs becomes the bottleneck.

**What this agent does:** one conversation coordinates those programs. The person states the scale, the wall, and the print goal. The agent calls tools for measurement, shell generation, validation, slicing, and the virtual printer. It stops and asks when units, scale, or approval are missing.

## 3. Demo workflow

Each stage has a tool, a result, and a condition that must be true before the next stage starts.

| Stage | What happens | Tool | Move on when |
|---|---|---|---|
| 1. Load | Store the STL unchanged and record its hash and bounding box. | `load_scan` | A `scan_id` exists and units are confirmed. |
| 2. Inspect | Report the open skin surface and cross-section perimeters. | `inspect_mesh`, `measure_cross_sections` | The mesh is one skin surface, not a skin-plus-bone mesh. |
| 3. Generate | Scale explicitly, orient the long axis to printer +Z, and build a constant-offset shell. | `generate_demo_socket` | A new revision file exists. |
| 4. Edit | Smooth or flare the rim. Decorative patterns are optional. | `modify_rim_geometry` | The user asks to validate, or stops editing. |
| 5. Validate | Check the closed shell, wall thickness, build volume, and overhangs. | `validate_mesh` | Every required check passes and a certificate is stored. |
| 6. Repair | Retry only the repairs listed in [Safety](#11-safety). | same geometry tools | A later certificate passes, or the agent stops and reports the measurements. |
| 7. Slice | Slice only a certified revision after the user approves. | `slice_model` | G-code exists and time and filament were parsed. |
| 8. Authorize | Read the virtual printer and ask for a separate print approval. | `check_printer_readiness`, `request_confirmation` | The printer is ready and the confirmation matches this job. |
| 9. Print | Upload, start, then read the job state back. | `start_print` | `GET /api/job` reports `Printing`. |
| 10. Recover | If the link drops, read state again and try a safe pause. | `reconcile_printer_state`, `request_safe_pause` | The report says what was verified and what was not. |
| 11. Report | Write the audit trail: dataset, scale, revisions, checks, profile, and printer observations. | agent, from the log | The report is saved with the job. |

An open boundary on the **scan** is expected. The **socket mesh** that goes to the slicer must be a closed solid. The cavity is inside that solid; the triangle mesh itself is watertight.

## 4. How tool calling works

**Tool.** A function the model may request. It has a name, a description that says when to use it and when to choose a different tool, and an argument schema with types, units, and ranges.

**Agent loop.** Send the conversation and the current tool list to the model. Run the requested function. Return the result. Repeat until the model answers the user or asks a question.

The model never receives the OctoPrint API key, a free filesystem path, or a raw G-code channel. Tools accept ids, and the server resolves them.

**Result envelope.** Every tool returns one of three statuses, plus a short human-readable message:

| Status | Meaning | What the model should do |
|---|---|---|
| `success` | The call ran. A validation that fails is still `success` if `data.passed` is false. | Read the data and choose the next legal step. |
| `fixable` | The arguments or the mesh can be corrected inside a known range. | Correct the arguments and retry, at most twice. |
| `fatal` | Retrying the same call will not help. | Stop that path, keep the last good revision, and tell the user. |

```json
{
  "status": "success",
  "message": "Skin mesh loaded. Units confirmed as tibia-length fractions.",
  "data": {},
  "error": null
}
```

A `fixable` error includes `error.code`, `error.reason`, and `error.valid` so the model can see the legal range.

**Two tool groups.** Geometry tools and manufacturing tools live in one Python process for the hackathon. They can be exposed later as two MCP servers. vLLM consumes OpenAI-style tool calls, so the first milestone is a working tool loop, not a second transport.

## 5. Model and serving

| Item | Choice |
|---|---|
| Model | NVIDIA Nemotron 3.5 Lightning, 30B total parameters, 3B active per token. This is the only generative model, under the 33B cap. |
| Checkpoint | `NVIDIA-Nemotron-3.5-Lightning-30B-A3B`, BF16 on an 80 GB-class GPU, or NVFP4 on a smaller supported GPU. |
| Serving | Red Hat vLLM on an NVIDIA Brev instance, tool calling enabled. |
| Bounties | Best Use of Nemotron Lightning, Best Use of Red Hat vLLM. NeMo Gym is optional and is the first bounty to drop. |

Published vLLM flags for this model:

- `--enable-auto-tool-choice`
- `--tool-call-parser qwen3_coder`
- `--reasoning-parser nemotron_v3`

When reasoning and tool calls are both enabled, send `chat_template_kwargs.force_nonempty_content: true`. Without it, the server can return an empty message body beside the tool call.

**Still to confirm on the instance:** the GPU from `nvidia-smi`, whether the Red Hat vLLM build accepts these parsers, and whether the weekend image is BF16 or NVFP4.

Why this model: only 3B parameters are active per token, so a multi-step tool loop stays responsive. vLLM turns the output into structured tool calls. The instance is ours, so scan files are not sent to an outside model API.

## 6. Architecture

```text
User
  |
  v
Chat, 3D view, phase list, confirmation buttons
  |
  v
Python agent
  phase gate, argument checks, confirmation store, audit log
  |
  +---- Nemotron 3.5 Lightning through vLLM
  |
  +---- Geometry tools
  |       load, measure, shell, rim, export, validate
  |       trimesh + manifold3d
  |       files in ./data/parts/<part_id>/<revision>/
  |
  +---- Manufacturing tools
          slice, printer status, gated start, recovery
          PrusaSlicer CLI
          OctoPrint REST, Virtual Printer only
          SQLite for revisions, jobs, confirmations, audit
```

The browser is a thin page: transcript, current phase, validation cards, and a model viewer for the exported STL. A full CAD viewport is a stretch goal.

## 7. Dataset and units

OpenLimbTT is a statistical shape model of transtibial residual limbs, built so researchers can share synthetic anatomy without publishing identifiable scans. Version `2025-07` is trained on 33 limbs. The authors describe it as a preliminary model with limited statistical generality. Mode 1 is mainly amputation height (about 52% of variance). Mode 2 is slender versus bulbous soft tissue (about 17%).

Use a **skin** file for the shell. `Mean-Limb` also contains bones and is the wrong input for an offset wall.

| File | Use |
|---|---|
| `version-2025-07/Mean-Skin.stl` | Default demo scan. |
| `Mode1-*-Mode2-*.stl` | Optional shape variants after the mean skin path works. |
| `Mean-Limb.stl`, `*-Bones-*` | Do not offset these into a socket. |

**Coordinates.** Training meshes follow the International Society of Biomechanics convention used in the paper: the xz plane is transverse, yz is coronal, and xy is sagittal, so Y is the longitudinal axis of that convention. Left limbs were mirrored, and the tibia centroid was moved to the origin. The loader still measures the bounding box and checks which axis is longest before rotating the mesh to printer +Z.

**Scale.** Training shapes are normalized by intact tibia length, because residual length is not a consistent fraction of the intact limb. The generation notes give a training range of about 313–466 mm and suggest 378.52 mm as an average intact tibia length. STL files do not store units. `Mean-Limb.stl` and `Mean-Limb-Full-Size.stl` have the same byte size, so a filename is not proof of millimetres.

`load_scan` stores the file unchanged. Generation is refused until units are confirmed. A half-scale demo stores both numbers: `scale_factor` 0.5 and `target_tibia_length_mm` 378.52. If the longest side is under 5 and the caller claims millimetres, the tool returns `ambiguous_units` and the agent asks the user.

**License.** The GitHub model is CC BY-SA 4.0. Derived meshes we redistribute stay under that license. Cite the paper in the repo and in the fabrication report. Raw MRI and CT are not in the dataset and are not used.

The checked-in STLs are the demo corpus. The published generation script depends on local paths and ampscan, and it is not a drop-in tool for this prototype.

## 8. Geometry approach

The shell is a geometric demonstration:

1. Copy the skin mesh.
2. Apply the explicit scale.
3. Rotate the measured long axis to printer +Z.
4. Cut a proximal opening at `trim_fraction` of the length.
5. Offset a constant wall with manifold3d.
6. Export a closed STL.

This is not a clinical socket design. There is no rectification, no landmark-based relief, and no patient trimline.

| Library | Role |
|---|---|
| [trimesh](https://trimsh.org/) | Load, bounds, cross-sections, normals, export, sampled wall thickness. |
| [manifold3d](https://github.com/elalish/manifold) | Constant offset and mesh booleans. |
| [PrusaSlicer](https://github.com/prusa3d/PrusaSlicer) CLI | G-code, estimated time, and filament, via `--export-gcode`. |
| [OctoPrint](https://docs.octoprint.org/en/main/api/) | Virtual printer state, upload, and job control. |

[uFit Blender](https://github.com/ortigital/ufit-blender) already has a transtibial workflow: import, measure, thickness, trim, flare, and STL export. Those steps are interactive Blender operators under GPL-3.0, not functions our agent can call with a thickness argument. We copy the order of operations and implement them with trimesh and manifold3d. Blender in background mode is the fallback if a constant offset of `Mean-Skin.stl` fails. FreeCAD and CadQuery stay out of this prototype because the input is an open triangle surface, not a STEP feature tree.

Ship two slicer profiles as INI files: `draft_028` and `demo_020`. PrusaSlicer does not provide a profile-list API.

## 9. Tools

Argument names carry units. Unknown fields are rejected. Ranges below are enforced in tool code before any mesh or network call.

Descriptions must tell the model when **not** to use a tool. Use `modify_rim_geometry` to change an existing shell. Use `generate_demo_socket` to create a new shell from a scan. Use `ask_user` when units, scale, or a skin file are missing. Do not invent a limb.

### Geometry

| Tool | Required arguments | Purpose |
|---|---|---|
| `load_scan` | `source` (`upload` or `catalog`), `units` (`mm`, `tibia_lengths`, or `unspecified`), plus `upload_token` or `catalog_id` | Store the STL, hash it, and report bounds. `unspecified` blocks generation. |
| `inspect_mesh` | `object_id`, `object_kind` (`scan` or `part`) | Extents, watertight flag, boundary length, and `open_surface`, `closed_shell`, or `multi_body`. |
| `measure_cross_sections` | `scan_id`, `axis`, `stations` (1–12 fractions from 0.05 to 0.95) | Perimeter and area at each station. Multiple loops are `fixable` by moving the station. |
| `generate_demo_socket` | `scan_id`, `wall_thickness_mm` (2.0–6.0), `trim_fraction` (0.55–0.90), and one scale field | New revision. `scale_factor` is 0.25–1.0. `target_tibia_length_mm` is 150–250 when the demo is half of the documented training range. Optional `preset_id`: `shell_3mm`, `shell_4mm`, `flared_rim`. |
| `modify_rim_geometry` | `part_id` | Optional `flare_mm` 0–8, `smooth_iterations` 0–25, `band_mm` 5–30. Writes a new revision. |
| `export_stl` | `part_id`, `revision_id` | Write the STL. Export does not mean the mesh passed validation. |
| `validate_mesh` | `part_id`, `revision_id`, `printer_profile_id` | Closed shell, winding, single component, minimum wall (default 2.0 mm), build volume, overhangs (default 55° from +Z). Optional thresholds override the defaults. Returns `certificate_id` only when all checks pass. |

`validate_mesh` includes wall, volume, and overhang checks so the weekend build has one certificate. Split helpers can be added later without changing the agent's first path.

`generate_demo_socket` refuses a combined skin-and-bone mesh and refuses unconfirmed units. A failed offset keeps the source scan.

### Manufacturing

| Tool | Required arguments | Purpose |
|---|---|---|
| `slice_model` | `part_id`, `revision_id`, `profile_id`, `confirmation_id`, `certificate_id` | Run PrusaSlicer. The confirmation must name this revision, and the certificate must be newer than the revision. Returns `job_id`, estimated seconds, and filament length and mass. |
| `get_printer_status` | none | `GET /api/connection`, `GET /api/printer`, and `GET /api/job`. |
| `check_printer_readiness` | none; optional `expected_port` default `VIRTUAL` | Ready only when OctoPrint is operational and not printing, paused, or in error, on the virtual port. |
| `start_print` | `job_id`, `confirmation_id`, `upload_id` | Upload is internal for the MVP. Select the file with `print: false`, post `start`, then read the job back. |
| `reconcile_printer_state` | none | Compare the command ledger with the live printer. Result is `verified`, `mismatch`, or `unknown`. |
| `request_safe_pause` | `job_id`, `reason` | Pause and verify if the printer is printing. If the link is down, record the intent and return `pause_not_delivered`. |

`slice_model` already returns time and filament. Separate estimate tools can read a finished `job_id` later.

### Built in to the loop

| Tool | Purpose |
|---|---|
| `ask_user` | Ask for a missing skin file, unit system, or scale. The model does not guess patient geometry. |
| `request_confirmation` | The UI creates a one-time `confirmation_id` for `slice` or `start_print`. The model cannot mint this id. Slice approval does not authorize a print. |

### Repairs the agent may attempt on its own

After a failed certificate, the agent may:

- raise wall thickness by at most 1.0 mm, staying inside 2.0–6.0 mm
- fill holes smaller than the configured edge length
- try four fixed rotations at the same scale if overhangs fail

Scale, trim height, a different scan, and pattern depth all require `ask_user`. After two unsuccessful repairs, the agent stops and reports the failing measurements.

### Stretch tools

Add these only after the twelve-tool path runs from upload through a report:

`apply_design_preset`, `add_decorative_pattern`, `compare_geometry`, `detect_mesh_defects` as its own tool, `list_print_profiles` as its own tool, `pause_print` as a user-facing tool separate from safe pause, `inspect_sensor_health`, `get_fault_history`, and MCP wrappers.

`add_decorative_pattern`, if built, is limited to a shallow exterior displacement (`depth_mm` 0.2–0.8 and under 25% of the wall) on the distal half. It does not cut holes through the wall.

## 10. State, phases, and confirmations

STL files live on disk. Metadata lives in SQLite. Each accepted edit creates a new revision. The source scan and earlier revisions stay recoverable.

A revision record stores:

- `part_id` and revision id
- parent revision
- source scan, file hash, and confirmed units
- scale factor and target tibia length
- operation history
- validation certificate, if one passed
- exported STL and G-code references

A job record stores the profile, G-code hash, confirmation ids, and the printer observations.

**Phases**

```text
empty → loaded → inspected → designed → validated
  → slice_approved → sliced → print_approved → printing
  → paused | completed | unknown
```

A failed validation returns the session to `designed`. A lost printer connection moves it to `unknown`. The tool list sent to the model is filtered by phase:

| Phase required | Tools that appear |
|---|---|
| `loaded` | `inspect_mesh`, `measure_cross_sections` |
| `inspected` | `generate_demo_socket` |
| `designed` | `modify_rim_geometry`, `validate_mesh`, `export_stl` |
| `validated` | `request_confirmation` for slicing, then `slice_model` |
| `sliced`, printer ready, unused print confirmation | `start_print` |
| `printing` or `unknown` | `reconcile_printer_state`, `request_safe_pause` |

`start_print` is omitted while the phase is `unknown`.

**Confirmations and the command ledger**

- A confirmation id is single-use and bound to one revision or one job.
- A new revision invalidates the previous certificate and any slice approval.
- The ledger records every `start` and `pause` by `job_id`.
- A second `start` is refused while the first is `sent`, `verified_printing`, or `unknown`.
- OctoPrint returns 204 with an empty body for an accepted job command, and 409 when the printer state does not allow it. The 204 is not proof that the job is printing. The tool always follows with `GET /api/job`.
- If that read fails, the stored state is `accepted_unverified` or `unknown`.

The OctoPrint API key used by the agent has `STATUS`, `FILES_UPLOAD`, `FILES_SELECT`, and `PRINT`. It does not have `CONTROL`, so the model cannot send arbitrary G-code, jog the head, or set temperatures.

## 11. Safety

These rules are enforced in tool code.

- Geometric arguments are checked before an operation runs.
- Imports keep the original file and do not silently change units or scale.
- Edits write a new revision.
- `slice_model` refuses a revision without a current certificate and a matching confirmation.
- `start_print` requires a separate confirmation, a ready virtual printer, and a ledger check.
- The demo instance is configured with the Virtual Printer only. A physical serial port fails the readiness check.
- The agent never reports a part printed or complete because a command was accepted.
- Ambiguous printer results trigger `reconcile_printer_state`. They do not trigger another `start`.
- Virtual Printer debug commands such as `!!DEBUG:action_disconnect` belong to the demo fault injector, on a separate key. They are not agent tools.
- Real printer firmware, including thermal limits and endstops, stays in the firmware. This software does not disable it. The virtual printer does not test those protections.
- Fabrication reports state that the object is a nonclinical demonstration model and that the checks are geometric and process checks only.

## 12. Failures and recovery

| Failure | What the tool returns | What the agent does |
|---|---|---|
| Dimension out of range | `fixable`, with the legal range | Correct the argument and retry, at most twice. |
| Missing skin file or scale | the loop asks through `ask_user` | Wait. Do not invent a limb or a scale. |
| Unsupported file | `fatal` for that import | Name the supported format, STL, and ask for another file. |
| Ambiguous units | `fixable` / `ambiguous_units` | Ask the user. Do not multiply by 378.52 until they answer. |
| Skin-plus-bone mesh | `fixable` / `combined_mesh` | Ask for `Mean-Skin.stl` or another skin-only file. |
| Offset or boolean fails | `fatal` for that generation | Keep the scan and the previous revision. Stop after two failures. |
| Wall or overhang check fails | `success` with `passed: false` | Apply one permitted repair, then validate again. |
| Part larger than the bed | failed build-volume check, or slicer `outside_volume` | Explain the limit. Ask before any scale change. |
| Slicer crash | `fatal` | Keep the STL and report the slicer output. |
| Printer already busy | HTTP 409 | Read the job state. Do not send `start` again. |
| Link drops after `start` | `unknown` | Reconcile, attempt `request_safe_pause`, and report whether the pause was verified. |

Three fault tests for the demo:

1. **Thin wall.** A shell under 2.0 mm fails validation. The agent raises thickness inside the 1.0 mm repair band and validates again. A request outside that band asks the user.
2. **Disconnect after start.** The injector sends `!!DEBUG:action_disconnect`. The agent reconciles to `unknown`, records an undelivered pause, and a second `start_print` is rejected from the ledger.
3. **Slice outside the volume.** A 40 mm bed profile makes `slice_model` return `outside_volume`. Nothing is uploaded, and `start_print` is not offered.

## 13. Demo script

Target length: 3–5 minutes. One path, plus the two faults that fit on camera.

1. Show `Mean-Skin.stl` and the measured bounding box, so the audience sees that the file is in tibia-length units.
2. “Generate a half-scale demonstration socket from this synthetic limb scan.” Show `0.5 × 378.52 mm`, the new revision, and the viewer.
3. “Make the rim smoother.” Show a new revision and the validation card.
4. Force one wall-thickness miss, then the in-band repair and a passing certificate.
5. Slice `draft_028`. Show an estimate under 90 minutes. If `demo_020` is also sliced, show both times and recommend the one that finishes inside the demonstration window.
6. Stop on the print confirmation button. After approval, start the virtual job and show progress from `GET /api/job`.
7. Inject the disconnect. Show `unknown`, the refused second start, and the fabrication report with the OpenLimbTT citation.

Video order: team introduction, the bottleneck, the live tool trace, the vLLM architecture, then the fault result and the report.

## 14. Evaluation

Build a small set of natural-language socket requests with expected tool order, arguments, and the expected question when information is missing. Ten scripted traces are enough for the hackathon if the live path already works. A set of 30–50 is a stretch goal.

Include:

- a complete half-scale shell request
- a missing unit or missing scale
- a skin-plus-bone file that must be refused
- a rim edit
- a validation failure and one legal repair
- an out-of-policy scale change that must ask the user
- a slicer or volume failure
- a printer disconnect after start

Do not include identifiable patient scans.

**Metrics**

- Correct tool selected
- Valid arguments on the first attempt
- Task completion
- Validation pass rate after permitted repairs
- Dimensional error against the expected scale and wall
- Recovery from the three injected faults
- Unauthorized or invalid operations
- Tool-call latency and end-to-end time
- How often the agent asks the user

Compare against a simpler tool-calling loop that has no structured `fixable` retry and no phase filter. Also keep deterministic tests for load, offset, validation, and the print ledger so those scores do not depend on the model. A system that refuses every request does not score well only because it avoids errors. Publish the denominator for each metric.

**Open data.** Pinned OpenLimbTT files, with the citation and CC BY-SA note in this repository. Confirm the hackathon's open-data wording before submission.

## 15. Team and timeline

| Person | Owns |
|---|---|
| 1 | Nemotron on vLLM, the agent loop, phase filter, confirmations, and the audit log. |
| 2 | Load, measure, shell generation, rim edit, revisions, and `validate_mesh`. |
| 3 | PrusaSlicer, OctoPrint Virtual Printer, fault injection, the report, and the demo recording. |

The geometry owner should know early whether manifold3d can offset `Mean-Skin.stl`. If it cannot, switch that one operation to Blender background mode and keep the same tool schema.

| When | Milestone |
|---|---|
| Saturday, ~2 PM | Nemotron tool calling works. A mesh loads. OctoPrint Virtual Printer responds. |
| Saturday, ~7 PM | Inspect the skin, generate one shell, edit the rim, and validate. |
| Saturday, ~11 PM | Export, slice, confirmation gate, and a verified virtual start. |
| Sunday, ~3 AM | The three fault tests have been run and the numbers written down. |
| Sunday, 7–10 AM | README, diagram, repeatable demo, and video. |
| Sunday, ~11 AM | Submission. |

**Do not cut:** STL import with an explicit unit check, a real shell operation, validation, structured tool errors, the Nemotron tool loop, or the confirmation gate before a virtual print.

**Cut first:** decorative patterns, revision color maps, extra OpenLimb modes, MCP transport, a second device type, Blender as the primary kernel, and NeMo Gym.

## 16. References

- Sunderland, F. E., Sobey, A. J., Bramley, J. L., Steer, J. W., Al-Dirini, R., Metcalf, C. D., Toderita, D., Bull, A., Ding, Z., Henson, D., Worsley, P. R., Dickinson, A. S., and the OpenLimb Group (2025). OpenLimbTT, a transtibial residual limb shape model for prosthetics simulation and design. *Data-Centric Engineering*, 6, e39. https://doi.org/10.1017/dce.2025.10019
- OpenLimbTT models and STL files, CC BY-SA 4.0: https://github.com/abel-research/OpenLimbTT
- Study dataset record, CC BY 4.0: https://doi.org/10.5258/SOTON/D2895
- Alignment toolbox used by the dataset authors: https://github.com/abel-research/ampscan
- uFit Blender, reviewed and not wrapped, GPL-3.0: https://github.com/ortigital/ufit-blender
- OctoPrint REST API: https://docs.octoprint.org/en/main/api/
- OctoPrint Virtual Printer: https://docs.octoprint.org/en/main/development/virtual_printer.html
- Nemotron 3.5 Lightning on vLLM: https://vllm.ai/blog/2026-08-10-nemotron-3-5-lightning-vllm

Pin the license of trimesh, manifold3d, and PrusaSlicer in the commit that vendors or installs them.
