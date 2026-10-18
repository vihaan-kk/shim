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
  { href: "/", label: "Residual limb" },
  { href: "/socket", label: "Socket" },
  { href: "/printer", label: "Printer" },
] as const;

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const session = useSession();
  const unlocked = [true, session.limbConfirmed, session.socketConfirmed];

  return (
    <div className="flex min-h-screen flex-col">
      <header className="relative overflow-hidden border-b">
        <HeaderDots className="pointer-events-none absolute inset-0 h-full w-full opacity-70" />
        <div className="relative mx-auto flex w-full max-w-[1400px] flex-wrap items-center justify-between gap-4 px-4 py-4 sm:px-8">
          <Link href="/" className="text-lg">
            Shim<span className="eyebrow ml-1 align-super">demo</span>
          </Link>
          <nav aria-label="Session steps" className="order-3 flex w-full gap-1 sm:order-none sm:w-auto">
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
          </nav>
          <span />
        </div>
      </header>

      <div className="mx-auto w-full max-w-[1400px] flex-1 px-4 py-8 sm:px-8">{children}</div>

      <footer className="eyebrow mx-auto w-full max-w-[1400px] px-4 py-6 sm:px-8">
        Nonclinical demonstration · synthetic parametric limb · checks are CAD checks, not fit, comfort or
        safety · parts are not wearable
      </footer>

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
    <div className="mb-8 flex flex-wrap items-end justify-between gap-4">
      <div className="grid max-w-2xl gap-2">
        <span className="eyebrow">{step}</span>
        <h1 className="display-2">{title}</h1>
        <p className="text-foreground/70">{description}</p>
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
