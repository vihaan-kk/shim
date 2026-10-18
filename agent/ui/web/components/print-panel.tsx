"use client";

import { Progress } from "@/components/ui/progress";
import { useSession } from "@/lib/session";
import { cn } from "@/lib/utils";
import type { PrintStep } from "@/lib/types";

// README §12 "Print monitoring": one highlighted step, the completion bar, and
// the OctoPrint fields. Missing fields say "not reported"; link loss, pausing
// and errors replace the bar's caption instead of inventing a number.
const STEPS: PrintStep[] = ["Starting", "Printing", "Pausing", "Paused", "Error", "Link lost", "Finished"];

const minutes = (s: number | null | undefined) =>
  s == null ? null : s < 60 ? `${s} s` : `${Math.floor(s / 60)} min ${String(s % 60).padStart(2, "0")} s`;

function Field({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="grid gap-0.5">
      <dt className="eyebrow">{label}</dt>
      <dd className="text-sm">{value ?? <span className="text-muted-foreground">not reported</span>}</dd>
    </div>
  );
}

export function PrintPanel() {
  const { snapshot: snap, job, started } = useSession();

  if (!started || !snap) {
    return (
      <div className="grid gap-2 rounded-md border border-dashed p-6">
        <span className="eyebrow">No job running</span>
        <p className="text-sm text-muted-foreground">
          Ask the agent to slice and print the confirmed socket. The job appears here after the printer confirms the
          start.
        </p>
      </div>
    );
  }

  const blocked = snap.step === "Link lost" || snap.step === "Error" || snap.step === "Pausing" || snap.step === "Paused";
  const caption =
    snap.step === "Link lost"
      ? `Link lost · showing the last good read from ${new Date(snap.observed_at).toLocaleTimeString()}`
      : snap.step === "Error"
        ? `Error${snap.error ? `: ${snap.error}` : ""}`
        : snap.step === "Pausing" || snap.step === "Paused"
          ? snap.step
          : `Observed ${new Date(snap.observed_at).toLocaleTimeString()}`;

  return (
    <div className="grid gap-6">
      <ol className="flex flex-wrap gap-1.5" aria-label="Print step">
        {STEPS.map((step) => (
          <li
            key={step}
            aria-current={snap.step === step ? "step" : undefined}
            className={cn(
              "rounded-full border px-3 py-1 text-xs",
              snap.step === step
                ? step === "Link lost" || step === "Error"
                  ? "border-destructive bg-destructive text-white"
                  : "border-primary bg-primary text-primary-foreground"
                : "text-muted-foreground",
            )}
          >
            {step}
          </li>
        ))}
      </ol>

      <div className="grid gap-3">
        <div className="flex items-baseline gap-3">
          <span className={cn("display-2 font-mono tabular-nums", snap.stale && "text-muted-foreground")}>
            {snap.completion == null ? "—" : snap.completion.toFixed(1)}
            {snap.completion != null && "%"}
          </span>
          <span className="text-sm text-muted-foreground">completion as reported by OctoPrint</span>
        </div>
        <Progress value={snap.completion ?? 0} aria-label="Print completion" className={blocked ? "opacity-40" : ""} />
        <p className={cn("eyebrow", snap.step === "Link lost" || snap.step === "Error" ? "text-destructive" : "")}>{caption}</p>
      </div>

      <dl className="grid grid-cols-2 gap-x-6 gap-y-4 sm:grid-cols-4">
        <Field label="Elapsed" value={minutes(snap.print_time_s)} />
        <Field
          label="Time left"
          value={snap.stale ? "unknown" : snap.print_time_left_s == null ? "not available yet" : minutes(snap.print_time_left_s)}
        />
        <Field label="File" value={snap.file ? <span className="font-mono">{snap.file.name}</span> : null} />
        <Field
          label="Filament estimate"
          value={snap.filament_mm != null ? `${(snap.filament_mm / 1000).toFixed(2)} m` : job?.filament_m != null ? `${job.filament_m} m` : null}
        />
        <Field
          label="Port"
          value={
            snap.port == null ? null : snap.port === "VIRTUAL" ? (
              <span className="font-mono">VIRTUAL</span>
            ) : (
              <span className="font-mono text-destructive">{snap.port} · not the virtual port</span>
            )
          }
        />
        <Field
          label="Nozzle (virtual)"
          value={snap.temperatures?.tool0 ? `${snap.temperatures.tool0.actual} / ${snap.temperatures.tool0.target ?? "—"} °C` : null}
        />
        <Field
          label="Bed (virtual)"
          value={snap.temperatures?.bed ? `${snap.temperatures.bed.actual} / ${snap.temperatures.bed.target ?? "—"} °C` : null}
        />
        <Field label="Profile" value={job ? <span className="font-mono">{job.profile_id}</span> : null} />
      </dl>
    </div>
  );
}
