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
from components.utils import overlap_score

# Metrics available at geo×SRType grain — on_time_rate and requests_per_1k require
# fields (DueDate, population) that aren't rolled up to this grain.
_METRIC_OPTIONS = {
    "Median days to close": "median_days_to_close",
    "Closure rate": "closure_rate",
}

_TOP_CATEGORIES_N = 8
_TOP_SUBTYPES_N = 7

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
def compute_subtype_score_summary(
    data_dir: Path,
    geo_key: str,
    demographics: pd.DataFrame,
    year: int,
    metric_col: str,
) -> dict[str, float]:
    """Mean Race/Income equity score across every individual SRType in `year` —
    the finest grain scoreable without a category selection. Each geo×SRType row
    is already one comparable value (no rollup), so this is a straight per-type
    score-and-average — used only for the opening summary's overall-vs-category-
    vs-subtype comparison that shows whether scores rise at finer grain (a usage-
    mix signature) or hold flat (a delivery-difference signature).

    Loads the geo×SRType history internally from `(data_dir, geo_key)` rather than
    taking it as a DataFrame argument — see `compute_category_equity_history` for why.
    """
    geo_srtype_history = load_geo_srtype_history(data_dir, geo_key)
    rows = geo_srtype_history[
        (geo_srtype_history["year"] == year)
        & (geo_srtype_history["total_requests"] >= MIN_GEO_SRTYPE_N)
    ].merge(demographics, on="geoid", how="left")
    if rows.empty:
        return {"Race": float("nan"), "Income": float("nan")}

    scores: dict[str, list[float]] = {"Race": [], "Income": []}
    for _, g in rows.groupby("SRType"):
        valid = g.dropna(subset=[metric_col])
        for dim, score in _dimension_scores(valid, metric_col).items():
            if pd.notna(score):
                scores[dim].append(score)
    return {dim: (sum(vals) / len(vals) if vals else float("nan")) for dim, vals in scores.items()}


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


# ── Render ────────────────────────────────────────────────────────────────────

def render_category_equity_explorer(
    data_dir: Path,
    demographics: pd.DataFrame | None,
    geo_key: str,
    year: int,
) -> None:
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

    # ── Metric selector — only metrics available at the geo×SRType grain ─────
    metric_label = st.radio(
        "Equity metric", list(_METRIC_OPTIONS.keys()),
        horizontal=True, key="cat_eq_metric",
    )
    metric_col = _METRIC_OPTIONS[metric_label]

    st.markdown(
        f"Scores below measure **{metric_label.lower()}** — how often outcomes "
        "interleave between majority-Black vs. majority-White geographies (Race) "
        "and below- vs. above-median-income geographies (Income). 100% = perfectly "
        "interleaved · >70% not bad · 40–70% could be better · <40% needs review. "
        f"Cells with fewer than {MIN_GEO_SRTYPE_N} requests are suppressed before scoring, "
        "matching the threshold the Operations map already applies."
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
        st.markdown(
            f"**What {year}'s {metric_label.lower()} scores show:** measured across all "
            f"categories together, the equity score is **{overall['Race']:.0%}** for race "
            f"and **{overall['Income']:.0%}** for income. Scored within individual "
            f"categories instead, those averages move to **{cat_avg['Race']:.0%}** / "
            f"**{cat_avg['Income']:.0%}**; within individual service types, "
            f"**{sub_summary['Race']:.0%}** / **{sub_summary['Income']:.0%}**. Scores "
            "rising at finer grain is the signature of a usage-mix effect, not a "
            "delivery-difference one: neighborhoods request different *kinds* of "
            "services in different proportions, and that compositional gap — not how "
            "any single service type is delivered once requested — drives most of the "
            "citywide score."
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
