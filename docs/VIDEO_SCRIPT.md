# 2-Minute Video Script — Teleprompter

**Required by the form.** "A simple phone or Zoom recording is fine."

**Recommended capture:** screen-record the terminal running `python run.py`,
and narrate over it. The console output already shows the decision owner, the
abstention reason, the cross-epoch result and the "never seen" register — the
whole submission is visible in one window, so you never have to describe a
diagram you can't show.

**Before you record:** open the repo README in a second tab, and have
`python run.py` ready to go. The run takes ~10–35 seconds, so the "demo" fits
comfortably inside the narration.

**Pace:** ~150 words/minute. The spoken script below is **~265 words**, which is
**1:46 at 150 wpm** and **1:54 at a slower 140 wpm**. Read it aloud once before
you record so you know your own pace. It should sound like you explaining
something, not like you reading.

---

## SCRIPT

**[0:00 — 0:14] The problem, in her words**

> Karima El Kassem, who posed this challenge, warned that if an AI gets good at
> known anomalies, operators stop trusting their own eye. I took that as the
> design requirement, not a footnote.

**[0:14 — 0:42] What I found first**

> I built a detector on real orbital data — and found it doesn't work how you'd
> expect. SGP4 is deterministic: with drag in the model, propagating one element
> set forward always shows a smooth decay. Calling that an anomaly is partly
> agreeing with yourself. Worse: over 24 hours a real satellite's altitude
> swings fourteen kilometres on orbital physics alone, while a plausible decay
> moves two or three.

**[0:42 — 1:08] What I did instead**

> So the evidence has to come from outside the model. I fetch a second,
> separately published element set, propagate the older forward to the newer
> one's timestamp, and see where the prediction lands. On the live fleet: seven
> of nine objects, baselines up to seventy-eight days, agreeing to within six
> hundred metres. External corroboration — and correctly, no anomaly. The
> satellites are fine.

**[1:08 — 1:34] What the system refuses to do** *(point at the console)*

> What it does instead is refuse. One satellite's element set was a thousand days
> old, so it withheld the assessment. Another showed a five-kilometre step that
> looks like debris — and the gate rejected it, because it wasn't drag, it was a
> manoeuvre. It ranked nothing by value at risk. I won't put a crewed satellite
> above a weather one. That call isn't mine.

**[1:34 — 1:46] Close**

> Every finding names a human who must confirm or reject it, and the system
> publishes a list of everything it has never been tested on. A detector that
> knows when it's wrong, and who answers when it is. Code's in the repo. Thank
> you.

---

## Notes for delivery

- **Don't rush the middle.** The two measured findings (SGP4 agreeing with
  itself; 14 km periodicity) are what separate this from a generic ML demo. If
  you only have time for one thing, keep those.
- **If you show the terminal, pause on it.** Let the judge read the owner name
  and the abstention reason while you talk. Silence while they read is fine.
- **You don't need slides.** A screen recording plus your voice is explicitly
  acceptable. Don't spend time on animation.
- **If you trip on a word, just keep going.** It's two minutes, not a keynote.

## If you're short on time

Record the script as-is and simply say "as you can see in the console" when
you'd normally point. The output speaks for itself.
