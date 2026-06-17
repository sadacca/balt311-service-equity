"""Cross-city comparison group intro — the "Compare cities" group (Phase 5).

All three cross-city tabs (Service Delivery, Service Equity, Maturity Index) now have
real components (`city_delivery.py`, `city_equity.py`, `maturity_index.py`); this module
just holds the group-level framing and comparability caveats shared by all three.
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
