# Frontend API contract

This is the HTTP layer the web page (`agent/ui/web`) expects for the three-page flow in README §3 and §13: residual limb, then socket, then printer. **It is proposed, not built.** Until it exists, the page runs on mock data (`NEXT_PUBLIC_USE_MOCK=1`, the default).

The server wraps the existing agent and adds no tool logic of its own.

- Keep one `Agent` (`agent/loop.py`) per browser session, identified by a session cookie. The same agent serves all three pages.
- The server owns the measurement document, the current limb and socket revisions, and the print phase (README §13).
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
- The agent is synchronous. Run it in a worker thread and drain a queue into the SSE response.
- If `/api/chat` arrives while a question or confirmation is pending, return 409, because `Agent.send` raises in that case.

The page reacts to some successful tool results. Pass their data through unchanged:

| Tool result | Required `data` fields | Effect on the page |
|---|---|---|
| `customize_residual_limb` | `revision_id`, `parent_revision_id`, `stl_url`, and `measurements` with the changed fields | The limb viewer reloads and the profile shows the new values |
| `modify_socket` | `socket_id`, `stl_url` | The socket viewer reloads |
| `prepare_print` / `slice` | `job_id`, `profile_id`, `estimated_seconds`, `filament_m` | Fills the print actions |
| `start_print` | `job_id`, `verified: true` | Starts the print panel |

## Page 1: residual limb

| Method and path | Body / returns |
|---|---|
| `POST /api/measurements` | Body: `Measurements` (`lib/types.ts`), with all required and optional fields. Runs `validate_measurements` and then the customize step. Returns `{ revision: LimbRevision }`. A rejection uses the `ToolResult` envelope with HTTP 422. |
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
| `GET /api/print/snapshot` | `PrintSnapshot`, or `null` before a verified start | The server-side poll in README §12 "Print monitoring" |
| `GET /api/report` | The fabrication report JSON, including the last observed step | The audit log |

`PrintSnapshot` (`lib/types.ts`) holds:
- one `step`: Starting, Printing, Pausing, Paused, Error, Link lost or Finished, chosen by the rules in README §12;
- `completion`, exactly as OctoPrint returned it (README marks its scale as unresolved);
- `filepos`, `print_time_s` and `print_time_left_s` (`null` when OctoPrint omits it);
- `file`, `filament_mm` and `port`;
- `temperatures`, when present;
- `observed_at` and `stale`.

When a poll fails, return the last good snapshot with `step: "Link lost"` and `stale: true`. Never estimate a new percentage.

These endpoints read only. They never call `start_print`, never change the job ledger, and use only the agent's read-scoped OctoPrint key.

## File serving

`GET /api/files/{id}/{role}.stl` serves the STL for `role`, which is `residual_limb` or `socket_shell`. The `stl_url` fields above should point here.

## Open dependencies (not frontend work)

1. **The CAD functions are not agent tools.** `tools/registry.py` imports `tools.cad.tools`, which does not exist. The functions in `tools/cad/*.py` return plain dicts, not `ToolResult`.
2. **Tool names differ.** The README uses `customize_residual_limb`, `validate_socket_geometry` and `slice_model`. The code has `modify_limb`, `validate_socket`, `prepare_print` and `slice`. The mock uses the README names for limb edits and `modify_socket` for socket edits.
3. **No STL for limb edits.** `modify_limb` writes `.step` and `.json` but no `.stl`, and the viewer needs an STL for each revision.
4. **No slice confirmation.** README §13 wants slice and print confirmations as separate controls, but `agent/builtins.py` has only `CONFIRMABLE_ACTIONS = ["start_print"]`. "Approve slice" is shown disabled with a tooltip.
5. **The snapshot needs more data than `get_printer_status` returns.** `get_printer_status` returns no `printTime`, temperatures or file name. The README §12 server poll has to collect those fields itself.
6. **The workspace layout is not agreed.** The printer tools read `workspace/revisions/<id>/part.stl` plus a `validated` marker. The CAD tools write to whatever `output_dir` they are given.
