"""Decision accountability: who is responsible, on what terms, and when unsure.

This module answers the challenge's central worry, quoted from the booklet:
*"If the AI becomes good at detecting known types of anomalies, operators might
start relying on it by default and stop training their own eye for it... The
tool meant to help us see more could end up making us see less on our own."*

Three mechanisms implement that concern concretely:

* :class:`Finding` always names a **human decision owner** and labels output a
  *recommendation*, never an instruction.
* :class:`DecisionLog` records every override, so operator corrections
  accumulate instead of being discarded -- the skill at risk of erosion is
  preserved rather than overwritten.
* :func:`never_seen_register` is emitted as machine-readable output, so the
  system states its own blind spots instead of letting a confident tone imply
  coverage it does not have.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional, Sequence

from . import config
from .data_source import TleRecord
from .detection import Candidate
from .orbits import Sample, classify_regime


@dataclass
class Finding:
    """A per-object assessment, including a deliberate 'no opinion' outcome."""

    norad_id: int
    name: str
    stakes: str
    why_it_matters: str
    status: str        # CONFIRMED | ARTEFACT_REJECTED | NO_ANOMALY | ABSTAINED
    recommendation: str
    decision_owner: str
    human_in_the_loop: bool
    evidence: List[str] = field(default_factory=list)
    abstained: bool = False
    abstention_reason: Optional[str] = None
    ground_truth: Optional[str] = None
    detected_correctly: Optional[bool] = None
    detector: str = "single-TLE trend"
    cross_epoch: Optional[Dict[str, object]] = None

    def to_dict(self) -> Dict[str, object]:
        return asdict(self)


# Roles, not names. A real deployment maps these to rostered operators; the
# important property is that accountability is *assigned*, never implicit.
DECISION_OWNERS = {
    "crewed": "Duty spacecraft operator (crew safety authority)",
    "science": "Mission science team lead",
    "public": "Constellation operations centre",
    "commercial": "Commercial fleet operations team",
}


def _assess_regime(mean_altitude_km: float) -> Optional[str]:
    """Return a reason string if the object is outside validated regimes."""
    regime = classify_regime(mean_altitude_km)
    if regime not in config.VALIDATED_REGIMES:
        return (
            f"Object is in {regime}, but this detector has only been validated "
            f"in {'/'.join(config.VALIDATED_REGIMES)}. No confident claim is made."
        )
    return None


def _check_integrity(
    record: TleRecord, spec: Dict[str, object], samples: Sequence[Sample]
) -> Optional[str]:
    """Sanity-check the inputs before any orbital claim is made.

    Three independent failure modes, each of which would otherwise produce a
    confident and wrong answer:

    1. **Staleness** - a TLE is a least-squares fit that decays with age. An
       element set served over a year old describes an orbit that may no
       longer exist. (Observed live: one satellite arrived 1002 days stale.)
    2. **Out-of-band altitude** - a propagated altitude far outside the
       object's published band indicates a unit or data fault upstream.
    3. **Empty series** - nothing to assess.
    """
    if not samples:
        return (
            f"No usable state vectors were produced for {record.name}, so there "
            f"is nothing to assess. Withheld rather than guessed."
        )

    epoch = record.epoch
    if epoch is None:
        return (
            f"The element-set epoch for {record.name} could not be parsed, so "
            f"the freshness of the data cannot be established. Withheld."
        )
    age_days = (datetime.now(timezone.utc) - epoch).days
    if age_days > config.MAX_TLE_AGE_DAYS:
        return (
            f"Element set is {age_days} days old (limit "
            f"{config.MAX_TLE_AGE_DAYS} days). A TLE is a least-squares fit "
            f"that degrades with age, and this object may have manoeuvred since. "
            f"Any anomaly claim from it would be confident and unfounded, so "
            f"the assessment is withheld pending a fresh element set."
        )
    band = spec.get("altitude_band_km")
    if not band:
        return None
    low, high = band  # type: ignore[misc]
    mean_alt = sum(s.altitude_km for s in samples) / max(1, len(samples))
    if not (low <= mean_alt <= high):
        return (
            f"Propagated mean altitude {mean_alt:.0f} km falls outside the "
            f"expected {low:.0f}-{high:.0f} km band for {record.name}. This "
            f"points to a data or unit fault upstream, so anomaly scoring is "
            f"withheld rather than reported."
        )
    return None


def staleness_note(record: TleRecord) -> Optional[str]:
    """Surface moderate data staleness in the evidence rather than hide it."""
    epoch = record.epoch
    if epoch is None:
        return None
    age_days = (datetime.now(timezone.utc) - epoch).days
    if config.TLE_CAUTION_DAYS < age_days <= config.MAX_TLE_AGE_DAYS:
        return (
            f"CAVEAT: element set is {age_days} days old. The assessment "
            f"proceeds, but the orbit may have changed since publication and "
            f"the result should be discounted accordingly."
        )
    return None



def assess_cross_epoch(result: Optional[Dict[str, object]]) -> Optional[Dict[str, object]]:
    """Grade cross-epoch evidence into a labelled, honest verdict.

    Deliberately conservative in both directions:

    * Two epochs too close together prove nothing and are reported as
      ``INSUFFICIENT_SEPARATION``, never as agreement.
    * Excellent agreement over a long baseline is reported as
      ``CORROBORATED_NO_SIGNAL``. That is weaker than it sounds: propagating a
      78-day-old fit forward accumulates error regardless of the object, so
      agreement mostly indicates the object behaved, not that the method is
      validated.
    """
    if result is None:
        return {
            "verdict": "NOT_AVAILABLE",
            "strength": "none",
            "explanation": (
                "No independently published second element set was obtainable, "
                "so this detector produced no evidence. Absence of a second "
                "epoch is not evidence of an absence of anomalies."
            ),
        }

    if "error" in result:
        return {
            "verdict": "ERROR",
            "strength": "none",
            "explanation": str(result["error"]),
        }

    separation = float(result["separation_hours"])  # type: ignore[arg-type]
    divergence = float(result["divergence_km"])      # type: ignore[arg-type]

    base = {
        "separation_hours": round(separation, 2),
        "divergence_km": round(divergence, 2),
        "predicted_altitude_km": round(float(result["predicted_altitude_km"]), 1),  # type: ignore[arg-type]
        "observed_altitude_km": round(float(result["observed_altitude_km"]), 1),    # type: ignore[arg-type]
    }

    # Two epochs from the same generation are not independent evidence. This
    # must be checked BEFORE any agreement is claimed, otherwise two near-
    # identical fits would be reported as corroboration.
    if separation < config.CROSS_EPOCH_MIN_SEPARATION_HOURS:
        return {
            **base,
            "verdict": "INSUFFICIENT_SEPARATION",
            "strength": "none",
            "explanation": (
                f"The two element sets are only {separation:.2f} h apart, below "
                f"the {config.CROSS_EPOCH_MIN_SEPARATION_HOURS} h minimum. They "
                f"are effectively the same data, so their agreement is not "
                f"evidence of anything."
            ),
        }

    if divergence >= config.CROSS_EPOCH_DATA_FAULT_KM:
        return {
            **base,
            "verdict": "DATA_FAULT_SUSPECTED",
            "strength": "strong",
            "explanation": (
                f"Propagating the older fit forward to the newer epoch "
                f"({separation:.1f} h apart) lands {divergence:.1f} km from what "
                f"the newer fit states. That is far too large to be orbital "
                f"behaviour, so at least one element set is faulty. This is a "
                f"data-integrity finding, not an anomaly in the object."
            ),
        }

    if divergence >= config.CROSS_EPOCH_MIN_SEPARATION_IS_NOISE_KM:
        return {
            **base,
            "verdict": "DIVERGENCE_DETECTED",
            "strength": "strong",
            "explanation": (
                f"Over a {separation:.1f} h baseline the older fit predicts an "
                f"altitude {divergence:.1f} km from the newer fit's own value. "
                f"This is an INDEPENDENT measurement: the two element sets were "
                f"produced separately, so this is not the model confirming "
                f"itself. Either the object departed from the older fit's "
                f"prediction, or one fit is poor. Both warrant a human."
            ),
        }

    if divergence <= config.CROSS_EPOCH_STRONG_AGREEMENT_KM:
        return {
            **base,
            "verdict": "CORROBORATED_NO_SIGNAL",
            "strength": "moderate",
            "explanation": (
                f"Two independently published element sets, {separation:.1f} h "
                f"apart, agree to within {divergence:.1f} km. This is genuine "
                f"external corroboration that the object behaved as its earlier "
                f"fit predicted. It is NOT proof of health: much of this "
                f"agreement reflects accumulated error in the older fit over the "
                f"baseline, so it is weak positive evidence at best."
            ),
        }

    return {
        **base,
        "verdict": "WITHIN_NOISE",
        "strength": "weak",
        "explanation": (
            f"Divergence of {divergence:.1f} km over {separation:.1f} h is below "
            f"the {config.CROSS_EPOCH_DATA_FAULT_KM:.0f} km fault threshold and "
            f"too large to be meaningful agreement. No signal either way."
        ),
    }

def build_finding(
    record: TleRecord,
    spec: Dict[str, object],
    samples: Sequence[Sample],
    candidates: Sequence[Candidate],
    cross_epoch: Optional[Dict[str, object]] = None,
) -> Finding:
    """Turn detector output into an accountable, abstention-aware finding."""
    stakes = str(spec.get("stakes", "public"))
    owner = DECISION_OWNERS.get(stakes, "Operations duty officer")
    mean_alt = sum(s.altitude_km for s in samples) / max(1, len(samples))
    epoch = record.epoch.isoformat() if record.epoch else "unparsed"
    evidence = [
        f"Propagated {len(samples)} samples at {config.SAMPLE_STEP_MINUTES}-minute "
        f"cadence; mean altitude {mean_alt:.1f} km, regime {classify_regime(mean_alt)}.",
        f"TLE epoch {epoch}, source: {record.source}.",
    ]

    finding = Finding(
        norad_id=record.norad_id,
        name=record.name,
        stakes=stakes,
        why_it_matters=str(spec.get("why", "")),
        status="NO_ANOMALY",
        recommendation="No action indicated. Continue routine monitoring.",
        decision_owner=owner,
        human_in_the_loop=True,
        evidence=evidence,
        detector="single-TLE trend",
    )

    # Cross-epoch evidence is independent of the single-TLE propagation, so it
    # is recorded on every finding regardless of outcome, including abstentions.
    cross_assessment = assess_cross_epoch(cross_epoch)
    finding.cross_epoch = cross_assessment
    if cross_assessment:
        finding.evidence.append(
            f"[cross-epoch / independent] {cross_assessment['verdict']}: "
            f"{cross_assessment['explanation']}"
        )
        # Promote the finding's stated basis to the stronger, independent test
        # whenever that test produced actionable evidence.
        if cross_assessment.get("verdict") in {"DIVERGENCE_DETECTED", "DATA_FAULT_SUSPECTED"}:
            finding.detector = "cross-epoch divergence"
            finding.status = "CONFIRMED"
            finding.recommendation = (
                f"RECOMMENDATION ONLY, not an instruction: two independently "
                f"published element sets disagree by "
                f"{cross_assessment.get('divergence_km')} km. This is external "
                f"evidence, not a self-prediction. {owner} should obtain a third "
                f"independent fix before acting."
            )
            return finding

    # Surface moderate staleness rather than letting it pass unremarked.
    caveat = staleness_note(record)
    if caveat:
        finding.evidence.append(caveat)

    # -- abstain whenever the inputs are not trustworthy -------------------
    integrity = _check_integrity(record, spec, samples)
    if integrity:
        finding.status = "ABSTAINED"
        finding.abstained = True
        finding.abstention_reason = integrity
        finding.recommendation = (
            "WITHHELD: the underlying data failed an integrity check. A named "
            "operator must resolve the data fault before any orbital claim is made."
        )
        finding.evidence.append(integrity)
        return finding

    regime_issue = _assess_regime(mean_alt)
    if regime_issue:
        finding.status = "ABSTAINED"
        finding.abstained = True
        finding.abstention_reason = regime_issue
        finding.recommendation = (
            "WITHHELD: this object is outside the regimes this detector has been "
            "validated in. Reporting a confident anomaly here would exceed the evidence."
        )
        finding.evidence.append(regime_issue)
        return finding

    if not candidates:
        return finding

    confirmed = [c for c in candidates if c.confirmed]
    rejected = [c for c in candidates if not c.confirmed]
    for cand in candidates:
        evidence.append(f"[{cand.verdict}] {cand.rationale}")
        if cand.ground_truth:
            finding.ground_truth = cand.ground_truth

    if rejected and not confirmed:
        # Something WAS flagged, and the gate refused to confirm it. That is a
        # materially different outcome from "nothing was found", and collapsing
        # the two would hide the most interesting thing the system does.
        finding.status = "ARTEFACT_REJECTED"
        verdicts = {c.verdict for c in rejected}
        if "REGIME_IMPLAUSIBLE_REJECTED" in verdicts:
            finding.recommendation = (
                f"FLAGGED, NOT CONFIRMED. A change was detected but is not "
                f"consistent with passive drag at this altitude, so it is more "
                f"likely a manoeuvre, a deployment, or a data fault than debris "
                f"decay. No debris action. {finding.decision_owner} should "
                f"check the manoeuvring history before this is dismissed."
            )
        else:
            finding.recommendation = (
                "No action. Statistical excursions were raised and then rejected "
                "on physical grounds. Recorded so the rejection is reviewable "
                "rather than silent."
            )
        if finding.ground_truth:
            finding.detected_correctly = True
        return finding

    if confirmed:
        best = max(confirmed, key=lambda c: abs(c.peak_z))
        finding.status = "CONFIRMED"
        finding.recommendation = (
            f"RECOMMENDATION ONLY, not an instruction: request ground follow-up "
            f"observation of {record.name} and have {owner} confirm or reject. "
            f"Implied drift {best.drift_km_per_day:+.2f} km/day, peak excursion "
            f"{best.peak_z:.1f} sigma. The decision to act rests with the named owner."
        )
        if finding.ground_truth:
            finding.detected_correctly = True

    return finding



class DecisionLog:
    """Append-only record of human decisions taken against model output.

    The point of keeping overrides is not audit for its own sake. If operators
    routinely reject a class of alert, that disagreement is evidence the model
    is wrong -- and the only way it can be noticed is if it is written down
    rather than lost. This is the mechanism that keeps the operator's skill
    alive rather than eroding it through silent automation.
    """

    def __init__(self) -> None:
        self.entries: List[Dict[str, object]] = []

    def record(
        self,
        norad_id: int,
        name: str,
        decision: str,
        operator: str,
        note: str = "",
    ) -> None:
        if decision not in {"ACCEPT", "REJECT", "DEFER"}:
            raise ValueError(f"decision must be ACCEPT, REJECT or DEFER, got {decision!r}")
        self.entries.append({
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "norad_id": norad_id,
            "name": name,
            "decision": decision,
            "operator": operator,
            "note": note,
        })

    def rejection_rate(self) -> float:
        if not self.entries:
            return 0.0
        rejected = sum(1 for e in self.entries if e["decision"] == "REJECT")
        return rejected / len(self.entries)

    def to_json(self) -> str:
        return json.dumps(
            {
                "entries": self.entries,
                "summary": {
                    "total": len(self.entries),
                    "rejection_rate": round(self.rejection_rate(), 3),
                    "note": (
                        "A rising rejection rate is a signal that the detector, "
                        "not the operator, needs attention."
                    ),
                },
            },
            indent=2,
        )


def never_seen_register() -> Dict[str, object]:
    """Machine-readable statement of what this system has never been shown."""
    return {
        "statement": (
            "This detector has not been tested against a real orbital anomaly, a "
            "real attack, or a real collision-avoidance decision. Every anomaly "
            "used to validate it is synthetic."
        ),
        "validated_regimes": list(config.VALIDATED_REGIMES),
        "limitations": list(config.NEVER_SEEN_REGISTER),
        "escalation_policy": (
            "The system never authorises a manoeuvre. It produces ranked "
            "recommendations for named human owners, and abstains when the "
            "evidence does not support a claim."
        ),
    }
