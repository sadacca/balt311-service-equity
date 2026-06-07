"""Service Category Equity Explorer — Tab 5.

The equity-flavored mirror of Tab 2 (Service Category Explorer): the same chart
language — multi-line trends, top-N + "all other" subtype folding, the shared
category selector, dotted-year guide, dashed citywide reference — but the plotted
metric is the Mann-Whitney equity score (race and income) rather than an
operational one. Answers whether the citywide equity picture (the Equity tab)
holds up — or differs — among and within individual service categories, and how
that picture has moved over time.
"""
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from components.equity_trend import compute_citywide_equity_trend
from components.srtype_shared import (
    CATEGORY_NAMES,
    MIN_GEO_SRTYPE_N,
    category_selector,
    extract_categories,
    load_geo_srtype_history,
)
from components.utils import overlap_score, score_label

# Metrics available at geo×SRType grain — on_time_rate and requests_per_1k require
# fields (DueDate, population) that aren't rolled up to this grain.
_METRIC_OPTIONS = {
    "Median days to close": "median_days_to_close",
    "Closure rate": "closure_rate",
}

_TOP_CATEGORIES_N = 8
_TOP_SUBTYPES_N = 7
_CONCERN_TOP_N = 8

# Minimum-data eligibility thresholds for the "most concerning service types" ranking —
# a low score is only meaningful if it's backed by enough geographic spread, volume,
# and historical depth to trust; otherwise a thin sample could just be noise.
_CONCERN_MIN_GEO_COVERAGE = 0.5
_CONCERN_MIN_REQUESTS_PER_YEAR = 250
_CONCERN_MIN_YEARS = 5

# Race / income trend-line colors — match the group colors `equity_distributions.py`
# already established, so the same dimension reads consistently across both tabs.
_DIM_COLORS = {"Race": "#8B2020", "Income": "#1F4E8C"}

# Cycled through for the among-category trend lines — same palette Tab 2 uses.
_PALETTE = [
    "#636EFA", "#EF553B", "#00CC96", "#AB63FA", "#FFA15A",
    "#19D3F3", "#FF6692", "#B6E880", "#FF97FF", "#FECB52",
]


def _short_label(srtype: str) -> str:
    """Drop the redundant category prefix from a legend label (e.g. 'SW-Dirty Alley' -> 'Dirty Alley')."""
    return srtype.split("-", 1)[1].strip() if "-" in srtype else srtype


def _add_score_bands(fig: go.Figure) -> None:
    """Green/amber/red overlap-score threshold bands, drawn behind the data —
    same convention and thresholds as `equity_trend.py`'s citywide trend chart."""
    fig.add_hrect(y0=0.7, y1=1.0, fillcolor="green",  opacity=0.06, line_width=0)
    fig.add_hrect(y0=0.4, y1=0.7, fillcolor="orange", opacity=0.06, line_width=0)
    fig.add_hrect(y0=0.0, y1=0.4, fillcolor="red",    opacity=0.06, line_width=0)


def _score_layout_kwargs(height: int) -> dict:
    """Shared layout for every equity-score line chart on this tab — fixed [0,1]
    axis (scores are bounded, unlike operational metrics) and percent formatting."""
    return dict(
        height=height,
        margin={"t": 8, "b": 8, "l": 55, "r": 8},
        xaxis=dict(title="Year", dtick=1),
        yaxis=dict(title="Equity score", range=[0, 1], tickformat=".0%", gridcolor="#eeeeee"),
        plot_bgcolor="white",
        paper_bgcolor="white",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0, font=dict(size=10), bgcolor="rgba(0,0,0,0)"),
    )


# ── Score computation ─────────────────────────────────────────────────────────
#
# All three helpers below share one shape: suppress sparse (geo, SRType) cells via
# `MIN_GEO_SRTYPE_N` (the same threshold Operations applies before mapping geo×SRType
# data), join to demographics, split into majority-Black/White and below/above-
# median-income groups, and score each split with `overlap_score()` — exactly the
# computation `equity_trend.py` already performs citywide, just re-scoped to a
# category or subtype slice for each year independently.

def _dimension_scores(valid: pd.DataFrame, metric_col: str) -> dict[str, float]:
    """Race and income overlap scores for one demographics-merged, metric-valid slice."""
    race_valid = valid.dropna(subset=["pct_black", "pct_white"])
    black = race_valid[race_valid["pct_black"] > 0.5][metric_col]
    white = race_valid[race_valid["pct_white"] > 0.5][metric_col]

    inc_valid = valid.dropna(subset=["median_income"])
    city_med = inc_valid["median_income"].median()
    below = inc_valid[inc_valid["median_income"] <= city_med][metric_col]
    above = inc_valid[inc_valid["median_income"] > city_med][metric_col]

    return {
        "Race": overlap_score(black, white),
        "Income": overlap_score(below, above),
    }


def _rollup_to_groups(rows: pd.DataFrame, group_col: str, metric_col: str) -> pd.DataFrame:
    """One row per (geoid, group, year): suppressed SRType cells volume-weighted up
    to a caller-defined grouping — used to give a category, or a category's
    lower-volume remainder, one comparable value per geography per year, mirroring
    `_category_aggregates`'s citywide rollup but at the per-geography grain that an
    equity comparison (which compares geographies, not raw request counts) needs.

    Vectorized groupby-agg rather than a per-group `wmean()` loop — at (geoid ×
    category × year) grain this can be tens of thousands of groups, and the
    Python-level loop was the dominant cost of the equity-score computation
    (~40s vs. ~0.05s for an equivalent dataset — a ~1000x difference for
    identical output)."""
    sub = rows.dropna(subset=[metric_col, "total_requests"])
    sub = sub[sub["total_requests"] > 0]
    if sub.empty:
        return pd.DataFrame(columns=["geoid", group_col, "year", metric_col, "total_requests"])
    sub = sub.assign(_weighted=sub[metric_col].to_numpy() * sub["total_requests"].to_numpy())
    out = (
        sub.groupby(["geoid", group_col, "year"], as_index=False)
        .agg(_weighted=("_weighted", "sum"), total_requests=("total_requests", "sum"))
    )
    out[metric_col] = out["_weighted"] / out["total_requests"]
    return out[["geoid", group_col, "year", metric_col, "total_requests"]]


@st.cache_data
def compute_category_equity_history(
    data_dir: Path,
    geo_key: str,
    demographics: pd.DataFrame,
    categories: tuple[str, ...],
    metric_col: str,
) -> pd.DataFrame:
    """Long DataFrame (_cat, year, dimension, score) — one row per (category, year, Race|Income).

    Rolls each category's suppressed SRType cells up to one volume-weighted value per
    geography (so every category is compared on equal footing — geographies, not raw
    SRType rows), then scores the demographic split for that category-year. *(implements
    the (category × year) half of P4-1b)*

    Takes `(data_dir, geo_key)` rather than the assembled history DataFrame directly —
    loading it internally via the already-cached `load_geo_srtype_history` (same pattern
    `compute_citywide_equity_trend` uses for its source parquet files) keeps this
    function's cache key to small, cheap-to-hash primitives. The combined geo×SRType
    history can run several hundred thousand rows across all years; hashing it on every
    Streamlit rerun to check the cache — which happens on *every* widget interaction,
    cache hit or not — adds measurable overhead for no benefit, since `data_dir` and
    `geo_key` already uniquely identify its contents.
    """
    geo_srtype_history = load_geo_srtype_history(data_dir, geo_key)
    work = geo_srtype_history[geo_srtype_history["total_requests"] >= MIN_GEO_SRTYPE_N].copy()
    cat_set = set(categories)
    has_cat = work["SRType"].apply(
        lambda n: isinstance(n, str) and "-" in n and n.split("-")[0].strip() in cat_set
    )
    work = work[has_cat].copy()
    work["_cat"] = work["SRType"].str.split("-").str[0].str.strip()

    rolled = _rollup_to_groups(work, "_cat", metric_col)
    if rolled.empty:
        return pd.DataFrame(columns=["_cat", "year", "dimension", "score"])
    merged = rolled.merge(demographics, on="geoid", how="left")

    records = []
    for (cat, yr), g in merged.groupby(["_cat", "year"]):
        valid = g.dropna(subset=[metric_col])
        for dim, score in _dimension_scores(valid, metric_col).items():
            records.append({"_cat": cat, "year": yr, "dimension": dim, "score": score})
    return pd.DataFrame(records)


@st.cache_data
def compute_subtype_equity_history(
    data_dir: Path,
    geo_key: str,
    demographics: pd.DataFrame,
    category: str,
    top_types: tuple[str, ...],
    other_label: str,
    metric_col: str,
) -> pd.DataFrame:
    """Long DataFrame (label, year, dimension, score) for one category's subtypes —
    the `top_types` individually (each geo×SRType row is already one comparable
    value, no rollup needed) plus their lower-volume remainder folded into one
    `other_label` pseudo-type via the same volume-weighted per-geography rollup
    `compute_category_equity_history` uses. Mirrors Tab 2's `_subtype_multiline_fig`
    top-N + "all other" convention. *(implements the (SRType × year) half of P4-1b)*

    Loads the geo×SRType history internally from `(data_dir, geo_key)` rather than
    taking it as a DataFrame argument — see `compute_category_equity_history` for why.
    """
    geo_srtype_history = load_geo_srtype_history(data_dir, geo_key)
    cat_rows = geo_srtype_history[
        (geo_srtype_history["total_requests"] >= MIN_GEO_SRTYPE_N)
        & geo_srtype_history["SRType"].str.startswith(f"{category}-")
    ]
    if cat_rows.empty:
        return pd.DataFrame(columns=["label", "year", "dimension", "score"])

    records = []

    top_set = set(top_types)
    top_rows = cat_rows[cat_rows["SRType"].isin(top_set)].merge(demographics, on="geoid", how="left")
    for (srtype, yr), g in top_rows.groupby(["SRType", "year"]):
        valid = g.dropna(subset=[metric_col])
        for dim, score in _dimension_scores(valid, metric_col).items():
            records.append({"label": _short_label(srtype), "year": yr, "dimension": dim, "score": score})

    rest = cat_rows[~cat_rows["SRType"].isin(top_set)].copy()
    if not rest.empty:
        rest["_other"] = other_label
        rolled = _rollup_to_groups(rest, "_other", metric_col)
        merged = rolled.merge(demographics, on="geoid", how="left")
        for yr, g in merged.groupby("year"):
            valid = g.dropna(subset=[metric_col])
            for dim, score in _dimension_scores(valid, metric_col).items():
                records.append({"label": other_label, "year": yr, "dimension": dim, "score": score})

    return pd.DataFrame(records)


@st.cache_data
def _subtype_current_year_scores(
    data_dir: Path,
    geo_key: str,
    demographics: pd.DataFrame,
    year: int,
    metric_col: str,
) -> pd.DataFrame:
    """Long (SRType, dimension, score) frame — every individual service type's Race
    and Income equity score for `year`, each computed once from its suppressed
    geo×SRType cells (no rollup needed; each row is already one comparable value).

    Factored out as the shared base for `compute_subtype_score_summary` (citywide
    subtype average, for the opening grain comparison) and `compute_concerning_subtypes`
    (eligibility + ranking, for the closing review section) — both need every
    individual type's current-year score, and previously computed it independently;
    scoring ~150 types × 2 dimensions is the dominant cost in both, so doing it once
    here and letting Streamlit cache the result is a real, not theoretical, saving.

    Loads the geo×SRType history internally from `(data_dir, geo_key)` rather than
    taking it as a DataFrame argument — see `compute_category_equity_history` for why.
    """
    geo_srtype_history = load_geo_srtype_history(data_dir, geo_key)
    rows = geo_srtype_history[
        (geo_srtype_history["year"] == year)
        & (geo_srtype_history["total_requests"] >= MIN_GEO_SRTYPE_N)
    ].merge(demographics, on="geoid", how="left")
    if rows.empty:
        return pd.DataFrame(columns=["SRType", "dimension", "score"])

    records = []
    for srtype, g in rows.groupby("SRType"):
        valid = g.dropna(subset=[metric_col])
        for dim, score in _dimension_scores(valid, metric_col).items():
            records.append({"SRType": srtype, "dimension": dim, "score": score})
    return pd.DataFrame(records)


@st.cache_data
def compute_subtype_score_summary(
    data_dir: Path,
    geo_key: str,
    demographics: pd.DataFrame,
    year: int,
    metric_col: str,
) -> dict[str, float]:
    """Mean Race/Income equity score across every individual SRType in `year` —
    the finest grain scoreable without a category selection — used only for the
    opening summary's overall-vs-category-vs-subtype comparison that shows whether
    scores rise at finer grain (a usage-mix signature) or hold flat (a
    delivery-difference signature)."""
    scores = _subtype_current_year_scores(data_dir, geo_key, demographics, year, metric_col)
    if scores.empty:
        return {"Race": float("nan"), "Income": float("nan")}
    return {
        dim: scores.loc[scores["dimension"] == dim, "score"].dropna().mean()
        for dim in ("Race", "Income")
    }


# ── Figures ───────────────────────────────────────────────────────────────────

def _multi_category_score_fig(
    history: pd.DataFrame,
    cats: list[str],
    dimension: str,
    year: int,
    citywide: pd.DataFrame | None = None,
) -> go.Figure:
    """One equity-score line per category, trended across years — the equity-flavored
    counterpart to Tab 2's `_multi_category_line_fig`: same per-category palette,
    dotted year guide, and dashed "All categories" reference line, but plotted against a
    fixed [0, 1] score axis with green/amber/red threshold bands instead of a
    log-scale operational metric."""
    fig = go.Figure()
    _add_score_bands(fig)
    for i, cat in enumerate(cats):
        d = history[(history["_cat"] == cat) & (history["dimension"] == dimension)]
        d = d.dropna(subset=["score"]).sort_values("year")
        if d.empty:
            continue
        label = CATEGORY_NAMES.get(cat, cat)
        color = _PALETTE[i % len(_PALETTE)]
        fig.add_trace(go.Scatter(
            x=d["year"], y=d["score"],
            mode="lines+markers", name=cat,
            line=dict(width=1.8, color=color),
            marker=dict(size=5, color=color),
            hovertemplate=f"<b>{cat} — {label}</b><br>%{{x}}: %{{y:.0%}}<extra></extra>",
        ))
    if citywide is not None:
        cw = citywide.dropna(subset=["score"]).sort_values("year")
        if not cw.empty:
            fig.add_trace(go.Scatter(
                x=cw["year"], y=cw["score"],
                mode="lines+markers", name="All categories",
                line=dict(width=2.4, dash="dash", color="#333333"),
                marker=dict(size=7, color="#333333", symbol="diamond"),
                hovertemplate="<b>All categories</b><br>%{x}: %{y:.0%}<extra></extra>",
            ))
    fig.add_vline(x=year, line_width=1, line_dash="dot", line_color="#999999")
    fig.update_layout(**_score_layout_kwargs(320))
    return fig


def _category_score_trend_fig(
    d: pd.DataFrame,
    citywide: pd.DataFrame,
    dimension: str,
    year: int,
) -> go.Figure:
    """One category's own equity-score trend, selected year picked out in red —
    mirrors Tab 2's `_line_fig` highlight convention — with the all-categories trend
    for the same metric and dimension overlaid as a dashed reference, exactly as
    Tab 2 overlays the citywide operational average on its rate/speed panels."""
    fig = go.Figure()
    _add_score_bands(fig)

    valid = d.dropna(subset=["score"]).sort_values("year")
    color = _DIM_COLORS[dimension]
    fig.add_trace(go.Scatter(
        x=valid["year"], y=valid["score"],
        mode="lines+markers", name=dimension,
        line=dict(color=color, width=2),
        marker=dict(
            size=[11 if y == year else 7 for y in valid["year"]],
            color=["#d73027" if y == year else color for y in valid["year"]],
        ),
        hovertemplate="%{x}: %{y:.0%}<extra>" + dimension + "</extra>",
    ))

    cw = citywide.dropna(subset=["score"]).sort_values("year")
    if not cw.empty:
        fig.add_trace(go.Scatter(
            x=cw["year"], y=cw["score"],
            mode="lines+markers", name="All categories",
            line=dict(width=2, dash="dash", color="#333333"),
            marker=dict(size=6, color="#333333", symbol="diamond"),
            hovertemplate="<b>All categories</b><br>%{x}: %{y:.0%}<extra></extra>",
        ))

    fig.update_layout(**_score_layout_kwargs(260))
    return fig


def _subtype_score_multiline_fig(
    history: pd.DataFrame,
    labels: list[str],
    other_label: str,
    dimension: str,
) -> go.Figure:
    """One equity-score line per subcategory across years, plus the "all other types"
    aggregate — the equity-flavored counterpart to Tab 2's `_subtype_multiline_fig`:
    identical top-N + dotted-gray-aggregate convention, scored instead of measured."""
    fig = go.Figure()
    _add_score_bands(fig)

    sub = history[history["dimension"] == dimension]
    for label in labels:
        d = sub[sub["label"] == label].dropna(subset=["score"]).sort_values("year")
        if d.empty:
            continue
        fig.add_trace(go.Scatter(
            x=d["year"], y=d["score"],
            mode="lines+markers", name=label,
            line=dict(width=1.8), marker=dict(size=5),
            hovertemplate=f"<b>{label}</b><br>%{{x}}: %{{y:.0%}}<extra></extra>",
        ))

    other = sub[sub["label"] == other_label].dropna(subset=["score"]).sort_values("year")
    if not other.empty:
        fig.add_trace(go.Scatter(
            x=other["year"], y=other["score"],
            mode="lines+markers", name=other_label,
            line=dict(width=2, dash="dot", color="#999999"),
            marker=dict(size=5, color="#999999"),
            hovertemplate=f"<b>{other_label}</b><br>%{{x}}: %{{y:.0%}}<extra></extra>",
        ))

    fig.update_layout(**_score_layout_kwargs(340))
    return fig


_GRAIN_LABELS = ["All categories<br>(citywide)", "Within<br>category", "Within<br>service type"]


def _grain_comparison_fig(scores: list[float], dimension: str) -> go.Figure:
    """Three bars — citywide, within-category, within-service-type equity scores for
    one dimension — colored by `score_label()`'s green/amber/red/gray convention so
    the rising-at-finer-grain pattern (the usage-mix signature) reads at a glance,
    in place of the sentence that used to spell out the same three numbers."""
    colors = [score_label(v)[1] for v in scores]
    fig = go.Figure(go.Bar(
        x=_GRAIN_LABELS, y=scores,
        marker_color=colors,
        text=[f"{v:.0%}" for v in scores], textposition="outside",
        hovertemplate="<b>%{x}</b><br>%{y:.0%}<extra></extra>",
        width=0.55,
    ))
    fig.add_hrect(y0=0.7, y1=1.16, fillcolor="green",  opacity=0.05, line_width=0)
    fig.add_hrect(y0=0.4, y1=0.7,  fillcolor="orange", opacity=0.05, line_width=0)
    fig.add_hrect(y0=0.0, y1=0.4,  fillcolor="red",    opacity=0.05, line_width=0)
    fig.update_layout(
        height=260,
        margin={"t": 8, "b": 8, "l": 50, "r": 8},
        yaxis=dict(title="Equity score", range=[0, 1.16], tickformat=".0%", gridcolor="#eeeeee"),
        xaxis=dict(title=None),
        plot_bgcolor="white", paper_bgcolor="white",
        showlegend=False,
    )
    return fig


_CONCERN_BINS = dict(start=0.0, end=1.0, size=0.05)


def _concern_distribution_fig(eligible_scores: list[float], concern_scores: list[float], dimension: str) -> go.Figure:
    """Histogram of every eligible service type's current-year **{dimension}** equity
    score (gray), with the flagged-for-review subset overlaid in red on identical
    bins — shows whether the most concerning types are a distinct, separated tail or
    just the bottom edge of one continuous distribution."""
    fig = go.Figure()
    fig.add_vrect(x0=0.7, x1=1.0, fillcolor="green",  opacity=0.05, line_width=0)
    fig.add_vrect(x0=0.4, x1=0.7, fillcolor="orange", opacity=0.05, line_width=0)
    fig.add_vrect(x0=0.0, x1=0.4, fillcolor="red",    opacity=0.05, line_width=0)
    fig.add_trace(go.Histogram(
        x=eligible_scores, xbins=_CONCERN_BINS, name="All eligible types",
        marker_color="#999999", opacity=0.65,
        hovertemplate="%{x}<br>%{y} type(s)<extra>All eligible types</extra>",
    ))
    fig.add_trace(go.Histogram(
        x=concern_scores, xbins=_CONCERN_BINS, name="Flagged for review",
        marker_color="#d73027", opacity=0.85,
        hovertemplate="%{x}<br>%{y} type(s)<extra>Flagged for review</extra>",
    ))
    fig.update_layout(
        height=240,
        barmode="overlay",
        margin={"t": 8, "b": 8, "l": 50, "r": 8},
        xaxis=dict(title=f"{dimension}-based equity score", range=[0, 1], tickformat=".0%"),
        yaxis=dict(title="Number of service types", gridcolor="#eeeeee"),
        plot_bgcolor="white", paper_bgcolor="white",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0, font=dict(size=10), bgcolor="rgba(0,0,0,0)"),
    )
    return fig


# ── Concerning-subtype ranking ────────────────────────────────────────────────

@st.cache_data
def compute_concerning_subtypes(
    data_dir: Path,
    geo_key: str,
    demographics: pd.DataFrame,
    metric_col: str,
    year: int,
    dimension: str,
    top_n: int,
) -> tuple[pd.DataFrame, list[str], list[float], list[float]]:
    """The `top_n` individual service types most in need of equity review this year
    *on `dimension` specifically*, restricted to types that meet minimum data
    standards — enough geographic spread, volume, and historical depth that a low
    score reflects a real pattern rather than a thin sample:

    - present in at least `_CONCERN_MIN_GEO_COVERAGE` of this year's scoreable geographies
    - at least `_CONCERN_MIN_REQUESTS_PER_YEAR` total requests in `year`
    - scoreable (post-suppression) in at least `_CONCERN_MIN_YEARS` years

    The eligibility filter is applied first, to the full set of individual service
    types — *then* the worst `top_n` (by `dimension` `year` score, ascending) are
    picked from that eligible set, so a thin or noisy sample can never crowd out a
    type with a real, well-supported low score. Ranking by the *displayed* dimension
    (rather than a worse-of-{Race, Income} composite) guarantees the flagged set is
    internally consistent with whichever histogram is shown — a flagged type's score
    on `dimension` is, by construction, among the worst — at the cost of the flagged
    set itself changing when the reader toggles dimensions, which is the more
    intuitive reading anyway ("show me the worst types by Race" vs. "by Income").

    Returns `(history, ranked_labels, eligible_scores, concern_scores)`:
    - `history`: long (label, year, dimension, score) frame for the ranked types,
      ready for `_subtype_score_multiline_fig`
    - `ranked_labels`: the `top_n` labels, worst-on-`dimension` first
    - `eligible_scores`: every eligible type's `year` score on `dimension` — the
      full distribution the ranked types are drawn from
    - `concern_scores`: same, but scoped to just the ranked types
    """
    empty = (pd.DataFrame(columns=["label", "year", "dimension", "score"]), [], [], [])
    geo_srtype_history = load_geo_srtype_history(data_dir, geo_key)
    if geo_srtype_history.empty:
        return empty

    suppressed = geo_srtype_history[geo_srtype_history["total_requests"] >= MIN_GEO_SRTYPE_N]
    year_rows = suppressed[suppressed["year"] == year]
    if year_rows.empty:
        return empty

    n_geos_this_year = year_rows["geoid"].nunique()
    if n_geos_this_year == 0:
        return empty

    geo_coverage = year_rows.groupby("SRType")["geoid"].nunique() / n_geos_this_year
    raw_volume = geo_srtype_history.loc[
        geo_srtype_history["year"] == year
    ].groupby("SRType")["total_requests"].sum()
    years_scoreable = suppressed.groupby("SRType")["year"].nunique()

    eligible = sorted(
        s for s in geo_coverage.index
        if geo_coverage.get(s, 0) >= _CONCERN_MIN_GEO_COVERAGE
        and raw_volume.get(s, 0) >= _CONCERN_MIN_REQUESTS_PER_YEAR
        and years_scoreable.get(s, 0) >= _CONCERN_MIN_YEARS
    )
    if not eligible:
        return empty

    current = _subtype_current_year_scores(data_dir, geo_key, demographics, year, metric_col)
    dim_scores = current[
        (current["dimension"] == dimension)
        & current["SRType"].isin(eligible)
        & current["score"].notna()
    ].sort_values("score")
    if dim_scores.empty:
        return empty

    ranked = dim_scores.head(top_n)
    ranked_types = ranked["SRType"].tolist()

    records = []
    hist_rows = suppressed[suppressed["SRType"].isin(ranked_types)].merge(demographics, on="geoid", how="left")
    for (srtype, yr), g in hist_rows.groupby(["SRType", "year"]):
        valid = g.dropna(subset=[metric_col])
        for dim, score in _dimension_scores(valid, metric_col).items():
            records.append({
                "label": f"{_short_label(srtype)} ({srtype.split('-')[0].strip()})",
                "year": yr, "dimension": dim, "score": score,
            })
    history = pd.DataFrame(records)
    ranked_labels = [f"{_short_label(s)} ({s.split('-')[0].strip()})" for s in ranked_types]

    eligible_scores = dim_scores["score"].tolist()
    concern_scores = ranked["score"].tolist()
    return history, ranked_labels, eligible_scores, concern_scores


# ── Render ────────────────────────────────────────────────────────────────────

def render_category_equity_explorer(
    data_dir: Path,
    demographics: pd.DataFrame | None,
    geo_key: str,
    year: int,
) -> None:
    st.caption("Does the citywide equity picture hold up or differ within individual service categories and types?")
    with st.expander("What to look for"):
        st.markdown(
            "- Does the equity gap shrink when you look within individual service types "
            "rather than citywide? The opening bar chart shows scores at three levels of detail.\n"
            "- If scores rise from left to right on that chart, it suggests the gap is partly "
            "about *which* services neighborhoods request, not just how quickly they're delivered.\n"
            "- Are there specific service types where the racial or income gap is especially large?"
        )

    if demographics is None or demographics.empty:
        st.caption(
            "Demographic data unavailable — "
            f"`{geo_key}_demographics.csv` not found in `data/processed/`. "
            "Re-run the pipeline to generate it."
        )
        return

    srtype_path = data_dir / f"srtype_metrics_{year}.parquet"
    if not srtype_path.exists():
        st.caption(
            "SRType performance data unavailable for this year — run "
            "`pipeline.py --stage srtype --year <year>` to generate it."
        )
        return
    sr_all = pd.read_parquet(srtype_path)

    geo_srtype_history = load_geo_srtype_history(data_dir, geo_key)
    if geo_srtype_history.empty:
        st.caption(
            "Geo × SRType data unavailable — run "
            "`pipeline.py --stage srtype --year <year>` to generate it."
        )
        return

    categories = extract_categories(sr_all)
    if not categories:
        st.caption("No categorized SRType data found for this year.")
        return

    # Rank categories by current-year volume — the same ordering Tab 2 uses for its
    # "top categories", so the set a reader recognizes from Tab 2 carries over here.
    has_prefix = sr_all["SRType"].apply(
        lambda n: isinstance(n, str) and "-" in n and n.split("-")[0].strip() in set(categories)
    )
    by_volume = sr_all[has_prefix].copy()
    by_volume["_cat"] = by_volume["SRType"].str.split("-").str[0].str.strip()
    ranked = by_volume.groupby("_cat")["total_requests"].sum().sort_values(ascending=False).index.tolist()
    top_cats = ranked[:_TOP_CATEGORIES_N]

    # ── Geographic unit + metric selectors ────────────────────────────────────
    # Tract and CSA rollups often diverge on these scores (CSA values are
    # population-weighted means of their member tracts) — exposing the same
    # toggle the Equity tab uses lets a reader check whether a finding holds at
    # both grains or is an artifact of one. Updates the shared `geo_level` state,
    # so the choice carries over to the Equity tab too — same convention.
    ctrl_geo, ctrl_metric = st.columns([1, 2])
    with ctrl_geo:
        _curr_geo = st.session_state.get("geo_level", "Census Tract")
        # Two-way sync with the shared `geo_level`: only overwrite this widget's
        # keyed value when `geo_level` changed *elsewhere* (e.g. the Equity tab's
        # own toggle) — tracked via `_seen` — so a fresh click here isn't clobbered
        # before it has a chance to propagate (Streamlit widgets ignore `index`
        # once their keyed state is set, so a one-way default isn't enough).
        if st.session_state.get("cat_eq_geo_seen") != _curr_geo:
            st.session_state["cat_eq_geo_choice"] = _curr_geo
            st.session_state["cat_eq_geo_seen"] = _curr_geo
        new_geo = st.radio(
            "Geographic unit", ["Census Tract", "CSA"],
            horizontal=True, key="cat_eq_geo_choice",
        )
        if new_geo != _curr_geo:
            st.session_state["geo_level"] = new_geo
            st.session_state["cat_eq_geo_seen"] = new_geo
            st.rerun()
    with ctrl_metric:
        metric_label = st.radio(
            "Equity metric", list(_METRIC_OPTIONS.keys()),
            horizontal=True, key="cat_eq_metric",
        )
    metric_col = _METRIC_OPTIONS[metric_label]

    st.caption(
        f"**{metric_label}** equity score — race (majority-Black vs. majority-White) "
        "and income (below- vs. above-median) geographies. 100% = perfectly "
        "interleaved · >70% not bad · 40–70% could be better · <40% needs review."
    )

    citywide_trend = compute_citywide_equity_trend(data_dir, demographics, geo_key)
    cat_history = compute_category_equity_history(data_dir, geo_key, demographics, tuple(categories), metric_col)
    sub_summary = compute_subtype_score_summary(data_dir, geo_key, demographics, year, metric_col)

    # ── Opening analysis — what this year's scores actually show ──────────────
    overall = {
        dim: citywide_trend.loc[
            (citywide_trend["year"] == year) & (citywide_trend["dimension"] == dim)
            & (citywide_trend["metric"] == metric_label),
            "score",
        ].mean()
        for dim in ("Race", "Income")
    }
    cat_avg = {
        dim: cat_history.loc[(cat_history["year"] == year) & (cat_history["dimension"] == dim), "score"].dropna().mean()
        for dim in ("Race", "Income")
    }
    if all(pd.notna(v) for v in [*overall.values(), *cat_avg.values(), *sub_summary.values()]):
        st.markdown(f"**What {year}'s {metric_label.lower()} scores show, at three grains:**")
        col_race, col_income = st.columns(2)
        with col_race:
            st.caption("Race-based equity score")
            st.plotly_chart(
                _grain_comparison_fig([overall["Race"], cat_avg["Race"], sub_summary["Race"]], "Race"),
                use_container_width=True, key="cat_eq_grain_race", config={"displayModeBar": False},
            )
        with col_income:
            st.caption("Income-based equity score")
            st.plotly_chart(
                _grain_comparison_fig([overall["Income"], cat_avg["Income"], sub_summary["Income"]], "Income"),
                use_container_width=True, key="cat_eq_grain_income", config={"displayModeBar": False},
            )
        st.caption(
            "Scores rising left to right is the signature of a **usage-mix effect**, not "
            "a delivery-difference one — neighborhoods request different *kinds* of "
            "services in different proportions, and that compositional gap, not how any "
            "single service is delivered once requested, drives most of the citywide score."
        )

    # ── Among-category equity trend ───────────────────────────────────────────
    st.subheader("How categories' equity scores compare over time")
    st.caption(
        f"Year-over-year **{metric_label.lower()}** equity score for the "
        f"**{len(top_cats)}** highest-volume categories (same set Tab 2 trends, "
        f"ranked by **{year}** volume) — read each line against the dashed "
        "**all categories** reference and the green/amber/red bands to see whether a "
        "category's equity picture tracks the citywide average, runs persistently "
        "better or worse, or has shifted over the years in this dataset."
    )
    if cat_history.empty:
        st.caption("Not enough geo×SRType coverage to compute category-level equity scores for this metric.")
    else:
        col_race, col_income = st.columns(2)
        with col_race:
            st.markdown("**Race-based equity score**")
            cw_race = citywide_trend[(citywide_trend["dimension"] == "Race") & (citywide_trend["metric"] == metric_label)]
            st.plotly_chart(
                _multi_category_score_fig(cat_history, top_cats, "Race", year, citywide=cw_race),
                use_container_width=True, key="cat_eq_among_race", config={"displayModeBar": False},
            )
        with col_income:
            st.markdown("**Income-based equity score**")
            cw_income = citywide_trend[(citywide_trend["dimension"] == "Income") & (citywide_trend["metric"] == metric_label)]
            st.plotly_chart(
                _multi_category_score_fig(cat_history, top_cats, "Income", year, citywide=cw_income),
                use_container_width=True, key="cat_eq_among_income", config={"displayModeBar": False},
            )

    # ── Where equity review is most warranted ─────────────────────────────────
    # Lives at the level of *individual service types*, not high-level categories —
    # a category can post a "not bad" overall score while one or two of its own
    # subtypes (which can vary widely in where and how fast they're delivered) are
    # the ones actually driving disparity, so this is where review should be aimed.
    st.divider()
    st.subheader("Where equity review is most warranted")
    st.caption(
        "Ranked by individual service type — not high-level category — since a "
        "category can read \"not bad\" overall while one of its own subtypes is the "
        "one actually driving disparity."
    )

    concern_dim = st.radio(
        "Equity dimension", ["Race", "Income"],
        horizontal=True, key="cat_eq_concern_dim",
    )

    concern_history, concern_labels, eligible_scores, concern_scores = compute_concerning_subtypes(
        data_dir, geo_key, demographics, metric_col, year, concern_dim, _CONCERN_TOP_N,
    )
    if not concern_labels:
        st.caption(
            "No individual service type currently meets the minimum-data standards "
            f"below for a reliable concern ranking on **{metric_label.lower()}** "
            f"({concern_dim.lower()})."
        )
    else:
        st.markdown(
            f"These **{len(concern_labels)}** individual service types posted the worst "
            f"current-year **{metric_label.lower()}** **{concern_dim.lower()}**-based "
            "equity — out of every type that meets the minimum data standards below — "
            "the types where review is most warranted, regardless of which category "
            "they belong to."
        )
        st.plotly_chart(
            _concern_distribution_fig(eligible_scores, concern_scores, concern_dim),
            use_container_width=True, key="cat_eq_concern_dist", config={"displayModeBar": False},
        )
        st.caption(
            f"Distribution of every eligible type's **{year}** **{concern_dim.lower()}**-based "
            "equity score — red bars mark where the flagged types fall within the full "
            "picture: a separated tail, or just the lower edge of one continuous spread."
        )
        st.markdown(f"**{concern_dim}-based equity score, year over year**")
        st.plotly_chart(
            _subtype_score_multiline_fig(concern_history, concern_labels, "", concern_dim),
            use_container_width=True, key="cat_eq_concern_line", config={"displayModeBar": False},
        )
        st.caption(
            "Eligible for this ranking: service types present in at least "
            f"**{_CONCERN_MIN_GEO_COVERAGE:.0%}** of this year's scoreable geographies, "
            f"with at least **{_CONCERN_MIN_REQUESTS_PER_YEAR}** requests in {year}, and "
            f"scoreable (post-suppression) in at least **{_CONCERN_MIN_YEARS}** years of "
            "the analysis — applied *before* ranking, so a thin or noisy sample can't "
            "crowd out a type with a real, well-supported low score, and types are "
            f"ranked by their **{concern_dim.lower()}** score specifically, so a flagged "
            "type is guaranteed to actually score low on the dimension shown — not just "
            "on whichever of its two scores happens to be lower. Gaps in the line above "
            "mean a year fell short of the suppression threshold, not zero equity."
        )

    # ── Category selection ────────────────────────────────────────────────────
    st.divider()
    st.subheader("Explore one category's equity picture over time")
    st.caption(
        "The panels above show each category as a single equity-score line — drilling "
        "into one reveals whether its trend tracks the all-categories line by coincidence or "
        "by consistency, and which of its specific service types are driving the score, "
        "for better or worse."
    )
    selected_cat = category_selector(ranked, _TOP_CATEGORIES_N, key="cat_eq_cat") if categories else None

    if not selected_cat:
        st.caption(
            "Select a category above to see its multi-year equity-score trend "
            "and a year-over-year breakdown by subcategory."
        )
        return

    cat_label = CATEGORY_NAMES.get(selected_cat, selected_cat)
    display_name = f"{cat_label} ({selected_cat})" if cat_label != selected_cat else selected_cat

    cat_scope = cat_history[cat_history["_cat"] == selected_cat]
    if cat_scope.dropna(subset=["score"]).empty:
        st.caption(f"Not enough geo×SRType coverage to compute equity scores for **{display_name}**.")
        return

    # ── Category-level equity-score trend, vs. all categories ─────────────────
    st.markdown(f"**{display_name}** — equity-score trend vs. all categories · **{year}** highlighted")
    col_r, col_i = st.columns(2)
    with col_r:
        st.caption("Race-based equity score")
        cw_race = citywide_trend[(citywide_trend["dimension"] == "Race") & (citywide_trend["metric"] == metric_label)]
        st.plotly_chart(
            _category_score_trend_fig(cat_scope[cat_scope["dimension"] == "Race"], cw_race, "Race", year),
            use_container_width=True, key="cat_eq_cat_race", config={"displayModeBar": False},
        )
    with col_i:
        st.caption("Income-based equity score")
        cw_income = citywide_trend[(citywide_trend["dimension"] == "Income") & (citywide_trend["metric"] == metric_label)]
        st.plotly_chart(
            _category_score_trend_fig(cat_scope[cat_scope["dimension"] == "Income"], cw_income, "Income", year),
            use_container_width=True, key="cat_eq_cat_income", config={"displayModeBar": False},
        )

    # ── Within-category subtype equity breakdown ──────────────────────────────
    st.divider()
    st.subheader(f"{display_name} — equity score by subcategory")

    current_year_rows = geo_srtype_history[
        (geo_srtype_history["year"] == year)
        & (geo_srtype_history["total_requests"] >= MIN_GEO_SRTYPE_N)
        & (geo_srtype_history["SRType"].str.startswith(f"{selected_cat}-"))
    ]
    all_types = sorted(geo_srtype_history.loc[
        geo_srtype_history["SRType"].str.startswith(f"{selected_cat}-"), "SRType"
    ].unique().tolist())
    top_types = (
        current_year_rows.groupby("SRType")["total_requests"].sum()
        .sort_values(ascending=False).head(_TOP_SUBTYPES_N).index.tolist()
    )
    n_other = len(all_types) - len(top_types)
    other_label = f"All other {selected_cat} types ({n_other})"

    if not top_types:
        st.caption(
            f"No {selected_cat} subtypes clear the {MIN_GEO_SRTYPE_N}-request "
            f"per-cell threshold in **{year}** — try a different year or category."
        )
        return

    if n_other > 0:
        st.caption(
            f"{selected_cat} contains {len(all_types)} request types. Showing equity scores "
            f"for the {len(top_types)} highest-volume types individually (ranked by {year} "
            f"volume, after suppressing sparse cells); the remaining {n_other} are folded "
            f"into **{other_label}** (volume-weighted per geography, then scored as one group) "
            "so the chart stays readable — exactly as Tab 2 folds its operational breakdown."
        )
    else:
        st.caption(f"{selected_cat} contains {len(all_types)} request type{'s' if len(all_types) != 1 else ''}.")

    sub_history = compute_subtype_equity_history(
        data_dir, geo_key, demographics, selected_cat, tuple(top_types), other_label, metric_col,
    )
    labels = [_short_label(t) for t in top_types]
    if sub_history.empty or sub_history.dropna(subset=["score"]).empty:
        st.caption(
            f"Not enough geo×SRType coverage within **{display_name}**'s subtypes to "
            "compute equity scores — try Median days to close vs. Closure rate, or a "
            "different category."
        )
    else:
        st.markdown("**Race-based equity score, year over year**")
        st.plotly_chart(
            _subtype_score_multiline_fig(sub_history, labels, other_label, "Race"),
            use_container_width=True, key="cat_eq_sub_race", config={"displayModeBar": False},
        )
        st.markdown("**Income-based equity score, year over year**")
        st.plotly_chart(
            _subtype_score_multiline_fig(sub_history, labels, other_label, "Income"),
            use_container_width=True, key="cat_eq_sub_income", config={"displayModeBar": False},
        )
        st.caption(
            "Sparse SRType×year×geography combinations routinely fall short of the "
            "minimum sample needed for a score (gaps in a line = insufficient data, "
            "not zero equity) — a thinner line simply means fewer years are scoreable "
            "for that type, not that its equity is worse."
        )
