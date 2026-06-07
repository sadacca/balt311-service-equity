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

# ACS 2023 5-year variables for demographics. Expanding beyond race+income to
# include age structure, Hispanic/Latino ethnicity, educational attainment, and
# poverty rate — the fuller profile makes the demographic-space embedding in Tab 3
# meaningfully multi-dimensional rather than essentially a race-income scatter.
_ACS_VARS = [
    # Race (B02001)
    "B02001_001E", "B02001_002E", "B02001_003E",
    # Median household income — null sentinel -666666666 (B19013)
    "B19013_001E",
    # Age sex×age (B01001): total + under-18 cells + 65+ cells by sex
    "B01001_001E",
    "B01001_003E", "B01001_004E", "B01001_005E", "B01001_006E",    # male: <5, 5-9, 10-14, 15-17
    "B01001_020E", "B01001_021E", "B01001_022E", "B01001_023E", "B01001_024E", "B01001_025E",  # male: 65-66, 67-69, 70-74, 75-79, 80-84, 85+
    "B01001_027E", "B01001_028E", "B01001_029E", "B01001_030E",    # female: <5, 5-9, 10-14, 15-17
    "B01001_044E", "B01001_045E", "B01001_046E", "B01001_047E", "B01001_048E", "B01001_049E",  # female: 65-66 … 85+
    # Median age — null sentinel -666666666 (B01002)
    "B01002_001E",
    # Hispanic/Latino origin — any race (B03003)
    "B03003_001E", "B03003_003E",
    # Educational attainment for pop 25+ (B15003): total + bachelor's through doctorate
    "B15003_001E", "B15003_022E", "B15003_023E", "B15003_024E", "B15003_025E",
    # Poverty status (B17001): total for determination + below poverty level
    "B17001_001E", "B17001_002E",
]
ACS_DEMOGRAPHICS_URL = (
    "https://api.census.gov/data/2023/acs/acs5"
    "?get=" + ",".join(_ACS_VARS) + "&for=tract:*&in=state:24%20county:510"
)

# BNIA VitalSigns 2020 census-tract → CSA crosswalk.
# Columns: TRACT20, GEOID20 (11-digit), CSA2020.
# Rows with empty GEOID20 are summary totals — filtered on load.
CSA_CROSSWALK_URL = (
    "https://raw.githubusercontent.com/BNIA/VitalSigns/main/CSA2020.csv"
)

# Baltimore City Neighborhood Statistical Areas (NSA) — ~278 official named
# neighborhoods, more granular than the 55 BNIA CSAs.
# Source: Open Baltimore ArcGIS Hub (data.baltimorecity.gov)
# Item ID 8112521d3e284518b9fa497a188bfb45 / dataset slug: neighborhood-1
NSA_GEOJSON_URLS = [
    "https://opendata.arcgis.com/datasets/8112521d3e284518b9fa497a188bfb45_0.geojson",
    "https://data.baltimorecity.gov/api/download/v1/items/"
    "8112521d3e284518b9fa497a188bfb45/geojson?redirect=true&layers=0",
]
# Candidate field names for the NSA name in the downloaded GeoJSON.
_NSA_NAME_CANDIDATES = ["Name", "NAME", "NBRDESC", "LABEL", "Label", "label", "Neighborhood"]


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


def _fetch_tract_demographics(dest: Path) -> bool:
    """Download ACS 2023 5-year demographics for Baltimore City census tracts.

    Saves geoid, race pct and raw counts (accurate CSA rollup), median income,
    plus age structure (pct_under18, pct_65plus, median_age), Hispanic/Latino
    ethnicity (pct_hispanic), educational attainment (pct_bachelors_plus), and
    poverty rate (pct_poverty) — the fuller profile that makes the demographic-
    space embedding in Tab 3 meaningfully multi-dimensional.
    Returns True on success, False on soft failure.
    """
    api_key = os.environ.get("CENSUS_API_KEY", "").strip()
    url = ACS_DEMOGRAPHICS_URL + (f"&key={api_key}" if api_key else "")
    if not api_key:
        log("  NOTE: CENSUS_API_KEY not set — demographics request may be rate-limited")
    log("Downloading ACS 2023 5-year demographics (race, income, age, ethnicity, education, poverty) ...")
    raw = ""
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
            log(f"  Census API returned non-JSON (first 200 chars): {raw[:200]!r}")
            if attempt < 4:
                time.sleep(2 ** attempt)
                continue
            return False
        except Exception as exc:
            if attempt == 4:
                log(f"  Demographics download failed after {attempt} attempts: {exc}")
                return False
            wait = 2 ** attempt
            log(f"  Attempt {attempt} failed ({exc}); retrying in {wait}s")
            time.sleep(wait)

    headers, data = rows[0], rows[1:]
    df = pd.DataFrame(data, columns=headers)
    df["geoid"] = df["state"] + df["county"] + df["tract"]

    # Parse all ACS estimate columns as numeric; coerce non-numeric to NaN.
    for col in _ACS_VARS:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    # ACS uses -666666666 as the null sentinel for suppressed estimates.
    for col in _ACS_VARS:
        if col in df.columns:
            df.loc[df[col] < 0, col] = float("nan")

    # ── Race (B02001) ─────────────────────────────────────────────────────────
    total_race = df["B02001_001E"].replace(0, float("nan"))
    df["pct_black"] = df["B02001_003E"] / total_race
    df["pct_white"] = df["B02001_002E"] / total_race
    df["median_income"] = df["B19013_001E"]
    df["total_race_pop"] = df["B02001_001E"]
    df["black_pop"] = df["B02001_003E"]
    df["white_pop"] = df["B02001_002E"]

    # ── Age structure (B01001) ────────────────────────────────────────────────
    total_age = df["B01001_001E"].replace(0, float("nan"))
    _under18 = [
        "B01001_003E", "B01001_004E", "B01001_005E", "B01001_006E",   # male
        "B01001_027E", "B01001_028E", "B01001_029E", "B01001_030E",   # female
    ]
    _over65 = [
        "B01001_020E", "B01001_021E", "B01001_022E", "B01001_023E", "B01001_024E", "B01001_025E",  # male
        "B01001_044E", "B01001_045E", "B01001_046E", "B01001_047E", "B01001_048E", "B01001_049E",  # female
    ]
    df["pct_under18"] = df[_under18].sum(axis=1) / total_age
    df["pct_65plus"] = df[_over65].sum(axis=1) / total_age
    df["median_age"] = df["B01002_001E"]

    # ── Hispanic / Latino origin (B03003) ─────────────────────────────────────
    total_hisp = df["B03003_001E"].replace(0, float("nan"))
    df["pct_hispanic"] = df["B03003_003E"] / total_hisp

    # ── Educational attainment for pop 25+ (B15003) ───────────────────────────
    total_edu = df["B15003_001E"].replace(0, float("nan"))
    _bach_plus = ["B15003_022E", "B15003_023E", "B15003_024E", "B15003_025E"]
    df["pct_bachelors_plus"] = df[_bach_plus].sum(axis=1) / total_edu

    # ── Poverty rate (B17001) ─────────────────────────────────────────────────
    total_pov = df["B17001_001E"].replace(0, float("nan"))
    df["pct_poverty"] = df["B17001_002E"] / total_pov

    out_cols = [
        "geoid",
        "pct_black", "pct_white", "median_income",
        "total_race_pop", "black_pop", "white_pop",
        "pct_hispanic",
        "pct_under18", "pct_65plus", "median_age",
        "pct_bachelors_plus",
        "pct_poverty",
    ]
    df[out_cols].to_csv(dest, index=False)
    log(f"  {len(df)} tracts → {dest.name} ({len(out_cols) - 1} features)")
    return True


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


def _fetch_nsa_crosswalk(tracts_path: Path, dest: Path) -> None:
    """Download Baltimore NSA boundaries, spatial-join tract centroids, write crosswalk.

    Writes data/processed/tract_to_nsa.csv with columns (geoid, nsa_name).
    Tracts whose centroid falls outside all NSA polygons get nsa_name = ''.
    """
    import geopandas as gpd

    log("Downloading Baltimore NSA (Neighborhood Statistical Area) boundaries ...")

    with tempfile.TemporaryDirectory() as tmp:
        nsa_path = Path(tmp) / "nsa.geojson"
        last_exc: Exception | None = None
        for url in NSA_GEOJSON_URLS:
            try:
                download_with_retry(url, nsa_path)
                nsa_gdf = gpd.read_file(nsa_path).to_crs("EPSG:4326")
                log(f"  Fetched {len(nsa_gdf)} NSA polygons from {url.split('/')[2]}")
                break
            except Exception as exc:
                last_exc = exc
                log(f"  Download failed ({url.split('/')[2]}): {exc}")
        else:
            raise RuntimeError("NSA boundary download failed from all sources") from last_exc

    # Identify the neighborhood name field
    name_col = next((c for c in _NSA_NAME_CANDIDATES if c in nsa_gdf.columns), None)
    if name_col is None:
        str_cols = [c for c in nsa_gdf.columns if nsa_gdf[c].dtype == object and c != "geometry"]
        if not str_cols:
            raise ValueError(f"No string columns found in NSA GeoJSON; columns: {list(nsa_gdf.columns)}")
        name_col = str_cols[0]
        log(f"  WARNING: guessing name field '{name_col}'. Available: {list(nsa_gdf.columns)}")
    else:
        log(f"  Using name field '{name_col}' ({nsa_gdf[name_col].nunique()} unique values)")

    # Compute tract centroids and spatially join to NSA polygons
    tracts = gpd.read_file(tracts_path).to_crs("EPSG:4326")
    centroids = tracts[["GEOID", "geometry"]].copy()
    centroids["geometry"] = centroids.geometry.centroid

    joined = gpd.sjoin(
        centroids,
        nsa_gdf[[name_col, "geometry"]].rename(columns={name_col: "nsa_name"}),
        how="left",
        predicate="within",
    )
    # Deduplicate: a centroid at a boundary may match multiple polygons — keep first
    joined = joined[~joined.index.duplicated(keep="first")]

    crosswalk = (
        joined[["GEOID", "nsa_name"]]
        .rename(columns={"GEOID": "geoid"})
        .fillna({"nsa_name": ""})
    )
    crosswalk.to_csv(dest, index=False)

    matched = (crosswalk["nsa_name"] != "").sum()
    log(f"  {matched}/{len(crosswalk)} tracts matched to an NSA → {dest.name}")


def stage_nsa() -> None:
    """Fetch Baltimore NSA boundaries and build the tract→NSA name crosswalk.

    Writes data/processed/tract_to_nsa.csv (geoid, nsa_name). Year-independent
    — run once, or after NSA boundary updates. Reads tract_boundaries.geojson
    from data/processed/ (produced by stage_process); falls back to data/raw/.
    """
    for d in (RAW_DIR, INTERIM, PROC):
        d.mkdir(parents=True, exist_ok=True)

    log("=== Stage: NSA crosswalk ===")

    tracts_path = PROC / "tract_boundaries.geojson"
    if not tracts_path.exists():
        tracts_path = RAW_DIR / "baltimore_tracts.geojson"
    if not tracts_path.exists():
        raise FileNotFoundError(
            "tract_boundaries.geojson not found in data/processed/ or data/raw/. "
            "Run --stage process first to generate it."
        )

    _fetch_nsa_crosswalk(tracts_path, PROC / "tract_to_nsa.csv")
    log("NSA stage complete.")


def stage_ingest(year: int) -> None:
    """Stage 1: fetch raw 311 records from ArcGIS FeatureServer."""
    for d in (RAW_DIR, INTERIM, PROC):
        d.mkdir(parents=True, exist_ok=True)

    t0 = time.time()
    log(f"=== Stage 1: Ingest {year} ===")

    raw_path = RAW_DIR / f"requests_{year}.parquet"
    records = fetch_year(year)
    if not records:
        log(f"WARNING: 0 records returned for {year} — endpoint may be empty or unavailable.")
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
        rollup_demographics_to_csa,
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

    # Historical Yearly service stores Lat/Lon as strings; coerce to numeric.
    for _col in ("Latitude", "Longitude"):
        if _col in df_raw.columns and df_raw[_col].dtype == object:
            df_raw[_col] = pd.to_numeric(df_raw[_col], errors="coerce")

    if df_raw.empty:
        log(f"No records to process for {year} — skipping. Re-run ingest when data is available.")
        return

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
        pop = pd.read_csv(pop_path, dtype={"geoid": str})
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


def _geo_srtype_agg(df: pd.DataFrame, geo_col: str) -> pd.DataFrame:
    """Aggregate total_requests, closed_requests, closure_rate, and median_days_to_close
    by (geo_col, SRType). Caller is responsible for pre-filtering df as needed."""
    base = df.dropna(subset=[geo_col])
    agg = (
        base.groupby([geo_col, "SRType"])
        .agg(
            total_requests=("SRRecordID", "count"),
            closed_requests=("SRStatus", lambda s: (s.str.strip().str.lower() == "closed").sum()),
        )
        .reset_index()
    )
    agg["closure_rate"] = agg["closed_requests"] / agg["total_requests"].replace(0, float("nan"))
    if "days_to_close" in base.columns:
        dtc = (
            base.dropna(subset=["days_to_close"])
            .groupby([geo_col, "SRType"])["days_to_close"]
            .median()
            .reset_index(name="median_days_to_close")
        )
        agg = agg.merge(dtc, on=[geo_col, "SRType"], how="left")
    else:
        agg["median_days_to_close"] = float("nan")
    return agg


def stage_srtype(year: int) -> None:
    """Stage srtype: per-SRType aggregate metrics across ALL requests for a given year.

    Reads data/interim/requests_{year}_clean.parquet (produced by stage_process).
    Does NOT filter to the equity subset — uses every row regardless of source or
    geocoding status so the counts reflect true service-type volume.
    """
    for d in (RAW_DIR, INTERIM, PROC):
        d.mkdir(parents=True, exist_ok=True)

    log(f"=== Stage srtype: SRType aggregate {year} ===")

    interim_path = INTERIM / f"requests_{year}_clean.parquet"
    if not interim_path.exists():
        raise FileNotFoundError(
            f"{interim_path} not found. Run --stage process first."
        )
    df = pd.read_parquet(interim_path)
    log(f"Loaded {len(df):,} rows from {interim_path.name}")

    # ── closed mask (case-insensitive, whitespace-tolerant) ─────────────────
    closed_mask = df["SRStatus"].str.strip().str.lower() == "closed"

    agg = (
        df.groupby("SRType")
        .agg(
            total_requests=("SRRecordID", "count"),
            closed_requests=("SRStatus", lambda s: (s.str.strip().str.lower() == "closed").sum()),
        )
        .reset_index()
    )
    agg["closure_rate"] = agg["closed_requests"] / agg["total_requests"].replace(0, float("nan"))

    # ── median_days_to_close (drop NaN before aggregating) ──────────────────
    if "days_to_close" in df.columns:
        dtc = (
            df.dropna(subset=["days_to_close"])
            .groupby("SRType")["days_to_close"]
            .median()
            .reset_index(name="median_days_to_close")
        )
        agg = agg.merge(dtc, on="SRType", how="left")
    else:
        log("  WARNING: days_to_close column absent — median_days_to_close will be omitted")
        agg["median_days_to_close"] = float("nan")

    # ── on_time_rate (drop NaN before aggregating) ───────────────────────────
    if "is_on_time" in df.columns:
        otr = (
            df.dropna(subset=["is_on_time"])
            .groupby("SRType")["is_on_time"]
            .mean()
            .reset_index(name="on_time_rate")
        )
        agg = agg.merge(otr, on="SRType", how="left")
    else:
        log("  WARNING: is_on_time column absent — on_time_rate will be omitted")
        agg["on_time_rate"] = float("nan")

    # ── pct_resident_initiated ───────────────────────────────────────────────
    if "is_resident" in df.columns:
        res = (
            df.groupby("SRType")["is_resident"]
            .mean()
            .reset_index(name="pct_resident_initiated")
        )
        agg = agg.merge(res, on="SRType", how="left")
    else:
        log("  WARNING: is_resident column absent — pct_resident_initiated will be omitted")
        agg["pct_resident_initiated"] = float("nan")

    out_path = PROC / f"srtype_metrics_{year}.parquet"
    agg.to_parquet(out_path, index=False)
    log(f"Saved SRType metrics ({len(agg)} types) → {out_path.name}")

    # ── tract-level per-type metrics (enables geographic map filtering) ─────────
    if "tract_geoid" in df.columns:
        tract_metrics = _geo_srtype_agg(df, "tract_geoid").rename(columns={"tract_geoid": "geoid"})
        out_tract = PROC / f"tract_srtype_metrics_{year}.parquet"
        tract_metrics.to_parquet(out_tract, index=False)
        log(f"Saved tract SRType metrics ({len(tract_metrics)} rows, {tract_metrics['SRType'].nunique()} types) → {out_tract.name}")
    else:
        log("  WARNING: tract_geoid absent — tract_srtype_metrics skipped")

    # ── CSA-level per-type metrics ────────────────────────────────────────────
    crosswalk_path = RAW_DIR / "tract_to_csa.csv"
    if "tract_geoid" in df.columns and crosswalk_path.exists():
        xwalk = pd.read_csv(crosswalk_path, dtype={"geoid": str})
        df_csa = df.merge(xwalk.rename(columns={"geoid": "tract_geoid"}), on="tract_geoid", how="left")
        csa_metrics = (
            _geo_srtype_agg(df_csa.dropna(subset=["csa_name"]), "csa_name")
            .rename(columns={"csa_name": "geoid"})
        )
        out_csa = PROC / f"csa_srtype_metrics_{year}.parquet"
        csa_metrics.to_parquet(out_csa, index=False)
        log(f"Saved CSA SRType metrics ({len(csa_metrics)} rows, {csa_metrics['SRType'].nunique()} types) → {out_csa.name}")
    else:
        log("  WARNING: crosswalk absent or tract_geoid missing — csa_srtype_metrics skipped")


def stage_demographics() -> None:
    """Fetch ACS demographics and write commit-ready CSVs to data/processed/.

    Fetches race (B02001), median income (B19013), age structure (B01001/B01002),
    Hispanic/Latino ethnicity (B03003), educational attainment (B15003), and
    poverty rate (B17001) — the fuller profile used by Tab 3's demographic-space
    embedding. Year-independent: only needs to be run once. Fails loudly if the
    Census API is unavailable — check that CENSUS_API_KEY is set in the environment.
    """
    for d in (RAW_DIR, INTERIM, PROC):
        d.mkdir(parents=True, exist_ok=True)

    from balt311.metrics import rollup_demographics_to_csa

    log("=== Stage: Demographics ===")

    crosswalk_path = RAW_DIR / "tract_to_csa.csv"
    if not crosswalk_path.exists():
        _fetch_csa_crosswalk(crosswalk_path)

    tract_demo_path = PROC / "tract_demographics.csv"
    ok = _fetch_tract_demographics(tract_demo_path)
    if not ok:
        raise RuntimeError(
            "Demographics download failed — check CENSUS_API_KEY and Census API availability."
        )

    xwalk = pd.read_csv(crosswalk_path, dtype=str)
    tract_demo = pd.read_csv(tract_demo_path, dtype={"geoid": str})
    csa_demo = rollup_demographics_to_csa(tract_demo, xwalk)
    csa_demo_path = PROC / "csa_demographics.csv"
    csa_demo.to_csv(csa_demo_path, index=False)
    log(f"  CSA demographics: {len(csa_demo)} CSAs → {csa_demo_path.name}")
    log("Demographics stage complete.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Baltimore 311 equity pipeline")
    parser.add_argument("--year", type=int, help="Year to process (not required for --stage demographics)")
    parser.add_argument(
        "--stage",
        choices=["ingest", "process", "demographics", "srtype", "nsa", "all"],
        default="all",
        help=(
            "ingest=Stage 1 only; process=Stages 2+3 only; "
            "demographics=fetch ACS race+income CSVs (year-independent); "
            "srtype=per-SRType aggregate metrics (requires process output); "
            "nsa=build tract→NSA name crosswalk (year-independent, requires tract_boundaries.geojson); "
            "all=full pipeline (default)"
        ),
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="Current-year live file — applies 30-day right-censoring",
    )
    args = parser.parse_args()

    if args.stage == "demographics":
        stage_demographics()
    elif args.stage == "nsa":
        stage_nsa()
    else:
        if not args.year:
            parser.error("--year is required for stages: ingest, process, srtype, all")
        if args.stage == "ingest":
            stage_ingest(args.year)
        elif args.stage == "process":
            stage_process(args.year, args.live)
        elif args.stage == "srtype":
            stage_srtype(args.year)
        else:
            stage_ingest(args.year)
            stage_process(args.year, args.live)
