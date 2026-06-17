"""Cross-City Service Equity — Tab 8 (Phase 5.6).

Each cohort city's own internal income-based equity score: does that city deliver the same
311 services more or less equitably to its below- vs. above-median-income tracts? The
**mix-adjusted** score (`adj_income_score` — within-service-type overlap scores, volume-
weighted into one citywide figure) is primary, since it isolates "how the same service is
delivered" from "which services an area requests"; the **raw** pooled score
(`raw_income_score`) is shown as a secondary reference, with the gap between the two
explained — a wide gap means a city's apparent raw disparity is largely a service-mix
effect, not a delivery-equity one (the same raw-vs-adjusted story Tab 6 tells citywide, now
computable for any city in the cohort).

Scored on **two metrics**, selectable via radio, same as the within-Baltimore tabs'
`_SRTYPE_METRICS` (`equity_adjusted.py`): median days to close and closure rate.

Race is out of scope for this phase (see TASKS.md / `cross_city_comparison.md` §6.5 — no
single race-group definition generalizes across the cohort's demographics). Reads the
precomputed `peer_city_equity.parquet` (one row per city × year × metric, built by
`scripts/peer_city_equity_score.py` in CI); soft-degrades to a "run the workflow" notice
until that file exists, and drops any city without a year's row rather than erroring.
"""
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from components.utils import score_label

_BALTIMORE_COLOR = "#C8102E"   # reference city — stands out from the muted peers
_PEER_COLOR = "#5f6368"        # dark enough that white in-bar labels stay legible
_RAW_COLOR = "#a6a6a6"         # lighter still — the secondary/reference series

# Green/amber/red overlap-score threshold bands — same convention and thresholds as
# `score_label()` and the within-Baltimore equity tabs.
_BANDS = [(0.0, 0.4, "red"), (0.4, 0.7, "orange"), (0.7, 1.0, "green")]

# Same two metrics, same labels, as the within-Baltimore `equity_adjusted._SRTYPE_METRICS`.
_METRICS = {
    "Median days to close": "median_days_to_close",
    "Closure rate": "closure_rate",
}


def _is_baltimore(city: str) -> bool:
    return str(city).lower().startswith("baltimore")


def _add_score_bands(fig: go.Figure) -> None:
    for lo, hi, color in _BANDS:
        fig.add_vrect(x0=lo, x1=hi, fillcolor=color, opacity=0.06, line_width=0)


def _score_bar(df: pd.DataFrame, metric_label: str) -> go.Figure:
    """Horizontal ranked bar of `adj_income_score`, Baltimore highlighted, fixed [0,1] axis
    with the green/amber/red threshold bands so a score's standing is visible at a glance."""
    d = df.sort_values("adj_income_score", ascending=True)
    colors = [_BALTIMORE_COLOR if _is_baltimore(c) else _PEER_COLOR for c in d["city"]]

    fig = go.Figure(go.Bar(
        x=d["adj_income_score"], y=d["city"], orientation="h",
        marker_color=colors,
        text=[f"{v:.0%}" for v in d["adj_income_score"]],
        textposition="outside", textfont={"size": 13},
        hovertemplate="<b>%{y}</b><br>Mix-adjusted score: %{x:.0%}<extra></extra>",
    ))
    _add_score_bands(fig)
    fig.update_layout(
        height=max(130, 40 * len(d) + 56),
        bargap=0.25,
        margin={"t": 24, "b": 10, "l": 10, "r": 40},
        xaxis_title=f"Mix-adjusted income equity score · {metric_label.lower()}", yaxis_title=None,
        plot_bgcolor="white", paper_bgcolor="white", showlegend=False,
    )
    fig.update_yaxes(automargin=True, tickfont={"size": 12})
    fig.update_xaxes(range=[0, 1.08], tickformat=".0%")
    return fig


def _raw_vs_adjusted(df: pd.DataFrame, metric_label: str) -> go.Figure:
    """Paired horizontal bars — raw (reference, light) behind adjusted (primary) per city,
    ordered by adjusted score, so the mix-driven gap is visible city by city."""
    d = df.sort_values("adj_income_score", ascending=True)
    colors = [_BALTIMORE_COLOR if _is_baltimore(c) else _PEER_COLOR for c in d["city"]]

    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=d["raw_income_score"], y=d["city"], orientation="h", name="Raw (pooled)",
        marker_color=_RAW_COLOR,
        hovertemplate="<b>%{y}</b><br>Raw score: %{x:.0%}<extra></extra>",
    ))
    fig.add_trace(go.Bar(
        x=d["adj_income_score"], y=d["city"], orientation="h", name="Mix-adjusted",
        marker_color=colors,
        hovertemplate="<b>%{y}</b><br>Mix-adjusted score: %{x:.0%}<extra></extra>",
    ))
    fig.update_layout(
        height=max(130, 40 * len(d) + 80),
        barmode="group", bargap=0.25, bargroupgap=0.1,
        margin={"t": 24, "b": 10, "l": 10, "r": 10},
        xaxis_title=f"Income equity score · {metric_label.lower()}", yaxis_title=None,
        plot_bgcolor="white", paper_bgcolor="white",
        legend={"orientation": "h", "yanchor": "bottom", "y": 1.02},
    )
    fig.update_yaxes(automargin=True, tickfont={"size": 12})
    fig.update_xaxes(range=[0, 1.0], tickformat=".0%")
    return fig


def _trend(df_all: pd.DataFrame, cities: list[str], metric_col: str) -> go.Figure | None:
    """Multi-year line chart of the mix-adjusted score, one line per city, Baltimore bold.
    Returns None if fewer than 2 years of data exist across the selected cities."""
    d = df_all[(df_all["city"].isin(cities)) & (df_all["metric"] == metric_col)]
    d = d.dropna(subset=["adj_income_score"]).sort_values("year")
    if d["year"].nunique() < 2:
        return None

    fig = go.Figure()
    for city in cities:
        cd = d[d["city"] == city]
        if cd.empty:
            continue
        is_balt = _is_baltimore(city)
        fig.add_trace(go.Scatter(
            x=cd["year"], y=cd["adj_income_score"], mode="lines+markers", name=city,
            line={"color": _BALTIMORE_COLOR if is_balt else _PEER_COLOR,
                  "width": 3 if is_balt else 1.5},
            marker={"size": 7 if is_balt else 5},
            opacity=1.0 if is_balt else 0.55,
            hovertemplate="<b>%{fullData.name}</b><br>%{x}: %{y:.0%}<extra></extra>",
        ))
    _add_score_bands_y(fig)
    fig.update_layout(
        height=280,
        margin={"t": 24, "b": 10, "l": 10, "r": 10},
        xaxis_title=None, yaxis_title="Mix-adjusted score",
        plot_bgcolor="white", paper_bgcolor="white",
        showlegend=True, legend={"orientation": "h", "yanchor": "bottom", "y": 1.02},
        hovermode="x unified",
    )
    fig.update_xaxes(dtick=1, tickformat="d")
    fig.update_yaxes(range=[0, 1], tickformat=".0%")
    return fig


def _add_score_bands_y(fig: go.Figure) -> None:
    for lo, hi, color in _BANDS:
        fig.add_hrect(y0=lo, y1=hi, fillcolor=color, opacity=0.06, line_width=0)


def render_city_equity(data_dir: Path, year: int) -> None:
    equity_path = data_dir / "peer_city_equity.parquet"
    if not equity_path.exists():
        st.subheader("Cross-City Service Equity")
        st.info(
            "Cross-city equity scores haven't been generated yet. Run the **Cross-city "
            "equity data** GitHub Actions workflow (or `python scripts/peer_city_equity_score.py`"
            ", after `peer_city.py` has produced the tract×SRType data) to produce "
            "`peer_city_equity.parquet`.",
            icon="🚧",
        )
        return

    df = pd.read_parquet(equity_path)
    st.subheader("Cross-City Service Equity")
    st.caption(
        "Within each city, does it deliver 311 services more or less equitably to its "
        "below- vs. above-median-income neighborhoods? **Income only** — see the "
        "methodology note below for why race is out of scope for this cohort."
    )

    if df.empty:
        st.caption("No cross-city equity rows yet.")
        return

    metric_label = st.radio(
        "Metric", list(_METRICS), horizontal=True, key="cc_equity_metric",
    )
    metric_col = _METRICS[metric_label]
    df = df[df["metric"] == metric_col]
    if df.empty:
        st.caption(f"No cross-city equity rows scored for **{metric_label.lower()}** yet.")
        return

    shared = df.groupby("year")["city"].nunique()
    available_years = shared.index
    use_year = year if year in set(available_years) else int(available_years.max())
    sub = df[df["year"] == use_year].copy()
    if sub.empty:
        st.caption("No cross-city equity rows for any year yet.")
        return
    if use_year != year:
        st.caption(f"Showing **{use_year}** — the most recent year with cross-city equity scores.")

    sub = sub.dropna(subset=["adj_income_score"])
    if sub.empty:
        st.caption(
            f"No city has enough volume/coverage to score a mix-adjusted {metric_label.lower()} "
            f"equity figure for {use_year} yet."
        )
        return

    cities_present = sorted(sub["city"], key=lambda c: (not _is_baltimore(c), c))
    if len(cities_present) > 2:
        chosen = st.multiselect("Cities", cities_present, default=cities_present, key="cc_equity_cities")
        if chosen:
            sub = sub[sub["city"].isin(chosen)]

    st.plotly_chart(_score_bar(sub, metric_label), use_container_width=True,
                    key="cc_equity_bar", config={"displayModeBar": False})
    st.caption(
        f"**Mix-adjusted {metric_label.lower()} equity score** — controlling for what each "
        "city requests, the within-service-type overlap between below- and above-median-"
        "income tracts' delivery, volume-weighted into one figure. 100% = fully interleaved "
        "(no detectable income gap); 0% = complete separation."
    )

    for _, r in sub.sort_values("city").iterrows():
        label, _ = score_label(r["adj_income_score"])
        if label == "needs review" and not pd.isna(r["adj_income_score"]):
            pass  # surfaced via the bar's red band already; avoid redundant per-city callouts

    with st.expander("Raw vs. mix-adjusted — is the gap a delivery issue or a service-mix issue?"):
        has_raw = sub["raw_income_score"].notna().any()
        if has_raw:
            st.plotly_chart(_raw_vs_adjusted(sub.dropna(subset=["raw_income_score"]), metric_label),
                            use_container_width=True,
                            key="cc_equity_raw_vs_adj", config={"displayModeBar": False})
            st.caption(
                "**Raw** is the pooled score across all service types — \"overall, including "
                "which services an area requests.\" A city whose raw score is much lower than "
                "its mix-adjusted score is mostly seeing a **service-mix** effect (poorer "
                "tracts requesting slower-to-resolve service types more often), not necessarily "
                "slower delivery of the *same* service. The same raw-vs-adjusted story Tab 6 "
                "tells within Baltimore, now computable for any city in the cohort."
            )
        else:
            st.caption("No raw (pooled) score available for the selected cities/year.")

        gap_rows = sub.dropna(subset=["raw_gap"])
        if not gap_rows.empty:
            if metric_col == "closure_rate":
                st.markdown("**Below- minus above-median-income pooled closure rate:**")
                for _, r in gap_rows.sort_values("city").iterrows():
                    sign = "higher" if r["raw_gap"] > 0 else "lower"
                    st.markdown(
                        f"- **{r['city']}** — poorer tracts close **{abs(r['raw_gap']):.1%} "
                        f"{sign}** a share of requests than richer tracts."
                    )
            else:
                st.markdown("**Below- minus above-median-income pooled median days to close:**")
                for _, r in gap_rows.sort_values("city").iterrows():
                    sign = "longer" if r["raw_gap"] > 0 else "shorter"
                    st.markdown(
                        f"- **{r['city']}** — poorer tracts wait **{abs(r['raw_gap']):.1f} "
                        f"days {sign}** (median) than richer tracts."
                    )

    trend_fig = _trend(df, sorted(sub["city"]), metric_col)
    if trend_fig is not None:
        st.plotly_chart(trend_fig, use_container_width=True,
                        key="cc_equity_trend", config={"displayModeBar": False})
        st.caption(f"Mix-adjusted {metric_label.lower()} equity score by year — Baltimore bold, peers muted.")

    with st.expander("Methodology & comparability (read before comparing)"):
        st.markdown(
            "**Income only, race deferred.** Race needs a city-appropriate group definition — "
            "Baltimore's majority-Black/majority-White split doesn't generalize to a "
            "plurality-Hispanic city or one with few or no majority tracts — so it's deferred "
            "to a follow-up phase rather than forced onto every city now. Income has no such "
            "problem: each city's tracts are split above/below **that city's own** tract "
            "median income (ACS 5-year), which is self-relative and never empty.\n\n"
            "**Two metrics, selectable** — median days to close and closure rate, the same "
            "two the within-Baltimore tabs offer (the other within-Baltimore metrics, "
            "on-time rate and requests-per-1k, need fields that don't roll up to the "
            "tract×SRType grain the same way).\n\n"
            "**Mix-adjusted vs. raw**, same as Tab 6: the adjusted score scores each service "
            "type's income gap separately (cells with fewer than 5 requests excluded), then "
            "volume-weights those scores together — isolating *how the same service is "
            "delivered* from *which services an area requests*. The raw score is the pooled, "
            "non-stratified version — closer to what a resident actually experiences overall, "
            "but conflated with service mix.\n\n"
            "**Scores are compared across cities; tracts are not.** Each city's income split "
            "and equity score are computed from its own data; this tab never compares one "
            "city's tract directly against another's."
        )
        n_scored = sub.get("n_srtypes_scored")
        n_tracts = sub.get("n_tracts")
        if n_scored is not None and n_tracts is not None:
            st.markdown("**Coverage this year:**")
            for _, r in sub.sort_values("city").iterrows():
                st.markdown(
                    f"- **{r['city']}** — {int(r['n_tracts']) if pd.notna(r['n_tracts']) else 0} "
                    f"tracts, {int(r['n_srtypes_scored']) if pd.notna(r['n_srtypes_scored']) else 0} "
                    "service types scored at the within-category grain."
                )
