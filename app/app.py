import json
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from components.area_embedding import render_area_embedding
from components.category_equity_explorer import render_category_equity_explorer
from components.category_explorer import render_category_explorer
from components.cross_city import (
    render_cross_city_intro,
    render_delivery_placeholder,
    render_equity_placeholder,
    render_maturity_placeholder,
)
from components.equity_adjusted import render_equity_adjusted
from components.equity_panel import render_equity
from components.operations_panel import render_operations

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
        "Does your neighborhood affect how quickly Baltimore responds when you call 311? "
        "Explore a decade of city service data — 2016 through 2025 — to find out."
    )
    with st.expander("What is 311?"):
        st.markdown(
            "311 is Baltimore's non-emergency city services hotline. Residents call, "
            "text, or use the app to report problems — potholes, broken streetlights, "
            "illegal dumping, missed trash pickups — and to request services like bulk "
            "item pickup. Every request is logged with a location, date, and service "
            "type, making it possible to track how quickly the city responds across "
            "different neighborhoods."
        )
    st.caption(
        "The dashboard has two parts. **Within Baltimore** tells one six-step story: "
        "start with how the city is doing overall → zoom into individual service types "
        "→ see which neighborhoods look alike → check whether outcomes differ by race or "
        "income → ask whether that gap holds up within service categories → and finally "
        "separate how much of it is about *which* services an area requests versus how "
        "the same service is delivered. **Compare cities** *(coming in Phase 5)* sets "
        "Baltimore against peer cities on the same metrics."
    )
    st.divider()
    st.markdown("### Within Baltimore — the story")
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
        "**Areas** — then, by neighborhood pattern\n\n"
        "*Which neighborhoods use 311 similarly — and which look alike "
        "demographically?* Two complementary 2D embeddings in a shared "
        "coordinate space. Cross-color them to see whether demographic "
        "similarity predicts 311-usage similarity. Tract dots labeled with "
        "NSA neighborhood names; a service-type bar and neighborhood list "
        "by quadrant sit below the scatter."
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
    st.markdown(
        "**Mix-Adjusted Equity** — the payoff\n\n"
        "*How much of the citywide gap is about which services an area requests "
        "versus how the same service is delivered?* The citywide score recomputed "
        "within each service type and recombined volume-weighted, a ranking of the "
        "most unequally delivered types, and a fixed-effects regression as an "
        "independent check."
    )
    st.divider()
    st.markdown("### Compare cities — coming in Phase 5")
    st.markdown(
        "*Baltimore against peer and leading cities at the city level* — delivery "
        "metrics, each city's own mix-adjusted equity score, and an open-data "
        "maturity index. Different data, different caveats; a separate group so the "
        "city-to-city comparison never gets confused with the within-Baltimore story."
    )
    with st.expander("Key terms"):
        st.markdown(
            "**Closure rate** — the share of requests marked resolved. "
            "A lower rate may mean backlog or that the issue couldn't be addressed.\n\n"
            "**Median days to close** — the typical number of days from filing to "
            "closure. Half of requests closed faster, half slower.\n\n"
            "**On-time rate** — the share of requests completed within the city's "
            "stated deadline for that service type.\n\n"
            "**Equity score** — how similar outcomes are between demographic groups. "
            "100% = no gap · 0% = complete separation.\n\n"
            "**Census tract** — a small geographic area (~4,000 residents) defined "
            "by the U.S. Census Bureau.\n\n"
            "**CSA (Community Statistical Area)** — Baltimore's 55 official "
            "neighborhood groupings used for city data tracking and planning.\n\n"
            "**Requests per 1,000 residents** — request count adjusted for "
            "neighborhood size so areas of different populations can be compared fairly.\n\n"
            "**Embedding / PCA** — in the Area tab, each neighborhood's 2D position "
            "is computed by a method (Principal Component Analysis) that places "
            "neighborhoods with similar profiles close together. "
            "Position = similarity, not geography."
        )
    st.divider()
    st.caption(
        "Data: Baltimore Open Data (311 requests 2016–2025) · "
        "Census ACS 2023 5-Year Estimates · BNIA Vital Signs crosswalk."
    )
    st.caption("*Detailed methodology and interpretation notes coming soon.*")


# ── Geographic unit — shared session state ────────────────────────────────────
# State only here; the toggle widget lives inside the Within-Baltimore group below
# (geo level is meaningless for the city-level Compare-cities group).
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
# Year is global to both groups (cross-city data is also city × year).
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

_NO_DATA_MSG = (
    f"No processed data found for **{year}** at **{geo_level}** level. "
    "Run the pipeline to generate it."
)


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

# ── Two groups: the within-Baltimore story, and the cross-city comparison ─────
grp_local, grp_cross = st.tabs(["🏙️ Within Baltimore", "🌐 Compare cities"])

# ══ Within Baltimore — the sequenced six-step story ═══════════════════════════
with grp_local:
    st.caption(
        "A six-step story: how Baltimore delivers 311 service, then whether it does so "
        "equitably — read left to right."
    )

    # ── Geographic unit — one global control for the whole group ──────────────
    # Writes the shared `geo_level` state every within-Baltimore tab reads. The Area
    # Service Usage tab is the exception: it shows tracts and CSAs together and ignores
    # this toggle.
    geo_col, _ = st.columns([2, 8])
    with geo_col:
        new_geo = st.radio(
            "Geographic unit",
            ["Census Tract", "CSA"],
            index=0 if geo_level == "Census Tract" else 1,
            horizontal=True,
            help="Applies to every tab in this group except Area Service Usage.",
        )
        if new_geo != geo_level:
            st.session_state["geo_level"] = new_geo
            st.rerun()

    tab_ops, tab_cat, tab_areas, tab_eq, tab_cat_eq, tab_adj = st.tabs([
        "Operations", "Services", "Area Service Usage", "Equity", "Service Equity",
        "Mix-Adjusted Equity",
    ])

    with tab_ops:
        if not data_ready:
            st.info(_NO_DATA_MSG)
        else:
            render_operations(
                DATA_DIR, geo_key, year,
                df=df_full,
                geojson=geojson,
                geo_id_col="geoid",
                featureidkey=featureidkey,
                mapbox_token=MAPBOX_TOKEN,
            )

    with tab_cat:
        if not data_ready:
            st.info(_NO_DATA_MSG)
        else:
            render_category_explorer(DATA_DIR, year)

    with tab_areas:
        render_area_embedding(DATA_DIR, year)

    with tab_eq:
        if not data_ready:
            st.info(_NO_DATA_MSG)
        else:
            render_equity(
                DATA_DIR, geo_key, year,
                df_full=df_full,
                geojson=geojson,
                featureidkey=featureidkey,
                mapbox_token=MAPBOX_TOKEN,
                demographics=demographics,
            )

    with tab_cat_eq:
        if not data_ready:
            st.info(_NO_DATA_MSG)
        else:
            render_category_equity_explorer(DATA_DIR, demographics, geo_key, year)

    with tab_adj:
        if not data_ready:
            st.info(_NO_DATA_MSG)
        else:
            # Carry over the Equity tab's metric selection so the two equity tabs stay
            # aligned; falls back to days-to-close inside the component when that metric
            # doesn't exist at the service-type grain.
            render_equity_adjusted(
                DATA_DIR, demographics, geo_key, year,
                eq_metric_label=st.session_state.get("eq_metric"),
            )

# ══ Compare cities — Phase 5 (scaffold) ═══════════════════════════════════════
with grp_cross:
    render_cross_city_intro()
    cc_delivery, cc_equity, cc_maturity = st.tabs([
        "Service Delivery", "Service Equity", "Maturity Index",
    ])
    with cc_delivery:
        render_delivery_placeholder()
    with cc_equity:
        render_equity_placeholder()
    with cc_maturity:
        render_maturity_placeholder()
