"""Equity tab — citywide race/income disparity by metric.

Extracted verbatim from the inline block that used to live in `app.py` so that all
six within-Baltimore tabs are uniform `render_*` calls and the app shell stays a thin
wiring layer. The geographic-unit toggle that used to sit here is now a single global
control in the Within-Baltimore group (it writes the shared `geo_level` state every
tab reads), so this component receives the resolved `geo_key`/`featureidkey` rather
than owning its own toggle.

Keeps `key="eq_metric"` on the metric selector: the Mix-Adjusted Equity tab reads that
session-state value so the two equity tabs stay aligned on the chosen metric.
"""
from pathlib import Path

import pandas as pd
import streamlit as st

from components import theme
from components.equity_distributions import render_equity_distributions
from components.equity_trend import render_equity_trend
from components.map_view import METRIC_OPTIONS, build_choropleth
from components.summary_panel import render as render_summary, render_peer_comparison


def render_equity(
    data_dir: Path,
    geo_key: str,
    year: int,
    df_full: pd.DataFrame,
    geojson: dict,
    featureidkey: str,
    mapbox_token: str,
    demographics: pd.DataFrame | None,
) -> None:
    theme.tab_intro(
        "Does service quality differ systematically by where it's delivered and who "
        "it's delivered to?"
    )
    st.caption(
        "*Note: differences here can reflect the kinds of services delivered as much "
        "as delivery quality.*"
    )
    with st.expander("What to look for"):
        st.markdown(
            "- How much do outcomes differ between majority-Black and majority-White "
            "neighborhoods? Between lower- and higher-income ones?\n"
            "- Is the gap larger for some metrics (wait time vs. closure rate) than others?\n"
            "- Is the gap getting larger or smaller over time? "
            "The trend chart at the bottom of the page shows year-over-year movement."
        )

    # ── Inline controls above map ─────────────────────────────────────────────
    # Geographic unit is now a single global control in the Within-Baltimore group;
    # this tab only chooses the metric and an optional request-type filter.
    ctrl_metric, ctrl_srtype = st.columns([3, 5])

    with ctrl_metric:
        metric_label = st.selectbox(
            "Color map by",
            list(METRIC_OPTIONS.keys()),
            key="eq_metric",
        )
        metric_col = METRIC_OPTIONS[metric_label]

    with ctrl_srtype:
        df = df_full
        if "top_sr_type" in df_full.columns:
            all_types = sorted(df_full["top_sr_type"].dropna().unique().tolist())
            selected_types = st.multiselect(
                "Filter by top request type",
                all_types,
                default=[],
                placeholder="All geographies",
                key="eq_srtype",
            )
            if selected_types:
                df = df_full[df_full["top_sr_type"].isin(selected_types)]

    # ── Choropleth map ────────────────────────────────────────────────────────
    if metric_col not in df.columns:
        st.warning(f"Metric column `{metric_col}` not found in processed data.")
        return

    col_map, col_panel = st.columns([3, 1])

    fig = build_choropleth(
        df=df,
        geojson=geojson,
        geo_id_col="geoid",
        featureidkey=featureidkey,
        metric_col=metric_col,
        metric_label=metric_label,
        mapbox_token=mapbox_token,
    )

    with col_map:
        selection = st.plotly_chart(
            fig,
            use_container_width=True,
            on_select="rerun",
            key="map_select",
        )

    selected_row = None
    if selection and selection.get("selection", {}).get("points"):
        pt = selection["selection"]["points"][0]
        loc_val = pt.get("location")
        if loc_val is not None:
            match = df[df["geoid"] == loc_val]
            if not match.empty:
                selected_row = match.iloc[0]

    with col_panel:
        render_summary(selected_row)

    # ── Multi-neighborhood comparison ─────────────────────────────────────────
    with st.expander("Compare neighborhoods side by side"):
        st.caption(
            "Select up to 5 neighborhoods to compare their service metrics. "
            "Click a neighborhood on the map above, then add others here."
        )
        all_geo_names = sorted(df["geoid"].tolist())
        compare_geos = st.multiselect(
            "Neighborhoods to compare",
            all_geo_names,
            default=(
                [str(selected_row["geoid"])]
                if selected_row is not None and "geoid" in selected_row.index
                else []
            ),
            max_selections=5,
            placeholder="Pick up to 5 neighborhoods",
            key="eq_compare_geos",
        )
        if compare_geos:
            cmp_rows = df[df["geoid"].isin(compare_geos)].set_index("geoid")
            cmp_metrics = [
                ("Closure rate", "closure_rate", ".1%"),
                ("Median days to close", "median_days_to_close", ".1f"),
                ("On-time rate", "on_time_rate", ".1%"),
                ("Requests / 1k", "requests_per_1k", ".1f"),
                ("Total requests", "total_requests", ",.0f"),
            ]
            tbl: dict[str, dict] = {}
            for lbl, col, fmt in cmp_metrics:
                if col not in cmp_rows.columns:
                    continue
                tbl[lbl] = {
                    geo: (
                        f"{cmp_rows.loc[geo, col]:{fmt}}"
                        if geo in cmp_rows.index and pd.notna(cmp_rows.loc[geo, col])
                        else "—"
                    )
                    for geo in compare_geos
                }
            if tbl:
                st.dataframe(
                    pd.DataFrame(tbl).T.rename_axis("Metric").reset_index(),
                    use_container_width=True,
                    hide_index=True,
                )

    # ── Peer neighborhood comparison ──────────────────────────────────────────
    if selected_row is not None and demographics is not None:
        render_peer_comparison(selected_row, df, demographics)

    if demographics is not None:
        st.divider()
        render_equity_distributions(df, demographics, metric_col, metric_label)
        st.divider()
        render_equity_trend(data_dir, demographics, geo_key, metric_label)
    else:
        st.divider()
        st.caption(
            "Demographic equity charts unavailable — "
            f"`{geo_key}_demographics.csv` not found in `data/processed/`. "
            "Re-run the pipeline to generate it."
        )
