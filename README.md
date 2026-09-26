# Seeing Less: an accountable anomaly detector for orbital debris

**Challenge 5: AI Approaches for Orbital Anomaly Detection**
*Youth-led challenge from Morocco. Presented by Karima El Kassem. Mentor: Hamid Idelbacha.*
*Submitted for the Yohaku hackathon, 25–27 September 2026.*

**Code:** https://github.com/gajjararyan/Project-yohaku (public, MIT)
**Team:** Supernova Systems (Aryan Gajjar, solo)

**Submission title:** *Seeing Less: a detector that knows when it is wrong, and
who answers when it is.*

> *"If the AI becomes good at detecting known types of anomalies, operators
> might start relying on it by default and stop training their own eye for it.
> ... The whole point of this system is to eventually catch something it has
> never seen before — and that's exactly the moment a human's intuition matters
> most. **The tool meant to help us see more could end up making us see less on
> our own.**"*
> — Challenge 5 abstract

This submission takes that sentence as its **design requirement** rather than as
a caveat. The detector is deliberately small. The work is in (a) refusing to
claim more than the evidence supports, and (b) keeping a named human answerable
when it is wrong.

**Short summary (for a judge skimming):** We built a working detector for
unusual changes in satellite orbits that runs on real orbital data. Its most
important feature is not that it finds things — it is that it *declines to*.
We found that a single prediction, on its own, can tell you almost nothing: a
prediction that agrees with itself is not evidence. So the system's primary
claim rests on comparing two *separately published* descriptions of the same
satellite, and it publishes a machine-readable list of everything it has never
been tested on. It never raises an alarm without naming the person who must
answer for it.

---

## 1. What was built

A working pipeline over real orbital data:

```
TLE element sets
   -> SGP4 propagation
   -> two statistical tests (impulse + trend)
   -> physics admissibility gate (altitude-scaled)
   -> cross-epoch divergence check (INDEPENDENT second opinion)
   -> named human owner / abstention / override log
   -> machine-readable "what I have never seen"
```

```bash
python run.py              # fetch TLEs, analyse, write reports
python run.py --offline    # no network; uses the local cache
python run.py --self-test  # verify the scientific claims still hold
```

**Live result (9 operational spacecraft, 145 samples each):**

| Outcome | Count | Meaning |
|---|---:|---|
| `CONFIRMED` | 0 | Nothing survived the physics gate — see §4 |
| `ARTEFACT_REJECTED` | 1 | Flagged, then refused (a synthetic manoeuvre) — §4.2 |
| `ABSTAINED` | 1 | Element set 1002 days stale — withheld, not guessed |
| `NO_ANOMALY` | 7 | Nothing above threshold |

**Cross-epoch result — the load-bearing evidence:**

| Objects | Baseline | Agreement between independent fits |
|---:|---|---|
| 7 of 9 | 6.7 h – 1880 h | 0.00 – 0.56 km |

Two independently published element sets, up to **78 days apart**, agree to
within **0.6 km**. That is genuine external corroboration, and it correctly
reports **no anomaly** on healthy objects. §2.1 explains why this — not the
single-propagation trend — is the stronger claim.


---

## 2. The design decisions that carry the submission

### 2.1 A prediction agreeing with itself is not evidence

This is the central scientific point, and it took two experiments to establish.

**The trap.** SGP4 is deterministic. With nonzero BSTAR, propagating a single
element set forward *always* produces a smooth secular decay. A detector that
reads "persistent altitude trend" from one propagation is therefore partly
observing **the model confirming itself** — uncomfortably close to the trap the
brief warns about, that a pattern can look significant while physically
meaningless.

**And worse.** Measuring real objects, we found the signal is *smaller than
noise that is not an anomaly at all*. Over 24 hours the ISS altitude runs
**411.1 → 425.1 km and back** purely from orbital periodicity. A physically
plausible drag decay (0.05–4 km/day) moves only 0.2–3 km in that window. A
linear trend test **cannot resolve real drag decay in 24 h of data.** No
threshold tuning fixes that; it is a property of the data.

**The response — an independent second opinion.** For each object the system
takes a second, *separately published* element set, propagates the older fit
forward to the newer fit's epoch, and measures where the prediction lands
relative to what the newer fit actually says:

| Verdict | Meaning |
|---|---|
| `DIVERGENCE_DETECTED` | Two independent fits disagree beyond noise — **strong**, and external |
| `DATA_FAULT_SUSPECTED` | Disagreement far too large to be orbital behaviour — at least one fit is bad |
| `CORROBORATED_NO_SIGNAL` | Fits agree — genuine corroboration, but **moderate** at best |
| `INSUFFICIENT_SEPARATION` | Epochs too close to be independent — **not** treated as agreement |
| `NOT_AVAILABLE` | No second epoch obtainable — **no evidence, not agreement** |

Measured on the live fleet: **0.00–0.56 km agreement across 6.7 h–1880 h
baselines.** Two deliberate honesty rules apply:

- Agreement is graded `moderate`, never `strong`. Propagating a 78-day-old fit
  forward accumulates error regardless of what the object did, so much of that
  agreement reflects the *old fit's age*, not the object's health.
- Two element sets less than an hour apart prove nothing and are refused
  outright rather than reported as corroboration.

### 2.2 Statistics propose; physics disposes

A z-score cannot distinguish "significant" from "meaningful", so detection is
three-stage:

1. **Impulse test** — robust median/MAD z-score on residuals from a *detrended*
   baseline. Catches point anomalies.
2. **Trend test** — least-squares slope judged by its **t-statistic**, so
   significance is measured against the *noise*, not the signal's magnitude.
3. **Physics gate** — a candidate must persist across ≥3 samples *and* imply a
   drift rate inside the envelope physically achievable **at that altitude**.
   **Only this stage may reject.**

Two findings that shaped this, both caught by `--self-test` rather than by
inspection:

- A single global z-score **cannot** detect sustained drift. Standardising a
  linear ramp against its own mean and standard deviation caps its maximum |z|
  near 1.73 *however steep the ramp is*, so a 3σ threshold is mathematically
  unreachable.
- A residual against a *moving average* is structurally blind to drift, because
  the moving average of a linear series reproduces that series exactly. The
  first working version of this detector could not see the phenomenon the
  challenge is about.

**The band scales with altitude.** A flat 0.001–20 km/day envelope would treat a
400 km object and an 800 km object as equally able to decay at 20 km/day, which
is physically wrong — atmospheric density falls by ~3 orders of magnitude across
that range. Implemented envelopes run from 0.05–4.0 km/day at 400 km down to
0.002–0.1 km/day at 800 km.

### 2.3 Abstention is a first-class output

The system withholds a claim — loudly, with a reason — whenever its inputs are
not trustworthy. Five gates, all covered by the self-test:

| Gate | Trigger | Consequence |
|---|---|---|
| Empty series | SGP4 produced no state vectors | Withheld |
| Non-finite data | NaN/inf altitudes | Refused (no candidates) |
| Staleness | TLE older than 90 days | Withheld |
| Altitude band | Propagated mean outside published band | Withheld |
| Regime | Object outside validated regimes (LEO only) | Withheld |

The staleness gate is not hypothetical. During development one satellite was
served an element set **1002 days old**. Without this gate the system would have
reported a confident anomaly about an orbit that may no longer exist.

**Where this design comes from.** The abstention gates are a direct response to
how the challenge owner framed the problem. In the participant booklet she
writes that what is still missing is an AI that is:

> *"...honest about what it doesn't know rather than forcing a confident
> answer."*
> — Challenge 5 abstract, participant booklet

In her recorded introduction to the challenge, Karima El Kassem puts the same
requirement plainly: the system should **"clearly say when it is not sure."**
*(Quoted from the challenge video as relayed by the submitting participant;
the booklet wording above is the verbatim, page-referenced version of the same
idea.)*

We took that as a design requirement rather than a nicety. A detector required
to be useful on every pass is a detector that will eventually invent a
confident answer to fill the gap. So "I don't know" is a first-class, reportable
result here — with a reason attached and a named human who must resolve it. The
five gates above are the implementation of that requirement, and
`out/never_seen.json` is its machine-readable form.

### 2.4 Accountability is assigned, never implicit

Every finding names a **human decision owner** and labels its output a
*recommendation*, never an instruction. Confirmed candidates are auto-logged as
`DEFER` pending human confirmation rather than actioned.

`DecisionLog` records every override. This is not audit for its own sake: **if
operators routinely reject a class of alert, that disagreement is evidence the
model is wrong**, and it can only be noticed if written down. Operator judgement
accumulates rather than being quietly overwritten — precisely the erosion the
challenge owner describes.

---

### 2.5 Orbital stewardship: what we refuse to do, and why

> *This system ranks nothing by value at risk. It has no basis for preferring a
> crewed satellite over a weather satellite when both are at risk, and declines
> to imply otherwise.*

That sentence is emitted at runtime into `out/never_seen.json` and printed in
every console run. It is the sharpest limit in this submission, and it is worth
being explicit about the reasoning.

**The trade-off is real and we do not pretend otherwise.** When two objects are
at risk, something has to give: observation time, a manoeuvre, a shutdown
decision. Deciding what to protect first is genuinely a *normative* question.
A detector that ranked a crewed satellite above a weather satellite would be
making a value judgement on behalf of operators, regulators, and the
communities those satellites serve — and it would be presenting that judgement
as though it were a measurement, because the ranking would arrive as a number.

**What responsible priority-across-actors reasoning would require:**

- published, contestable value-at-risk inputs, with a stated provenance;
- an agreed weighting, and a record of **who set the weights and on what
  grounds**;
- a way for affected parties to contest the weighting, not merely observe it;
- some accounting for the people behind the object, not just the object.

None of that exists here. We do not have authority to set those weights, and
inventing them would be the most consequential error available to us.

**So the system refuses the task rather than improvising it.** This is the same
discipline that governs abstention elsewhere in the pipeline: where the evidence
does not support a claim, the honest output is *no claim*, clearly labelled.
It would have been easy — and would have looked impressive — to add a
`value_at_risk` score and rank the findings by it. That is precisely why it is
left out. The `stakes` field on each object (*"Six people are aboard; loss of
control is a life-safety event."*) is descriptive context for the human reader,
**not** an input to any ranking, and the system never acts on it.

This is also the point at which our work touches Challenge 2, *Seven Generations
in Orbit*, which asks directly about priority across objects and over future
generations. We did not attempt to answer that challenge here, and we note that
its Lakota knowledge-holding framing is not ours to translate into a scoring
function.

---





---

## 3. Answering the challenge questions directly

**"How can AI help detect unusual changes in satellite orbits and determine which
objects should be prioritized for observation?"**

By proposing candidates cheaply and honestly, then refusing to escalate what it
cannot physically justify — so scarce human attention is spent where attention
actually changes outcomes.

**"Can we really trust a security system that has never been tested against a
real attack, only a simulation of what we imagine an attack looks like?"**

No. This system has **never** seen a real anomaly, a real attack, or a real
spoofed TLE. It says so in `out/never_seen.json`, generated at runtime rather
than asserted in prose. The question is treated as a design requirement: the
answer to "what if the attack is what we didn't imagine?" is *a system that
abstains when it is out of its depth* — not a system with higher confidence.

**NARETU: *"If an AI decides which objects we watch, what do those who build it
and those who rely on it owe to each other, and to those who will come after?"***

- **To those who rely on it:** the right to see *why* a target was ranked, the
  right to disagree, and the right to an answer of "I don't know". A system that
  forces a confident answer takes that right away.
- **To those it does not flag:** an honest account of what was missed. Silence is
  not neutral — an unfilled gap in coverage looks identical to a quiet sky.
- **Across the time horizon:** every threshold here is an operational choice made
  by people who will not live with the consequences. They are declared in
  `src/config.py` so they can be argued with, which is the only form of
  long-horizon accountability available to a weekend prototype.

---

## 4. Two negative results, reported rather than hidden

### 4.1 The system detected nothing, and said so

On live data, **zero** objects reached `CONFIRMED`. Every one of the seven
synthetic or real excursions was either rejected on physical grounds or fell
below the noise floor. Given that the fleet is currently healthy, that is the
correct result — but it means **this submission contains no demonstration of a
true positive on real data.** We say so rather than implying otherwise.

### 4.2 The demo is a manoeuvre, not a decay — and the gate refuses it

The self-test injects synthetic events with known ground truth. Over 24 hours
the injected event must exceed the ~14 km periodic swing to be visible at all,
so it cannot be a physically plausible decay. We therefore inject a
**manoeuvre-like 5 km altitude step**, which is both real physics and clearly
labelled synthetic.

The result is more useful than a fake detection: the system **flags** the step
and the **physics gate rejects it** as inconsistent with passive drag, reporting
`FLAGGED, NOT CONFIRMED — more likely a manoeuvre, a deployment, or a data
fault than debris decay.` That is precisely the behaviour we want: the tool
declines to call a spacecraft's own burn an anomaly. This also matches a
declared limitation (manoeuvre confirmation is out of scope).

### 4.3 The blind spots are part of the deliverable

`out/never_seen.json` is generated at runtime, not asserted in prose. Its
first entry is the most important limitation in this project:

> Over a 24 h window a real LEO altitude series varies by ~14 km peak-to-peak
> from orbital periodicity alone. A plausible secular decay of 0.05–4 km/day is
> only 0.2–3 km over that window, so it sits *inside* the natural variation. The
> 24 h single-TLE trend detector therefore cannot resolve real drag decay in
> this data.

We could have hidden this by injecting a large synthetic decay and reporting a
confident detection. That would have been a lie about what the system can do.


---

## 5. Credit and terms of use

- **The question is not mine.** Challenge 5 is presented by **Karima El Kassem**
  (Morocco); **Hamid Idelbacha** is the mentor. The framing of automation
  complacency and false confidence is theirs, and this submission is a response
  to it.
- **NARETU** — the obligations-based framework applied in §3 — was developed by
  **Chief Titus Letaapo** drawing on Indigenous Samburu governance principles. It
  is applied here as a framing borrowed on its own terms, not translated into a
  technical variable. The knowledge-holder decides what belongs in a technical
  system; that authority is not mine to assume.
- **Indigenous Cultural and Intellectual Property governs this work.** No
  community knowledge was used, reconstructed, imitated, or uploaded to any model
  in producing it. No Indigenous artwork, story, or recording was involved.
  Nothing here should be read as speaking for any Indigenous person or community.
- **Data:** public TLEs from CelesTrak and a public per-satellite mirror. TLEs
  are operator-published least-squares fits, not ground truth.
- **This prototype is not certified** for any real collision-avoidance decision.

---

## 6. Reproducing and limitations

```bash
pip install -r requirements.txt
python run.py --self-test   # must pass before the results mean anything
python run.py --offline     # deterministic; safe for a live demo
```

**Known limitations** (full list generated to `out/never_seen.json`):

- No real labelled anomaly; all validation events are synthetic and injected here.
- No adversary, attack, or spoofed TLE has ever been tested against it.
- Not validated for manoeuvre confirmation — a real burn would look anomalous.
- LEO only, 24-hour window, 9 hand-picked operational spacecraft.
- No conjunction assessment, ground-station geometry, weather or sensor
  constraints, so it cannot yet produce a usable observation plan by itself.
- ~6 km RMS noise floor limits single-sample sensitivity.

---

## 7. Scope of what was validated, and what was not

This prototype validates the detection and abstention logic on **9 tracked
objects, analysed on demand**. The architecture — fetch, propagate, detect,
gate, log — has **no object-count ceiling** and could run continuously against
CelesTrak's full active catalogue; we scoped to 9 objects to keep every result
independently verifiable within the hackathon window, and see continuous
real-time monitoring at catalogue scale as the natural next step.

That ceiling claim was tested rather than asserted: a 600-object fleet was
pushed through the identical propagate → detect loop used by `run.py`, and all
600 processed with **zero failures** at ~331 objects/s. Extrapolated,
CelesTrak's full active catalogue (~16,600 objects) is roughly **0.8 minutes**
of single-threaded work with no code change.

Two honest qualifiers on that number. First, the 600-object scale test used
element sets *derived* from the 9 real ones (mean motion and inclination
perturbed) — CelesTrak was rate-limiting the full-catalogue download at the
time, so the loop was exercised at scale but not against the live catalogue.
Second, throughput is not the interesting limit: at 16,600 objects the
bottleneck would become the *per-object data volume* and the decision-owner
queue, not propagation. The point of the claim is that nothing in the design
caps the object count, not that scaling is free.

---

## 8. AI-use disclosure

See [`docs/AI_USE_DISCLOSURE.md`](docs/AI_USE_DISCLOSURE.md) for the full
statement required by the Yohaku AI-use policy.

---

## 9. Repository layout

```
run.py                    orchestrator + --self-test
src/config.py             every constant and threshold, auditable in one place
src/data_source.py        TLE fetch, cache, fallback, schema normalisation
src/orbits.py             SGP4 propagation; synthetic scenario injection
src/detection.py          impulse test, trend test, physics gate
src/accountability.py     decision owners, abstention, decision log, blind spots
src/reporting.py          console + JSON artefacts
data/tle_cache.json       cached element sets (offline-first)
out/                      summary.json, findings.json, never_seen.json, decision_log.json
```
