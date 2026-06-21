#!/usr/bin/env python3
"""Fill the maturity coverage census's `population` column from the live Census ACS.

The maturity scorecard sorts cities by size, so every census city needs a population. The
cohort and originally hand-curated cities carry a figure in `scripts/score_maturity.POPULATION`
(the offline seed); this script fetches the rest — e.g. a newly-added top-50 city that has no
seed value yet — from the ACS 5-year place table (B01003), matching the census city name to a
Census place, and writes a `population` column into `peer_city_coverage_census.csv` so
`score_maturity.py` picks it up. Network + an optional `CENSUS_API_KEY` (env) are required, so
this is meant for CI / a networked machine.

    python scripts/fetch_census_population.py            # fill only cities with no population
    python scripts/fetch_census_population.py --all      # refetch every city from ACS (authoritative)
    python scripts/fetch_census_population.py --acs-year 2023

Default = fill-only: cities that already have a population (census column or seed) are kept, so
a normal run only touches genuinely-new cities. `--all` re-fetches everything from ACS.

Stdlib only, so it runs anywhere with no install step (it imports the seed dict lazily).
"""
import argparse
import csv
import json
import os
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CENSUS = ROOT / "data" / "processed" / "peer_city_coverage_census.csv"

# State USPS abbreviation → 2-digit FIPS (50 states + DC), for the ACS place query.
STATE_FIPS = {
    "AL": "01", "AK": "02", "AZ": "04", "AR": "05", "CA": "06", "CO": "08", "CT": "09",
    "DE": "10", "DC": "11", "FL": "12", "GA": "13", "HI": "15", "ID": "16", "IL": "17",
    "IN": "18", "IA": "19", "KS": "20", "KY": "21", "LA": "22", "ME": "23", "MD": "24",
    "MA": "25", "MI": "26", "MN": "27", "MS": "28", "MO": "29", "MT": "30", "NE": "31",
    "NV": "32", "NH": "33", "NJ": "34", "NM": "35", "NY": "36", "NC": "37", "ND": "38",
    "OH": "39", "OK": "40", "OR": "41", "PA": "42", "RI": "44", "SC": "45", "SD": "46",
    "TN": "47", "TX": "48", "UT": "49", "VT": "50", "VA": "51", "WA": "53", "WV": "54",
    "WI": "55", "WY": "56",
}
_HEADERS = {"Accept": "application/json", "User-Agent": "balt311-census-pop"}


def _seed_pop() -> dict:
    """The curated offline populations from score_maturity (best-effort import)."""
    sys.path.insert(0, str(ROOT / "scripts"))
    try:
        from score_maturity import POPULATION
        return dict(POPULATION)
    except Exception:
        return {}


def _fetch_state_places(state_fips: str, acs_year: int, api_key: str) -> list[tuple[str, int]]:
    """All places in a state with their ACS population — [(NAME, pop), ...]."""
    url = (
        f"https://api.census.gov/data/{acs_year}/acs/acs5"
        f"?get=NAME,B01003_001E&for=place:*&in=state:{state_fips}"
        + (f"&key={api_key}" if api_key else "")
    )
    for attempt in range(1, 5):
        try:
            req = urllib.request.Request(url, headers=_HEADERS)
            with urllib.request.urlopen(req, timeout=45) as r:
                rows = json.loads(r.read().decode("utf-8"))
            out = []
            for row in rows[1:]:  # row[0] is the header
                name, pop = row[0], row[1]
                try:
                    pop = int(float(pop))
                except (TypeError, ValueError):
                    continue
                if pop >= 0:
                    out.append((name, pop))
            return out
        except Exception:
            if attempt == 4:
                return []
            time.sleep(2 ** attempt)
    return []


def _match(city_name: str, places: list[tuple[str, int]]) -> tuple[int | None, str | None]:
    """Match the census city to a Census place. Census NAMEs look like 'Long Beach city,
    California' / 'Nashville-Davidson metropolitan government (balance), Tennessee', so the
    place-part *starts with* the city name; among matches we take the largest population (so
    'Miami' picks Miami city, not Miami Beach). Falls back to a substring match."""
    target = city_name.strip().lower()

    def place_part(name: str) -> str:
        return name.split(",")[0].strip().lower()

    cands = [(pop, name) for name, pop in places if place_part(name).startswith(target)]
    if not cands:
        cands = [(pop, name) for name, pop in places if target in place_part(name)]
    if not cands:
        return None, None
    pop, name = max(cands)
    return pop, name


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true",
                    help="refetch every city from ACS (override curated/seed values)")
    ap.add_argument("--acs-year", type=int, default=2023)
    args = ap.parse_args()

    if not CENSUS.exists():
        print(f"census not found: {CENSUS}", file=sys.stderr)
        return 2

    rows = list(csv.DictReader(CENSUS.open()))
    if not rows:
        print("census is empty", file=sys.stderr)
        return 2
    api_key = os.environ.get("CENSUS_API_KEY", "").strip()
    seed = _seed_pop()
    state_cache: dict[str, list[tuple[str, int]]] = {}
    fetched = unmatched = 0

    print(f"{'city':26} {'population':>11}  source")
    print("-" * 64)
    for row in rows:
        city = row["city"]
        existing = (row.get("population") or "").strip()
        if not existing and seed.get(city) is not None:
            existing = str(int(seed[city]))

        # Default: keep any population we already have; only fetch what's missing.
        if existing and not args.all:
            row["population"] = existing
            print(f"{city:26} {existing:>11}  kept")
            continue

        if "," not in city or STATE_FIPS.get(city.rsplit(",", 1)[1].strip()) is None:
            row["population"] = existing
            print(f"{city:26} {(existing or '?'):>11}  SKIP (no/unknown state)")
            continue

        name, st = (p.strip() for p in city.rsplit(",", 1))
        fips = STATE_FIPS[st]
        if fips not in state_cache:
            state_cache[fips] = _fetch_state_places(fips, args.acs_year, api_key)
        pop, matched = _match(name, state_cache[fips])
        if pop is None:
            row["population"] = existing
            unmatched += 1
            print(f"{city:26} {(existing or '?'):>11}  NO MATCH (kept)")
            continue
        row["population"] = str(pop)
        fetched += 1
        print(f"{city:26} {pop:>11}  ACS «{matched}»")

    # Write back, inserting `population` right after `city` if it's a new column.
    cols = list(rows[0].keys())
    if "population" not in cols:
        cols.insert(cols.index("city") + 1 if "city" in cols else len(cols), "population")
    with CENSUS.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        for r in rows:
            r.setdefault("population", "")
            w.writerow(r)

    print(f"\nFetched {fetched} from ACS ({unmatched} unmatched); wrote {CENSUS.name} "
          f"({len(rows)} rows). Re-run score_maturity.py to fold into the scorecard.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
