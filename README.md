# CAD-to-Print Agent: Design Outline

**Reference dataset:** [OpenLimbTT](https://github.com/abel-research/OpenLimbTT)

## 1. Problem & Target User

**User:** Healthcare workers or prosthetics engineers who need to build and design prosthetics but can't use CAD software.

**Problem:** Designing a very specific prosthetic part currently needs someone who knows CAD, slicing and printer operation. That's slow, and staff become the bottleneck.

**Our solution:** A single small model, using real tools, that turns a plain-language request into a measured, checked part and sends it to a 3D printer. It asks when information is missing, recovers from errors, and never prints without a person's confirmation.

## 2. Key Concepts

**Tool:** A function the model can ask to call. It has three parts:

- **Name**, e.g. `make_bracket`
- **Description** the model reads to decide when to use it, and when not to
- **Argument schema** with names, types, units and allowed ranges, e.g. `width_mm: number, 10–200`

The model never runs code itself. It outputs a request ("call `make_bracket` with `width_mm=60`"), our agent loop runs the real function, and the result goes back to the model.

**MCP (Model Context Protocol):** We run two MCP servers, CAD and 3DPrinter, each with its own set of tools.

**Agent loop:** The program that repeats these steps: send the conversation and tool list to the model → run whatever tool it asks for → return the result → repeat, until the model gives a final answer or asks the user something.

## 3. Model & Serving

- **Model:** NVIDIA Nemotron 3.5 Lightning, 30B total parameters, 3B active per token (mixture-of-experts). This is our only generative model, so we stay under the 33B cap.
- **Serving:** Red Hat vLLM with tool calling enabled, on an NVIDIA Brev GPU instance (80 GB card for BF16 weights, or a quantized version). **[TBD: confirm the GPU type]**
- **Why these choices (for judges):**
  - Only 3B parameters are active per token, so responses are fast enough for a multi-step tool loop.
  - vLLM turns the model's output into clean, structured tool calls.
  - Everything runs on our own instance, so no data goes to an outside API.
- **Bounties targeted:** Best Use of Nemotron Lightning, Best Use of Red Hat vLLM. Optional: NeMo Gym.

## 4. Architecture

```
User
  |
  v
Chat UI / CAD Task Description
  |
  v
Python Agent Loop <------> Nemotron Lightning via vLLM
  |
  +------ CAD MCP Server
  |          |
  |          +-- Import existing CAD / mesh
  |          +-- Generate orthosis shell
  |          +-- Modify geometry
  |          +-- Add parametric features
  |          +-- Validate geometry
  |          +-- Compare revisions
  |          +-- Export STEP / STL / 3MF
  |                     |
  |                     v
  |              CAD Kernel / Mesh Engine
  |              FreeCAD or CadQuery
  |              OpenCascade / Trimesh
  |
  +------ Manufacturing MCP Server
             |
             +-- Check printability
             +-- Slice validated model
             +-- Get virtual printer status
             +-- Start after confirmation
             +-- Monitor job progress
                        |
                        v
                 Slicer / Virtual Printer
```

**[TBD: draw a cleaner version for the README]**

## 5. Tool Result Format (same for every tool)

Every tool returns exactly one of these:

- **success:** the result data (`part_id`, dimensions, file path, status…)
- **fixable:** the arguments were wrong. Includes the reason and what's valid, e.g. "hole_d_mm 40 exceeds face width 30". The model should correct the arguments and retry.
- **fatal:** retrying won't help, e.g. printer offline or slicer crash. The model should fall back and tell the user.

Every result also includes a short human-readable message.

## 6. Tool Inventory

### CAD MCP Server

| Tool | Arguments (units, range) | Purpose |
|---|---|---|
| `import_part` | `file_path`, `format`, `units` | Import a user's own STEP, STL, or supported CAD/mesh file and assign a `part_id`. |
| `inspect_part` | `part_id` | Return units, bounding box, body count, mesh status, and available feature information. |
| `generate_orthosis_shell` | `scan_id`, `orthosis_type`, `approved_design_id`, `output_format` | Generate a preliminary wrist-hand orthosis or AFO shell from approved inputs. |
| `modify_geometry` | `part_id`, `operation`, `target_feature_id`, operation-specific parameters | Translate, rotate, offset, or otherwise modify a supported geometric feature. |
| `add_parametric_feature` | `part_id`, `feature_type`, `reference_id`, `dimensions` | Add a hole, slot, rib, boss, fillet, or chamfer to a valid reference. |
| `combine_cad_models` | `part_ids`, `operation`, `output_part_id` | Perform a supported union, subtraction, or intersection. |
| `create_from_reference_geometry` | `reference_part_id`, `reference_feature_id`, `creation_type`, `parameters` | Create an offset surface, extrusion, profile, or enclosure using existing geometry. |
| `validate_geometry` | `part_id`, `checks`, optional `thresholds` | Check watertightness, self-intersections, disconnected bodies, dimensions, and configured minimum wall thickness. |

**[TBD: exact ranges for every argument]**

### Printer MCP Server

| Tool | Arguments | Purpose |
|---|---|---|
| `slice` | `part_id`, `material_profile_id`, `quality_profile_id`, `printer_profile_id` | Convert a printable model to G-code using a supported slicer. Refuses unless required validation passes. |
| `get_printer_status` | None | Return virtual printer connectivity, state, temperatures, and active job. |
| `start_print` | `job_id`, `confirmation_id` | Start a virtual print only after explicit human confirmation. |
| `get_job_progress` | `job_id` | Return progress and estimated remaining time when available. |
| `cancel_print` | `job_id`, `confirmation_id` where required | Request cancellation and verify the resulting state. |

### Built-in

| Tool | Purpose |
|---|---|
| `ask_user` | Request missing dimensions, units, approved design references, or other required information. |
| `request_confirmation` | Obtain human approval before slicing or starting a print, as configured by policy. |

**Tool description rule:** Every tool description must state when to use it and when to choose a different tool. For example, use `modify_geometry` to adjust an existing part; use `generate_afo_shell` to create a new preliminary AFO shell from approved inputs.

**Argument schemas:** Define operation-specific parameters, explicit units, enumerated values, and realistic limits. Do not use a generic `changes` object with arbitrary, undocumented fields for core CAD operations.

## 7. State

The CAD server stores each imported or generated part under a `part_id`. Each accepted edit creates a new revision so the original design remains recoverable.

A model record should include:

- `part_id` and revision ID
- Source file and format
- Unit system
- Parent revision, if applicable
- Geometry operation history
- Validation results
- Exported file references

The manufacturing server stores sliced jobs under a `job_id` and tracks the virtual printer's current state.

**Storage plan:** Use local disk for CAD files and a lightweight SQLite database or structured JSON records for metadata. Keep the initial implementation simple and reproducible. **[TBD: in memory, or saved to disk?]**

## 8. Safety Rules (enforced in tool code, not just the prompt)

Safety and geometry constraints must be enforced in tool code, not only in the model prompt.

- Every geometric argument is validated before an operation runs.
- Imports preserve the original file and do not silently change units or scale.
- Geometry changes are applied to a new revision, not destructively to the only copy.
- Clinical boundaries and patient-specific design parameters must come from approved inputs.
- A geometrically valid model is not automatically clinically appropriate or structurally safe.
- `slice` refuses a model when required geometry or printability checks fail.
- `start_print` requires explicit human confirmation.
- The agent never reports that a physical part is clinically approved just because a CAD check passes.
- The agent never claims that a job is printed or complete when only a command was accepted.
- Ambiguous tool outcomes trigger independent state checks rather than blind retries.

## 9. Failures & Fallbacks

| Failure | Trigger | Expected agent behavior |
|---|---|---|
| Invalid argument | A dimension is out of range | Read the fixable error, correct the arguments, and retry within a bounded limit. |
| Missing input | User asks for an orthosis without an approved scan or design reference | Call `ask_user`; do not invent patient geometry. |
| Unsupported file | Import parser rejects a file | Explain the supported formats and request a compatible export. |
| Incorrect units | File units are absent or ambiguous | Ask the user to confirm units; do not silently scale. |
| Invalid geometry | Boolean operation produces invalid geometry | Preserve the previous revision and attempt a supported alternative only when appropriate. |
| Feature out of bounds | A slot crosses the approved region | Reject the change and explain the conflicting constraint. |
| Validation failure | Wall thickness or mesh checks fail | Report the failed checks; revise only within approved parameters. |
| Printability failure | Part exceeds build volume | Explain the constraint and ask before reorientation or any scale change that alters dimensions. |
| CAD operation fails repeatedly | Geometry engine returns persistent errors | Stop retrying, preserve the original, and return diagnostics. |
| Slicer fails | Invalid mesh or slicer error | Preserve the CAD export and report the failure. |
| Virtual printer disconnects | Injected connection failure | Query state, avoid duplicate starts, and report whether status can be verified. |

## 10. Open Data & Evaluation

**Evaluation dataset:** Create 30–50 natural-language CAD requests with expected tool paths, arguments, geometry constraints, and expected behavior when information is missing.

Include a mixture of:

- General CAD operations such as holes, slots, offsets, and enclosures
- Imported-part modification requests
- Orthosis-related requests based on synthetic or appropriately licensed sample geometry
- Ambiguous requests that should trigger clarification
- Invalid dimensions and out-of-bounds features
- Geometry-validation failures
- Manufacturing and export failures

Do not include identifiable patient scans or medical records. Use synthetic geometry or appropriately licensed public assets and document their provenance.

**Metrics:**

- Correct tool selected
- Valid arguments on the first attempt
- Task completion rate
- Geometry validation pass rate
- Dimensional accuracy against the expected result
- Successful recovery from injected failures
- Rate of unauthorized or invalid operations
- Average tool-call latency and end-to-end completion time
- Human clarification rate

**Baselines:** Compare the agent with a simpler tool-calling baseline without structured error recovery, and include deterministic tests for operations that do not require a model.

Define the denominators and run repeatable tests. A system that refuses every request should not score well simply because it avoids errors.

**Open-data requirement:** Use public, appropriately licensed assets or synthetic models, and cite each dataset or asset source in the repository. Verify the hackathon's exact open-data requirements before submission.

## 11. Demo Scenarios (3–5 Minutes)

**Scenario 1: Import and modify an existing orthosis**
> "Import this wrist orthosis STL, add ventilation slots to the approved region, validate the geometry, and export the result."

Show the import, tool selection, actual CAD operation, validation results, and exported revision.

**Scenario 2: Correct a geometry failure**
> "Add slots to this model."

Inject a request that exceeds the available region. Show the CAD tool returning a structured fixable error, the model correcting its arguments or asking the user a question, and the validator checking the revised geometry.

**Scenario 3: Missing clinical design input**
> "Create an AFO for this patient."

The agent should ask for the approved scan, trimline, and design specification rather than inventing anatomical geometry or clinical settings.

**Scenario 4: Revision comparison**
> "Make the ventilation slots wider, but do not change the support boundary."

Show a new model revision, a comparison against the baseline, and validation of the affected geometry.

**Scenario 5: Manufacturing preparation**
> "Check whether this part fits the selected printer and export it for slicing."

Show printability checks, a successful export, and the confirmation gate before any virtual print begins.

**Video order:** Team introduction → problem and target user → live CAD tool-calling demo → architecture and NVIDIA/Red Hat integration → measured results and impact.

## 12. Team Split

- **Team member 1:** Nemotron serving through vLLM on Brev, Python agent loop, and MCP orchestration.
- **Team member 2:** CAD MCP server, import workflow, geometry operations, revision management, and deterministic validation.
- **Team member 3:** Manufacturing MCP server, slicer and virtual printer integration, fault injection, evaluation dataset, README, and demo video.

Adjust responsibilities based on each person's experience. Prioritize an end-to-end working workflow over independent components that do not integrate.

## 13. Timeline (Saturday–Sunday)

| Target | Milestone |
|---|---|
| Saturday, ~2 PM | Nemotron tool calling verified; CAD engine and virtual printer start successfully. |
| Saturday, ~7 PM | Import a user part, inspect geometry, perform at least two CAD operations, and validate the result. |
| Saturday, ~11 PM | Specialized orthosis workflow, export, and manufacturing confirmation gate integrated. |
| Sunday, ~3 AM | Evaluation dataset and fault-injection tests run; metrics recorded. |
| Sunday, 7–10 AM | README, architecture diagram, reproducible demo, and video completed. |
| Sunday, ~11 AM | Submission finalized. |

**Cut first if behind:** Additional orthosis types, advanced assembly operations, sophisticated visualization, and the optional NeMo Gym bounty.

**Do not cut:** Part import, actual CAD modification, geometry validation, structured tool errors, or the working Nemotron tool-calling loop.