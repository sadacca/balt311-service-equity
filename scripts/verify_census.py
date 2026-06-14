"""Re-verify the 311 open-data coverage census by probing each city's live API.

The maturity census (`data/processed/peer_city_coverage_census.csv`) records, per city, a
`status` (scoreable / partial / unconfirmed) and an `evidence` tier describing HOW it was
verified — `api` (we hit the live dataset endpoint, the strongest), `city_docs` (the city's
own portal page), `third_party` (an aggregator / news), or `none`. This script makes the
`api` tier reproducible and re-runnable down the chain (Claude → GitHub Actions → a local
machine): for every row that carries an `endpoint` URL it fetches one record and reports
which of the analysis-critical fields — a created timestamp, a closed timestamp, and
geocoordinates — are actually present.

Run:
    python scripts/verify_census.py                 # probe every endpoint, print a report
    python scripts/verify_census.py --strict        # exit 1 if any api-tier endpoint regressed
    python scripts/verify_census.py --write          # refresh the `api_checked` / `api_fields` columns

It deliberately uses only the stdlib so it runs anywhere (CI, a bare container, a laptop)
with no install step.
"""
import argparse
import csv
import json
import sys
import urllib.parse
import urllib.request
from pathlib import Path

CENSUS = Path(__file__).resolve().parents[1] / "data" / "processed" / "peer_city_coverage_census.csv"
_HEADERS = {"User-Agent": "Mozilla/5.0 (balt311-census-verify)"}
TIMEOUT = 45

# Heuristic field-name matchers — open-311 schemas vary in naming across platforms.
_CREATED = ("created", "requested", "opened", "open_dt", "start", "intake", "receiv")
_CLOSED = ("closed", "resolved", "completed", "close_dt", "closeddate", "resolution_dt")
_GEO = ("lat", "lon", "latitude", "longitude", "the_geom", "geom", "point", "shape", "x_coord", "y_coord")


def _fetch_json(url: str):
    req = urllib.request.Request(url, headers=_HEADERS)
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return json.loads(r.read())


def _first_record_fields(endpoint: str) -> list[str]:
    """Fetch one record from a Socrata / ArcGIS / Carto endpoint and return its field names."""
    data = _fetch_json(endpoint)
    if isinstance(data, list):                       # Socrata: [ {field: val, ...} ]
        return list(data[0].keys()) if data else []
    if isinstance(data, dict):
        if "features" in data and data["features"]:  # ArcGIS: {features:[{attributes:{...}}]}
            feat = data["features"][0]
            return list((feat.get("attributes") or feat.get("properties") or {}).keys())
        if "rows" in data and data["rows"]:           # Carto: {rows:[{...}]}
            return list(data["rows"][0].keys())
        if "fields" in data:                          # ArcGIS metadata fallback
            return [f.get("name", "") for f in data["fields"]]
    return []


def _has(fields: list[str], needles: tuple[str, ...]) -> bool:
    low = [f.lower() for f in fields]
    return any(any(n in f for f in low) for n in needles)


def probe(endpoint: str) -> dict:
    try:
        fields = _first_record_fields(endpoint)
    except Exception as exc:
        return {"ok": False, "error": str(exc)[:140], "created": False, "closed": False, "geo": False}
    if not fields:
        return {"ok": False, "error": "no records returned", "created": False, "closed": False, "geo": False}
    return {
        "ok": True, "error": "",
        "created": _has(fields, _CREATED),
        "closed": _has(fields, _CLOSED),
        "geo": _has(fields, _GEO),
        "n_fields": len(fields),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--strict", action="store_true", help="exit 1 if any api-tier endpoint regressed")
    ap.add_argument("--write", action="store_true", help="write api_checked / api_fields back to the census")
    args = ap.parse_args()

    if not CENSUS.exists():
        print(f"census not found: {CENSUS}", file=sys.stderr)
        return 2
    rows = list(csv.DictReader(CENSUS.open()))
    if "endpoint" not in (rows[0].keys() if rows else []):
        print("census has no `endpoint` column yet — nothing to probe.", file=sys.stderr)
        return 0

    regressions = 0
    print(f"{'city':28} {'status':11} {'evidence':11} created closed geo   result")
    print("-" * 92)
    for row in rows:
        endpoint = (row.get("endpoint") or "").strip()
        if not endpoint:
            continue
        res = probe(endpoint)
        flags = "".join("  ✓   " if res[k] else "  ·   " for k in ("created", "closed", "geo"))
        verdict = "OK" if res["ok"] else f"FAIL: {res['error']}"
        if res["ok"] and not (res["created"] and res["geo"]):
            verdict = "THIN (missing created/geo)"
        print(f"{row['city']:28} {row.get('status',''):11} {row.get('evidence',''):11} {flags} {verdict}")
        # an api-tier scoreable row that no longer returns the core fields is a regression
        if row.get("evidence") == "api" and row.get("status") == "scoreable" and not (
            res["ok"] and res["created"] and res["geo"]
        ):
            regressions += 1
        if args.write:
            row["api_checked"] = "ok" if res["ok"] else "fail"
            row["api_fields"] = "+".join(k for k in ("created", "closed", "geo") if res.get(k))

    if args.write:
        cols = list(rows[0].keys())
        for extra in ("api_checked", "api_fields"):
            if extra not in cols:
                cols.append(extra)
        with CENSUS.open("w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=cols)
            w.writeheader()
            w.writerows(rows)
        print(f"\nwrote api_checked / api_fields to {CENSUS.name}")

    print(f"\n{regressions} api-tier regression(s).")
    return 1 if (args.strict and regressions) else 0


if __name__ == "__main__":
    raise SystemExit(main())
