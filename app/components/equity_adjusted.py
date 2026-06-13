"""Equity Adjusted for Service Mix — Tab 6, the payoff of the equity arc.

Tabs 4 and 5 surfaced, informally, that the citywide equity gap shrinks sharply
once you look within individual service types — the signature of a *usage-mix*
effect (disadvantaged areas request structurally slower services more often)
rather than a *delivery-difference* one (the same service delivered worse to
some areas). This tab makes that separation formal:

1. **Raw vs. mix-adjusted score** (P4d-14) — the citywide score recomputed
   *within* each service type and recombined volume-weighted, side by side with
   the raw geo-level score. A higher adjusted score is direct evidence the gap is
   partly mix-driven; a similar score means it's in delivery.
2. **Within-type equity ranking** (P4d-15) — every service type ranked by its own
   overlap score, color-coded; pick one to see the raw race/income distributions
   behind its score.
3. **Regression** (P4d-16) — an OLS/WLS panel with service-type and year fixed
   effects: an independent check on whether a demographic gap survives once the
   *kind* of service requested is held constant.
"""
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

# Reuse the canonical per-type scoring (cached) and the box-strip distribution
# comparison rather than re-implementing either — keeps this tab's numbers
# identical to Tab 5's and its distribution plots identical to the Equity tab's.
from components.category_equity_explorer import _subtype_current_year_scores
from components.equity_distributions import _comparison_fig
from components.equity_trend import compute_citywide_equity_trend
from components.map_view import METRIC_OPTIONS
from components.srtype_shared import (
    CATEGORY_NAMES,
    MIN_GEO_SRTYPE_N,
    load_geo_srtype_history,
    load_srtype_history,
)
from components.utils import score_label

# Only median-days and closure-rate roll up to the geo×SRType grain — on-time rate
# and requests-per-1k need fields (DueDate, population) that don't, so the adjusted
# score and ranking can only be computed for these two.
_SRTYPE_METRICS = {
    "Median days to close": "median_days_to_close",
    "Closure rate": "closure_rate",
}

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


# ── Raw vs. adjusted score (P4d-14) ───────────────────────────────────────────

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


def _raw_adj_fig(raw: float, adjusted: float) -> go.Figure:
    """Two bars — raw citywide vs. mix-adjusted equity score — colored by
    `score_label()`'s green/amber/red/gray convention."""
    vals = [raw, adjusted]
    colors = [score_label(v)[1] for v in vals]
    fig = go.Figure(go.Bar(
        x=["Raw<br>(citywide)", "Mix-adjusted<br>(within service type)"],
        y=vals,
        marker_color=colors,
        text=[f"{v:.0%}" if not np.isnan(v) else "—" for v in vals],
        textposition="outside",
        hovertemplate="<b>%{x}</b><br>%{y:.0%}<extra></extra>",
        width=0.5,
    ))
    fig.add_hrect(y0=0.7, y1=1.16, fillcolor="green", opacity=0.05, line_width=0)
    fig.add_hrect(y0=0.4, y1=0.7, fillcolor="orange", opacity=0.05, line_width=0)
    fig.add_hrect(y0=0.0, y1=0.4, fillcolor="red", opacity=0.05, line_width=0)
    fig.update_layout(
        height=260,
        margin={"t": 8, "b": 8, "l": 50, "r": 8},
        yaxis=dict(title="Equity score", range=[0, 1.16], tickformat=".0%", gridcolor="#eeeeee"),
        xaxis=dict(title=None),
        plot_bgcolor="white", paper_bgcolor="white",
        showlegend=False,
    )
    return fig


# ── Within-type ranking (P4d-15) ──────────────────────────────────────────────

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


def _short_label(srtype: str) -> str:
    """'SW-Dirty Alley' -> 'Dirty Alley (SW)' — keeps the department visible while
    dropping the redundant prefix from the descriptive part."""
    if "-" in srtype:
        prefix, rest = srtype.split("-", 1)
        return f"{rest.strip()} ({prefix.strip()})"
    return srtype


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
        x=d[dimension], y=labels,
        mode="markers",
        marker=dict(size=11, color=colors, line=dict(width=1, color="#444444")),
        hovertemplate="<b>%{y}</b><br>" + dimension + " equity score: %{x:.0%}<extra></extra>",
    ))
    fig.update_layout(
        height=max(280, 26 * len(labels) + 60),
        margin={"t": 8, "b": 8, "l": 8, "r": 8},
        xaxis=dict(title=f"{dimension}-based equity score", range=[0, 1], tickformat=".0%", gridcolor="#eeeeee"),
        yaxis=dict(title=None, automargin=True),
        plot_bgcolor="white", paper_bgcolor="white",
        showlegend=False,
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


# ── Regression (P4d-16) ───────────────────────────────────────────────────────

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
    statsmodels result. `coef_df` has one row per demographic predictor with `beta`,
    `ci_low`, `ci_high`, `pvalue`; `meta` carries `nobs`, `n_types`, `rsquared`.
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

    # Drop the long tail of rarely-observed types — a fixed effect estimated from a
    # handful of cells is noise, and the extra dummies balloon the design matrix.
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
                type="data",
                array=[r["ci_high"] - r["beta"]],
                arrayminus=[r["beta"] - r["ci_low"]],
                thickness=1.5, width=6, color=color,
            ),
            mode="markers",
            marker=dict(size=11, color=color),
            hovertemplate=(
                "<b>%{y}</b><br>coef: %{x:.4f}<br>"
                f"95% CI: [{r['ci_low']:.4f}, {r['ci_high']:.4f}]<br>"
                f"p = {r['pvalue']:.3g}<extra></extra>"
            ),
            showlegend=False,
        ))
    fig.update_layout(
        height=200,
        margin={"t": 8, "b": 8, "l": 8, "r": 8},
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
        # Coefficient is per full 0→1 swing; report per +10 percentage points.
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
    eq_metric_label: str | None = None,
) -> None:
    st.caption(
        "The last tab showed the citywide equity gap shrinking when scored within "
        "individual service categories. This tab makes that formal: it recomputes the "
        "citywide score *within each service type* and recombines it volume-weighted, "
        "then checks the result against a fixed-effects regression."
    )
    with st.expander("What to look for"):
        st.markdown(
            "- **Raw vs. mix-adjusted:** if the adjusted bar is higher, part of the citywide "
            "gap is explained by *which* services a neighborhood requests (some are "
            "structurally slower), not by how the same service is delivered.\n"
            "- **The ranking:** which specific service types are delivered most unequally, "
            "even after isolating them from the mix? Click one to see the raw distributions.\n"
            "- **The regression:** an independent check — does a race or income gap survive "
            "once service type and year are held constant?"
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
    # The Equity tab can color by metrics (on-time rate, requests/1k) that don't roll
    # up to the geo×SRType grain; when the user is on one of those, default to days
    # to close and say so, rather than silently showing a different metric.
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
    if eq_metric_label and eq_col not in _SRTYPE_METRICS.values():
        st.caption(
            f"The Equity tab's **{eq_metric_label}** isn't available at the service-type "
            "grain — showing **Median days to close** instead. Closure rate is also available."
        )

    # ── 1 — Raw vs. mix-adjusted citywide score ───────────────────────────────
    st.subheader("Raw vs. mix-adjusted equity score")
    st.caption(
        f"The citywide **{metric_label.lower()}** equity score, computed two ways: the "
        "**raw** geo-level score (the Equity tab's number), and the **mix-adjusted** "
        "score — the same comparison run *within* each service type, then averaged "
        "across types weighted by request volume. 100% = no gap between groups."
    )

    per_type = compute_adjusted_scores(data_dir, geo_key, demographics, year, metric_col)
    citywide = compute_citywide_equity_trend(data_dir, demographics, geo_key)

    raw = {
        dim: citywide.loc[
            (citywide["year"] == year) & (citywide["dimension"] == dim)
            & (citywide["metric"] == metric_label),
            "score",
        ].mean()
        for dim in ("Race", "Income")
    }
    adjusted = {dim: _wmean(per_type[dim], per_type["volume"]) for dim in ("Race", "Income")}

    col_r, col_i = st.columns(2)
    with col_r:
        st.markdown("**Race — majority-Black vs. majority-White**")
        st.plotly_chart(_raw_adj_fig(raw["Race"], adjusted["Race"]), use_container_width=True,
                        key="adj_raw_race", config={"displayModeBar": False})
    with col_i:
        st.markdown("**Income — below vs. above median**")
        st.plotly_chart(_raw_adj_fig(raw["Income"], adjusted["Income"]), use_container_width=True,
                        key="adj_raw_income", config={"displayModeBar": False})

    st.caption(_adjusted_interpretation(raw, adjusted, year))

    # ── 2 — Within-type ranking ───────────────────────────────────────────────
    st.divider()
    st.subheader("Which service types are delivered most unequally?")
    st.caption(
        "Every eligible service type ranked by its own within-type equity score — the "
        "gap that remains *after* the service-mix effect is stripped out. A type low on "
        "this axis is one where the same service reaches different neighborhoods "
        "differently. Pick one below to see the raw distributions behind its score."
    )

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

        # Drill-down — raw distributions behind one type's score.
        options = ranked.sort_values(rank_dim)["SRType"].tolist()
        chosen = st.selectbox(
            "Inspect a service type's distributions",
            options,
            format_func=_short_label,
            key="adj_drill",
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

    # ── 3 — Regression ────────────────────────────────────────────────────────
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


def _adjusted_interpretation(raw: dict, adjusted: dict, year: int) -> str:
    """Plain-language reading of how the adjusted scores moved relative to raw."""
    msgs = []
    for dim in ("Race", "Income"):
        r, a = raw.get(dim), adjusted.get(dim)
        if r is None or a is None or np.isnan(r) or np.isnan(a):
            continue
        gap = a - r
        if gap >= 0.08:
            msgs.append(
                f"**{dim}:** the adjusted score ({a:.0%}) is well above the raw score "
                f"({r:.0%}) — much of the {year} {dim.lower()} gap is **mix-driven**: "
                "disadvantaged areas request structurally slower services more often."
            )
        elif gap <= -0.08:
            msgs.append(
                f"**{dim}:** the adjusted score ({a:.0%}) is *below* the raw score "
                f"({r:.0%}) — the service mix was masking a within-type {dim.lower()} gap."
            )
        else:
            msgs.append(
                f"**{dim}:** adjusted ({a:.0%}) and raw ({r:.0%}) are close — the "
                f"{dim.lower()} gap is mostly in **how the same service is delivered**, "
                "not in the mix of services requested."
            )
    return "  \n".join(msgs)
