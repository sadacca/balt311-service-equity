#!/usr/bin/env python3
"""Cross-city equity methodology (Phase 5.5), step 3: per-city mix-adjusted income equity
score. Combines the three Phase 5.5 inputs that already exist on disk —
`peer_city_tract_srtype_metrics.parquet` (5.5-2), `peer_city_tract_metrics.parquet` (5.5-2),
and `peer_city_tract_income.parquet` (5.5-1) — into one row per (city, year):
`adj_income_score` (within-SRType, volume-weighted — "how the same service is delivered"),
`raw_income_score` (pooled across SRType — "overall, including which services an area
requests"), and `raw_median_days_gap` (the raw between-group median-days-to-close gap,
below-median-income minus above-median-income; positive means the poorer half waits longer).

This is a pure local computation (no network fetch) over already-committed parquet files,
so it's near-instant and re-run freely — every (city, year) is recomputed by default rather
than cached, since the upstream inputs can be regenerated/backfilled at any time and a stale
score would silently disagree with its own inputs.

Usage:
    python scripts/peer_city_equity_score.py                  # all (city, year) in the tract data
    python scripts/peer_city_equity_score.py --cities dc,philadelphia
"""
import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import pandas as pd

from balt311.cities import ADAPTERS
from balt311.peer_metrics import EQUITY_COLUMNS, compute_income_equity_score

PROC = ROOT / "data" / "processed"
TRACT_SRTYPE_PATH = PROC / "peer_city_tract_srtype_metrics.parquet"
TRACT_PATH = PROC / "peer_city_tract_metrics.parquet"
INCOME_PATH = PROC / "peer_city_tract_income.parquet"
EQUITY_PATH = PROC / "peer_city_equity.parquet"


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def run(
    cities: list[str],
    *,
    tract_srtype_path: Path = TRACT_SRTYPE_PATH,
    tract_path: Path = TRACT_PATH,
    income_path: Path = INCOME_PATH,
    equity_path: Path = EQUITY_PATH,
) -> None:
    equity_path.parent.mkdir(parents=True, exist_ok=True)

    if not tract_srtype_path.exists() or not income_path.exists():
        log(f"Missing required input(s) — need {tract_srtype_path.name} and "
            f"{income_path.name} (run peer_city.py and peer_city_equity.py first).")
        sys.exit(1)

    tract_srtype = pd.read_parquet(tract_srtype_path)
    tract_pooled = pd.read_parquet(tract_path) if tract_path.exists() else pd.DataFrame()
    income = pd.read_parquet(income_path)

    wanted_display = {ADAPTERS[s]().city for s in cities if s in ADAPTERS}
    if wanted_display:
        tract_srtype = tract_srtype[tract_srtype["city"].isin(wanted_display)]
        if not tract_pooled.empty:
            tract_pooled = tract_pooled[tract_pooled["city"].isin(wanted_display)]

    if tract_srtype.empty:
        log("No (city, year) rows found for the requested cities — nothing to score.")
        return

    rows = []
    for (city, year), grp in tract_srtype.groupby(["city", "year"]):
        city_income = income[income["city"] == city]
        if city_income.empty:
            log(f"  SKIP {city} {year} — no tract income data for this city")
            continue
        city_pooled = (
            tract_pooled[(tract_pooled["city"] == city) & (tract_pooled["year"] == year)]
            if not tract_pooled.empty else pd.DataFrame()
        )
        score = compute_income_equity_score(grp, city_pooled, city_income)
        score["city"] = city
        score["year"] = int(year)
        rows.append(score)
        log(f"  {city} {year}: adj={score['adj_income_score']} raw={score['raw_income_score']} "
            f"gap={score['raw_median_days_gap']} (n_tracts={score['n_tracts']}, "
            f"n_srtypes_scored={score['n_srtypes_scored']})")

    if not rows:
        log("Nothing scored — no city had both tract×SRType data and income data.")
        return

    new_df = pd.DataFrame(rows)[EQUITY_COLUMNS]

    existing = pd.read_parquet(equity_path) if equity_path.exists() else None
    if existing is not None and not existing.empty:
        keys = set(zip(new_df["city"], new_df["year"]))
        kept = existing[~existing.apply(lambda r: (r["city"], r["year"]) in keys, axis=1)]
        combined = pd.concat([kept, new_df], ignore_index=True)
    else:
        combined = new_df
    combined = combined.sort_values(["city", "year"]).reset_index(drop=True)
    combined.to_parquet(equity_path, index=False)
    log(f"Wrote {len(combined)} rows ({combined['city'].nunique()} cities) → {equity_path}")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Per-city mix-adjusted income equity score (Phase 5.5-3)")
    p.add_argument("--cities", default=",".join(ADAPTERS),
                   help="Comma-separated city slugs (default: all registered)")
    args = p.parse_args()

    run([c.strip() for c in args.cities.split(",") if c.strip()])
