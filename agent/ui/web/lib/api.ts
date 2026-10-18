// One interface for the page, two implementations:
//   mockApi  scripted data shaped exactly like the Python payloads (default)
//   httpApi  the real backend described in docs/FRONTEND_API.md
// Select with NEXT_PUBLIC_USE_MOCK ("1" = mock, "0" = http).

import { mockApi } from "@/lib/mock/mock-api";
import type {
  AgentEvent,
  LimbRevision,
  Pause,
  Measurements,
  PreparedJob,
  PrinterStatus,
  PrintLayers,
  PrintSnapshot,
  SocketRevision,
  SocketValidation,
  ToolResult,
} from "@/lib/types";

export interface SocketBundle {
  socket: SocketRevision;
  validation: SocketValidation;
}

// GET /api/session: the server owns this state (README §13); the page loads it
// on start and after a reload instead of keeping its own copy.
export interface SessionSnapshot {
  measurements: Measurements;
  limb: LimbRevision; // r0 (the standardized shape) before any edit
  socket: SocketBundle | null; // set once the limb is confirmed
  socket_confirmed: boolean;
  job: PreparedJob | null;
  started: boolean; // a verified start_print happened
  pending: Pause | null; // a question or confirmation still waiting for the person
}

export interface WorkbenchApi {
  readonly isMock: boolean;
  getSession(): Promise<SessionSnapshot>;
  // Agent turns. Each yields tool_call / tool_result events, then one pause.
  sendMessage(text: string): AsyncIterable<AgentEvent>;
  answer(text: string): AsyncIterable<AgentEvent>;
  confirm(approved: boolean): AsyncIterable<AgentEvent>;
  // Limb page: the profile writes the measurement document; the server
  // validates, customizes and returns the new limb revision.
  applyMeasurements(m: Measurements): Promise<{ revision: LimbRevision }>;
  // Limb page Confirm: builds the demonstration socket for that revision.
  confirmLimb(revisionId: string): Promise<SocketBundle>;
  // Socket page Confirm: accepts the socket and moves the session to the printer.
  confirmSocket(socketId: string): Promise<void>;
  // Printer page, polled while the page is open (README §12 print monitoring).
  getPrinterStatus(): Promise<ToolResult<PrinterStatus>>;
  getPrintSnapshot(): Promise<PrintSnapshot | null>;
  // The started job's layers for the live layer view; null without real G-code.
  getPrintLayers(): Promise<PrintLayers | null>;
  getReport(): Promise<Record<string, unknown>>;
  // Mock only: demo control that is never exposed to the model.
  simulateLinkLoss?(): void;
}

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8001/api";

async function* readEventStream(response: Response): AsyncIterable<AgentEvent> {
  if (!response.ok || !response.body) {
    throw await responseError(response, `Agent request failed: HTTP ${response.status}`);
  }
  const reader = response.body.pipeThrough(new TextDecoderStream()).getReader();
  let buffer = "";
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += value;
    let split: number;
    while ((split = buffer.indexOf("\n\n")) !== -1) {
      const block = buffer.slice(0, split);
      buffer = buffer.slice(split + 2);
      const data = block
        .split("\n")
        .filter((line) => line.startsWith("data:"))
        .map((line) => line.slice(5).trim())
        .join("\n");
      if (data) yield JSON.parse(data) as AgentEvent;
    }
  }
}

function post(path: string, body: unknown): Promise<Response> {
  return fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    credentials: "include",
  });
}

// The server's error bodies carry the real reason: a ToolResult envelope
// ({ error: { reason, ... } }) for tool rejections (e.g. a 422 from
// /measurements), or { error: "..." } for conflicts. Surface that reason
// instead of a bare HTTP status, which tells the user nothing.
async function responseError(response: Response, fallback: string): Promise<Error> {
  try {
    const body = await response.json();
    const reason =
      (typeof body?.error === "string" ? body.error : body?.error?.reason) ?? body?.message;
    if (reason) return new Error(String(reason));
  } catch {
    // Body was not JSON; fall through to the status line.
  }
  return new Error(fallback);
}

async function postJson<T>(path: string, body: unknown): Promise<T> {
  const response = await post(path, body);
  if (!response.ok) throw await responseError(response, `POST ${path} failed: HTTP ${response.status}`);
  return (await response.json()) as T;
}

async function getJson<T>(path: string): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, { credentials: "include" });
  if (!response.ok) throw await responseError(response, `GET ${path} failed: HTTP ${response.status}`);
  return (await response.json()) as T;
}

export const httpApi: WorkbenchApi = {
  isMock: false,
  getSession: () => getJson("/session"),
  async *sendMessage(text) {
    yield* readEventStream(await post("/chat", { text }));
  },
  async *answer(text) {
    yield* readEventStream(await post("/answer", { answer: text }));
  },
  async *confirm(approved) {
    yield* readEventStream(await post("/confirm", { approved }));
  },
  applyMeasurements: (m) => postJson("/measurements", m),
  confirmLimb: (revisionId) => postJson("/limb/confirm", { revision_id: revisionId }),
  async confirmSocket(socketId) {
    await postJson("/socket/confirm", { socket_id: socketId });
  },
  getPrinterStatus: () => getJson("/printer"),
  getPrintSnapshot: () => getJson("/print/snapshot"),
  getPrintLayers: () => getJson("/print/layers"),
  getReport: () => getJson("/report"),
};

export const api: WorkbenchApi =
  process.env.NEXT_PUBLIC_USE_MOCK === "0" ? httpApi : mockApi;
