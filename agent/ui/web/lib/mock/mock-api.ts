// Mock backend for the three-page flow (README §3, §13). Payload shapes match
// the Python tools and the proposed endpoints in docs/FRONTEND_API.md. Values
// come from data/reference/ (copied to public/mock/) or a recorded agent run.
// The UI labels all of it "Mock data".

import type { SocketBundle, WorkbenchApi } from "@/lib/api";
import type {
  AgentEvent,
  Measurements,
  PrinterStatus,
  PrintSnapshot,
  SocketValidation,
  ToolResult,
} from "@/lib/types";

const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

const JOB_ID = "job_3fa9c1";
const ESTIMATED_SECONDS = 4635;
const FILAMENT_MM = 4542.84;

function ok<D>(message: string, data: D): ToolResult {
  return { status: "success", data, message, error: null, retryable: false } as unknown as ToolResult;
}

function fatal<D>(code: string, reason: string, message: string, data: D): ToolResult {
  return { status: "fatal", data, message, error: { code, reason }, retryable: false } as unknown as ToolResult;
}

// ----- mock session state -----

const state = {
  limbRevision: 0,
  socketRevision: 0,
  socketConfirmed: false,
  startedAt: null as number | null,
  completion: 0,
  linkLost: false,
  lastSnapshot: null as PrintSnapshot | null,
  awaiting: null as null | "profile",
};

const printing = () => state.startedAt != null && state.completion < 100;

function printerStatus(): ToolResult {
  if (state.linkLost) {
    return fatal(
      "printer_unreachable",
      "GET /api/connection failed: URLError",
      "Could not read the printer. Do not assume it is idle or printing.",
      { connection: null, port: null, ready: false, reasons: [], job_state: null, completion: null },
    );
  }
  const busy = printing();
  return ok(busy ? "Printer is Printing, not ready: busy_or_error." : "Printer is Operational, ready.", {
    connection: busy ? "Printing" : "Operational",
    port: "VIRTUAL",
    ready: !busy,
    reasons: busy ? ["busy_or_error"] : [],
    job_state: busy ? "Printing" : "Operational",
    completion: state.startedAt != null ? state.completion : null,
  } satisfies PrinterStatus);
}

// ----- scripted agent -----

async function* play(events: AgentEvent[]): AsyncIterable<AgentEvent> {
  for (const event of events) {
    await sleep(event.type === "pause" ? 450 : 600);
    yield event;
  }
}

const answer = (text: string): AgentEvent => ({ type: "pause", pause: { kind: "answer", text, details: {} } });

function measurementTurn(text: string): AgentEvent[] {
  // e.g. "change the proximal circumference to 310 mm"
  const value = Number(text.match(/(\d+(?:\.\d+)?)\s*mm/i)?.[1]);
  const field = /proximal|\bp\b/i.test(text)
    ? "proximal_circumference_mm"
    : /distal|\bd\b/i.test(text)
      ? "distal_circumference_mm"
      : /length|long/i.test(text)
        ? "length_mm"
        : null;
  if (!field || !Number.isFinite(value)) {
    return [
      {
        type: "pause",
        pause: { kind: "question", text: "Which measurement should change, and to how many millimetres?", details: {} },
      },
    ];
  }
  state.limbRevision += 1;
  const revision = `r${state.limbRevision}`;
  return [
    { type: "tool_call", name: "validate_measurements", args: { measurements: { [field]: value }, correction: true } },
    { type: "tool_result", name: "validate_measurements", result: ok("Measurements accepted.", { accepted: true }) },
    { type: "tool_call", name: "customize_residual_limb", args: { [field]: value } },
    {
      type: "tool_result",
      name: "customize_residual_limb",
      result: ok(`Limb revision ${revision} written. Targets met within tolerance.`, {
        revision_id: revision,
        parent_revision_id: `r${state.limbRevision - 1}`,
        stl_url: "/mock/standardized_limb.stl",
        measurements: { [field]: value },
      }),
    },
    answer(
      `Updated ${field.replace(/_mm$/, "").replaceAll("_", " ")} to ${value} mm. Revision ${revision}; other measurements are unchanged.`,
    ),
  ];
}

function socketTurn(text: string): AgentEvent[] {
  const wall = Number(text.match(/(\d+(?:\.\d+)?)\s*mm/i)?.[1]) || 5;
  state.socketRevision += 1;
  const socketId = `socket_r${state.socketRevision}`;
  return [
    { type: "tool_call", name: "modify_socket", args: { operation: "set_nominal_wall_thickness", value_mm: wall } },
    {
      type: "tool_result",
      name: "modify_socket",
      result: ok(`Socket ${socketId} written with ${wall} mm nominal wall. Validation passed.`, {
        socket_id: socketId,
        stl_url: "/mock/standardized_socket.stl",
      }),
    },
    answer(`Set the nominal wall to ${wall} mm (${socketId}). The limb file is unchanged.`),
  ];
}

function printStartTurn(): AgentEvent[] {
  if (!state.socketConfirmed) {
    return [answer("Confirm the socket first; then I can slice and print it.")];
  }
  state.awaiting = "profile";
  return [
    { type: "tool_call", name: "get_printer_status", args: {} },
    { type: "tool_result", name: "get_printer_status", result: printerStatus() },
    {
      type: "pause",
      pause: { kind: "question", text: "Which profile should I use: draft_028 (faster) or demo_020 (finer)?", details: {} },
    },
  ];
}

function statusTurn(): AgentEvent[] {
  const result = printerStatus();
  const snap = state.lastSnapshot;
  const text =
    result.status !== "success"
      ? "I can't read the printer right now, so the job state is unknown. I won't say it finished or failed."
      : snap
        ? `Step ${snap.step}, ${snap.completion}% complete, ${Math.round((snap.print_time_s ?? 0) / 60)} min elapsed${
            snap.print_time_left_s != null
              ? `, about ${Math.round(snap.print_time_left_s / 60)} min left`
              : ", time left not reported yet"
          }. Port ${snap.port}.`
        : "The printer is ready and nothing is printing.";
  return [
    { type: "tool_call", name: "get_printer_status", args: {} },
    { type: "tool_result", name: "get_printer_status", result },
    answer(text),
  ];
}

// ----- printer snapshot (proposed server poll) -----

function snapshot(): PrintSnapshot | null {
  if (state.startedAt == null) return null;
  if (state.linkLost) {
    return state.lastSnapshot ? { ...state.lastSnapshot, step: "Link lost", stale: true } : null;
  }
  const elapsed = Math.round((Date.now() - state.startedAt) / 1000);
  if (elapsed > 2) state.completion = Math.min(100, state.completion + 3);
  const done = state.completion >= 100;
  const snap: PrintSnapshot = {
    job_id: JOB_ID,
    step: done ? "Finished" : elapsed <= 2 ? "Starting" : "Printing",
    observed_at: new Date().toISOString(),
    stale: false,
    completion: state.completion,
    filepos: Math.round(2480449 * (state.completion / 100)),
    print_time_s: elapsed,
    print_time_left_s: state.completion < 8 ? null : Math.round(ESTIMATED_SECONDS * (1 - state.completion / 100)),
    file: { name: `${JOB_ID}.gcode`, size: 2480449 },
    filament_mm: FILAMENT_MM,
    port: "VIRTUAL",
    temperatures: { tool0: { actual: 214.8, target: 215 }, bed: { actual: 60.1, target: 60 } },
    error: null,
    layer: null,
    layer_count: null,
    layer_z: null,
  };
  state.lastSnapshot = snap;
  return snap;
}

// ----- the mock api -----

export const mockApi: WorkbenchApi = {
  isMock: true,

  async getSession() {
    await sleep(150);
    return {
      measurements: {
        length_mm: null,
        proximal_circumference_mm: null,
        distal_circumference_mm: null,
        mid_circumference_mm: null,
        ap_depth_mm: null,
        ml_width_mm: null,
        distal_shape: "template",
        side: "template",
      },
      limb: { revision_id: "r0", parent_revision_id: null, stl_url: "/mock/standardized_limb.stl" },
      socket: null,
      socket_confirmed: false,
      job: null,
      started: false,
      pending: null,
    };
  },

  sendMessage(text) {
    if (/how.*(going|print)|progress|status/i.test(text) && state.startedAt != null) return play(statusTurn());
    if (/print|slice/i.test(text)) return play(printStartTurn());
    if (/wall|thick|depth|socket/i.test(text)) return play(socketTurn(text));
    if (/\d\s*mm|circumference|length/i.test(text)) return play(measurementTurn(text));
    if (/status|ready|printer/i.test(text)) return play(statusTurn());
    return play([
      answer("(Mock agent) I can change a measurement, change the socket, check the printer, or slice and print."),
    ]);
  },

  answer(text) {
    if (state.awaiting !== "profile") return play(measurementTurn(text));
    state.awaiting = null;
    const profile = /demo/i.test(text) ? "demo_020" : "draft_028";
    const socketId = `socket_r${state.socketRevision}`;
    const summary = `Print ${socketId} with ${profile}. Estimated 77 minutes and 4.54 m of filament.`;
    return play([
      { type: "tool_call", name: "prepare_print", args: { revision_id: socketId, profile_id: profile } },
      {
        type: "tool_result",
        name: "prepare_print",
        result: ok(`Sliced with ${profile}: about 77 min, 4.54 m of filament. Next: request_confirmation for start_print.`, {
          job_id: JOB_ID,
          revision_id: socketId,
          profile_id: profile,
          estimated_seconds: ESTIMATED_SECONDS,
          filament_m: 4.54,
          reused: false,
        }),
      },
      { type: "tool_call", name: "request_confirmation", args: { action: "start_print", subject: JOB_ID, summary } },
      { type: "pause", pause: { kind: "confirmation", text: summary, details: { action: "start_print", subject: JOB_ID } } },
    ]);
  },

  confirm(approved) {
    if (!approved) return play([answer("Understood. I won't start the print.")]);
    state.startedAt = Date.now();
    state.completion = 0;
    return play([
      { type: "tool_call", name: "start_print", args: { job_id: JOB_ID, confirmation_id: "conf_8d21e6a0" } },
      {
        type: "tool_result",
        name: "start_print",
        result: ok(`Print of ${JOB_ID} started and confirmed by the printer (Printing).`, {
          job_id: JOB_ID,
          state: "Printing",
          verified: true,
        }),
      },
      answer("The print has started and the printer confirmed it. Ask me how it's going at any time."),
    ]);
  },

  async applyMeasurements(m: Measurements) {
    await sleep(800);
    void m;
    state.limbRevision += 1;
    return {
      revision: {
        revision_id: `r${state.limbRevision}`,
        parent_revision_id: `r${state.limbRevision - 1}`,
        stl_url: "/mock/standardized_limb.stl",
      },
    };
  },

  async confirmLimb(revisionId): Promise<SocketBundle> {
    await sleep(1200);
    const response = await fetch("/mock/standardized_socket_report.json");
    const validation = (await response.json()) as SocketValidation;
    state.socketRevision = 1;
    return {
      socket: { socket_id: "socket_r1", limb_revision_id: revisionId, stl_url: "/mock/standardized_socket.stl" },
      validation,
    };
  },

  async confirmSocket() {
    await sleep(400);
    state.socketConfirmed = true;
  },

  async getPrinterStatus() {
    await sleep(100);
    return printerStatus() as unknown as ToolResult<PrinterStatus>;
  },

  async getPrintLayers() {
    return null; // mock jobs have no G-code
  },

  async getPrintSnapshot() {
    await sleep(100);
    return snapshot();
  },

  async getReport() {
    return {
      mock: true,
      clinical_use: false,
      statement: "Nonclinical demonstration. Scaled synthetic template; checks are geometric and process checks.",
      limb_revision: `r${state.limbRevision}`,
      socket: `socket_r${state.socketRevision}`,
      job_id: JOB_ID,
      last_observed_step: state.lastSnapshot?.step ?? null,
      last_observed_at: state.lastSnapshot?.observed_at ?? null,
    };
  },

  simulateLinkLoss() {
    state.linkLost = true;
  },
};
