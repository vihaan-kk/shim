"use client";

import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { Badge } from "@/components/ui/badge";
import type { SocketValidation } from "@/lib/types";

const CATEGORY_LABELS: Record<string, string> = {
  cad_validity: "Geometric check: solid is valid",
  dimensions: "Geometric check: dimensions",
  structure: "Geometric check: structure",
  reference_integrity: "Geometric check: reference integrity",
};

// Renders validate_socket output. Every row is named as a geometric check,
// never as fit or safety.
export function ValidationList({ data }: { data: SocketValidation }) {
  return (
    <div className="grid gap-3">
      {Object.keys(data.categories).length === 0 && (
        <p className="rounded-md border border-dashed px-4 py-3 text-sm text-muted-foreground">
          {(data.error as { message?: string } | null)?.message ?? "Not validated yet."}
        </p>
      )}
      {Object.entries(data.categories).map(([key, category]) => {
        const failed = category.checks.filter((c) => !c.passed).length;
        return (
          <Collapsible key={key} className="rounded-md border bg-card">
            <CollapsibleTrigger className="flex w-full cursor-pointer items-center justify-between gap-3 px-4 py-3 text-left">
              <span className="text-sm">{CATEGORY_LABELS[key] ?? key}</span>
              <span className="flex items-center gap-2">
                <span className="eyebrow">{category.checks.length} checks</span>
                {category.passed ? (
                  <Badge variant="outline" className="border-success/40 text-success">PASS</Badge>
                ) : (
                  <Badge variant="destructive">{failed} FAIL</Badge>
                )}
              </span>
            </CollapsibleTrigger>
            <CollapsibleContent>
              <ul className="divide-y border-t">
                {category.checks.map((check) => (
                  <li key={check.name} className="flex items-start justify-between gap-4 px-4 py-2">
                    <div className="min-w-0">
                      <p className="font-mono text-xs">{check.name}</p>
                      <p className="truncate text-xs text-muted-foreground" title={check.detail}>
                        {check.detail}
                      </p>
                    </div>
                    <span className={check.passed ? "eyebrow text-success" : "eyebrow text-destructive"}>
                      {check.passed ? "pass" : "fail"}
                    </span>
                  </li>
                ))}
              </ul>
            </CollapsibleContent>
          </Collapsible>
        );
      })}
      <p className="text-xs text-muted-foreground">{data.disclaimer}</p>
    </div>
  );
}
