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
    fetch_place_population,
    upsert_metrics,
)


def resolve_population(adapter) -> float | None:
    """City-proper place population when the adapter declares a `place_fips` (correct for a
    311 system), else the county total. Falls back to county if the place lookup fails."""
    place = getattr(adapter, "place_fips", "")
    if place:
        pop = fetch_place_population(place)
        if pop is not None:
            return pop
        log(f"  place population lookup failed for {place}; falling back to county {adapter.fips}")
    return fetch_county_population(adapter.fips)

PROC = ROOT / "data" / "processed"
METRICS_PATH = PROC / "peer_city_metrics.parquet"
META_PATH = PROC / "peer_city_meta.csv"


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def run(year: int, cities: list[str], is_live: bool, force: bool = False,
        metrics_path: Path = METRICS_PATH, meta_path: Path = META_PATH) -> None:
    metrics_path.parent.mkdir(parents=True, exist_ok=True)
    PROC.mkdir(parents=True, exist_ok=True)
    right_censor_days = 30 if is_live else 0

    existing = pd.read_parquet(metrics_path) if metrics_path.exists() else None
    have = (
        set(zip(existing["city"], existing["year"]))
        if existing is not None and not existing.empty else set()
    )
    meta = (
        pd.read_csv(meta_path, dtype={"fips": str}).set_index("city").to_dict("index")
        if meta_path.exists() else {}
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
            population = resolve_population(adapter)
            pop_src = f"place {adapter.place_fips}" if getattr(adapter, "place_fips", "") else f"county {adapter.fips}"
            log(f"  ACS population ({pop_src}): {population}")

            # Prefer metrics already computed by the within-app pipeline (Baltimore) so the
            # cross-city row equals the Operations tab and no re-fetch is needed.
            pre = adapter.precomputed(year, PROC)
            if pre is not None:
                log(f"  using within-app pooled metrics for {adapter.city} {year} (no re-fetch)")
                row = {
                    "city": adapter.city, "year": int(year),
                    "total_requests": pre["total_requests"],
                    "requests_per_1k": (pre["total_requests"] / population * 1000.0) if population else None,
                    "median_days_to_close": pre["median_days_to_close"],
                    "closure_rate": pre["closure_rate"],
                    "on_time_rate": pre["on_time_rate"],
                    "population": population, "closure_definition": adapter.closure_definition,
                }
            else:
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
    metrics.to_parquet(metrics_path, index=False)
    log(f"Wrote {len(metrics)} rows → {metrics_path}")

    meta_df = (
        pd.DataFrame.from_dict(meta, orient="index")
        .rename_axis("city").reset_index()
        [["city", "fips", "population", "portal_url", "closure_definition"]]
    )
    meta_df.to_csv(meta_path, index=False)
    log(f"Wrote {len(meta_df)} rows → {meta_path}")

    if failures:
        # Successful cities are already written/committed; exit non-zero so CI flags the
        # gap and the failed city can be re-run on its own.
        log(f"FAILED cities (re-run these): {', '.join(failures)}")
        sys.exit(1)


def merge_artifacts(in_dir: str, metrics_path: Path = METRICS_PATH,
                    meta_path: Path = META_PATH) -> None:
    """Merge per-city artifacts (from the parallel matrix workflow) into the canonical files.

    Each matrix job writes its own `<city>.parquet` + `<city>.meta.csv` so the parallel fetch
    jobs never touch the shared file (no commit races). This collects all of them — recursively,
    since `download-artifact` nests each artifact in its own subdir — and upserts once."""
    src = Path(in_dir)
    rows: list[dict] = []
    parts = sorted(p for p in src.rglob("*.parquet") if p.resolve() != metrics_path.resolve())
    for part in parts:
        rows.extend(pd.read_parquet(part).to_dict("records"))
    if rows:
        existing = pd.read_parquet(metrics_path) if metrics_path.exists() else None
        metrics = upsert_metrics(existing, rows)
        metrics.to_parquet(metrics_path, index=False)
        log(f"Merged {len(parts)} metric parts → {len(metrics)} rows in {metrics_path}")

    meta: dict = {}
    if meta_path.exists():
        meta = pd.read_csv(meta_path, dtype={"fips": str}).set_index("city").to_dict("index")
    meta_parts = sorted(p for p in src.rglob("*.csv")
                        if "meta" in p.name and p.resolve() != meta_path.resolve())
    for part in meta_parts:
        for _, r in pd.read_csv(part, dtype={"fips": str}).iterrows():
            meta[r["city"]] = {k: r[k] for k in ("fips", "population", "portal_url", "closure_definition")}
    if meta:
        meta_df = (pd.DataFrame.from_dict(meta, orient="index").rename_axis("city").reset_index()
                   [["city", "fips", "population", "portal_url", "closure_definition"]])
        meta_df.to_csv(meta_path, index=False)
        log(f"Merged {len(meta_parts)} meta parts → {len(meta_df)} rows in {meta_path}")

    _print_merge_sanity(metrics_path)


def _print_merge_sanity(metrics_path: Path) -> None:
    """Per-city sanity table so an under-pulling / missing adapter is loud in the merge log,
    not a silent 0-row drop. Flags an implausibly low per-1k (a likely wrong dataset)."""
    if not metrics_path.exists():
        log("no metrics file to summarize.")
        return
    df = pd.read_parquet(metrics_path)
    latest = df.sort_values("year").groupby("city").tail(1).sort_values("requests_per_1k")
    log(f"=== cross-city sanity ({df['city'].nunique()} cities) ===")
    for _, r in latest.iterrows():
        p1k = r.get("requests_per_1k")
        flag = "  ⚠ implausibly low — check dataset" if (p1k is not None and p1k == p1k and p1k < 20) else ""
        log(f"  {r['city']:20} {int(r['year'])}  total={int(r['total_requests']):>9,}  "
            f"per_1k={p1k:.0f}{flag}" if p1k == p1k else
            f"  {r['city']:20} {int(r['year'])}  total={int(r['total_requests']):>9,}  per_1k=NA")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Cross-city 311 ingestion + metrics")
    p.add_argument("--year", type=int, help="Year to process (required unless --merge)")
    p.add_argument("--cities", default=",".join(ADAPTERS),
                   help="Comma-separated city slugs (default: all registered)")
    p.add_argument("--live", action="store_true", help="Apply 30-day right-censoring")
    p.add_argument("--force", action="store_true",
                   help="Refetch even if a (city, year) row already exists (default: skip existing)")
    p.add_argument("--metrics-path", default=str(METRICS_PATH),
                   help="Where to read/write the metrics parquet (matrix jobs use a per-city path)")
    p.add_argument("--meta-path", default=str(META_PATH),
                   help="Where to read/write the meta csv")
    p.add_argument("--merge", metavar="DIR",
                   help="Merge per-city artifact dir into the canonical files, then exit")
    args = p.parse_args()

    metrics_path, meta_path = Path(args.metrics_path), Path(args.meta_path)
    if args.merge:
        merge_artifacts(args.merge, metrics_path, meta_path)
    else:
        if args.year is None:
            p.error("--year is required unless --merge is given")
        run(args.year, [c.strip() for c in args.cities.split(",") if c.strip()],
            args.live, args.force, metrics_path, meta_path)
