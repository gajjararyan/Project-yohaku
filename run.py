#!/usr/bin/env python3
"""Entry point: fetch -> propagate -> inject -> detect -> account -> report.

Usage
-----
    python run.py                # full run (fetches TLEs, caches them)
    python run.py --offline      # use only the local cache
    python run.py --self-test    # verify the physics gate behaves correctly

The pipeline is intentionally deterministic: sampling cadence and scenario
placement are fixed in :mod:`src.config`, so two runs on the same cached TLEs
produce identical output and a reviewer can diff them.
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

from src import accountability, config, data_source, detection, orbits, reporting
from src.orbits import Sample


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Yohaku Challenge 5 - orbital anomaly detection prototype",
    )
    parser.add_argument(
        "--offline", action="store_true",
        help="use only locally cached TLEs; make no network requests",
    )
    parser.add_argument(
        "--self-test", action="store_true",
        help="run the physics-gate assertions and exit",
    )
    parser.add_argument(
        "--quiet", action="store_true", help="suppress the console summary",
    )
    parser.add_argument(
        "--cross-epoch", action="store_true",
        help="note: cross-epoch comparison is automatic when online. Requires "
             "network for a second element set; cannot run against cache alone.",
    )
    return parser.parse_args()


def _spec_by_id() -> Dict[int, Dict[str, object]]:
    return {int(s["norad"]): s for s in config.TRACKED_OBJECTS}  # type: ignore[arg-type]


def _synthetic_series(n: int = 144, altitude: float = 420.0):
    """A clean, physically plausible LEO series used by the self-test."""
    base = datetime(2026, 9, 27, 12, 0, tzinfo=timezone.utc)
    return [
        Sample(
            time=base + timedelta(minutes=10 * i),
            altitude_km=altitude,
            speed_km_s=7.6,
            inclination_deg=51.6,
            semi_major_axis_km=config.R_EARTH_KM + altitude,
        )
        for i in range(n)
    ]


def run_self_test() -> int:
    """Assert the two claims the submission actually rests on.

    1. A sustained, physically plausible decay is CONFIRMED.
    2. An isolated single-sample spike is REJECTED on physical grounds even
       though it is a large statistical excursion.
    3. An object outside its published altitude band ABSTAINS rather than
       producing a confident score.

    If any of these fail, the prototype's central argument does not hold and
    it should not be submitted.
    """
    print("Self-test: physics gate behaviour")
    failures: List[str] = []

    clean = _synthetic_series()
    decayed = [
        Sample(
            time=s.time,
            altitude_km=s.altitude_km - (i * 0.0015),  # ~0.22 km/day: real LEO decay
            speed_km_s=s.speed_km_s,
            inclination_deg=s.inclination_deg,
            semi_major_axis_km=s.semi_major_axis_km,
        )
        for i, s in enumerate(clean)
    ]

    clean_c = detection.detect(clean)
    decayed_c = detection.detect(decayed)
    print(f"  clean series        -> {len(clean_c)} candidate(s) (expect 0)")
    print(f"  sustained decay     -> {len(decayed_c)} candidate(s) (expect >=1 confirmed)")
    if clean_c:
        failures.append("clean series produced a false candidate")
    if not any(c.confirmed for c in decayed_c):
        failures.append("physically plausible LEO decay was not confirmed")

    # A decay far too fast for the object's altitude must be REJECTED by the
    # scaled band. The per-sample ramp below measures at ~7.2 km/day against a
    # 420 km object's 0.05-4.0 km/day envelope (the trend test measures roughly
    # half the nominal ramp rate, hence the deliberately large coefficient).
    too_fast = [
        Sample(
            time=s.time,
            altitude_km=s.altitude_km - (i * 0.05),  # measures ~7.2 km/day
            speed_km_s=s.speed_km_s,
            inclination_deg=s.inclination_deg,
            semi_major_axis_km=s.semi_major_axis_km,
        )
        for i, s in enumerate(clean)
    ]
    fast_c = detection.detect(too_fast)
    if any(c.confirmed for c in fast_c):
        failures.append("impossible decay rate for 420 km was wrongly confirmed")
    print(f"  over-fast decay     -> {len(fast_c)} candidate(s), "
          f"{sum(1 for c in fast_c if c.confirmed)} confirmed (expect 0 confirmed)")

    spiky = _synthetic_series()
    spiky[len(spiky) // 2].altitude_km += config.SYNTHETIC_SPIKE_KM
    spike_c = detection.detect(spiky)
    confirmed_spikes = [c for c in spike_c if c.confirmed]
    print(f"  single-sample spike -> {len(spike_c)} candidate(s), "
          f"{len(confirmed_spikes)} confirmed (expect 0 confirmed)")
    if confirmed_spikes:
        failures.append("single-sample spike was wrongly confirmed")

    from src.data_source import TleRecord
    # A deliberately *fresh* element set, so this case tests the altitude band
    # rather than tripping the staleness gate first.
    fresh_epoch = datetime.now(timezone.utc) - timedelta(hours=2)
    yy = fresh_epoch.year % 100
    ddd = (fresh_epoch - datetime(fresh_epoch.year, 1, 1, tzinfo=timezone.utc)).total_seconds() / 86400.0 + 1
    fresh_line1 = (
        f"1 25544U 98067A   {yy:02d}{ddd:012.8f}  .00016717  00000-0  10270-3 0  9007"
    )
    fake = TleRecord(
        99999, "TEST OBJECT", fresh_line1,
        "2 25544  51.6400 100.0000 0005000  50.0000 310.0000 15.50000000 10000",
        "synthetic",
    )
    spec = {"norad": 99999, "stakes": "public",
            "altitude_band_km": (400.0, 440.0), "why": "self-test fixture"}
    far = [
        Sample(time=s.time, altitude_km=s.altitude_km + 500.0,
               speed_km_s=7.6, inclination_deg=51.6)
        for s in clean
    ]
    finding = accountability.build_finding(fake, spec, far, [])
    print(f"  out-of-band object  -> status={finding.status} (expect ABSTAINED)")
    if finding.status != "ABSTAINED":
        failures.append("out-of-band object did not abstain")

    # A stale element set must also abstain, even when the orbit looks fine.
    stale_line1 = "1 25544U 98067A   20100.50000000  .00016717  00000-0  10270-3 0  9007"
    stale = TleRecord(
        99998, "STALE OBJECT", stale_line1,
        "2 25544  51.6400 100.0000 0005000  50.0000 310.0000 15.50000000 10000",
        "synthetic",
    )
    stale_spec = {"norad": 99998, "stakes": "public",
                  "altitude_band_km": (400.0, 440.0), "why": "self-test fixture"}
    stale_finding = accountability.build_finding(stale, stale_spec, clean, [])
    print(f"  stale element set   -> status={stale_finding.status} (expect ABSTAINED)")
    if stale_finding.status != "ABSTAINED":
        failures.append("stale element set did not abstain")

    # Altitude-scaled band: a high object must be held to a tighter standard.
    b400 = detection.plausible_decay_band_km_per_day(420.0)
    b800 = detection.plausible_decay_band_km_per_day(820.0)
    print(f"  band @420 km        -> {b400['regime']} "
          f"{b400['min_km_per_day']}-{b400['max_km_per_day']} km/day")
    print(f"  band @820 km        -> {b800['regime']} "
          f"{b800['min_km_per_day']}-{b800['max_km_per_day']} km/day")
    if b400["max_km_per_day"] <= b800["max_km_per_day"]:
        failures.append("altitude-scaled band did not narrow with altitude")
    if b400["regime"] == b800["regime"]:
        failures.append("altitude-scaled band did not select distinct regimes")

    # Cross-epoch: two epochs too close must NOT be treated as agreement.
    near = accountability.assess_cross_epoch({
        "separation_hours": 0.1, "divergence_km": 0.5,
        "predicted_altitude_km": 420.0, "observed_altitude_km": 420.5,
    })
    print(f"  cross-epoch 0.1 h   -> {near['verdict']} (expect NOT_AVAILABLE/none)")
    if near["verdict"] == "CORROBORATED_NO_SIGNAL":
        failures.append("near-simultaneous epochs wrongly reported as corroboration")

    # Cross-epoch: a large real divergence must be graded as strong evidence.
    far = accountability.assess_cross_epoch({
        "separation_hours": 48.0, "divergence_km": 75.0,
        "predicted_altitude_km": 420.0, "observed_altitude_km": 495.0,
    })
    print(f"  cross-epoch 48 h/75km -> {far['verdict']} (expect DIVERGENCE_DETECTED)")
    if far["verdict"] != "DIVERGENCE_DETECTED":
        failures.append("large cross-epoch divergence not detected")

    # Cross-epoch: an absurd divergence must be called a data fault, not an anomaly.
    fault = accountability.assess_cross_epoch({
        "separation_hours": 2000.0, "divergence_km": 5000.0,
        "predicted_altitude_km": 420.0, "observed_altitude_km": 5420.0,
    })
    print(f"  cross-epoch 5000 km   -> {fault['verdict']} (expect DATA_FAULT_SUSPECTED)")
    if fault["verdict"] != "DATA_FAULT_SUSPECTED":
        failures.append("absurd cross-epoch divergence not flagged as a data fault")

    print()
    if failures:
        print("SELF-TEST FAILED:")
        for item in failures:
            print(f"  - {item}")
        return 1
    print("SELF-TEST PASSED: all claims hold.")
    return 0


def main() -> int:
    args = parse_args()
    if args.self_test:
        return run_self_test()

    print("[run] Yohaku Challenge 5 - anomaly detection prototype")
    # ONE budget for the whole run, shared by the fleet fetch and the
    # cross-epoch second-opinion phase. Without this the second phase issues
    # another N requests and doubles the worst-case wall time.
    budget = data_source._FetchBudget()
    records = data_source.load_tracked(offline=args.offline, budget=budget)
    if not records:
        print(
            "[run] No element sets available and none bundled.\n"
            "      Run once with network access first:  python run.py\n"
            "      Or re-clone the repository, which includes a small bundled sample."
        )
        return 1

    specs = _spec_by_id()
    findings: List[accountability.Finding] = []
    log = accountability.DecisionLog()

    # Cross-epoch comparison needs a PINNED earlier fit. If none exists yet,
    # capture the current element sets as the baseline so that a LATER run can
    # compare against them. Doing this here -- rather than in data_source -- is
    # what stops an online run from silently erasing its own 'before' snapshot.
    baseline = data_source.load_baseline()
    baseline_records = {
        int(k): data_source.TleRecord.from_dict(v)
        for k, v in (baseline.get("records") or {}).items()
    }
    if not args.offline and not baseline_records:
        data_source.save_baseline({r.norad_id: r for r in records})
        print("[data] no cross-epoch baseline yet; pinned current element sets. "
              "Re-run later to get a genuine independent comparison.")
    elif baseline_records:
        print(f"[data] cross-epoch baseline pinned at "
              f"{str(baseline.get('captured_utc'))[:19]} "
              f"({len(baseline_records)} objects)")

    for record in records:
        spec = specs.get(
            record.norad_id, {"stakes": "public", "why": "Unspecified object."}
        )
        try:
            samples = orbits.propagate(record)
        except orbits.PropagationError as exc:
            # Abstention is a valid outcome, not a crash.
            print(f"[run] {record.name}: propagation failed ({exc}); abstaining")
            findings.append(accountability.build_finding(record, spec, [], []))
            continue

        # Independent second epoch, when a network is available. The OLD fit
        # comes from the pinned baseline; the NEW fit is fetched live.
        cross: Optional[dict] = None
        old_record = baseline_records.get(record.norad_id)
        if not args.offline and old_record is not None:
            second = data_source.fetch_second_epoch(
                record.norad_id, budget=budget
            )
            if second is not None:
                cross = orbits.cross_epoch_divergence(old_record, second)
        if args.cross_epoch and args.offline:
            print("[run] --cross-epoch requested with --offline; no second epoch "
                  "can be fetched from cache alone")

        scenario = config.DEMO_SCENARIOS.get(record.norad_id)
        if scenario:
            samples = orbits.inject_scenario(samples, scenario)

        candidates = detection.detect(samples)
        finding = accountability.build_finding(
            record, spec, samples, candidates, cross_epoch=cross
        )
        findings.append(finding)

        if finding.status == "CONFIRMED":
            log.record(
                record.norad_id, record.name, "DEFER",
                operator=finding.decision_owner,
                note="Automatically deferred pending human confirmation.",
            )

    paths = reporting.write_reports(findings, log, records, verbose=not args.quiet)

    if not args.quiet:
        print(reporting.render_console(findings, log, records))
        print("\nArtefacts written:")
        for label, path in paths.items():
            print(f"  {label:13s} -> {path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())

