from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from components.map_view import METRIC_OPTIONS, build_choropleth

# How to aggregate each metric to a single citywide value
_METRIC_AGG = {
    "median_days_to_close": "median",
    "closure_rate":         "wmean",   # weighted by total_requests
    "on_time_rate":         "wmean",
    "requests_per_1k":      "median",
}


def _citywide_value(df: pd.DataFrame, col: str) -> float:
    method = _METRIC_AGG.get(col, "median")
    if method == "wmean" and "total_requests" in df.columns:
        w = df["total_requests"].fillna(0)
        mask = df[col].notna() & (w > 0)
        if mask.any():
            return (df.loc[mask, col] * w[mask]).sum() / w[mask].sum()
    return df[col].median()


@st.cache_data
def _build_timeseries(data_dir: Path, geo_key: str) -> pd.DataFrame:
    """Aggregate citywide metric values for every available year parquet."""
    records = []
    for path in sorted(data_dir.glob(f"{geo_key}_metrics_*.parquet")):
        try:
            year = int(path.stem.split("_")[-1])
        except ValueError:
            continue
        df = pd.read_parquet(path)
        row: dict = {"year": year, "total_requests": df["total_requests"].sum() if "total_requests" in df.columns else float("nan")}
        for col in METRIC_OPTIONS.values():
            if col in df.columns:
                row[col] = _citywide_value(df, col)
            else:
                row[col] = float("nan")
        records.append(row)
    return pd.DataFrame(records).sort_values("year").reset_index(drop=True)


def _delta_str(current: float, prior: float, is_pct: bool) -> str:
    if pd.isna(current) or pd.isna(prior) or prior == 0:
        return None
    diff = current - prior
    if is_pct:
        return f"{diff:+.1%}"
    return f"{diff:+.1f}"


def _scope_banner(data_dir: Path, year: int, equity_total: float) -> None:
    srtype_path = data_dir / f"srtype_metrics_{year}.parquet"

    all_total = None
    if srtype_path.exists():
        sr = pd.read_parquet(srtype_path)
        if "total_requests" in sr.columns:
            all_total = int(sr["total_requests"].sum())

    if all_total is not None and not pd.isna(equity_total):
        excluded = all_total - int(equity_total)
        pct_in = equity_total / all_total if all_total > 0 else float("nan")
        c1, c2, c3 = st.columns(3)
        c1.metric("All requests received", f"{all_total:,}")
        c2.metric("Equity analysis subset", f"{int(equity_total):,}",
                  delta=f"{pct_in:.0%} of total", delta_color="off")
        c3.metric("Excluded from analysis", f"{excluded:,}",
                  delta=f"{1 - pct_in:.0%} of total", delta_color="off")
    elif not pd.isna(equity_total):
        st.metric("Equity analysis subset", f"{int(equity_total):,}")

    st.caption(
        "**Equity subset** = resident-initiated requests (Phone / API / Mail / Email) "
        "that are geocoded and not ECC-prefix service types. "
        "Performance metrics below apply to this subset only."
    )


def _kpi_bar(ts: pd.DataFrame, year: int) -> None:
    row = ts[ts["year"] == year]
    if row.empty:
        return
    row = row.iloc[0]

    prior_years = ts[ts["year"] < year]["year"]
    prior_row = None
    if not prior_years.empty:
        prior_row = ts[ts["year"] == prior_years.max()].iloc[0]

    def delta(col: str, is_pct: bool = False):
        if prior_row is None:
            return None
        return _delta_str(row.get(col, float("nan")), prior_row.get(col, float("nan")), is_pct)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric(
        "Requests analyzed",
        f"{row['total_requests']:,.0f}" if not pd.isna(row.get("total_requests", float("nan"))) else "—",
        delta=_delta_str(row.get("total_requests"), prior_row.get("total_requests") if prior_row is not None else float("nan"), False),
        delta_color="off",
    )
    c2.metric(
        "Median days to close",
        f"{row['median_days_to_close']:.1f}" if not pd.isna(row.get("median_days_to_close", float("nan"))) else "—",
        delta=delta("median_days_to_close"),
        delta_color="off",
    )
    c3.metric(
        "Closure rate",
        f"{row['closure_rate']:.1%}" if not pd.isna(row.get("closure_rate", float("nan"))) else "—",
        delta=delta("closure_rate", is_pct=True),
        delta_color="off",
    )
    c4.metric(
        "On-time rate",
        f"{row['on_time_rate']:.1%}" if not pd.isna(row.get("on_time_rate", float("nan"))) else "—",
        delta=delta("on_time_rate", is_pct=True),
        delta_color="off",
    )


def _timeseries_fig(ts: pd.DataFrame, metric_col: str, metric_label: str, year: int) -> go.Figure:
    valid = ts[ts[metric_col].notna()].copy() if metric_col in ts.columns else pd.DataFrame()
    is_pct = metric_col in ("closure_rate", "on_time_rate")

    fig = go.Figure()
    if not valid.empty:
        fig.add_trace(go.Scatter(
            x=valid["year"],
            y=valid[metric_col],
            mode="lines+markers",
            line=dict(color="#1F4E8C", width=2),
            marker=dict(
                size=[12 if y == year else 7 for y in valid["year"]],
                color=["#d73027" if y == year else "#1F4E8C" for y in valid["year"]],
            ),
            hovertemplate=(
                "%{x}: %{y:.1%}<extra></extra>" if is_pct
                else "%{x}: %{y:.1f}<extra></extra>"
            ),
        ))

    fig.update_layout(
        height=220,
        margin={"t": 8, "b": 8, "l": 60, "r": 8},
        yaxis=dict(
            title=metric_label,
            tickformat=".0%" if is_pct else None,
            gridcolor="#eeeeee",
        ),
        xaxis=dict(title="Year", dtick=1),
        plot_bgcolor="white",
        paper_bgcolor="white",
    )
    return fig


@st.cache_data
def _load_srtype_history(data_dir: Path) -> pd.DataFrame:
    """All available srtype_metrics years combined into one DataFrame."""
    dfs = []
    for p in sorted(data_dir.glob("srtype_metrics_*.parquet")):
        try:
            y = int(p.stem.split("_")[-1])
        except ValueError:
            continue
        df = pd.read_parquet(p)
        df["year"] = y
        dfs.append(df)
    return pd.concat(dfs, ignore_index=True) if dfs else pd.DataFrame()


def _srtype_charts(data_dir: Path, year: int) -> str | None:
    """Render performance table + year-over-year detail. Returns selected SRType or None."""
    srtype_path = data_dir / f"srtype_metrics_{year}.parquet"
    if not srtype_path.exists():
        st.caption(
            "SRType breakdown unavailable — run `pipeline.py --stage srtype --year <year>` "
            "to generate it."
        )
        return None

    sr = (
        pd.read_parquet(srtype_path)
        .sort_values("total_requests", ascending=False)
        .reset_index(drop=True)
    )
    pct_col = "pct_resident_initiated" if "pct_resident_initiated" in sr.columns else None

    # ── Selectable performance table ──────────────────────────────────────────
    st.markdown("**Performance by type** — click a row to see year-over-year trends")
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
        "on_time_rate": "On-time rate", "pct_resident_initiated": "% Resident",
    }
    display = sr[display_cols].rename(columns=rename)
    event = st.dataframe(
        display.style.format({rename.get(k, k): v for k, v in fmt.items()}, na_rep="—"),
        use_container_width=True,
        hide_index=True,
        height=400,
        on_select="rerun",
        selection_mode="single-row",
        key="srtype_table",
    )

    # ── Year-over-year detail for selected type ───────────────────────────────
    selected_rows = event.selection.rows
    if not selected_rows:
        st.caption("Click a row above to see year-over-year volume and time-to-close trends.")
        return None

    selected_type = sr.iloc[selected_rows[0]]["SRType"]
    history = _load_srtype_history(data_dir)
    type_hist = history[history["SRType"] == selected_type].sort_values("year")

    if type_hist.empty:
        st.caption(f"No historical data found for **{selected_type}**.")
        return None

    st.markdown(f"**{selected_type}** — year over year · selected year in red")
    bar_colors = ["#d73027" if y == year else "#1F4E8C" for y in type_hist["year"]]
    chart_layout = dict(
        height=260,
        margin={"t": 8, "b": 8, "l": 60, "r": 8},
        xaxis=dict(title="Year", dtick=1),
        plot_bgcolor="white",
        paper_bgcolor="white",
    )

    col_vol, col_days = st.columns(2)
    with col_vol:
        st.caption("Total requests")
        fig_vol = go.Figure(go.Bar(
            x=type_hist["year"],
            y=type_hist["total_requests"],
            marker_color=bar_colors,
            hovertemplate="%{x}: %{y:,}<extra></extra>",
        ))
        fig_vol.update_layout(**chart_layout,
                              yaxis=dict(title="Requests", gridcolor="#eeeeee"))
        st.plotly_chart(fig_vol, use_container_width=True, key="srtype_vol",
                        config={"displayModeBar": False})

    with col_days:
        st.caption("Median days to close")
        days_hist = type_hist.dropna(subset=["median_days_to_close"])
        days_colors = ["#d73027" if y == year else "#1F4E8C" for y in days_hist["year"]]
        fig_days = go.Figure(go.Bar(
            x=days_hist["year"],
            y=days_hist["median_days_to_close"],
            marker_color=days_colors,
            hovertemplate="%{x}: %{y:.1f} days<extra></extra>",
        ))
        fig_days.update_layout(**chart_layout,
                               yaxis=dict(title="Days", gridcolor="#eeeeee"))
        st.plotly_chart(fig_days, use_container_width=True, key="srtype_days",
                        config={"displayModeBar": False})

    return selected_type


def render_operations(
    data_dir: Path,
    geo_key: str,
    year: int,
    metric_col: str,
    metric_label: str,
    df: pd.DataFrame,
    geojson: dict,
    geo_id_col: str,
    featureidkey: str,
    mapbox_token: str,
) -> None:
    ts = _build_timeseries(data_dir, geo_key)

    st.subheader("City-wide Performance")
    equity_total = ts.loc[ts["year"] == year, "total_requests"].squeeze() if not ts.empty else float("nan")
    _scope_banner(data_dir, year, equity_total)
    st.divider()
    _kpi_bar(ts, year)

    st.markdown(f"**{metric_label} — all available years** · click a point to change year")
    ts_event = st.plotly_chart(
        _timeseries_fig(ts, metric_col, metric_label, year),
        use_container_width=True,
        key="ops_timeseries",
        on_select="rerun",
        config={"displayModeBar": False},
    )
    if ts_event and ts_event.selection and ts_event.selection.points:
        clicked_year = int(ts_event.selection.points[0]["x"])
        st.session_state["ops_year_clicked"] = clicked_year
        st.rerun()

    st.divider()
    st.subheader("Breakdown by Request Type")
    selected_type = _srtype_charts(data_dir, year)

    # ── Geographic distribution map ───────────────────────────────────────────
    st.divider()
    st.subheader("Geographic Distribution")

    map_df = df.copy()
    if selected_type and "top_sr_type" in df.columns:
        filtered = df[df["top_sr_type"] == selected_type]
        if not filtered.empty:
            map_df = filtered
            st.caption(f"Tracts where **{selected_type}** is the top request type · total requests")
        else:
            st.caption(f"No tracts have **{selected_type}** as top type — showing all · total requests")
    else:
        st.caption("Total requests by geography · click a table row above to filter by type")

    if "total_requests" in map_df.columns and not map_df.empty:
        fig_map = build_choropleth(
            df=map_df,
            geojson=geojson,
            geo_id_col=geo_id_col,
            featureidkey=featureidkey,
            metric_col="total_requests",
            metric_label="Total requests",
            mapbox_token=mapbox_token,
        )
        st.plotly_chart(fig_map, use_container_width=True, key="ops_map")
