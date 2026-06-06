"""Service Category Explorer — Tab 2.

Operational overview across and within Baltimore's 311 service categories: usage,
service rate, and speed — compared among categories and trended within them.
"""
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from components.srtype_shared import (
    CATEGORY_NAMES,
    EXCLUDED_CATEGORIES,
    extract_categories,
    load_srtype_history,
)

# How many highest-volume categories get individual lines in the among-category
# trend charts and a permanent slot in the category selector — keeps both legible
# and lets the selector's primary row fit on one line on mobile; everything else is
# one click away via the selector's expander.
_TOP_CATEGORIES_N = 8

# Reference gridlines for the log-scale usage axis — without explicit labels, a log
# axis is easy to misread (e.g. mistaking a value sitting between the 100K and 1M
# lines for "close to 1M" or higher).
_LOG_TICKVALS = [100, 1_000, 10_000, 100_000, 1_000_000]
_LOG_TICKTEXT = ["100", "1K", "10K", "100K", "1M"]

# How many highest-volume subcategories to plot individually before folding the
# rest into a single "all other types" line — keeps the multi-line charts readable
# for categories (e.g. Solid Waste) that contain dozens of SRTypes.
_TOP_SUBTYPES_N = 10

# Cycled through for the among-category comparison lines — Plotly's default
# qualitative palette gives ten visually distinct colors.
_PALETTE = [
    "#636EFA", "#EF553B", "#00CC96", "#AB63FA", "#FFA15A",
    "#19D3F3", "#FF6692", "#B6E880", "#FF97FF", "#FECB52",
]


def _wmean(df: pd.DataFrame, value_col: str, weight_col: str = "total_requests") -> float:
    """Volume-weighted mean — the convention this dashboard uses everywhere it
    needs to combine a rate metric (closure rate, median days) across SRTypes."""
    sub = df.dropna(subset=[value_col, weight_col])
    sub = sub[sub[weight_col] > 0]
    if sub.empty:
        return float("nan")
    return float((sub[value_col] * sub[weight_col]).sum() / sub[weight_col].sum())


def _category_aggregates(sr_all: pd.DataFrame) -> pd.DataFrame:
    """Roll SRType rows up to department-prefix categories for the selected year.

    Mirrors `extract_categories`'s definition of a "category": a hyphen-prefixed
    SRType with a non-empty, non-excluded prefix — anything else is left out,
    exactly as it's left out of the category selector.
    """
    has_prefix = sr_all["SRType"].apply(
        lambda n: isinstance(n, str) and "-" in n
        and n.split("-")[0].strip()
        and n.split("-")[0].strip() not in EXCLUDED_CATEGORIES
    )
    work = sr_all[has_prefix].copy()
    work["_cat"] = work["SRType"].str.split("-").str[0].str.strip()

    rows = []
    for cat, g in work.groupby("_cat"):
        rows.append({
            "_cat": cat,
            "label": CATEGORY_NAMES.get(cat, cat),
            "total_requests": g["total_requests"].sum(),
            "closure_rate": _wmean(g, "closure_rate"),
            "median_days_to_close": _wmean(g, "median_days_to_close"),
        })
    return pd.DataFrame(rows).sort_values("total_requests", ascending=False).reset_index(drop=True)


def _yearly_aggregate(scope: pd.DataFrame, value_col: str) -> pd.DataFrame:
    """Per-year aggregate across a set of SRType rows: sum for volume, volume-weighted mean for rates."""
    if value_col == "total_requests":
        return (
            scope.groupby("year")["total_requests"].sum()
            .reset_index(name=value_col)
            .sort_values("year")
        )
    rows = [{"year": yr, value_col: _wmean(g, value_col)} for yr, g in scope.groupby("year")]
    return pd.DataFrame(rows).sort_values("year").reset_index(drop=True)


def _multi_category_line_fig(
    history: pd.DataFrame,
    cats: list[str],
    value_col: str,
    value_label: str,
    year: int,
    log_y: bool = False,
    is_pct: bool = False,
) -> go.Figure:
    """One line per category, trended across years — a dotted guide marks the selected year."""
    hover_fmt = "%{y:.1%}" if is_pct else "%{y:,.1f}"
    fig = go.Figure()
    for i, cat in enumerate(cats):
        scope = history[history["SRType"].str.startswith(f"{cat}-")]
        d = _yearly_aggregate(scope, value_col).dropna(subset=[value_col])
        if d.empty:
            continue
        label = CATEGORY_NAMES.get(cat, cat)
        color = _PALETTE[i % len(_PALETTE)]
        fig.add_trace(go.Scatter(
            x=d["year"], y=d[value_col],
            mode="lines+markers", name=cat,
            line=dict(width=1.8, color=color),
            marker=dict(size=5, color=color),
            hovertemplate=f"<b>{cat} — {label}</b><br>%{{x}}: {hover_fmt}<extra></extra>",
        ))
    fig.add_vline(x=year, line_width=1, line_dash="dot", line_color="#999999")
    fig.update_layout(
        height=320,
        margin={"t": 8, "b": 8, "l": 70, "r": 8},
        xaxis=dict(title="Year", dtick=1),
        yaxis=dict(
            title=value_label,
            type="log" if log_y else "linear",
            tickvals=_LOG_TICKVALS if log_y else None,
            ticktext=_LOG_TICKTEXT if log_y else None,
            tickformat=".0%" if is_pct else None,
            gridcolor="#eeeeee",
        ),
        plot_bgcolor="white",
        paper_bgcolor="white",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0, font=dict(size=10)),
    )
    return fig


def _line_fig(d: pd.DataFrame, value_col: str, value_label: str, year: int, is_pct: bool = False) -> go.Figure:
    """Single-line year-over-year chart with the selected year picked out in red."""
    valid = d.dropna(subset=[value_col])
    hover_fmt = "%{y:.1%}" if is_pct else "%{y:,.1f}"
    fig = go.Figure(go.Scatter(
        x=valid["year"],
        y=valid[value_col],
        mode="lines+markers",
        line=dict(color="#1F4E8C", width=2),
        marker=dict(
            size=[11 if y == year else 7 for y in valid["year"]],
            color=["#d73027" if y == year else "#1F4E8C" for y in valid["year"]],
        ),
        hovertemplate=f"%{{x}}: {hover_fmt}<extra></extra>",
    ))
    fig.update_layout(
        height=240,
        margin={"t": 8, "b": 8, "l": 60, "r": 8},
        xaxis=dict(title="Year", dtick=1),
        yaxis=dict(title=value_label, tickformat=".0%" if is_pct else None, gridcolor="#eeeeee"),
        plot_bgcolor="white",
        paper_bgcolor="white",
    )
    return fig


def _short_label(srtype: str) -> str:
    """Drop the redundant category prefix from a legend label (e.g. 'SW-Dirty Alley' -> 'Dirty Alley')."""
    return srtype.split("-", 1)[1].strip() if "-" in srtype else srtype


def _subtype_multiline_fig(
    scope: pd.DataFrame,
    top_types: list[str],
    other_label: str,
    value_col: str,
    value_label: str,
    is_pct: bool = False,
) -> go.Figure:
    """One line per subcategory (SRType) across years, plus a volume-weighted "all other types" line."""
    hover_fmt = "%{y:.1%}" if is_pct else "%{y:,.1f}"
    fig = go.Figure()
    for srtype in top_types:
        g = scope[scope["SRType"] == srtype].sort_values("year").dropna(subset=[value_col])
        if g.empty:
            continue
        fig.add_trace(go.Scatter(
            x=g["year"], y=g[value_col],
            mode="lines+markers", name=_short_label(srtype),
            line=dict(width=1.8), marker=dict(size=5),
            hovertemplate=f"<b>{srtype}</b><br>%{{x}}: {hover_fmt}<extra></extra>",
        ))

    rest = scope[~scope["SRType"].isin(top_types)]
    if not rest.empty:
        other = _yearly_aggregate(rest, value_col).dropna(subset=[value_col])
        if not other.empty:
            fig.add_trace(go.Scatter(
                x=other["year"], y=other[value_col],
                mode="lines+markers", name=other_label,
                line=dict(width=2, dash="dot", color="#999999"),
                marker=dict(size=5, color="#999999"),
                hovertemplate=f"<b>{other_label}</b><br>%{{x}}: {hover_fmt}<extra></extra>",
            ))

    fig.update_layout(
        height=340,
        margin={"t": 8, "b": 8, "l": 60, "r": 8},
        xaxis=dict(title="Year", dtick=1),
        yaxis=dict(title=value_label, tickformat=".0%" if is_pct else None, gridcolor="#eeeeee"),
        plot_bgcolor="white",
        paper_bgcolor="white",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0, font=dict(size=10)),
    )
    return fig


def _category_selector(agg: pd.DataFrame, key: str) -> str | None:
    """Two-tier category picker.

    The highest-volume categories (sorted alphabetically, so they read as a scannable
    grid rather than a volume ranking) sit in an always-visible row sized to fit on
    one line on mobile, labeled by their acronym with a small legend underneath —
    these are the categories a returning user will recognize and want to jump to
    quickly. Lower-volume categories are tucked behind an expander and labeled by
    their full department name instead — a user opening that drawer is browsing,
    not recalling an acronym, so the name carries more information than the code
    and no separate legend is needed. Selecting in one tier clears the other so
    there's always at most one active category.
    """
    ranked = agg["_cat"].tolist()
    top_cats = sorted(ranked[:_TOP_CATEGORIES_N])
    rest_cats = sorted(ranked[_TOP_CATEGORIES_N:])
    top_key, more_key = f"{key}_top", f"{key}_more"

    top_sel = st.pills(
        "Category", top_cats, key=top_key,
        on_change=lambda: st.session_state.update({more_key: None}),
    )
    top_known = {c: CATEGORY_NAMES[c] for c in top_cats if c in CATEGORY_NAMES}
    if top_known:
        st.caption("  ·  ".join(f"**{k}** {v}" for k, v in sorted(top_known.items())))

    more_sel = None
    if rest_cats:
        with st.expander(f"+ {len(rest_cats)} lower-volume categories"):
            more_sel = st.pills(
                "More categories", rest_cats,
                format_func=lambda c: CATEGORY_NAMES.get(c, c),
                key=more_key,
                on_change=lambda: st.session_state.update({top_key: None}),
            )

    return top_sel or more_sel


def render_category_explorer(data_dir: Path, year: int) -> None:
    st.caption(
        "An operational overview of Baltimore's 311 service categories — usage, "
        "service rate, and speed — compared among categories and trended within them."
    )

    srtype_path = data_dir / f"srtype_metrics_{year}.parquet"
    if not srtype_path.exists():
        st.caption(
            "SRType performance data unavailable for this year — run "
            "`pipeline.py --stage srtype --year <year>` to generate it."
        )
        return
    sr_all = pd.read_parquet(srtype_path)
    history = load_srtype_history(data_dir)
    if history.empty:
        st.caption("No historical SRType data found.")
        return

    agg = _category_aggregates(sr_all)
    if agg.empty:
        st.caption("No categorized SRType data found for this year.")
        return
    top_cats = agg["_cat"].head(_TOP_CATEGORIES_N).tolist()

    # ── Among-category comparison, trended across years ───────────────────────
    st.subheader("How categories compare over time")
    st.caption(
        f"Year-over-year trend for the **{len(top_cats)}** highest-volume categories "
        f"(ranked by **{year}** volume) — read down the three panels to see whether a "
        "high-volume category also tends to run slower or faster than its peers. "
        f"Dotted vertical guide marks **{year}**."
    )
    st.caption("**Usage** — total requests per year (log scale: usage spans several orders of magnitude across categories)")
    st.plotly_chart(
        _multi_category_line_fig(history, top_cats, "total_requests", "Requests", year, log_y=True),
        use_container_width=True, key="cat_explorer_trend_vol", config={"displayModeBar": False},
    )
    st.caption("**Service rate** — closure rate per year")
    st.plotly_chart(
        _multi_category_line_fig(history, top_cats, "closure_rate", "Closure rate", year, is_pct=True),
        use_container_width=True, key="cat_explorer_trend_closure", config={"displayModeBar": False},
    )
    st.caption("**Speed** — median days to close per year")
    st.plotly_chart(
        _multi_category_line_fig(history, top_cats, "median_days_to_close", "Median days to close", year),
        use_container_width=True, key="cat_explorer_trend_days", config={"displayModeBar": False},
    )

    # ── Category selection ────────────────────────────────────────────────────
    st.divider()
    st.subheader("Explore one category over time")
    categories = extract_categories(sr_all)
    selected_cat = _category_selector(agg, key="cat_explorer_cat") if categories else None

    if not selected_cat:
        st.caption(
            "Select a category above to see its multi-year trend and a "
            "year-over-year breakdown by subcategory."
        )
        return

    scope = history[history["SRType"].str.startswith(f"{selected_cat}-")].copy()
    if scope.empty:
        st.caption(f"No historical data found for **{selected_cat}**.")
        return

    cat_label = CATEGORY_NAMES.get(selected_cat, selected_cat)
    display_name = f"{cat_label} ({selected_cat})" if cat_label != selected_cat else selected_cat

    # ── Category-level year-over-year composite ───────────────────────────────
    st.markdown(f"**{display_name}** — category average, year over year · **{year}** highlighted")
    vol_yoy = _yearly_aggregate(scope, "total_requests")
    days_yoy = _yearly_aggregate(scope, "median_days_to_close")
    col_v, col_d = st.columns(2)
    with col_v:
        st.caption("Total requests")
        st.plotly_chart(_line_fig(vol_yoy, "total_requests", "Requests", year),
                        use_container_width=True, key="cat_explorer_cat_vol",
                        config={"displayModeBar": False})
    with col_d:
        st.caption("Median days to close")
        st.plotly_chart(_line_fig(days_yoy, "median_days_to_close", "Days", year),
                        use_container_width=True, key="cat_explorer_cat_days",
                        config={"displayModeBar": False})

    # ── Within-category subcategory breakdown ─────────────────────────────────
    st.divider()
    st.subheader(f"{display_name} — by subcategory")

    current = scope[scope["year"] == year].sort_values("total_requests", ascending=False)
    n_types = scope["SRType"].nunique()
    top_types = current["SRType"].head(_TOP_SUBTYPES_N).tolist()
    n_other = n_types - len(top_types)
    other_label = f"All other {selected_cat} types ({n_other})"

    if n_other > 0:
        st.caption(
            f"{selected_cat} contains {n_types} request types. Showing the "
            f"{len(top_types)} highest-volume types individually (ranked by {year} volume); "
            f"the remaining {n_other} are combined into **{other_label}** "
            "(volume summed, rates volume-weighted) so the chart stays readable."
        )
    else:
        st.caption(f"{selected_cat} contains {n_types} request type{'s' if n_types != 1 else ''}.")

    st.markdown("**Requests, year over year**")
    st.plotly_chart(
        _subtype_multiline_fig(scope, top_types, other_label, "total_requests", "Requests"),
        use_container_width=True, key="cat_explorer_sub_vol", config={"displayModeBar": False},
    )
    st.markdown("**Closure rate, year over year**")
    st.plotly_chart(
        _subtype_multiline_fig(scope, top_types, other_label, "closure_rate", "Closure rate", is_pct=True),
        use_container_width=True, key="cat_explorer_sub_closure", config={"displayModeBar": False},
    )
    st.markdown("**Median days to close, year over year**")
    st.plotly_chart(
        _subtype_multiline_fig(scope, top_types, other_label, "median_days_to_close", "Median days to close"),
        use_container_width=True, key="cat_explorer_sub_days", config={"displayModeBar": False},
    )
