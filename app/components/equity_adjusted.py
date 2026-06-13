"""Equity Adjusted for Service Mix — Tab 6, the payoff of the equity arc.

Tabs 4 and 5 surfaced, informally, that the citywide equity gap shrinks sharply
once you look within individual service types — the signature of a *usage-mix*
effect (disadvantaged areas request structurally slower services more often)
rather than a *delivery-difference* one. This tab makes the normalized picture
concrete, in space and in time:

1. **Normalized equity over time** — the citywide equity score recomputed *within*
   each service type and recombined volume-weighted (the "mix-adjusted" score),
   trended against the raw geo-level score across all years. Answers: once you
   account for service mix, is the gap *actually* closing? This is also the exact
   scalar the cross-city group compares, so it bridges to Phase 5.
2. **Normalized delivery across neighborhoods** — each geography's metric relative
   to the citywide norm *for the very services it requests* (volume-weighted across
   its own mix), as a residual choropleth and an actual-vs-expected scatter. After
   adjusting for what a neighborhood asks for, who is still over- or under-served?
3. **Within-type equity ranking** + per-type distribution drill-down — which
   specific services are delivered most unequally once isolated from the mix.
4. **Regression** — a fixed-effects panel as an independent corroboration.
"""
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

# Reuse the canonical per-type scoring (cached) and the box-strip distribution
# comparison rather than re-implementing either — keeps this tab's numbers
# identical to Tab 5's and its distribution plots identical to the Equity tab's.
from components.category_equity_explorer import _subtype_current_year_scores
from components.equity_distributions import _comparison_fig
from components.equity_trend import compute_citywide_equity_trend
from components.map_view import (
    BALTIMORE_CENTER,
    BALTIMORE_ZOOM,
    MAPBOX_STYLE,
    METRIC_OPTIONS,
)
from components.srtype_shared import (
    MIN_GEO_SRTYPE_N,
    load_geo_srtype_history,
    load_srtype_history,
)
from components.utils import score_label

# Only median-days and closure-rate roll up to the geo×SRType grain — on-time rate
# and requests-per-1k need fields (DueDate, population) that don't, so the adjusted
# score, the normalized residual, and the ranking can only use these two.
_SRTYPE_METRICS = {
    "Median days to close": "median_days_to_close",
    "Closure rate": "closure_rate",
}
_HIGHER_IS_BETTER = {"closure_rate", "on_time_rate"}

# Eligibility for the within-type ranking — a low score only means something if it's
# backed by enough geographic spread and volume that it isn't just a thin sample.
_RANK_MIN_GEO_COVERAGE = 0.33
_RANK_MIN_REQUESTS = 100
_RANK_TOP_N = 20

# A geography needs at least this many scoreable service types for its mix-normalized
# value to be stable rather than a one- or two-service artifact.
_NORM_MIN_TYPES = 3

# Regression: drop the long tail of rarely-seen types (their fixed-effect dummy is
# near-degenerate and only inflates the design matrix) and scale income so its
# coefficient is per +$10k rather than a near-zero per-dollar figure.
_REG_MIN_TYPE_ROWS = 25

_DIM_COLORS = {"Race": "#8B2020", "Income": "#1F4E8C"}


def _wmean(values: pd.Series, weights: pd.Series) -> float:
    """Volume-weighted mean over the non-null, positive-weight rows."""
    df = pd.DataFrame({"v": values, "w": weights}).dropna()
    df = df[df["w"] > 0]
    if df.empty:
        return float("nan")
    return float((df["v"] * df["w"]).sum() / df["w"].sum())


def _short_label(srtype: str) -> str:
    """'SW-Dirty Alley' -> 'Dirty Alley (SW)' — keeps the department visible while
    dropping the redundant prefix from the descriptive part."""
    if "-" in srtype:
        prefix, rest = srtype.split("-", 1)
        return f"{rest.strip()} ({prefix.strip()})"
    return srtype


def _add_score_bands(fig: go.Figure) -> None:
    """Green/amber/red overlap-score threshold bands, drawn behind the data — same
    convention and thresholds as the other equity tabs."""
    fig.add_hrect(y0=0.7, y1=1.0, fillcolor="green", opacity=0.06, line_width=0)
    fig.add_hrect(y0=0.4, y1=0.7, fillcolor="orange", opacity=0.06, line_width=0)
    fig.add_hrect(y0=0.0, y1=0.4, fillcolor="red", opacity=0.06, line_width=0)


def _score_layout(height: int) -> dict:
    """Shared layout for the equity-score line charts — fixed [0,1] axis (scores are
    bounded) and percent formatting."""
    return dict(
        height=height,
        margin={"t": 8, "b": 8, "l": 55, "r": 8},
        xaxis=dict(title="Year", dtick=1),
        yaxis=dict(title="Equity score", range=[0, 1], tickformat=".0%", gridcolor="#eeeeee"),
        plot_bgcolor="white", paper_bgcolor="white",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0,
                    font=dict(size=10), bgcolor="rgba(0,0,0,0)"),
    )


# ── Per-type scores → adjusted citywide score ─────────────────────────────────

@st.cache_data
def compute_adjusted_scores(
    data_dir: Path,
    geo_key: str,
    demographics: pd.DataFrame,
    year: int,
    metric_col: str,
) -> pd.DataFrame:
    """Per-SRType within-type equity scores for `year`, joined to that type's
    citywide request volume — the building block for both the volume-weighted
    "adjusted" citywide score and the ranking panel.

    Columns: `SRType`, `Race`, `Income`, `volume`. One row per service type that
    was scoreable on at least one dimension after `MIN_GEO_SRTYPE_N` suppression.
    """
    scores = _subtype_current_year_scores(data_dir, geo_key, demographics, year, metric_col)
    if scores.empty:
        return pd.DataFrame(columns=["SRType", "Race", "Income", "volume"])
    wide = scores.pivot_table(index="SRType", columns="dimension", values="score").reset_index()
    for dim in ("Race", "Income"):
        if dim not in wide.columns:
            wide[dim] = float("nan")

    sr_hist = load_srtype_history(data_dir)
    vol = (
        sr_hist[sr_hist["year"] == year].groupby("SRType")["total_requests"].sum()
        if not sr_hist.empty else pd.Series(dtype=float)
    )
    wide["volume"] = wide["SRType"].map(vol).fillna(0.0)
    return wide[["SRType", "Race", "Income", "volume"]]


@st.cache_data
def compute_adjusted_equity_trend(
    data_dir: Path,
    geo_key: str,
    demographics: pd.DataFrame,
    metric_col: str,
    metric_label: str,
) -> pd.DataFrame:
    """Long frame (year, dimension, kind, score) with one Raw and one Mix-adjusted
    row per (year, Race|Income).

    *Raw* is the geo-level citywide score (the Equity tab's number, from
    `compute_citywide_equity_trend`). *Mix-adjusted* is the volume-weighted mean of
    the within-type scores for that year (`compute_adjusted_scores` → `_wmean`).
    Trending the two together shows whether the gap is closing for real or whether
    the raw line is just tracking shifts in what neighborhoods request.
    """
    raw = compute_citywide_equity_trend(data_dir, demographics, geo_key)
    years = sorted({
        int(p.stem.split("_")[-1])
        for p in data_dir.glob(f"{geo_key}_srtype_metrics_*.parquet")
        if p.stem.split("_")[-1].isdigit()
    })
    recs = []
    for yr in years:
        per = compute_adjusted_scores(data_dir, geo_key, demographics, yr, metric_col)
        for dim in ("Race", "Income"):
            adj = _wmean(per[dim], per["volume"]) if not per.empty else float("nan")
            recs.append({"year": yr, "dimension": dim, "kind": "Mix-adjusted", "score": adj})
            r = raw[(raw["year"] == yr) & (raw["dimension"] == dim) & (raw["metric"] == metric_label)]["score"]
            recs.append({"year": yr, "dimension": dim, "kind": "Raw", "score": float(r.mean()) if not r.empty else float("nan")})
    return pd.DataFrame(recs)


def _norm_trend_fig(trend: pd.DataFrame, dimension: str, year: int) -> go.Figure:
    """Raw vs. mix-adjusted equity score for one dimension, across years — the
    mix-adjusted line solid in the dimension color, the raw line dashed gray, on the
    shared [0,1] axis with threshold bands and the selected year picked out."""
    fig = go.Figure()
    _add_score_bands(fig)
    sub = trend[trend["dimension"] == dimension]

    raw = sub[sub["kind"] == "Raw"].dropna(subset=["score"]).sort_values("year")
    if not raw.empty:
        fig.add_trace(go.Scatter(
            x=raw["year"], y=raw["score"], mode="lines+markers", name="Raw (citywide)",
            line=dict(width=2, dash="dash", color="#999999"),
            marker=dict(size=6, color="#999999", symbol="diamond"),
            hovertemplate="<b>Raw</b><br>%{x}: %{y:.0%}<extra></extra>",
        ))
    adj = sub[sub["kind"] == "Mix-adjusted"].dropna(subset=["score"]).sort_values("year")
    if not adj.empty:
        color = _DIM_COLORS[dimension]
        fig.add_trace(go.Scatter(
            x=adj["year"], y=adj["score"], mode="lines+markers", name="Mix-adjusted",
            line=dict(width=2.4, color=color), marker=dict(size=7, color=color),
            hovertemplate="<b>Mix-adjusted</b><br>%{x}: %{y:.0%}<extra></extra>",
        ))
    fig.add_vline(x=year, line_width=1, line_dash="dot", line_color="#999999")
    fig.update_layout(**_score_layout(300))
    return fig


# ── Per-geography mix-normalized metric (residual map + scatter) ───────────────

@st.cache_data
def compute_normalized_geo_metrics(
    data_dir: Path, geo_key: str, year: int, metric_col: str,
) -> pd.DataFrame:
    """Each geography's *observed* metric vs. the value its **service mix** predicts —
    classic indirect standardization.

    - `actual` — the geography's true metric, read straight from
      `{geo}_metrics_{year}.parquet` (the *exact* number the Equity tab shows, so the
      two tabs always agree). It is **not** rebuilt from per-type values: a median
      does not decompose into a weighted mean of per-type medians (mean-of-medians
      overweights the slow-tail types and inflates the scale), so reconstructing it
      would diverge from the verified rollup.
    - `expected` — the geography's own request mix scored at the **citywide** per-type
      rate: `Σ_t w_{g,t} · city_value_t` where `w_{g,t}` is the geography's share of
      its own volume in type t. This isolates the pure mix effect (what an area would
      experience if every service it requests were delivered at the city's typical
      pace for that service). It is rescaled by one global constant so the
      volume-weighted citywide aggregate of `expected` equals that of `actual` —
      putting it on the same scale as the rollup and centering the residual at 0 (for
      closure rate, which decomposes cleanly, that constant is ≈1, i.e. direct
      standardization).
    - `residual` — `actual − expected`: over/under-performance once the mix the
      geography requests is held constant. An area that asks for structurally slow
      services is not penalized for that here — only for being handled differently
      than the city handles those same services.

    Columns: `geoid`, `actual`, `expected`, `residual`, `volume`, `n_types`. Drops
    geographies with fewer than `_NORM_MIN_TYPES` scoreable types.
    """
    cols = ["geoid", "actual", "expected", "residual", "volume", "n_types"]
    hist = load_geo_srtype_history(data_dir, geo_key)
    sr_path = data_dir / f"srtype_metrics_{year}.parquet"
    rollup_path = data_dir / f"{geo_key}_metrics_{year}.parquet"
    if hist.empty or not sr_path.exists() or not rollup_path.exists():
        return pd.DataFrame(columns=cols)

    # The verified geo-level value (== Equity tab) is the single source of truth for `actual`.
    rollup = pd.read_parquet(rollup_path)[["geoid", metric_col, "total_requests"]].rename(
        columns={metric_col: "actual", "total_requests": "volume"}
    )

    cells = hist[(hist["year"] == year) & (hist["total_requests"] >= MIN_GEO_SRTYPE_N)]
    city = pd.read_parquet(sr_path)[["SRType", metric_col]].rename(columns={metric_col: "_city"})
    m = cells.merge(city, on="SRType", how="left").dropna(subset=["_city", "total_requests"])
    m = m[m["total_requests"] > 0]
    if m.empty:
        return pd.DataFrame(columns=cols)

    recs = []
    for gid, grp in m.groupby("geoid"):
        if grp["SRType"].nunique() < _NORM_MIN_TYPES:
            continue
        w = grp["total_requests"].to_numpy(float)
        raw_expected = float((grp["_city"].to_numpy(float) * w).sum() / w.sum())
        recs.append({"geoid": gid, "raw_expected": raw_expected, "n_types": int(grp["SRType"].nunique())})
    if not recs:
        return pd.DataFrame(columns=cols)

    out = pd.DataFrame(recs).merge(rollup, on="geoid", how="inner").dropna(subset=["actual", "raw_expected"])
    if out.empty:
        return pd.DataFrame(columns=cols)

    # One global rescale so the volume-weighted citywide aggregates of expected and
    # actual coincide — anchors expected to the rollup scale and centers residuals at 0.
    wv = out["volume"].to_numpy(float)
    denom = float((out["raw_expected"].to_numpy(float) * wv).sum())
    c = float((out["actual"].to_numpy(float) * wv).sum()) / denom if denom else 1.0
    out["expected"] = out["raw_expected"] * c
    out["residual"] = out["actual"] - out["expected"]
    return out[cols]


def _residual_choropleth_fig(
    df: pd.DataFrame, geojson: dict, featureidkey: str,
    metric_label: str, metric_col: str, higher_better: bool, mapbox_token: str,
) -> go.Figure:
    """Diverging residual map centered at 0 (on par with the city). Blue = better
    than the citywide norm for this area's mix, red = worse — direction handled per
    metric so 'better' always reads blue regardless of whether high or low is good."""
    is_rate = metric_col == "closure_rate"
    fmt, resid_fmt = (":.0%", ":+.1%") if is_rate else (":.1f", ":+.1f")
    vals = df["residual"].dropna()
    m = float(max(abs(vals.min()), abs(vals.max()))) if not vals.empty else 1.0
    m = m or 1.0
    # RdBu: low→red, high→blue. For a higher-is-better metric a positive residual is
    # good, so RdBu already puts it on blue. For a lower-is-better metric flip it.
    colorscale = "RdBu" if higher_better else "RdBu_r"
    better_at_high = higher_better  # whether +residual is the "better" end
    ticktext = (
        ["Worse than city", "On par", "Better than city"]
        if better_at_high else
        ["Better than city", "On par", "Worse than city"]
    )
    fig = px.choropleth_mapbox(
        df, geojson=geojson, locations="geoid", featureidkey=featureidkey,
        color="residual", color_continuous_scale=colorscale,
        color_continuous_midpoint=0.0, range_color=[-m, m],
        mapbox_style=MAPBOX_STYLE, zoom=BALTIMORE_ZOOM, center=BALTIMORE_CENTER,
        opacity=0.75, labels={"residual": f"{metric_label} vs. city norm"},
        hover_data={"geoid": True, "actual": fmt, "expected": fmt, "residual": resid_fmt},
    )
    fig.update_layout(
        margin={"r": 0, "t": 0, "l": 0, "b": 55}, height=560,
        coloraxis_colorbar=dict(
            orientation="h", x=0.5, xanchor="center", y=-0.04, yanchor="top",
            thickness=12, len=0.85, title=dict(text=f"{metric_label} vs. city norm", side="top"),
            tickvals=[-m, 0, m], ticktext=ticktext,
        ),
        mapbox_accesstoken=mapbox_token,
    )
    return fig


def _actual_expected_scatter_fig(
    df: pd.DataFrame, metric_label: str, metric_col: str, higher_better: bool,
) -> go.Figure:
    """One dot per neighborhood: expected (what its service mix predicts) on x, actual
    (the verified rollup value) on y, with the y=x reference line. Off the diagonal =
    over/under-performing beyond what the service mix predicts. Colored by median
    income — a neutral demographic shading for the equity read."""
    is_rate = metric_col == "closure_rate"
    fmt = ".0%" if is_rate else ".1f"
    resid_fmt = ":+.1%" if is_rate else ":+.1f"
    lo = float(min(df["expected"].min(), df["actual"].min()))
    hi = float(max(df["expected"].max(), df["actual"].max()))
    pad = (hi - lo) * 0.05 or 1.0

    color_col = "median_income" if "median_income" in df.columns else None
    fig = px.scatter(
        df, x="expected", y="actual",
        color=color_col,
        color_continuous_scale="Viridis" if color_col else None,
        size="volume", size_max=22,
        hover_name="geoid",
        hover_data={
            "expected": f":{fmt}", "actual": f":{fmt}", "residual": resid_fmt,
            "volume": ":,.0f", "median_income": ":$,.0f" if color_col else False,
        },
        labels={
            "expected": f"Expected {metric_label.lower()} (predicted by service mix)",
            "actual": f"Actual {metric_label.lower()}",
            "median_income": "Median income",
        },
    )
    fig.add_trace(go.Scatter(
        x=[lo - pad, hi + pad], y=[lo - pad, hi + pad], mode="lines",
        line=dict(color="#888888", width=1, dash="dash"),
        name="On par with mix", hoverinfo="skip", showlegend=False,
    ))
    fig.update_layout(
        height=460, margin={"t": 8, "b": 8, "l": 8, "r": 8},
        plot_bgcolor="white", paper_bgcolor="white",
        xaxis=dict(gridcolor="#eeeeee", tickformat=fmt, range=[lo - pad, hi + pad]),
        yaxis=dict(gridcolor="#eeeeee", tickformat=fmt, range=[lo - pad, hi + pad]),
        coloraxis_colorbar=dict(title="Median<br>income", tickprefix="$", tickformat=",.0f"),
    )
    return fig


# ── Within-type ranking ───────────────────────────────────────────────────────

@st.cache_data
def _eligible_types(data_dir: Path, geo_key: str, year: int) -> list[str]:
    """Service types with enough geographic spread and volume this year for a
    within-type score to be trustworthy rather than a thin-sample artifact."""
    hist = load_geo_srtype_history(data_dir, geo_key)
    if hist.empty:
        return []
    year_rows = hist[(hist["year"] == year) & (hist["total_requests"] >= MIN_GEO_SRTYPE_N)]
    if year_rows.empty:
        return []
    n_geos = year_rows["geoid"].nunique()
    coverage = year_rows.groupby("SRType")["geoid"].nunique() / max(n_geos, 1)
    volume = hist[hist["year"] == year].groupby("SRType")["total_requests"].sum()
    return sorted(
        s for s in coverage.index
        if coverage.get(s, 0) >= _RANK_MIN_GEO_COVERAGE
        and volume.get(s, 0) >= _RANK_MIN_REQUESTS
    )


def _ranking_fig(ranked: pd.DataFrame, dimension: str) -> go.Figure:
    """Horizontal dot-plot of within-type scores, worst at the bottom, each dot
    colored by `score_label()`. Threshold bands sit behind the dots."""
    d = ranked.sort_values(dimension)  # worst first → lands at the bottom of the y-axis
    labels = [_short_label(s) for s in d["SRType"]]
    colors = [score_label(v)[1] for v in d[dimension]]
    fig = go.Figure()
    for x0, x1, c in [(0.7, 1.0, "green"), (0.4, 0.7, "orange"), (0.0, 0.4, "red")]:
        fig.add_vrect(x0=x0, x1=x1, fillcolor=c, opacity=0.05, line_width=0)
    fig.add_trace(go.Scatter(
        x=d[dimension], y=labels, mode="markers",
        marker=dict(size=11, color=colors, line=dict(width=1, color="#444444")),
        hovertemplate="<b>%{y}</b><br>" + dimension + " equity score: %{x:.0%}<extra></extra>",
    ))
    fig.update_layout(
        height=max(280, 26 * len(labels) + 60),
        margin={"t": 8, "b": 8, "l": 8, "r": 8},
        xaxis=dict(title=f"{dimension}-based equity score", range=[0, 1], tickformat=".0%", gridcolor="#eeeeee"),
        yaxis=dict(title=None, automargin=True),
        plot_bgcolor="white", paper_bgcolor="white", showlegend=False,
    )
    return fig


def _type_groups(
    data_dir: Path, geo_key: str, demographics: pd.DataFrame,
    year: int, srtype: str, metric_col: str,
) -> dict[str, pd.Series]:
    """The four group-value series behind one service type's score this year —
    majority-Black/White and below/above-median-income — ready for `_comparison_fig`."""
    hist = load_geo_srtype_history(data_dir, geo_key)
    rows = hist[
        (hist["year"] == year)
        & (hist["SRType"] == srtype)
        & (hist["total_requests"] >= MIN_GEO_SRTYPE_N)
    ].merge(demographics, on="geoid", how="left")
    valid = rows.dropna(subset=[metric_col])

    race = valid.dropna(subset=["pct_black", "pct_white"])
    inc = valid.dropna(subset=["median_income"])
    city_med = inc["median_income"].median()
    return {
        "black": race[race["pct_black"] > 0.5][metric_col],
        "white": race[race["pct_white"] > 0.5][metric_col],
        "below": inc[inc["median_income"] <= city_med][metric_col],
        "above": inc[inc["median_income"] > city_med][metric_col],
    }


# ── Regression ────────────────────────────────────────────────────────────────

@st.cache_data
def compute_regression(
    data_dir: Path, geo_key: str, demographics: pd.DataFrame,
) -> tuple[pd.DataFrame, dict]:
    """WLS of log(1 + median days to close) on neighborhood race and income, with
    service-type and year fixed effects, over the stacked geo×SRType×year panel.

    An *aggregate-level approximation* of the original record-level spec (record-level
    data isn't in `data/processed/`): each observation is a (geography, service type,
    year) cell weighted by its request count. The fixed effects absorb between-type and
    between-year differences, so the race/income coefficients estimate the within-type,
    within-year demographic gap — the formal counterpart to this tab's adjusted score.

    Returns `(coef_df, meta)` — small, cache-friendly objects rather than the full
    statsmodels result.
    """
    import statsmodels.formula.api as smf

    hist = load_geo_srtype_history(data_dir, geo_key)
    empty = (pd.DataFrame(columns=["term", "beta", "ci_low", "ci_high", "pvalue"]), {})
    if hist.empty:
        return empty

    panel = hist[hist["total_requests"] >= MIN_GEO_SRTYPE_N].merge(demographics, on="geoid", how="left")
    panel = panel.dropna(subset=["median_days_to_close", "pct_black", "median_income", "total_requests"])
    panel = panel[panel["total_requests"] > 0]
    if panel.empty:
        return empty

    type_counts = panel["SRType"].value_counts()
    keep_types = type_counts[type_counts >= _REG_MIN_TYPE_ROWS].index
    panel = panel[panel["SRType"].isin(keep_types)]
    if panel.empty or panel["SRType"].nunique() < 2 or panel["year"].nunique() < 2:
        return empty

    panel = panel.assign(
        log_days=np.log1p(panel["median_days_to_close"]),
        income_10k=panel["median_income"] / 10_000.0,
    )

    model = smf.wls(
        "log_days ~ pct_black + income_10k + C(SRType) + C(year)",
        data=panel, weights=panel["total_requests"],
    ).fit()

    ci = model.conf_int()
    rows = []
    for term, pretty in [("pct_black", "% Black (0→100%)"), ("income_10k", "Median income (+$10k)")]:
        if term in model.params.index:
            rows.append({
                "term": pretty,
                "beta": float(model.params[term]),
                "ci_low": float(ci.loc[term, 0]),
                "ci_high": float(ci.loc[term, 1]),
                "pvalue": float(model.pvalues[term]),
            })
    meta = {
        "nobs": int(model.nobs),
        "n_types": int(panel["SRType"].nunique()),
        "n_years": int(panel["year"].nunique()),
        "rsquared": float(model.rsquared),
    }
    return pd.DataFrame(rows), meta


def _coef_fig(coef: pd.DataFrame) -> go.Figure:
    """Forest plot of each predictor's coefficient with its 95% CI, on the log-days
    scale; a dashed zero line marks 'no effect'."""
    fig = go.Figure()
    fig.add_vline(x=0, line_dash="dash", line_color="#999999", line_width=1)
    for _, r in coef.iterrows():
        sig = r["pvalue"] < 0.05
        color = "#d73027" if sig else "#999999"
        fig.add_trace(go.Scatter(
            x=[r["beta"]], y=[r["term"]],
            error_x=dict(
                type="data", array=[r["ci_high"] - r["beta"]],
                arrayminus=[r["beta"] - r["ci_low"]], thickness=1.5, width=6, color=color,
            ),
            mode="markers", marker=dict(size=11, color=color),
            hovertemplate=(
                "<b>%{y}</b><br>coef: %{x:.4f}<br>"
                f"95% CI: [{r['ci_low']:.4f}, {r['ci_high']:.4f}]<br>"
                f"p = {r['pvalue']:.3g}<extra></extra>"
            ),
            showlegend=False,
        ))
    fig.update_layout(
        height=200, margin={"t": 8, "b": 8, "l": 8, "r": 8},
        xaxis=dict(title="Coefficient on log(1 + days to close)", gridcolor="#eeeeee", zeroline=False),
        yaxis=dict(title=None, automargin=True),
        plot_bgcolor="white", paper_bgcolor="white",
    )
    return fig


def _regression_interpretation(coef: pd.DataFrame) -> str:
    """Plain-language reading of the two coefficients of interest."""
    parts = []
    lookup = {r["term"]: r for _, r in coef.iterrows()}

    black = lookup.get("% Black (0→100%)")
    if black is not None:
        pct = np.expm1(black["beta"] * 0.10)
        if black["pvalue"] >= 0.05:
            parts.append(
                "Holding service type and year constant, a neighborhood's **share Black "
                "is not a statistically significant predictor** of how long requests take "
                "to close — consistent with the gap being driven by *which* services areas "
                "request, not how the same service is delivered."
            )
        else:
            direction = "longer" if pct > 0 else "shorter"
            parts.append(
                f"Holding service type and year constant, each **+10 percentage points** in "
                f"a neighborhood's share Black is associated with **{abs(pct):.1%} {direction}** "
                "time to close — a within-type gap that survives the service-mix adjustment."
            )

    income = lookup.get("Median income (+$10k)")
    if income is not None:
        pct = np.expm1(income["beta"])
        if income["pvalue"] >= 0.05:
            parts.append(
                "Median household income is likewise **not a significant predictor** once "
                "service type and year are held constant."
            )
        else:
            direction = "longer" if pct > 0 else "shorter"
            parts.append(
                f"Each **+$10,000** in median household income is associated with "
                f"**{abs(pct):.1%} {direction}** time to close, within type and year."
            )
    return "  \n".join(parts)


# ── Render ────────────────────────────────────────────────────────────────────

def render_equity_adjusted(
    data_dir: Path,
    demographics: pd.DataFrame | None,
    geo_key: str,
    year: int,
    geojson: dict | None = None,
    featureidkey: str = "properties.csa_name",
    mapbox_token: str = "",
    eq_metric_label: str | None = None,
) -> None:
    st.caption(
        "The last tab showed the citywide equity gap shrinking when scored within "
        "individual service categories. This tab normalizes for service mix directly — "
        "in time and in space — then checks the result against a fixed-effects regression."
    )
    with st.expander("What to look for"):
        st.markdown(
            "- **Over time:** does the *mix-adjusted* equity line sit above the raw line, "
            "and is it actually trending up? A flat or falling adjusted line means real "
            "disparity, not just a shift in what neighborhoods request.\n"
            "- **Across neighborhoods:** after adjusting for the services each area asks "
            "for, who is still over- or under-served? On the scatter, points off the "
            "diagonal are doing better or worse than their service mix predicts.\n"
            "- **By service type:** which specific services are delivered most unequally "
            "once isolated from the mix? Click one to see the raw distributions.\n"
            "- **The regression:** does a race or income gap survive once service type and "
            "year are held constant?"
        )

    if demographics is None or demographics.empty:
        st.info(
            f"Demographic data unavailable — `{geo_key}_demographics.csv` not found in "
            "`data/processed/`. Re-run the pipeline to generate it."
        )
        return

    geo_hist = load_geo_srtype_history(data_dir, geo_key)
    if geo_hist.empty:
        st.info(
            "Geo × SRType data unavailable — run "
            "`pipeline.py --stage srtype --year <year>` to generate it."
        )
        return

    # ── Metric — align with the Equity tab when possible ──────────────────────
    eq_col = METRIC_OPTIONS.get(eq_metric_label or "")
    default_label = eq_metric_label if eq_col in _SRTYPE_METRICS.values() else "Median days to close"
    metric_label = st.radio(
        "Metric",
        list(_SRTYPE_METRICS.keys()),
        index=list(_SRTYPE_METRICS.keys()).index(default_label),
        horizontal=True,
        key="adj_metric",
    )
    metric_col = _SRTYPE_METRICS[metric_label]
    higher_better = metric_col in _HIGHER_IS_BETTER
    if eq_metric_label and eq_col not in _SRTYPE_METRICS.values():
        st.caption(
            f"The Equity tab's **{eq_metric_label}** isn't available at the service-type "
            "grain — showing **Median days to close** instead. Closure rate is also available."
        )

    # ── 1 — Normalized equity over time ───────────────────────────────────────
    st.subheader("Normalized equity, year over year")
    st.caption(
        f"The citywide **{metric_label.lower()}** equity score computed two ways, across "
        "every year: the **raw** geo-level score (the Equity tab's number, dashed) and the "
        "**mix-adjusted** score — the same comparison run *within* each service type, then "
        "averaged across types weighted by volume. The gap between the lines is the part "
        "of the disparity that reflects *which* services neighborhoods request. 100% = no "
        "gap between groups."
    )
    with st.spinner("Scoring within-type equity across all years…"):
        trend = compute_adjusted_equity_trend(data_dir, geo_key, demographics, metric_col, metric_label)
    col_r, col_i = st.columns(2)
    with col_r:
        st.markdown("**Race — majority-Black vs. majority-White**")
        st.plotly_chart(_norm_trend_fig(trend, "Race", year), use_container_width=True,
                        key="adj_trend_race", config={"displayModeBar": False})
    with col_i:
        st.markdown("**Income — below vs. above median**")
        st.plotly_chart(_norm_trend_fig(trend, "Income", year), use_container_width=True,
                        key="adj_trend_income", config={"displayModeBar": False})

    # ── 2 — Normalized delivery across neighborhoods ──────────────────────────
    st.divider()
    st.subheader(f"Normalized {metric_label.lower()} across neighborhoods · {year}")
    st.caption(
        "Each neighborhood's performance relative to the **citywide norm for the very "
        "services it requests** (volume-weighted across its own mix). An area that asks "
        "for structurally slow services isn't penalized for that here — only for handling "
        "them differently than the city does on average."
    )

    norm = compute_normalized_geo_metrics(data_dir, geo_key, year, metric_col)
    if norm.empty:
        st.caption(
            f"Not enough geo×SRType coverage to normalize **{metric_label.lower()}** "
            f"for **{year}** at this geographic level."
        )
    else:
        norm = norm.merge(demographics, on="geoid", how="left")
        if geojson is not None:
            st.markdown("**Residual map** — blue is better than the city norm, red is worse")
            st.plotly_chart(
                _residual_choropleth_fig(norm, geojson, featureidkey, metric_label, metric_col, higher_better, mapbox_token),
                use_container_width=True, key="adj_resid_map", config={"displayModeBar": False},
            )
        st.markdown("**Actual vs. expected** — each dot a neighborhood; the dashed line is "
                    "exactly as its service mix predicts")
        st.plotly_chart(
            _actual_expected_scatter_fig(norm, metric_label, metric_col, higher_better),
            use_container_width=True, key="adj_scatter", config={"displayModeBar": False},
        )
        better = "above" if higher_better else "below"
        st.caption(
            f"The y-axis is the **verified rollup value** (identical to the Equity tab); "
            f"the x-axis is what each area's **service mix** predicts at citywide per-type "
            f"rates. Points **{better}** the dashed line out-perform what their mix predicts; "
            "points on the other side under-perform. Shading by median income shows whether "
            "off-diagonal performance lines up with neighborhood wealth — the equity question, "
            "asked on the mix-normalized metric."
        )

    # ── 3 — Within-type ranking ───────────────────────────────────────────────
    st.divider()
    st.subheader("Which service types are delivered most unequally?")
    st.caption(
        "Every eligible service type ranked by its own within-type equity score — the "
        "gap that remains *after* the service-mix effect is stripped out. Pick one below "
        "to see the raw distributions behind its score."
    )
    per_type = compute_adjusted_scores(data_dir, geo_key, demographics, year, metric_col)
    rank_dim = st.radio("Rank by", ["Race", "Income"], horizontal=True, key="adj_rank_dim")
    eligible = _eligible_types(data_dir, geo_key, year)
    ranked = per_type[per_type["SRType"].isin(eligible)].dropna(subset=[rank_dim])

    if ranked.empty:
        st.caption(
            "No service type meets the minimum coverage and volume standards for a "
            f"reliable within-type score on **{metric_label.lower()}** this year."
        )
    else:
        worst = ranked.nsmallest(_RANK_TOP_N, rank_dim)
        st.markdown(
            f"**{len(worst)}** lowest-scoring of **{len(ranked)}** eligible service types "
            f"on the **{rank_dim.lower()}** dimension · **{year}**"
        )
        st.plotly_chart(_ranking_fig(worst, rank_dim), use_container_width=True,
                        key="adj_rank", config={"displayModeBar": False})

        options = ranked.sort_values(rank_dim)["SRType"].tolist()
        chosen = st.selectbox(
            "Inspect a service type's distributions", options,
            format_func=_short_label, key="adj_drill",
        )
        if chosen:
            groups = _type_groups(data_dir, geo_key, demographics, year, chosen, metric_col)
            st.markdown(f"**{_short_label(chosen)}** — {metric_label.lower()}, {year}")
            d_race, d_income = st.columns(2)
            with d_race:
                st.markdown("**Race**")
                if len(groups["black"].dropna()) >= 3 and len(groups["white"].dropna()) >= 3:
                    _comparison_fig(groups["black"], "Maj. Black", groups["white"], "Maj. White",
                                    metric_col, key="adj_drill_race")
                else:
                    st.caption("Too few majority-race geographies for this type to compare.")
            with d_income:
                st.markdown("**Income**")
                if len(groups["below"].dropna()) >= 3 and len(groups["above"].dropna()) >= 3:
                    _comparison_fig(groups["below"], "Below median", groups["above"], "Above median",
                                    metric_col, key="adj_drill_income")
                else:
                    st.caption("Too few geographies with income data for this type to compare.")

    # ── 4 — Regression ────────────────────────────────────────────────────────
    st.divider()
    st.subheader("Regression — does the gap survive holding service type constant?")
    st.caption(
        "An OLS/WLS check independent of the overlap score: log(1 + median days to close) "
        "regressed on neighborhood race and income, with **service-type and year fixed "
        "effects**. The fixed effects hold *what* is requested and *when* constant, so the "
        "race and income coefficients estimate the within-type demographic gap directly. "
        "*Aggregate-level approximation — each row is a (geography, service type, year) "
        "cell weighted by request count, not an individual record.*"
    )

    with st.spinner("Fitting the fixed-effects panel regression…"):
        coef, meta = compute_regression(data_dir, geo_key, demographics)

    if coef.empty:
        st.info("Not enough panel data to fit the regression at this geographic level.")
    else:
        c_plot, c_tbl = st.columns([3, 2])
        with c_plot:
            st.plotly_chart(_coef_fig(coef), use_container_width=True,
                            key="adj_reg_coef", config={"displayModeBar": False})
        with c_tbl:
            show = coef.assign(
                Coefficient=coef["beta"].map(lambda v: f"{v:.4f}"),
                **{"95% CI": coef.apply(lambda r: f"[{r['ci_low']:.3f}, {r['ci_high']:.3f}]", axis=1)},
                **{"p-value": coef["pvalue"].map(lambda v: f"{v:.3g}")},
            ).rename(columns={"term": "Predictor"})[["Predictor", "Coefficient", "95% CI", "p-value"]]
            st.dataframe(show, use_container_width=True, hide_index=True)
        st.caption(
            f"n = {meta['nobs']:,} (geography × service type × year) cells · "
            f"{meta['n_types']} service types · {meta['n_years']} years · "
            f"R² = {meta['rsquared']:.2f} (mostly the fixed effects). "
            "Red = significant at p < 0.05; gray = not."
        )
        interp = _regression_interpretation(coef)
        if interp:
            st.markdown(interp)
