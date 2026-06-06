import json
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from components.category_equity_explorer import render_category_equity_explorer
from components.category_explorer import render_category_explorer
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


# ── Sidebar — dashboard overview ──────────────────────────────────────────────
with st.sidebar:
    st.title("Baltimore 311\nService Equity")
    st.markdown(
        "Operational and equity visibility into Baltimore's 311 "
        "service request system — 2016 through 2025."
    )
    st.caption(
        "The four tabs read as one arc: how the city is doing → how that breaks "
        "down by service → whether outcomes differ by neighborhood demographics → "
        "whether that citywide equity picture holds up once you account for "
        "*which* services an area actually requests."
    )
    st.divider()
    st.markdown(
        "**Operations** — start here\n\n"
        "*A citywide health check: request volume and performance trends.* "
        "Breakdown by service type with year-over-year comparison, plus "
        "geographic distribution of requests by census tract or CSA."
    )
    st.markdown(
        "**Services** — then, by department\n\n"
        "*How individual service categories perform and compare* — usage "
        "volume, closure rate, time to close, on-time rate — trended across "
        "years, with no race or income framing yet."
    )
    st.markdown(
        "**Equity** — then, citywide\n\n"
        "*Does service quality differ systematically by where it's delivered "
        "and who it's delivered to?* Choropleth map, demographic comparisons "
        "(race, income) via Mann-Whitney overlap scores, and a year-over-year "
        "equity trend — though differences here can reflect *which* services "
        "an area requests as much as delivery quality, which the next tab "
        "investigates."
    )
    st.markdown(
        "**Service Equity** — finally, by department\n\n"
        "*Does the citywide equity picture hold up or differ within individual "
        "service categories and types?* The same equity lens, scored within "
        "and across categories instead of citywide. The picture improves "
        "substantially at that finer grain — evidence that some of the "
        "citywide gap reflects *which* services different neighborhoods "
        "request, not just how they're delivered — though it doesn't fully "
        "close, so real disparities remain even after accounting for that."
    )
    st.divider()
    st.caption(
        "Data: Baltimore Open Data (311 requests 2016–2025) · "
        "Census ACS 2023 5-Year Estimates · BNIA Vital Signs crosswalk."
    )
    st.caption("*Detailed methodology and interpretation notes coming soon.*")


# ── Geographic unit — shared session state ────────────────────────────────────
if "geo_level" not in st.session_state:
    st.session_state["geo_level"] = "CSA"
geo_level = st.session_state["geo_level"]
geo_key = "tract" if geo_level == "Census Tract" else "csa"
featureidkey = "properties.GEOID" if geo_level == "Census Tract" else "properties.csa_name"


@st.cache_data
def available_years(gk: str) -> list[int]:
    files = sorted(DATA_DIR.glob(f"{gk}_metrics_*.parquet"))
    years = [int(f.stem.split("_")[-1]) for f in files]
    return sorted(years, reverse=True) if years else [2024]


years = available_years(geo_key)

# ── Header + year navigation ──────────────────────────────────────────────────
st.title("Baltimore 311 Service Equity")

if "ops_year_clicked" in st.session_state:
    clicked = st.session_state.pop("ops_year_clicked")
    if clicked in years:
        st.session_state["year_select"] = clicked

year = st.radio("Year", years, horizontal=True, key="year_select")
st.caption("Demographics from ACS 2023 5-Year Estimates")

# ── Data loading ──────────────────────────────────────────────────────────────
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

# ── Tabs ──────────────────────────────────────────────────────────────────────
tab_ops, tab_cat, tab_eq, tab_cat_eq = st.tabs([
    "Operations", "Services", "Equity", "Service Equity",
])

# ── Operations tab ────────────────────────────────────────────────────────────
with tab_ops:
    if not data_ready:
        st.info(
            f"No processed data found for **{year}** at **{geo_level}** level. "
            "Run the pipeline to generate it."
        )
    else:
        render_operations(
            DATA_DIR, geo_key, year,
            df=df_full,
            geojson=geojson,
            geo_id_col="geoid",
            featureidkey=featureidkey,
            mapbox_token=MAPBOX_TOKEN,
        )

# ── Service Category Explorer tab ─────────────────────────────────────────────
with tab_cat:
    if not data_ready:
        st.info(
            f"No processed data found for **{year}** at **{geo_level}** level. "
            "Run the pipeline to generate it."
        )
    else:
        render_category_explorer(DATA_DIR, year)

# ── Equity tab ────────────────────────────────────────────────────────────────
with tab_eq:
    if not data_ready:
        st.info(
            f"No processed data found for **{year}** at **{geo_level}** level.\n\n"
            "Run the pipeline notebooks in order:\n"
            "1. `notebooks/01_ingest.ipynb` — download raw data\n"
            "2. `notebooks/02_clean.ipynb` — parse and clean\n"
            "3. `notebooks/03_aggregate.ipynb` — aggregate to tract / CSA\n\n"
            f"Expected output: `data/processed/{geo_key}_metrics_{year}.parquet`",
            icon="ℹ️",
        )
    else:
        st.caption(
            "Does service quality differ systematically by where it's delivered and who "
            "it's delivered to? *Note: differences here can reflect the kinds of services "
            "delivered as much as delivery quality.*"
        )

        # ── Inline controls above map ─────────────────────────────────────────
        ctrl1, ctrl2, ctrl3 = st.columns([2, 3, 5])

        with ctrl1:
            _curr_geo_eq = st.session_state.get("geo_level", "Census Tract")
            new_geo_eq = st.radio(
                "Geographic unit",
                ["Census Tract", "CSA"],
                index=0 if _curr_geo_eq == "Census Tract" else 1,
                horizontal=True,
            )
            if new_geo_eq != _curr_geo_eq:
                st.session_state["geo_level"] = new_geo_eq
                st.rerun()

        with ctrl2:
            metric_label = st.selectbox(
                "Color map by",
                list(METRIC_OPTIONS.keys()),
                key="eq_metric",
            )
            metric_col = METRIC_OPTIONS[metric_label]

        with ctrl3:
            df = df_full
            if "top_sr_type" in df_full.columns:
                all_types = sorted(df_full["top_sr_type"].dropna().unique().tolist())
                selected_types = st.multiselect(
                    "Filter by top request type",
                    all_types,
                    default=[],
                    placeholder="All geographies",
                    key="eq_srtype",
                )
                if selected_types:
                    df = df_full[df_full["top_sr_type"].isin(selected_types)]

        # ── Choropleth map ────────────────────────────────────────────────────
        if metric_col not in df.columns:
            st.warning(f"Metric column `{metric_col}` not found in processed data.")
        else:
            col_map, col_panel = st.columns([3, 1])

            fig = build_choropleth(
                df=df,
                geojson=geojson,
                geo_id_col="geoid",
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
                    match = df[df["geoid"] == loc_val]
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

# ── Service Category Equity Explorer tab ──────────────────────────────────────
with tab_cat_eq:
    if not data_ready:
        st.info(
            f"No processed data found for **{year}** at **{geo_level}** level. "
            "Run the pipeline to generate it."
        )
    else:
        render_category_equity_explorer(DATA_DIR, demographics, geo_key, year)
