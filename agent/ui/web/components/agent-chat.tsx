"use client";

import { ChatPanel } from "@/components/chat-panel";
import { useSession } from "@/lib/session";
import { cn } from "@/lib/utils";

// The same agent on every page (README §13). The conversation lives in the
// session, so it carries over between the limb, socket and printer pages.
export function AgentChat({ className }: { className?: string }) {
  const session = useSession();
  return (
    <div className={cn("flex min-h-0 flex-col overflow-hidden rounded-md border bg-card", className)}>
      <div className="flex items-center justify-between border-b px-4 py-3">
        <span className="text-sm">Agent</span>
        <span className="eyebrow">Nemotron 3.5 Lightning · vLLM</span>
      </div>
      <ChatPanel
        items={session.items}
        pending={session.pending}
        busy={session.busy}
        onSend={session.send}
        onReviewConfirmation={() => session.setDialogOpen(true)}
      />
    </div>
  );
}
