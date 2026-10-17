# Demo video script

Target length: about 4 minutes. Everything in [brackets] must be filled in or confirmed before recording. Roles are a guess; swap if wrong.

Every statistic has a source shown as a small caption on screen. Sources are listed at the end.

## 1. Team intro (0:00–0:25), everyone, one line each

> **[You]:** Hi, we're [team name], in the tool-calling track. I built the agent: the loop that lets the model pick tools and recover from errors.
> **[Teammate 2]:** I built [the geometry and CAD tools that make the part].
> **[Teammate 3]:** And I set up [the slicer and the virtual printer]. Here's what we made.

## 2. The hook (0:25–1:00), [You]

> Making a prosthetic socket the traditional way takes about eight hours of manual labor. At the median prosthetist wage, that's roughly three hundred dollars of labor per socket. And the need is growing: 1.6 million Americans were living with limb loss in 2005, projected to more than double by 2050.
>
> We built an agent that runs the software side from one sentence, powered by a small model: Nemotron 3.5 Lightning, 30 billion parameters, only 3 billion active, on one GPU. The model chooses tools. Plain code checks everything. And it never starts a print without a human saying yes.

*On screen:* captions "~8 h manual labor, ~$310 at $38.99/h (Sunnybrook; BLS)" and "1.6 M (2005) to 3.6 M (2050) projected (Ziegler-Graham et al.)". Then the one-line flow: `request → tools → slice → human approval → verified print`.

## 3. Live demo (1:00–2:05), [You] narrate, one continuous take

*Screen: the terminal chat on the left, OctoPrint at localhost:5001 on the right.*

| Beat | You type / show | What to say |
|---|---|---|
| 1 | `start a print` | "A vague request. It doesn't guess. It asks which part and which profile." |
| 2 | `benchy, draft_028` | "It finds the file, slices it, and reports time and filament." |
| 3 | The `CONFIRM start_print` prompt, press `y` | "Here's the gate. The model can't start the print itself. I have to approve." |
| 4 | OctoPrint page showing the job | "The printer says it's printing, and the agent only reports that after reading it back." |
| 5 | `check progress` | "It reads real state from the printer each time." |
| 6 | **Kill OctoPrint**, then `check progress` | "Now I break it on purpose. The agent says it can't read the printer. It does not say the print finished." |

Cut only to skip waiting on slicing or progress.

## 4. How we built it (2:05–3:35), split between the three

**[You], model and agent (about 40 s).**
> Nemotron 3.5 Lightning runs on vLLM on a Brev H200. The weights are about 40 GB, so one GPU holds the model with room to spare. We use vLLM's tool-call parser to get structured calls. The agent loop is plain Python. Every tool returns one of three typed results: success, fixable, or fatal. Fixable tells the model how to correct itself and retry. Fatal tells it to stop and tell the user.

**[Teammate 2], the part (about 20 s).**
> [Describe your CAD/geometry work and what it produces. Fill in.]

**[Teammate 3], the printer (about 25 s).**
> PrusaSlicer runs from the command line and turns the part into G-code. OctoPrint's virtual printer takes the job. We don't trust the printer's "OK": after every command we read the job state back. We also block a second start of the same job.

**[You], challenges (about 25 s), pick two.**
> - The model embellished: it invented details about our print profiles. We tightened the prompt to use only what tools return.
> - One error message made it offer a profile that was also missing. We rewrote the message so it stops instead.
> - Thinking costs speed: about a thousand reasoning tokens even on a one-line answer. [Say what you decided about that.]

## 5. So what? (3:35–4:05), [You] or all three

> One clinic that went digital reported saving about two hours of staff time per socket. At the median wage, that's about seventy-eight dollars each. Our agent targets the tool-juggling that's left: one sentence, a human approval, and a verified print.
>
> We built and tested all of it on under [X] dollars of GPU credit, with a small model that keeps the data local.
>
> This is a demonstration of safe automation, not a medical device. The printed parts are non-wearable. Thank you.

*On screen:* "~2 h saved per socket (one clinic's report) × $38.99/h ≈ $78. Illustrative estimate, not a measured result of our system."

## Before recording

- Fill [X] from the Brev console (credits spent).
- Add one measured line after the eval harness runs, for example "[N] of [M] test prompts used the right tools."
- Run the kill-OctoPrint beat once beforehand to confirm it behaves the same way.
- What we printed so far is a Benchy. If the CAD side can produce a socket by then, show that and say so.
- Never imply the printed part is wearable or clinically valid.

## Claims to avoid

- "Saves clinics $X" or any ROI figure. No study measured our system.
- The $310 as a saving. It is the whole manual labor, and our agent doesn't remove casting.
- The 1 day vs 17 day trial result as a cost or 3D-printing result. It tested a modular socket and found higher direct cost.
- The "quarter of the material cost" claim. Unverified.

## Sources for on-screen captions

- Sunnybrook, about 8 h manual labor per plaster socket: https://sunnybrook.ca/2019/10/could-3d-printing-make-prosthetics-quicker-and-more-comfortable-for-patients/
- BLS, median pay $38.99 per hour (May 2025): https://www.bls.gov/ooh/healthcare/orthotists-and-prosthetists.htm
- Ziegler-Graham et al., limb-loss prevalence: https://pubmed.ncbi.nlm.nih.gov/18295618/
- One clinic's digital workflow, 1 h to 15 min practitioner and 1.5 h to 15 min technician: single-practice report from the search in this session; [add the exact citation before using on screen].
