"""311 Open-Data Maturity — Tab 9 (Phase 5.8).

Scores each cohort city's 311 *open-data publishing* maturity (not service quality) and,
just as importantly, **credits** the cities whose openness makes this analysis possible —
Baltimore foremost, as a first-mover. A scorecard heatmap + ranking, Baltimore's gap
profile against the cohort leader, and a coverage census naming how few of the largest US
cities can be scored at all. Reads two curated CSVs (`peer_city_maturity.csv`,
`peer_city_coverage_census.csv`); the scores are a provisional canvass (rubric §8 of
cross_city_comparison.md), to be hardened in P5.8-1/2.
"""
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from components import theme

# Rubric dimension column → display label (order = left-to-right on the heatmap).
_DIMS = {
    "availability_license": "Availability<br>& license",
    "granularity": "Granularity",
    "history_depth": "History<br>depth",
    "update_cadence": "Update<br>cadence",
    "api_access": "API<br>access",
    "standardization": "Open311<br>standard",
    "field_completeness": "Field<br>completeness",
    "geocoding_coverage": "Geocoding<br>coverage",
    "documentation": "Documentation",
}
_MAX_PER_DIM = 3
# Compact labels for the sortable full table (the heatmap uses the <br> labels above).
_DIM_SHORT = {
    "availability_license": "Avail/Lic", "granularity": "Granular", "history_depth": "History",
    "update_cadence": "Cadence", "api_access": "API", "standardization": "Open311",
    "field_completeness": "Fields", "geocoding_coverage": "Geocode", "documentation": "Docs",
}
# Explicit 1/2/3 anchors per dimension (0 = absent / data inaccessible). This is the rubric of
# record — shown on the page AND the standard `scripts/score_maturity.py` derives against, so
# the displayed criteria and the numbers always agree.
_RUBRIC: dict[str, tuple[str, str, str]] = {
    "availability_license": ("published, unclear/closed license", "open data, standard terms",
                             "open under an explicit open license (CC0 / PDDL / public domain)"),
    "granularity": ("aggregate / summary only", "record-level but a subset (e.g. app-channel)",
                    "full record-level — one row per request"),
    "history_depth": ("< 3 years, or a rolling window only", "≈ 3–9 years",
                      "≥ 10 years of continuous coverage"),
    "update_cadence": ("annual or irregular / manual", "weekly", "daily or faster"),
    "api_access": ("bulk download only (no API)", "an API, but constrained",
                   "full programmatic API (SODA / ArcGIS / Carto / CKAN)"),
    "standardization": ("non-standard schema", "partial or historical Open311",
                        "current Open311 GeoReport v2 endpoint"),
    "field_completeness": ("missing a core field (no close timestamp, or no geo)",
                           "the core set — created, closed, geo, type, status",
                           "core plus extras — intake channel, agency, reopen / cost"),
    "geocoding_coverage": ("sparse / partial coordinates", "most requests geocoded",
                           "near-complete lat/lon"),
    "documentation": ("minimal or none", "a published data dictionary",
                      "rich field-level docs + metadata"),
}
# Specific practice that would close each dimension's gap (cross-refs requirements.md §5).
_GAP_HINTS = {
    "availability_license": "publish under an explicit open license",
    "granularity": "publish record-level (per-request) data, not aggregates",
    "history_depth": "extend continuous published history",
    "update_cadence": "move from annual layers to a single daily-refreshed feed",
    "api_access": "expose a programmatic API (SODA / ArcGIS / Carto)",
    "standardization": "add an Open311 GeoReport v2 endpoint",
    "field_completeness": "publish the missing fields (reopen, cost)",
    "geocoding_coverage": "geocode the remaining requests (raise valid lat/lon share)",
    "documentation": "publish a fuller data dictionary / field-level metadata",
}
_STATUS = {  # census status code → (emoji, label)
    "scoreable": ("✅", "Scoreable"),
    "partial": ("🟡", "Partial / limited"),
    "unconfirmed": ("❔", "None found / unconfirmed"),
}
_BALTIMORE = "Baltimore, MD"


def _is_baltimore(city: str) -> bool:
    return str(city).startswith("Baltimore")


def _scorecard_heatmap(df: pd.DataFrame, max_total: int) -> go.Figure:
    """Cities × dimensions, colored 0–3 (red→green), each cell labeled with its score.
    Rows ordered best-total at top; Baltimore starred in the y label."""
    z = df[list(_DIMS)].values
    ylabels = [
        f"{'★ ' if _is_baltimore(c) else ''}#{r}  {c}  ({t}/{max_total})"
        for c, r, t in zip(df["city"], df["rank"], df["total"])
    ]
    fig = go.Figure(go.Heatmap(
        z=z, x=list(_DIM_SHORT.values()), y=ylabels,
        text=z, texttemplate="%{text}", textfont={"size": 13},
        colorscale=theme.MATURITY_SCALE, zmin=0, zmax=_MAX_PER_DIM,
        showscale=False,  # the score is printed in every cell — the colorbar is redundant
        xgap=2, ygap=2,
        hovertemplate="%{y}<br>%{x}: %{z}/3<extra></extra>",
    ))
    fig.update_layout(**theme.base_layout(
        height=130 + 34 * len(df),
        margin={"t": 10, "b": 10, "l": 10, "r": 10},
        yaxis={"autorange": "reversed"},  # rank 1 at the top
        # Short labels, angled, with automargin — single-word headers slanted so the nine
        # columns never overlap on a narrow (mobile) viewport.
        xaxis={"side": "top", "tickangle": -45, "tickfont": {"size": 11}, "automargin": True},
    ))
    return fig


def _gap_profile(df: pd.DataFrame) -> list[str]:
    """Dimensions where Baltimore trails the top-ranked (leader) city, with the practice
    that would close each gap."""
    balt = df[df["city"].apply(_is_baltimore)].iloc[0]
    leader = df.iloc[0]
    rows = []
    for col, label in _DIMS.items():
        gap = int(leader[col]) - int(balt[col])
        if gap > 0:
            clean = label.replace("<br>", " ")
            rows.append(f"**{clean}** ({int(balt[col])} -> {int(leader[col])}) — {_GAP_HINTS[col]}")
    return rows


def render_maturity_index(data_dir: Path) -> None:
    path = data_dir / "peer_city_maturity.csv"
    if not path.exists():
        theme.notice_pending("Maturity scorecard not found (`peer_city_maturity.csv`).")
        return

    df = pd.read_csv(path)
    df["total"] = df[list(_DIMS)].sum(axis=1)
    df = df.sort_values("total", ascending=False).reset_index(drop=True)
    df["rank"] = df.index + 1
    max_total = len(_DIMS) * _MAX_PER_DIM

    # Credit first — name the enabling openness before any critical finding.
    st.markdown(
        "**Openness is the precondition for everything else on this dashboard.** This tab "
        "measures how maturely each city *publishes* its 311 data — and credits the cities "
        "whose transparency makes delivery and equity analysis possible at all. When this "
        "dashboard scrutinizes Baltimore, it scrutinizes one of the relatively few American "
        "cities that has *chosen to be scrutinizable*."
    )

    scoreable = (df[df["status"] == "scoreable"].reset_index(drop=True)
                 if "status" in df.columns else df)

    if df["city"].apply(_is_baltimore).any():
        balt = df[df["city"].apply(_is_baltimore)].iloc[0]
        sc_mask = scoreable["city"].apply(_is_baltimore)
        balt_sc_rank = int(scoreable.index[sc_mask][0]) + 1 if sc_mask.any() else int(balt["rank"])
        st.markdown(
            f"**Baltimore ranks #{balt_sc_rank} of {len(scoreable)} scoreable cities** "
            f"({int(balt['total'])}/{max_total}) — a genuine first-mover (first US 311 in 1996, "
            "early Open311 adopter ~2011) that the Socrata leaders now edge out on cadence and "
            "documentation. Both truths, shown honestly."
        )

    # Detailed heatmap — every scoreable city across the nine rubric dimensions.
    st.subheader("Detailed scorecard — every scoreable city")
    # staticPlot: the heatmap is a read-only image — no zoom/drag/select — so a mobile finger
    # swipe scrolls the page past it instead of being captured by the chart. Every value is
    # printed in-cell and the row labels carry rank/total, so no interactivity is lost.
    st.plotly_chart(_scorecard_heatmap(scoreable, max_total), use_container_width=True,
                    key="maturity_heatmap", config={"staticPlot": True, "displayModeBar": False})
    _render_rubric()

    n_inspected = int((~df["derived"]).sum()) if "derived" in df.columns else 0
    st.caption(
        f"**Reading the scores honestly.** {n_inspected} cities — the cohort we built ingestion "
        "adapters for and so scored against their **actual published schema and history** — are "
        "marked *inspected* (Basis = hand in the table below). The other "
        f"{len(df) - n_inspected} are derived from the coverage census and scored "
        "**conservatively** on the four dimensions that need data inspection — field "
        "completeness, geocoding, documentation, Open311 (2 = “present / standard, not "
        "individually verified”). So a derived city's score on those four is a **floor, not a "
        "ceiling**: it would rise with direct inspection (P5.9-4). The rule-based dimensions "
        "(availability, granularity, history, cadence, API) derive identically for every city. "
        "This is why an inspected city like Boston can outrank a census-derived one even when "
        "its underlying data is comparable — the inspected scores simply have more evidence."
    )

    gaps = _gap_profile(df)
    if gaps:
        with st.expander(f"Baltimore's gap profile — {len(gaps)} dimension(s) behind the leader"):
            st.markdown(
                "Where Baltimore trails the top-ranked city, the specific practice that would "
                "close it (maps to `requirements.md` §5):"
            )
            for g in gaps:
                st.markdown(f"- {g}")

    _render_full_table(df, max_total)

    with st.expander("Three standing caveats"):
        st.markdown(
            "1. **It measures publishing maturity, not service quality.** A city can publish "
            "beautifully and still deliver inequitably — only the open cities can even be "
            "*evaluated*. A high score is a precondition for accountability, not a substitute.\n\n"
            "2. **All US cities means US cities with public 311 open data** — a few dozen — "
            "the only defensible denominator. Most municipalities run no 311 system, or publish "
            "nothing.\n\n"
            "3. **Publishing maturely ≠ publishing *trustworthy* data.** A complete, open feed "
            "can still be contaminated or gamed — most often by auto-closing records the instant "
            "they open (which inflates closure rate and crushes median time-to-close; see the ⚠ "
            "flags on the Service Delivery tab). A high publishing score is not a clean bill of "
            "data health.\n\n"
            "4. **`field_completeness` scores schema presence, not fill rate.** It asks whether a "
            "core field (e.g. a close timestamp) exists in the published schema — not whether "
            "that field is reliably populated once it does. Chicago scores a 3 here because its "
            "schema lists `closed_date` alongside the rest of the core set, but in practice that "
            "column is null for nearly all records even among ones marked closed by status — "
            "which is why Tab 8's mix-adjusted equity score can compute Chicago's closure rate "
            "fine but can't compute its median days-to-close at all (see TASKS.md/"
            "`cross_city_comparison.md` for the full finding). A genuine fill-rate signal exists "
            "in the data already fetched (e.g. the NaN-rate on `median_days_to_close`) but isn't "
            "folded into this score yet.\n\n"
            "Scores are a provisional canvass (rubric §8), to be hardened in P5.8."
        )


def _render_rubric() -> None:
    """The explicit 1/2/3 anchors per dimension, so a reader can judge any score against the
    standard (and spot scores worth re-comparing)."""
    with st.expander("What each score means — the rubric (0 = absent / data inaccessible)"):
        rows = [
            {"Dimension": _DIM_SHORT[d], "1": one, "2": two, "3": three}
            for d, (one, two, three) in _RUBRIC.items()
        ]
        st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)


def _render_full_table(df: pd.DataFrame, max_total: int) -> None:
    """Full numerical ranking of all metros — every rubric dimension, sortable, with the
    inaccessible cities scored 0 sitting at the bottom."""
    counts = df["status"].value_counts() if "status" in df.columns else {}
    st.subheader(f"Full numerical ranking — all {len(df)} cities (sortable)")
    st.markdown(
        f"✅ {int(counts.get('scoreable', 0))} scoreable · 🟡 {int(counts.get('partial', 0))} "
        f"partial · ❔ {int(counts.get('unconfirmed', 0))} none/unconfirmed. **Cities whose "
        "record-level 311 is inaccessible score 0 across the rubric** — you cannot credit data "
        "you cannot reach, and naming the cities that *cannot* be evaluated is half the point. "
        "Click any column header to sort."
    )

    disp = df.copy()
    disp["Status"] = disp["status"].map(lambda s: f"{_STATUS.get(s, ('', s))[0]} {_STATUS.get(s, ('', s))[1]}") \
        if "status" in disp.columns else ""
    if "derived" in disp.columns:
        disp["Basis"] = disp["derived"].map({True: "census", False: "hand"})
    disp = disp.rename(columns={"rank": "#", "city": "City", "population": "Population",
                                "evidence": "Evidence", "total": "Total", **_DIM_SHORT})
    # Population sits up front so the table can be sorted by city size — surfacing the biggest
    # cities (which carry the most 311 data) and, just as tellingly, which large cities publish
    # nothing (a big city with a 0 Total).
    order = ["#", "City", "Population", "Status", "Evidence", "Basis", "Total", *_DIM_SHORT.values()]
    order = [c for c in order if c in disp.columns]
    st.dataframe(
        disp[order], hide_index=True, use_container_width=True, height=560,
        column_config={
            "Total": st.column_config.NumberColumn("Total", help=f"out of {max_total}"),
            "Population": st.column_config.NumberColumn(
                "Population", format="localized",
                help="City (Census place) population — click to sort by size. Cohort cities use "
                     "our ACS figure; others use the 2020 Census.",
            ),
        },
    )
