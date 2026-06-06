"""Service Category Explorer — Tab 2.

Pure operational comparison among and within service categories: usage volume,
closure rate, time to close, and on-time performance, trended across years.
Deliberately contains **no** race/income framing — that lens lives in the
Service Category Equity Explorer (Tab 5). A department manager should be able
to answer "how is my service type doing, where, and how fast" here without
wading through demographic content that isn't theirs to interpret.
"""
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from components.map_view import build_choropleth
from components.srtype_shared import (
    CATEGORY_NAMES,
    EXCLUDED_CATEGORIES,
    MIN_GEO_SRTYPE_N,
    category_pills,
    extract_categories,
    load_geo_srtype_metrics,
    load_srtype_history,
)

_CHART_LAYOUT = dict(
    height=260,
    margin={"t": 8, "b": 8, "l": 60, "r": 8},
    xaxis=dict(title="Year", dtick=1),
    plot_bgcolor="white",
    paper_bgcolor="white",
)


def _category_aggregates(sr_all: pd.DataFrame) -> pd.DataFrame:
    """Roll SRType rows up to department-prefix categories.

    total_requests is summed; median_days_to_close is a volume-weighted mean —
    the same convention `_build_timeseries` uses to combine SRTypes citywide.
    """
    # Mirrors `extract_categories`'s definition of a "category": a hyphen-prefixed
    # SRType name with a non-empty, non-excluded prefix. Anything else (e.g. names
    # without a department prefix) is left out of this rollup, exactly as it's left
    # out of the category pills.
    has_prefix = sr_all["SRType"].apply(
        lambda n: isinstance(n, str) and "-" in n
        and n.split("-")[0].strip()
        and n.split("-")[0].strip() not in EXCLUDED_CATEGORIES
    )
    work = sr_all[has_prefix].copy()
    work["_cat"] = work["SRType"].str.split("-").str[0].str.strip()

    out = work.groupby("_cat")["total_requests"].sum().reset_index(name="total_requests")

    days = work.dropna(subset=["median_days_to_close", "total_requests"]).copy()
    if not days.empty:
        days["_wtd"] = days["median_days_to_close"] * days["total_requests"]
        wmean = (
            (days.groupby("_cat")["_wtd"].sum() / days.groupby("_cat")["total_requests"].sum())
            .reset_index(name="median_days_to_close")
        )
        out = out.merge(wmean, on="_cat", how="left")
    else:
        out["median_days_to_close"] = float("nan")

    out["label"] = out["_cat"].map(lambda c: CATEGORY_NAMES.get(c, c))
    return out.sort_values("total_requests", ascending=False).reset_index(drop=True)


def _among_category_fig(agg: pd.DataFrame) -> go.Figure:
    """Bubble chart: one point per category — x = volume, y = typical time to close, size = volume.

    Puts categories side by side on the two axes the narrative most often invokes
    ("rodent control runs N× longer than streetlight repair") without any demographic split.
    """
    sizes = agg["total_requests"].fillna(0)
    max_size = max(float(sizes.max()), 1.0) if not sizes.empty else 1.0
    fig = go.Figure(go.Scatter(
        x=agg["total_requests"],
        y=agg["median_days_to_close"],
        mode="markers+text",
        text=agg["_cat"],
        textposition="top center",
        marker=dict(
            size=sizes,
            sizemode="area",
            sizeref=2.0 * max_size / (42.0 ** 2),
            sizemin=6,
            color="#1F4E8C",
            opacity=0.65,
            line=dict(width=1, color="white"),
        ),
        customdata=agg["label"],
        hovertemplate=(
            "<b>%{customdata}</b> (%{text})<br>"
            "Requests: %{x:,.0f}<br>"
            "Median days to close: %{y:.1f}<extra></extra>"
        ),
    ))
    fig.update_layout(
        height=380,
        margin={"t": 8, "b": 45, "l": 60, "r": 20},
        xaxis=dict(title="Total requests (volume)", gridcolor="#eeeeee"),
        yaxis=dict(title="Median days to close (speed)", gridcolor="#eeeeee"),
        plot_bgcolor="white",
        paper_bgcolor="white",
    )
    return fig


def _table_and_selection(data_dir: Path, year: int) -> tuple[pd.DataFrame | None, str | None, str | None]:
    """Citywide SRType performance table for the selected year, with category pills.

    Returns (sr_all, selected_type, selected_cat) — sr_all is None if no data exists.
    """
    srtype_path = data_dir / f"srtype_metrics_{year}.parquet"
    if not srtype_path.exists():
        st.caption(
            "SRType performance data unavailable for this year — run "
            "`pipeline.py --stage srtype --year <year>` to generate it."
        )
        return None, None, None

    sr_all = (
        pd.read_parquet(srtype_path)
        .sort_values("total_requests", ascending=False)
        .reset_index(drop=True)
    )
    pct_col = "pct_resident_initiated" if "pct_resident_initiated" in sr_all.columns else None

    categories = extract_categories(sr_all)
    selected_cat = category_pills(categories, key="cat_explorer_cat") if categories else None
    sr = (
        sr_all[sr_all["SRType"].str.startswith(f"{selected_cat}-")]
        if selected_cat
        else sr_all
    ).reset_index(drop=True)

    scope_label = f"**{selected_cat}** types" if selected_cat else "all types"
    st.markdown(
        f"**Performance by type** ({scope_label}, {year}) — "
        "click a column header to sort, click a row to drill into its trend and geography"
    )
    display_cols = ["SRType", "total_requests", "closure_rate", "median_days_to_close", "on_time_rate"]
    if pct_col:
        display_cols.append(pct_col)
    fmt = {
        "total_requests": "{:,.0f}",
        "closure_rate": "{:.1%}",
        "median_days_to_close": "{:.1f}",
        "on_time_rate": "{:.1%}",
    }
    if pct_col:
        fmt[pct_col] = "{:.0%}"
    rename = {
        "SRType": "Type", "total_requests": "Requests",
        "closure_rate": "Closure rate", "median_days_to_close": "Median days",
        "on_time_rate": "On-time rate", "pct_resident_initiated": "% Resident-initiated",
    }
    display = sr[display_cols].rename(columns=rename)
    event = st.dataframe(
        display.style.format({rename.get(k, k): v for k, v in fmt.items()}, na_rep="—"),
        use_container_width=True,
        hide_index=True,
        height=min(420, max(150, 35 * len(sr) + 38)),
        on_select="rerun",
        selection_mode="single-row",
        key="cat_explorer_table",
    )

    selected_rows = event.selection.rows
    selected_type = sr.iloc[selected_rows[0]]["SRType"] if selected_rows else None
    return sr_all, selected_type, selected_cat


def _within_type_trend(history: pd.DataFrame, selected_type: str, year: int) -> None:
    """Year-over-year volume + median-days bars for one SRType — selected year highlighted in red."""
    type_hist = history[history["SRType"] == selected_type].sort_values("year")
    if type_hist.empty:
        st.caption(f"No historical data found for **{selected_type}**.")
        return

    days_hist = type_hist.dropna(subset=["median_days_to_close"])
    bar_colors_vol = ["#d73027" if y == year else "#1F4E8C" for y in type_hist["year"]]
    bar_colors_days = ["#d73027" if y == year else "#1F4E8C" for y in days_hist["year"]]

    st.markdown(f"**{selected_type}** — year over year · selected year in red")
    col_vol, col_days = st.columns(2)
    with col_vol:
        st.caption("Total requests")
        fig_vol = go.Figure(go.Bar(
            x=type_hist["year"],
            y=type_hist["total_requests"],
            marker_color=bar_colors_vol,
            hovertemplate="%{x}: %{y:,}<extra></extra>",
        ))
        fig_vol.update_layout(**_CHART_LAYOUT, yaxis=dict(title="Requests", gridcolor="#eeeeee"))
        st.plotly_chart(fig_vol, use_container_width=True, key="cat_explorer_vol",
                        config={"displayModeBar": False})

    with col_days:
        st.caption("Median days to close")
        fig_days = go.Figure(go.Bar(
            x=days_hist["year"],
            y=days_hist["median_days_to_close"],
            marker_color=bar_colors_days,
            hovertemplate="%{x}: %{y:.1f} days<extra></extra>",
        ))
        fig_days.update_layout(**_CHART_LAYOUT, yaxis=dict(title="Days", gridcolor="#eeeeee"))
        st.plotly_chart(fig_days, use_container_width=True, key="cat_explorer_days",
                        config={"displayModeBar": False})


def _geo_breakdown(
    data_dir: Path,
    geo_key: str,
    year: int,
    df: pd.DataFrame,
    geojson: dict,
    geo_id_col: str,
    featureidkey: str,
    mapbox_token: str,
    selected_type: str,
) -> None:
    """Plain (non-demographic) choropleth of one SRType's volume across geography."""
    geo_srtype = load_geo_srtype_metrics(data_dir / f"{geo_key}_srtype_metrics_{year}.parquet")
    if geo_srtype.empty:
        st.caption(
            "Geo × SRType data unavailable for this year — run "
            "`pipeline.py --stage srtype --year <year>` to generate it."
        )
        return

    totals = geo_srtype[geo_srtype["total_requests"] >= MIN_GEO_SRTYPE_N]
    type_totals = totals[totals["SRType"] == selected_type][["geoid", "total_requests"]]
    map_df = df[["geoid"]].merge(type_totals, on="geoid", how="left")
    map_df["total_requests"] = map_df["total_requests"].fillna(0).astype(int)

    st.caption(
        f"**{selected_type}** request volume by geography "
        f"(cells with fewer than {MIN_GEO_SRTYPE_N} requests suppressed — shown as-is, no demographic lens)"
    )
    fig_map = build_choropleth(
        df=map_df,
        geojson=geojson,
        geo_id_col=geo_id_col,
        featureidkey=featureidkey,
        metric_col="total_requests",
        metric_label="Total requests",
        mapbox_token=mapbox_token,
        sequential=True,
    )
    st.plotly_chart(fig_map, use_container_width=True, key="cat_explorer_map")


def render_category_explorer(
    data_dir: Path,
    geo_key: str,
    year: int,
    df: pd.DataFrame,
    geojson: dict,
    geo_id_col: str,
    featureidkey: str,
    mapbox_token: str,
) -> None:
    st.caption(
        "A pure operational view — usage rates, time to close, and trends among and within "
        "service categories, with **no race or income framing**. Looking for the equity angle "
        "on these same categories? See **Service Category Equity Explorer**."
    )

    sr_all, selected_type, selected_cat = _table_and_selection(data_dir, year)
    if sr_all is None:
        return

    st.divider()
    st.subheader("How categories compare to each other")
    st.caption(
        "Each bubble is one department category. Position shows volume (x) and typical "
        "time to close (y); size also tracks volume. Categories toward the bottom resolve "
        "quickly relative to demand; those toward the top take longer."
    )
    agg = _category_aggregates(sr_all)
    if not agg.empty:
        st.plotly_chart(
            _among_category_fig(agg),
            use_container_width=True,
            key="cat_explorer_among",
            config={"displayModeBar": False},
        )

    st.divider()
    if selected_type:
        st.subheader(f"{selected_type} — within-category detail")
        history = load_srtype_history(data_dir)
        _within_type_trend(history, selected_type, year)
        st.divider()
        _geo_breakdown(
            data_dir, geo_key, year, df, geojson, geo_id_col, featureidkey, mapbox_token, selected_type,
        )
    else:
        st.caption(
            "Select a row in the performance table above to see that type's trend across "
            "all available years and its geographic distribution."
        )
