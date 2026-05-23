#!/usr/bin/env python3
"""
Headless Baltimore 311 pipeline: fetch → clean → spatial join → aggregate → save.

Equivalent to running notebooks 01-03 in sequence. Designed to run in CI
(GitHub Actions) or locally without Jupyter.

Usage:
    python scripts/pipeline.py --year 2024
    python scripts/pipeline.py --year 2026 --live
"""

import argparse
import shutil
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import geopandas as gpd
import pandas as pd

from balt311.ingest import fetch_year
from balt311.metrics import (
    aggregate_tract,
    clean_strings,
    compute_days_to_close,
    compute_due_date_gap,
    filter_equity_subset,
    flag_request_source,
    parse_timestamps,
    rollup_to_csa,
)

RAW_DIR = ROOT / "data" / "raw"
INTERIM = ROOT / "data" / "interim"
PROC    = ROOT / "data" / "processed"

TIGER_TRACT_URL = (
    "https://tigerweb.geo.census.gov/arcgis/rest/services"
    "/TIGERweb/tigerWMS_Current/MapServer/8/query"
    "?where=STATE%3D24+AND+COUNTY%3D510&outFields=GEOID,NAME&f=geojson"
)


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def download_with_retry(url: str, dest: Path, retries: int = 4) -> None:
    for attempt in range(1, retries + 1):
        try:
            urllib.request.urlretrieve(url, dest)
            return
        except Exception as exc:
            if attempt == retries:
                raise
            wait = 2 ** attempt
            log(f"  Download attempt {attempt} failed ({exc}); retrying in {wait}s")
            time.sleep(wait)


def run(year: int, is_live: bool) -> None:
    for d in (RAW_DIR, INTERIM, PROC):
        d.mkdir(parents=True, exist_ok=True)

    right_censor_days = 30 if is_live else 0
    log(f"Pipeline start — year={year}  live={is_live}  right_censor_days={right_censor_days}")
    t0 = time.time()

    # ── Stage 1: Ingest ──────────────────────────────────────────────────────
    log("=== Stage 1: Ingest ===")
    raw_path = RAW_DIR / f"requests_{year}.parquet"
    records = fetch_year(year)
    df_raw = pd.DataFrame(records)
    df_raw.to_parquet(raw_path, index=False)
    log(f"Saved {len(df_raw):,} rows → {raw_path.name}  ({time.time()-t0:.0f}s elapsed)")

    # ── Stage 2: Clean + spatial join ────────────────────────────────────────
    log("=== Stage 2: Clean + spatial join ===")

    tracts_path = RAW_DIR / "baltimore_tracts.geojson"
    if not tracts_path.exists():
        log("Downloading Baltimore census tract boundaries from TIGER/Line ...")
        download_with_retry(TIGER_TRACT_URL, tracts_path)
        log(f"  Saved → {tracts_path.name}")

    df = parse_timestamps(df_raw.copy())
    df = clean_strings(df)
    df = flag_request_source(df)
    df = compute_days_to_close(df)
    df = compute_due_date_gap(df)

    valid_coords = (
        df["Latitude"].notna()
        & df["Longitude"].notna()
        & (df["Latitude"] != 0)
    )
    df_geo = df[valid_coords].copy()
    log(f"Geocoded: {len(df_geo):,}/{len(df):,} ({100 * valid_coords.mean():.1f}%)")

    tracts = gpd.read_file(tracts_path).to_crs("EPSG:4326")
    gdf = gpd.GeoDataFrame(
        df_geo,
        geometry=gpd.points_from_xy(df_geo["Longitude"], df_geo["Latitude"]),
        crs="EPSG:4326",
    )
    joined = gpd.sjoin(gdf, tracts[["GEOID", "geometry"]], how="left", predicate="within")
    joined = joined.rename(columns={"GEOID": "tract_geoid"})

    no_tract = joined["tract_geoid"].isna().sum()
    log(f"Spatial join complete — {no_tract:,} unmatched ({100 * no_tract / len(joined):.1f}%)")

    df_clean = pd.DataFrame(
        joined.drop(columns=["geometry", "index_right"], errors="ignore")
    )
    interim_path = INTERIM / f"requests_{year}_clean.parquet"
    df_clean.to_parquet(interim_path, index=False)
    log(f"Saved {len(df_clean):,} rows → {interim_path.name}  ({time.time()-t0:.0f}s elapsed)")

    # ── Stage 3: Aggregate ───────────────────────────────────────────────────
    log("=== Stage 3: Aggregate ===")

    df_eq = filter_equity_subset(df_clean, right_censor_days=right_censor_days)
    log(
        f"Equity subset: {len(df_eq):,} rows across "
        f"{df_eq['tract_geoid'].nunique()} tracts"
    )

    tract_metrics = aggregate_tract(df_eq)
    out_tract = PROC / f"tract_metrics_{year}.parquet"
    tract_metrics.to_parquet(out_tract, index=False)
    log(f"Saved tract metrics ({len(tract_metrics)} tracts) → {out_tract.name}")

    crosswalk_path = RAW_DIR / "tract_to_csa.csv"
    if crosswalk_path.exists():
        xwalk = pd.read_csv(crosswalk_path)
        csa_metrics = rollup_to_csa(tract_metrics, xwalk)
        out_csa = PROC / f"csa_metrics_{year}.parquet"
        csa_metrics.to_parquet(out_csa, index=False)
        log(f"Saved CSA metrics ({len(csa_metrics)} CSAs) → {out_csa.name}")
    else:
        log("No crosswalk at data/raw/tract_to_csa.csv — CSA rollup skipped")

    shutil.copy(tracts_path, PROC / "tract_boundaries.geojson")
    log("Copied tract boundaries → processed/tract_boundaries.geojson")

    csa_geo = RAW_DIR / "baltimore_csas.geojson"
    if csa_geo.exists():
        shutil.copy(csa_geo, PROC / "csa_boundaries.geojson")
        log("Copied CSA boundaries → processed/csa_boundaries.geojson")

    log(f"Pipeline complete — total elapsed: {time.time()-t0:.0f}s")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Baltimore 311 equity pipeline")
    parser.add_argument("--year", type=int, required=True, help="Year to process")
    parser.add_argument(
        "--live",
        action="store_true",
        help="Current-year live file — applies 30-day right-censoring",
    )
    args = parser.parse_args()
    run(args.year, args.live)
