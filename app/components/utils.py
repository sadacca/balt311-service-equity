import numpy as np
import pandas as pd

from components.theme import SCORE_AMBER, SCORE_GRAY, SCORE_GREEN, SCORE_RED

# overlap_score / wmean live in balt311.equity_stats so the cross-city equity pipeline
# (Phase 5.5-3) scores cities with the exact same implementation as the within-Baltimore
# tabs; re-exported here so existing `from components.utils import overlap_score` call
# sites are unchanged.
from balt311.equity_stats import overlap_score, wmean  # noqa: F401


def score_label(score: float) -> tuple[str, str]:
    """Return (text label, color) for a probability-of-superiority equity score.

    The color is a shared design token (hex), used both for HTML badges and Plotly fills.
    """
    if np.isnan(score):
        return "insufficient data", SCORE_GRAY
    if score > 0.7:
        return "not bad", SCORE_GREEN
    if score > 0.4:
        return "could be better", SCORE_AMBER
    return "needs review", SCORE_RED


def format_metric(val: float, metric_col: str) -> str:
    """Format a metric value for display (percentage or decimal)."""
    if metric_col in ("closure_rate", "on_time_rate"):
        return f"{val:.1%}"
    return f"{val:.1f}"


def hex_to_rgba(hex_color: str, alpha: float) -> str:
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"rgba({r},{g},{b},{alpha})"
