"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { HeaderDots } from "@/components/header-dots";
import { ConfirmDialog } from "@/components/print-controls";
import { api } from "@/lib/api";
import { useSession } from "@/lib/session";
import { cn } from "@/lib/utils";

const STEPS = [
  { href: "/limb", label: "Residual limb" },
  { href: "/socket", label: "Socket" },
  { href: "/printer", label: "Printer" },
] as const;

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const session = useSession();
  const unlocked = [true, session.limbConfirmed, session.socketConfirmed];

  return (
    <div className="flex h-dvh min-h-0 flex-col overflow-hidden">
      <header className="relative shrink-0 overflow-hidden border-b">
        <HeaderDots className="pointer-events-none absolute inset-0 h-full w-full opacity-70" />
        <div className="relative mx-auto flex w-full max-w-[1400px] flex-wrap items-center justify-between gap-2 px-4 py-2 sm:px-6">
          <Link href="/" className="text-lg">
            Shim
          </Link>
          {pathname === "/login" ? <span /> : pathname === "/" ? <Link href="/limb" className="rounded-full border px-4 py-2 text-sm hover:bg-muted">Open workbench ↗</Link> : <nav aria-label="Session steps" className="order-3 flex w-full gap-1 sm:order-none sm:w-auto">
            {STEPS.map((step, i) => {
              const active = pathname === step.href;
              const className = cn(
                "flex items-center gap-2 rounded-full px-3 py-1.5 text-sm transition-colors",
                active ? "bg-primary text-primary-foreground" : "text-foreground/70",
                !active && unlocked[i] && "hover:bg-muted",
                !unlocked[i] && "pointer-events-none opacity-40",
              );
              const content = (
                <>
                  <span className="font-mono text-xs">{String(i + 1).padStart(2, "0")}</span>
                  {step.label}
                </>
              );
              return unlocked[i] ? (
                <Link key={step.href} href={step.href} className={className} aria-current={active ? "page" : undefined}>
                  {content}
                </Link>
              ) : (
                <span key={step.href} className={className} aria-disabled>
                  {content}
                </span>
              );
            })}
          </nav>}
          {api.isMock ? <Badge variant="secondary">Mock data</Badge> : <span />}
        </div>
      </header>

      <main className="workbench-main mx-auto flex min-h-0 w-full max-w-[1600px] flex-1 flex-col overflow-hidden px-4 py-3 sm:px-6">{children}</main>

      <ConfirmDialog
        open={session.dialogOpen}
        pending={session.pending}
        onDecide={session.decide}
        onOpenChange={session.setDialogOpen}
      />
    </div>
  );
}

// Page heading shared by the three pages: step label, big title, Confirm on the right.
export function PageHeading({
  step,
  title,
  description,
  action,
}: {
  step: string;
  title: string;
  description: string;
  action?: React.ReactNode;
}) {
  return (
    <div className="page-heading mb-3 flex shrink-0 flex-wrap items-end justify-between gap-2">
      <div className="grid max-w-2xl gap-1">
        <h1 className="text-[clamp(1.5rem,3vw,2.25rem)] leading-tight tracking-tight">{step}: {title}</h1>
        <p className="text-sm text-foreground/70">{description}</p>
      </div>
      {action}
    </div>
  );
}

export function ConfirmButton({
  children,
  disabled,
  pending,
  onClick,
  hint,
}: {
  children: React.ReactNode;
  disabled: boolean;
  pending: boolean;
  onClick: () => void;
  hint?: string;
}) {
  return (
    <div className="grid justify-items-end gap-1.5">
      <Button className="h-11 rounded-full px-6" disabled={disabled || pending} onClick={onClick}>
        {pending ? "Working…" : children}
      </Button>
      {hint && <span className="eyebrow">{hint}</span>}
    </div>
  );
}
