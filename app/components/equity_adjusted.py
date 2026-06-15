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
2. **Mix-adjusted delivery across neighborhoods** — each geography reweighted so its
   service-type mix matches the citywide mix (direct standardization, computed
   record-level in the pipeline `adjusted` stage — the only sound way to mix-adjust a
   median), as a residual choropleth and a raw-vs-adjusted scatter. After holding the
   mix at citywide proportions, who is still over- or under-served?
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
    load_adjusted_metrics,
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


@st.cache_data
def _tract_nsa_map(data_dir: Path) -> dict[str, str]:
    """geoid → NSA neighborhood name, from `tract_to_nsa.csv` (empty if absent)."""
    path = data_dir / "tract_to_nsa.csv"
    if not path.exists():
        return {}
    df = pd.read_csv(path, dtype={"geoid": str, "nsa_name": str}).fillna({"nsa_name": ""})
    return dict(zip(df["geoid"], df["nsa_name"]))


def _add_labels(df: pd.DataFrame, data_dir: Path, geo_key: str) -> pd.DataFrame:
    """Add a human-readable `label` column. CSA geoids are already names; tract
    geoids become 'NSA Name · Tract XXXX.XX' (or just the tract code when the NSA
    name is unknown), mirroring the Areas tab."""
    if geo_key != "tract":
        df["label"] = df["geoid"].astype(str)
        return df
    nsa = _tract_nsa_map(data_dir)
    g = df["geoid"].astype(str)
    t = g.str[5:]
    tract = "Tract " + t.str[:4] + "." + t.str[4:]
    name = g.map(nsa).fillna("")
    df["label"] = np.where(name.ne(""), name + " · " + tract, tract)
    return df


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
    """Each geography's observed metric vs. its **mix-standardized** value, from the
    precomputed `adjusted` pipeline stage (direct standardization over records).

    - `raw` — the geography's true metric, read straight from
      `{geo}_metrics_{year}.parquet` (the *exact* number the Equity tab shows).
    - `adjusted` — the same geography reweighted so its service-type mix matches the
      citywide mix (`adj_{metric_col}`). This is the statistically correct
      mix-adjustment, computed record-level in the pipeline because a median does not
      decompose into a weighted mean of per-type medians.
    - `residual` — `adjusted − citywide reference`: over/under-performance once the
      mix the geography requests is held at citywide proportions. An area that asks
      for structurally slow services is not penalized for that — only for delivering
      the citywide service mix faster or slower than the city as a whole.

    Returns empty (→ the tab shows a "run the adjusted stage" notice) when the
    `{geo}_adjusted_metrics_{year}.parquet` file isn't present. Columns: `geoid`,
    `raw`, `adjusted`, `residual`, `volume`.
    """
    cols = ["geoid", "raw", "adjusted", "residual", "volume"]
    adj = load_adjusted_metrics(data_dir, geo_key, year)
    rollup_path = data_dir / f"{geo_key}_metrics_{year}.parquet"
    adj_col, ref_col = f"adj_{metric_col}", f"ref_{metric_col}"
    if adj.empty or adj_col not in adj.columns or not rollup_path.exists():
        return pd.DataFrame(columns=cols)

    raw = pd.read_parquet(rollup_path)[["geoid", metric_col]].rename(columns={metric_col: "raw"})
    out = adj.merge(raw, on="geoid", how="inner").rename(
        columns={adj_col: "adjusted", "n_obs": "volume"}
    )
    out = out.dropna(subset=["adjusted", "raw"])
    if out.empty:
        return pd.DataFrame(columns=cols)
    out["residual"] = out["adjusted"] - out[ref_col]
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
        hover_name="label" if "label" in df.columns else None,
        hover_data={"raw": fmt, "adjusted": fmt, "residual": resid_fmt},
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


def _neighborhood_index_table(
    df: pd.DataFrame, metric_col: str, higher_better: bool,
) -> tuple[pd.DataFrame, dict]:
    """Sortable/searchable per-neighborhood table behind the map — raw, mix-adjusted,
    and Δ-vs-city for every geography, worst-first by default. Returns the display
    frame and a Streamlit `column_config` so numbers sort numerically (not as text)."""
    is_rate = metric_col == "closure_rate"
    scale = 100.0 if is_rate else 1.0
    unit = "%" if is_rate else "days"
    raw_c, adj_c, delta_c = f"Raw ({unit})", f"Mix-adjusted ({unit})", f"Δ vs city ({unit})"

    name_col = "label" if "label" in df.columns else "geoid"
    out = pd.DataFrame({
        "Neighborhood": df[name_col].astype(str),
        raw_c: df["raw"] * scale,
        adj_c: df["adjusted"] * scale,
        delta_c: df["residual"] * scale,
        "Requests": df["volume"].round().astype("Int64"),
    })
    if "median_income" in df.columns:
        out["Median income"] = df["median_income"]
    # Worst first: for higher-is-better metrics the worst residual is the most negative
    # (ascending); for days the worst is the most positive (descending).
    out = out.sort_values(delta_c, ascending=higher_better).reset_index(drop=True)

    num = "%.0f" if is_rate else "%.1f"
    cfg = {
        raw_c: st.column_config.NumberColumn(format=num),
        adj_c: st.column_config.NumberColumn(format=num),
        delta_c: st.column_config.NumberColumn(format=("%+.0f" if is_rate else "%+.1f")),
        "Requests": st.column_config.NumberColumn(format="%d"),
    }
    if "Median income" in out.columns:
        cfg["Median income"] = st.column_config.NumberColumn(format="$%d")
    return out, cfg


def _raw_adjusted_scatter_fig(
    df: pd.DataFrame, metric_label: str, metric_col: str, higher_better: bool,
) -> go.Figure:
    """One dot per neighborhood: raw (the verified rollup value, as observed) on x,
    mix-adjusted (reweighted to the citywide service mix) on y, with the y=x reference
    line. The two pastel half-planes split by the diagonal label where neighborhoods
    are faster/slower (or better/worse) than they appear once the service mix is held
    constant. Colored by median income — a neutral shading for the equity read."""
    is_rate = metric_col == "closure_rate"
    fmt = ".0%" if is_rate else ".1f"

    # Zoom to the central bulk (2nd–98th pct of the combined values) so points spread
    # across the plot instead of being compressed by a few extreme neighborhoods.
    combined = pd.concat([df["raw"], df["adjusted"]]).dropna()
    lo = float(combined.quantile(0.02))
    hi = float(combined.quantile(0.98))
    if hi <= lo:
        lo, hi = float(combined.min()), float(combined.max() or lo + 1)
    pad = (hi - lo) * 0.04 or 1.0
    lo, hi = lo - pad, hi + pad

    color_col = "median_income" if "median_income" in df.columns else None
    fig = px.scatter(
        df, x="raw", y="adjusted",
        color=color_col,
        color_continuous_scale="Viridis" if color_col else None,
        size="volume", size_max=22,
        hover_name="label" if "label" in df.columns else "geoid",
        hover_data={
            "raw": f":{fmt}", "adjusted": f":{fmt}", "residual": ":+.1%" if is_rate else ":+.1f",
            "volume": ":,.0f", "median_income": ":$,.0f" if color_col else False,
        },
        labels={
            "raw": f"Raw {metric_label.lower()} (as observed)",
            "adjusted": f"Mix-adjusted {metric_label.lower()} (citywide service mix)",
            "median_income": "Median income",
        },
    )

    # Diagonal half-planes: above the line adjusted > raw. For a lower-is-better metric
    # (days) that means slower-than-it-looks (worse, red); for closure it means
    # better-than-it-looks (blue). Held consistent with the app-wide red = worse rule.
    RED, BLUE = "rgba(214,39,40,0.06)", "rgba(31,119,180,0.06)"
    above_better = higher_better
    above_color = BLUE if above_better else RED
    below_color = RED if above_better else BLUE
    for path, fill in [
        (f"M {lo},{lo} L {lo},{hi} L {hi},{hi} Z", above_color),   # upper-left: adjusted > raw
        (f"M {lo},{lo} L {hi},{lo} L {hi},{hi} Z", below_color),   # lower-right: adjusted < raw
    ]:
        fig.add_shape(type="path", path=path, fillcolor=fill, line_width=0, layer="below")

    if is_rate:
        above_word, below_word = ("Better", "Worse") if above_better else ("Worse", "Better")
    else:
        above_word, below_word = ("Faster", "Slower") if above_better else ("Slower", "Faster")
    note = "than they appear<br>(after adjusting for service mix)"
    fig.add_annotation(x=lo + 0.04 * (hi - lo), y=hi - 0.04 * (hi - lo), xanchor="left", yanchor="top",
                       text=f"{above_word} {note}", showarrow=False, align="left",
                       font=dict(size=11, color="rgba(70,70,70,0.6)"))
    fig.add_annotation(x=hi - 0.04 * (hi - lo), y=lo + 0.04 * (hi - lo), xanchor="right", yanchor="bottom",
                       text=f"{below_word} {note}", showarrow=False, align="right",
                       font=dict(size=11, color="rgba(70,70,70,0.6)"))

    fig.add_trace(go.Scatter(
        x=[lo, hi], y=[lo, hi], mode="lines",
        line=dict(color="#888888", width=1, dash="dash"),
        name="Mix had no effect", hoverinfo="skip", showlegend=False,
    ))
    fig.update_layout(
        height=460, margin={"t": 8, "b": 8, "l": 8, "r": 8},
        plot_bgcolor="white", paper_bgcolor="white",
        xaxis=dict(gridcolor="#eeeeee", tickformat=fmt, range=[lo, hi]),
        yaxis=dict(gridcolor="#eeeeee", tickformat=fmt, range=[lo, hi]),
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

    Solved via the **sparse weighted normal equations** rather than a dense formula fit: the
    design is mostly the ~200 service-type fixed-effect dummies (99% zeros), so building the
    137k×230 dense matrix dominated the cold render (~8 s). Keeping the dummies sparse and
    forming the small k×k system `XᵀWX β = XᵀWy` gives **identical** coefficients, CIs,
    p-values, and R² (verified to 6 dp against statsmodels WLS) in ~0.8 s — and drops the
    statsmodels import entirely.
    """
    import scipy.sparse as sp
    from scipy.stats import t as _t

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

    # Design: [const, pct_black, income_10k, C(SRType), C(year)] — the two FE blocks kept
    # sparse (drop-first dummies). `log_days ~ pct_black + income_10k + C(SRType) + C(year)`,
    # WLS-weighted by request count.
    y = panel["log_days"].to_numpy(float)
    w = panel["total_requests"].to_numpy(float)
    n = len(y)
    srtype_d = pd.get_dummies(panel["SRType"], drop_first=True)
    year_d = pd.get_dummies(panel["year"], drop_first=True)
    dense = np.column_stack([
        np.ones(n), panel["pct_black"].to_numpy(float), panel["income_10k"].to_numpy(float),
    ])
    X = sp.hstack([
        sp.csr_matrix(dense), sp.csr_matrix(srtype_d.to_numpy(float)),
        sp.csr_matrix(year_d.to_numpy(float)),
    ]).tocsr()
    k = X.shape[1]
    if n <= k:
        return empty

    XtWX = (X.T @ X.multiply(w[:, None])).toarray()
    XtWy = X.T @ (w * y)
    beta = np.linalg.solve(XtWX, XtWy)
    resid = y - X @ beta
    rss = float(np.sum(w * resid ** 2))
    dof = n - k
    cov = np.linalg.inv(XtWX) * (rss / dof)
    se = np.sqrt(np.diag(cov))
    tcrit = float(_t.ppf(0.975, dof))
    wmean = float(np.sum(w * y) / np.sum(w))
    tss = float(np.sum(w * (y - wmean) ** 2))

    # pct_black and income_10k are columns 1 and 2 of the design (const is 0).
    rows = []
    for idx, pretty in [(1, "% Black (0→100%)"), (2, "Median income (+$10k)")]:
        rows.append({
            "term": pretty,
            "beta": float(beta[idx]),
            "ci_low": float(beta[idx] - tcrit * se[idx]),
            "ci_high": float(beta[idx] + tcrit * se[idx]),
            "pvalue": float(2 * _t.sf(abs(beta[idx] / se[idx]), dof)),
        })
    meta = {
        "nobs": n,
        "n_types": int(panel["SRType"].nunique()),
        "n_years": int(panel["year"].nunique()),
        "rsquared": float(1 - rss / tss) if tss > 0 else 0.0,
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
            "- **Across neighborhoods:** with every area reweighted to the citywide "
            "service mix, who is still over- or under-served? On the scatter, points that "
            "stay far from the diagonal after adjustment are genuine delivery differences.\n"
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

    # ── 2 — Mix-adjusted delivery across neighborhoods ────────────────────────
    st.divider()
    st.subheader(f"Mix-adjusted {metric_label.lower()} across neighborhoods · {year}")
    st.caption(
        "Each neighborhood reweighted so its **service-type mix matches the citywide "
        "mix**, then compared to the citywide norm. An area that asks for structurally "
        "slow services isn't penalized for that here — only for delivering the citywide "
        "service mix faster or slower than the city as a whole. *(Direct standardization, "
        "computed record-level in the pipeline — the only sound way to mix-adjust a median.)*"
    )

    norm = compute_normalized_geo_metrics(data_dir, geo_key, year, metric_col)
    if norm.empty:
        st.info(
            f"The mix-adjusted per-neighborhood view needs the **`adjusted`** pipeline "
            f"stage, which writes `{geo_key}_adjusted_metrics_{year}.parquet`. Run "
            f"`python scripts/pipeline.py --year {year} --stage adjusted` (or the backfill "
            "workflow) to enable it. The year-over-year trend above and the within-type "
            "ranking below don't require it."
        )
    else:
        norm = norm.merge(demographics, on="geoid", how="left")
        norm = _add_labels(norm, data_dir, geo_key)
        if geojson is not None:
            st.markdown("**Residual map** — blue is better than the citywide norm, red is worse")
            st.plotly_chart(
                _residual_choropleth_fig(norm, geojson, featureidkey, metric_label, metric_col, higher_better, mapbox_token),
                use_container_width=True, key="adj_resid_map", config={"displayModeBar": False},
            )
        st.markdown("**Raw vs. mix-adjusted** — each dot a neighborhood; the dashed line is "
                    "where the service mix made no difference")
        st.plotly_chart(
            _raw_adjusted_scatter_fig(norm, metric_label, metric_col, higher_better),
            use_container_width=True, key="adj_scatter", config={"displayModeBar": False},
        )
        st.caption(
            "The x-axis is the **verified rollup value** (identical to the Equity tab); the "
            "y-axis is the same neighborhood reweighted to the citywide service mix. The two "
            "shaded halves split by the dashed line mark where a neighborhood comes out **"
            f"{'better' if higher_better else 'faster'}** (blue) or **"
            f"{'worse' if higher_better else 'slower'}** (red) than its raw number suggests "
            "once mix is held constant; distance from the line is how much the mix was "
            "distorting that raw number. Shading the dots by median income "
            "shows whether that lines up with neighborhood wealth — the equity question, "
            "asked on the mix-adjusted metric."
        )

        st.markdown("**Find a neighborhood** — every geography, worst-first; click a "
                    "column to re-sort, or the ⌕ icon to search by name")
        index_tbl, index_cfg = _neighborhood_index_table(norm, metric_col, higher_better)
        st.dataframe(
            index_tbl, use_container_width=True, hide_index=True, height=320,
            column_config=index_cfg, key="adj_index",
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
