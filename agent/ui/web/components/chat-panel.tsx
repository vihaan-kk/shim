"use client";

import { useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { cn } from "@/lib/utils";
import type { Pause, ToolResult } from "@/lib/types";

export interface TraceStep {
  name: string;
  args: Record<string, unknown>;
  result?: ToolResult;
}

export type ChatItem =
  | { id: string; role: "user" | "agent" | "question" | "error"; text: string }
  | { id: string; role: "trace"; steps: TraceStep[] };

const STATUS_STYLE: Record<string, string> = {
  success: "text-success",
  fixable: "text-warning",
  fatal: "text-destructive",
};

function ToolTrace({ steps }: { steps: TraceStep[] }) {
  return (
    <Collapsible defaultOpen className="rounded-md border border-dashed bg-secondary/60">
      <CollapsibleTrigger className="eyebrow flex w-full cursor-pointer items-center justify-between px-3 py-2">
        <span>Tool calls · {steps.length}</span>
        <span>{steps.map((s) => s.name).join(" → ")}</span>
      </CollapsibleTrigger>
      <CollapsibleContent>
        <ol className="grid gap-2 border-t border-dashed px-3 py-2">
          {steps.map((step, i) => (
            <li key={i} className="grid gap-0.5 font-mono text-xs">
              <span>
                → {step.name}({Object.keys(step.args).length ? JSON.stringify(step.args) : ""})
              </span>
              {step.result ? (
                <span className={STATUS_STYLE[step.result.status]}>
                  ← {step.result.status}
                  {step.result.error ? ` [${step.result.error.code}]` : ""}: {step.result.message}
                </span>
              ) : (
                <span className="text-muted-foreground">← waiting for the person</span>
              )}
            </li>
          ))}
        </ol>
      </CollapsibleContent>
    </Collapsible>
  );
}

export function ChatPanel({
  items,
  pending,
  busy,
  onSend,
  onReviewConfirmation,
}: {
  items: ChatItem[];
  pending: Pause | null;
  busy: boolean;
  onSend: (text: string) => void;
  onReviewConfirmation: () => void;
}) {
  const [draft, setDraft] = useState("");
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }, [items.length]);

  const awaitingApproval = pending?.kind === "confirmation";
  const submit = () => {
    const text = draft.trim();
    if (!text || busy || awaitingApproval) return;
    onSend(text);
    setDraft("");
  };

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="flex-1 space-y-3 overflow-y-auto p-4" aria-live="polite">
        {items.length === 0 && (
          <p className="text-sm text-muted-foreground">
            Ask the agent to check the printer, or to slice and print the current socket.
          </p>
        )}
        {items.map((item) =>
          item.role === "trace" ? (
            <ToolTrace key={item.id} steps={item.steps} />
          ) : (
            <div
              key={item.id}
              className={cn(
                "max-w-[90%] rounded-md px-3 py-2 text-sm leading-relaxed",
                item.role === "user" && "ml-auto bg-primary text-primary-foreground",
                item.role === "agent" && "bg-card ring-1 ring-border",
                item.role === "question" && "bg-accent ring-1 ring-border",
                item.role === "error" && "bg-destructive/10 text-destructive",
              )}
            >
              {item.role === "question" && <span className="eyebrow mb-1 block">Agent asks</span>}
              {item.text}
            </div>
          ),
        )}
        {busy && <p className="eyebrow animate-pulse">Agent is working…</p>}
        <div ref={endRef} />
      </div>

      <div className="border-t p-3">
        {awaitingApproval ? (
          <div className="flex items-center justify-between gap-3 rounded-md bg-accent px-3 py-2">
            <span className="text-sm">The agent is waiting for your approval.</span>
            <Button size="sm" className="rounded-full px-4" onClick={onReviewConfirmation}>
              Review
            </Button>
          </div>
        ) : (
          <div className="flex items-end gap-2">
            <Textarea
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  submit();
                }
              }}
              placeholder={pending?.kind === "question" ? "Answer the agent…" : "Message the agent…"}
              aria-label="Message the agent"
              rows={2}
              className="min-h-0 resize-none"
            />
            <Button onClick={submit} disabled={busy || !draft.trim()} className="h-10 rounded-full px-5">
              Send
            </Button>
          </div>
        )}
      </div>
    </div>
  );
}
