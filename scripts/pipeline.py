#!/usr/bin/env python3
"""
Headless Baltimore 311 pipeline: fetch → clean → spatial join → aggregate → save.

Equivalent to running notebooks 01-03 in sequence. Designed to run in CI
(GitHub Actions) or locally without Jupyter.

Usage:
    # Run everything (local use)
    python scripts/pipeline.py --year 2024

    # Run only Stage 1 — fetch raw data (CI ingest job)
    python scripts/pipeline.py --year 2025 --stage ingest

    # Run only Stages 2+3 — clean, join, aggregate (CI process job)
    # Requires data/raw/requests_{year}.parquet to already exist
    python scripts/pipeline.py --year 2025 --stage process [--live]
"""

import argparse
import json
import os
import shutil
import sys
import tempfile
import time
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import pandas as pd

from balt311.ingest import fetch_year

RAW_DIR = ROOT / "data" / "raw"
INTERIM = ROOT / "data" / "interim"
PROC    = ROOT / "data" / "processed"

# Census Bureau cartographic boundary shapefile — Maryland tracts, 2020 definitions.
# ZIP format is unambiguous; JSON naming conventions have changed across Census releases.
MD_TRACTS_ZIP_URL = (
    "https://www2.census.gov/geo/tiger/GENZ2023/shp/cb_2023_24_tract_500k.zip"
)

# ACS 2023 5-year total population (B01003) — all tracts in Baltimore City (state=24, county=510).
# No API key required for this query.
ACS_POPULATION_URL = (
    "https://api.census.gov/data/2023/acs/acs5"
    "?get=B01003_001E&for=tract:*&in=state:24%20county:510"
)

# BNIA VitalSigns 2020 census-tract → CSA crosswalk.
# Columns: TRACT20, GEOID20 (11-digit), CSA2020.
# Rows with empty GEOID20 are summary totals — filtered on load.
CSA_CROSSWALK_URL = (
    "https://raw.githubusercontent.com/BNIA/VitalSigns/main/CSA2020.csv"
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


def _fetch_baltimore_tracts(dest: Path) -> None:
    """Download Census cartographic boundary ZIP, extract SHP, filter to Baltimore City."""
    import geopandas as gpd

    log("Downloading Maryland census tract boundaries (Census GENZ2023 shapefile) ...")
    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        zip_path = tmp_dir / "tracts.zip"
        download_with_retry(MD_TRACTS_ZIP_URL, zip_path)

        with zipfile.ZipFile(zip_path) as z:
            z.extractall(tmp_dir)

        shp_path = next(tmp_dir.glob("*.shp"))
        md = gpd.read_file(shp_path).to_crs("EPSG:4326")
        balt = md[md["COUNTYFP"] == "510"].copy()
        balt.to_file(dest, driver="GeoJSON")
        log(f"  {len(balt)} Baltimore City tracts saved → {dest.name}")


def _fetch_baltimore_population(dest: Path) -> bool:
    """Download ACS 2023 5-year total population for Baltimore City census tracts.

    Reads CENSUS_API_KEY from the environment and appends it to the request.
    Get a free key at https://api.census.gov/data/key_signup.html and set it
    as a GitHub Actions secret named CENSUS_API_KEY.

    Returns True on success. On failure logs a warning and returns False so the
    pipeline can continue without population data (requests_per_1k will be omitted).
    """
    api_key = os.environ.get("CENSUS_API_KEY", "").strip()
    url = ACS_POPULATION_URL + (f"&key={api_key}" if api_key else "")
    if not api_key:
        log("  NOTE: CENSUS_API_KEY not set — request may be rate-limited")
    log("Downloading ACS 2023 5-year population estimates (Baltimore City tracts) ...")
    for attempt in range(1, 5):
        try:
            req = urllib.request.Request(url, headers={"Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=30) as resp:
                if resp.status != 200:
                    raise ValueError(f"HTTP {resp.status}")
                raw = resp.read().decode("utf-8").strip()
            if not raw:
                raise ValueError("Empty response body")
            rows = json.loads(raw)
            break
        except json.JSONDecodeError:
            log(f"  Census API returned non-JSON (first 500 chars): {raw[:500]!r}")
            if attempt < 4:
                time.sleep(2 ** attempt)
                continue
            log("  WARNING: population download failed — requests_per_1k will be omitted")
            return False
        except Exception as exc:
            if attempt == 4:
                log(f"  WARNING: population download failed ({exc}) — requests_per_1k will be omitted")
                return False
            wait = 2 ** attempt
            log(f"  Attempt {attempt} failed ({exc}); retrying in {wait}s")
            time.sleep(wait)

    headers, data = rows[0], rows[1:]
    df = pd.DataFrame(data, columns=headers)
    df["geoid"] = df["state"] + df["county"] + df["tract"]
    df = df.rename(columns={"B01003_001E": "population"})
    df["population"] = pd.to_numeric(df["population"], errors="coerce")
    df[["geoid", "population"]].to_csv(dest, index=False)
    log(f"  {len(df)} tracts → {dest.name}")
    return True
    log(f"  {len(df)} tracts → {dest.name}")


def _fetch_csa_crosswalk(dest: Path) -> None:
    """Download BNIA 2020 tract→CSA crosswalk and save as geoid,csa_name CSV."""
    log("Downloading BNIA VitalSigns 2020 tract→CSA crosswalk ...")
    with tempfile.TemporaryDirectory() as tmp:
        raw = Path(tmp) / "csa2020.csv"
        download_with_retry(CSA_CROSSWALK_URL, raw)
        df = pd.read_csv(raw, dtype=str)
    # Drop summary rows that have no GEOID (e.g. city-total row)
    df = df[df["GEOID20"].notna() & (df["GEOID20"].str.strip() != "")].copy()
    df = df.rename(columns={"GEOID20": "geoid", "CSA2020": "csa_name"})
    df[["geoid", "csa_name"]].to_csv(dest, index=False)
    log(f"  {len(df)} tracts → {df['csa_name'].nunique()} CSAs → {dest.name}")


def _build_csa_boundaries(tracts_path: Path, crosswalk_path: Path, dest: Path) -> None:
    """Dissolve tract polygons by CSA name to produce CSA boundary GeoJSON.

    CSAs are defined as aggregations of census tracts, so this exactly matches
    the authoritative definition — no separate boundary download needed.
    """
    import geopandas as gpd

    log("Building CSA boundaries by dissolving tract polygons ...")
    tracts = gpd.read_file(tracts_path).to_crs("EPSG:4326")[["GEOID", "geometry"]]
    xwalk = pd.read_csv(crosswalk_path, dtype=str)
    merged = tracts.merge(xwalk, left_on="GEOID", right_on="geoid", how="left")
    csas = (
        merged[merged["csa_name"].notna()]
        .dissolve(by="csa_name", as_index=False)[["csa_name", "geometry"]]
    )
    csas.to_file(dest, driver="GeoJSON")
    log(f"  {len(csas)} CSA polygons → {dest.name}")


def stage_ingest(year: int) -> None:
    """Stage 1: fetch raw 311 records from ArcGIS FeatureServer."""
    for d in (RAW_DIR, INTERIM, PROC):
        d.mkdir(parents=True, exist_ok=True)

    t0 = time.time()
    log(f"=== Stage 1: Ingest {year} ===")

    raw_path = RAW_DIR / f"requests_{year}.parquet"
    records = fetch_year(year)
    df_raw = pd.DataFrame(records)
    df_raw.to_parquet(raw_path, index=False)
    log(f"Saved {len(df_raw):,} rows → {raw_path.name}  ({time.time()-t0:.0f}s elapsed)")


def stage_process(year: int, is_live: bool) -> None:
    """Stages 2+3: clean, spatial join, aggregate. Reads data/raw/requests_{year}.parquet."""
    import geopandas as gpd
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

    for d in (RAW_DIR, INTERIM, PROC):
        d.mkdir(parents=True, exist_ok=True)

    right_censor_days = 30 if is_live else 0
    t0 = time.time()

    # ── Stage 2: Clean + spatial join ────────────────────────────────────────
    log(f"=== Stage 2: Clean + spatial join (right_censor_days={right_censor_days}) ===")

    raw_path = RAW_DIR / f"requests_{year}.parquet"
    if not raw_path.exists():
        raise FileNotFoundError(
            f"{raw_path} not found. Run --stage ingest first."
        )
    df_raw = pd.read_parquet(raw_path)
    log(f"Loaded {len(df_raw):,} rows from {raw_path.name}")

    tracts_path = RAW_DIR / "baltimore_tracts.geojson"
    if not tracts_path.exists():
        _fetch_baltimore_tracts(tracts_path)

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

    # ── Population enrichment (optional — soft failure) ──────────────────────
    pop_path = RAW_DIR / "tract_population.csv"
    if not pop_path.exists():
        _fetch_baltimore_population(pop_path)
    if pop_path.exists():
        pop = pd.read_csv(pop_path)
        tract_metrics = tract_metrics.merge(pop, on="geoid", how="left")
        tract_metrics["requests_per_1k"] = (
            tract_metrics["total_requests"] / tract_metrics["population"].replace(0, float("nan")) * 1000
        )
        missing_pop = tract_metrics["population"].isna().sum()
        if missing_pop:
            log(f"  WARNING: {missing_pop} tract(s) missing population data")
    else:
        log("  Population unavailable — population and requests_per_1k columns omitted")

    out_tract = PROC / f"tract_metrics_{year}.parquet"
    tract_metrics.to_parquet(out_tract, index=False)
    log(f"Saved tract metrics ({len(tract_metrics)} tracts) → {out_tract.name}")

    crosswalk_path = RAW_DIR / "tract_to_csa.csv"
    if not crosswalk_path.exists():
        _fetch_csa_crosswalk(crosswalk_path)

    csa_geo = RAW_DIR / "baltimore_csas.geojson"
    if not csa_geo.exists():
        _build_csa_boundaries(tracts_path, crosswalk_path, csa_geo)

    xwalk = pd.read_csv(crosswalk_path, dtype=str)
    unmatched = set(tract_metrics["geoid"]) - set(xwalk["geoid"])
    if unmatched:
        log(f"  {len(unmatched)} tract(s) not in CSA crosswalk — excluded from CSA rollup")
    csa_metrics = rollup_to_csa(tract_metrics, xwalk)
    out_csa = PROC / f"csa_metrics_{year}.parquet"
    csa_metrics.to_parquet(out_csa, index=False)
    log(f"Saved CSA metrics ({len(csa_metrics)} CSAs) → {out_csa.name}")

    shutil.copy(tracts_path, PROC / "tract_boundaries.geojson")
    log("Copied tract boundaries → processed/tract_boundaries.geojson")

    shutil.copy(csa_geo, PROC / "csa_boundaries.geojson")
    log("Copied CSA boundaries → processed/csa_boundaries.geojson")

    log(f"Process stages complete — total elapsed: {time.time()-t0:.0f}s")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Baltimore 311 equity pipeline")
    parser.add_argument("--year", type=int, required=True, help="Year to process")
    parser.add_argument(
        "--stage",
        choices=["ingest", "process", "all"],
        default="all",
        help="ingest=Stage 1 only; process=Stages 2+3 only; all=full pipeline (default)",
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="Current-year live file — applies 30-day right-censoring",
    )
    args = parser.parse_args()

    if args.stage == "ingest":
        stage_ingest(args.year)
    elif args.stage == "process":
        stage_process(args.year, args.live)
    else:
        stage_ingest(args.year)
        stage_process(args.year, args.live)
