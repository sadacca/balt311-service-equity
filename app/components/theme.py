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

# Surface palette — Stripe-style near-monochrome cool grays for the app chrome (cards,
# borders, ink). Kept distinct from the data-series colors above so chart identity is
# untouched. Mirrored into CSS custom properties by inject_global_css() — keep in sync.
CANVAS = "#FFFFFF"     # page background
SURFACE = "#F6F9FC"    # card / secondary background
BORDER = "#E3E8EF"     # hairline border
INK = "#0A2540"        # primary text (deep navy)
MUTED_INK = "#525F7F"  # secondary text

# Hero gradient halo — a single decorative gradient used once behind the header (Phase 2),
# never behind content. Kept to three stops per Stripe's gradient discipline.
HALO = ("#1F4E8C", "#3A6FB0", "#C8102E")

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
FONT_FAMILY = "Inter, Source Sans Pro, sans-serif"  # Inter (loaded by inject_global_css), system fallback
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
    # Unified tooltip styling matching the app's card look — applied unless a caller
    # overrode it. setdefault so per-chart hoverlabel overrides still win.
    layout.setdefault("hoverlabel", {
        "bgcolor": "white",
        "bordercolor": BORDER,
        "font": {"family": FONT_FAMILY, "size": FONT_SIZE, "color": INK},
    })
    return layout


# ── Status notices ───────────────────────────────────────────────────────────────
def notice_pending(msg: str) -> None:
    """A dataset that a workflow/pipeline run will produce isn't present yet."""
    st.info(msg, icon="🚧")


def notice_unavailable(msg: str) -> None:
    """Data is missing for the current selection (no construction action implied)."""
    st.info(msg)


# ── Global CSS (clean-light polish layer) ─────────────────────────────────────────
# A single static <style> block injected once from app.py (right after set_page_config).
# It loads Inter and restyles Streamlit's chrome — cards, headings, pill nav, tabs — into
# the Stripe / Google-Health clean-light look. No JS, no animation beyond cheap CSS hover
# transitions, so it adds no per-rerun cost. The CSS custom properties below mirror the
# Python color tokens above; keep the two in sync.
_GLOBAL_CSS = f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

:root {{
    --primary: {PRIMARY};
    --brand: {BRAND};
    --ink: {INK};
    --muted-ink: {MUTED_INK};
    --surface: {SURFACE};
    --border: {BORDER};
}}

/* Inter across the whole Streamlit DOM so widget/markdown text matches the charts. */
html, body, [class*="css"], button, input, textarea, select {{
    font-family: 'Inter', 'Source Sans Pro', sans-serif !important;
}}

/* Trim Streamlit's tall default top padding for a tighter, more designed header. */
.block-container {{ padding-top: 2.2rem; }}

/* Headings — tight tracking + deep-navy ink (Stripe restraint). */
h1, h2, h3 {{ color: var(--ink); letter-spacing: -0.02em; }}
h1 {{ font-weight: 700; }}
h2, h3 {{ font-weight: 600; }}

/* Cards — st.metric and bordered containers get a soft rounded surface
   (Google-Health calm cards: hairline border + barely-there shadow). */
[data-testid="stMetric"],
[data-testid="stVerticalBlockBorderWrapper"] {{
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 0.9rem 1.1rem;
    box-shadow: 0 1px 2px rgba(10,37,64,.04), 0 1px 3px rgba(10,37,64,.06);
}}
/* Airy metric value weight. */
[data-testid="stMetricValue"] {{ font-weight: 600; color: var(--ink); }}
[data-testid="stMetricLabel"] {{ color: var(--muted-ink); }}

/* Segmented control + horizontal radios → modern rounded pill nav. */
[data-testid="stSegmentedControl"] button,
div[role="radiogroup"] label {{
    border-radius: 999px !important;
    transition: background .15s ease, color .15s ease;
}}

/* Tab strip — lighter, with a clean primary active indicator. */
[data-testid="stTabs"] [data-baseweb="tab-list"] {{ gap: 0.4rem; }}
[data-testid="stTabs"] [data-baseweb="tab"] {{
    padding: 0.4rem 0.85rem;
    color: var(--muted-ink);
}}
[data-testid="stTabs"] [aria-selected="true"] {{ color: var(--ink); font-weight: 600; }}
[data-testid="stTabs"] [data-baseweb="tab-highlight"] {{ background: var(--primary); }}

/* Sidebar — calm surface tone. */
[data-testid="stSidebar"] {{ background: var(--surface); }}

/* Soften dividers and expanders. */
hr {{ border-color: var(--border); }}
[data-testid="stExpander"] {{ border-radius: 10px; border-color: var(--border); }}
</style>
"""


def inject_global_css() -> None:
    """Inject the clean-light polish CSS once. Call right after st.set_page_config."""
    st.markdown(_GLOBAL_CSS, unsafe_allow_html=True)


def hero_banner(title: str, tagline: str) -> str:
    """Return the header hero markup — title + tagline over a single soft gradient halo.

    The halo (the HALO token) is the app's one decorative gradient, sat *behind the
    title only* per Stripe's discipline — a blurred radial glow, not a content
    background. Pure CSS, no image/canvas/animation. Render with
    ``st.markdown(theme.hero_banner(...), unsafe_allow_html=True)``.
    """
    c0, c1, c2 = HALO
    halo = (
        f"radial-gradient(closest-side, {_rgba(c0, 0.18)}, {_rgba(c1, 0.10)}, "
        f"{_rgba(c2, 0.06)}, transparent 80%)"
    )
    return f"""
<div style="position:relative; padding:0.4rem 0 0.8rem 0; margin-bottom:0.4rem;">
  <div style="position:absolute; top:-44px; left:-64px; width:420px; height:170px;
       background:{halo}; filter:blur(20px); z-index:0; pointer-events:none;"></div>
  <div style="position:relative; z-index:1;">
    <h1 style="margin:0; font-size:2.1rem;">{title}</h1>
    <p style="margin:0.3rem 0 0; color:{MUTED_INK}; font-size:1.02rem; max-width:660px;">
      {tagline}
    </p>
  </div>
</div>
"""


def _rgba(hex_color: str, alpha: float) -> str:
    """'#RRGGBB' + alpha -> 'rgba(r, g, b, a)' for the hero halo gradient stops."""
    h = hex_color.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    return f"rgba({r}, {g}, {b}, {alpha})"
