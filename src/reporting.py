"""Output rendering: console summary, machine-readable JSON, and a run manifest.

Everything written here is intended to be pasted straight into a submission,
so the wording is deliberate: claims are labelled as synthetic, abstentions are
reported as first-class results, and the manifest records the run so a reviewer
can reproduce it.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Dict, List, Sequence

from . import config
from .accountability import DecisionLog, Finding, never_seen_register
from .data_source import TleRecord

BANNER = r"""
=====================================================================
  Yohaku Challenge 5 - Orbital Anomaly Detection
  "The tool meant to help us see more could end up making us
   see less on our own."  - challenge owner's stated concern
=====================================================================
"""


def render_console(
    findings: Sequence[Finding],
    log: DecisionLog,
    records: Sequence[TleRecord],
) -> str:
    """Human-readable run summary, ordered by how much attention is needed."""
    rank = {
        "CONFIRMED": 0,
        "ARTEFACT_REJECTED": 1,   # flagged but not confirmed: worth seeing
        "ABSTAINED": 2,
        "NO_ANOMALY": 3,
    }
    ordered = sorted(findings, key=lambda f: (rank.get(f.status, 9), f.name))

    lines = [BANNER]
    lines.append(
        f"Fleet: {len(records)} objects | "
        f"Cadence: {config.SAMPLE_STEP_MINUTES} min over "
        f"{config.SAMPLE_SPAN_MINUTES} min | "
        f"Threshold: {config.Z_THRESHOLD} sigma\n"
    )

    icons = {
        "CONFIRMED": "[!] CONFIRMED CANDIDATE",
        "ABSTAINED": "[?] ABSTAINED",
        "ARTEFACT_REJECTED": "[x] ARTEFACT REJECTED",
        "NO_ANOMALY": "[.] no anomaly",
    }

    for f in ordered:
        lines.append(f"{icons.get(f.status, '[?]')}  {f.name} (NORAD {f.norad_id})")
        lines.append(f"    status      : {f.status}")
        lines.append(f"    basis       : {f.detector}")
        lines.append(f"    owner       : {f.decision_owner}")
        if f.stakes:
            lines.append(f"    stakes      : {f.stakes} - {f.why_it_matters}")
        if f.abstention_reason:
            lines.append(f"    abstained   : {f.abstention_reason}")
        if f.cross_epoch and f.cross_epoch.get("verdict"):
            ce = f.cross_epoch
            lines.append(
                f"    cross-epoch : {ce['verdict']} "
                f"(strength: {ce.get('strength', '?')})"
            )
        for item in f.evidence:
            lines.append(f"    evidence    : {item}")
        lines.append(f"    action      : {f.recommendation}")
        if f.ground_truth:
            correct = "yes" if f.detected_correctly else "no"
            lines.append(
                f"    ground truth: {f.ground_truth} "
                f"(synthetic; handled correctly: {correct})"
            )
        lines.append("")

    register = never_seen_register()
    lines.append("-" * 69)
    lines.append("WHAT THIS SYSTEM HAS NEVER BEEN SHOWN")
    for item in register["limitations"][:5]:
        lines.append(f"  - {item}")
    lines.append(f"  ... and {len(register['limitations']) - 5} more in out/never_seen.json")
    lines.append("")
    lines.append("HUMAN DECISIONS RECORDED: " + str(len(log.entries)))
    lines.append(
        "This system recommends. It does not command. A named human owner "
        "decides."
    )
    lines.append("=" * 69)
    return "\n".join(lines)


def write_reports(
    findings: Sequence[Finding],
    log: DecisionLog,
    records: Sequence[TleRecord],
    verbose: bool = True,
) -> Dict[str, str]:
    """Write all output artefacts and return their paths."""
    if verbose:
        print("[report] writing artefacts...")

    findings_path = config.OUT_DIR / "findings.json"
    findings_path.write_text(
        json.dumps([f.to_dict() for f in findings], indent=2), encoding="utf-8"
    )

    register_path = config.OUT_DIR / "never_seen.json"
    register_path.write_text(json.dumps(never_seen_register(), indent=2), encoding="utf-8")

    log_path = config.OUT_DIR / "decision_log.json"
    log_path.write_text(log.to_json(), encoding="utf-8")

    summary = {
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "challenge": "Yohaku Challenge 5 - AI Approaches for Orbital Anomaly Detection",
        "data_provenance": {
            "sources": sorted({r.source for r in records}),
            "objects": len(records),
            "note": (
                "TLEs are operator-published least-squares fits, not ground "
                "truth. All injected anomalies are synthetic."
            ),
        },
        "parameters": {
            "z_threshold": config.Z_THRESHOLD,
            "min_consecutive_samples": config.MIN_CONSECUTIVE_SAMPLES,
            "plausible_decay_km_per_day": list(config.PLAUSIBLE_DECAY_KM_PER_DAY),
            "sample_step_minutes": config.SAMPLE_STEP_MINUTES,
        },
        "counts": {
            status: sum(1 for f in findings if f.status == status)
            for status in ("CONFIRMED", "ABSTAINED", "ARTEFACT_REJECTED", "NO_ANOMALY")
        },
        "findings": [f.to_dict() for f in findings],
        "never_seen": never_seen_register(),
        "human_decisions": json.loads(log.to_json())["summary"],
    }
    summary_path = config.OUT_DIR / "summary.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    return {
        "summary": str(summary_path),
        "findings": str(findings_path),
        "never_seen": str(register_path),
        "decision_log": str(log_path),
    }
