import json
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from components import theme
from components.area_embedding import render_area_embedding
from components.category_equity_explorer import render_category_equity_explorer
from components.category_explorer import render_category_explorer
from components.cross_city import render_cross_city_intro
from components.city_delivery import render_city_delivery
from components.city_equity import render_city_equity
from components.maturity_index import render_maturity_index
from components.equity_adjusted import render_equity_adjusted
from components.equity_panel import render_equity
from components.operations_panel import render_operations

DATA_DIR = Path(__file__).parent.parent / "data" / "processed"

st.set_page_config(
    page_title="Baltimore 311 Service Equity",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Clean-light polish layer (Inter + card/nav/heading restyle). Static, injected once.
theme.inject_global_css()

try:
    MAPBOX_TOKEN = st.secrets["mapbox"]["token"]
except (KeyError, FileNotFoundError):
    MAPBOX_TOKEN = ""


# ── Cached loaders ────────────────────────────────────────────────────────────
@st.cache_data
def available_years(gk: str) -> list[int]:
    files = sorted(DATA_DIR.glob(f"{gk}_metrics_*.parquet"))
    years = [int(f.stem.split("_")[-1]) for f in files]
    return sorted(years, reverse=True) if years else [2024]


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


# ── Sidebar — dashboard overview ──────────────────────────────────────────────
# st.navigation renders the page links at the top of the sidebar; this overview sits
# below them as reference.
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
        "the same service is delivered. **Compare cities** sets Baltimore against a cohort "
        "of peer cities on the same metrics — Service Delivery, Service Equity, and "
        "Open-Data Maturity are all live."
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
            "**Embedding / PCA** — in the Areas view, each neighborhood's 2D position "
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
# State only here; the toggle widget renders below for the Within-Baltimore pages only
# (geo level is meaningless for the city-level Compare-cities pages).
if "geo_level" not in st.session_state:
    st.session_state["geo_level"] = "CSA"
geo_level = st.session_state["geo_level"]
geo_key = "tract" if geo_level == "Census Tract" else "csa"
featureidkey = "properties.GEOID" if geo_level == "Census Tract" else "properties.csa_name"

# ── Persist the cross-page metric selection ───────────────────────────────────
# Each view is now its own st.navigation page, so only the active page runs. Streamlit
# garbage-collects the state of a widget on runs where its page isn't rendered, which
# would drop the Equity page's `eq_metric` that the Mix-Adjusted page reads. Re-committing
# it here (the entry script runs on every rerun, before any page) keeps it alive. The
# selectbox sets no default=, so the re-commit is warning-free.
if "eq_metric" in st.session_state:
    st.session_state["eq_metric"] = st.session_state["eq_metric"]

years = available_years(geo_key)

# ── Masthead + global year navigation ─────────────────────────────────────────
# A bold full-width editorial masthead band, then the global year selector (cross-city
# data is also city × year, so year is shared by both page groups). Both render on every
# page, above the active page's body.
st.markdown(
    theme.masthead(
        "Baltimore · 311 Service Equity",
        "Does your block change the wait?",
        "A decade of city service data — 2016 to 2025 — read by neighborhood: who calls, "
        "from where, and how fast Baltimore responds.",
    ),
    unsafe_allow_html=True,
)

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

if data_ready:
    df_full = load_metrics(parquet_path)
    geojson = load_geojson(geojson_path)
else:
    df_full, geojson = None, None

demographics = load_demographics(DATA_DIR / f"{geo_key}_demographics.csv")


# ── Pages ─────────────────────────────────────────────────────────────────────
# Thin wrappers that close over the shared state computed above (year, geo, loaded data).
# st.navigation runs only the selected page, so the heavy views (Areas PCA, Service-Equity
# scoring, Mix-Adjusted regression) compute only when you're actually on them.
def page_operations() -> None:
    if not data_ready:
        theme.notice_pending(_NO_DATA_MSG)
        return
    render_operations(
        DATA_DIR, geo_key, year,
        df=df_full, geojson=geojson, geo_id_col="geoid",
        featureidkey=featureidkey, mapbox_token=MAPBOX_TOKEN,
    )


def page_services() -> None:
    if not data_ready:
        theme.notice_pending(_NO_DATA_MSG)
        return
    render_category_explorer(DATA_DIR, year)


def page_areas() -> None:
    render_area_embedding(DATA_DIR, year)


def page_equity() -> None:
    if not data_ready:
        theme.notice_pending(_NO_DATA_MSG)
        return
    render_equity(
        DATA_DIR, geo_key, year,
        df_full=df_full, geojson=geojson, featureidkey=featureidkey,
        mapbox_token=MAPBOX_TOKEN, demographics=demographics,
    )


def page_service_equity() -> None:
    if not data_ready:
        theme.notice_pending(_NO_DATA_MSG)
        return
    render_category_equity_explorer(DATA_DIR, demographics, geo_key, year)


def page_mix_adjusted() -> None:
    if not data_ready:
        theme.notice_pending(_NO_DATA_MSG)
        return
    # Carry over the Equity page's metric selection so the two equity views stay aligned;
    # falls back to days-to-close inside the component when that metric doesn't exist at the
    # service-type grain. The persist above keeps `eq_metric` alive across the page switch.
    render_equity_adjusted(
        DATA_DIR, demographics, geo_key, year,
        geojson=geojson, featureidkey=featureidkey,
        mapbox_token=MAPBOX_TOKEN, eq_metric_label=st.session_state.get("eq_metric"),
    )


def page_city_delivery() -> None:
    render_city_delivery(DATA_DIR, year)


def page_city_equity() -> None:
    render_city_equity(DATA_DIR, year)


def page_maturity() -> None:
    render_maturity_index(DATA_DIR)


# url_paths of the Within-Baltimore pages — used to gate the geo toggle / group intros.
within_pages = [
    st.Page(page_operations, title="Operations", icon="📊",
            url_path="operations", default=True),
    st.Page(page_services, title="Services", icon="🧰", url_path="services"),
    st.Page(page_areas, title="Area Service Usage", icon="🗺️", url_path="areas"),
    st.Page(page_equity, title="Equity", icon="⚖️", url_path="equity"),
    st.Page(page_service_equity, title="Service Equity", icon="🔍",
            url_path="service-equity"),
    st.Page(page_mix_adjusted, title="Mix-Adjusted Equity", icon="🎛️",
            url_path="mix-adjusted"),
]
compare_pages = [
    st.Page(page_city_delivery, title="Service Delivery", icon="🏙️",
            url_path="city-delivery"),
    st.Page(page_city_equity, title="Service Equity", icon="⚖️",
            url_path="city-equity"),
    st.Page(page_maturity, title="Maturity Index", icon="🏅", url_path="maturity"),
]

pg = st.navigation({"Within Baltimore": within_pages, "Compare cities": compare_pages})

# ── Per-group chrome — shown above the active page's body ──────────────────────
# Identity check against the page list (not pg.url_path): Streamlit blanks the default
# page's url_path to "" at the app root, so a string match would misfire on the landing page.
if pg in within_pages:
    # Geographic unit — one global control for the Within-Baltimore pages. Writes the
    # shared `geo_level` state every such page reads; the Areas view is the exception (it
    # shows tracts and CSAs together and ignores this toggle).
    geo_col, _ = st.columns([2, 8])
    with geo_col:
        new_geo = st.radio(
            "Geographic unit",
            ["Census Tract", "CSA"],
            index=0 if geo_level == "Census Tract" else 1,
            horizontal=True,
            help="Applies to every Within-Baltimore view except Area Service Usage.",
        )
        if new_geo != geo_level:
            st.session_state["geo_level"] = new_geo
            st.rerun()
else:
    # Compare-cities group intro + comparability caveats, shown once above each city page.
    render_cross_city_intro()

pg.run()
