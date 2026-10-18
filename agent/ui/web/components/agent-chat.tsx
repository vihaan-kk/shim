"use client";

import { usePathname } from "next/navigation";
import { ChatPanel } from "@/components/chat-panel";
import { useSession } from "@/lib/session";
import { STAGE_GUIDANCE } from "@/lib/agent-examples";
import { cn } from "@/lib/utils";

// The same agent on every page (README §13). The conversation lives in the
// session, so it carries over between the limb, socket and printer pages.
export function AgentChat({ className }: { className?: string }) {
  const session = useSession();
  const pathname = usePathname();
  const guidance = STAGE_GUIDANCE[pathname] ?? STAGE_GUIDANCE["/limb"];

  return (
    <div className={cn("flex min-h-0 flex-col overflow-hidden rounded-md border bg-card", className)}>
      <div className="flex shrink-0 flex-wrap items-center justify-between gap-1 border-b px-3 py-2">
        <span className="text-sm">Agent</span>
        <span className="eyebrow">Nemotron 3.5 Lightning · vLLM</span>
      </div>
      <ChatPanel
        examples={guidance.groups}
        introduction={guidance.intro}
        items={session.items}
        pending={session.pending}
        busy={session.busy}
        onSend={session.send}
        onReviewConfirmation={() => session.setDialogOpen(true)}
      />
    </div>
  );
}
