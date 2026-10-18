"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
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

// Form ranges from README §5. They only catch typos; validate_measurements on
// the server decides whether the standardized shape can honour a number.
const REQUIRED: { key: NumberKey; label: string; hint: string; min: number; max: number }[] = [
  { key: "length_mm", label: "Residual length", hint: "Mid-patellar tendon to distal end, knee extended", min: 50, max: 300 },
  { key: "proximal_circumference_mm", label: "Proximal circumference (P)", hint: "40 mm below the mid-patellar tendon", min: 150, max: 550 },
  { key: "distal_circumference_mm", label: "Distal circumference (D)", hint: "40 mm above the distal end", min: 100, max: 500 },
];

const OPTIONAL: { key: NumberKey; label: string; hint: string; min: number; max: number }[] = [
  { key: "mid_circumference_mm", label: "Mid circumference (M)", hint: "Halfway between P and D", min: 100, max: 550 },
  { key: "ap_depth_mm", label: "AP depth at P", hint: "With ML, or leave both empty", min: 40, max: 200 },
  { key: "ml_width_mm", label: "ML width at P", hint: "With AP, or leave both empty", min: 40, max: 200 },
];

export function MeasurementProfile() {
  const { measurements, setMeasurements, applyMeasurements, applying, limb } = useSession();
  const [errors, setErrors] = useState<Partial<Record<NumberKey | "pair", string>>>({});

  const setNumber = (key: NumberKey, raw: string) => {
    const value = raw.trim() === "" ? null : Number(raw);
    setMeasurements({ ...measurements, [key]: Number.isNaN(value) ? measurements[key] : value });
  };

  const check = () => {
    const next: typeof errors = {};
    for (const f of [...REQUIRED, ...OPTIONAL]) {
      const v = measurements[f.key];
      if (v == null) {
        if (REQUIRED.includes(f)) next[f.key] = "Required";
      } else if (v < f.min || v > f.max) next[f.key] = `Accepts ${f.min}–${f.max} mm`;
    }
    if ((measurements.ap_depth_mm == null) !== (measurements.ml_width_mm == null)) {
      next.pair = "AP and ML go together. Fill both or neither.";
    }
    setErrors(next);
    return Object.keys(next).length === 0;
  };

  const field = (f: (typeof REQUIRED)[number], required: boolean) => (
    <div key={f.key} className="grid gap-1">
      <Label htmlFor={f.key} className="text-xs">
        {f.label}
        {required && <span className="text-muted-foreground"> *</span>}
      </Label>
      <div className="relative">
        <Input
          id={f.key}
          inputMode="decimal"
          value={measurements[f.key] ?? ""}
          onChange={(e) => setNumber(f.key, e.target.value)}
          aria-invalid={Boolean(errors[f.key])}
          aria-describedby={`${f.key}-hint`}
          className="h-9 pr-10 font-mono"
        />
        <span className="eyebrow pointer-events-none absolute top-1/2 right-3 -translate-y-1/2">mm</span>
      </div>
      <p id={`${f.key}-hint`} className={errors[f.key] ? "text-[11px] text-destructive" : "text-[11px] text-muted-foreground"}>
        {errors[f.key] ?? f.hint}
      </p>
    </div>
  );

  return (
    <form
      className="grid gap-4 rounded-md border bg-card p-4"
      noValidate
      onSubmit={(e) => {
        e.preventDefault();
        if (check()) applyMeasurements();
      }}
    >
      <div className="flex items-baseline justify-between gap-2">
        <h2 className="text-base">Measurement profile</h2>
        <span className="eyebrow">Limb {limb?.revision_id ?? "…"}</span>
      </div>

      <div className="grid gap-3 sm:grid-cols-3 lg:grid-cols-1 xl:grid-cols-3">{REQUIRED.map((f) => field(f, true))}</div>

      <div className="grid gap-2">
        <span className="eyebrow">Optional</span>
        <div className="grid gap-3 sm:grid-cols-3 lg:grid-cols-1 xl:grid-cols-3">{OPTIONAL.map((f) => field(f, false))}</div>
        {errors.pair && <p className="text-[11px] text-destructive">{errors.pair}</p>}
        <div className="grid gap-3 sm:grid-cols-2">
          <div className="grid gap-1">
            <Label htmlFor="distal_shape" className="text-xs">
              Distal-end shape
            </Label>
            <select
              id="distal_shape"
              value={measurements.distal_shape}
              onChange={(e) => setMeasurements({ ...measurements, distal_shape: e.target.value as Measurements["distal_shape"] })}
              className="h-9 rounded-md border border-input bg-background px-3 text-sm"
            >
              <option value="template">Template</option>
              <option value="rounder">Slightly rounder</option>
              <option value="more_tapered">Slightly more tapered</option>
            </select>
          </div>
          <div className="grid gap-1">
            <Label htmlFor="side" className="text-xs">
              Side
            </Label>
            <select
              id="side"
              value={measurements.side}
              onChange={(e) => setMeasurements({ ...measurements, side: e.target.value as Measurements["side"] })}
              className="h-9 rounded-md border border-input bg-background px-3 text-sm"
            >
              <option value="template">Template side</option>
              <option value="left">Left</option>
              <option value="right">Right</option>
            </select>
          </div>
        </div>
      </div>

      <div className="flex flex-wrap items-center justify-between gap-3 border-t pt-3">
        <p className="max-w-xs text-[11px] text-muted-foreground">
          Values resize the standard demonstration limb. They do not reconstruct a residual limb.
        </p>
        <Button type="submit" variant="outline" disabled={applying} className="h-9 rounded-full px-4">
          {applying ? "Updating…" : "Update model"}
        </Button>
      </div>
    </form>
  );
}
