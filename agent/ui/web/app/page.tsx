"use client";

import dynamic from "next/dynamic";
import { useRouter } from "next/navigation";
import { AgentChat } from "@/components/agent-chat";
import { ConfirmButton, PageHeading } from "@/components/app-shell";
import { MeasurementProfile } from "@/components/measurement-profile";
import { useSession } from "@/lib/session";

const StlViewer = dynamic(() => import("@/components/stl-viewer").then((m) => m.StlViewer), {
  ssr: false,
  loading: () => <div className="eyebrow grid h-full place-items-center">Loading viewer…</div>,
});

// README §13, page 1: the standardized limb on the left, the measurement
// profile above the agent chat on the right, and Confirm.
export default function ResidualLimbPage() {
  const router = useRouter();
  const session = useSession();

  const confirm = async () => {
    if (await session.confirmLimb()) router.push("/socket");
  };

  return (
    <>
      <PageHeading
        step="Step 1 of 3"
        title="Residual limb"
        description="The standardized transtibial shape is loaded. Set the measurements here or tell the agent, then confirm the limb to build its socket."
        action={
          <ConfirmButton
            disabled={!session.requiredFilled || !session.limb}
            pending={session.confirmingLimb}
            onClick={confirm}
            hint={session.requiredFilled ? `Confirms limb ${session.limb?.revision_id ?? "…"}` : "Fill length, P and D to confirm"}
          >
            Confirm limb →
          </ConfirmButton>
        }
      />
      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_440px]">
        <section aria-label="Residual limb" className="grid gap-2">
          <div className="flex items-baseline justify-between">
            <h2 className="text-base">Residual limb</h2>
            <span className="eyebrow">Revision {session.limb?.revision_id ?? "…"}</span>
          </div>
          <div className="h-[420px] overflow-hidden rounded-md border lg:h-[calc(100vh-15rem)] lg:min-h-[560px]">
            {session.loadError ? (
              <div className="grid h-full place-items-center p-6 text-center text-sm text-destructive">
                Could not load the session: {session.loadError}
              </div>
            ) : session.limb ? (
              <StlViewer url={session.limb.stl_url} label="Residual limb 3D view" />
            ) : (
              <div className="eyebrow grid h-full place-items-center">Loading session…</div>
            )}
          </div>
        </section>
        <div className="grid content-start gap-4">
          <MeasurementProfile />
          <AgentChat className="h-[440px]" />
        </div>
      </div>
    </>
  );
}
