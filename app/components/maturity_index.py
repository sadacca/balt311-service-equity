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
        z=z, x=list(_DIMS.values()), y=ylabels,
        text=z, texttemplate="%{text}", textfont={"size": 13},
        colorscale="RdYlGn", zmin=0, zmax=_MAX_PER_DIM,
        showscale=True, colorbar={"title": "score", "tickvals": [0, 1, 2, 3]},
        xgap=2, ygap=2,
        hovertemplate="%{y}<br>%{x}: %{z}/3<extra></extra>",
    ))
    fig.update_layout(
        height=110 + 34 * len(df),
        margin={"t": 10, "b": 10, "l": 10, "r": 10},
        yaxis={"autorange": "reversed"},  # rank 1 at the top
        xaxis={"side": "top", "tickfont": {"size": 12}},
        plot_bgcolor="white", paper_bgcolor="white",
    )
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
    st.subheader("311 Open-Data Maturity")
    path = data_dir / "peer_city_maturity.csv"
    if not path.exists():
        st.info("Maturity scorecard not found (`peer_city_maturity.csv`).", icon="🚧")
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
    st.markdown("#### Detailed scorecard — every scoreable city")
    st.plotly_chart(_scorecard_heatmap(scoreable, max_total), use_container_width=True,
                    key="maturity_heatmap", config={"displayModeBar": False})
    cohort = df[df["in_cohort"]]["city"].tolist() if "in_cohort" in df.columns else []
    if cohort:
        st.caption(
            "**6 cities are hand-scored** (Baltimore, DC, Philadelphia, NYC, Chicago, SF); the "
            "rest are scored from the verified coverage census (status · evidence · published "
            "history). Cities with 311 data actually ingested into this dashboard: "
            + ", ".join(cohort) + "."
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
            "data health.\n\nScores are a provisional canvass (rubric §8), to be hardened in P5.8."
        )


def _render_full_table(df: pd.DataFrame, max_total: int) -> None:
    """Full numerical ranking of all metros — every rubric dimension, sortable, with the
    inaccessible cities scored 0 sitting at the bottom."""
    counts = df["status"].value_counts() if "status" in df.columns else {}
    st.markdown("#### Full numerical ranking — all 45 metros (sortable)")
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
    disp = disp.rename(columns={"rank": "#", "city": "City", "evidence": "Evidence",
                                "total": "Total", **_DIM_SHORT})
    order = ["#", "City", "Status", "Evidence", "Basis", "Total", *_DIM_SHORT.values()]
    order = [c for c in order if c in disp.columns]
    st.dataframe(
        disp[order], hide_index=True, use_container_width=True, height=560,
        column_config={"Total": st.column_config.NumberColumn("Total", help=f"out of {max_total}")},
    )
