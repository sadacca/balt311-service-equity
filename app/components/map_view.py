import json
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from components import theme


METRIC_OPTIONS: dict[str, str] = {
    "Median days to close": "median_days_to_close",
    "Closure rate": "closure_rate",
    "On-time rate": "on_time_rate",
    "Requests per 1,000 residents": "requests_per_1k",
}

MAPBOX_STYLE = "mapbox://styles/mapbox/light-v11"
BALTIMORE_CENTER = {"lat": 39.2904, "lon": -76.6122}
BALTIMORE_ZOOM = 10.5


def build_choropleth(
    df: pd.DataFrame,
    geojson: dict,
    geo_id_col: str,
    featureidkey: str,
    metric_col: str,
    metric_label: str,
    mapbox_token: str,
    sequential: bool = False,
) -> go.Figure:
    valid_vals = df[metric_col].dropna()
    if sequential:
        colorscale = theme.SEQUENTIAL_SCALE
        midpoint = None
        data_max = float(valid_vals.max()) if not valid_vals.empty else 1.0
        range_color = [0, data_max]
        colorbar_ticks = {"tickvals": [0, data_max], "ticktext": ["Fewer", "More"]}
    else:
        midpoint = float(valid_vals.median()) if not valid_vals.empty else None
        range_color = None
        data_min = float(valid_vals.min()) if not valid_vals.empty else 0.0
        data_max = float(valid_vals.max()) if not valid_vals.empty else 1.0
        data_mid = midpoint if midpoint is not None else (data_min + data_max) / 2
        # Convention across the app: red = worse. `RdBu` is red at the low end, blue at
        # the high end; `RdBu_r` is the reverse.
        if metric_col == "median_days_to_close":
            # Higher days = slower = worse → red at the high end.
            colorscale = theme.DIVERGING_WORSE_HIGH
            colorbar_ticks = {
                "tickvals": [data_min, data_mid, data_max],
                "ticktext": ["Shorter wait", "City median", "Longer wait"],
            }
        else:
            # Closure / on-time rate, requests-per-1k: higher = better → red at the low end.
            colorscale = theme.DIVERGING_BETTER_HIGH
            colorbar_ticks = {
                "tickvals": [data_min, data_mid, data_max],
                "ticktext": ["Lower", "City median", "Higher"],
            }

    fig = px.choropleth_mapbox(
        df,
        geojson=geojson,
        locations=geo_id_col,
        featureidkey=featureidkey,
        color=metric_col,
        color_continuous_scale=colorscale,
        color_continuous_midpoint=midpoint,
        range_color=range_color,
        mapbox_style=MAPBOX_STYLE,
        zoom=BALTIMORE_ZOOM,
        center=BALTIMORE_CENTER,
        opacity=0.75,
        labels={metric_col: metric_label},
        hover_data={geo_id_col: True, metric_col: ":.1f"},
    )
    fig.update_layout(
        margin={"r": 0, "t": 0, "l": 0, "b": 55},
        height=580,
        font={"family": theme.FONT_FAMILY, "size": theme.FONT_SIZE},
        coloraxis_colorbar=dict(
            orientation="h",
            x=0.5,
            xanchor="center",
            y=-0.04,
            yanchor="top",
            thickness=12,
            len=0.85,
            title=dict(text=metric_label, side="top"),
            **colorbar_ticks,
        ),
        mapbox_accesstoken=mapbox_token,
    )
    return fig
