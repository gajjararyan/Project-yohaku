# Form Answers — Yohaku 2026 Final Submission, Challenge 5

Copy-paste source for: https://forms.gle/Z4Kn1aqhwc1Ry8ht6
Deadline: **Sun 27 Sept 2026, 14:00 CEST**

Four fields need personal detail from Aryan Gajjar and are marked `[← FILL]`:
email, location, organisation, short bio.

**Required video:** see [`VIDEO_SCRIPT.md`](VIDEO_SCRIPT.md) for a timed
teleprompter script. A phone or Zoom screen recording is explicitly acceptable.

---

## 1. Email(s) to contact the team

```
[← FILL your email]
```

## 2. Team or group name

```
Supernova Systems
```

## 3. Solution title

```
Seeing Less: a detector that knows when it is wrong, and who answers when it is
```

## 4. Team members

```
Aryan Gajjar
```

## 5. Location

```
[← FILL city/region + country, e.g. "Bengaluru, India"]
```

## 6. Organisation, university or community

```
[← FILL your university, employer, or community]
```

## 7. Short bios (1–2 sentences per participant)

```
[← FILL 1–2 sentences: what you do, study, or care about]
```

## 8. 2-minute solution video

**Required.** Use [`VIDEO_SCRIPT.md`](VIDEO_SCRIPT.md).

**Suggested capture:** screen-record `python run.py` and narrate over it. The
console output already shows the named decision owner, the abstention reason,


---

# The five rubric answers

These five boxes are the judging surface. Drafted at a length a judge can
actually read.

## 11. Relationships & Consequences — *Who is affected, and what changes for them?*

Four groups, and one that is easy to forget.

**The people in orbit.** The fleet includes the ISS, where six people are
currently aboard. For that object an "anomaly" is a life-safety question, not
a data-quality one, and each finding is tagged with that stakes level
(`crewed`, `science`, `public`, `commercial`) so a human can triage on it.

**Everyone downstream of weather satellites.** NOAA 15/18/19/20 and Terra/Aqua
feed forecasting, hurricane tracking and disaster monitoring. Silent
degradation of one of these is felt by people who will never know it happened —
which is the argument for abstaining loudly rather than quietly.

**The operators, not just the satellites.** This is the group most at risk in
the challenge owner's framing. If a system becomes reliable, operators stop
forming their own judgement, and the skill is gone exactly when it is needed.
That is why every finding names a human decision owner, why output is labelled
a *recommendation rather than an instruction*, and why overrides are logged —
so the operator's corrections accumulate instead of being overwritten.

**And the objects we never looked at.** On a live run one satellite could not
be resolved, and the system reported it *absent* rather than silently shrinking
the fleet. An unfilled gap in coverage looks identical to a quiet sky, so the
system is required to say which questions it did not answer. That group is
affected by every omission in this submission — which is why the limitations
are published in machine-readable form rather than in a footnote.

## 12. Knowledge, Authority & Reciprocity — *What does it draw on, and who should be credited?*

**The question is not ours.** It was posed by Karima El Kassem in this
youth-led challenge from Morocco, with Hamid Idelbacha as mentor. Their framing
of automation complacency and false confidence is the design requirement, and
this submission is a response to it.

**The framing of obligation is NARETU**, developed by Chief Titus Letaapo
drawing on Indigenous Samburu governance principles. We apply it on its own
terms — as a question to ask, not as a variable to optimise. We did not
translate it into a scoring function, and we state why: the knowledge-holder
decides what belongs inside a technical system, and that authority is not ours
to assume. ICIP and community consent take precedence over anything here.

**The technical foundations** are not ours either: SGP4 (Vallado et al.), the
US Standard Atmosphere density model behind our decay envelopes, and
CelesTrak's public element-set catalogue, which is public domain.

**What we owe back.** Reciprocity means the people whose thinking shaped the
*questions* get credit for it, and that borrowing a framework does not transfer
authority over it to us. We keep that visible rather than folded into a
footnote — every object in the fleet carries a `stakes` note explaining who is
affected, so the reader is never asked to take the value judgement on trust
from the machine.

## 13. Orbital Stewardship & Justice — *How does it treat orbit as a shared responsibility?*

By **refusing** the decision that would make it look like it treats orbit as
someone's private property.

When two objects are at risk, something must give: observation time, a
manoeuvre, a shutdown call. Choosing what to protect first is a *normative*
question, and this system explicitly declines to answer it: it ranks nothing by
value at risk and has no basis for preferring a crewed satellite to a weather
satellite. That limitation is emitted at runtime into `out/never_seen.json`
and printed on every run, so it travels with the artefact rather than living
in a README someone may never open.



## 14. Responsible AI & Accountability — *What does the AI do, and who remains accountable?*

**There is no trained model in the decision path.** The detector is arithmetic:
SGP4 propagation, a robust median/MAD z-score, a least-squares trend test
judged by its t-statistic, a threshold comparison, and a comparison of two
independently published element sets. No learned parameter, no black box.

**Every finding names a human decision owner** — for the ISS, the duty
spacecraft operator with crew-safety authority; for weather spacecraft, the
constellation operations centre. Output is always labelled *RECOMMENDATION
ONLY, not an instruction*, and confirmed candidates are automatically logged
as `DEFER` pending human confirmation rather than actioned.

**Overrides are recorded permanently.** If operators routinely reject a class
of alert, that disagreement is evidence the model is wrong, and it can only be
noticed if it is written down rather than discarded. The log reports its own
rejection rate for that reason.

**Abstention is a first-class output** behind five gates: empty series,
non-finite data, stale element sets, altitude outside the object's published
band, and orbits outside the validated regime. On the live run it withheld
assessment entirely for a satellite served a 1002-day-old element set, and
flagged-then-refused a manoeuvre rather than calling it debris.

For transparency: generative AI (Claude, via the Cline coding assistant) was
used to *build* this, and is disclosed in full in `docs/AI_USE_DISCLOSURE.md`,
including nine specific errors it introduced that were caught by testing. It
is not part of the solution's decision logic.

## 15. From Obligation to Action — *What could happen next, and who could do it?*

The obligation ("the tool should say when it is unsure") is turned into a
concrete step, assigned to a person, in every finding: **a named owner must
confirm or reject.** Confirmed candidates cannot sit silently; they are logged
`DEFER`, which forces a human decision with a timestamp.

The recommendation itself is a next action, not a verdict — for a real
divergence it says *obtain a third independent element set before acting*,
because two disagreeing sources are a reason to look, not to act.

Three things are already in place for whoever picks this up. The cross-epoch


---

## 16. AI use

```
Yes.

Tools: Claude (Anthropic), via the Cline coding assistant in VS Code, for code
drafting, debugging, scientific review and documentation. pypdf (open-source
library, not an AI tool) to extract the text of the participant booklet.

What it was used for: understanding the challenge; drafting and debugging all
code; writing the documentation; and interrogating the statistical design.

What we independently checked - every claim below was verified by running it,
not by reading it:
- SGP4 returns position from the Earth's centre. Our first result gave the ISS
  an altitude of 6.8 km. Corrected by subtracting Earth's radius, giving
  418.5 km, which matches the published orbit.
- A residual against a moving average is mathematically incapable of detecting
  a linear drift, because the moving average of a linear series reproduces that
  series exactly. Our first working detector was therefore blind to the very
  phenomenon this challenge is about. Found by writing a self-test and watching
  it fail, not by inspection.
- A global z-score cannot detect sustained drift at all: standardising a linear
  ramp caps its maximum |z| near 1.73 however steep the ramp is, so a 3-sigma
  threshold is mathematically unreachable. This forced a separate trend test.
- Deriving altitude from an element set's eccentricity gives the MEAN altitude
  of the ellipse - about 3 km for the ISS, not 420 km. This produced a
  cross-epoch "divergence" of 793 km that would have been reported as a fault.
- Two configured altitude bands were wrong; both corrected from measurement.
- A fallback data source silently returned 0 of 9 objects because it names its
  catalogue field differently. The pipeline looked like "no anomalies found"
  rather than "no data".
- One satellite was served an element set 1002 days old, and one satellite
  cannot be resolved at all. Both are now refused or reported absent.

Nine such errors are listed in full in docs/AI_USE_DISCLOSURE.md. The
self-test (python run.py --self-test, 11 assertions) exists so this class of
error cannot return silently.

Whether AI forms part of the solution: NO, not in the decision logic. The
detector is arithmetic - SGP4 propagation, a robust z-score, a least-squares
trend test, a threshold comparison, and a comparison of two independently
published element sets. There is no trained model, no learned parameter, and no
model output accepted without execution. AI assisted in writing the code that
implements those operations; it did not supply predictions, classifications or
orbital assessments. It did contribute to the design, and the most valuable
contribution was questioning the science rather than writing the code.

Human participants remain responsible for this work, including its errors.
```

## 17. Sharing restrictions

```
None.

This submission contains no material with sharing restrictions. It uses only
public-domain orbital data (TLE element sets from CelesTrak and a public
per-satellite mirror) and open-source software (numpy, BSD; sgp4, Apache 2.0).

No Indigenous knowledge, story, artwork, recording or community-held material
was used, accessed, reproduced, or uploaded anywhere in this work. The NARETU
framework is referenced as a named, attributed framework originating in Chief
Titus Letaapo's Samburu governance work; it is cited, not reproduced, and no
community content is redistributed.

Indigenous Cultural and Intellectual Property, community protocols and consent
conditions take precedence over this submission, and nothing in it should be
read as speaking for any Indigenous person or community.
```

## 18. Permission to share

```
Yes
```

baseline is pinned in version control, so the next run gets an independent
comparison for free rather than needing two element sets to exist first. The
`never_seen.json` register doubles as an onboarding checklist — it is the list
of things the system is not yet entitled to claim. And the loop is
object-count agnostic: a 600-object test processed with zero failures at ~331
objects/s, so continuous monitoring at catalogue scale is an infrastructure
decision, not a redesign.

The honest near-term action is narrower than the ambition: keep the fleet,
re-run it when new element sets publish, and let the abstention gates keep
saying "I don't know" until they can earn the right to say more.

Doing it responsibly would need published, contestable value-at-risk inputs, an
agreed weighting, a record of **who set the weights and why**, and a way for
affected parties to contest them. None of that exists here. A
`value_at_risk` score would have looked impressive and would have laundered a
political choice through the appearance of a number.

Across the time horizon the claim is smaller but real: the 90-day staleness
gate exists partly so that whoever operates this next is not handed a
1002-day-old element set as though it described today's orbit, and the
machine-readable list of what the system has never been shown is a message to
that next operator. Orbit is treated as inherited, not owned.

the cross-epoch result and the "never seen" register — the whole submission is
visible in one terminal.

## 9. Final work

```
https://github.com/gajjararyan/Project-yohaku
```

Run it: `pip install -r requirements.txt && python run.py --self-test`
(11 assertions covering every scientific claim) then `python run.py`.

## 10. Code repository

```
https://github.com/gajjararyan/Project-yohaku
```

Open source, MIT. Public.
