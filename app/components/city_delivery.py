"""Cross-City Service Delivery — Tab 7 (Phase 5.2), the MVP pair Baltimore vs. DC.

Compares whole cities on the same 311 *delivery* metrics, always as **rates** (never raw
counts — NYC dwarfs Baltimore), with Baltimore the fixed reference. Reads the precomputed
`peer_city_metrics.parquet` (one row per city × year, built by `scripts/peer_city.py` in
CI); soft-degrades to a "run the workflow" notice until that file exists, and drops any
city for which the selected metric isn't derivable.
"""
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from components import theme

_BALTIMORE_COLOR = theme.BRAND   # reference city — stands out from the muted peers
_PEER_COLOR = theme.PEER         # dark enough that white in-bar labels stay legible

# label → (column, value format, higher_is_better | None for neutral)
_METRICS: dict[str, tuple[str, str, bool | None]] = {
    "Requests per 1,000 residents": ("requests_per_1k", "{:.0f}", None),
    "Total requests": ("total_requests", "{:,.0f}", None),
    "Median days to close": ("median_days_to_close", "{:.1f}", False),
    "Closure rate": ("closure_rate", "{:.0%}", True),
    "On-time rate": ("on_time_rate", "{:.0%}", True),
}
_RATE_COLS = {"closure_rate", "on_time_rate"}

# Data-quality heuristics: open 311 datasets are often contaminated by auto-closed /
# same-timestamp records (referrals, duplicates, invalids closed the instant they open),
# which inflate closure rate and crush median days-to-close toward zero. We don't silently
# drop them (we can't tell gamed from genuinely-fast cross-city), but we flag the cities
# whose numbers look implausible so the comparison is read with appropriate suspicion.
_SUSPICIOUS_SAME_DAY = 0.50     # ≥half of closed requests close the same instant they open
_SUSPICIOUS_MEDIAN_DAYS = 1.0   # a sub-day citywide median is implausible for real delivery
_SUSPICIOUS_CLOSURE = 0.99      # near-total closure usually means auto-close, not performance
_SUSPICIOUS_LOW_CLOSURE = 0.05  # near-zero closure usually means a closed-status mapping gap


def _is_baltimore(city: str) -> bool:
    return str(city).lower().startswith("baltimore")


def _quality_flags(row) -> list[str]:
    """Reasons a city-year's delivery numbers look auto-close-contaminated (empty = clean)."""
    reasons = []
    sd = row.get("pct_same_day_close")
    if sd is not None and pd.notna(sd) and sd >= _SUSPICIOUS_SAME_DAY:
        reasons.append(f"{sd:.0%} of closed requests close the same instant they open (likely auto-close)")
    md = row.get("median_days_to_close")
    if md is not None and pd.notna(md) and md < _SUSPICIOUS_MEDIAN_DAYS:
        reasons.append(f"sub-day median time-to-close ({md:.1f} d)")
    cr = row.get("closure_rate")
    if cr is not None and pd.notna(cr) and cr >= _SUSPICIOUS_CLOSURE:
        reasons.append(f"near-total closure ({cr:.0%})")
    if cr is not None and pd.notna(cr) and cr <= _SUSPICIOUS_LOW_CLOSURE and row.get("total_requests", 0) > 1000:
        reasons.append(f"near-zero closure ({cr:.0%}) — likely a closed-status mapping gap, not real performance")
    return reasons


def _bar(df: pd.DataFrame, col: str, label: str, fmt: str, flagged: set | None = None) -> go.Figure:
    """Horizontal ranked bar, Baltimore highlighted. Value labels sit *inside* wide bars
    and *outside* (black text) when the bar is too narrow to fit the label legibly. City
    names on the y-axis use automargin so they're never cut off. Cities in `flagged` get a
    ⚠ appended so data-quality concerns travel with the bar, not just a footnote."""
    flagged = flagged or set()
    d = df.sort_values(col, ascending=True)  # largest at the top
    colors = [_BALTIMORE_COLOR if _is_baltimore(c) else _PEER_COLOR for c in d["city"]]
    ylabels = [f"{c}  ⚠" if c in flagged else c for c in d["city"]]

    vals = d[col].tolist()
    max_val = max(vals) if vals else 1
    # Bars narrower than 20% of the axis range won't fit a label inside legibly.
    _INSIDE_THRESHOLD = 0.20
    textpositions = ["inside" if (max_val and v / max_val >= _INSIDE_THRESHOLD) else "outside" for v in vals]
    textcolors = ["white" if p == "inside" else "black" for p in textpositions]

    fig = go.Figure(go.Bar(
        x=vals, y=ylabels, orientation="h",
        marker_color=colors,
        text=[fmt.format(v) for v in vals],
        textposition=textpositions, insidetextanchor="end",
        textfont={"color": textcolors, "size": 13},
        hovertemplate="<b>%{y}</b><br>" + label + ": %{text}<extra></extra>",
    ))
    has_outside = any(p == "outside" for p in textpositions)
    fig.update_layout(**theme.base_layout(
        height=max(130, 40 * len(d) + 56),
        bargap=0.25,
        margin={"t": 24, "b": 10, "l": 10, "r": 80 if has_outside else 10},
        xaxis_title=label, yaxis_title=None,
        showlegend=False,
    ))
    fig.update_yaxes(automargin=True, tickfont={"size": 12})
    if col in _RATE_COLS:
        fig.update_xaxes(tickformat=".0%", range=[0, 1])
    elif has_outside:
        # Extend axis so outside labels aren't clipped at the plot edge.
        fig.update_xaxes(rangemode="tozero", range=[0, max_val * 1.35])
    else:
        fig.update_xaxes(rangemode="tozero")
    return fig


def _trend(df_all: pd.DataFrame, cities: list[str], col: str, label: str, fmt: str) -> go.Figure | None:
    """Multi-year line chart for the selected metric, one line per city, Baltimore bold on
    top of the muted peer lines. Returns None if fewer than 2 years of data exist across
    the selected cities (a single point isn't a trend)."""
    d = df_all[df_all["city"].isin(cities)].dropna(subset=[col]).sort_values("year")
    if d["year"].nunique() < 2:
        return None

    fig = go.Figure()
    for city in cities:
        cd = d[d["city"] == city]
        if cd.empty:
            continue
        is_balt = _is_baltimore(city)
        fig.add_trace(go.Scatter(
            x=cd["year"], y=cd[col], mode="lines+markers", name=city,
            line={"color": _BALTIMORE_COLOR if is_balt else _PEER_COLOR,
                  "width": 3 if is_balt else 1.5},
            marker={"size": 7 if is_balt else 5},
            opacity=1.0 if is_balt else 0.55,
            hovertemplate="<b>%{fullData.name}</b><br>%{x}: %{y}<extra></extra>",
        ))
    fig.update_layout(**theme.base_layout(
        height=280,
        margin={"t": 24, "b": 10, "l": 10, "r": 10},
        xaxis_title=None, yaxis_title=label,
        showlegend=True, legend=theme.LEGEND_H,
        hovermode="x unified",
    ))
    fig.update_xaxes(dtick=1, tickformat="d")
    if col in _RATE_COLS:
        fig.update_yaxes(tickformat=".0%")
    return fig


def render_city_delivery(data_dir: Path, year: int) -> None:
    metrics_path = data_dir / "peer_city_metrics.parquet"
    if not metrics_path.exists():
        theme.notice_pending(
            "Cross-city metrics haven't been generated yet. Run the **Cross-city 311 "
            "metrics** GitHub Actions workflow (or `python scripts/peer_city.py --year "
            "<year>`) to produce `peer_city_metrics.parquet`."
        )
        return

    df = pd.read_parquet(metrics_path)
    st.caption(
        "Baltimore against peer cities on the same delivery metrics, compared as **rates**, "
        "Baltimore highlighted as the reference. City-level only — no neighborhood breakdown."
    )

    # Pick the year to show: prefer the global selection, else the most recent year shared
    # by at least two cities (so a comparison always has something to compare).
    shared = df.groupby("year")["city"].nunique()
    shared_years = shared[shared >= 2].index
    use_year = (
        year if year in set(shared_years)
        else (int(shared_years.max()) if len(shared_years) else int(df["year"].max()))
    )
    sub = df[df["year"] == use_year].copy()
    if sub.empty:
        st.caption("No cross-city rows for any year yet.")
        return
    if use_year != year:
        st.caption(f"Showing **{use_year}** — the most recent year shared across the compared cities.")

    # Let the user focus a comparison set once the cohort grows; Baltimore stays the reference.
    cities_present = sorted(sub["city"], key=lambda c: (not _is_baltimore(c), c))
    if len(cities_present) > 2:
        chosen = st.multiselect("Cities", cities_present, default=cities_present, key="cc_delivery_cities")
        if chosen:
            sub = sub[sub["city"].isin(chosen)]

    # Flag cities whose delivery numbers look auto-close-contaminated (see _quality_flags).
    flags = {r["city"]: _quality_flags(r) for _, r in sub.iterrows()}
    flagged = {c for c, rs in flags.items() if rs}

    metric_label = st.radio("Metric", list(_METRICS), horizontal=True, key="cc_delivery_metric")
    col, fmt, higher_better = _METRICS[metric_label]

    # For the median, offer a "clean" version that drops 0-day (auto-close) closures — a more
    # comparable figure for the contaminated cities. Only when the column has been populated.
    if col == "median_days_to_close" and "median_days_to_close_excl_same_day" in sub.columns \
            and sub["median_days_to_close_excl_same_day"].notna().any():
        if st.checkbox("Exclude same-day (0-day) closures — cleaner cross-city comparison",
                       key="cc_excl_sameday"):
            col = "median_days_to_close_excl_same_day"
            metric_label = "Median days to close (excl. same-day)"

    valid = sub.dropna(subset=[col])
    missing = sorted(set(sub["city"]) - set(valid["city"]))
    if valid.empty:
        st.caption(
            f"**{metric_label}** isn't derivable for the cities available in {use_year} "
            "(e.g. no published due-date standard for on-time rate)."
        )
    else:
        st.plotly_chart(_bar(valid, col, metric_label, fmt, flagged=flagged),
                        use_container_width=True,
                        key="cc_delivery_bar", config={"displayModeBar": False})
        if col == "total_requests":
            st.caption("Raw ticket volume — a scale reference and sanity check; **not** "
                       "population-adjusted, so the largest cities dominate. Use requests "
                       "per 1,000 for a fair comparison.")
        elif higher_better is True:
            st.caption("Higher is better.")
        elif higher_better is False:
            st.caption("Lower is better.")
        else:
            st.caption("Request volume normalized by population — higher means more 311 demand, not better or worse.")

        trend_fig = _trend(df, sorted(valid["city"]), col, metric_label, fmt)
        if trend_fig is not None:
            st.plotly_chart(trend_fig, use_container_width=True,
                            key="cc_delivery_trend", config={"displayModeBar": False})
            st.caption(f"{metric_label} by year — Baltimore bold, peers muted.")
    if missing:
        st.caption(f"Not available for: {', '.join(missing)}.")

    if flagged:
        st.warning(
            "⚠ **Some cities' numbers look contaminated by auto-closed requests.** Many open "
            "311 systems close referral / duplicate / invalid records the instant they open, "
            "which inflates closure rate and pushes the median time-to-close toward zero — so "
            "these figures reflect data practices as much as service speed. Flagged cities are "
            "marked ⚠ above; treat their closure rate and median days-to-close as upper bounds, "
            "not delivery performance.",
            icon="⚠️",
        )
        with st.expander("Why each flagged city is flagged"):
            for city in sorted(flagged):
                st.markdown(f"**{city}** — " + "; ".join(flags[city]) + ".")

    with st.expander("Methodology & comparability (read before comparing)"):
        st.markdown("**How each city defines a “closed” request:**")
        for _, r in sub.sort_values("city").iterrows():
            note = r.get("closure_definition") or "—"
            st.markdown(f"**{r['city']}** — {note}")
        st.caption(
            "Closure semantics differ by city, so closure rate and median days-to-close are "
            "directional, not exact. Volumes are compared per 1,000 residents (ACS county "
            "population), never as raw counts.\n\n"
            "**Median days-to-close is a record-level pooled median here** — half of all the "
            "city's requests closed within that many days — computed identically for every "
            "city. For Baltimore this is the *same* canonical figure the Operations tab reports "
            "as its “citizen-initiated” median (one source of truth). It is the only measure "
            "DC can match (no tract join), so it anchors every cross-city comparison. It does "
            "differ from the Operations “all requests received” headline, which is a broader, "
            "differently-scoped figure."
        )

