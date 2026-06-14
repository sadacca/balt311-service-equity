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
        height=90 + 46 * len(df),
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
            rows.append(f"**{clean}** ({int(balt[col])} → {int(leader[col])}) — {_GAP_HINTS[col]}")
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

    if df["city"].apply(_is_baltimore).any():
        balt = df[df["city"].apply(_is_baltimore)].iloc[0]
        st.markdown(
            f"**Baltimore ranks #{int(balt['rank'])} of {len(df)}** scored cities "
            f"({int(balt['total'])}/{max_total}) — a genuine first-mover (first US 311 in 1996, "
            "early Open311 adopter ~2011) that the Socrata leaders now edge out on cadence and "
            "documentation. Both truths, shown honestly."
        )

    st.plotly_chart(_scorecard_heatmap(df, max_total), use_container_width=True,
                    key="maturity_heatmap", config={"displayModeBar": False})
    cohort = df[df["in_cohort"]]["city"].tolist() if "in_cohort" in df.columns else []
    if cohort:
        st.caption(
            "Cities with 311 data actually ingested into this dashboard: "
            + ", ".join(cohort)
            + ". Others are scored from a portal canvass (reference points), not ingested."
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

    _render_census(data_dir)

    with st.expander("Two standing caveats"):
        st.markdown(
            "1. **It measures publishing maturity, not service quality.** A city can publish "
            "beautifully and still deliver inequitably — only the open cities can even be "
            "*evaluated*. A high score is a precondition for accountability, not a substitute.\n\n"
            "2. **“All US cities” means “US cities with public 311 open data”** — a few dozen — "
            "the only defensible denominator. Most municipalities run no 311 system, or publish "
            "nothing.\n\nScores are a provisional canvass (rubric §8), to be hardened in P5.8."
        )


def _render_census(data_dir: Path) -> None:
    path = data_dir / "peer_city_coverage_census.csv"
    if not path.exists():
        return
    census = pd.read_csv(path)
    counts = census["status"].value_counts()
    n = len(census)
    parts = []
    for code in ("scoreable", "partial", "unconfirmed"):
        emoji, label = _STATUS[code]
        parts.append(f"{emoji} {int(counts.get(code, 0))} {label.lower()}")

    st.markdown("#### Who can even be scored — coverage census")
    st.markdown(
        f"Of the **{n} largest US cities**, only " + ", ".join(parts) + ". A smaller subset "
        "match Baltimore's combination of **record-level data + a decade of history + an open "
        "API**. Several cities far larger than Baltimore simply **cannot be evaluated this "
        "way** — the data isn't open, isn't record-level, or doesn't exist publicly. The ❔ "
        "cities aren't “better,” only less visible."
    )
    with st.expander(f"Full census of the {n} largest US cities"):
        disp = census.copy()
        disp["status"] = disp["status"].map(lambda s: f"{_STATUS.get(s, ('', s))[0]} {_STATUS.get(s, ('', s))[1]}")
        disp = disp.rename(columns={"rank": "Rank", "city": "City", "status": "Status", "note": "Note"})
        st.dataframe(disp, hide_index=True, use_container_width=True)
