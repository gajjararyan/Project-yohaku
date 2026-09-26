# AI-Use Disclosure

*Required under the Yohaku AI-use policy. Submitted with Challenge 5 —
"AI Approaches for Orbital Anomaly Detection".*

The policy requires disclosure of which AI tools were used, what for, what was
independently checked, and whether AI contributed to the solution itself. This
document answers all four.

---

## 1. Which AI tools were used

| Tool | Role in this work |
|---|---|
| Claude (Anthropic), via the Cline coding assistant in VS Code | Code drafting and review, debugging, structuring, documentation |
| Claude (Anthropic) | Extracting the text of the participant booklet PDF to understand the challenge |
| `pypdf` (open-source library, not an AI tool) | Mechanical PDF text extraction only |

No other generative AI system was used. No image, audio, or video generation
was involved.

---

## 2. What the AI was used for

1. **Understanding the challenge.** The participant booklet is a designed PDF
   whose text extracts in a fragmented layout. AI was used to read and summarise
   it, and to identify the judging criteria, the AI-use policy, and the
   challenge owner's stated concerns.
2. **Code drafting and debugging.** All modules in `src/` were drafted with AI
   assistance, then executed and corrected iteratively.
3. **Documentation.** `README.md` and this disclosure were drafted with AI
   assistance.
4. **Scientific review.** AI was used to interrogate the statistical design —
   specifically to question whether a global z-score could detect sustained
   drift, which surfaced a real flaw described in §5.

**AI did not choose the research question, the framing, the detection
architecture, or the accountability design.** Those are the human
contribution, and they follow directly from the challenge owner's own words.

---

## 3. What was independently checked

Every factual and technical claim was verified by execution rather than
accepted from the AI. Specific checks:

| Claim | How it was verified |
|---|---|
| SGP4 returns position from Earth's **centre**, not its surface | Propagated the ISS; raw output implied 6.8 km altitude. Corrected by subtracting R⊕ = 6378.137 km, giving **418.5 km**, which matches the published orbit |
| Altitudes of all 9 tracked objects are physically plausible | Compared propagated means against published orbital bands; two NOAA bands were **wrong in the original config** and were corrected from measurement |
| CelesTrak returns live data | Direct request returned 16,619 active objects with full elements |
| CelesTrak rate-limits and returns HTTP 403 | Reproduced on repeated calls; this is why the pipeline caches and uses a fallback |
| The fallback mirror's schema | Inspected the actual JSON; it uses JSON-LD and names the field `satelliteId`, not `norad_id`. An early version silently returned **0 of 9** objects because of this |
| `Satrec` attribute names | Inspected the object: it exposes `ecco`/`inclo`, **not** `ecc`/`inclination` |
| The self-test claims | `python run.py --self-test` — all four assertions pass |
| All numerical results quoted in the README | Regenerated from `out/summary.json` and read back |

**Corrections made because checking disagreed with the AI's first answer:**

- SGP4 unit handling (6.8 km vs the true 418.5 km)
- A moving-average residual being mathematically blind to linear drift
- Absurd confidence values (9196σ, 3.7×10¹³σ) caused by a zero noise estimate
- Two incorrect satellite altitude bands
- A `satelliteId` schema mismatch that silently zeroed the fleet
- Stale element-set data (one satellite served a **1002-day-old** TLE)

---

## 4. Did AI contribute to the solution itself?

**No — not to the decision logic.** The detector is arithmetic: SGP4
propagation, a robust z-score, a least-squares trend test, a threshold
comparison, and a comparison of two element sets. There is no trained model, no
learned parameter, and no model output that was accepted without execution. AI
assisted in *writing the code* that implements those operations. It did not
supply predictions, classifications, or orbital assessments.

**Yes — to the design of the system, and this should be stated plainly.** The
most consequential contribution in this work was not writing code: it was
*questioning the science*. Probing whether a global z-score could detect a
sustained drift surfaced the fact that it cannot, which forced a separate trend
test. Probing whether the trend test was trustworthy surfaced that a
moving-average residual is mathematically blind to linear drift. Probing the
cross-epoch comparison surfaced that deriving altitude from eccentricity yields
the *mean* altitude of an ellipse, which for a near-circular orbit is ~3 km
rather than the true ~420 km.

Each of those changed the design, and each was found by running the code rather
than by reading it. A human chose the research question, chose to treat the
challenge owner's own words as the design requirement, and decided which
findings were safe to publish. That judgement is the human contribution, and it
is the part a judge should weigh.

---

## 5. Disclosed AI-introduced errors

Disclosed because each is a concrete instance of a plausible-looking artefact
that survived review, and because the fix is part of the final design.

**5.1 A detector that could not see its own subject.** The first version used a
residual against a 3-point moving average. That approach **cannot** detect a
sustained drift: the moving average of a linear series reproduces that series
exactly, so the residual is identically zero. The detector was structurally
blind to the phenomenon Challenge 5 is about. Found by writing
`run.py --self-test` and watching the "sustained decay" case fail — not by
inspection.

**5.2 Unit error producing physically impossible altitudes.** SGP4 returns
position from the Earth's centre. Dividing by 1000 — an intuitive-looking but
wrong move — gave an ISS altitude of 6.8 km. Corrected by subtracting
R⊕ = 6378.137 km, giving 418.5 km, which matches the published orbit.

**5.3 Absurd confidence values.** With near-zero noise estimates the system
reported 9196σ and 3.7×10¹³σ. A confidence that large is not a strength, it is
evidence of a broken denominator. Fixed with a noise floor; the same cases now
report 12σ and 41.9σ.

**5.4 Silent total data loss.** The fallback mirror serves JSON-LD naming the
catalogue field `satelliteId`, not `norad_id`. The pipeline silently returned
**0 of 9** objects — it looked like "no anomalies found" rather than "no data".

**5.5 Wrong query parameter, masked as a JSON error.** CelesTrak requires
`CATNR=`, not `GROUP=CATNR-<id>`. The wrong form returns **HTTP 200** with a
plain-text "Invalid query" body, which surfaced as a JSON decode error rather
than a clean HTTP failure. Separately, `FORMAT=json` returns *parsed* orbital
elements with no `LINE1`/`LINE2` at all, so it cannot be fed to `twoline2rv`.

**5.6 Mean altitude mistaken for instantaneous altitude.** Deriving altitude
from an element set's eccentricity gives the *mean* altitude of the ellipse. For
the ISS (e ≈ 5×10⁻⁴) that is ~3 km, not ~420 km. This produced a cross-epoch
"divergence" of 793 km and would have been reported as a data fault. Corrected by
propagating the newer fit to its own epoch and reading the radius there.

**5.7 A rejected candidate reported as confirmed.** `confirmed` was derived from
`persistent and plausible_rate`, which was still true for a
`REGIME_IMPLAUSIBLE_REJECTED` verdict — so the system called a rejected
candidate confirmed. Found by a self-test assertion that the physics gate
rejects an over-fast decay.

**5.8 Phantom alerts from non-finite data.** A 20-sample series of `NaN`
altitudes produced 20 spurious candidates. Now refused outright.

**5.9 NaN altitudes in the output rationale.** Reported by the verification
script; a NaN-altitude finding would have printed "NaN" in a submitted
rationale. Refused at the detection boundary.


---

## 6. Compliance with the AI-use policy

- No sources, claims, citations, or community positions were fabricated. Every
  quotation is from the participant booklet, and every technical claim was
  verified by execution.
- No restricted or unshared Indigenous knowledge was used, reconstructed, or
  imitated.
- Nothing was done that speaks for an Indigenous person or community.
- **No Indigenous knowledge, story, artwork, or recording was uploaded to any AI
  system.** None was used in this work at all.
- No material provided for a Yohaku challenge was used for AI training,
  fine-tuning, or any other model development.
- Indigenous Cultural and Intellectual Property, community protocols, and consent
  conditions take precedence over anything in this submission.
- **The human participants remain responsible for this work**, including its
  errors.
