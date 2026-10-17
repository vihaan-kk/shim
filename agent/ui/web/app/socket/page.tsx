"use client";

import dynamic from "next/dynamic";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { AgentChat } from "@/components/agent-chat";
import { ConfirmButton, PageHeading } from "@/components/app-shell";
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
            disabled={!bundle.validation.passed}
            pending={session.confirmingSocket}
            onClick={confirm}
            hint={bundle.validation.passed ? `Confirms ${bundle.socket.socket_id}` : "Geometric checks must pass"}
          >
            Confirm socket →
          </ConfirmButton>
        }
      />
      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_440px]">
        <section aria-label="Socket shell" className="grid gap-2">
          <div className="flex items-baseline justify-between">
            <h2 className="text-base">Socket shell</h2>
            <span className="eyebrow">{bundle.socket.socket_id}</span>
          </div>
          <div className="h-[420px] overflow-hidden rounded-md border lg:h-[calc(100vh-15rem)] lg:min-h-[560px]">
            <StlViewer url={bundle.socket.stl_url} color="#a89c92" label="Socket shell 3D view" />
          </div>
        </section>
        <div className="grid content-start gap-4">
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
