"use client";

// One session shared by all three pages (README §13: "The same agent chat is on
// every page"). Mounted in the root layout so client navigation keeps the chat,
// the measurement document and the print state.

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { api, type SocketBundle } from "@/lib/api";
import type { ChatItem, TraceStep } from "@/components/chat-panel";
import type {
  AgentEvent,
  LimbRevision,
  Measurements,
  Pause,
  PreparedJob,
  PrinterStatus,
  PrintSnapshot,
  SocketValidation,
  ToolResult,
} from "@/lib/types";

const POLL_MS = 2000; // README §12: server polls about every 2 s; the page paints it

export const EMPTY_MEASUREMENTS: Measurements = {
  length_mm: null,
  proximal_circumference_mm: null,
  distal_circumference_mm: null,
  mid_circumference_mm: null,
  ap_depth_mm: null,
  ml_width_mm: null,
  distal_shape: "template",
  side: "template",
};

export const REQUIRED_FIELDS = ["length_mm", "proximal_circumference_mm", "distal_circumference_mm"] as const;

let nextId = 0;
const newId = () => `item-${++nextId}`;

interface Session {
  loaded: boolean;
  loadError: string | null;
  // Limb page
  measurements: Measurements;
  setMeasurements: (m: Measurements) => void;
  limb: LimbRevision | null;
  applying: boolean;
  applyMeasurements: () => Promise<void>;
  requiredFilled: boolean;
  confirmingLimb: boolean;
  confirmLimb: () => Promise<boolean>;
  // Socket page
  socket: SocketBundle | null;
  limbConfirmed: boolean;
  confirmingSocket: boolean;
  confirmSocket: () => Promise<boolean>;
  socketConfirmed: boolean;
  // Agent
  items: ChatItem[];
  pending: Pause | null;
  busy: boolean;
  send: (text: string) => void;
  decide: (approved: boolean) => void;
  dialogOpen: boolean;
  setDialogOpen: (open: boolean) => void;
  // Printer page
  printer: ToolResult<PrinterStatus> | null;
  job: PreparedJob | null;
  started: boolean;
  snapshot: PrintSnapshot | null;
  downloadReport: () => Promise<void>;
}

const SessionContext = createContext<Session | null>(null);

export function useSession(): Session {
  const session = useContext(SessionContext);
  if (!session) throw new Error("useSession must be used inside <SessionProvider>");
  return session;
}

export function SessionProvider({ children }: { children: React.ReactNode }) {
  const [measurements, setMeasurements] = useState<Measurements>(EMPTY_MEASUREMENTS);
  const [loaded, setLoaded] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [limb, setLimb] = useState<LimbRevision | null>(null);
  const [applying, setApplying] = useState(false);
  const [confirmingLimb, setConfirmingLimb] = useState(false);
  const [socket, setSocket] = useState<SocketBundle | null>(null);
  const [confirmingSocket, setConfirmingSocket] = useState(false);
  const [socketConfirmed, setSocketConfirmed] = useState(false);

  const [items, setItems] = useState<ChatItem[]>([]);
  const [pending, setPending] = useState<Pause | null>(null);
  const [busy, setBusy] = useState(false);
  const [dialogOpen, setDialogOpen] = useState(false);

  const router = useRouter();

  const [printer, setPrinter] = useState<ToolResult<PrinterStatus> | null>(null);
  const [job, setJob] = useState<PreparedJob | null>(null);
  const [started, setStarted] = useState(false);
  const [snapshot, setSnapshot] = useState<PrintSnapshot | null>(null);

  // The server is the source of truth; this applies its session snapshot.
  const applyServerSession = useCallback((s: Awaited<ReturnType<typeof api.getSession>>) => {
    setMeasurements(s.measurements);
    setLimb(s.limb);
    setSocket(s.socket);
    setSocketConfirmed(s.socket_confirmed);
    setJob(s.job);
    setStarted(s.started);
    setPending(s.pending);
  }, []);

  // Load the server's session once.
  useEffect(() => {
    let alive = true;
    api
      .getSession()
      .then((s) => {
        if (!alive) return;
        applyServerSession(s);
        setLoaded(true);
      })
      .catch((error: Error) => alive && setLoadError(error.message));
    return () => {
      alive = false;
    };
  }, [applyServerSession]);

  const requiredFilled = REQUIRED_FIELDS.every((key) => measurements[key] != null);

  // Printer readiness and the print snapshot are polled once the socket is
  // confirmed, whether or not the chat is active.
  useEffect(() => {
    if (!socketConfirmed) return;
    let alive = true;
    const tick = async () => {
      try {
        const status = await api.getPrinterStatus();
        if (alive) setPrinter(status);
      } catch {
        if (alive) setPrinter(null);
      }
      if (started) {
        try {
          const snap = await api.getPrintSnapshot();
          if (alive && snap) setSnapshot(snap);
        } catch {
          if (alive) setSnapshot((prev) => (prev ? { ...prev, step: "Link lost", stale: true } : prev));
        }
      }
    };
    tick();
    const timer = setInterval(tick, POLL_MS);
    return () => {
      alive = false;
      clearInterval(timer);
    };
  }, [socketConfirmed, started]);

  const handleToolResult = useCallback((name: string, result: ToolResult) => {
    const data = result.data as Record<string, unknown>;
    // validate_part reports for the current socket whether it passed or not.
    if (name === "validate_part" && data.validation) {
      setSocket((s) =>
        s && s.socket.socket_id === data.revision_id ? { ...s, validation: data.validation as SocketValidation } : s,
      );
      return;
    }
    if (result.status !== "success") return;
    if (name === "customize_residual_limb") {
      setLimb({
        revision_id: String(data.revision_id),
        parent_revision_id: (data.parent_revision_id as string) ?? null,
        stl_url: String(data.stl_url),
      });
      if (data.measurements) setMeasurements((m) => ({ ...m, ...(data.measurements as Partial<Measurements>) }));
    }
    // fit_socket_to_limb also makes a new socket revision (e.g. after a limb change in chat).
    if ((name === "modify_socket" || name === "fit_socket_to_limb") && data.socket_id) {
      // A new socket revision has not been checked yet; the server sends that state.
      setSocket((s) =>
        s
          ? {
              socket: {
                ...s.socket,
                socket_id: String(data.socket_id),
                stl_url: String(data.stl_url ?? s.socket.stl_url),
                limb_revision_id: typeof data.limb_revision_id === "string" ? data.limb_revision_id : s.socket.limb_revision_id,
              },
              validation: (data.validation as SocketValidation) ?? {
                ...s.validation, passed: false, categories: {}, measurements: undefined,
                error: { message: "Measurements and checks have not been reported for this socket revision." },
              },
            }
          : s,
      );
      setSocketConfirmed(false);
    }
    if (name === "prepare_print" || name === "slice") setJob(data as unknown as PreparedJob);
    if (name === "start_print" && data.verified) setStarted(true);
  }, []);

  const runTurn = useCallback(
    async (events: AsyncIterable<AgentEvent>) => {
      setBusy(true);
      const traceId = newId();
      let steps: TraceStep[] = [];
      const pushTrace = () =>
        setItems((prev) => {
          const without = prev.filter((item) => item.id !== traceId);
          return steps.length ? [...without, { id: traceId, role: "trace", steps: [...steps] }] : without;
        });
      try {
        for await (const event of events) {
          if (event.type === "tool_call") {
            steps = [...steps, { name: event.name, args: event.args }];
            pushTrace();
          } else if (event.type === "navigate") {
            // The server performed the stage change (built/confirmed the
            // socket as needed). Refresh from it before routing, so the
            // destination page's own guards see the new state.
            try {
              applyServerSession(await api.getSession());
            } catch {
              // Keep the current state; routing below still applies.
            }
            router.push(event.stage === "socket" ? "/socket" : event.stage === "printer" ? "/printer" : "/");
          } else if (event.type === "tool_result") {
            const index = steps.findLastIndex((s) => s.name === event.name && !s.result);
            if (index >= 0) steps = steps.map((s, i) => (i === index ? { ...s, result: event.result } : s));
            pushTrace();
            handleToolResult(event.name, event.result);
          } else {
            const pause = event.pause;
            setPending(pause.kind === "question" || pause.kind === "confirmation" ? pause : null);
            if (pause.kind === "confirmation") setDialogOpen(true);
            else
              setItems((prev) => [
                ...prev,
                {
                  id: newId(),
                  role: pause.kind === "question" ? "question" : "agent",
                  text: pause.text,
                  ...(pause.kind === "question" ? { options: pause.details?.options } : {}),
                },
              ]);
          }
        }
      } catch (error) {
        setItems((prev) => [...prev, { id: newId(), role: "error", text: (error as Error).message }]);
      } finally {
        setBusy(false);
      }
    },
    [handleToolResult, applyServerSession, router],
  );

  const send = useCallback(
    (text: string) => {
      setItems((prev) => [...prev, { id: newId(), role: "user", text }]);
      if (pending?.kind === "question") {
        setPending(null);
        runTurn(api.answer(text));
      } else {
        runTurn(api.sendMessage(text));
      }
    },
    [pending, runTurn],
  );

  const decide = useCallback(
    (approved: boolean) => {
      setDialogOpen(false);
      setPending(null);
      setItems((prev) => [...prev, { id: newId(), role: "user", text: approved ? "Approved." : "Declined." }]);
      runTurn(api.confirm(approved));
    },
    [runTurn],
  );

  const applyMeasurements = useCallback(async () => {
    setApplying(true);
    try {
      const { revision } = await api.applyMeasurements(measurements);
      setLimb(revision);
    } catch (error) {
      setItems((prev) => [...prev, { id: newId(), role: "error", text: (error as Error).message }]);
    } finally {
      setApplying(false);
    }
  }, [measurements]);

  const confirmLimb = useCallback(async () => {
    if (!requiredFilled || !limb) return false;
    setConfirmingLimb(true);
    try {
      setSocket(await api.confirmLimb(limb.revision_id));
      return true;
    } catch (error) {
      setItems((prev) => [...prev, { id: newId(), role: "error", text: (error as Error).message }]);
      return false;
    } finally {
      setConfirmingLimb(false);
    }
  }, [limb, requiredFilled]);

  const confirmSocket = useCallback(async () => {
    if (!socket) return false;
    setConfirmingSocket(true);
    try {
      await api.confirmSocket(socket.socket.socket_id);
      setSocketConfirmed(true);
      return true;
    } catch (error) {
      setItems((prev) => [...prev, { id: newId(), role: "error", text: (error as Error).message }]);
      return false;
    } finally {
      setConfirmingSocket(false);
    }
  }, [socket]);

  const downloadReport = useCallback(async () => {
    const report = await api.getReport();
    const blob = new Blob([JSON.stringify(report, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = Object.assign(document.createElement("a"), { href: url, download: "fabrication-report.json" });
    a.click();
    URL.revokeObjectURL(url);
  }, []);

  const value = useMemo<Session>(
    () => ({
      loaded,
      loadError,
      measurements,
      setMeasurements,
      limb,
      applying,
      applyMeasurements,
      requiredFilled,
      confirmingLimb,
      confirmLimb,
      socket,
      limbConfirmed: socket != null,
      confirmingSocket,
      confirmSocket,
      socketConfirmed,
      items,
      pending,
      busy,
      send,
      decide,
      dialogOpen,
      setDialogOpen,
      printer,
      job,
      started,
      snapshot,
      downloadReport,
    }),
    [
      loaded,
      loadError,
      measurements,
      limb,
      applying,
      applyMeasurements,
      requiredFilled,
      confirmingLimb,
      confirmLimb,
      socket,
      confirmingSocket,
      confirmSocket,
      socketConfirmed,
      items,
      pending,
      busy,
      send,
      decide,
      dialogOpen,
      printer,
      job,
      started,
      snapshot,
      downloadReport,
    ],
  );

  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}
