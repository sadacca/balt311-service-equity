"""Cross-city comparison scaffold — the "Compare cities" group (Phase 5).

These render functions are intentionally placeholders: the navigation shell ships now,
with the two-group structure (Within Baltimore / Compare cities) made explicit, but the
cross-city data pipeline and charts are the Phase 5 build. Each placeholder states what
the view will show so the structure reads as deliberate, not unfinished, and points at
`cross_city_comparison.md` for the full plan.

When Phase 5 lands, these bodies fill in — the wiring in `app.py` and the caveat framing
do not need to change. Cross-city views are city-level only (no tracts/CSAs), so they do
*not* read the within-Baltimore `geo_level` state.
"""
import streamlit as st

_CAVEATS = (
    "- **Closure semantics differ by city** — what counts as \"closed\" isn't uniform, "
    "so closure rate and time-to-close are directional, not exact.\n"
    "- **Channel scope differs** — some cities publish app-only requests, others the "
    "full system; request volumes aren't strictly comparable.\n"
    "- **On-time rate isn't always derivable** — not every city publishes a due-date "
    "standard, so that metric is shown only where it exists.\n"
    "- **City-level only** — these views compare whole cities; there is no tract or "
    "neighborhood breakdown here (that lives in the Within-Baltimore group)."
)


def render_cross_city_intro() -> None:
    """Group-level framing + the comparability caveats that apply to every cross-city view."""
    st.caption(
        "How does Baltimore compare to peer and leading cities on the same 311 metrics? "
        "This group sets Baltimore against other cities at the **city level** — a "
        "different kind of question from the within-Baltimore story, on different data."
    )
    with st.expander("Before you compare — how these numbers differ from Baltimore's"):
        st.markdown(_CAVEATS)


def _placeholder(title: str, body: str) -> None:
    st.subheader(title)
    st.info(body, icon="🚧")
    st.caption("Planned in **Phase 5** — see `cross_city_comparison.md` for the full design.")


def render_delivery_placeholder() -> None:
    _placeholder(
        "Cross-City Service Delivery",
        "Delivery metrics — requests per 1,000 residents, median days to close, closure "
        "rate, on-time rate — for Baltimore against peer and leading cities, Baltimore "
        "highlighted as the reference. City-level aggregation, no neighborhood breakdown.",
    )


def render_equity_placeholder() -> None:
    _placeholder(
        "Cross-City Service Equity",
        "Each city's own internal race- and income-based equity scores — the "
        "**mix-adjusted overall score** (the Tab 6 \"adjusted\" measure, the portable "
        "one) as the primary comparison, with the raw citywide score for reference. "
        "Answers whether Baltimore delivers the same services more or less equitably "
        "than its peers.",
    )


def render_maturity_placeholder() -> None:
    _placeholder(
        "311 Open-Data Maturity Index",
        "How Baltimore's 311 *publishing* maturity ranks among the few US cities that "
        "publish 311 open data at all — availability, granularity, history depth, update "
        "cadence, API access, Open311 compliance, field completeness, geocoding. Credit "
        "first (Baltimore is why this whole analysis is even possible), critique second.",
    )
