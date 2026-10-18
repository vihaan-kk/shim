"use client";

import Link from "next/link";
import { AgentChat } from "@/components/agent-chat";
import { PageHeading } from "@/components/app-shell";
import { LayerView } from "@/components/layer-view";
import { PrintBar } from "@/components/print-controls";
import { PrintPanel } from "@/components/print-panel";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";
import { useSession } from "@/lib/session";

// README §13, page 3: the virtual job's metadata from the server poll, the
// separate slice and print controls, the same agent, and the report.
export default function PrinterPage() {
  const session = useSession();

  if (!session.socketConfirmed) {
    return (
      <div className="grid gap-3 py-16">
        <span className="eyebrow">Step 3 of 3</span>
        <h1 className="display-2">Virtual printer</h1>
        <p className="text-foreground/70">Confirm the socket first. Only a confirmed socket can be sliced and printed.</p>
        <Link href={session.limbConfirmed ? "/socket" : "/"} className="text-sm underline underline-offset-4">
          ← Back
        </Link>
      </div>
    );
  }

  return (
    <>
      <PageHeading
        step="Step 3 of 3"
        title="Virtual printer"
        description="Ask the agent to slice and print. Nothing starts without your approval, and every number here is read back from the printer."
      />
      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_440px]">
        <div className="grid content-start gap-6">
          <section aria-label="Print actions" className="rounded-md border bg-card p-5">
            <PrintBar
              printer={session.printer}
              job={session.job}
              pending={session.pending}
              onApprovePrint={() => session.setDialogOpen(true)}
            />
          </section>
          <section aria-label="Job" className="rounded-md bg-primary p-1">
            <div className="rounded-[calc(var(--radius)-1px)] bg-background p-5">
              <PrintPanel />
            </div>
          </section>
          {session.started && (
            <section aria-label="Live layer view" className="rounded-md border bg-card p-5">
              <LayerView />
            </section>
          )}
          <div className="flex flex-wrap gap-3">
            <Button variant="outline" className="h-10 rounded-full px-5" onClick={session.downloadReport}>
              Download report
            </Button>
            {api.isMock && api.simulateLinkLoss && session.started && (
              <Button variant="ghost" className="h-10 rounded-full px-5" onClick={() => api.simulateLinkLoss?.()}>
                Demo: simulate link loss
              </Button>
            )}
          </div>
        </div>
        <AgentChat className="h-[600px] lg:h-[calc(100vh-15rem)] lg:min-h-[560px]" />
      </div>
    </>
  );
}
