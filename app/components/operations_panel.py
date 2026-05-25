from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from components.map_view import METRIC_OPTIONS

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


def _srtype_charts(srtype_path: Path) -> None:
    if not srtype_path.exists():
        st.caption(
            f"SRType breakdown unavailable — run `pipeline.py --stage srtype --year <year>` "
            "to generate it."
        )
        return

    sr = pd.read_parquet(srtype_path).sort_values("total_requests", ascending=False)

    st.markdown("**Requests by type**")
    st.caption("Bar width = volume · Color = % resident-initiated (gray → blue)")

    pct_col = "pct_resident_initiated" if "pct_resident_initiated" in sr.columns else None
    colors = (
        [f"rgba(31,78,140,{0.3 + 0.7 * v})" for v in sr[pct_col].fillna(0)]
        if pct_col else "#1F4E8C"
    )

    fig = go.Figure(go.Bar(
        y=sr["SRType"],
        x=sr["total_requests"],
        orientation="h",
        marker_color=colors,
        hovertemplate="<b>%{y}</b><br>Requests: %{x:,}<extra></extra>",
    ))
    fig.update_layout(
        height=max(300, 20 * len(sr)),
        margin={"t": 8, "b": 8, "l": 220, "r": 8},
        xaxis=dict(title="Total requests", gridcolor="#eeeeee"),
        yaxis=dict(autorange="reversed"),
        plot_bgcolor="white",
        paper_bgcolor="white",
    )
    st.plotly_chart(fig, use_container_width=True, key="srtype_volume")

    st.markdown("**Performance by type**")
    display = sr[["SRType", "total_requests", "closure_rate", "median_days_to_close", "on_time_rate"]
                 + (["pct_resident_initiated"] if pct_col else [])].copy()

    # Format for display
    fmt: dict = {
        "total_requests": "{:,.0f}",
        "closure_rate": "{:.1%}",
        "median_days_to_close": "{:.1f}",
        "on_time_rate": "{:.1%}",
    }
    if pct_col:
        fmt["pct_resident_initiated"] = "{:.0%}"

    rename = {
        "SRType": "Type",
        "total_requests": "Requests",
        "closure_rate": "Closure rate",
        "median_days_to_close": "Median days",
        "on_time_rate": "On-time rate",
        "pct_resident_initiated": "% Resident",
    }
    display = display.rename(columns=rename)
    st.dataframe(
        display.style.format({rename.get(k, k): v for k, v in fmt.items()}, na_rep="—"),
        use_container_width=True,
        hide_index=True,
        height=400,
    )


def render_operations(
    data_dir: Path,
    geo_key: str,
    year: int,
    metric_col: str,
    metric_label: str,
) -> None:
    ts = _build_timeseries(data_dir, geo_key)

    st.subheader("City-wide Performance")
    equity_total = ts.loc[ts["year"] == year, "total_requests"].squeeze() if not ts.empty else float("nan")
    _scope_banner(data_dir, year, equity_total)
    st.divider()
    _kpi_bar(ts, year)

    st.markdown(f"**{metric_label} — all available years**")
    st.plotly_chart(
        _timeseries_fig(ts, metric_col, metric_label, year),
        use_container_width=True,
        key="ops_timeseries",
    )

    st.divider()
    st.subheader("Breakdown by Request Type")
    _srtype_charts(data_dir / f"srtype_metrics_{year}.parquet")
