import numpy as np
import pandas as pd


def overlap_score(a: pd.Series, b: pd.Series) -> float:
    """Mann-Whitney probability-of-superiority equity score.

    Computes P(a > b) across all pairwise comparisons (ties split 0.5).
    Maps to an equity score: 0.5 → 1.0 (perfectly interleaved groups),
    0 or 1 → 0.0 (one group entirely above the other).

    Formula: score = 1 - 2 * |P(a > b) - 0.5|

    Sensitive to the full distribution, not just the median, so it detects
    tail differences and systematic shifts even when medians are close.
    Returns NaN if either group has fewer than 3 non-null values.
    """
    a, b = a.dropna().to_numpy(), b.dropna().to_numpy()
    if len(a) < 3 or len(b) < 3:
        return float("nan")
    # All pairwise comparisons: a[:, None] vs b[None, :]
    diff = a[:, None] - b[None, :]
    a_wins = np.sum(diff > 0)
    ties   = np.sum(diff == 0)
    p_sup  = (a_wins + 0.5 * ties) / (len(a) * len(b))
    return 1.0 - 2.0 * abs(p_sup - 0.5)


def score_label(score: float) -> tuple[str, str]:
    """Return (text label, CSS color) for a probability-of-superiority equity score."""
    if np.isnan(score):
        return "insufficient data", "gray"
    if score > 0.7:
        return "not bad", "green"
    if score > 0.4:
        return "could be better", "orange"
    return "needs review", "red"


def wmean(df: pd.DataFrame, value_col: str, weight_col: str = "total_requests") -> float:
    """Volume-weighted mean — the convention this dashboard uses everywhere it
    needs to combine a rate metric (closure rate, median days) across SRTypes
    or geographies: sum(value*weight) / sum(weight)."""
    sub = df.dropna(subset=[value_col, weight_col])
    sub = sub[sub[weight_col] > 0]
    if sub.empty:
        return float("nan")
    return float((sub[value_col] * sub[weight_col]).sum() / sub[weight_col].sum())


def format_metric(val: float, metric_col: str) -> str:
    """Format a metric value for display (percentage or decimal)."""
    if metric_col in ("closure_rate", "on_time_rate"):
        return f"{val:.1%}"
    return f"{val:.1f}"


def hex_to_rgba(hex_color: str, alpha: float) -> str:
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"rgba({r},{g},{b},{alpha})"
