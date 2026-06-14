#!/usr/bin/env python3
"""Cross-city 311 ingestion + metrics (Phase 5.1).

For each requested city, fetch the year's records via its adapter, compute the uniform
delivery metrics, and upsert one (city, year) row into
`data/processed/peer_city_metrics.parquet`, alongside a `peer_city_meta.csv` of city
metadata (FIPS, ACS population, portal, closure definition).

ArcGIS endpoints are unreachable from sandboxed dev environments, so this is designed to
run in CI (see .github/workflows/peer_city.yml), exactly like the Baltimore backfill.

By default a (city, year) already in `peer_city_metrics.parquet` is reused, not refetched
(Baltimore alone is a ~12-min pull) — so adding a new city is cheap. `--force` reprocesses.

Usage:
    python scripts/peer_city.py --year 2024                    # all registered cities (skip existing)
    python scripts/peer_city.py --year 2024 --cities dc,philly # add cities; cached ones reused
    python scripts/peer_city.py --year 2025 --force            # reprocess all (e.g. after a fix)
    python scripts/peer_city.py --year 2025 --cities dc --force  # reprocess just DC
    python scripts/peer_city.py --year 2026 --live             # 30-day right-censoring
"""
import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import pandas as pd

from balt311.cities import ADAPTERS
from balt311.peer_metrics import (
    METRIC_COLUMNS,
    compute_city_metrics,
    fetch_county_population,
    upsert_metrics,
)

PROC = ROOT / "data" / "processed"
METRICS_PATH = PROC / "peer_city_metrics.parquet"
META_PATH = PROC / "peer_city_meta.csv"


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def run(year: int, cities: list[str], is_live: bool, force: bool = False) -> None:
    PROC.mkdir(parents=True, exist_ok=True)
    right_censor_days = 30 if is_live else 0

    existing = pd.read_parquet(METRICS_PATH) if METRICS_PATH.exists() else None
    have = (
        set(zip(existing["city"], existing["year"]))
        if existing is not None and not existing.empty else set()
    )
    meta = (
        pd.read_csv(META_PATH, dtype={"fips": str}).set_index("city").to_dict("index")
        if META_PATH.exists() else {}
    )

    new_rows = []
    failures = []
    skipped = []
    for slug in cities:
        if slug not in ADAPTERS:
            log(f"SKIP unknown city '{slug}' (known: {', '.join(ADAPTERS)})")
            continue
        adapter = ADAPTERS[slug]()

        # Smart reuse: keep an existing (city, year) row instead of re-fetching it (Baltimore
        # alone is a ~12-min pull), so adding a new city is cheap. --force overrides.
        if not force and (adapter.city, year) in have:
            log(f"CACHED — {adapter.city} {year} already present; skipping (use --force to refetch)")
            skipped.append(slug)
            continue

        log(f"=== {adapter.city} ({slug}) · {year} ===")

        # Isolate each city: a network failure on one (DC's ArcGIS can time out) must not
        # discard the others' completed work — write what succeeded, flag the rest.
        try:
            population = fetch_county_population(adapter.fips)
            log(f"  ACS population (FIPS {adapter.fips}): {population}")

            t0 = time.time()
            records = adapter.fetch(year)
            log(f"  fetched {len(records):,} records in {time.time() - t0:.0f}s")

            row = compute_city_metrics(
                records, city=adapter.city, year=year, population=population,
                right_censor_days=right_censor_days, closure_definition=adapter.closure_definition,
                scope_fn=adapter.scope, closed_fn=adapter.is_closed,
            )
            log(
                f"  total={row['total_requests']:,}  per_1k="
                f"{row['requests_per_1k']}  median_days={row['median_days_to_close']}  "
                f"closure_rate={row['closure_rate']}"
            )
            new_rows.append(row)
            meta[adapter.city] = {
                "fips": adapter.fips, "population": population,
                "portal_url": adapter.portal_url, "closure_definition": adapter.closure_definition,
            }
        except Exception as exc:
            log(f"  ERROR processing {slug} ({year}): {exc!r} — continuing with other cities")
            failures.append(slug)

    if not new_rows:
        if failures:
            log(f"All fetches failed: {', '.join(failures)} — nothing written.")
            sys.exit(1)
        log(f"Nothing to do — all requested cities already present ({', '.join(skipped)}). "
            "Use --force to reprocess.")
        return

    metrics = upsert_metrics(existing, new_rows)
    metrics.to_parquet(METRICS_PATH, index=False)
    log(f"Wrote {len(metrics)} rows → {METRICS_PATH.name}")

    meta_df = (
        pd.DataFrame.from_dict(meta, orient="index")
        .rename_axis("city").reset_index()
        [["city", "fips", "population", "portal_url", "closure_definition"]]
    )
    meta_df.to_csv(META_PATH, index=False)
    log(f"Wrote {len(meta_df)} rows → {META_PATH.name}")

    if failures:
        # Successful cities are already written/committed; exit non-zero so CI flags the
        # gap and the failed city can be re-run on its own.
        log(f"FAILED cities (re-run these): {', '.join(failures)}")
        sys.exit(1)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Cross-city 311 ingestion + metrics")
    p.add_argument("--year", type=int, required=True)
    p.add_argument("--cities", default=",".join(ADAPTERS),
                   help="Comma-separated city slugs (default: all registered)")
    p.add_argument("--live", action="store_true", help="Apply 30-day right-censoring")
    p.add_argument("--force", action="store_true",
                   help="Refetch even if a (city, year) row already exists (default: skip existing)")
    args = p.parse_args()
    run(args.year, [c.strip() for c in args.cities.split(",") if c.strip()], args.live, args.force)
