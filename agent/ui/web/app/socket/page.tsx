"use client";

import dynamic from "next/dynamic";
import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { AgentChat } from "@/components/agent-chat";
import { ConfirmButton, PageHeading } from "@/components/app-shell";
import { Button } from "@/components/ui/button";
import { ValidationList } from "@/components/validation-list";
import { useSession } from "@/lib/session";

const StlViewer = dynamic(() => import("@/components/stl-viewer").then((m) => m.StlViewer), {
  ssr: false,
  loading: () => <div className="eyebrow grid h-full place-items-center">Loading viewer…</div>,
});

// README §13, page 2: the socket shell for the confirmed limb, its geometric
// checks, the same agent, and Confirm.
export default function SocketPage() {
  const router = useRouter();
  const session = useSession();
  const bundle = session.socket;
  const [showLimb, setShowLimb] = useState(true);
  const [measuredGeometry, setMeasuredGeometry] = useState(true);
  const [insertion, setInsertion] = useState(0);
  const [revealInterior, setRevealInterior] = useState(false);
  const matchingLimb = session.limb?.revision_id === bundle?.socket.limb_revision_id ? session.limb : null;
  const limbVisible = showLimb && Boolean(matchingLimb);

  if (!bundle) {
    return (
      <div className="grid gap-3 py-16">
        <span className="eyebrow">Step 2 of 3</span>
        <h1 className="display-2">Socket shell</h1>
        <p className="text-foreground/70">Confirm the residual limb first. The socket is built from that revision.</p>
        <Link href="/" className="text-sm underline underline-offset-4">
          ← Back to the residual limb
        </Link>
      </div>
    );
  }

  const confirm = async () => {
    if (await session.confirmSocket()) router.push("/printer");
  };

  return (
    <>
      <PageHeading
        step="Step 2 of 3"
        title="Socket shell"
        description={`Demonstration shell built around limb ${bundle.socket.limb_revision_id}. Ask the agent for a supported change, such as wall thickness or depth. The limb file is unchanged.`}
        action={
          <ConfirmButton
            disabled={!bundle.validation.passed || !matchingLimb}
            pending={session.confirmingSocket}
            onClick={confirm}
            hint={!matchingLimb ? "Reconfirm the current limb to rebuild a matching socket" : bundle.validation.passed ? `Confirms ${bundle.socket.socket_id}` : "Geometric checks must pass"}
          >
            Confirm socket →
          </ConfirmButton>
        }
      />
      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_440px]">
        <section aria-labelledby="socket-viewer-heading" className="grid content-start gap-1">
          <h2 id="socket-viewer-heading" className="eyebrow">Socket shell 3D Demonstration</h2>
          <fieldset className="my-2 grid gap-2 rounded-md border bg-card px-3 py-2" disabled={!matchingLimb}>
            <legend className="sr-only">Assembly demonstration controls</legend>
            <div className="flex flex-wrap items-center gap-x-5 gap-y-1">
              <label className="flex min-h-11 cursor-pointer items-center gap-2 text-sm">
                <input type="checkbox" checked={limbVisible} onChange={(event) => setShowLimb(event.target.checked)}
                  className="size-4 accent-primary focus-visible:outline-2 focus-visible:outline-offset-4" />
                Show limb
              </label>
              <label className="flex min-h-11 cursor-pointer items-center gap-2 text-sm">
                <input type="checkbox" checked={revealInterior} onChange={(event) => setRevealInterior(event.target.checked)}
                  className="size-4 accent-primary focus-visible:outline-2 focus-visible:outline-offset-4" />
                Reveal interior
              </label>
              <label className="flex min-h-11 cursor-pointer items-center gap-2 text-sm">
                <input type="checkbox" checked={measuredGeometry} onChange={(event) => setMeasuredGeometry(event.target.checked)}
                  className="size-4 accent-primary focus-visible:outline-2 focus-visible:outline-offset-4" />
                Use measured geometry
              </label>
              <Button type="button" variant="outline" className="min-h-11 rounded-full" disabled={!limbVisible}
                onClick={() => setInsertion(insertion === 100 ? 0 : 100)}>
                {insertion === 100 ? "Separate parts" : "Seat limb"}
              </Button>
            </div>
            <div className="grid gap-1">
              <label htmlFor="limb-insertion" className="flex justify-between text-xs">
                <span>Insertion</span><span>{insertion === 0 ? "Separated" : insertion === 100 ? "Seated" : `${insertion}%`}</span>
              </label>
              <input id="limb-insertion" type="range" min="0" max="100" step="1" value={insertion}
                disabled={!limbVisible} onChange={(event) => setInsertion(Number(event.target.value))}
                aria-describedby="socket-view-mode"
                aria-valuetext={insertion === 0 ? "Separated" : insertion === 100 ? "Seated in shared model coordinates" : `${insertion}% inserted`}
                className="h-6 w-full accent-primary focus-visible:outline-2 focus-visible:outline-offset-4" />
            </div>
          </fieldset>
          <p id="socket-view-mode" className="mb-2 text-xs text-muted-foreground" aria-live="polite">
            {!matchingLimb ? "Matching confirmed limb unavailable." : !showLimb ? "Limb hidden. Socket and viewing position are unchanged." : insertion === 100 ? "Limb seated. Reveal interior to inspect the relationship between the models." : "Move the slider or select Seat limb to bring the aligned models together."}
          </p>
          <div className="h-[420px] overflow-hidden rounded-md border lg:h-[calc(100vh-15rem)] lg:min-h-[560px]">
            <StlViewer
              url={bundle.socket.stl_url}
              shell
              limbUrl={matchingLimb?.stl_url}
              showLimb={limbVisible}
              insertion={insertion}
              revealInterior={revealInterior}
              measuredGeometry={measuredGeometry}
              socketMeasurements={bundle.validation.measurements}
              label={limbVisible ? `Confirmed residual limb and generated socket: ${insertion === 100 ? "seated" : "separated"}${revealInterior ? ", transparent socket" : ""}` : "Generated socket with residual limb hidden"}
            />
          </div>
          <p className="mt-2 text-xs text-muted-foreground">
            {bundle.validation.measurements?.units !== "mm" ? "Socket measurements not reported." : measuredGeometry ? "Rings show outer socket circumferences; the vertical line shows depth." : "Enable measured geometry to show socket dimensions."}
            {process.env.NEXT_PUBLIC_USE_MOCK !== "0" && " Recorded mock measurements."}
          </p>
          <ul className="sr-only" aria-label="Reported socket circumferences">
            {(bundle.validation.measurements?.sections ?? []).filter(row => row.status === "measured").map(row => (
              <li key={row.id}>{row.id}, {row.z_mm} mm below the opening: outer circumference {Number.isFinite(row.outer_perimeter_mm) ? `${row.outer_perimeter_mm.toFixed(1)} millimetres` : "not reported"}.</li>
            ))}
          </ul>
          <p className="mt-2 text-xs text-muted-foreground">
            {measuredGeometry ? "Measured geometry: original backend mesh dimensions, with decorative surface materials." : "Illustrative contours: the natural curve and tip taper alter the displayed surface. Use measured geometry to inspect dimensions."}
            {" "}This is not a clinical fit or insertion clearance test.
          </p>
        </section>
        <div className="grid min-w-0 content-start gap-4">
          <div className="grid max-h-[420px] gap-3 overflow-y-auto rounded-md border bg-card p-4">
            <h2 className="text-base">Geometric checks</h2>
            <ValidationList data={bundle.validation} />
          </div>
          <AgentChat className="h-[440px]" />
        </div>
      </div>
    </>
  );
}
