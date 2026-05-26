from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from components.map_view import METRIC_OPTIONS, build_choropleth

# Minimum requests in a geo×SRType cell to display (suppresses noise; adjustable without rerunning pipeline)
_MIN_GEO_SRTYPE_N = 5

# Full department names for category pill abbreviations.
# Source: Baltimore City 311 system (balt311.baltimorecity.gov). Extend as new prefixes appear.
_CATEGORY_NAMES: dict[str, str] = {
    "BGE":  "BGE Street Lights",
    "BCRP": "Recreation & Parks",
    "CDW":  "Construction & Development",
    "CHE":  "Environmental Services",
    "DPW":  "Public Works",
    "ECC":  "Emergency Communications",
    "FF":   "Fire & Flood",
    "GRM":  "Grounds Maintenance",
    "HCD":  "Housing & Community Development",
    "MONO": "Parking Authority",
    "PC":   "Police Commissioner",
    "SW":   "Solid Waste",
    "TRS":  "Transportation",
}

# Ops-tab metric options — excludes requests_per_1k (NaN at all-requests level)
_OPS_METRIC_OPTIONS: dict[str, str] = {
    k: v for k, v in METRIC_OPTIONS.items() if v != "requests_per_1k"
}

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
def _build_equity_citywide_ts(data_dir: Path) -> pd.DataFrame:
    """Aggregate citywide citizen-initiated (equity subset) metrics from tract_metrics files."""
    records = []
    for path in sorted(data_dir.glob("tract_metrics_*.parquet")):
        try:
            year = int(path.stem.split("_")[-1])
        except ValueError:
            continue
        df = pd.read_parquet(path)
        if "total_requests" not in df.columns:
            continue
        w = df["total_requests"].fillna(0)
        total = w.sum()
        row: dict = {"year": year, "total_requests": float(total)}
        for col in ("closure_rate", "on_time_rate", "median_days_to_close"):
            if col in df.columns:
                mask = df[col].notna() & (w > 0)
                row[col] = (df.loc[mask, col] * w[mask]).sum() / w[mask].sum() if mask.any() else float("nan")
            else:
                row[col] = float("nan")
        records.append(row)
    return pd.DataFrame(records).sort_values("year").reset_index(drop=True) if records else pd.DataFrame()


@st.cache_data
def _build_timeseries(data_dir: Path) -> pd.DataFrame:
    """Aggregate citywide metrics for every available year from srtype_metrics (all requests).

    Uses volume-weighted means for rate metrics so each SRType contributes proportionally.
    requests_per_1k is omitted — not available at this level of aggregation.
    """
    records = []
    for path in sorted(data_dir.glob("srtype_metrics_*.parquet")):
        try:
            year = int(path.stem.split("_")[-1])
        except ValueError:
            continue
        df = pd.read_parquet(path)
        w = df["total_requests"].fillna(0) if "total_requests" in df.columns else None
        row: dict = {
            "year": year,
            "total_requests": df["total_requests"].sum() if w is not None else float("nan"),
            "requests_per_1k": float("nan"),
        }
        for col in ("closure_rate", "on_time_rate", "median_days_to_close"):
            if col in df.columns and w is not None:
                mask = df[col].notna() & (w > 0)
                row[col] = (df.loc[mask, col] * w[mask]).sum() / w[mask].sum() if mask.any() else float("nan")
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


def _scope_banner(data_dir: Path, year: int, equity_total: float | None = None) -> None:
    srtype_path = data_dir / f"srtype_metrics_{year}.parquet"

    all_total = None
    if srtype_path.exists():
        sr = pd.read_parquet(srtype_path)
        if "total_requests" in sr.columns:
            all_total = int(sr["total_requests"].sum())

    if equity_total is not None and not pd.isna(equity_total) and all_total is not None:
        # Full breakdown: used by equity / request-source tabs
        excluded = all_total - int(equity_total)
        pct_in = equity_total / all_total if all_total > 0 else float("nan")
        c1, c2, c3 = st.columns(3)
        c1.metric("All requests received", f"{all_total:,}")
        c2.metric("Equity analysis subset", f"{int(equity_total):,}",
                  delta=f"{pct_in:.0%} of total", delta_color="off")
        c3.metric("Excluded from analysis", f"{excluded:,}",
                  delta=f"{1 - pct_in:.0%} of total", delta_color="off")
        st.caption(
            "**Equity subset** = resident-initiated requests (Phone / API / Mail / Email) "
            "that are geocoded and not ECC-prefix service types. "
            "Performance metrics below apply to this subset only."
        )
    elif all_total is not None:
        # Simple total: used by ops tab — no equity framing
        st.metric("Total 311 requests received", f"{all_total:,}")


def _kpi_bar(ts: pd.DataFrame, year: int, eq_ts: pd.DataFrame | None = None) -> None:
    row = ts[ts["year"] == year]
    if row.empty:
        return
    row = row.iloc[0]

    prior_years = ts[ts["year"] < year]["year"]
    prior_row = None
    if not prior_years.empty:
        prior_row = ts[ts["year"] == prior_years.max()].iloc[0]

    eq_row = None
    if eq_ts is not None and not eq_ts.empty:
        eq_match = eq_ts[eq_ts["year"] == year]
        if not eq_match.empty:
            eq_row = eq_match.iloc[0]

    def delta(col: str, is_pct: bool = False):
        if prior_row is None:
            return None
        return _delta_str(row.get(col, float("nan")), prior_row.get(col, float("nan")), is_pct)

    def _fmt(val: float, is_pct: bool = False) -> str:
        if pd.isna(val):
            return "—"
        if is_pct:
            return f"{val:.1%}"
        return f"{val:,.0f}" if val >= 100 else f"{val:.1f}"

    c1, c2, c3, c4 = st.columns(4)
    c1.metric(
        "Requests received",
        f"{row['total_requests']:,.0f}" if not pd.isna(row.get("total_requests", float("nan"))) else "—",
        delta=_delta_str(row.get("total_requests"), prior_row.get("total_requests") if prior_row is not None else float("nan"), False),
        delta_color="off",
    )
    if eq_row is not None:
        c1.caption(f"citizen-initiated: {_fmt(eq_row.get('total_requests', float('nan')))}")

    c2.metric(
        "Median days to close",
        f"{row['median_days_to_close']:.1f}" if not pd.isna(row.get("median_days_to_close", float("nan"))) else "—",
        delta=delta("median_days_to_close"),
        delta_color="off",
    )
    if eq_row is not None:
        c2.caption(f"citizen-initiated: {_fmt(eq_row.get('median_days_to_close', float('nan')))} days")

    c3.metric(
        "Closure rate",
        f"{row['closure_rate']:.1%}" if not pd.isna(row.get("closure_rate", float("nan"))) else "—",
        delta=delta("closure_rate", is_pct=True),
        delta_color="off",
    )
    if eq_row is not None:
        c3.caption(f"citizen-initiated: {_fmt(eq_row.get('closure_rate', float('nan')), is_pct=True)}")

    c4.metric(
        "On-time rate",
        f"{row['on_time_rate']:.1%}" if not pd.isna(row.get("on_time_rate", float("nan"))) else "—",
        delta=delta("on_time_rate", is_pct=True),
        delta_color="off",
    )
    if eq_row is not None:
        c4.caption(f"citizen-initiated: {_fmt(eq_row.get('on_time_rate', float('nan')), is_pct=True)}")

    if prior_row is not None:
        st.caption(f"Δ vs. {int(prior_years.max())}")


def _timeseries_fig(
    ts: pd.DataFrame,
    metric_col: str,
    metric_label: str,
    year: int,
    eq_ts: pd.DataFrame | None = None,
) -> go.Figure:
    valid = ts[ts[metric_col].notna()].copy() if metric_col in ts.columns else pd.DataFrame()
    is_pct = metric_col in ("closure_rate", "on_time_rate")
    has_eq = bool(
        eq_ts is not None
        and not eq_ts.empty
        and metric_col in eq_ts.columns
        and eq_ts[metric_col].notna().any()
    )

    hover_fmt = "%{x}: %{y:.1%}<extra></extra>" if is_pct else "%{x}: %{y:.1f}<extra></extra>"

    fig = go.Figure()
    if not valid.empty:
        fig.add_trace(go.Scatter(
            x=valid["year"],
            y=valid[metric_col],
            mode="lines+markers",
            name="All requests",
            showlegend=has_eq,
            line=dict(color="#1F4E8C", width=2),
            marker=dict(
                size=[12 if y == year else 7 for y in valid["year"]],
                color=["#d73027" if y == year else "#1F4E8C" for y in valid["year"]],
            ),
            hovertemplate=hover_fmt,
        ))

    if has_eq:
        eq_valid = eq_ts[eq_ts[metric_col].notna()].copy()
        if not eq_valid.empty:
            fig.add_trace(go.Scatter(
                x=eq_valid["year"],
                y=eq_valid[metric_col],
                mode="lines+markers",
                name="Citizen-initiated",
                line=dict(color="#E07B39", width=2, dash="dash"),
                marker=dict(
                    size=[10 if y == year else 6 for y in eq_valid["year"]],
                    color=["#d73027" if y == year else "#E07B39" for y in eq_valid["year"]],
                ),
                hovertemplate=hover_fmt,
            ))

    fig.update_layout(
        height=250 if has_eq else 220,
        margin={"t": 30 if has_eq else 8, "b": 8, "l": 60, "r": 8},
        yaxis=dict(
            title=metric_label,
            tickformat=".0%" if is_pct else None,
            gridcolor="#eeeeee",
        ),
        xaxis=dict(title="Year", dtick=1),
        plot_bgcolor="white",
        paper_bgcolor="white",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        showlegend=has_eq,
    )
    return fig


@st.cache_data
def _load_geo_srtype_metrics(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    return pd.read_parquet(path)


_EXCLUDED_CATEGORIES = {"TEST"}


def _extract_categories(sr: pd.DataFrame) -> list[str]:
    """Return sorted unique hyphen-prefixes from SRType names (e.g. 'SW', 'HCD', 'TRS')."""
    return sorted({
        name.split("-")[0].strip()
        for name in sr["SRType"]
        if isinstance(name, str) and "-" in name
        and name.split("-")[0].strip()
        and name.split("-")[0].strip() not in _EXCLUDED_CATEGORIES
    })


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


def _srtype_charts(data_dir: Path, year: int) -> tuple[str | None, str | None]:
    """Render category pills + performance table + year-over-year detail.
    Returns (selected_type, selected_cat) — either may be None."""
    srtype_path = data_dir / f"srtype_metrics_{year}.parquet"
    if not srtype_path.exists():
        st.caption(
            "SRType breakdown unavailable — run `pipeline.py --stage srtype --year <year>` "
            "to generate it."
        )
        return None, None

    sr_all = (
        pd.read_parquet(srtype_path)
        .sort_values("total_requests", ascending=False)
        .reset_index(drop=True)
    )
    pct_col = "pct_resident_initiated" if "pct_resident_initiated" in sr_all.columns else None

    # ── Category pills ────────────────────────────────────────────────────────
    categories = _extract_categories(sr_all)
    selected_cat = None
    if categories:
        cat_sel = st.pills(
            "Category", ["All"] + categories,
            default="All",
            key="srtype_cat",
        )
        selected_cat = cat_sel if (cat_sel and cat_sel != "All") else None
        known = {c: _CATEGORY_NAMES[c] for c in categories if c in _CATEGORY_NAMES}
        if known:
            st.caption("  ·  ".join(f"**{k}** {v}" for k, v in sorted(known.items())))
        sr = (
            sr_all[sr_all["SRType"].str.startswith(f"{selected_cat}-")]
            if selected_cat
            else sr_all
        ).reset_index(drop=True)
    else:
        sr = sr_all

    # ── Selectable performance table ──────────────────────────────────────────
    scope_label = f"**{selected_cat}** types" if selected_cat else "all types"
    st.markdown(f"**Performance by type** ({scope_label}) — click any row to drill into year-over-year trends")
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
        height=min(400, max(150, 35 * len(sr) + 38)),
        on_select="rerun",
        selection_mode="single-row",
        key="srtype_table",
    )

    # ── Year-over-year detail ─────────────────────────────────────────────────
    history = _load_srtype_history(data_dir)
    selected_rows = event.selection.rows
    chart_layout = dict(
        height=260,
        margin={"t": 8, "b": 8, "l": 60, "r": 8},
        xaxis=dict(title="Year", dtick=1),
        plot_bgcolor="white",
        paper_bgcolor="white",
    )

    if selected_rows and not history.empty:
        selected_type = sr.iloc[selected_rows[0]]["SRType"]
        type_hist = history[history["SRType"] == selected_type].sort_values("year")
        if type_hist.empty:
            st.caption(f"No historical data found for **{selected_type}**.")
            return selected_type, selected_cat
        chart_title = f"**{selected_type}** — year over year · selected year in red"
        vol_hist = type_hist
        days_hist = type_hist.dropna(subset=["median_days_to_close"])
    else:
        selected_type = None
        # Aggregate to year level for the current table scope
        scope = (
            history[history["SRType"].str.startswith(f"{selected_cat}-")]
            if selected_cat else history
        )
        vol_hist = scope.groupby("year")["total_requests"].sum().reset_index().sort_values("year")
        days_sub = scope.dropna(subset=["median_days_to_close", "total_requests"])
        if not days_sub.empty:
            days_sub = days_sub.copy()
            days_sub["_wtd"] = days_sub["median_days_to_close"] * days_sub["total_requests"]
            days_hist = (
                (days_sub.groupby("year")["_wtd"].sum() / days_sub.groupby("year")["total_requests"].sum())
                .reset_index(name="median_days_to_close")
                .sort_values("year")
            )
        else:
            days_hist = pd.DataFrame(columns=["year", "median_days_to_close"])
        scope_str = f"**{selected_cat} category**" if selected_cat else "**All request types**"
        chart_title = f"{scope_str} — year over year · selected year in red"

    bar_colors_vol = ["#d73027" if y == year else "#1F4E8C" for y in vol_hist["year"]]
    bar_colors_days = ["#d73027" if y == year else "#1F4E8C" for y in days_hist["year"]]

    st.markdown(chart_title)
    col_vol, col_days = st.columns(2)
    with col_vol:
        st.caption("Total requests")
        fig_vol = go.Figure(go.Bar(
            x=vol_hist["year"],
            y=vol_hist["total_requests"],
            marker_color=bar_colors_vol,
            hovertemplate="%{x}: %{y:,}<extra></extra>",
        ))
        fig_vol.update_layout(**chart_layout, yaxis=dict(title="Requests", gridcolor="#eeeeee"))
        vol_ev = st.plotly_chart(fig_vol, use_container_width=True, key="srtype_vol",
                        on_select="rerun", config={"displayModeBar": False})

    with col_days:
        st.caption("Median days to close")
        fig_days = go.Figure(go.Bar(
            x=days_hist["year"],
            y=days_hist["median_days_to_close"],
            marker_color=bar_colors_days,
            hovertemplate="%{x}: %{y:.1f} days<extra></extra>",
        ))
        fig_days.update_layout(**chart_layout, yaxis=dict(title="Days", gridcolor="#eeeeee"))
        days_ev = st.plotly_chart(fig_days, use_container_width=True, key="srtype_days",
                        on_select="rerun", config={"displayModeBar": False})

    # Bar click → navigate year (same mechanism as the time series chart above)
    for ev in [vol_ev, days_ev]:
        if ev and ev.selection and ev.selection.points:
            st.session_state["ops_year_clicked"] = int(ev.selection.points[0]["x"])
            st.rerun()

    return selected_type, selected_cat


def render_operations(
    data_dir: Path,
    geo_key: str,
    year: int,
    df: pd.DataFrame,
    geojson: dict,
    geo_id_col: str,
    featureidkey: str,
    mapbox_token: str,
) -> None:
    ts = _build_timeseries(data_dir)
    eq_ts = _build_equity_citywide_ts(data_dir)

    st.subheader("City-wide Performance")
    _kpi_bar(ts, year, eq_ts=eq_ts)

    # Inline metric selector for time series and geo map
    metric_label = st.radio(
        "Metric",
        list(_OPS_METRIC_OPTIONS.keys()),
        horizontal=True,
        key="ops_metric",
        label_visibility="collapsed",
    )
    metric_col = _OPS_METRIC_OPTIONS[metric_label]

    st.markdown(f"**{metric_label} — all available years** · click a point to change year")
    ts_event = st.plotly_chart(
        _timeseries_fig(ts, metric_col, metric_label, year, eq_ts=eq_ts),
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
    selected_type, selected_cat = _srtype_charts(data_dir, year)

    # ── Geographic distribution map ───────────────────────────────────────────
    st.divider()
    geo_col, _ = st.columns([3, 7])
    with geo_col:
        _curr_geo = st.session_state.get("geo_level", "Census Tract")
        new_geo_ops = st.radio(
            "View as",
            ["Census Tract", "CSA"],
            index=0 if _curr_geo == "Census Tract" else 1,
            horizontal=True,
        )
        if new_geo_ops != _curr_geo:
            st.session_state["geo_level"] = new_geo_ops
            st.rerun()
    st.subheader("Geographic Distribution")

    geo_srtype = _load_geo_srtype_metrics(data_dir / f"{geo_key}_srtype_metrics_{year}.parquet")
    totals = (
        geo_srtype[geo_srtype["total_requests"] >= _MIN_GEO_SRTYPE_N]
        if not geo_srtype.empty else geo_srtype
    )

    if selected_type and not totals.empty:
        type_totals = totals[totals["SRType"] == selected_type][["geoid", "total_requests"]]
        map_df = df[["geoid"]].merge(type_totals, on="geoid", how="left")
        map_df["total_requests"] = map_df["total_requests"].fillna(0).astype(int)
        map_caption = f"**{selected_type}** request count by geography"
    elif selected_type:
        map_df = df[["geoid", "total_requests"]] if "total_requests" in df.columns else None
        map_caption = "Overall request volume shown (re-run pipeline to get per-type geographic counts)"
    elif selected_cat and not totals.empty:
        cat_totals = (
            totals[totals["SRType"].str.startswith(f"{selected_cat}-")]
            .groupby("geoid")["total_requests"].sum()
            .reset_index()
        )
        map_df = df[["geoid"]].merge(cat_totals, on="geoid", how="left")
        map_df["total_requests"] = map_df["total_requests"].fillna(0).astype(int)
        map_caption = f"**{selected_cat}** category request count by geography"
    else:
        map_df = df[["geoid", "total_requests"]] if "total_requests" in df.columns else None
        map_caption = "Total requests by geography · select a category or row above to filter"

    if map_df is not None and "total_requests" in map_df.columns and not map_df.empty:
        st.caption(map_caption)
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
