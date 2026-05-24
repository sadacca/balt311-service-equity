import json
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

# Make src/ importable when running from repo root
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from components.equity_distributions import render_equity_distributions
from components.equity_trend import render_equity_trend
from components.map_view import METRIC_OPTIONS, build_choropleth
from components.summary_panel import render as render_summary

DATA_DIR = Path(__file__).parent.parent / "data" / "processed"

st.set_page_config(
    page_title="Baltimore 311 Service Equity",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Mapbox token (set via .streamlit/secrets.toml or Streamlit Cloud secrets) ─
try:
    MAPBOX_TOKEN = st.secrets["mapbox"]["token"]
except (KeyError, FileNotFoundError):
    MAPBOX_TOKEN = ""


# ── Sidebar ───────────────────────────────────────────────────────────────────
st.sidebar.header("Filters")

geo_level = st.sidebar.radio(
    "Geographic unit",
    ["Census Tract", "CSA"],
    help="Tracts: ~200 areas. CSAs: 55 BNIA Community Statistical Areas.",
)
geo_key = "tract" if geo_level == "Census Tract" else "csa"


@st.cache_data
def available_years(gk: str) -> list[int]:
    files = sorted(DATA_DIR.glob(f"{gk}_metrics_*.parquet"))
    years = [int(f.stem.split("_")[-1]) for f in files]
    return sorted(years, reverse=True) if years else [2024]


years = available_years(geo_key)
year = st.sidebar.selectbox("Year", years)

parquet_path = DATA_DIR / f"{geo_key}_metrics_{year}.parquet"
geojson_path = DATA_DIR / f"{geo_key}_boundaries.geojson"
data_ready = parquet_path.exists() and geojson_path.exists()


@st.cache_data
def load_metrics(path: Path) -> pd.DataFrame:
    return pd.read_parquet(path)


@st.cache_data
def load_geojson(path: Path) -> dict:
    with open(path) as f:
        return json.load(f)


@st.cache_data
def load_demographics(path: Path) -> pd.DataFrame | None:
    if not path.exists():
        return None
    return pd.read_csv(path, dtype={"geoid": str})


if data_ready:
    df = load_metrics(parquet_path)
    geojson = load_geojson(geojson_path)
else:
    df, geojson = None, None

demographics = load_demographics(DATA_DIR / f"{geo_key}_demographics.csv")

# SRType filter (only when data is loaded)
if data_ready and "top_sr_type" in df.columns:
    all_types = sorted(df["top_sr_type"].dropna().unique().tolist())
    selected_types = st.sidebar.multiselect(
        "Request type (SRType)",
        all_types,
        default=[],
        placeholder="All types",
    )
    if selected_types:
        df = df[df["top_sr_type"].isin(selected_types)]

metric_label = st.sidebar.selectbox("Color map by", list(METRIC_OPTIONS.keys()))
metric_col = METRIC_OPTIONS[metric_label]


# ── Header ────────────────────────────────────────────────────────────────────
st.title("Baltimore 311 Service Equity")
st.caption(
    f"311 data {year} · {geo_level}s · Demographics from ACS 2023 5-Year Estimates"
)

col_map, col_panel = st.columns([3, 1])

if not data_ready:
    with col_map:
        st.info(
            f"No processed data found for **{year}** at **{geo_level}** level.\n\n"
            "Run the pipeline notebooks in order:\n"
            "1. `notebooks/01_ingest.ipynb` — download raw data (run locally)\n"
            "2. `notebooks/02_clean.ipynb` — parse and clean\n"
            "3. `notebooks/03_aggregate.ipynb` — aggregate to tract / CSA\n\n"
            f"Expected output: `data/processed/{geo_key}_metrics_{year}.parquet`",
            icon="ℹ️",
        )
    st.stop()


# ── Map ───────────────────────────────────────────────────────────────────────
geo_id_col = "geoid"
featureidkey = (
    "properties.GEOID" if geo_level == "Census Tract" else "properties.csa_name"
)

if metric_col not in df.columns:
    with col_map:
        st.warning(f"Metric column `{metric_col}` not found in processed data.")
    st.stop()

fig = build_choropleth(
    df=df,
    geojson=geojson,
    geo_id_col=geo_id_col,
    featureidkey=featureidkey,
    metric_col=metric_col,
    metric_label=metric_label,
    mapbox_token=MAPBOX_TOKEN,
)

with col_map:
    selection = st.plotly_chart(
        fig,
        use_container_width=True,
        on_select="rerun",
        key="map_select",
    )

# ── Summary panel ─────────────────────────────────────────────────────────────
selected_row = None
if selection and selection.get("selection", {}).get("points"):
    pt = selection["selection"]["points"][0]
    loc_val = pt.get("location")
    if loc_val is not None:
        match = df[df[geo_id_col] == loc_val]
        if not match.empty:
            selected_row = match.iloc[0]

with col_panel:
    render_summary(selected_row)


# ── City-wide summary bar ─────────────────────────────────────────────────────
st.divider()
c1, c2, c3, c4 = st.columns(4)
c1.metric(f"{geo_level}s shown", f"{len(df):,}")
if "median_days_to_close" in df.columns:
    c2.metric("Citywide median days to close", f"{df['median_days_to_close'].median():.1f}")
if "closure_rate" in df.columns:
    c3.metric("Citywide closure rate", f"{df['closure_rate'].mean():.1%}")
if "total_requests" in df.columns:
    c4.metric("Total requests", f"{df['total_requests'].sum():,.0f}")

# ── Demographic equity summaries ──────────────────────────────────────────────
if demographics is not None:
    st.divider()
    render_equity_distributions(df, demographics, metric_col, metric_label)
    st.divider()
    render_equity_trend(DATA_DIR, demographics, geo_key, metric_label)
else:
    st.divider()
    st.caption(
        "Demographic equity charts unavailable — "
        f"`{geo_key}_demographics.csv` not found in `data/processed/`. "
        "Re-run the pipeline to generate it."
    )
