"""Area Embedding — Tab 3.

Each geography placed in a shared 2D space — by demographic profile (ACS) or
by 311 service-request mix. Color by the opposite dimension to test whether
demographic similarity predicts service experience.
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

# CLR transform uses the top-K categories by mean share — enough to capture the
# dominant structure without letting thin, high-variance ones dominate.
_TOP_K_CATEGORIES = 15

_PSEUDOCOUNT = 1e-4
_N_CLUSTERS = 3

# Max distinct SRTypes shown as named colours; remainder grouped as "Other".
_TOP_SRTYPE_SHOW = 12

# Cluster bar shows this many named categories; rest grouped as "Other".
_BAR_TOP_N = 5

# Columns containing fractions (0–1) that should display as percentages (0–100)
_PCT_COLS = {
    "pct_black", "pct_white", "pct_hispanic", "pct_poverty",
    "pct_bachelors_plus", "pct_under18", "pct_65plus",
}

# Clean hover/axis labels for demographic columns
_DEMO_HOVER_NAMES: dict[str, str] = {
    "pct_black":       "Black pop. %",
    "pct_white":       "White pop. %",
    "pct_hispanic":    "Hispanic pop. %",
    "pct_poverty":     "Poverty rate %",
    "pct_bachelors_plus": "Bachelor's+ %",
    "pct_under18":     "Under 18 %",
    "pct_65plus":      "Age 65+ %",
    "median_income":   "Median income ($)",
    "median_age":      "Median age",
}

_DEMO_COLOR_OPTIONS = {
    "% Black population": "pct_black",
    "% White population": "pct_white",
    "Median household income": "median_income",
}

_DEMO_FEATURE_COLS = [
    "pct_black", "pct_white",
    "pct_hispanic",
    "median_income", "pct_poverty",
    "pct_bachelors_plus",
    "pct_under18", "pct_65plus",
    "median_age",
]

# Service metrics for coloring the demographic view — leading options are
# continuous delivery metrics so the default shows service disparities directly.
_SERVICE_COLOR_OPTIONS = {
    "Median days to close": "median_days_to_close",
    "Closure rate": "closure_rate",
    "Requests per 1,000 residents": "requests_per_1k",
    "Predominant service type": "top_sr_type",
}

_VIEWS = {
    "Demographic profile": "demographic",
    "Service usage": "usage",
}

_CLUSTER_LETTERS = ["A", "B", "C"]


# ── Embedding computation ─────────────────────────────────────────────────────

def _usage_share_matrix(history: pd.DataFrame) -> pd.DataFrame:
    """Wide `(geoid, year) × category` share matrix — each row sums to 1."""
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
    """Centered log-ratio of the top-k highest-mean-share columns."""
    keep = shares.mean().sort_values(ascending=False).head(top_k).index.tolist()
    sub = shares[keep]
    renorm = sub.div(sub.sum(axis=1), axis=0)
    logs = np.log(renorm.to_numpy() + _PSEUDOCOUNT)
    return logs - logs.mean(axis=1, keepdims=True), keep


@st.cache_data
def compute_usage_embedding(
    data_dir: Path, geo_key: str,
) -> tuple[pd.DataFrame, list[str], tuple[float, float]]:
    """2D PCA of every (geoid, year) by high-level service category mix.

    Fit once across all years so animation frames share one coordinate system —
    movement between frames reflects real change, not axes rotating under it.
    Returns (embedding, feature_cols, (pc1_var, pc2_var)).
    """
    history = load_geo_srtype_history(data_dir, geo_key)
    if history.empty:
        return pd.DataFrame(), [], (float("nan"), float("nan"))
    shares = _usage_share_matrix(history)
    if shares.empty or shares.shape[1] < _TOP_K_CATEGORIES:
        return pd.DataFrame(), [], (float("nan"), float("nan"))
    transformed, feature_cols = _clr(shares, _TOP_K_CATEGORIES)
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
    """Top individual SRType (by volume) for each (geoid, year)."""
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
    return (
        df.sort_values("total_requests", ascending=False)
        .drop_duplicates(subset=["geoid", "year"])
        [["geoid", "year", "SRType"]]
        .rename(columns={"SRType": "top_srtype"})
        .reset_index(drop=True)
    )


@st.cache_data
def compute_demographic_embedding(
    demographics: pd.DataFrame,
) -> tuple[pd.DataFrame, list[str], tuple[float, float]]:
    """2D PCA of each geography's ACS demographic profile (year-independent).

    Returns (embedding, feature_cols, (pc1_var, pc2_var)).
    """
    cols = [c for c in _DEMO_FEATURE_COLS if c in demographics.columns]
    df = demographics.dropna(subset=cols) if cols else demographics.iloc[0:0]
    if len(cols) < 2 or len(df) < 3:
        return pd.DataFrame(), [], (float("nan"), float("nan"))
    X = RobustScaler().fit_transform(df[cols].to_numpy())
    pca = PCA(n_components=2)
    xy = pca.fit_transform(X)
    embedding = df[["geoid"] + cols].reset_index(drop=True)
    embedding["x"] = xy[:, 0]
    embedding["y"] = xy[:, 1]
    var = (float(pca.explained_variance_ratio_[0]), float(pca.explained_variance_ratio_[1]))
    return embedding, cols, var


# ── Cluster assignment ────────────────────────────────────────────────────────

def _assign_clusters(embedding: pd.DataFrame, n_clusters: int = _N_CLUSTERS) -> pd.DataFrame:
    """Assign each geoid to a cluster on its mean (x, y) across all years.

    Sorted left-to-right by mean x so letters (A/B/C) are consistent across runs.
    Returns a DataFrame with [geoid, cluster_label].
    """
    mean_pos = embedding.groupby("geoid")[["x", "y"]].mean().reset_index()
    km = KMeans(n_clusters=n_clusters, random_state=42, n_init=10)
    mean_pos["_cid"] = km.fit_predict(mean_pos[["x", "y"]])
    order = mean_pos.groupby("_cid")["x"].mean().sort_values().index.tolist()
    remap = {old: i for i, old in enumerate(order)}
    mean_pos["_cid"] = mean_pos["_cid"].map(remap)
    mean_pos["cluster_label"] = mean_pos["_cid"].map(
        {i: ltr for i, ltr in enumerate(_CLUSTER_LETTERS[:n_clusters])}
    )
    return mean_pos[["geoid", "cluster_label"]]


# ── Shared chart helpers ──────────────────────────────────────────────────────

def _dedup_legend(fig) -> None:
    """Hide duplicate legend entries (animated scatter creates one per frame)."""
    seen: set[str] = set()
    for trace in fig.data:
        name = trace.name or ""
        if name in seen:
            trace.update(showlegend=False)
        else:
            seen.add(name)


def _top_legend_layout(is_categorical: bool) -> dict:
    """Layout fragment that keeps legend/colorbar at the top of the chart."""
    if is_categorical:
        return dict(
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
            margin=dict(l=10, r=10, t=10, b=10),
        )
    return dict(
        coloraxis_colorbar=dict(
            orientation="h",
            yanchor="bottom", y=1.02,
            xanchor="center", x=0.5,
            thickness=15, len=0.6,
            title=dict(side="bottom"),
        ),
        margin=dict(l=10, r=10, t=10, b=10),
    )


def _scale_pct_cols(df: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    """Return a copy of df with fraction columns (0–1) scaled to 0–100."""
    df = df.copy()
    for col in cols:
        if col in _PCT_COLS and col in df.columns:
            df[col] = (df[col] * 100).round(1)
    return df


# ── Cluster bar chart ─────────────────────────────────────────────────────────

def _render_cluster_bar(
    embedding: pd.DataFrame, feature_cols: list[str], year: int,
) -> None:
    """100% stacked bar — top-5 category share per cluster for the selected year."""
    year_df = embedding[embedding["year"] == year]
    if year_df.empty or "cluster_label" not in year_df.columns:
        st.info(f"No data for {year} at this geographic level.")
        return

    cluster_sizes = year_df.groupby("cluster_label").size().to_dict()
    cluster_shares = year_df.groupby("cluster_label")[feature_cols].mean().reset_index()

    # Identify top-_BAR_TOP_N categories by global mean share
    global_mean = year_df[feature_cols].mean()
    top_cols = global_mean.sort_values(ascending=False).head(_BAR_TOP_N).index.tolist()
    other_cols = [c for c in feature_cols if c not in top_cols]

    if other_cols:
        cluster_shares["Other"] = cluster_shares[other_cols].sum(axis=1)
    display_cols = top_cols + (["Other"] if other_cols else [])

    # Renormalize each cluster row to 100%
    row_totals = cluster_shares[display_cols].sum(axis=1).replace(0, np.nan)
    cluster_shares[display_cols] = cluster_shares[display_cols].div(row_totals, axis=0)

    # Descriptive x-axis label: dominant category + geo count
    dominant = cluster_shares.set_index("cluster_label")[top_cols].idxmax(axis=1)
    dominant_name = dominant.map(lambda c: CATEGORY_NAMES.get(c, c))
    cluster_shares["Cluster"] = cluster_shares["cluster_label"].map(
        lambda c: f"Cluster {c} · {dominant_name.get(c, '')}  (n={cluster_sizes.get(c, 0)})"
    )

    melted = cluster_shares.melt(
        id_vars=["cluster_label", "Cluster"],
        value_vars=display_cols,
        var_name="category", value_name="share",
    )
    melted["Category"] = melted["category"].map(lambda c: CATEGORY_NAMES.get(c, c))

    # Stack with most-common at the bottom (easier to compare across clusters)
    cat_order = (
        melted.groupby("Category")["share"].mean()
        .sort_values(ascending=False).index.tolist()
    )
    cluster_order = sorted(
        cluster_shares["Cluster"].tolist(),
        key=lambda s: s.split("·")[0].strip(),
    )

    fig = px.bar(
        melted,
        x="Cluster", y="share",
        color="Category",
        category_orders={"Category": cat_order, "Cluster": cluster_order},
        labels={"share": "", "Cluster": ""},
        color_discrete_sequence=px.colors.qualitative.Safe,
    )
    fig.update_yaxes(tickformat=".0%")
    fig.update_layout(
        barmode="stack",
        height=420,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
        margin=dict(l=10, r=10, t=10, b=10),
        yaxis_title="Share of requests",
    )
    st.plotly_chart(fig, use_container_width=True)


# ── View renderers (fragments: color/metric dropdown only reruns its section) ──

@st.fragment
def _render_usage_view(
    data_dir: Path, demographics: pd.DataFrame | None, geo_key: str, year: int,
) -> None:
    st.caption(
        "Every tract or CSA projected into a shared 2D space by *service-request "
        "mix* — fit once across all years so movement between frames reflects real "
        "change, not the coordinate system shifting. Press play to trace trajectories."
    )

    embedding, feature_cols, var = compute_usage_embedding(data_dir, geo_key)
    if embedding.empty:
        st.info(
            "Not enough usage history at this geographic level — "
            "try switching to CSA for a more stable embedding."
        )
        return

    embedding = embedding.copy()

    # Cluster by mean position across all years (persistent, frame-independent)
    cluster_df = _assign_clusters(embedding)
    embedding = embedding.merge(cluster_df, on="geoid", how="left")

    # Top individual SRType per (geoid, year) — the subcategory colour signal
    top_srtype_df = _top_srtype_by_geo_year(data_dir, geo_key)
    embedding = embedding.merge(top_srtype_df, on=["geoid", "year"], how="left")

    # Cap legend: top-_TOP_SRTYPE_SHOW types named, tail → "Other"
    srtype_freq = embedding["top_srtype"].value_counts()
    top_n = srtype_freq.head(_TOP_SRTYPE_SHOW).index.tolist()
    embedding["srtype_color"] = embedding["top_srtype"].where(
        embedding["top_srtype"].isin(top_n), "Other"
    )
    has_other = embedding["srtype_color"].eq("Other").any()
    srtype_order = top_n + (["Other"] if has_other else [])

    # Build colour options; merge demographic cols for coloring
    color_options: dict[str, str] = {"Top service type": "srtype_color"}
    demo_cols: list[str] = []
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
        f"High-level service categories · PC1 **{pc1_pct:.0f}%** · "
        f"PC2 **{pc2_pct:.0f}%** · combined **{pc1_pct + pc2_pct:.0f}%**"
    )

    years_sorted = sorted(int(y) for y in embedding["year"].unique())

    # Scale pct demographic columns to 0–100 for colour bar and hover readability
    display_df = _scale_pct_cols(embedding, demo_cols)

    # Build hover label map
    hover_labels: dict[str, str] = {
        "x": "PC1", "y": "PC2",
        color_col: color_label,
        "cluster_label": "Cluster",
        "top_srtype": "Top type",
        **{c: _DEMO_HOVER_NAMES.get(c, c) for c in demo_cols},
    }

    # Include demo cols in hover so context is visible regardless of colour choice
    hover_data: dict[str, bool] = {
        "cluster_label": True,
        "top_srtype": True,
        "srtype_color": False,
        **{c: True for c in demo_cols if c in display_df.columns},
    }

    fig = px.scatter(
        display_df.sort_values("year"),
        x="x", y="y",
        animation_frame="year",
        animation_group="geoid",
        color=color_col,
        hover_name="geoid",
        hover_data=hover_data,
        labels=hover_labels,
        category_orders=(
            {"year": years_sorted, color_col: srtype_order}
            if is_categorical else {"year": years_sorted}
        ),
        color_continuous_scale="Viridis" if not is_categorical else None,
    )
    fig.update_traces(marker=dict(size=10, opacity=0.8, line=dict(width=0.5, color="white")))
    fig.update_layout(height=640, **_top_legend_layout(is_categorical))

    pad = 0.08
    x5, x95 = np.percentile(embedding["x"], [5, 95])
    y5, y95 = np.percentile(embedding["y"], [5, 95])
    fig.update_xaxes(range=[x5 - (x95 - x5) * pad, x95 + (x95 - x5) * pad])
    fig.update_yaxes(range=[y5 - (y95 - y5) * pad, y95 + (y95 - y5) * pad])

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

    _dedup_legend(fig)
    st.plotly_chart(fig, use_container_width=True)
    st.caption("Hover for cluster assignment and top service type. Play or drag the slider to trace trajectories.")

    # ── Cluster profiles ──────────────────────────────────────────────────────
    geo_noun = "tracts" if geo_key == "tract" else "CSAs"
    st.subheader(f"Cluster Profiles — {year}")
    year_df = embedding[embedding["year"] == year]
    n_by_cluster = year_df.groupby("cluster_label").size().to_dict() if not year_df.empty else {}
    summary = "  ·  ".join(
        f"**{ltr}** {n_by_cluster.get(ltr, 0)} {geo_noun}"
        for ltr in _CLUSTER_LETTERS[:_N_CLUSTERS]
    )
    st.caption(
        f"Clusters assigned by mean position across all years. {summary}. "
        "Bars show how each cluster's typical request mix distributes across the top service categories."
    )
    _render_cluster_bar(embedding, feature_cols, year)


@st.fragment
def _render_demographic_view(
    demographics: pd.DataFrame | None,
    geo_key: str,
    df: pd.DataFrame | None,
    year: int,
) -> None:
    st.caption(
        "Each geography placed by *who lives there* — ACS 2023 demographic profile. "
        f"Color by a **{year}** service metric to test whether demographic similarity "
        "predicts service experience."
    )

    if demographics is None:
        st.info(
            f"`{geo_key}_demographics.csv` not found in `data/processed/`. "
            "Re-run the pipeline demographics stage to generate it."
        )
        return

    embedding, feature_cols, var = compute_demographic_embedding(demographics)
    if embedding.empty:
        st.info("Not enough demographic coverage at this geographic level.")
        return

    embedding = embedding.copy()
    color_options: dict[str, str] = {}
    if df is not None:
        for label, col in _SERVICE_COLOR_OPTIONS.items():
            if col in df.columns:
                color_options[label] = col

    color_col = color_label = None
    is_categorical = False
    if color_options:
        color_label = st.selectbox(
            "Color by (service metric)", list(color_options.keys()),
            key="area_emb_demo_color",
        )
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
    geo_count = len(embedding)
    geo_noun = "tracts" if geo_key == "tract" else "CSAs"
    st.caption(
        f"PC1 **{pc1_pct:.0f}%** · PC2 **{pc2_pct:.0f}%** · "
        f"combined **{pc1_pct + pc2_pct:.0f}%** of variation in {feature_phrase} "
        f"across {geo_count} {geo_noun}."
    )

    # Scale pct cols to 0–100 for display; build clean hover labels
    display_df = _scale_pct_cols(embedding, feature_cols)
    hover_labels: dict[str, str] = {
        "x": "PC1", "y": "PC2",
        **({color_col: color_label} if color_col else {}),
        **{c: _DEMO_HOVER_NAMES.get(c, c) for c in feature_cols},
    }

    fig = px.scatter(
        display_df,
        x="x", y="y",
        color=color_col,
        hover_name="geoid",
        hover_data={c: True for c in feature_cols},
        labels=hover_labels,
        color_continuous_scale="RdYlGn_r" if not is_categorical else None,
    )
    fig.update_traces(marker=dict(size=11, opacity=0.85, line=dict(width=0.5, color="white")))
    fig.update_layout(height=600, **_top_legend_layout(is_categorical))
    _dedup_legend(fig)
    st.plotly_chart(fig, use_container_width=True)
    st.caption("Hover for geographic ID and demographic profile values.")


# ── Public entry point ────────────────────────────────────────────────────────

def render_area_embedding(
    data_dir: Path,
    demographics: pd.DataFrame | None,
    geo_key: str,
    year: int,
    df: pd.DataFrame | None = None,
) -> None:
    st.caption(
        "Each geography embedded by *demographic profile* or by *service-request mix* — "
        "switch views and color by the opposite dimension to ask whether areas that "
        "look alike demographically receive similar 311 service."
    )

    # Default to the demographic view (most immediately actionable for equity readers)
    if "area_emb_view" not in st.session_state:
        st.session_state["area_emb_view"] = "Demographic profile"

    ctrl_geo, ctrl_view = st.columns([2, 3])

    with ctrl_geo:
        _curr_geo = st.session_state.get("geo_level", "CSA")
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
