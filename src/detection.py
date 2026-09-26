"""Anomaly detection: two statistically distinct tests, then a physics gate.

Why two tests rather than one
-----------------------------
A single global z-score cannot do this job, and the failure is instructive:

* A **sustained drift** (drag decay) is a *trend*. Standardising a linear ramp
  against its own mean and standard deviation caps its maximum |z| near 1.73
  *however steep the ramp is*, so a 3-sigma threshold is unreachable. Detecting
  a trend requires a trend test.
* A **point anomaly** (one corrupted sample) has no trend at all. A regression
  slope would dilute it to nothing, so detecting an impulse requires an impulse
  test.

Worse, a residual against a *moving average* is mathematically incapable of
detecting a linear drift: the moving average of a linear series reproduces that
series exactly, so the residual is identically zero. That was a genuine bug,
caught by ``run.py --self-test`` rather than by inspection.

Detection therefore runs three stages:

  Stage 1a  impulse  - robust (median/MAD) z-score on residuals from a
                       detrended baseline.
  Stage 1b  trend    - least-squares slope judged by its t-statistic, so
                       significance is measured against the *noise*, not
                       against the magnitude of the signal.
  Stage 2   physics  - persistence plus a plausibility check on the implied
                       drift rate. Only this stage may reject a candidate.

Anything surviving all stages is still a *recommendation*, routed to a named
human owner in :mod:`accountability`. This module never declares an orbit lost.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence

import numpy as np

from . import config
from .orbits import Sample, classify_regime


@dataclass
class Candidate:
    """A flagged excursion, with the evidence that justifies it."""

    start_index: int
    end_index: int
    peak_z: float
    mean_altitude_km: float
    drift_km_per_day: float
    persistent: bool
    physically_plausible: bool
    verdict: str
    rationale: str
    detector: str = "trend"        # which stage raised it
    ground_truth: Optional[str] = None
    extra: Dict[str, object] = field(default_factory=dict)

    @property
    def confirmed(self) -> bool:
        return self.persistent and self.physically_plausible


def _moving_average(values: np.ndarray, window: int = 3) -> np.ndarray:
    """Centred moving average in 'valid' mode.

    'valid' shortens the result by ``window - 1``; callers must slice the
    original array to match rather than broadcasting against it. Getting this
    wrong is the most common bug in this kind of pipeline.
    """
    kernel = np.ones(window) / float(window)
    return np.convolve(values, kernel, mode="valid")


def residuals(altitudes: Sequence[float], window: int = 3) -> np.ndarray:
    """Residual against a centred moving average, correctly aligned.

    NOTE: exposes *impulses* only. It is blind to linear drift by construction,
    because the moving average of a linear series reproduces that series.
    """
    values = np.asarray(altitudes, dtype=float)
    baseline = _moving_average(values, window)
    half = (window - 1) // 2
    trimmed = values[half: len(values) - half] if half else values
    return trimmed[: len(baseline)] - baseline


def detrended_residuals(altitudes: Sequence[float]) -> np.ndarray:
    """Residual after removing a least-squares *linear* trend.

    This is the baseline the impulse test needs: removing a fitted line (rather
    than a moving average) leaves point anomalies intact while genuinely
    absorbing sustained drift, which the moving average cannot do.
    """
    values = np.asarray(altitudes, dtype=float)
    if values.size < 3:
        return np.zeros_like(values)
    x = np.arange(values.size, dtype=float)
    slope, intercept = np.polyfit(x, values, 1)
    return values - (slope * x + intercept)


def robust_z(values: Sequence[float]) -> np.ndarray:
    """Median/MAD z-score, which a single wild sample cannot destabilise.

    Uses the median and median-absolute-deviation rather than mean and standard
    deviation precisely because the impulse we are hunting *is* a wild sample.
    The scale is floored at :data:`config.MIN_NOISE_SIGMA_KM` so that a
    near-perfectly clean series cannot manufacture an absurd confidence.
    """
    data = np.asarray(values, dtype=float)
    if data.size == 0:
        return data
    median = np.median(data)
    mad = np.median(np.abs(data - median))
    scale = 1.4826 * mad            # MAD -> sigma equivalent for normal data
    if scale < config.MIN_NOISE_SIGMA_KM:
        scale = max(data.std(), config.MIN_NOISE_SIGMA_KM)
    return (data - median) / scale


def trend_test(altitudes: Sequence[float]) -> Dict[str, float]:
    """Least-squares slope with a t-statistic.

    Significance is measured against the residual scatter, so a steep but
    perfectly smooth drift is significant while noise masquerading as a drift
    is not. The scatter estimate is floored for the same reason as in
    :func:`robust_z`. Returns slope in km per sample.
    """
    values = np.asarray(altitudes, dtype=float)
    n = values.size
    if n < 3:
        return {"slope": 0.0, "t_stat": 0.0, "residual_sigma": 0.0}
    x = np.arange(n, dtype=float)
    slope, intercept = np.polyfit(x, values, 1)
    fitted = slope * x + intercept
    resid = values - fitted
    dof = n - 2
    if dof <= 0:
        return {"slope": float(slope), "t_stat": 0.0,
                "residual_sigma": config.MIN_NOISE_SIGMA_KM}
    raw_sigma = float(np.sqrt(np.sum(resid ** 2) / dof))
    sigma = max(raw_sigma, config.MIN_NOISE_SIGMA_KM)
    sxx = float(np.sum((x - x.mean()) ** 2))
    if sxx <= 0:
        return {"slope": float(slope), "t_stat": 0.0, "residual_sigma": sigma}
    slope_stderr = sigma / np.sqrt(sxx)
    t_stat = float(slope / slope_stderr) if slope_stderr > 0 else 0.0
    return {"slope": float(slope), "t_stat": t_stat, "residual_sigma": sigma}


def plausible_decay_band_km_per_day(altitude_km: float) -> Dict[str, object]:
    """Return the physically plausible decay envelope for this altitude.

    A single flat band treats a 400 km object and an 800 km object as equally
    able to decay at 20 km/day, which is physically wrong: atmospheric density
    falls by roughly three orders of magnitude across that range. This scales
    the envelope by altitude so a high object cannot be excused by a loose band
    that only suits a low one.
    """
    regime = "MEO"
    # Walk DESCENDING thresholds and keep the last match, so an 820 km object
    # selects LEO-800 rather than stopping at the first (400 km) threshold.
    for threshold, name in config.REGIME_BOUNDARIES_KM:
        if altitude_km >= threshold:
            regime = name
    low, high = config.PLAUSIBLE_DECAY_BANDS_BY_REGIME[regime]
    return {
        "regime": regime,
        "min_km_per_day": low,
        "max_km_per_day": high,
        "altitude_km": round(altitude_km, 1),
    }


def _drift_km_per_day(altitudes: Sequence[float], start: int, end: int) -> float:
    """Signed altitude change per day across the candidate window."""
    span_minutes = config.SAMPLE_STEP_MINUTES * max(1, (end - start))
    if span_minutes <= 0:
        return 0.0
    return ((altitudes[end] - altitudes[start]) / span_minutes) * 1440.0



def _judge(
    samples: Sequence[Sample],
    altitudes: Sequence[float],
    s0: int,
    s1: int,
    peak_z: float,
    detector: str,
    min_consecutive: int,
) -> Optional[Candidate]:
    """Apply the physics gate to a candidate window and explain the verdict.

    Only this function may reject a candidate. Statistics decide what is worth
    looking at; physics decides what is believable.
    """
    run_length = (s1 - s0) + 1
    persistent = run_length >= min_consecutive
    drift = _drift_km_per_day(altitudes, s0, s1)
    low, high = config.PLAUSIBLE_DECAY_KM_PER_DAY
    # A passive object cannot climb without a manoeuvre, so a large upward
    # excursion is as implausible as an impossibly fast decay.
    plausible_rate = low <= abs(drift) <= high and drift <= high

    window = samples[s0: s1 + 1]
    if not window:
        return None
    ground_truth = next((s.injected for s in window if s.injected), None)
    mean_alt = float(np.mean([s.altitude_km for s in window]))

    # Altitude-scaled envelope: a high object is held to a tighter physical
    # standard than a low one, because drag at 800 km is far weaker.
    band = plausible_decay_band_km_per_day(mean_alt)
    b_low = float(band["min_km_per_day"])   # type: ignore[arg-type]
    b_high = float(band["max_km_per_day"])  # type: ignore[arg-type]
    within_scaled_band = b_low <= abs(drift) <= b_high and drift <= b_high

    if not persistent:
        verdict = "ARTEFACT_REJECTED"
        rationale = (
            f"{detector} test flagged {peak_z:.1f} sigma but the excursion "
            f"lasted only {run_length} sample(s). Real orbital changes persist "
            f"across successive samples, whereas an isolated jump is far more "
            f"consistent with an ephemeris or decoding artefact. Rejected "
            f"without escalation, because escalating artefacts is how operators "
            f"learn to ignore real alerts."
        )
    elif not plausible_rate:
        verdict = "IMPLAUSIBLE_RATE_REJECTED"
        rationale = (
            f"Excursion persisted {run_length} samples but implies "
            f"{drift:+.1f} km/day, outside the {low}-{high} km/day coarse "
            f"envelope for passive objects. Treated as a data-integrity "
            f"problem, not an orbital event."
        )
    elif not within_scaled_band:
        verdict = "REGIME_IMPLAUSIBLE_REJECTED"
        rationale = (
            f"Excursion persisted {run_length} samples at {mean_alt:.0f} km, "
            f"implying {drift:+.2f} km/day. That falls outside the "
            f"{b_low}-{b_high} km/day envelope physically achievable in the "
            f"{band['regime']} regime, so it is rejected as decay -- though it "
            f"is retained for review, because a manoeuvre or a genuine anomaly "
            f"could also produce it."
        )
    else:
        verdict = "CONFIRMED_CANDIDATE"
        rationale = (
            f"{detector} test: {peak_z:.1f} sigma, persisting {run_length} "
            f"samples, implying {drift:+.2f} km/day at {mean_alt:.0f} km - "
            f"inside the {b_low}-{b_high} km/day {band['regime']} envelope. "
            f"NOTE: this is single-TLE propagation, so it cannot separate a real "
            f"event from the secular decay the model itself predicts. See the "
            f"cross-epoch detector for an independent check. Human "
            f"confirmation required before any action."
        )

    # The physics gate is the ONLY stage permitted to reject, so "confirmed"
    # is derived from the verdict rather than from the intermediate booleans.
    # Deriving it from `persistent and plausible_rate` was wrong: that pair was
    # still True for REGIME_IMPLAUSIBLE_REJECTED, so a rejected candidate was
    # being reported as confirmed. Found by a self-test assertion.
    rejected = verdict in {
        "ARTEFACT_REJECTED",
        "IMPLAUSIBLE_RATE_REJECTED",
        "REGIME_IMPLAUSIBLE_REJECTED",
    }
    return Candidate(
        start_index=s0,
        end_index=s1,
        peak_z=peak_z,
        mean_altitude_km=mean_alt,
        drift_km_per_day=drift,
        persistent=persistent,
        physically_plausible=(not rejected) and plausible_rate,
        verdict=verdict,
        rationale=rationale,
        detector=detector,
        ground_truth=ground_truth,
        extra={
            "regime": classify_regime(mean_alt),
            "run_length": run_length,
            "scaled_band": band,
        },
    )


def detect(
    samples: Sequence[Sample],
    z_threshold: float = config.Z_THRESHOLD,
    min_consecutive: int = config.MIN_CONSECUTIVE_SAMPLES,
) -> List[Candidate]:
    """Run the impulse test, the trend test, and the physics gate."""
    if len(samples) < 7:
        return []

    altitudes = [s.altitude_km for s in samples]
    # Non-finite inputs (NaN/inf) would otherwise propagate through the
    # regression and manufacture entirely spurious candidates -- observed
    # producing 20 phantom alerts from a 20-sample NaN series. Refuse instead.
    if not all(math.isfinite(a) for a in altitudes):
        return []

    n = len(altitudes)
    candidates: List[Candidate] = []

    # -- Stage 1b: sustained drift ----------------------------------------
    trend = trend_test(altitudes)
    drift_per_day = trend["slope"] * (1440.0 / config.SAMPLE_STEP_MINUTES)
    significant = abs(trend["t_stat"]) >= config.TREND_T_THRESHOLD
    materially = abs(drift_per_day) >= config.MIN_DRIFT_KM_PER_DAY
    if significant and materially:
        cand = _judge(
            samples, altitudes, 0, n - 1, abs(trend["t_stat"]), "trend",
            min_consecutive,
        )
        if cand:
            cand.extra["trend_slope_km_per_sample"] = trend["slope"]
            cand.extra["residual_sigma_km"] = trend["residual_sigma"]
            candidates.append(cand)

    # -- Stage 1a: point anomalies -----------------------------------------
    zs = robust_z(detrended_residuals(altitudes))
    index = 0
    while index < zs.size:
        if abs(zs[index]) < z_threshold:
            index += 1
            continue
        end = index
        while end + 1 < zs.size and abs(zs[end + 1]) >= z_threshold:
            end += 1
        cand = _judge(
            samples, altitudes, index, end, abs(float(zs[index])), "impulse",
            min_consecutive,
        )
        if cand:
            candidates.append(cand)
        index = end + 1

    return candidates
