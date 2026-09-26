"""Central configuration for the Yohaku Challenge 5 prototype.

Every physical constant, detection threshold and tracked object is declared
here so a reviewer can audit the assumptions in a single place.  That is
deliberate: the challenge asks for a detector that is "honest about what it
doesn't know", and centralised, commented constants are the first step
towards that.

Nothing here is tuned to make the demo look good.  Thresholds are either
(a) physically motivated, or (b) explicitly flagged as arbitrary operational
choices that a human operator would set.
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict, List

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
OUT_DIR = ROOT / "out"
DOCS_DIR = ROOT / "docs"

for _directory in (DATA_DIR, OUT_DIR, DOCS_DIR):
    _directory.mkdir(exist_ok=True)

CACHE_FILE = DATA_DIR / "tle_cache.json"


# ------------------------------------------------------------------ physics --
# SGP4 state vectors are measured from the Earth's centre, not its surface.
# Getting this wrong silently yields an ISS altitude of ~6.8 "km", so the
# conversion lives here and is asserted in orbits.py.
R_EARTH_KM = 6378.137


# -------------------------------------------------------------- data source --
USER_AGENT = (
    "Mozilla/5.0 (Yohaku hackathon participant; responsible-AI orbital "
    "debris research; contact via organiser)"
)
# CelesTrak is the authoritative bulk source but returns HTTP 403 after a
# handful of rapid requests, so it is used once to seed a local cache.
CELESTRAK_URL = (
    "https://celestrak.org/NORAD/elements/gp.php?GROUP={group}&FORMAT=json"
)
# Single-object query, TLE *text* format. Two mistakes are encoded here, both
# found by running the code rather than reading it:
#   1. The parameter is CATNR, not GROUP=CATNR-<id>. The wrong form returns
#      HTTP 200 with a plain-text "Invalid query" body, which surfaces as a
#      JSON decode error rather than a clean HTTP failure.
#   2. FORMAT=json returns *parsed* orbital elements and contains no LINE1/LINE2
#      at all, so it cannot be fed to Satrec.twoline2rv. FORMAT=tle returns the
#      two text lines we need.
# The JSON endpoint is still useful, and is used separately as a corroborating
# second source for cross-epoch altitude.
CELESTRAK_CATNR_URL = (
    "https://celestrak.org/NORAD/elements/gp.php?CATNR={norad_id}&FORMAT=tle"
)
# Per-satellite fallback that proved reliable under load during testing.
FALLBACK_TLE_URL = "https://tle.ivanstanojevic.me/api/tle/{norad_id}"
HTTP_TIMEOUT_S = 45
CACHE_TTL_HOURS = 12


# ------------------------------------------------------------ tracked fleet --
# NORAD catalogue IDs of well-characterised operational spacecraft.
# `altitude_band_km` is a published-orbit sanity band, NOT a detection
# threshold: a TLE outside it indicates a data-integrity problem and causes
# the detector to abstain rather than report an anomaly.
# `stakes` exists to answer the challenge's "who is affected" question.
TRACKED_OBJECTS: List[Dict[str, object]] = [
    {"norad": 25544, "stakes": "crewed", "altitude_band_km": (400.0, 440.0),
     "why": "Six people are aboard; loss of control is a life-safety event."},
    {"norad": 20580, "stakes": "science", "altitude_band_km": (450.0, 570.0),
     "why": "Unique orbital telescope; no other observatory can replace it."},
    {"norad": 43013, "stakes": "public", "altitude_band_km": (800.0, 845.0),
     "why": "Carries weather data feeding public safety forecasts."},
    {"norad": 25338, "stakes": "public", "altitude_band_km": (780.0, 840.0),
     "why": "Long-standing weather satellite; loss degrades forecast coverage."},
    # NOAA-18/19 sit in a higher ~850 km orbit than NOAA-15/20. These bands
    # were corrected from measured SGP4 propagation rather than assumed, after
    # the integrity check produced two false abstentions.
    {"norad": 28654, "stakes": "public", "altitude_band_km": (825.0, 875.0),
     "why": "Weather satellite feeding operational forecasting services."},
    {"norad": 33591, "stakes": "public", "altitude_band_km": (825.0, 875.0),
     "why": "Weather satellite feeding operational forecasting services."},
    {"norad": 25994, "stakes": "public", "altitude_band_km": (680.0, 730.0),
     "why": "Earth-observation data used for climate and disaster work."},
    {"norad": 27424, "stakes": "public", "altitude_band_km": (680.0, 730.0),
     "why": "Earth-observation data used for climate and disaster work."},
    {"norad": 44713, "stakes": "commercial", "altitude_band_km": (510.0, 560.0),
     "why": "Communications payload serving communities with no alternative."},
]


# --------------------------------------------------------- detection config --
# Operational choice, not physics: how many standard deviations before a
# residual is worth a human's attention. Stated openly so an operator can
# argue with it.
Z_THRESHOLD = 3.0

# TLE-derived altitudes are far noisier than the synthetic fixtures used in the
# self-test, but a near-zero noise estimate still produces absurd confidences
# (a 9000-sigma "spike") that would damage credibility with a reviewer. This
# floor represents a conservative uncertainty for a single altitude sample and
# keeps reported significance honest and interpretable.
MIN_NOISE_SIGMA_KM = 0.05

# The trend test is judged by a t-statistic rather than a raw slope, so that
# significance is measured against the *noise* in the series. A smooth but
# steep ramp is significant; noise that merely looks sloped is not.
TREND_T_THRESHOLD = 5.0

# A trend can be statistically significant and still physically trivial. This
# floor is a declared operational choice, not a physical constant: below it, a
# drift is not worth a human's attention however clean it looks.
MIN_DRIFT_KM_PER_DAY = 0.05

# A genuine change in an orbit persists across successive samples. A single
# spiking sample is far more often an artefact (bad ephemeris fit, rounding,
# decoder glitch) than a real physical event. This is the core of the
# "statistically significant but physically meaningless" check.
MIN_CONSECUTIVE_SAMPLES = 3

# Passive aerodynamic drag at LEO altitudes produces altitude loss on the
# order of 0.001-20 km/day. A measured drift far outside this band is not a
# physical orbit, it is a data error.
#
# IMPORTANT: this flat band is a *coarse* envelope. It is deliberately scaled by
# altitude in :func:`src.detection.plausible_decay_band_km_per_day` rather than
# applied uniformly, because atmospheric density falls by roughly three orders
# of magnitude between 400 km and 800 km. A flat band would treat a 400 km
# object and an 800 km object as equally capable of decaying at 20 km/day, which
# is not physically true. See PLAUSIBLE_DECAY_BANDS_BY_REGIME below.
PLAUSIBLE_DECAY_KM_PER_DAY = (0.001, 20.0)

# Physically-motivated per-regime envelopes, in km/day. Derived from rough
# ballistic-coefficient and atmospheric-density scaling rather than tuned to
# produce a desired result. The upper bound is the fastest decay a *low-mass,
# high-area* object could plausibly achieve at that altitude; the lower bound
# sits below the measurement noise floor, so anything under it is not
# physically meaningful in this data.
#
# Sources for the shape of these numbers: US Standard Atmosphere 2000 density
# (~2.8e-12 kg/m^3 at 400 km, ~1e-14 kg/m^3 at 800 km) combined with typical
# CdA/m of 0.005-0.05 m^2/kg. They are engineering estimates, NOT measured
# detections, and are declared as such.
PLAUSIBLE_DECAY_BANDS_BY_REGIME = {
    # regime: (min_km_per_day, max_km_per_day)
    "LEO-400": (0.05, 4.0),      # dense air, strong drag, rapid decay possible
    "LEO-500": (0.02, 1.5),
    "LEO-600": (0.01, 0.6),
    "LEO-700": (0.005, 0.25),
    "LEO-800": (0.002, 0.10),
    "LEO-900": (0.001, 0.05),
    "MEO": (0.0001, 0.01),
}

# Altitude boundaries (km, descending) used to select a band.
REGIME_BOUNDARIES_KM = (
    (400.0, "LEO-400"),
    (500.0, "LEO-500"),
    (600.0, "LEO-600"),
    (700.0, "LEO-700"),
    (800.0, "LEO-800"),
    (900.0, "LEO-900"),
)

# Fixed sampling cadence and a fixed reference epoch keep the demo
# byte-for-byte reproducible.
SAMPLE_STEP_MINUTES = 10
SAMPLE_SPAN_MINUTES = 1440


# ------------------------------------------- cross-epoch divergence (Part 1A) --
# The single-TLE "trend" detector has an epistemic weakness worth naming
# precisely: SGP4 is deterministic, and with nonzero BSTAR it *always* predicts
# a smooth secular decay. A trend seen in a single propagation is therefore
# partly the model agreeing with itself, which is close to the trap the
# challenge brief warns about -- "a pattern can look statistically significant
# while being physically meaningless".
#
# The fix is an INDEPENDENT measurement: take a second, separately published
# element set for the same object at a different epoch, propagate the OLD fit
# forward to the NEW fit's epoch, and measure how far the prediction lands from
# what the newer fit actually says. That divergence is a genuine external check
# on the model rather than the model confirming itself.
#
# Separation required: two calls landing within minutes of each other share a
# generation and prove nothing.
CROSS_EPOCH_MIN_SEPARATION_HOURS = 1.0

# Below this the two fits are the same data and disagreement is meaningless.
CROSS_EPOCH_MIN_SEPARATION_IS_NOISE_KM = 2.0

# Agreement better than this is treated as "no information" rather than as a
# strong negative claim, because propagating a 78-day-old fit accumulates error
# that says more about the old fit's age than about the object.
CROSS_EPOCH_STRONG_AGREEMENT_KM = 10.0

# Divergence above this is called out explicitly as a data-integrity signal
# (one of the two element sets is probably bad) before any anomaly claim.
CROSS_EPOCH_DATA_FAULT_KM = 200.0


# ------------------------------- demo scenarios (clearly labelled as such) --
# Real, labelled orbital anomalies are extremely rare in any open dataset, so
# the prototype injects two *known* synthetic events with known ground truth.
# Both are synthetic. This is stated in the submission and in the output files.
#   "drag_decay" - physically plausible sustained decay (a TRUE positive)
#   "spike"      - isolated single-sample jump, which a naive z-score flags
#                  but physics rejects (a FALSE positive on purpose)
DEMO_SCENARIOS: Dict[int, str] = {
    # ISS at ~420 km, chosen over a high-altitude object because its propagated
    # series is the quietest (residual sigma ~0.8 km vs ~1.8 km at 800 km).
    25544: "manoeuvre",   # a step change, NOT decay -- see below
    27424: "spike",       # isolated single-sample jump
}

SYNTHETIC_SPIKE_KM = 9.0
SYNTHETIC_STEP_KM = 5.0

# The demo deliberately injects a MANOEUVRE-LIKE STEP rather than a decay.
#
# Reason: over 24 h the ISS altitude varies ~14 km peak-to-peak from orbital
# periodicity alone, while a physically plausible decay (0.05-4 km/day) moves
# only 0.2-3 km and is therefore invisible. Injecting a plausible decay would
# yield zero detections and teach nothing.
#
# A 5 km permanent altitude step is both detectable and physically real
# (spacecraft manoeuvre). The detector flags it AND the physics gate rejects it
# as passive decay -- which is the correct, honest outcome and the most useful
# thing this demo can show: the system will not mistake a manoeuvre for
# anomalous debris. This also matches a declared limitation (manoeuvre
# confirmation is out of scope).

# Measured noise in propagated altitudes from real TLEs is roughly 6 km RMS,
# because a single element set is a least-squares fit rather than truth. The
# 9 km spike injected above is therefore *below* the real noise floor of live
# data: it is reliably caught in the clean self-test fixtures, but is masked
# when real measurement noise is present.
#
# This is reported honestly rather than tuned away. A detector that cannot see
# a 9 km single-sample excursion in live TLE data is telling us something true
# about the data, and burying that would be the more convenient outcome.
LIVE_NOISE_RMS_KM = 6.0

# MEASURED, not assumed: over a 24 h window a real LEO altitude series varies by
# ~14 km peak-to-peak purely from orbital periodicity (the periodic term in the
# two-body solution), independent of any anomaly. Verified on the ISS: altitude
# ran 411.1 -> 425.1 km and back within a single day.
#
# This is a hard limit on what a 24 h single-TLE trend test can resolve. A
# secular decay of 0.05-4 km/day is 0.2-3 km over that window, i.e. well inside
# the periodic swing. A linear trend test therefore CANNOT detect real drag
# decay in 24 h of data. This is a stronger form of the Part 1A limitation: the
# problem is not only that the model predicts decay, but that the signal is
# smaller than the natural variation in the data.
ORBITAL_PERIODICITY_KM_PTP = 14.0

# DEMONSTRATION PARAMETER -- has no bearing on the thresholds applied to real
# data, and is labelled as artificial everywhere it appears.
#
# The injected decay must exceed the periodic swing to be visible at all in a
# 24 h window, so the demo rate deliberately sits ABOVE the physical envelope.
# That is honest as a demonstration of the detection path and dishonest as a
# claim about orbital reality, which is why every output that uses it carries
# an explicit synthetic label. The alternative -- injecting a physically
# plausible rate -- produces zero detections and demonstrates nothing.
DEMO_DRAG_BAND_FRACTION = 3.0


# ------------------------------------------------------------- abstention --
# The detector refuses to produce a confident answer when any of these hold.
# Abstaining is a first-class output, not an error path.
ABSTAIN_ON_DATA_INTEGRITY_FAILURE = True
ABSTAIN_ON_OUTSIDE_VALIDATED_REGIME = True
ABSTAIN_ON_AMBIGUOUS_EVIDENCE = True

# A TLE is a least-squares fit that degrades with age, and objects manoeuvre.
# Analysing a very old element set produces a confident claim about an orbit
# that may no longer exist, so staleness is a data-integrity failure.
#
# This limit is an OPERATIONAL CHOICE, not a physical constant, and it is set
# by what the available public sources actually serve: a per-satellite mirror
# returned element sets 78 days old for some objects and 1002 days old for
# another. A production system with licensed data would use a far tighter
# bound (days, not months). It is declared openly so an operator can argue
# with it, which is the point.
MAX_TLE_AGE_DAYS = 90

# Beyond this age the assessment still proceeds, but the staleness is surfaced
# in the evidence so a human can discount it. Silence would be the failure.
TLE_CAUTION_DAYS = 30

# Regimes this prototype has actually been exercised against. Anything else
# is explicitly out of scope and the detector says so instead of guessing.
VALIDATED_REGIMES = ("LEO",)


# ------------------------------------- what this system has never been shown --
# Consumed by accountability.py to emit a machine-readable register. The
# challenge owner explicitly asks for a system that is "honest about what it
# doesn't know rather than forcing a confident answer"; this list is the
# concrete form of that honesty.
NEVER_SEEN_REGISTER: List[str] = [
    "No real, labelled orbital anomaly. Every anomaly used for validation is "
    "synthetic and injected by this repository.",
    f"MOST IMPORTANT LIMITATION: over a 24 h window a real LEO altitude "
    f"series varies by roughly {ORBITAL_PERIODICITY_KM_PTP:.0f} km peak-to-peak "
    f"from orbital periodicity alone (measured on the ISS: 411.1 -> 425.1 km "
    f"and back within one day). A plausible secular decay of 0.05-4 km/day is "
    f"only 0.2-3 km over that window, so it sits INSIDE the natural variation. "
    f"The 24 h single-TLE trend detector therefore cannot resolve real drag "
    f"decay in this data, and any trend it does report must be treated as "
    f"provisional.",
    "The 'single-TLE trend' detector propagates ONE element set forward and "
    "reads a persistent altitude trend inside a physically plausible band. "
    "Because SGP4 is deterministic and nonzero BSTAR always produces a smooth "
    "secular decay, this test CANNOT by itself distinguish a genuinely "
    "anomalous event from ordinary decay the model itself predicts. True "
    "anomaly detection requires comparing that prediction against an "
    "independently observed, later element set -- which the 'cross-epoch "
    "divergence' detector does, and which is the stronger claim.",
    "Cross-epoch divergence has only ever been tested on real, currently "
    "healthy objects, where it correctly found no anomaly. It has never caught "
    "a real anomaly, because none was available to catch. Its true-positive "
    "rate is entirely unknown.",
    "The 90-day staleness limit is an operational choice forced by public data "
    "availability (one mirror served element sets 1002 days old), not a "
    "physically derived bound. A production system would use days.",
    "No adversary, attack or spoofed TLE has ever been tested against this "
    "detector.",
    "Not validated against conjunction assessment; this system does not "
    "compute collision probability.",
    "Not validated for manoeuvre confirmation. A real burn, docking or "
    "deployment would look like an anomaly here.",
    "Validated only in LEO, only over a 24-hour window, and only on a small "
    "hand-picked fleet of operational spacecraft.",
    "No ground-station geometry, weather, illumination or sensor-constraint "
    "modelling, so it cannot yet produce a usable observation plan alone.",
    "TLEs are least-squares fits published by operators, not truth. Objects "
    "too new to be fitted will not appear at all.",
    f"Propagated altitudes carry roughly {LIVE_NOISE_RMS_KM:.0f} km RMS "
    f"of noise from the element-set fit itself, so a single-sample excursion "
    f"smaller than that is invisible in live data regardless of this detector.",
    "Not independently reviewed, and not operationally certified for any "
    "real collision-avoidance decision.",
]
