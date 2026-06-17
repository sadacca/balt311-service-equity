import numpy as np
import pandas as pd

# overlap_score / wmean live in balt311.equity_stats so the cross-city equity pipeline
# (Phase 5.5-3) scores cities with the exact same implementation as the within-Baltimore
# tabs; re-exported here so existing `from components.utils import overlap_score` call
# sites are unchanged.
from balt311.equity_stats import overlap_score, wmean  # noqa: F401


def score_label(score: float) -> tuple[str, str]:
    """Return (text label, CSS color) for a probability-of-superiority equity score."""
    if np.isnan(score):
        return "insufficient data", "gray"
    if score > 0.7:
        return "not bad", "green"
    if score > 0.4:
        return "could be better", "orange"
    return "needs review", "red"


def format_metric(val: float, metric_col: str) -> str:
    """Format a metric value for display (percentage or decimal)."""
    if metric_col in ("closure_rate", "on_time_rate"):
        return f"{val:.1%}"
    return f"{val:.1f}"


def hex_to_rgba(hex_color: str, alpha: float) -> str:
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"rgba({r},{g},{b},{alpha})"
