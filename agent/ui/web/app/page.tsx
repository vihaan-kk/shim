import Link from "next/link";
import "./landing.css";

function Sketch({ kind }: { kind: "limb" | "socket" | "printer" }) {
  return (
    <svg viewBox="0 0 160 120" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" className="h-24 w-32 shrink-0 text-foreground/80" aria-hidden="true">
      {kind === "limb" ? <>
        <path d="M55 16c-3 22-2 50 3 70 3 14 12 20 24 19 14-1 20-12 21-25l5-63M55 17c15-8 37-8 53 0M54 19c17 7 36 8 53-1" />
        <path d="M60 23c-2 28 0 51 5 66M99 51l-3 31M57 50c13 6 34 7 48 0M60 78c12 6 26 6 40 1M40 18v84m-4-82 8-4m-8 88 8-4" opacity=".45" />
        <path d="m69 94 3 5m4-6 3 7m4-8 3 7" opacity=".3" />
      </> : kind === "socket" ? <>
        <path d="M47 29c9 7 18 13 32 12 15-1 25-12 35-16l-9 62c-2 17-12 23-27 20-13-2-20-10-22-23Z" />
        <path d="M47 29c-1-12 10-18 18-12 11 9 19 13 29 7 12-8 20-8 20 1M53 30c10 13 38 20 55-3M62 49l7 40c2 8 13 13 23 6l8-45M51 44l8 43c3 13 8 17 18 19" />
        <path d="m54 51 8 8m-6 1 8 8m-6 1 8 8m-6 1 8 8m34-37 6 6m-7 4 6 6m-8 4 6 6m-7 4 5 5" opacity=".35" />
      </> : <>
        <path d="M34 101V19h92v82ZM42 93V28h76v65ZM29 102h102v7H29ZM43 74h73M79 29v18l-5 8h12l-7-8M79 56v7" />
        <path d="M65 74v-8h29v8M62 79h35M60 84h39M58 89h42M37 22l85-1M36 98h88" opacity=".5" />
        <path d="M112 104h8" />
      </>}
    </svg>
  );
}

const steps = [
  { kind: "limb" as const, title: "Shape the limb", text: "Enter measurements or describe an adjustment. Review the updated residual limb in 3D." },
  { kind: "socket" as const, title: "Build the socket", text: "Confirm the limb. The agent coordinates CAD tools to generate and refine its socket shell." },
  { kind: "printer" as const, title: "Prepare a virtual print", text: "Review the result, slice the shell, and approve the virtual print. Ask the agent for progress." },
];

export default function LandingPage() {
  return (
    <div className="landing-page">
      <section className="landing-hero" aria-labelledby="intro-title">
        <div className="flex flex-col items-start gap-5">
          <h1 id="intro-title" className="landing-title">Your words.<br />The right tools.<br /><span className="text-muted-foreground">A tangible next step.</span></h1>
          <p className="max-w-lg text-base leading-relaxed text-foreground/70">Meet Shim, a tool-calling agent that turns your instructions into measurement updates, socket geometry, and a virtual print. You guide the process. Shim connects the tools.</p>
          <Link href="/limb" className="inline-flex min-h-12 items-center gap-8 rounded-full bg-primary px-6 py-3 text-sm text-primary-foreground transition-colors hover:bg-primary/85 focus-visible:outline-2 focus-visible:outline-offset-4">Start with your measurements <span aria-hidden="true">↗</span></Link>
        </div>
        <div className="rounded-md border bg-card p-5 sm:p-6" aria-label="Illustrative example of the agent calling a tool">
          <div className="mb-6 flex items-center justify-between gap-3"><span className="eyebrow">From instruction to action</span><span className="eyebrow">Example</span></div>
          <blockquote className="ml-5 rounded-md border bg-background p-4 text-lg leading-snug">“Change only the proximal circumference to 310 mm.”</blockquote>
          <div className="ml-9 h-6 border-l border-dashed" aria-hidden="true" />
          <div className="border-l-2 border-foreground pl-4">
            <p className="mb-2 text-sm font-medium">Shim chooses the measurement tool</p>
            <p className="text-sm leading-relaxed text-muted-foreground">It passes the requested value to the tool, which updates the model and returns the result.</p>
            <p className="eyebrow mt-3 rounded-sm bg-muted px-3 py-2">Proximal circumference → 310 mm</p>
          </div>
          <div className="ml-9 h-6 border-l border-dashed" aria-hidden="true" />
          <p className="text-sm leading-relaxed"><span className="mr-2" aria-hidden="true">↳</span> Review the new 3D revision. Keep refining in the same conversation.</p>
          <p className="mt-5 border-t pt-4 text-xs leading-relaxed text-muted-foreground">Tools make the changes. You confirm each stage and approve the print.</p>
        </div>
      </section>
      <section aria-label="How it works" className="border-t pt-4">
        <ol className="grid gap-5 md:grid-cols-3">
          {steps.map((step, i) => <li key={step.kind} className="flex items-center gap-3"><Sketch kind={step.kind} /><div><p className="eyebrow mb-1">0{i + 1}</p><h3 className="mb-1 text-lg tracking-tight">{step.title}</h3><p className="text-sm leading-relaxed text-muted-foreground">{step.text}</p></div></li>)}
        </ol>
      </section>
    </div>
  );
}
