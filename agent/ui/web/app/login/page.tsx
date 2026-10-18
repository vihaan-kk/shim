"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { api } from "@/lib/api";

// Where to go after signing in: the page the visitor asked for, if it is on this site.
function nextPath(): string {
  const next = new URLSearchParams(window.location.search).get("next");
  return next && next.startsWith("/") && !next.startsWith("//") && next !== "/login" ? next : "/limb";
}

// Sign-in for the hosted demo. Caddy sends every signed-out request here.
export default function LoginPage() {
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!password || pending) return;
    setPending(true);
    setError(null);
    try {
      await api.login(password);
      // A full load, so the workbench session is fetched with the new sign-in.
      window.location.assign(nextPath());
    } catch (err) {
      setError((err as Error).message);
      setPending(false);
    }
  };

  return (
    <div className="grid min-h-0 flex-1 place-items-center overflow-y-auto py-8">
      <div className="grid w-full max-w-md gap-6">
        <div className="grid gap-2">
          <span className="eyebrow">Shim · demonstration workbench</span>
          <h1 className="text-[clamp(2rem,4vw,3rem)] leading-tight tracking-tight">Sign in</h1>
          <p className="text-sm leading-relaxed text-foreground/70">
            This hosted demo runs the agent, the CAD tools and a virtual printer. Enter the access password to continue.
          </p>
        </div>

        <form onSubmit={submit} className="grid gap-4 rounded-md border bg-card p-5" noValidate>
          <div className="grid gap-1.5">
            <Label htmlFor="password" className="text-xs">
              Password
            </Label>
            <Input
              id="password"
              type="password"
              autoComplete="current-password"
              autoFocus
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              aria-invalid={Boolean(error)}
              aria-describedby={error ? "login-error" : undefined}
              className="h-10"
            />
            {error && (
              <p id="login-error" role="alert" className="text-[11px] text-destructive">
                {error}
              </p>
            )}
          </div>
          <Button type="submit" disabled={!password || pending} className="h-11 justify-between rounded-full px-6">
            {pending ? "Signing in…" : "Sign in"}
            <span aria-hidden="true">↗</span>
          </Button>
        </form>

        <p className="eyebrow">Nonclinical demonstration · parts are not wearable</p>
      </div>
    </div>
  );
}
