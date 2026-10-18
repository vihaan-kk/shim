"use client";

import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useSession } from "@/lib/session";
import type { Measurements } from "@/lib/types";

type NumberKey =
  | "length_mm"
  | "proximal_circumference_mm"
  | "distal_circumference_mm"
  | "mid_circumference_mm"
  | "ap_depth_mm"
  | "ml_width_mm";

const REQUIRED: { key: NumberKey; label: string; hint: string }[] = [
  { key: "length_mm", label: "Residual length", hint: "Mid-patellar tendon to distal end, knee extended" },
  { key: "proximal_circumference_mm", label: "Proximal circumference (P)", hint: "40 mm below the mid-patellar tendon" },
  { key: "distal_circumference_mm", label: "Distal circumference (D)", hint: "40 mm above the distal end" },
];

const OPTIONAL: { key: NumberKey; label: string; hint: string }[] = [
  { key: "mid_circumference_mm", label: "Mid circumference (M)", hint: "Halfway between P and D" },
  { key: "ap_depth_mm", label: "AP depth at P", hint: "Set together with ML" },
  { key: "ml_width_mm", label: "ML width at P", hint: "Set together with AP" },
];

const DISTAL_SHAPE: Record<Measurements["distal_shape"], string> = {
  template: "Template",
  rounder: "Slightly rounder",
  more_tapered: "Slightly more tapered",
};

const SIDE: Record<Measurements["side"], string> = {
  template: "Template side",
  left: "Left",
  right: "Right",
};

// Read-only: the agent changes these values (validate_measurements, then
// customize_residual_limb), and the page shows what the server reports.
export function MeasurementProfile() {
  const { measurements, limb } = useSession();

  const field = (f: (typeof REQUIRED)[number]) => {
    const value = measurements[f.key];
    return (
      <div key={f.key} className="grid gap-1">
        <Label htmlFor={f.key} className="text-xs">
          {f.label}
        </Label>
        <div className="relative">
          <Input
            id={f.key}
            readOnly
            value={value ?? "Standard"}
            aria-describedby={`${f.key}-hint`}
            className="h-9 cursor-default bg-muted/40 pr-10 font-mono focus-visible:ring-0"
          />
          {value != null && (
            <span className="eyebrow pointer-events-none absolute top-1/2 right-3 -translate-y-1/2">mm</span>
          )}
        </div>
        <p id={`${f.key}-hint`} className="text-[11px] text-muted-foreground">
          {f.hint}
        </p>
      </div>
    );
  };

  const choice = (id: string, label: string, value: string) => (
    <div className="grid gap-1">
      <Label htmlFor={id} className="text-xs">
        {label}
      </Label>
      <Input id={id} readOnly value={value} className="h-9 cursor-default bg-muted/40 focus-visible:ring-0" />
    </div>
  );

  return (
    <section className="measurement-panel grid gap-2 rounded-md border bg-card p-3" aria-label="Measurement profile">
      <div className="flex items-baseline justify-between gap-2">
        <h2 className="text-base">Measurement profile</h2>
        <span className="eyebrow">Limb {limb?.revision_id ?? "…"}</span>
      </div>

      <div className="grid gap-3 sm:grid-cols-3">{REQUIRED.map(field)}</div>

      <details className="rounded border px-3 py-2">
        <summary className="cursor-pointer text-sm focus-visible:outline-2">Optional measurements and shape</summary>
        <div className="mt-3 grid gap-3">
          <div className="grid gap-3 sm:grid-cols-3">{OPTIONAL.map(field)}</div>
          <div className="grid gap-3 sm:grid-cols-2">
            {choice("distal_shape", "Distal-end shape", DISTAL_SHAPE[measurements.distal_shape])}
            {choice("side", "Side", SIDE[measurements.side])}
          </div>
        </div>
      </details>

      <p className="border-t pt-2 text-[11px] text-muted-foreground">
        Ask the agent to change a value, for example &ldquo;make the residual length 150 mm&rdquo;. Values resize
        the standard demonstration limb. They do not reconstruct a residual limb.
      </p>
    </section>
  );
}
