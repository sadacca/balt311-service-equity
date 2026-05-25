import json
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from components.equity_distributions import render_equity_distributions
from components.equity_trend import render_equity_trend
from components.map_view import METRIC_OPTIONS, build_choropleth
from components.operations_panel import render_operations
from components.summary_panel import render as render_summary

DATA_DIR = Path(__file__).parent.parent / "data" / "processed"

st.set_page_config(
    page_title="Baltimore 311 Service Equity",
    layout="wide",
    initial_sidebar_state="expanded",
)

try:
    MAPBOX_TOKEN = st.secrets["mapbox"]["token"]
except (KeyError, FileNotFoundError):
    MAPBOX_TOKEN = ""


# ── Sidebar — filters that don't depend on year ───────────────────────────────
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

# ── Header + year navigation ──────────────────────────────────────────────────
st.title("Baltimore 311 Service Equity")

# Allow the operations time series to drive year selection via session state
if "ops_year_clicked" in st.session_state:
    clicked = st.session_state.pop("ops_year_clicked")
    if clicked in years:
        st.session_state["year_select"] = clicked

year = st.radio("Year", years, horizontal=True, key="year_select")
st.caption(f"{geo_level}s · Demographics from ACS 2023 5-Year Estimates")

# ── Data loading (depends on year) ────────────────────────────────────────────
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
    df_full = load_metrics(parquet_path)
    geojson = load_geojson(geojson_path)
else:
    df_full, geojson = None, None

demographics = load_demographics(DATA_DIR / f"{geo_key}_demographics.csv")

# ── Sidebar — filters that depend on loaded data ──────────────────────────────
df = df_full
if data_ready and "top_sr_type" in df_full.columns:
    all_types = sorted(df_full["top_sr_type"].dropna().unique().tolist())
    selected_types = st.sidebar.multiselect(
        "Request type (SRType)",
        all_types,
        default=[],
        placeholder="All types",
    )
    if selected_types:
        df = df_full[df_full["top_sr_type"].isin(selected_types)]

metric_label = st.sidebar.selectbox("Color map by", list(METRIC_OPTIONS.keys()))
metric_col = METRIC_OPTIONS[metric_label]

# ── Tabs ──────────────────────────────────────────────────────────────────────
tab_ops, tab_eq = st.tabs(["Operations", "Equity"])

# ── Operations tab ────────────────────────────────────────────────────────────
with tab_ops:
    if not data_ready:
        st.info(
            f"No processed data found for **{year}** at **{geo_level}** level. "
            "Run the pipeline to generate it."
        )
    else:
        render_operations(
            DATA_DIR, geo_key, year, metric_col, metric_label,
            df=df_full,
            geojson=geojson,
            geo_id_col="geoid",
            featureidkey=(
                "properties.GEOID" if geo_level == "Census Tract" else "properties.csa_name"
            ),
            mapbox_token=MAPBOX_TOKEN,
        )

# ── Equity tab ────────────────────────────────────────────────────────────────
with tab_eq:
    if not data_ready:
        st.info(
            f"No processed data found for **{year}** at **{geo_level}** level.\n\n"
            "Run the pipeline notebooks in order:\n"
            "1. `notebooks/01_ingest.ipynb` — download raw data (run locally)\n"
            "2. `notebooks/02_clean.ipynb` — parse and clean\n"
            "3. `notebooks/03_aggregate.ipynb` — aggregate to tract / CSA\n\n"
            f"Expected output: `data/processed/{geo_key}_metrics_{year}.parquet`",
            icon="ℹ️",
        )
    else:
        geo_id_col = "geoid"
        featureidkey = (
            "properties.GEOID" if geo_level == "Census Tract" else "properties.csa_name"
        )

        if metric_col not in df.columns:
            st.warning(f"Metric column `{metric_col}` not found in processed data.")
        else:
            col_map, col_panel = st.columns([3, 1])

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
