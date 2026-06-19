"""Central design tokens — the single source of truth for the dashboard's visual layer.

Every component imports colors, the shared Plotly layout, and status-notice helpers from
here, so the look is defined once. Before this module the same hexes were re-declared in
8 files (the dark blue `#1F4E8C` in five of them) and the chart chrome — white background,
`#eeeeee` gridlines, the horizontal legend — was copy-pasted ~15 times with small drift.

Color identity (deliberately unified — see CLAUDE.md design-consistency pass):
  - ONE focus/brand red (`BRAND`) for "this is the thing to look at": the Baltimore
    reference bar in the cross-city tabs AND the selected-year highlight within Baltimore
    (which used to be a second, near-identical red `#d73027`).
  - ONE analytic blue (`PRIMARY`), which doubles as the income demographic dimension and the
    Streamlit theme `primaryColor` in `.streamlit/config.toml`.
"""
from __future__ import annotations

import streamlit as st

# ── Brand / series colors ─────────────────────────────────────────────────────
BRAND = "#C8102E"      # focus red: cross-city Baltimore reference + selected-year highlight
PRIMARY = "#1F4E8C"    # primary analytic blue (also the Streamlit theme primaryColor)
SECONDARY = "#E07B39"  # secondary series (e.g. citizen-initiated trend)

# Demographic dimensions — shared by every equity chart
RACE = "#8B2020"
INCOME = PRIMARY
DIM_COLORS: dict[str, str] = {"Race": RACE, "Income": INCOME}

# Cross-city series
PEER = "#5f6368"       # peer cities — dark enough for white in-bar labels
MUTED = "#a6a6a6"      # raw / secondary-reference series

# Neutrals
GRID = "#eeeeee"       # axis gridlines
REF_LINE = "#999999"   # dotted reference / vlines / "all other" series
AXIS_LINE = "#333333"  # emphasized reference line (e.g. citywide-average dashed)
MARKER_LINE = "#444444"

# One color per equity metric (the citywide equity-trend lines)
METRIC_COLORS: dict[str, str] = {
    "Median days to close": "#2166ac",
    "Closure rate": BRAND,
    "On-time rate": "#1a9641",
    "Requests per 1,000 residents": "#762a83",
}

# Qualitative palette for multi-category line charts (Plotly's default 10, named once here)
PALETTE: list[str] = [
    "#636EFA", "#EF553B", "#00CC96", "#AB63FA", "#FFA15A",
    "#19D3F3", "#FF6692", "#B6E880", "#FF97FF", "#FECB52",
]

# Area-embedding quadrant background fills (UL / UR / LL / LR)
QUADRANT_COLORS: dict[str, str] = {
    "UL": "rgba(100, 149, 237, 0.08)",
    "UR": "rgba(60,  179, 113, 0.08)",
    "LL": "rgba(255, 165,   0, 0.08)",
    "LR": "rgba(218, 112, 214, 0.08)",
}

# Equity-score threshold-band colors (match score_label thresholds: >0.7 / >0.4 / ≤0.4).
# Used both for the green/amber/red bands behind score charts and for score_label() text.
SCORE_GREEN = "#1a9641"
SCORE_AMBER = "#E08A1E"
SCORE_RED = "#C8102E"
SCORE_GRAY = "#999999"

# Map / heatmap color scales (the red = worse convention documented in one place)
SEQUENTIAL_SCALE = "Blues"          # volume / counts (low→high)
DIVERGING_WORSE_HIGH = "RdBu_r"     # higher value is worse (e.g. days to close): red at top
DIVERGING_BETTER_HIGH = "RdBu"      # higher value is better (e.g. closure rate): red at bottom
EMBEDDING_SCALE = "Viridis"         # area-embedding continuous color
MATURITY_SCALE = "RdYlGn"           # 0–3 rubric scores

# ── Typography ─────────────────────────────────────────────────────────────────
FONT_FAMILY = "Source Sans Pro, sans-serif"  # matches the Streamlit theme font
FONT_SIZE = 12
LEGEND_FONT_SIZE = 11

# ── Plotly chart chrome ──────────────────────────────────────────────────────────
# Disable the Plotly modebar everywhere so no stray toolbar appears on hover.
CHART_CONFIG: dict = {"displayModeBar": False}

# The standard horizontal legend, anchored above the plot, left-aligned.
LEGEND_H: dict = {
    "orientation": "h", "yanchor": "bottom", "y": 1.02, "xanchor": "left", "x": 0,
    "font": {"size": LEGEND_FONT_SIZE}, "bgcolor": "rgba(0,0,0,0)",
}


def base_layout(**overrides) -> dict:
    """Common Plotly layout (white background, app font); merge per-chart keys via overrides.

    Usage: ``fig.update_layout(**base_layout(height=240, margin={...}, yaxis={...}))``.
    Axes that show gridlines should set ``gridcolor=theme.GRID``; charts with a legend should
    pass ``legend=theme.LEGEND_H``.
    """
    layout = {
        "plot_bgcolor": "white",
        "paper_bgcolor": "white",
        "font": {"family": FONT_FAMILY, "size": FONT_SIZE},
    }
    layout.update(overrides)
    return layout


# ── Status notices ───────────────────────────────────────────────────────────────
def notice_pending(msg: str) -> None:
    """A dataset that a workflow/pipeline run will produce isn't present yet."""
    st.info(msg, icon="🚧")


def notice_unavailable(msg: str) -> None:
    """Data is missing for the current selection (no construction action implied)."""
    st.info(msg)
