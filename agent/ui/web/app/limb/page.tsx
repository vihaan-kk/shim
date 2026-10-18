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
            disabled={!session.requiredFilled || !session.limb || session.measurementsDirty || session.applying || session.busy}
            pending={session.confirmingLimb}
            onClick={confirm}
            hint={session.measurementsDirty ? "Apply your measurements before continuing" : session.requiredFilled ? `Confirms limb ${session.limb?.revision_id ?? "…"}` : "Fill length, P and D to confirm"}
          >
            Confirm limb →
          </ConfirmButton>
        }
      />
      <div className="workspace-grid">
        <div className="workspace-sidebar">
        <section aria-labelledby="limb-viewer-heading" className="workspace-viewer">
          <h2 id="limb-viewer-heading" className="eyebrow">Transtibial Residual Limb 3D demonstration</h2>
          <div className="viewer-canvas">
            {session.loadError ? (
              <div className="grid h-full place-items-center p-6 text-center text-sm text-destructive">
                Could not load the session: {session.loadError}
              </div>
            ) : session.limb ? (
              <StlViewer
              url={session.limb.stl_url}
              skin
              label="Transtibial Residual Limb 3D demonstration"
              annotations={{
                lengthMm: session.appliedMeasurements.length_mm,
                stations: [
                  { label: "P", zMm: 40, circumferenceMm: session.appliedMeasurements.proximal_circumference_mm },
                  {
                    label: "M",
                    zMm: (session.appliedMeasurements.length_mm ?? 140) / 2,
                    circumferenceMm: session.appliedMeasurements.mid_circumference_mm,
                  },
                  {
                    label: "D",
                    zMm: (session.appliedMeasurements.length_mm ?? 140) - 40,
                    circumferenceMm: session.appliedMeasurements.distal_circumference_mm,
                  },
                ],
              }}
            />
            ) : (
              <div className="eyebrow grid h-full place-items-center">Loading session…</div>
            )}
          </div>
        </section>
          <MeasurementProfile />
        </div>
        <AgentChat className="workspace-agent" />
      </div>
    </>
  );
}
