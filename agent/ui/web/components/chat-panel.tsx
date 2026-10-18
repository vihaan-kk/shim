"use client";

import { useEffect, useRef, useState } from "react";
import ReactMarkdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { cn } from "@/lib/utils";
import type { AgentExampleGroup } from "@/lib/agent-examples";
import type { Pause, ToolResult } from "@/lib/types";

export interface TraceStep {
  name: string;
  args: Record<string, unknown>;
  result?: ToolResult;
}

export type ChatItem =
  | { id: string; role: "user" | "agent" | "question" | "error"; text: string; options?: string[] }
  | { id: string; role: "trace"; steps: TraceStep[] };

// Agent replies are Markdown (the model writes **bold**, lists, `code`).
// Render them with compact styles that match the panel instead of showing
// the raw markers. Raw HTML stays off (react-markdown default), and user
// messages are never rendered as Markdown.
const MARKDOWN_COMPONENTS: Components = {
  p: ({ children }) => <p className="mb-2 last:mb-0">{children}</p>,
  ul: ({ children }) => <ul className="my-2 list-disc space-y-1 pl-5 first:mt-0 last:mb-0">{children}</ul>,
  ol: ({ children }) => <ol className="my-2 list-decimal space-y-1 pl-5 first:mt-0 last:mb-0">{children}</ol>,
  li: ({ children }) => <li className="[&>p]:mb-0">{children}</li>,
  strong: ({ children }) => <strong className="font-semibold">{children}</strong>,
  a: ({ children, href }) => (
    <a href={href} target="_blank" rel="noreferrer" className="underline underline-offset-2">
      {children}
    </a>
  ),
  code: ({ children }) => (
    <code className="rounded bg-muted px-1 py-0.5 font-mono text-[0.85em]">{children}</code>
  ),
  pre: ({ children }) => (
    <pre className="my-2 overflow-x-auto rounded-md bg-secondary p-3 font-mono text-xs [&>code]:bg-transparent [&>code]:p-0">
      {children}
    </pre>
  ),
  h1: ({ children }) => <h1 className="mb-1 mt-3 text-base font-semibold first:mt-0">{children}</h1>,
  h2: ({ children }) => <h2 className="mb-1 mt-3 text-base font-semibold first:mt-0">{children}</h2>,
  h3: ({ children }) => <h3 className="mb-1 mt-3 font-semibold first:mt-0">{children}</h3>,
  h4: ({ children }) => <h4 className="mb-1 mt-3 font-semibold first:mt-0">{children}</h4>,
  blockquote: ({ children }) => (
    <blockquote className="my-2 border-l-2 pl-3 text-muted-foreground">{children}</blockquote>
  ),
  hr: () => <hr className="my-3" />,
  table: ({ children }) => (
    <div className="my-2 overflow-x-auto">
      <table className="w-full border-collapse text-xs">{children}</table>
    </div>
  ),
  th: ({ children }) => <th className="border px-1.5 py-1 text-left font-semibold">{children}</th>,
  td: ({ children }) => <td className="border px-1.5 py-1">{children}</td>,
};

function MessageMarkdown({ text }: { text: string }) {
  return (
    <div className="break-words">
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={MARKDOWN_COMPONENTS}>
        {text}
      </ReactMarkdown>
    </div>
  );
}

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
  examples,
  introduction,
}: {
  examples?: AgentExampleGroup[];
  introduction?: string;
  items: ChatItem[];
  pending: Pause | null;
  busy: boolean;
  onSend: (text: string) => void;
  onReviewConfirmation: () => void;
}) {
  const [draft, setDraft] = useState("");
  const scrollRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    if (scrollRef.current) scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
  }, [items.length]);

  const awaitingApproval = pending?.kind === "confirmation";
  // Choice buttons belong to the currently pending question only; once it is
  // answered (or an identical question was asked earlier) they disappear.
  const pendingQuestionIndex =
    pending?.kind === "question"
      ? items.findLastIndex((item) => item.role === "question" && item.text === pending.text)
      : -1;
  const submit = () => {
    const text = draft.trim();
    if (!text || busy || awaitingApproval) return;
    onSend(text);
    setDraft("");
  };

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div ref={scrollRef} className="min-h-0 flex-1 space-y-3 overflow-y-auto p-3" aria-live="polite">
        {items.length === 0 && (
          <p className="text-sm text-muted-foreground">
            {introduction ?? "Tell the agent what you would like to do."}
          </p>
        )}
        {examples && (
          <details open={items.length === 0} className="rounded-md border bg-secondary/40 p-2">
            <summary className="cursor-pointer text-xs">Example instructions · select to edit</summary>
            <p className="mt-2 text-xs text-muted-foreground">Choose an example, edit the message, then send.</p>
            <div className="mt-2 space-y-2">
              {examples.map((group, index) => (
                <details key={group.title} open={index === 0}>
                  <summary className="min-h-8 cursor-pointer py-1.5 text-xs font-medium">{group.title}</summary>
                  <div className="flex flex-wrap gap-2 pb-1">
                    {group.examples.map(example => (
                      <button key={example.label} type="button" disabled={busy || awaitingApproval}
                        aria-label={`${example.label}: ${example.prompt}`} title={example.prompt}
                        onClick={() => { setDraft(example.prompt); inputRef.current?.focus(); }}
                        className="min-h-9 rounded-full border bg-card px-3 py-2 text-left text-xs leading-relaxed hover:bg-accent focus-visible:outline-2 focus-visible:outline-offset-2 disabled:opacity-50">
                        {example.label}
                      </button>
                    ))}
                  </div>
                </details>
              ))}
            </div>
          </details>
        )}
        {items.map((item, itemIndex) =>
          item.role === "trace" ? (
            <ToolTrace key={item.id} steps={item.steps} />
          ) : (
            <div
              key={item.id}
              className={cn(
                "max-w-[90%] rounded-md px-3 py-2 text-sm leading-relaxed",
                item.role === "user" && "ml-auto bg-primary text-primary-foreground",
                item.role === "agent" && "bg-card ring-1 ring-border",
                item.role === "question" && "w-full max-w-[95%] bg-accent ring-1 ring-border",
                item.role === "error" && "bg-destructive/10 text-destructive",
              )}
            >
              {item.role === "question" && <span className="eyebrow mb-1 block">Agent asks</span>}
              {item.role === "agent" || item.role === "question" ? (
                <MessageMarkdown text={item.text} />
              ) : (
                <span className="whitespace-pre-wrap">{item.text}</span>
              )}
              {item.role === "question" && itemIndex === pendingQuestionIndex && item.options?.length ? (
                <div className="mt-3 grid gap-2">
                  <span className="eyebrow">Choose one, or type your own answer below</span>
                  {item.options.map((option) => (
                    <Button
                      key={option}
                      variant="outline"
                      disabled={busy}
                      onClick={() => onSend(option)}
                      className="h-auto justify-start whitespace-normal bg-card px-3 py-2 text-left text-sm"
                    >
                      {option}
                    </Button>
                  ))}
                </div>
              ) : null}
            </div>
          ),
        )}
        {busy && <p className="eyebrow animate-pulse">Agent is working…</p>}

      </div>

      <div className="shrink-0 border-t p-3">
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
              ref={inputRef}
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
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
