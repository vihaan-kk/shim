# Shim web workbench

The landing page (`/`) introduces the tool-calling agent and links to the three-stage frontend from [README_LONG](../../../docs/README_LONG.md) §3 and §13:
- **Residual limb** (`/limb`): the 3D limb, the measurement profile, the agent chat, and Confirm.
- **Socket** (`/socket`): the socket shell, its geometric checks, the agent chat, and Confirm.
- **Printer** (`/printer`): the job metadata, slice and print controls, the agent chat, and the report.

The same agent conversation carries across all three pages.

**Status:** scaffold. Every region runs on mock data shaped like the Python payloads. The real backend is specified in [`docs/FRONTEND_API.md`](../../../docs/FRONTEND_API.md) and is not built yet.

## Run

```bash
cd agent/ui/web
npm install
npm run dev
```

Open http://localhost:3000. The `predev` and `prebuild` scripts copy the reference meshes and reports from `data/reference/` into `public/mock/`, which is gitignored.

### Demo flow (mock)

1. **Limb.** Type in the profile, or tell the agent "change the proximal circumference to 310 mm". Fill length, P and D, select **Apply measurements**, then press **Confirm limb**.
2. **Socket.** Optionally tell the agent "make the wall 6 mm", then press **Confirm socket**.
3. **Printer.** Tell the agent "slice and print the socket", answer `draft_028`, and approve in the dialog. Ask "how is the print going?", then press **Demo: simulate link loss**.

The mock keeps its state until you reload the page.

| Variable | Default | Meaning |
|---|---|---|
| `NEXT_PUBLIC_USE_MOCK` | `1` | Set `0` to use the real HTTP API |
| `NEXT_PUBLIC_API_BASE` | `http://localhost:8001/api` | Base URL of the Python API |

To run against the real API, start the `web-real-api` entry in the repo's `.claude/launch.json`, or run `NEXT_PUBLIC_USE_MOCK=0 npm run dev -- --port 3001`. The page loads its state from `GET /api/session` on every load.

## Where things are

| Path | What |
|---|---|
| `app/page.tsx`, `app/socket/page.tsx`, `app/printer/page.tsx` | The three pages |
| `app/layout.tsx` | Fonts, the session provider, and the app shell. They live here so state survives navigation. |
| `lib/session.tsx` | Session state: measurement document, limb and socket revisions, agent turns, confirmations, and printer polling |
| `components/app-shell.tsx` | Top bar with the three steps. A step unlocks after the previous Confirm. Also holds the page heading, Confirm button, and global approval dialog. |
| `components/measurement-profile.tsx` | Required fields always expanded; optional fields in an expandable disclosure |
| `components/agent-chat.tsx`, `chat-panel.tsx` | Agent chat with editable example instructions and a collapsible tool-call trace |
| `components/print-panel.tsx` | One highlighted step plus the OctoPrint fields ([README_LONG](../../../docs/README_LONG.md) §12). Missing fields say "not reported". |
| `components/print-controls.tsx` | Slice and print actions, and the confirmation dialog |
| `components/stl-viewer.tsx`, `validation-list.tsx`, `header-dots.tsx` | The three.js viewer, the geometric checks, and the header dot field |
| `lib/types.ts`, `lib/api.ts`, `lib/mock/mock-api.ts` | Types that mirror Python, the API interface plus the HTTP client, and the mock |

## Design

The look follows the v0 template "Optimus" by kerroudj. Tokens are in `app/globals.css` and fonts in `app/layout.tsx`.
- **Fonts:** Instrument Sans, with JetBrains Mono for labels.
- **Colors:** a warm off-white `#fafaf9` background and ink `#080503`.
- **Shapes:** pill buttons, 4 px corners, and large tight-tracked headings (`.display-1` and `.display-2`).
- **Animation:** one dot-field canvas in the header only. It stays static under `prefers-reduced-motion`.

The UI components are shadcn/ui in the `base-nova` style, which is built on Base UI rather than Radix. Use the `render` prop instead of `asChild`.

## Rules the page keeps

- The browser never computes geometry and never sends file paths. It sends ids and displays what tools return.
- The limb has its own page. The socket page also offers an assembly demonstration using the matching confirmed limb revision: separated-to-seated translation, optional socket transparency, and a limb visibility toggle. Both display meshes receive the same limb-relative illustrative curve, preserving the form's P/M/D section sizes and axial length. The terminal section below D has an illustrative taper applied consistently to both parts. Source meshes and backend geometry remain unchanged; this is not a wall-thickness or clinical-fit simulation. Camera framing stays fixed across these controls. This demonstrates alignment, not clinical fit or collision-free insertion.
- Each stage fits the viewport; panels scroll internally when expanded content or smaller screens need more space. The first stage places the compact viewer and measurement form beside a larger agent panel.
- Manual measurements are drafts until **Apply measurements** succeeds. **Discard edits** restores the applied values; viewer annotations retain applied values while edits are pending. Limb Confirm stays disabled while length, P or D is empty, or edits are unapplied. Socket Confirm stays disabled unless the geometric checks pass.
- Socket measurements come only from the current validation report. Missing values say "Not reported". The socket viewer defaults to measured geometry (unaltered vertex positions); disabling that control enables the illustrative contour. Depth and circumference rings appear directly on measured geometry, using backend section heights and reported outer perimeters. An expandable details area provides all section values, while the viewer labels opening, middle and distal rings to avoid crowding. Recorded mock values are labeled. No pair clearance or overlap is inferred from socket dimensions.
- "Approve print" is enabled only when three things hold: the printer is ready, a job is sliced, and the agent has asked for a `start_print` confirmation.
- When the link drops, the panel keeps the last good read and labels it "Link lost". Time left shows "unknown", and no percentage is invented.
- "Simulate link loss" exists in mock mode only. Fault injection is never something the model can call.

## Notes

- Next.js 16: read `AGENTS.md` first. Next 16 keeps the previous page mounted but hidden (React Activity) for fast back navigation. That is why the DOM can hold more than one chat box. Only the visible one is live.
- The 3D viewers size themselves on animation frames. In a hidden or background tab they stay at the default canvas size until the tab is shown.

## Next steps for the owner

1. Build the API in `docs/FRONTEND_API.md`, then run with `NEXT_PUBLIC_USE_MOCK=0`.
2. Resolve the open dependencies at the end of that file. They cover CAD tool registration, naming, STL export and slice confirmation, and belong to Person 1 and Person 2.
