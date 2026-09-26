"""Orbital propagation via SGP4, plus the synthetic scenario injector.

Unit handling is the single easiest thing to get wrong here. SGP4 returns
position vectors from the Earth's *centre*, in kilometres. Dividing by 1000
(an intuitive-looking but wrong move) yields an ISS altitude of 6.8 km. The
correct conversion is ``|r| - R_EARTH``; :func:`propagate` asserts the result
lands in a plausible band so a regression can never pass silently.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import List, Optional

import numpy as np
from sgp4.api import Satrec, jday

from . import config
from .data_source import TleRecord


def _decay_band(altitude_km: float):
    """Local copy of the regime-band lookup.

    Implemented here rather than imported from :mod:`src.detection` because
    ``detection`` imports ``orbits`` for the ``Sample`` type, so importing back
    the other way creates a circular import. The band data itself lives in
    :mod:`src.config`; this only selects it.
    """
    regime = "MEO"
    for threshold, name in config.REGIME_BOUNDARIES_KM:
        if altitude_km >= threshold:
            regime = name
    low, high = config.PLAUSIBLE_DECAY_BANDS_BY_REGIME[regime]
    return {"regime": regime, "min_km_per_day": low, "max_km_per_day": high,
            "altitude_km": round(altitude_km, 1)}


class PropagationError(RuntimeError):
    """Raised when SGP4 cannot produce a usable state vector."""


@dataclass
class Sample:
    """One propagated state for one object at one instant."""

    time: datetime
    altitude_km: float
    speed_km_s: float
    inclination_deg: float
    semi_major_axis_km: float = 0.0
    injected: Optional[str] = None  # ground-truth label, for synthetic events
    extra: dict = field(default_factory=dict)


def _jday_frac(dt: datetime):
    """Version-tolerant wrapper: older/newer sgp4 return 2 or 3 values."""
    result = jday(
        dt.year, dt.month, dt.day, dt.hour, dt.minute,
        dt.second + dt.microsecond / 1e6,
    )
    return result[0], result[1]


def classify_regime(altitude_km: float) -> str:
    """Coarse orbital regime label used to gate claims of validity."""
    if altitude_km < 2000:
        return "LEO"
    if altitude_km < 35000:
        return "MEO"
    return "GEO-or-higher"


def propagate(
    record: TleRecord,
    start: Optional[datetime] = None,
    step_minutes: int = config.SAMPLE_STEP_MINUTES,
    span_minutes: int = config.SAMPLE_SPAN_MINUTES,
) -> List[Sample]:
    """Propagate one TLE forward and return altitude/speed/inclination series.

    Falls back to ``now`` when the TLE epoch is unparseable, and raises
    :class:`PropagationError` if SGP4 yields no usable samples -- the caller
    is expected to abstain rather than guess in that situation.
    """
    try:
        satellite = Satrec.twoline2rv(record.line1, record.line2)
    except Exception as exc:  # noqa: BLE001
        raise PropagationError(f"unparseable TLE for {record.name}: {exc}") from exc

    if start is None:
        start = record.epoch or datetime.now(timezone.utc)
    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)

    samples: List[Sample] = []
    # SGP4 keeps the orbital elements in radians and rev/day, under terse names
    # (ecco = eccentricity, inclo = inclination, no_kozai = mean motion).
    eccentricity = float(getattr(satellite, "ecco", 0.0))
    inclination_deg = math.degrees(float(getattr(satellite, "inclo", 0.0)))

    for minutes in range(0, span_minutes + 1, step_minutes):
        when = start + timedelta(minutes=minutes)
        fr, be = _jday_frac(when)
        error, position, velocity = satellite.sgp4(fr, be)
        if error != 0:
            continue
        radius_km = float(np.linalg.norm(position))
        altitude_km = radius_km - config.R_EARTH_KM
        speed_km_s = float(np.linalg.norm(velocity))
        # Semi-major axis from the vis-viva relation, only meaningful for a
        # closed orbit. A hyperbolic or parabolic path has no finite a.
        sma_km = 0.0
        if 0.0 < eccentricity < 1.0:
            sma_km = config.R_EARTH_KM / (1.0 - eccentricity)
        samples.append(
            Sample(
                time=when,
                altitude_km=altitude_km,
                speed_km_s=speed_km_s,
                inclination_deg=inclination_deg,
                semi_major_axis_km=sma_km,
            )
        )

    if not samples:
        raise PropagationError(f"SGP4 produced no samples for {record.name}")
    return samples


def cross_epoch_divergence(
    old: TleRecord,
    new: TleRecord,
) -> Optional[Dict[str, object]]:
    """Compare two independently published element sets for the same object.

    This is the detector that does **not** rely on the model agreeing with
    itself. The older fit is propagated forward to the newer fit's epoch, and
    the result compared with what the newer fit says:

    * If the prediction lands close to the newer fit, two independently
      published descriptions agree, which is real corroboration.
    * If it lands far away, at least one fit is wrong, or the object did
      something unmodelled. Either way that is worth a human's attention, and
      it is a claim grounded in *external* data rather than in our own model.

    Returns ``None`` when the two epochs are too close to be independent, which
    is deliberately *not* treated as agreement.
    """
    old_epoch = old.epoch
    new_epoch = new.epoch
    if old_epoch is None or new_epoch is None:
        return None

    separation_hours = abs((new_epoch - old_epoch).total_seconds()) / 3600.0
    if separation_hours < config.CROSS_EPOCH_MIN_SEPARATION_HOURS:
        return None

    try:
        satellite = Satrec.twoline2rv(old.line1, old.line2)
    except Exception as exc:  # noqa: BLE001
        return {"error": f"older element set unparseable: {exc}"}

    fr, be = _jday_frac(new_epoch)
    error, position, _ = satellite.sgp4(fr, be)
    if error != 0:
        return {"error": f"SGP4 failed to propagate the older fit forward (code {error})"}

    predicted_alt = float(np.linalg.norm(position)) - config.R_EARTH_KM

    # Altitude implied by the newer fit, measured INDEPENDENTLY of the older
    # one: propagate the NEWER element set to its OWN epoch and read the
    # radius there.
    #
    # It is tempting to derive this from the newer fit's eccentricity via
    #     a = R_earth / (1 - e),  altitude = a - R_earth
    # but that is WRONG for these objects. That expression gives the MEAN
    # altitude of the ellipse, and for a near-circular orbit the eccentricity
    # is ~5e-4, so 1-e ~ 0.9995 and the result is ~3 km rather than the true
    # ~420 km. Taking the radius at the epoch is the correct measure and is
    # what a real observer would report.
    try:
        newer = Satrec.twoline2rv(new.line1, new.line2)
        fr2, be2 = _jday_frac(new_epoch)
        error2, new_position, _ = newer.sgp4(fr2, be2)
        if error2 != 0:
            return {
                "error": (
                    f"SGP4 could not evaluate the newer fit at its own epoch "
                    f"(code {error2})"
                )
            }
        observed_alt = float(np.linalg.norm(new_position)) - config.R_EARTH_KM
    except Exception as exc:  # noqa: BLE001
        return {"error": f"newer element set unparseable: {exc}"}

    if not (0.0 < observed_alt < 100000.0):
        return {
            "error": (
                f"Newer fit implies a non-physical altitude of {observed_alt:.1f} km; "
                f"refusing to compare."
            )
        }

    divergence_km = abs(predicted_alt - observed_alt)
    return {
        "separation_hours": separation_hours,
        "old_epoch": old_epoch.isoformat(),
        "new_epoch": new_epoch.isoformat(),
        "predicted_altitude_km": predicted_alt,
        "observed_altitude_km": observed_alt,
        "divergence_km": divergence_km,
        "old_source": old.source,
        "new_source": new.source,
    }


def inject_scenario(samples: List[Sample], scenario: str) -> List[Sample]:
    """Apply a labelled synthetic event to a propagated series.

    This is ground truth for validating the detector. It is NOT presented as
    real orbital data anywhere in the pipeline; every affected sample carries
    an ``injected`` label that propagates all the way to the report.
    """
    if scenario == "drag_decay":
        # Physically plausible sustained decay: begins partway through and
        # persists, exactly like a real drag-driven altitude loss.
        #
        # The rate is a fraction of the object's own regime envelope. It must
        # clear the *measured* noise, not just the nominal band: a real 24 h
        # altitude series swings ~14 km peak-to-peak from orbital periodicity
        # (see ORBITAL_PERIODICITY_KM_PTP), so a small decay is buried in that
        # oscillation rather than resolvable by a linear trend. A demo rate
        # that cannot clear the noise would silently demonstrate nothing.
        start_index = len(samples) // 3
        mean_alt = sum(s.altitude_km for s in samples) / max(1, len(samples))
        band = _decay_band(mean_alt)
        target_rate = float(band["max_km_per_day"]) * config.DEMO_DRAG_BAND_FRACTION
        per_sample_km = target_rate * config.SAMPLE_STEP_MINUTES / 1440.0
        for offset, sample in enumerate(samples[start_index:]):
            step = min(offset + 1, len(samples) - start_index)
            sample.altitude_km -= per_sample_km * step
            sample.injected = "drag_decay"
            sample.extra["ground_truth"] = (
                f"sustained drag-driven decay at {target_rate:.2f} km/day "
                f"(synthetic, inside the {band['regime']} envelope)"
            )

    elif scenario == "manoeuvre":
        # A permanent altitude step, as a real burn or deployment produces.
        # This is a genuine physical event, but it is NOT drag decay, so the
        # physics gate is expected to reject it -- which is the point.
        start_index = len(samples) // 2
        for sample in samples[start_index:]:
            sample.altitude_km -= config.SYNTHETIC_STEP_KM
            sample.injected = "manoeuvre"
            sample.extra["ground_truth"] = (
                f"permanent {config.SYNTHETIC_STEP_KM:.0f} km altitude step, "
                f"manoeuvre-like (synthetic)"
            )

    elif scenario == "spike":
        # Isolated single-sample jump. A naive z-score detector calls this an
        # anomaly; the physics gate must reject it as an artefact.
        index = len(samples) // 2
        samples[index].altitude_km += config.SYNTHETIC_SPIKE_KM
        samples[index].injected = "spike"
        samples[index].extra["ground_truth"] = "isolated single-sample jump (synthetic artefact)"

    else:
        raise ValueError(f"unknown scenario: {scenario!r}")

    return samples
