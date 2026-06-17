#!/usr/bin/env python3
"""Cross-city equity methodology (Phase 5.5), step 1: per-city tract median income.

Scope is **income-only** for this phase (see TASKS.md Phase 5.5 note): a race-based split
needs a city-appropriate group definition (Baltimore's majority-Black/majority-White split
doesn't generalize to a plurality-Hispanic or no-majority-tract cohort city), so it's
deferred to a follow-up phase rather than forced onto every city now. Income has no such
problem — each city's tracts are split above/below *that city's own* median, which is
self-relative and never empty.

ACS 5-year estimates are a single (year-independent) vintage, like `tract_demographics.csv`
— this is a one-time-per-city fetch, not a per-year pull like `peer_city.py`. Output is one
row per (city, tract): `data/processed/peer_city_tract_income.parquet`. A later step
(P5.5-2/5.5-3) spatially joins each city's 311 records to these tracts and computes the
mix-adjusted income equity score from the above/below-median split.

Usage:
    python scripts/peer_city_equity.py                       # all registered cities (skip existing)
    python scripts/peer_city_equity.py --cities dc,philadelphia
    python scripts/peer_city_equity.py --force                # refetch all
"""
import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import pandas as pd

from balt311.cities import ADAPTERS
from balt311.peer_metrics import fetch_tract_median_income

PROC = ROOT / "data" / "processed"
INCOME_PATH = PROC / "peer_city_tract_income.parquet"


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def run(cities: list[str], force: bool = False, income_path: Path = INCOME_PATH) -> None:
    income_path.parent.mkdir(parents=True, exist_ok=True)

    existing = pd.read_parquet(income_path) if income_path.exists() else None
    have_cities = set(existing["city"]) if existing is not None and not existing.empty else set()

    new_frames = []
    failures = []
    skipped = []
    for slug in cities:
        if slug not in ADAPTERS:
            log(f"SKIP unknown city '{slug}' (known: {', '.join(ADAPTERS)})")
            continue
        adapter = ADAPTERS[slug]()

        # Smart reuse, same convention as peer_city.py: ACS vintage doesn't change between
        # runs, so a city already present is skipped unless --force.
        if not force and adapter.city in have_cities:
            log(f"CACHED — {adapter.city} tract income already present; skipping (use --force to refetch)")
            skipped.append(slug)
            continue

        log(f"=== {adapter.city} ({slug}) tract median income ===")
        try:
            df = fetch_tract_median_income(adapter.fips)
            if df.empty:
                raise RuntimeError(f"no tracts returned for fips={adapter.fips}")
            df.insert(0, "city", adapter.city)
            n_valid = int(df["median_income"].notna().sum())
            log(f"  {len(df)} tracts ({n_valid} with a valid median income)")
            new_frames.append(df)
        except Exception as exc:
            # Isolate each city, same as peer_city.py: one city's ACS hiccup shouldn't
            # discard the others' completed work.
            log(f"  ERROR fetching {slug}: {exc!r} — continuing with other cities")
            failures.append(slug)

    if not new_frames:
        if failures:
            log(f"All fetches failed: {', '.join(failures)} — nothing written.")
            sys.exit(1)
        log(f"Nothing to do — all requested cities already present ({', '.join(skipped)}). "
            "Use --force to reprocess.")
        return

    new_df = pd.concat(new_frames, ignore_index=True)
    if existing is not None and not existing.empty:
        kept = existing[~existing["city"].isin(new_df["city"])]
        combined = pd.concat([kept, new_df], ignore_index=True)
    else:
        combined = new_df
    combined = combined.sort_values(["city", "geoid"]).reset_index(drop=True)
    combined.to_parquet(income_path, index=False)
    log(f"Wrote {len(combined)} rows ({combined['city'].nunique()} cities) → {income_path}")

    if failures:
        log(f"FAILED cities (re-run these): {', '.join(failures)}")
        sys.exit(1)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Per-city tract median income (Phase 5.5 step 1)")
    p.add_argument("--cities", default=",".join(ADAPTERS),
                   help="Comma-separated city slugs (default: all registered)")
    p.add_argument("--force", action="store_true",
                   help="Refetch even if the city is already present (default: skip existing)")
    p.add_argument("--income-path", default=str(INCOME_PATH),
                   help="Where to read/write the tract-income parquet")
    args = p.parse_args()

    run([c.strip() for c in args.cities.split(",") if c.strip()],
        args.force, Path(args.income_path))
