# Demo video script

Target length about **4:40**. The hackathon asks for 3–5 minutes. Section times are the ideal range from their instructions, except that we add a short business and regulation beat inside the "Why" part.

Everything in [brackets] must be filled in or confirmed before recording. Roles are a guess; swap them if wrong. Every statistic has a small on-screen source caption, and sources are listed at the end.

Each section has a **Say** block (what is spoken) and a **How to shoot it** block (camera, location, on-screen text, audio, cuts).

| # | Section | Time | Who | Shot |
|---|---|---|---|---|
| 1 | Team intro | 0:00–0:20 | All three | One locked wide shot, city behind |
| 2 | Hook | 0:20–0:55 | One line each | Three walk-toward-camera shots |
| 3 | Live demo | 0:55–1:55 | [You] | Screen recording, one take |
| 4 | How we built it | 1:55–3:00 | All three | Architecture slide plus real screens |
| 5 | Business and MVP | 3:00–3:40 | [You] or [Teammate 3] | Medium shot, then a three-column graphic |
| 6 | Regulation, plainly | 3:40–4:05 | [Teammate 2] | Close piece-to-camera, no music |
| 7 | Close | 4:05–4:40 | All three | Same spot as the intro, final brand card |

Spoken-word counts per section were checked at a calm pace of about 2.5–3 words per second. If a take runs long, cut a sentence from section 4 first, then section 5.

## The product as a business

Shim is a workflow agent for the people who already make prosthetic sockets: prosthetists, technicians and central labs. A small model picks the tools, plain code checks everything, and a person approves every print. Today it proves the software chain on **synthetic data and non-wearable parts**, and every print runs on **OctoPrint's virtual printer, a software simulator**. We do not have a physical printer yet. The business is the next step: a pilot in which real clinics run their own work through the same agent, with a clinician approving each step.

This is an **MVP**, not a product that is ready for patients. The video should say so plainly. That honesty is part of the brand: a small team that knows exactly where the line is.

What the MVP is trying to learn:

| Question | How we find out | Proposed bar to call it validated |
|---|---|---|
| Will a prosthetist use it? | Observed sessions in 3–5 clinics with synthetic or de-identified inputs | [X] of [Y] finish a print without help |
| Does it save time? | Time one person doing slice-and-print by hand against the agent | [N] minutes saved per part, measured by us |
| Do they trust the approval gate? | Short interviews after each session | They say the gate makes them more comfortable, not less |
| Will anyone pay? | Ask for a paid pilot at the end of the session | [N] of [M] say yes to a paid pilot |

These bars are proposals. Set them before the first pilot, not after.

## 1. Team intro (0:00–0:20), everyone, one line each

**Say**

> **[You]:** Hi, we're [team name], in the tool-calling track. I built the agent: the loop that lets the model pick tools and recover from errors.
> **[Teammate 2]:** I built [the geometry and CAD tools that make the part].
> **[Teammate 3]:** And I set up [the slicer and the virtual printer]. Here's what we made.

**How to shoot it**

- One locked-off wide shot of all three standing in a line, speaking in turn. City in the background.
- Camera on a tripod at chest height, 16:9, with some empty space around the group so a square or vertical crop still works.
- Light: overcast or the hour after sunrise. Avoid harsh midday sun and avoid backlighting faces.
- Audio: a lavalier mic on each person, or a phone held close just out of frame. City noise will hurt more than the picture.
- On-screen text: "Shim" large on the first frame. Names and roles as lower-thirds when each person speaks. Keep it to 2 seconds each.
- Do 3 takes. Pick the one where all three finish cleanly.

## 2. The hook (0:20–0:55), one line each

**Say**

> **[You]:** Making a prosthetic socket the traditional way takes about eight hours of manual labor. At the median prosthetist wage, that's roughly three hundred dollars of labor per socket.
> **[Teammate 2]:** Plus the need is growing: 1.6 million Americans were living with limb loss in 2005, projected to more than double by 2050.
> **[Teammate 3]:** That's why we built an agent that runs the software side from one sentence, powered by a small model: Nemotron 3.5 Lightning, 30 billion parameters, only 3 billion active, on one GPU. The model chooses tools. Plain code checks everything. And it never starts a print without a human saying yes.

**How to shoot it**

- Three separate shots, one per speaker, each walking toward the camera while talking. Same city background as the intro so it cuts as one scene.
- Tripod low and still, with each person walking from about 8 metres out to close-up. Or a gimbal held by a fourth person walking backward. The first is steadier and easier.
- Cut on the footstep after each speaker's last word so the three shots flow.
- On-screen text, after each line lands: "~8 h manual labor · ~$310 at $38.99/h" then "1.6 M (2005) → 3.6 M (2050), projected". Sources in small type underneath: Sunnybrook, BLS, Ziegler-Graham et al.
- Finish with a clean full-screen graphic of the flow: `request → tools → slice → human approval → verified print`. Build it as a slide, 3 seconds.
- Do 3 takes per person. The walking pace matters more than the words, so rehearse it.

## 3. Live demo (0:55–1:55), [You] narrate, one continuous take

**Say**

| Beat | You type / show | What to say |
|---|---|---|
| 1 | `start a print` | "A vague request. It doesn't guess. It asks which part and which profile." |
| 2 | `benchy, draft_028` | "It finds the file, slices it, and reports time and filament." |
| 3 | The `CONFIRM start_print` prompt, press `y` | "Here's the gate. The model can't start the print itself. I have to approve." |
| 4 | OctoPrint page showing the job | "This is OctoPrint's virtual printer, a simulator, because we don't have a physical printer yet. It says it's printing, and the agent only reports that after reading it back." |
| 5 | `check progress` | "It reads the state back from the printer each time, here the simulator." |
| 6 | **Kill OctoPrint**, then `check progress` | "Now I break it on purpose. The agent says it can't read the printer. It does not say the print finished." |

**How to shoot it**

- Screen recording only (QuickTime or OBS), 1920×1080, 30 fps. Terminal on the left, OctoPrint at localhost:5001 on the right. Keep a small label on the OctoPrint side for the whole demo: **"Virtual printer (simulator) · no physical hardware yet"**. Narrate live over the top. Don't re-record the voice afterwards, because the pauses sound natural.
- Terminal font size 18 pt or larger, dark text on a light background, so it stays readable when compressed for a phone.
- Hide the dock, notifications and bookmarks. Turn on Do Not Disturb.
- Cut only to skip waiting on slicing or progress. If you do, add a small "sped up" label. Never cut inside a tool call or the confirmation prompt.
- Add a zoom-in on three moments: the confirmation prompt, the "printing, confirmed" line, and the "can't read the printer" answer. Hold each for about 2 seconds.
- **Show only real output.** The repo now has the backend for the three-page web workbench (`agent/web_api.py`) and registered CAD tools. We have **not** run them together end to end, so don't promise it on camera until you have. Start them with the `api` and `web-real-api` entries in `.claude/launch.json`. The page must show no "Mock data" badge. If one full run works (limb, confirm, socket, confirm, print, link loss), shoot the demo in the web workbench instead of the terminal: browser on the left at 1920×1080, OctoPrint at localhost:5001 on the right, same beats as the table above. If anything in that run is flaky, shoot the terminal version, which is the one we've tested against real OctoPrint.
- Rehearse the kill-OctoPrint beat once beforehand to confirm it behaves the same way.
- If you shoot the web workbench, run the full flow twice first and keep the "Mock data" badge out of frame.
- What we have run so far is a Benchy on the virtual printer, not on a real machine. The CAD tools are now registered, so if you can run the whole chain once (set the three measurements, confirm the limb, change the socket, confirm it, print), show a socket and say that it is a synthetic, non-wearable demonstration part printed on the simulator. If not, show the Benchy and say so.

## 4. How we built it (1:55–3:00), split between the three

**Say**

**[You], model and agent (about 30 s).**
> Nemotron 3.5 Lightning runs on vLLM on a Brev H200. The weights are about 40 GB, so one GPU holds the model with room to spare. vLLM's tool-call parser gives us structured calls. Every tool returns success, fixable or fatal. Fixable tells the model how to correct itself and retry. Fatal tells it to stop and tell the user.

**[Teammate 2], the part (about 15 s).**
> [Describe your CAD/geometry work in your own words. The registered tools include `customize_residual_limb`, `modify_socket` and `validate_part`: say which ones you wrote and what check each one runs. Fill in.]

**[Teammate 3], the printer (about 15 s).**
> PrusaSlicer turns the part into G-code and OctoPrint's virtual printer, a software simulator, takes the job, since we don't have a physical printer yet. We don't trust the printer's "OK": after every command we read the job state back, and we block a second start of the same job.

**[You], challenges (about 10 s), pick one.**
> - The model embellished and invented details about our print profiles, so we tightened the prompt to use only what tools return.
> - One error message made it offer a profile that was also missing, so we rewrote it to make the model stop.
> - Thinking costs speed: about a thousand reasoning tokens even on a one-line answer. [Say what you decided.]

**How to shoot it**

- One architecture slide, built once and reused: **model on Brev H200 → vLLM → agent loop → tools → PrusaSlicer → OctoPrint → read-back**. Light background, ink lines, the same fonts as the product. Reveal it left to right as you speak.
- Show real evidence, not stock footage: the Brev console and a terminal running `nvidia-smi` that shows the H200, the vLLM startup log, and a screenshot of a failing-then-fixed tool result.
- Each person records their part as a voiceover over the slide or over their own screen. Alternatively, shoot each in front of a laptop in the city setting, speaking to the camera, and cut to the screen. Pick one style for all three so it feels consistent.
- Keep each person's segment under 30 seconds. Cut any sentence that doesn't help a judge understand your engineering.
- On-screen text: sponsor names where they are true (NVIDIA Nemotron, Brev) and small labels on each box of the diagram.

## 5. The business: MVP, users and validation (3:00–3:40), [You] or [Teammate 3]

**Say**

> Shim is built for people who already make sockets: prosthetists, technicians and labs. Digital design is already in clinics. One design package alone reports 700 to 800-plus facilities worldwide. So the habit exists. Our bet is the glue between the steps.
>
> Today this is an MVP on synthetic data. Will people use it? We don't know yet. Next we move from the simulator to a real printer, take it to [3–5] clinics, time a person against the agent, and ask: would you pay for a pilot?

**How to shoot it**

- One medium shot, speaker standing or seated at a plain table with the city soft behind. Calm pace, no walking: this is the credibility beat.
- Cut to one clean graphic with three columns, **Who** (prosthetists, technicians, labs), **What we test** (minutes saved, trust in the gate, willingness to pay), and **Status** with a clear "Not yet validated" tag. Hold 5 seconds so people can read it.
- On-screen source caption: "Vorum Canfit reports 700–800+ facilities (3dprint.com)" and the BLS count if you use it.
- Don't cut to stock footage of happy patients. We have no patients, and it would imply clinical use.

## 6. Regulation, plainly (3:40–4:05), [Teammate 2]

**Say**

> A finished socket is a medical device. FDA's records list socket components as Class I, exempt from premarket review. An assembled lower-limb prosthesis is Class II. Whether software that designs a socket is regulated depends on what we claim. So today we claim nothing clinical, and before any patient use, we get regulatory counsel.

**How to shoot it**

- One close piece-to-camera, neutral background, steady and unhurried. No music under this part.
- On-screen text, three short lines that appear one at a time:
  1. "Socket components: Class I, 510(k) exempt (FDA classification)"
  2. "Assembled lower-limb prosthesis: Class II"
  3. "This demo: synthetic data · not for patient use"
- Keep the on-screen text to those three lines. Do not show the CFR text or any legal wording on screen.
- Verify every statement here with a regulatory consultant before publishing. The research below was desk research, not legal advice.

## 7. So what? Close (4:05–4:40), everyone, bookend the intro

**Say**

> **[You]:** Eight hours of manual labor per socket. 1.6 million Americans with limb loss, heading to 3.6 million.
> **[Teammate 2]:** A small model, one GPU, and a human approving every print.
> **[Teammate 3]:** One clinic reported saving two hours per socket. We want to give more back.
> **[All]:** We're Shim. From tape measure to verified print.

**How to shoot it**

- Shoot in the **same location and framing as the intro** so the video bookends. All three in line, same positions, slow push-in on the tripod over the last 8 seconds.
- Deliver the last line together, on a beat, looking at the camera. Do 5 takes. Pick the one with the strongest energy, not the cleanest timing.
- Final frame, held for 3 seconds on a clean card: the **Shim** wordmark, the tagline "From tape measure to verified print.", [URL or QR code to the repo/landing page], "Built on NVIDIA Nemotron 3.5 Lightning · [event hashtag]", and the lines "Nonclinical demonstration." and "Virtual printer demo · no physical hardware."
- Add a short audio sting under the last line. Fade the music out cleanly, with no abrupt cut.
- Export a 16:9 master for the hackathon. If it will go to LinkedIn or social, export a square crop too, with **burned-in captions** since most people watch muted.
- The small caption "~2 h saved per socket (one clinic's report) × $38.99/h ≈ $78. Illustrative estimate, not a measured result of our system." should appear under the line about two hours.

## Regulation notes for the team (not spoken)

This is desk research from the session, not legal advice. **Get a regulatory consultant before any patient use or any clinical claim.** The sources vary in quality, and each row says how far to trust it.

| Topic | What we found | Trust | What to do |
|---|---|---|---|
| Socket components | FDA classifies external limb prosthetic components, including socket components, as **Class I** under 21 CFR 890.3420. The thigh socket product code (ISS) is listed as 510(k) exempt. | FDA's classification record, plus a 2014 CFR printout | Confirm that a **transtibial** socket maps to the same code. We did not find a separate one. |
| Assembled lower-limb prosthesis | Classified **Class II** (special controls) under 21 CFR 890.3500. | CFR text | Confirm whether a clinic assembling a prosthesis around our socket triggers Class II duties. |
| Exemption limits | Exempt from premarket notification, but still subject to general controls, including records and complaint files. | FDA's classification record | Have counsel read the exact limits. |
| 3D printing and patient-matched devices | FDA's additive manufacturing guidance (draft 2016, final 2018) covers design, testing and quality for 3D-printed devices. Its **point-of-care** discussion paper (2021) asks for feedback on who counts as the "manufacturer" when a clinic prints. It is **not** policy. | A law-firm blog and FDA's own paper | Ask counsel who the manufacturer is if a clinic prints a socket with our software. |
| Custom device exemption | A patient-matched device is **not** automatically a custom device. FDA's criteria include unique pathology and no more than 5 units a year. A 3D-printed copy of a device that has a conventional equivalent doesn't qualify. | Pew summary of FDA material | Assume we **cannot** rely on this exemption. |
| Quality system | The QMSR replaced the old Quality System Regulation on **2 February 2026**, folding in ISO 13485:2016. Design controls are required even for custom devices. | Secondary commentary | Check the Federal Register final rule. Plan an ISO 13485 gap analysis before any commercial manufacture. |
| AI and software | FDA updated its clinical decision support guidance in January 2026 to widen enforcement discretion for some software. Sources disagree on the exact date. Our agent makes **no clinical recommendation** and a person approves each action. | Law-firm summaries | Confirm that our software is not a device function, or whether it is an accessory or manufacturing software. Intended use and our claims decide this. |
| Intended use | FDA looks at what we claim. Every on-screen and written claim must stay non-clinical until the path is settled. | General principle | Write an intended-use statement now, and keep every word of marketing consistent with it. |
| Privacy | Measurements alone may not be PHI, but become PHI when linked to a person or received from a provider. If we host a clinic's data, we are probably a **business associate** and need a BAA, as does our cloud host. | Vendor explainers, not legal sources | Keep pilots on synthetic or de-identified data until counsel reviews the data flow. |

Questions for the consultant:
1. Is software that designs and drives printing of a socket a device, an accessory, or exempt? What intended-use wording keeps us outside premarket review?
2. If a clinic prints the socket, who is the manufacturer, and what does the clinic owe under QMSR?
3. What do we need for a pilot with real patient data?
4. What state-level rules and payer or Medicare billing rules apply to a clinic using this workflow? We did not research these.

## Before recording

- Fill [X] from the Brev console (credits spent).
- Add one measured line after the eval harness runs, for example "[N] of [M] test prompts used the right tools."
- Run the kill-OctoPrint beat once beforehand to confirm it behaves the same way.
- Decide the validation bars in the table above and say them aloud only if the team agrees.
- Confirm the regulation lines with a consultant, or soften them to "we are checking this with a regulatory expert."
- Pick the brand card text and the URL or QR code. Check the QR scans from a phone screen.
- Never imply the printed part is wearable or clinically valid.
- Keep the "Virtual printer (simulator)" label on screen during the whole demo and say it out loud in beat 4.

## Claims to avoid

- "Saves clinics $X" or any ROI figure. No study measured our system.
- The $310 as a saving. It is the whole manual labor, and our agent doesn't remove casting.
- The 1 day vs 17 day trial result as a cost or 3D-printing result. It tested a modular socket and found higher direct cost.
- The "quarter of the material cost" claim. Unverified.
- **"FDA approved", "FDA cleared", "FDA compliant", "HIPAA compliant", "clinically validated", "medical device", or any claim that patients can wear the output.** None of these are true or settled.
- "Validated" or "proven demand". We have not run the pilots.
- "We printed a socket" or "real 3D printing" without saying it was on a simulator. Say "virtual print" or "simulated print".
- Anything about real printer safety, thermal limits or firmware. The virtual printer does not test those, so the demo says nothing about them.
- Dropping the "nonclinical demonstration" line. It must be on the final card.

## Sources for on-screen captions and notes

- Sunnybrook, about 8 h manual labor per plaster socket: https://sunnybrook.ca/2019/10/could-3d-printing-make-prosthetics-quicker-and-more-comfortable-for-patients/
- BLS, median pay $38.99 per hour (May 2025), about 9,500 jobs: https://www.bls.gov/ooh/healthcare/orthotists-and-prosthetists.htm
- Ziegler-Graham et al., limb-loss prevalence: https://pubmed.ncbi.nlm.nih.gov/18295618/
- Vorum Canfit facility count: https://3dprint.com/167852/create-op-vorum-canfit/
- 21 CFR 890.3420, external limb prosthetic component (socket components, Class I): https://www.ecfr.gov/current/title-21/chapter-I/subchapter-H/part-890/subpart-D/section-890.3420
- FDA product classification, thigh socket (ISS, 510(k) exempt): https://www.accessdata.fda.gov/scripts/cdrh/cfdocs/cfpcd/classification.cfm?id=ISS
- FDA point-of-care 3D printing discussion paper, summary: https://www.thefdalawblog.com/2022/01/fda-publishes-discussion-paper-seeking-feedback-on-3d-printing-of-medical-devices-at-the-point-of-care/
- Medical 3D printing and the custom device exemption, Pew summary: https://www.pew.org/en/research-and-analysis/issue-briefs/2020/10/what-is-medical-3d-printing-and-how-is-it-regulated
- QMSR effective 2 February 2026, secondary summary: https://intuitionlabs.ai/articles/fda-qmsr-iso-13485-changes-2026
- FDA clinical decision support update, January 2026, secondary summary: https://www.orrick.com/en/Insights/2026/01/FDA-Eases-Oversight-for-AI-Enabled-Clinical-Decision-Support-Software-and-Wearables
- One clinic's digital workflow, 1 h to 15 min practitioner and 1.5 h to 15 min technician: single-practice report from an earlier search; [add the exact citation before using on screen, or cut that line].
