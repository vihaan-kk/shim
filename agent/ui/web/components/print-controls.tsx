"use client";

import { Button } from "@/components/ui/button";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import {
  AlertDialog,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import type { Pause, PreparedJob, PrinterStatus, ToolResult } from "@/lib/types";

const minutes = (s: number | null | undefined) => (s == null ? "—" : `${Math.round(s / 60)} min`);

// ----- print bar -----

export function PrintBar({
  printer,
  job,
  pending,
  onApprovePrint,
}: {
  printer: ToolResult<PrinterStatus> | null;
  job: PreparedJob | null;
  pending: Pause | null;
  onApprovePrint: () => void;
}) {
  const ready = printer?.status === "success" && printer.data.ready;
  const startRequested = pending?.kind === "confirmation" && pending.details.action === "start_print";
  const canApprove = Boolean(ready && job && startRequested);
  const why = !ready
    ? "Printer is not ready"
    : !job
      ? "Nothing sliced yet"
      : !startRequested
        ? "The agent has not asked to start a print"
        : "";

  return (
    <div className="grid gap-3">
      <dl className="grid grid-cols-2 gap-x-4 gap-y-2 text-sm break-words sm:grid-cols-4">
        <div>
          <dt className="eyebrow">Printer</dt>
          <dd>
            {printer == null ? "…" : printer.status === "success" ? printer.data.connection : "Unreachable"}
            {printer?.status === "success" && printer.data.port ? (
              <span className="eyebrow ml-2">{printer.data.port}</span>
            ) : null}
          </dd>
        </div>
        <div>
          <dt className="eyebrow">Slice</dt>
          <dd className="font-mono">{job ? job.job_id : "not sliced"}</dd>
        </div>
        <div>
          <dt className="eyebrow">Estimate</dt>
          <dd>{job ? minutes(job.estimated_seconds) : "—"}</dd>
        </div>
        <div>
          <dt className="eyebrow">Filament</dt>
          <dd>{job?.filament_m != null ? `${job.filament_m} m` : "—"}</dd>
        </div>
      </dl>

      <div className="flex flex-wrap gap-2">
        <Tooltip>
          <TooltipTrigger render={<span tabIndex={0} />}>
            <Button variant="outline" disabled className="h-10 rounded-full px-5">
              Approve slice
            </Button>
          </TooltipTrigger>
          <TooltipContent>
            The backend has no slice confirmation yet (CONFIRMABLE_ACTIONS is start_print only).
          </TooltipContent>
        </Tooltip>
        <Tooltip>
          <TooltipTrigger render={<span tabIndex={0} />}>
            <Button disabled={!canApprove} onClick={onApprovePrint} className="h-10 rounded-full px-5">
              Approve print
            </Button>
          </TooltipTrigger>
          {!canApprove && <TooltipContent>{why}</TooltipContent>}
        </Tooltip>
      </div>
    </div>
  );
}

// ----- confirmation dialog -----

export function ConfirmDialog({
  open,
  pending,
  onDecide,
  onOpenChange,
}: {
  open: boolean;
  pending: Pause | null;
  onDecide: (approved: boolean) => void;
  onOpenChange: (open: boolean) => void;
}) {
  return (
    <AlertDialog open={open} onOpenChange={onOpenChange}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>Approve {pending?.details.action?.replace("_", " ")}?</AlertDialogTitle>
          <AlertDialogDescription>
            {pending?.text}
            <span className="eyebrow mt-3 block">
              Target {pending?.details.subject} · one-time approval · virtual printer only
            </span>
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel className="rounded-full" onClick={() => onDecide(false)}>
            Decline
          </AlertDialogCancel>
          <Button className="rounded-full px-5" onClick={() => onDecide(true)}>
            Approve and start
          </Button>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
