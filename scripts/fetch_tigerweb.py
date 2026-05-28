"""
Fetch Census tract GeoJSON from TIGERweb and prepare it for Plotly choropleth maps.

TIGERweb is the Census Bureau's ArcGIS REST service for geographic boundaries.
This script mirrors the pattern used by the 311 ingest: paginated ArcGIS queries,
retry with backoff, GeoJSON output compatible with build_choropleth().

Usage
-----
    python scripts/fetch_tigerweb.py                      # Baltimore tracts → data/processed/
    python scripts/fetch_tigerweb.py --state 24 --county 510 --out data/processed/tract_boundaries.geojson

The output GeoJSON has features with:
  properties.GEOID  → 11-digit Census tract ID  (matches tract_metrics_{year}.parquet "geoid" column)
  properties.NAME   → human-readable tract name
"""

import argparse
import json
import time
import urllib.parse
import urllib.request
from pathlib import Path

# ---------------------------------------------------------------------------
# TIGERweb ArcGIS REST endpoints
# ---------------------------------------------------------------------------
# Census 2020 Tracts layer (layer 6 in the tigerWMS_Current service).
# Outfields: GEOID (11-digit), NAME, STATE, COUNTY, TRACT.
TIGERWEB_BASE = (
    "https://tigerweb.geo.census.gov/arcgis/rest/services"
    "/TIGERweb/tigerWMS_Current/MapServer/6/query"
)

# Geographic SR 4326 (WGS84) — required by Plotly / Mapbox choropleths.
_OUT_SR = 4326
_PAGE_SIZE = 1000   # TIGERweb hard-caps responses at 1,000 features
_RETRIES = 4


# ---------------------------------------------------------------------------
# Fetch helpers
# ---------------------------------------------------------------------------

def _get(url: str, timeout: int = 30, retries: int = _RETRIES) -> dict:
    """GET a URL with exponential-backoff retries; return parsed JSON."""
    for attempt in range(1, retries + 1):
        try:
            with urllib.request.urlopen(url, timeout=timeout) as resp:
                return json.loads(resp.read())
        except Exception as exc:
            if attempt == retries:
                raise
            wait = 2 ** attempt
            print(f"  attempt {attempt} failed ({exc}); retrying in {wait}s")
            time.sleep(wait)
    return {}  # unreachable


def _count(state_fips: str, county_fips: str) -> int:
    """Return the server's total feature count for the given county."""
    where = f"STATE='{state_fips}' AND COUNTY='{county_fips}'"
    params = urllib.parse.urlencode({
        "where": where,
        "returnCountOnly": "true",
        "f": "json",
    })
    data = _get(f"{TIGERWEB_BASE}?{params}")
    return int(data.get("count", 0))


def _fetch_page(state_fips: str, county_fips: str, offset: int) -> list[dict]:
    """Fetch one page of GeoJSON features (WGS84) from TIGERweb."""
    where = f"STATE='{state_fips}' AND COUNTY='{county_fips}'"
    params = urllib.parse.urlencode({
        "where": where,
        "outFields": "GEOID,NAME,STATE,COUNTY,TRACT",
        "outSR": _OUT_SR,
        "resultOffset": offset,
        "resultRecordCount": _PAGE_SIZE,
        "f": "geojson",
    })
    data = _get(f"{TIGERWEB_BASE}?{params}")
    return data.get("features", [])


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def fetch_tract_geojson(state_fips: str, county_fips: str) -> dict:
    """
    Fetch all Census tract boundaries for a county from TIGERweb.

    Parameters
    ----------
    state_fips  : 2-digit state FIPS code, e.g. "24" for Maryland
    county_fips : 3-digit county FIPS code, e.g. "510" for Baltimore City

    Returns
    -------
    A GeoJSON FeatureCollection dict ready for use with:
      - plotly.express.choropleth_mapbox (featureidkey="properties.GEOID")
      - geopandas.GeoDataFrame.from_features()
    """
    total = _count(state_fips, county_fips)
    print(f"TIGERweb reports {total} tracts for state={state_fips} county={county_fips}")

    features: list[dict] = []
    offset = 0
    while True:
        page = _fetch_page(state_fips, county_fips, offset)
        features.extend(page)
        print(f"  offset={offset:>4}  +{len(page):>3}  total_so_far={len(features)}")
        if len(page) < _PAGE_SIZE:
            break
        offset += _PAGE_SIZE

    return {
        "type": "FeatureCollection",
        "features": features,
    }


def load_tract_geojson(
    state_fips: str = "24",
    county_fips: str = "510",
    cache_path: str | Path | None = None,
) -> dict:
    """
    Load tract GeoJSON from cache if available, otherwise fetch from TIGERweb.

    Parameters
    ----------
    state_fips  : 2-digit state FIPS (default "24" = Maryland)
    county_fips : 3-digit county FIPS (default "510" = Baltimore City)
    cache_path  : path to read/write a local .geojson file; None = no caching

    Returns
    -------
    GeoJSON FeatureCollection dict.
    """
    if cache_path is not None:
        path = Path(cache_path)
        if path.exists():
            print(f"Loading tract boundaries from cache: {path}")
            return json.loads(path.read_text())

    geojson = fetch_tract_geojson(state_fips, county_fips)

    if cache_path is not None:
        Path(cache_path).parent.mkdir(parents=True, exist_ok=True)
        Path(cache_path).write_text(json.dumps(geojson))
        print(f"Saved {len(geojson['features'])} features → {cache_path}")

    return geojson


# ---------------------------------------------------------------------------
# Choropleth usage example
# ---------------------------------------------------------------------------

def example_choropleth(geojson: dict, df, metric_col: str = "median_days_to_close"):
    """
    Build a Plotly choropleth_mapbox from TIGERweb boundaries.

    The GeoJSON feature key is "properties.GEOID" (11-digit tract ID).
    Your dataframe must have a "geoid" column with matching 11-digit strings.

    This mirrors how app/components/map_view.py calls build_choropleth().
    """
    import plotly.express as px

    fig = px.choropleth_mapbox(
        df,
        geojson=geojson,
        locations="geoid",                    # column in df
        featureidkey="properties.GEOID",      # key in GeoJSON feature properties
        color=metric_col,
        color_continuous_scale="RdBu_r",
        color_continuous_midpoint=df[metric_col].median(),
        mapbox_style="carto-positron",        # no token required (public style)
        zoom=10.5,
        center={"lat": 39.2904, "lon": -76.6122},
        opacity=0.75,
        labels={metric_col: metric_col.replace("_", " ").title()},
    )
    fig.update_layout(margin={"r": 0, "t": 0, "l": 0, "b": 0}, height=600)
    return fig


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Fetch Census tract GeoJSON from TIGERweb")
    p.add_argument("--state",  default="24",  help="2-digit state FIPS (default: 24 = Maryland)")
    p.add_argument("--county", default="510", help="3-digit county FIPS (default: 510 = Baltimore City)")
    p.add_argument(
        "--out",
        default="data/processed/tract_boundaries_tigerweb.geojson",
        help="Output path for the GeoJSON file",
    )
    return p.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    geojson = load_tract_geojson(
        state_fips=args.state,
        county_fips=args.county,
        cache_path=args.out,
    )
    print(f"\nReady: {len(geojson['features'])} tract features")
    print(f"Sample GEOID: {geojson['features'][0]['properties'].get('GEOID', 'n/a')}")
