import json
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go


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
) -> go.Figure:
    citywide_median = df[metric_col].median()

    fig = px.choropleth_mapbox(
        df,
        geojson=geojson,
        locations=geo_id_col,
        featureidkey=featureidkey,
        color=metric_col,
        color_continuous_scale="RdBu_r",
        color_continuous_midpoint=citywide_median,
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
        coloraxis_colorbar=dict(
            orientation="h",
            x=0.5,
            xanchor="center",
            y=-0.04,
            yanchor="top",
            thickness=12,
            len=0.85,
            title=dict(text=metric_label, side="top"),
        ),
        mapbox_accesstoken=mapbox_token,
    )
    return fig
