import numpy as np
import pandas as pd


def overlap_score(a: pd.Series, b: pd.Series) -> float:
    """Distribution overlap fraction between two series (0 = no overlap, 1 = complete overlap).

    Computes the fraction of the combined 10th–90th percentile span that the two
    bands share. Wider than IQR (80% of data vs 50%) to avoid over-penalising
    modest median separation when distributions are otherwise similar.
    Returns NaN if either group has fewer than 3 non-null values.
    """
    a, b = a.dropna(), b.dropna()
    if len(a) < 3 or len(b) < 3:
        return float("nan")
    q10_a, q90_a = np.percentile(a, [10, 90])
    q10_b, q90_b = np.percentile(b, [10, 90])
    overlap = max(0.0, min(q90_a, q90_b) - max(q10_a, q10_b))
    span = max(q90_a, q90_b) - min(q10_a, q10_b)
    return overlap / span if span > 0 else 1.0


def score_label(score: float) -> tuple[str, str]:
    """Return (text label, CSS color) for a distribution overlap score."""
    if np.isnan(score):
        return "insufficient data", "gray"
    if score > 0.6:
        return "not bad", "green"
    if score > 0.3:
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
