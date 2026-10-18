# Frontend API contract

This is the HTTP layer the web page (`agent/ui/web`) expects for the three-page flow in [README_LONG](README_LONG.md) §3 and §13: residual limb, then socket, then printer. **It is built** in `agent/web_api.py`. Start it with `uv run uvicorn agent.web_api:app --port 8001` (`FAKE_TOOLS=1` uses the fake printer), then run the page with `NEXT_PUBLIC_USE_MOCK=0` (the `api` and `web-real-api` entries in `.claude/launch.json`). Without it the page runs on mock data.

The server wraps the existing agent and adds no tool logic of its own.

- Keep one `Agent` (`agent/loop.py`) per browser session, identified by a session cookie. The same agent serves all three pages.
- The server owns the measurement document, the current limb and socket revisions, and the print phase ([README_LONG](README_LONG.md) §13).
- JSON bodies reuse the existing envelopes: `ToolResult.to_dict()` (`common/result.py`), `Pause`, and the `on_event` payloads. The page's TypeScript copies are in `agent/ui/web/lib/types.ts`. Keep the two in sync.
- The browser sends ids, never filesystem paths. The server resolves ids to files.

The default base URL is `http://localhost:8001/api`. Override it with `NEXT_PUBLIC_API_BASE`.

CORS: the page runs on another port and sends `credentials: "include"`. Every response, and the `OPTIONS` preflight, needs four headers:
- `Access-Control-Allow-Origin` set to the page's exact origin (not `*`)
- `Access-Control-Allow-Credentials: true`
- `Access-Control-Allow-Headers: Content-Type`
- `Access-Control-Allow-Methods: GET, POST, OPTIONS`

Set the session cookie with `SameSite=Lax`. Different localhost ports count as the same site.

**Client check:** `httpApi` was exercised against a throwaway stub server that followed this contract. Session loading, STL fetch, an SSE chat turn whose event was split across two network writes, cookie forwarding and the measurements POST all worked. To run the page against your server, start the `web-real-api` entry in `.claude/launch.json`, or run `NEXT_PUBLIC_USE_MOCK=0 npm run dev -- --port 3001` with the API on 8001.

## Session state, on every page load

`GET /api/session` returns a `SessionSnapshot` (`lib/api.ts`):

```json
{
  "measurements": { "length_mm": null, "proximal_circumference_mm": null, "distal_circumference_mm": null,
                    "mid_circumference_mm": null, "ap_depth_mm": null, "ml_width_mm": null,
                    "distal_shape": "template", "side": "template" },
  "limb": { "revision_id": "r0", "parent_revision_id": null, "stl_url": "http://localhost:8001/api/files/r0/residual_limb.stl" },
  "socket": null,
  "socket_confirmed": false,
  "job": null,
  "started": false,
  "pending": null
}
```

The page loads its state from this response and keeps no copy of its own, so a reload resumes where the server is. `limb` is `r0`, the standardized shape, before any edit. `pending` is a question or confirmation the person has not answered yet.

## Agent turns (server-sent events), on every page

- `POST /api/chat` with `{ "text": "..." }`
- `POST /api/answer` with `{ "answer": "..." }`, which calls `Agent.answer_question`
- `POST /api/confirm` with `{ "approved": true }`, which calls `Agent.resolve_confirmation`

Each responds with `text/event-stream`. Each event is one `data:` line holding JSON:

```
data: {"type":"tool_call","name":"prepare_print","args":{"profile_id":"draft_028"}}

data: {"type":"tool_result","name":"prepare_print","result":{"status":"success","data":{...},"message":"...","error":null,"retryable":false}}

data: {"type":"pause","pause":{"kind":"confirmation","text":"Print ...","details":{"action":"start_print","subject":"job_3fa9c1"}}}
```

- `tool_call` and `tool_result` events come from `on_event`.
- Every turn ends with exactly one `pause`. Its `kind` is `answer`, `question`, `confirmation` or `stopped`.
- A `question` pause may carry `details.options`: a list of short choices from `ask_user`, which the page shows as buttons under the question. Clicking one sends its text via `/api/answer`; typing a free-form answer stays possible. Agent and question text is Markdown and the page renders it as such.
- A turn may also contain a `{"type": "navigate", "stage": "socket"}` event, emitted when the agent calls `move_to_stage`. The server performs the stage change first (going to `socket` builds the socket from the current limb if there is none; going to `printer` confirms the socket if it passed its checks), so the page should refresh `GET /api/session` and then route: `limb` → `/`, `socket` → `/socket`, `printer` → `/printer`.
- Printing is stage-gated per session: until the socket has been confirmed, the agent's `prepare_print`, `slice` and `start_print` calls (and a `start_print` confirmation request) are refused with a fatal `stage_gate` tool result, whichever page the user asks from.
- The agent is synchronous. Run it in a worker thread and drain a queue into the SSE response.
- If `/api/chat` arrives while a question or confirmation is pending, return 409, because `Agent.send` raises in that case.

The page reacts to some successful tool results. Pass their data through unchanged:

| Tool result | Required `data` fields | Effect on the page |
|---|---|---|
| `customize_residual_limb` | `revision_id`, `parent_revision_id`, `stl_url`, and `measurements` with the changed fields | The limb viewer reloads and the profile shows the new values |
| `modify_socket`, `fit_socket_to_limb`, `engrave_label` | `socket_id`, `stl_url`, `validation` | The socket viewer reloads; the socket shows as not validated |
| `prepare_print` / `slice` | `job_id`, `profile_id`, `estimated_seconds`, `filament_m` | Fills the print actions |
| `start_print` | `job_id`, `verified: true` | Starts the print panel |

## Page 1: residual limb

| Method and path | Body / returns |
|---|---|
| `POST /api/measurements` | Body: `Measurements` (`lib/types.ts`), with all required and optional fields. Runs `validate_measurements` and then the customize step. Returns `{ revision: LimbRevision }`. A rejection uses the `ToolResult` envelope with HTTP 422. The page no longer calls it: the profile is read-only and values change through the agent. |
| `POST /api/limb/confirm` | Body: `{ "revision_id": "r1" }`. Builds the demonstration socket for that revision. Returns `{ socket: SocketRevision, validation: SocketValidation }`. |

`SocketValidation` is the return dict of `validate_socket` (`tools/cad/validate_socket.py`), unchanged.

## Page 2: socket

| Method and path | Body / returns |
|---|---|
| `POST /api/socket/confirm` | Body: `{ "socket_id": "socket_r1" }`. Accepts the socket and moves the phase to the printer. Returns `{}`. |

## Page 3: printer

These endpoints are polled about every 2 seconds while the page is open, including when the chat is idle.

| Method and path | Returns | Backed by |
|---|---|---|
| `GET /api/printer` | `ToolResult` with `PrinterStatus` data. Used for readiness. | `get_printer_status` |
| `GET /api/print/snapshot` | `PrintSnapshot`, or `null` before a verified start | The server-side poll in [README_LONG](README_LONG.md) §12 "Print monitoring" |
| `GET /api/print/layers` | `PrintLayers`: each layer's `z` and outer-wall paths, or `null` without the job's G-code (fake printer) | `tools/printer/gcode_layers.py` |
| `GET /api/report` | The fabrication report JSON, including the last observed step | The audit log |

`PrintSnapshot` (`lib/types.ts`) holds:
- one `step`: Starting, Printing, Pausing, Paused, Error, Link lost, Cancelled or Finished, chosen by the rules in [README_LONG](README_LONG.md) §12;
- `completion`, exactly as OctoPrint returned it ([README_LONG](README_LONG.md) marks its scale as unresolved);
- `filepos`, `print_time_s` and `print_time_left_s` (`null` when OctoPrint omits it);
- `file`, `filament_mm` and `port`;
- `temperatures`, when present;
- `layer`, `layer_count` and `layer_z`: the layer containing `filepos` in the job's own G-code, or `null` (fake printer, or OctoPrint printing another file);
- `observed_at` and `stale`.

When a poll fails, return the last good snapshot with `step: "Link lost"` and `stale: true`. Never estimate a new percentage.

These endpoints read only. They never call `start_print`, never change the job ledger, and use only the agent's read-scoped OctoPrint key.

## File serving

`GET /api/files/{id}/{role}.stl` serves the STL for `role`, which is `residual_limb` or `socket_shell`. The `stl_url` fields above should point here.

## How the server fills the gaps listed earlier

1. **CAD tools.** `tools/cad/tools.py` registers the CAD library as agent tools (`create_part`, `inspect_part`, `validate_measurements`, `customize_residual_limb`, `fit_socket_to_limb`, `modify_socket`, `check_fit`, `validate_part`, `engrave_label`, `make_preview_print`, plus the adapter, pylon and foot tools). A scaled preview (`preview-N`) of the confirmed socket may be printed; its confirmation text starts with "PREVIEW at N%, NOT TO SIZE". Each returns the `ToolResult` envelope.
2. **Limb measurements.** `GET /api/session` returns length, P and D filled with the standard limb's values and the optional fields empty. `POST /api/measurements` sends only the values that differ from those defaults to `validate_measurements`, then `customize_residual_limb`. `ap_depth_mm` / `ml_width_mm` map to the tools' `ap_mm` / `ml_mm`; `side: "template"` means no side.
3. **STL files.** `GET /api/files/{id}/{role}.stl` writes `view.stl` from the revision's STEP on first request, in the design orientation. (The print STL, `part.stl`, is turned opening-up and is not served.)
4. **Socket validation on the page.** A socket made by `modify_socket` or `fit_socket_to_limb` comes back with `data.validation` set to "not validated" (no categories). `validate_part` results carry the full `validate_socket` report in `data.validation`. `POST /api/socket/confirm` returns 409 unless the current socket passed.
5. **Slice confirmation.** Still only `start_print` is confirmable; "Approve slice" stays disabled.
6. **Print snapshot.** Read from OctoPrint's job, printer and connection endpoints on each poll, with the step rules of [README_LONG](README_LONG.md) §12. A failed read returns the last snapshot as `Link lost`, `stale: true`.
7. **Page changes the model should know.** The form, Confirm limb and Confirm socket add a short `[workbench page]` note to the agent's conversation, so a later chat request builds on them.
