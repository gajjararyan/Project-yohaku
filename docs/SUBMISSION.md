# Submission Information

Copy the fields below into the submission form. Everything here is also present
in `README.md` and `docs/AI_USE_DISCLOSURE.md`.

---

## Title

**Seeing Less: a detector that knows when it is wrong, and who answers when it is**

## Challenge selected

**Challenge 5: AI Approaches for Orbital Anomaly Detection**
Youth-led, Morocco. Presented by Karima El Kassem. Mentor: Hamid Idelbacha.

## Participant / team name(s)

**Team name:** Supernova Systems
**Participant:** Aryan Gajjar (solo participant)

Submitted as a solo entry under the team name *Supernova Systems*. The booklet
asks for participant/team names in the entry, and requires one team member to
submit one final entry — that member is Aryan Gajjar.

## Short summary (for a judge skimming — ~90 words)

We built a working detector for unusual changes in satellite orbits, running on
real orbital data. Its most important feature is not that it finds things — it
is that it *declines to*. We discovered that a model predicting its own future
is not evidence: a single propagation always "detects" drag decay, because the
model predicts decay. We also found that real 24-hour altitude variation is
*larger* than any plausible decay signal. So the system's primary claim rests
on comparing two **separately published** descriptions of the same satellite
(up to 78 days apart, agreeing to within 0.6 km), and it publishes a
machine-readable list of everything it has never been tested on. It never raises
an alarm without naming the person answerable for it.

## Work

- **Prototype / code:** the repository README (open source, MIT).
- **Runnable:** `python run.py` — see README quickstart.
- **Generated evidence:** `out/summary.json`, `out/findings.json`,
  `out/never_seen.json`, `out/decision_log.json`.
- **Self-test:** `python run.py --self-test` — 11 assertions covering every
  scientific claim in this submission.

Repository URL: **https://github.com/gajjararyan/Project-yohaku** (public, MIT).
Pushed and verified live: the repository page shows *Public*, branch `main`, and
this README rendering correctly.

## AI-use disclosure

Present and included: [`docs/AI_USE_DISCLOSURE.md`](AI_USE_DISCLOSURE.md).
Also summarised in `README.md` §7.

## Limits on public sharing

**None.** This submission contains no material with sharing restrictions. It
uses only:

- **Public orbital data** — TLE element sets published by CelesTrak (public
  domain) and a public per-satellite mirror. These are operator-published
  least-squares fits, freely redistributable.
- **Open-source software** — `numpy` (BSD) and `sgp4` (Apache 2.0).

**No Indigenous knowledge, story, artwork, recording, or community-held
material was used, accessed, reproduced, or uploaded anywhere in this work.**
The NARETU framework is referenced as a named, attributed framework originating
in Chief Titus Letaapo's Samburu governance work; it is cited, not reproduced,
and no community content is redistributed. Indigenous Cultural and Intellectual
Property, community protocols, and consent conditions take precedence over this
submission, and nothing here should be read as speaking for any Indigenous
person or community.
