"""Area Embedding — Tab 3.

A 2D projection of Baltimore's geographies by *what they ask 311 for* — every
tract or CSA, for every year, placed in a single shared coordinate space fit
once across the whole history. Because the space doesn't get re-fit per year,
a geography's movement between frames reflects real change in usage patterns
rather than the axes drifting underneath it — the animated year slider traces
genuine trajectories, not coordinate-system noise.

The embedding is always built from high-level service categories (SW, HCD, WW,
etc.) which produce stable, interpretable clusters. Individual SRType ("top
service type") is used for point coloring — a more granular label that reveals
*which* subtype drives each neighbourhood, without letting thin, high-variance
types destabilise the coordinate space.
"""
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st
from sklearn.cluster import KMeans
from sklearn.decomposition import PCA
from sklearn.preprocessing import QuantileTransformer, RobustScaler

from components.srtype_shared import CATEGORY_NAMES, MIN_GEO_SRTYPE_N, load_geo_srtype_history

# Minimum total requests in a (geo, year) row for its usage-share vector to be
# meaningful — distinct from MIN_GEO_SRTYPE_N, which suppresses individual cells.
_MIN_GEO_YEAR_TOTAL = 200

# Restrict the CLR transform to the K most common features by mean share —
# anchors the embedding to substantively meaningful categories instead of
# letting thin, high-variance ones (whose log-ratios swing wildly on small
# counts) dominate with noise.
_TOP_K_CATEGORIES = 15

_PSEUDOCOUNT = 1e-4
_N_CLUSTERS = 3

# Max distinct SRTypes shown as named colours; remainder grouped as "Other".
# Keeps the legend readable (≤13 entries instead of 30+).
_TOP_SRTYPE_SHOW = 12

_DEMO_COLOR_OPTIONS = {
    "% Black population": "pct_black",
    "% White population": "pct_white",
    "Median household income": "median_income",
}

# Demographic-space embedding input features. The pipeline now writes these
# columns to `{tract,csa}_demographics.csv`; `compute_demographic_embedding`
# uses whichever subset is actually present, so adding more features to the
# pipeline CSV automatically enriches the embedding with no code change here.
_DEMO_FEATURE_COLS = [
    "pct_black", "pct_white",        # race
    "pct_hispanic",                   # ethnicity (distinct axis from race in Census conventions)
    "median_income", "pct_poverty",   # economic position
    "pct_bachelors_plus",             # educational attainment
    "pct_under18", "pct_65plus",      # age structure (two poles of the age distribution)
    "median_age",                     # age scalar — complementary to the shares
]

_SERVICE_COLOR_OPTIONS = {
    "Predominant service type": "top_sr_type",
    "Requests per 1,000 residents": "requests_per_1k",
    "Median days to close": "median_days_to_close",
}

_VIEWS = {
    "Service usage": "usage",
    "Demographic profile": "demographic",
}

# Letter labels for clusters, ordered left-to-right by mean x in PCA space.
_CLUSTER_LETTERS = ["A", "B", "C"]


def _usage_share_matrix(history: pd.DataFrame) -> pd.DataFrame:
    """Wide `(geoid, year) × category` share matrix — each row sums to 1.

    ECC types (information/dispatch calls, no actual service delivery) are
    excluded — they inflate a geography's usage share without reflecting what
    services that area actually receives, causing ECC-heavy geographies to
    appear as outliers far from every operational cluster.
    """
    df = history[
        (history["total_requests"] >= MIN_GEO_SRTYPE_N)
        & history["SRType"].astype(str).str.contains("-")
        & ~history["SRType"].astype(str).str.startswith("ECC-")
    ].copy()

    df["_feature"] = df["SRType"].str.split("-").str[0].str.strip()

    pivot = df.pivot_table(
        index=["geoid", "year"], columns="_feature", values="total_requests",
        aggfunc="sum", fill_value=0,
    )
    totals = pivot.sum(axis=1)
    keep = totals >= _MIN_GEO_YEAR_TOTAL
    return pivot[keep].div(totals[keep], axis=0)


def _clr(shares: pd.DataFrame, top_k: int) -> tuple[np.ndarray, list[str]]:
    """Centered log-ratio transform of the `top_k` highest-mean-share columns.

    Usage shares sum to 1 per row — compositional data that violates the
    Euclidean assumptions PCA relies on (raw shares + scaling explained only
    ~20-27% of variance in 2D in validation). CLR — `log(share) - row_mean(log(share))`
    — is the standard fix; restricting to the top-K columns by mean share first
    keeps thin, noisy categories from dominating the transformed space.
    """
    keep = shares.mean().sort_values(ascending=False).head(top_k).index.tolist()
    sub = shares[keep]
    renormalized = sub.div(sub.sum(axis=1), axis=0)
    logs = np.log(renormalized.to_numpy() + _PSEUDOCOUNT)
    return logs - logs.mean(axis=1, keepdims=True), keep


@st.cache_data
def compute_usage_embedding(
    data_dir: Path, geo_key: str,
) -> tuple[pd.DataFrame, list[str], tuple[float, float]]:
    """2D PCA embedding of every `(geoid, year)` row using high-level categories.

    Fitting `QuantileTransformer` + `PCA` once across all years — rather than
    per year — is what makes the animated trajectory view meaningful: every
    point shares one fixed coordinate system, so movement between frames is
    real change, not axes re-fit and rotated under a stable cluster.

    Returns `(embedding, feature_cols, (pc1_variance_ratio, pc2_variance_ratio))`.
    `embedding` carries `geoid`, `year`, the raw category-share columns, and `x`/`y`.
    """
    history = load_geo_srtype_history(data_dir, geo_key)
    if history.empty:
        return pd.DataFrame(), [], (float("nan"), float("nan"))

    shares = _usage_share_matrix(history)
    if shares.empty or shares.shape[1] < _TOP_K_CATEGORIES:
        return pd.DataFrame(), [], (float("nan"), float("nan"))

    transformed, feature_cols = _clr(shares, _TOP_K_CATEGORIES)

    # QuantileTransformer maps each CLR column independently to a Gaussian,
    # regardless of how skewed or sparse the column is. This is the right tool
    # here because most usage-space features are heavily zero-inflated: e.g. FCPF
    # (parking citations) is near 0% for 98% of CSA-years and 24-64% for Downtown
    # alone — making standard outlier-resistance approaches brittle when IQR ≈ 0.
    n_q = min(len(shares), 300)
    X = QuantileTransformer(
        n_quantiles=n_q, output_distribution="normal", random_state=42,
    ).fit_transform(transformed)
    pca = PCA(n_components=2)
    xy = pca.fit_transform(X)

    embedding = shares[feature_cols].reset_index()
    embedding["x"] = xy[:, 0]
    embedding["y"] = xy[:, 1]
    var = (float(pca.explained_variance_ratio_[0]), float(pca.explained_variance_ratio_[1]))
    return embedding, feature_cols, var


@st.cache_data
def _top_srtype_by_geo_year(data_dir: Path, geo_key: str) -> pd.DataFrame:
    """Top individual SRType (by volume) for each (geoid, year) — used as subcategory colour."""
    history = load_geo_srtype_history(data_dir, geo_key)
    if history.empty:
        return pd.DataFrame(columns=["geoid", "year", "top_srtype"])
    df = history[
        (history["total_requests"] >= MIN_GEO_SRTYPE_N)
        & history["SRType"].astype(str).str.contains("-")
        & ~history["SRType"].astype(str).str.startswith("ECC-")
    ].copy()
    if df.empty:
        return pd.DataFrame(columns=["geoid", "year", "top_srtype"])
    top = (
        df.sort_values("total_requests", ascending=False)
        .drop_duplicates(subset=["geoid", "year"])
        [["geoid", "year", "SRType"]]
        .rename(columns={"SRType": "top_srtype"})
    )
    return top.reset_index(drop=True)


@st.cache_data
def compute_demographic_embedding(
    demographics: pd.DataFrame,
) -> tuple[pd.DataFrame, list[str], tuple[float, float]]:
    """2D PCA embedding of every geography's ACS demographic profile.

    Unlike the usage space, this is a single, year-independent snapshot (ACS
    2023 5-year estimates) — each geography appears once, not animated across
    years, and the input is low-dimensional enough that this is closer to a
    "light PCA" than the usage space's compositional-data treatment.

    Returns `(embedding, feature_cols, (pc1_variance_ratio, pc2_variance_ratio))`.
    `embedding` carries `geoid`, the feature columns, and `x` / `y`.
    """
    cols = [c for c in _DEMO_FEATURE_COLS if c in demographics.columns]
    df = demographics.dropna(subset=cols) if cols else demographics.iloc[0:0]
    if len(cols) < 2 or len(df) < 3:
        return pd.DataFrame(), [], (float("nan"), float("nan"))

    # RobustScaler neutralises income's heavy-tailed distribution (a handful of
    # census tracts with very high or very low median income would otherwise
    # compress the main cluster if StandardScaler were used).
    X = RobustScaler().fit_transform(df[cols].to_numpy())
    pca = PCA(n_components=2)
    xy = pca.fit_transform(X)

    embedding = df[["geoid"] + cols].reset_index(drop=True)
    embedding["x"] = xy[:, 0]
    embedding["y"] = xy[:, 1]
    var = (float(pca.explained_variance_ratio_[0]), float(pca.explained_variance_ratio_[1]))
    return embedding, cols, var


def _assign_clusters(embedding: pd.DataFrame, n_clusters: int = _N_CLUSTERS) -> pd.DataFrame:
    """Assign each geoid to a cluster based on its mean (x, y) across all years.

    Clusters are sorted left-to-right by mean x so letters (A/B/C) are stable
    across re-runs regardless of KMeans initialisation ordering.
    Returns a DataFrame with columns [geoid, cluster_label].
    """
    mean_pos = embedding.groupby("geoid")[["x", "y"]].mean().reset_index()
    km = KMeans(n_clusters=n_clusters, random_state=42, n_init=10)
    mean_pos["_cid"] = km.fit_predict(mean_pos[["x", "y"]])
    order = mean_pos.groupby("_cid")["x"].mean().sort_values().index.tolist()
    remap = {old: i for i, old in enumerate(order)}
    mean_pos["_cid"] = mean_pos["_cid"].map(remap)
    mean_pos["cluster_label"] = mean_pos["_cid"].map(
        {i: letter for i, letter in enumerate(_CLUSTER_LETTERS[:n_clusters])}
    )
    return mean_pos[["geoid", "cluster_label"]]


def _dedup_legend(fig) -> None:
    """Hide duplicate legend entries in an animated Plotly scatter.

    Animated scatter creates one trace per unique colour category per frame;
    all but the first occurrence have redundant legend entries.
    """
    seen: set[str] = set()
    for trace in fig.data:
        name = trace.name or ""
        if name in seen:
            trace.update(showlegend=False)
        else:
            seen.add(name)


def _top_legend_layout(is_categorical: bool) -> dict:
    """Shared layout fragment that pins the legend/colorbar to the top of the chart."""
    base = dict(margin=dict(l=10, r=10, t=10, b=10))
    if is_categorical:
        base["legend"] = dict(
            orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0,
        )
    else:
        base["coloraxis_colorbar"] = dict(
            orientation="h",
            yanchor="bottom", y=1.02,
            xanchor="center", x=0.5,
            thickness=15, len=0.6,
            title=dict(side="bottom"),
        )
    return base


def _render_cluster_bar(
    embedding: pd.DataFrame, feature_cols: list[str], year: int,
) -> None:
    """100% stacked bar — high-level service category share per cluster for `year`."""
    year_df = embedding[embedding["year"] == year]
    if year_df.empty or "cluster_label" not in year_df.columns:
        st.info(f"No data available for {year} at this geographic level.")
        return

    cluster_sizes = year_df.groupby("cluster_label").size().to_dict()

    # Mean share per category within each cluster (unweighted across geos — consistent
    # with how clusters were formed, and appropriate for characterising each cluster's
    # "typical" usage mix rather than its total volume).
    cluster_shares = (
        year_df.groupby("cluster_label")[feature_cols].mean().reset_index()
    )

    # Renormalize rows to 1.0 — feature_cols cover only the top-K categories, so
    # their shares may not sum to exactly 1 per row.
    row_totals = cluster_shares[feature_cols].sum(axis=1).replace(0, np.nan)
    cluster_shares[feature_cols] = cluster_shares[feature_cols].div(row_totals, axis=0)

    # Determine dominant category per cluster for informative x-axis labels
    dominant = cluster_shares.set_index("cluster_label")[feature_cols].idxmax(axis=1)
    dominant_name = dominant.map(lambda c: CATEGORY_NAMES.get(c, c))

    cluster_shares["Cluster"] = cluster_shares["cluster_label"].map(
        lambda c: f"Cluster {c} · {dominant_name.get(c, '')} (n={cluster_sizes.get(c, 0)})"
    )

    melted = cluster_shares.melt(
        id_vars=["cluster_label", "Cluster"],
        value_vars=feature_cols,
        var_name="category",
        value_name="share",
    )
    melted["Category"] = melted["category"].map(lambda c: CATEGORY_NAMES.get(c, c))

    # Sort categories by global mean share descending — most common sits at the
    # bottom of every bar (aligned on baseline), making cross-cluster comparison easier.
    cat_order = (
        melted.groupby("Category")["share"].mean()
        .sort_values(ascending=False).index.tolist()
    )

    # Cluster x-axis order: A → B → C
    cluster_order = sorted(cluster_shares["Cluster"].tolist(),
                           key=lambda s: s.split("·")[0].strip())

    fig = px.bar(
        melted,
        x="Cluster", y="share",
        color="Category",
        category_orders={"Category": cat_order, "Cluster": cluster_order},
        labels={"share": "Share of top service categories", "Cluster": ""},
        color_discrete_sequence=px.colors.qualitative.Safe,
    )
    fig.update_yaxes(tickformat=".0%")
    fig.update_layout(
        barmode="stack",
        height=420,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
        margin=dict(l=10, r=10, t=10, b=10),
        yaxis_title="",
    )
    st.plotly_chart(fig, use_container_width=True)


def _render_usage_view(
    data_dir: Path, demographics: pd.DataFrame | None, geo_key: str, year: int,
) -> None:
    st.caption(
        "Where does each neighborhood sit in the citywide landscape of *what it "
        "asks 311 for*? Every tract or CSA, for every year, is projected into a "
        "single shared 2D space — built from high-level service categories — so a "
        "point's movement between frames reflects real change in usage mix, not the "
        "coordinate system shifting under it. Press play to trace trajectories."
    )

    embedding, feature_cols, var = compute_usage_embedding(data_dir, geo_key)

    if embedding.empty:
        st.info(
            "Not enough usage history at this geographic level to build a "
            "trustworthy embedding — try the other geographic unit."
        )
        return

    embedding = embedding.copy()

    # Cluster each geoid by its mean position across all years — persistent labels
    # that don't shift frame to frame even though the scatter is animated.
    cluster_df = _assign_clusters(embedding)
    embedding = embedding.merge(cluster_df, on="geoid", how="left")

    # Top individual SRType per (geoid, year) — the subcategory colour signal.
    top_srtype_df = _top_srtype_by_geo_year(data_dir, geo_key)
    embedding = embedding.merge(top_srtype_df, on=["geoid", "year"], how="left")

    # Cap legend to the _TOP_SRTYPE_SHOW most frequent types; group the tail as "Other".
    srtype_freq = embedding["top_srtype"].value_counts()
    top_n = srtype_freq.head(_TOP_SRTYPE_SHOW).index.tolist()
    embedding["srtype_color"] = embedding["top_srtype"].where(
        embedding["top_srtype"].isin(top_n), "Other"
    )
    # Colour order: most-frequent types first, "Other" last
    srtype_order = top_n + (["Other"] if embedding["srtype_color"].eq("Other").any() else [])

    # Build colour options: subcategory first, then demographics
    color_options: dict[str, str] = {"Top service type": "srtype_color"}
    if demographics is not None:
        demo_cols = [c for c in _DEMO_COLOR_OPTIONS.values() if c in demographics.columns]
        if demo_cols:
            embedding = embedding.merge(
                demographics[["geoid"] + demo_cols], on="geoid", how="left",
            )
            for label, col in _DEMO_COLOR_OPTIONS.items():
                if col in demo_cols:
                    color_options[label] = col

    color_label = st.selectbox("Color by", list(color_options.keys()), key="area_emb_color")
    color_col = color_options[color_label]
    is_categorical = color_col == "srtype_color"

    pc1_pct, pc2_pct = var[0] * 100, var[1] * 100
    st.caption(
        f"High-level categories as features — PC1 captures **{pc1_pct:.0f}%** and "
        f"PC2 **{pc2_pct:.0f}%** of usage-mix variation "
        f"(**{pc1_pct + pc2_pct:.0f}% combined**). "
        "Read clusters and trajectories as suggestive groupings, not a complete picture."
    )

    years_sorted = sorted(int(y) for y in embedding["year"].unique())

    fig = px.scatter(
        embedding.sort_values("year"),
        x="x", y="y",
        animation_frame="year",
        animation_group="geoid",
        color=color_col,
        hover_name="geoid",
        hover_data={
            "cluster_label": True,
            "top_srtype": True,
            "srtype_color": False,  # shown via colour, not hover
        },
        labels={
            "x": "PC1", "y": "PC2",
            color_col: color_label,
            "cluster_label": "Cluster",
            "top_srtype": "Top type",
        },
        category_orders=(
            {"year": years_sorted, color_col: srtype_order}
            if is_categorical
            else {"year": years_sorted}
        ),
        color_continuous_scale="Viridis" if not is_categorical else None,
    )
    fig.update_traces(marker=dict(size=10, opacity=0.8, line=dict(width=0.5, color="white")))
    fig.update_layout(height=640, **_top_legend_layout(is_categorical))

    # Fix axis ranges across frames so the animation doesn't jitter. Use 5th/95th
    # percentile: genuine outliers (Downtown's FCPF, Dickeyville's SW) stay visible
    # at the edges without compressing the main cluster into 30% of the chart.
    pad = 0.08
    x5, x95 = np.percentile(embedding["x"], [5, 95])
    y5, y95 = np.percentile(embedding["y"], [5, 95])
    xw, yw = (x95 - x5) * pad, (y95 - y5) * pad
    fig.update_xaxes(range=[x5 - xw, x95 + xw])
    fig.update_yaxes(range=[y5 - yw, y95 + yw])

    # Open on the year selected elsewhere in the dashboard.
    if year in years_sorted and fig.frames:
        active_idx = years_sorted.index(year)
        fig.update(data=fig.frames[active_idx].data)
        if fig.layout.sliders:
            fig.layout.sliders[0].active = active_idx

    if fig.layout.updatemenus:
        fig.layout.updatemenus[0].x = 0
        fig.layout.updatemenus[0].y = -0.08
    if fig.layout.sliders:
        fig.layout.sliders[0].y = -0.08

    # Deduplicate legend: animated scatter creates one trace per colour category
    # per frame — all but the first occurrence are redundant legend entries.
    _dedup_legend(fig)

    st.plotly_chart(fig, use_container_width=True)
    st.caption(
        "Hover for geography ID, cluster (A/B/C), and top service type. "
        "Press play or drag the slider to trace year-by-year trajectories."
    )

    # ── Cluster profiles ──────────────────────────────────────────────────────
    geo_noun = "tracts" if geo_key == "tract" else "CSAs"
    st.subheader(f"Cluster Profiles — {year}")
    n_by_cluster = (
        embedding[embedding["year"] == year]
        .groupby("cluster_label").size().to_dict()
    )
    cluster_summary = "  ·  ".join(
        f"**{letter}** {n_by_cluster.get(letter, 0)} {geo_noun}"
        for letter in _CLUSTER_LETTERS[:_N_CLUSTERS]
    )
    st.caption(
        f"Each geography's mean position across all years determines its cluster. "
        f"{cluster_summary}. "
        "Bars show how each cluster's typical request mix is distributed across the "
        "top service categories — revealing the operational character of each peer group."
    )
    _render_cluster_bar(embedding, feature_cols, year)


def _render_demographic_view(
    demographics: pd.DataFrame | None, geo_key: str, df: pd.DataFrame | None, year: int,
) -> None:
    st.caption(
        "The inverse view: where does each neighborhood sit by *who lives there*? "
        "This space comes from a single, year-independent ACS 2023 snapshot — race, "
        "income — so each geography is one fixed point (no trajectory; the profile "
        "doesn't move year to year the way usage does). Coloring it by a "
        f"**{year}** service-side measure tests the inverse question directly: do "
        "areas that look alike demographically also look alike in how they use "
        "and experience 311 — or do the two diverge?"
    )

    if demographics is None:
        st.info(
            f"Demographic data unavailable — `{geo_key}_demographics.csv` not found "
            "in `data/processed/`. Re-run the pipeline to generate it."
        )
        return

    embedding, feature_cols, var = compute_demographic_embedding(demographics)
    if embedding.empty:
        st.info("Not enough demographic coverage at this geographic level to build an embedding.")
        return

    embedding = embedding.copy()
    color_options = {}
    if df is not None:
        for label, col in _SERVICE_COLOR_OPTIONS.items():
            if col in df.columns:
                color_options[label] = col

    color_col = color_label = None
    is_categorical = True
    if color_options:
        color_label = st.selectbox("Color by", list(color_options.keys()), key="area_emb_demo_color")
        color_col = color_options[color_label]
        if df is not None and color_col in df.columns:
            embedding = embedding.merge(df[["geoid", color_col]], on="geoid", how="left")
        is_categorical = color_col == "top_sr_type"

    pc1_pct, pc2_pct = var[0] * 100, var[1] * 100
    _topic = {
        "pct_black": "race", "pct_white": "race",
        "pct_hispanic": "ethnicity",
        "median_income": "income/poverty", "pct_poverty": "income/poverty",
        "pct_bachelors_plus": "education",
        "pct_under18": "age", "pct_65plus": "age", "median_age": "age",
    }
    feature_phrase = " and ".join(dict.fromkeys(_topic.get(c, c) for c in feature_cols))
    st.caption(
        f"The first two principal components capture **{pc1_pct:.0f}%** (PC1) and "
        f"**{pc2_pct:.0f}%** (PC2) of the variation in {feature_phrase} — "
        f"**{pc1_pct + pc2_pct:.0f}% combined** — across {len(embedding)} "
        f"{'tracts' if geo_key == 'tract' else 'CSAs'}. *(P4d-6a will broaden the "
        "profile with age, ethnicity, and education variables, sharpening this view.)*"
    )

    fig = px.scatter(
        embedding,
        x="x", y="y",
        color=color_col,
        hover_name="geoid",
        hover_data={c: True for c in feature_cols},
        labels={"x": "PC1", "y": "PC2", **({color_col: color_label} if color_col else {})},
        color_continuous_scale="Viridis" if not is_categorical else None,
    )
    fig.update_traces(marker=dict(size=11, opacity=0.85, line=dict(width=0.5, color="white")))
    fig.update_layout(height=600, **_top_legend_layout(is_categorical))

    _dedup_legend(fig)
    st.plotly_chart(fig, use_container_width=True)
    st.caption("Hover a point for its geography ID and demographic profile.")


def render_area_embedding(
    data_dir: Path,
    demographics: pd.DataFrame | None,
    geo_key: str,
    year: int,
    df: pd.DataFrame | None = None,
) -> None:
    st.caption(
        "Two complementary lenses on the same geographies: what each one *asks "
        "311 for* (service-usage space, trended across years) and *who lives "
        "there* (demographic profile, a single ACS 2023 snapshot). Switch between "
        "them below — each can be colored by the other side's variables, so a "
        "reader can ask either half of the same question: does service usage "
        "track demographics, or do the two diverge?"
    )

    ctrl_geo, ctrl_view = st.columns([2, 3])

    with ctrl_geo:
        # Two-way sync with the shared `geo_level` (mirrors the Service Equity
        # Explorer's `cat_eq_geo_*` pattern): only overwrite this widget's keyed
        # state when `geo_level` changed *elsewhere*, so a fresh click here isn't
        # clobbered before it propagates — Streamlit ignores `index` once a
        # widget's keyed state is set, so a one-way default isn't enough.
        _curr_geo = st.session_state.get("geo_level", "Census Tract")
        if st.session_state.get("area_emb_geo_seen") != _curr_geo:
            st.session_state["area_emb_geo_choice"] = _curr_geo
            st.session_state["area_emb_geo_seen"] = _curr_geo
        new_geo = st.radio(
            "Geographic unit", ["Census Tract", "CSA"],
            horizontal=True, key="area_emb_geo_choice",
        )
        if new_geo != _curr_geo:
            st.session_state["geo_level"] = new_geo
            st.session_state["area_emb_geo_seen"] = new_geo
            st.rerun()

    with ctrl_view:
        view_label = st.radio(
            "View", list(_VIEWS.keys()), horizontal=True, key="area_emb_view",
        )
        view = _VIEWS[view_label]

    st.divider()

    if view == "usage":
        _render_usage_view(data_dir, demographics, geo_key, year)
    else:
        _render_demographic_view(demographics, geo_key, df, year)
