import numpy as np
import pandas as pd


def overlap_score(a: pd.Series, b: pd.Series) -> float:
    """Median ratio equity score: min(median_a, median_b) / max(median_a, median_b).

    Returns 1.0 when both groups have identical medians; lower values indicate
    a larger gap. Returns NaN if either group has fewer than 3 non-null values
    or both medians are zero.
    """
    a, b = a.dropna(), b.dropna()
    if len(a) < 3 or len(b) < 3:
        return float("nan")
    med_a, med_b = np.median(a), np.median(b)
    denom = max(med_a, med_b)
    if denom == 0:
        return 1.0
    return min(med_a, med_b) / denom


def score_label(score: float) -> tuple[str, str]:
    """Return (text label, CSS color) for a median ratio equity score."""
    if np.isnan(score):
        return "insufficient data", "gray"
    if score > 0.85:
        return "not bad", "green"
    if score > 0.65:
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
