"""Generic Census TIGER cartographic-boundary tract fetch, for any city's FIPS.

Generalizes the within-Baltimore `_fetch_baltimore_tracts` (`scripts/pipeline.py`) — that
helper hardcodes Maryland (state 24) and Baltimore City (`COUNTYFP` "510"); this version
takes any 5-digit state+county FIPS, or several comma-separated ones (NYC's five boroughs,
all state 36), and returns the union as one GeoDataFrame. Used by the Phase 5.5 cross-city
equity tract×SRType join (`peer_metrics.compute_tract_srtype_metrics`).
"""
import tempfile
import time
import urllib.request
import zipfile
from pathlib import Path

# Census Bureau cartographic boundary shapefile, per state, 2020 tract definitions —
# same vintage as the within-Baltimore fetch, for one consistent tract geography cross-city.
TRACTS_ZIP_URL = "https://www2.census.gov/geo/tiger/GENZ2023/shp/cb_2023_{state}_tract_500k.zip"


def _download_with_retry(url: str, dest: Path, retries: int = 4) -> None:
    for attempt in range(1, retries + 1):
        try:
            urllib.request.urlretrieve(url, dest)
            return
        except Exception:
            if attempt == retries:
                raise
            time.sleep(2 ** attempt)


def fetch_city_tracts(fips: str):
    """Census cartographic-boundary tracts for a city's FIPS (5-digit state+county, or
    several comma-separated — grouped by state so a multi-county single-state city like
    NYC downloads each state's ZIP once). Returns a GeoDataFrame in EPSG:4326 with at
    least `GEOID` and `geometry`, filtered to the requested counties."""
    import geopandas as gpd
    import pandas as pd

    parts = [f.strip() for f in str(fips).split(",") if f.strip()]
    by_state: dict[str, list[str]] = {}
    for f in parts:
        by_state.setdefault(f[:2], []).append(f[2:])

    frames = []
    for state, counties in by_state.items():
        url = TRACTS_ZIP_URL.format(state=state)
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            zip_path = tmp_dir / "tracts.zip"
            _download_with_retry(url, zip_path)
            with zipfile.ZipFile(zip_path) as z:
                z.extractall(tmp_dir)
            shp_path = next(tmp_dir.glob("*.shp"))
            state_gdf = gpd.read_file(shp_path).to_crs("EPSG:4326")
            frames.append(state_gdf[state_gdf["COUNTYFP"].isin(counties)].copy())

    return gpd.GeoDataFrame(pd.concat(frames, ignore_index=True), crs="EPSG:4326")
