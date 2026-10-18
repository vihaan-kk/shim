"use client";

import dynamic from "next/dynamic";
import { useState } from "react";
import { engravingUrl, lowerLegUrl } from "@/lib/lower-leg";
import { useSession } from "@/lib/session";

const StlViewer = dynamic(() => import("@/components/stl-viewer").then((m) => m.StlViewer), {
  ssr: false,
  loading: () => <div className="eyebrow grid h-full place-items-center">Loading viewer…</div>,
});

// The confirmed socket with the limb seated and, optionally, the standard
// adapter, pylon and foot under it. Visualization only: only the socket prints.
export function ProsthesisPreview() {
  const { socket, limb } = useSession();
  const [showLowerLeg, setShowLowerLeg] = useState(true);
  if (!socket || !limb) return null;
  const matchingLimb = limb.revision_id === socket.socket.limb_revision_id ? limb : null;

  return (
    <div className="grid gap-2">
      <div className="flex flex-wrap items-baseline justify-between gap-3">
        <span className="eyebrow">Full prosthesis · visualization only</span>
        <label className="flex cursor-pointer items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={showLowerLeg}
            onChange={(event) => setShowLowerLeg(event.target.checked)}
            className="size-4 accent-primary focus-visible:outline-2 focus-visible:outline-offset-4"
          />
          Show lower leg
        </label>
      </div>
      <div className="h-[360px] overflow-hidden rounded-md border">
        <StlViewer
          url={socket.socket.stl_url}
          shell
          limbUrl={matchingLimb?.stl_url}
          showLimb={Boolean(matchingLimb)}
          insertion={100}
          measuredGeometry
          lowerLegUrl={lowerLegUrl(socket.socket.stl_url)}
          showLowerLeg={showLowerLeg}
          engravingUrl={engravingUrl(socket.socket.stl_url)}
          label={`Socket ${socket.socket.socket_id} with the limb seated${showLowerLeg ? ", above the standard adapter, pylon and foot" : ""}`}
        />
      </div>
      <p className="text-[11px] text-muted-foreground">
        Only the socket is sliced and printed. The adapter, pylon and foot are standard demonstration parts shown for
        context.
      </p>
    </div>
  );
}
