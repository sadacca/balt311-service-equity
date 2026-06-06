"""Service Category Explorer — Tab 2.

Pure operational comparison among and within service categories: usage,
service rate, and speed — trended across years. Deliberately contains
**no** race/income framing — that lens lives in the Service Category Equity
Explorer (Tab 5). A department manager should be able to answer "how is my
service type doing, and how fast" here without wading through demographic
content that isn't theirs to interpret.
"""
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from components.srtype_shared import (
    CATEGORY_NAMES,
    EXCLUDED_CATEGORIES,
    category_pills,
    extract_categories,
    load_srtype_history,
)

# How many highest-volume subcategories to plot individually before folding the
# rest into a single "all other types" line — keeps the multi-line charts readable
# for categories (e.g. Solid Waste) that contain dozens of SRTypes.
_TOP_SUBTYPES_N = 10


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
    exactly as it's left out of the category pills.
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


def _ranked_bar_fig(agg: pd.DataFrame, value_col: str, value_label: str, is_pct: bool = False) -> go.Figure:
    """Horizontal bar ranking, one bar per category — highest value at top."""
    d = agg.dropna(subset=[value_col]).sort_values(value_col, ascending=True)
    hover_fmt = "%{x:.1%}" if is_pct else "%{x:,.1f}"
    fig = go.Figure(go.Bar(
        x=d[value_col],
        y=d["_cat"],
        orientation="h",
        marker_color="#1F4E8C",
        customdata=d["label"],
        hovertemplate=f"<b>%{{customdata}}</b> (%{{y}}): {hover_fmt}<extra></extra>",
    ))
    fig.update_layout(
        height=max(220, 26 * len(d) + 50),
        margin={"t": 4, "b": 30, "l": 60, "r": 16},
        xaxis=dict(title=value_label, tickformat=".0%" if is_pct else None, gridcolor="#eeeeee"),
        yaxis=dict(title=None),
        plot_bgcolor="white",
        paper_bgcolor="white",
    )
    return fig


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


def render_category_explorer(data_dir: Path, year: int) -> None:
    st.caption(
        "A pure operational view — usage, service rate, and speed, compared among and "
        "within service categories, with **no race or income framing**. Looking for the "
        "equity angle on these same categories? See **Service Category Equity Explorer**."
    )

    srtype_path = data_dir / f"srtype_metrics_{year}.parquet"
    if not srtype_path.exists():
        st.caption(
            "SRType performance data unavailable for this year — run "
            "`pipeline.py --stage srtype --year <year>` to generate it."
        )
        return
    sr_all = pd.read_parquet(srtype_path)

    # ── Among-category comparison ─────────────────────────────────────────────
    st.subheader("How categories compare to each other")
    st.caption(
        f"Citywide, {year} — each panel ranks departments on one operational dimension. "
        "Read across all three to see, for example, whether a high-volume category also "
        "tends to run slow (e.g. \"rodent control runs 3× longer than streetlight repair\")."
    )
    agg = _category_aggregates(sr_all)
    if not agg.empty:
        col_vol, col_close, col_days = st.columns(3)
        with col_vol:
            st.caption("**Usage** — total requests")
            st.plotly_chart(_ranked_bar_fig(agg, "total_requests", "Total requests"),
                            use_container_width=True, key="cat_explorer_rank_vol",
                            config={"displayModeBar": False})
        with col_close:
            st.caption("**Service rate** — closure rate")
            st.plotly_chart(_ranked_bar_fig(agg, "closure_rate", "Closure rate", is_pct=True),
                            use_container_width=True, key="cat_explorer_rank_closure",
                            config={"displayModeBar": False})
        with col_days:
            st.caption("**Speed** — median days to close")
            st.plotly_chart(_ranked_bar_fig(agg, "median_days_to_close", "Median days to close"),
                            use_container_width=True, key="cat_explorer_rank_days",
                            config={"displayModeBar": False})

    # ── Category selection ────────────────────────────────────────────────────
    st.divider()
    st.subheader("Explore one category over time")
    categories = extract_categories(sr_all)
    selected_cat = category_pills(categories, key="cat_explorer_cat") if categories else None

    if not selected_cat:
        st.caption(
            "Select a category above to see its multi-year trend and a "
            "year-over-year breakdown by subcategory."
        )
        return

    history = load_srtype_history(data_dir)
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
