"""TLE acquisition: bulk fetch, local cache, and per-satellite fallback.

Three real failure modes were observed while building this and are handled
explicitly:

1. CelesTrak returns HTTP 403 after a handful of rapid requests. We therefore
   seed a local cache once and then prefer it, so a live demo can never die
   on a rate limit.
2. The fallback mirror only serves satellites by NORAD ID, not by category.
3. Both endpoints use different field names, so all parsing funnels through
   :func:`_normalise`.
"""
from __future__ import annotations

import json
import urllib.request
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

from . import config


class TleRecord:
    """A single two-line element set, plus provenance."""

    __slots__ = ("norad_id", "name", "line1", "line2", "source")

    def __init__(self, norad_id: int, name: str, line1: str, line2: str, source: str):
        self.norad_id = int(norad_id)
        self.name = name or f"NORAD {norad_id}"
        self.line1 = line1
        self.line2 = line2
        self.source = source

    def to_dict(self) -> Dict[str, object]:
        return {
            "norad_id": self.norad_id,
            "name": self.name,
            "line1": self.line1,
            "line2": self.line2,
            "source": self.source,
        }

    @classmethod
    def from_dict(cls, payload: Dict[str, object]) -> "TleRecord":
        return cls(
            int(payload["norad_id"]),  # type: ignore[arg-type]
            str(payload.get("name", "")),
            str(payload["line1"]),
            str(payload["line2"]),
            str(payload.get("source", "cache")),
        )

    @property
    def epoch(self) -> Optional[datetime]:
        """Epoch year/day-of-year parsed from TLE line 1, if readable."""
        try:
            yy = int(self.line1[18:20])
            ddd = float(self.line1[20:32])
            year = 2000 + yy if yy < 57 else 1900 + yy
            base = datetime(year, 1, 1, tzinfo=timezone.utc)
            return base + timedelta(days=ddd - 1)
        except (ValueError, IndexError):
            return None

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<TleRecord {self.norad_id} {self.name!r} via {self.source}>"


def _http_json(url: str, timeout: int = config.HTTP_TIMEOUT_S):
    request = urllib.request.Request(url, headers={"User-Agent": config.USER_AGENT})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.load(response)


def _normalise(raw: Dict[str, object], fallback_id: int, source: str) -> Optional[TleRecord]:
    """Accept either CelesTrak's schema or the fallback mirror's schema.

    The mirror serves JSON-LD and names the catalogue field ``satelliteId``,
    which is easy to miss and fails silently as a "no TLE available" result.
    """
    line1 = raw.get("line1") or raw.get("LINE1")
    line2 = raw.get("line2") or raw.get("LINE2")
    if not line1 or not line2:
        return None
    norad = (
        raw.get("norad_cat_id")
        or raw.get("norad_id")
        or raw.get("satelliteId")
        or raw.get("satid")
        or fallback_id
    )
    name = raw.get("name") or raw.get("OBJECT_NAME") or raw.get("satname") or ""
    return TleRecord(int(norad), str(name), str(line1), str(line2), source)


# ------------------------------------------------------------------ cache --
def _read_cache() -> Dict[str, object]:
    if not config.CACHE_FILE.exists():
        return {"fetched_utc": None, "records": {}}
    try:
        return json.loads(config.CACHE_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"fetched_utc": None, "records": {}}


def _baseline_path():
    return config.DATA_DIR / "tle_baseline.json"


def load_baseline() -> Dict[str, object]:
    """Read the pinned 'before' element sets used for cross-epoch comparison.

    Cross-epoch needs a *stable* earlier fit. Refreshing the main cache on every
    online run would overwrite that earlier fit with the current one, leaving
    nothing independent to compare against -- which is exactly what happened
    during development, silently disabling the detector.
    """
    path = _baseline_path()
    if not path.exists():
        return {"captured_utc": None, "records": {}}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"captured_utc": None, "records": {}}


def save_baseline(records: Dict[int, TleRecord]) -> None:
    """Pin the current element sets as the cross-epoch 'before' snapshot."""
    _baseline_path().write_text(
        json.dumps(
            {
                "captured_utc": datetime.now(timezone.utc).isoformat(),
                "records": {str(k): v.to_dict() for k, v in records.items()},
            },
            indent=1,
        ),
        encoding="utf-8",
    )


def _write_cache(cache: Dict[str, object]) -> None:
    config.CACHE_FILE.write_text(json.dumps(cache, indent=1), encoding="utf-8")


def _cache_is_fresh(cache: Dict[str, object]) -> bool:
    stamp = cache.get("fetched_utc")
    if not stamp:
        return False
    try:
        fetched = datetime.fromisoformat(str(stamp))
    except ValueError:
        return False
    if fetched.tzinfo is None:
        fetched = fetched.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) - fetched < timedelta(hours=config.CACHE_TTL_HOURS)


# ----------------------------------------------------------------- public --
def load_tracked(offline: bool = False, verbose: bool = True) -> List[TleRecord]:
    """Return a TLE for every object in :data:`config.TRACKED_OBJECTS`.

    Order of preference: fresh cache, bulk CelesTrak fetch, per-satellite
    fallback, single-object bulk fetch, then any stale cached record. Never
    raises for one missing satellite -- an unresolvable object is reported and
    skipped, because a partial fleet beats a failed demo.
    """
    cache = _read_cache()
    records: Dict[int, TleRecord] = {}

    if not offline and not _cache_is_fresh(cache):
        if verbose:
            print("[data] seeding cache from CelesTrak (one bulk request)...")
        try:
            bulk = _http_json(config.CELESTRAK_URL.format(group="active"))
            by_id = {}
            for entry in bulk:
                rec = _normalise(entry, -1, "celestrak")
                if rec:
                    by_id[rec.norad_id] = rec
            cache["records"] = {str(k): v.to_dict() for k, v in by_id.items()}
            cache["fetched_utc"] = datetime.now(timezone.utc).isoformat()
            _write_cache(cache)
            if verbose:
                print(f"[data] cached {len(by_id)} objects from CelesTrak")
        except Exception as exc:  # noqa: BLE001 - network is best-effort
            if verbose:
                print(f"[data] bulk fetch unavailable ({type(exc).__name__}); using fallback")

    for spec in config.TRACKED_OBJECTS:
        norad = int(spec["norad"])  # type: ignore[arg-type]
        cached = (cache.get("records") or {}).get(str(norad))
        if cached:
            records[norad] = TleRecord.from_dict(cached)
            continue
        if offline:
            continue
        try:
            raw = _http_json(config.FALLBACK_TLE_URL.format(norad_id=norad))
            rec = _normalise(raw, norad, "fallback-mirror")
            if rec:
                records[norad] = rec
                continue
        except Exception as exc:  # noqa: BLE001
            if verbose:
                print(f"[data] {norad} unavailable via fallback ({type(exc).__name__})")
        try:  # last resort: single object from the bulk source
            raw = _http_json(config.CELESTRAK_CATNR_URL.format(norad_id=norad))
            if isinstance(raw, list) and raw:
                rec = _normalise(raw[0], norad, "celestrak")
                if rec:
                    records[norad] = rec
        except Exception:  # noqa: BLE001
            pass

    if not offline:
        merged = dict(cache.get("records") or {})  # type: ignore[arg-type]
        merged.update({str(k): v.to_dict() for k, v in records.items()})
        cache["records"] = merged
        _write_cache(cache)

    resolved = list(records.values())
    if verbose:
        print(f"[data] resolved {len(resolved)}/{len(config.TRACKED_OBJECTS)} tracked objects")
    return resolved


def _parse_tle_text(text: str, norad_id: int, source: str) -> Optional[TleRecord]:
    """Parse the FORMAT=tle response, which is name + two lines of TLE.

    The payload is plain text, not JSON, with the object name on the first
    non-empty line and the element set on the next two.
    """
    lines = [ln.rstrip() for ln in text.splitlines() if ln.strip()]
    if len(lines) < 3:
        return None
    name, line1, line2 = lines[0], lines[1], lines[2]
    if not line1.startswith("1 ") or not line2.startswith("2 "):
        return None
    return TleRecord(norad_id, name.strip(), line1, line2, source)


def fetch_second_epoch(norad_id: int, verbose: bool = False) -> Optional[TleRecord]:
    """Fetch an independently published element set for one object.

    Used by the cross-epoch detector. This requests the *current* fit for a
    single object, which is normally a different generation from the element
    set already in our cache. The cache is deliberately NOT updated, so the
    original fit remains available as the "before" observation.

    Returns ``None`` when no distinct second epoch can be obtained; the caller
    must treat that as *no evidence*, never as agreement.
    """
    url = config.CELESTRAK_CATNR_URL.format(norad_id=norad_id)
    try:
        request = urllib.request.Request(
            url, headers={"User-Agent": config.USER_AGENT}
        )
        with urllib.request.urlopen(request, timeout=config.HTTP_TIMEOUT_S) as response:
            payload = response.read().decode("utf-8", errors="replace")
    except Exception as exc:  # noqa: BLE001
        if verbose:
            print(f"[data] second epoch unavailable for {norad_id}: {type(exc).__name__}")
        return None

    record = _parse_tle_text(payload, norad_id, "celestrak-catnr")
    if record is None:
        if verbose:
            print(f"[data] {norad_id}: could not parse the second-epoch response")
        return None

    # Compare against the PINNED baseline, not the live cache. The cache is
    # refreshed on every online run; the baseline is the 'before' snapshot and
    # must not move, or there is nothing independent left to compare against.
    baseline = (load_baseline().get("records") or {}).get(str(norad_id))
    if baseline:
        previous = TleRecord.from_dict(baseline)
        if previous.line1.strip() == record.line1.strip():
            if verbose:
                print(f"[data] {norad_id}: current fit matches the baseline exactly; "
                      f"no independent second epoch yet")
            return None
    return record

    norad = raw.get("norad_cat_id") or raw.get("norad_id") or raw.get("satid") or fallback_id
    name = raw.get("name") or raw.get("OBJECT_NAME") or raw.get("satname") or ""
    return TleRecord(int(norad), str(name), str(line1), str(line2), source)
