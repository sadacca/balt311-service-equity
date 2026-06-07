from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from components.map_view import METRIC_OPTIONS
from components.utils import overlap_score, score_label

# One color per metric, consistent across both trend charts
_METRIC_COLORS = {
    "Median days to close":        "#2166ac",
    "Closure rate":                "#d73027",
    "On-time rate":                "#1a9641",
    "Requests per 1,000 residents": "#762a83",
}


@st.cache_data
def compute_citywide_equity_trend(
    data_dir: Path,
    demographics: pd.DataFrame,
    geo_key: str,
) -> pd.DataFrame:
    """Return a long DataFrame with columns: year, metric, dimension, score."""
    records = []
    for path in sorted(data_dir.glob(f"{geo_key}_metrics_*.parquet")):
        try:
            year = int(path.stem.split("_")[-1])
        except ValueError:
            continue
        df = pd.read_parquet(path)
        merged = df.merge(demographics, on="geoid", how="left")

        for label, col in METRIC_OPTIONS.items():
            if col not in merged.columns:
                continue
            valid = merged.dropna(subset=[col])

            # Race: majority-Black vs. majority-White
            race_valid = valid.dropna(subset=["pct_black", "pct_white"])
            black_g = race_valid[race_valid["pct_black"] > 0.5][col]
            white_g = race_valid[race_valid["pct_white"] > 0.5][col]
            records.append({
                "year": year, "metric": label, "dimension": "Race",
                "score": overlap_score(black_g, white_g),
            })

            # Income: below vs. above median
            inc_valid = valid.dropna(subset=["median_income"])
            city_med = inc_valid["median_income"].median()
            below = inc_valid[inc_valid["median_income"] <= city_med][col]
            above = inc_valid[inc_valid["median_income"] > city_med][col]
            records.append({
                "year": year, "metric": label, "dimension": "Income",
                "score": overlap_score(below, above),
            })

    return pd.DataFrame(records)


def _trend_fig(trend_df: pd.DataFrame, dimension: str, metric_label: str) -> go.Figure:
    fig = go.Figure()

    # Threshold bands (drawn first, below the lines)
    fig.add_hrect(y0=0.7, y1=1.0, fillcolor="green",  opacity=0.06, line_width=0)
    fig.add_hrect(y0=0.4, y1=0.7, fillcolor="orange", opacity=0.06, line_width=0)
    fig.add_hrect(y0=0.0, y1=0.4, fillcolor="red",    opacity=0.06, line_width=0)

    sub = (
        trend_df[(trend_df["dimension"] == dimension) & (trend_df["metric"] == metric_label)]
        .dropna(subset=["score"])
        .sort_values("year")
    )
    if not sub.empty:
        color = _METRIC_COLORS.get(metric_label, "#666666")
        fig.add_trace(go.Scatter(
            x=sub["year"],
            y=sub["score"],
            mode="lines+markers",
            name=metric_label,
            line=dict(color=color, width=2),
            marker=dict(size=8, color=color),
            hovertemplate="%{x}: %{y:.0%}<extra>" + metric_label + "</extra>",
        ))

    fig.update_layout(
        height=260,
        margin={"t": 8, "b": 8, "l": 55, "r": 8},
        showlegend=False,
        yaxis=dict(
            title="Equity score",
            range=[0, 1],
            tickformat=".0%",
            gridcolor="#eeeeee",
        ),
        xaxis=dict(title="Year", dtick=1),
        plot_bgcolor="white",
        paper_bgcolor="white",
    )
    return fig


def render_equity_trend(
    data_dir: Path,
    demographics: pd.DataFrame,
    geo_key: str,
    metric_label: str,
) -> None:
    year_files = list(data_dir.glob(f"{geo_key}_metrics_*.parquet"))
    if len(year_files) < 2:
        return  # nothing to trend with one year

    st.subheader("Equity Trend — Year over Year")
    st.caption(
        f"Is the **{metric_label}** gap between demographic groups getting better or worse over time? "
        "Higher scores mean more similar outcomes between groups. "
        "Green = not much of a gap · amber = worth watching · red = significant gap."
    )

    trend_df = compute_citywide_equity_trend(data_dir, demographics, geo_key)
    if trend_df.empty:
        st.caption("No trend data available.")
        return

    col_race, col_income = st.columns(2)
    with col_race:
        st.markdown("**Race-based disparity**")
        st.plotly_chart(_trend_fig(trend_df, "Race", metric_label), use_container_width=True, key="trend_race", config={"displayModeBar": False})
    with col_income:
        st.markdown("**Income-based disparity**")
        st.plotly_chart(_trend_fig(trend_df, "Income", metric_label), use_container_width=True, key="trend_income", config={"displayModeBar": False})
