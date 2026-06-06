"""Area Embedding — Tab 3.

A 2D projection of Baltimore's geographies by *what they ask 311 for* — every
tract or CSA, for every year, placed in a single shared coordinate space fit
once across the whole history. Because the space doesn't get re-fit per year,
a geography's movement between frames reflects real change in usage patterns
rather than the axes drifting underneath it — the animated year slider traces
genuine trajectories, not coordinate-system noise.
"""
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st
from sklearn.decomposition import PCA
from sklearn.preprocessing import StandardScaler

from components.srtype_shared import CATEGORY_NAMES, MIN_GEO_SRTYPE_N, load_geo_srtype_history

# Minimum total requests in a (geo, year) row for its usage-share vector to be
# meaningful — distinct from MIN_GEO_SRTYPE_N, which suppresses individual cells.
_MIN_GEO_YEAR_TOTAL = 50

# Restrict the CLR transform to the K most common features by mean share —
# anchors the embedding to substantively meaningful categories/types instead of
# letting thin, high-variance ones (whose log-ratios swing wildly on small counts)
# dominate with noise. Empirically nearly doubled variance explained vs. either
# raw-share scaling or an unrestricted CLR.
_TOP_K_CATEGORIES = 15
_TOP_K_SRTYPES = 30

# Individual SRTypes are ranked by pooled volume across all years (not per-year),
# so the same column set persists across years and year-to-year movement is valid.
_SRTYPE_POOL_RANK_N = 100

_PSEUDOCOUNT = 1e-4

_FEATURE_SETS = {
    "High-level categories": "category",
    "Individual service types": "srtype",
}

_DEMO_COLOR_OPTIONS = {
    "% Black population": "pct_black",
    "% White population": "pct_white",
    "Median household income": "median_income",
}


def _usage_share_matrix(history: pd.DataFrame, feature_set: str) -> pd.DataFrame:
    """Wide `(geoid, year) x feature` share matrix — each row sums to 1."""
    df = history[
        (history["total_requests"] >= MIN_GEO_SRTYPE_N)
        & history["SRType"].astype(str).str.contains("-")
    ].copy()

    if feature_set == "category":
        df["_feature"] = df["SRType"].str.split("-").str[0].str.strip()
    else:
        top_types = (
            df.groupby("SRType")["total_requests"].sum()
            .sort_values(ascending=False).head(_SRTYPE_POOL_RANK_N).index
        )
        df = df[df["SRType"].isin(top_types)]
        df["_feature"] = df["SRType"]

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
    data_dir: Path, geo_key: str, feature_set: str,
) -> tuple[pd.DataFrame, list[str], tuple[float, float]]:
    """2D PCA embedding of every `(geoid, year)` row, fit ONCE on the pooled matrix.

    Fitting `StandardScaler` + `PCA` once across all years — rather than per
    year — is what makes the animated trajectory view meaningful: every point
    shares one fixed coordinate system, so movement between frames is real
    change, not axes re-fit and rotated under a stable cluster.

    Returns `(embedding, feature_cols, (pc1_variance_ratio, pc2_variance_ratio))`.
    `embedding` carries `geoid`, `year`, the share columns, and `x` / `y`.
    """
    top_k = _TOP_K_CATEGORIES if feature_set == "category" else _TOP_K_SRTYPES
    history = load_geo_srtype_history(data_dir, geo_key)
    if history.empty:
        return pd.DataFrame(), [], (float("nan"), float("nan"))

    shares = _usage_share_matrix(history, feature_set)
    if shares.empty or shares.shape[1] < top_k:
        return pd.DataFrame(), [], (float("nan"), float("nan"))

    transformed, feature_cols = _clr(shares, top_k)
    X = StandardScaler().fit_transform(transformed)
    pca = PCA(n_components=2)
    xy = pca.fit_transform(X)

    embedding = shares[feature_cols].reset_index()
    embedding["x"] = xy[:, 0]
    embedding["y"] = xy[:, 1]
    var = (float(pca.explained_variance_ratio_[0]), float(pca.explained_variance_ratio_[1]))
    return embedding, feature_cols, var


def _dominant_feature_labels(embedding: pd.DataFrame, feature_cols: list[str], feature_set: str) -> pd.Series:
    """The feature with the largest share in each row — a readable categorical color key."""
    dominant = embedding[feature_cols].idxmax(axis=1)
    if feature_set == "category":
        return dominant.map(lambda c: CATEGORY_NAMES.get(c, c))
    return dominant


def render_area_embedding(data_dir: Path, demographics: pd.DataFrame | None, geo_key: str, year: int) -> None:
    st.caption(
        "Where does each neighborhood sit in the citywide landscape of *what it "
        "asks 311 for*? Every tract or CSA, for every year, is projected into a "
        "single shared 2D space — fit once across the full history — so a point's "
        "movement between frames reflects real change in usage mix, not the "
        "coordinate system shifting under it. Press play to trace trajectories."
    )

    ctrl_geo, ctrl_feat, ctrl_color = st.columns([2, 2, 3])

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

    with ctrl_feat:
        feature_label = st.radio(
            "Usage features", list(_FEATURE_SETS.keys()),
            horizontal=True, key="area_emb_feature_set",
        )
        feature_set = _FEATURE_SETS[feature_label]

    embedding, feature_cols, var = compute_usage_embedding(data_dir, geo_key, feature_set)

    if embedding.empty:
        st.info(
            "Not enough usage history at this geographic level to build a "
            "trustworthy embedding — try the other geographic unit or feature set."
        )
        return

    embedding = embedding.copy()
    embedding["Dominant service category"] = _dominant_feature_labels(embedding, feature_cols, feature_set)

    color_options = {"Dominant service category": "Dominant service category"}
    if demographics is not None:
        demo_cols = [c for c in _DEMO_COLOR_OPTIONS.values() if c in demographics.columns]
        if demo_cols:
            embedding = embedding.merge(demographics[["geoid"] + demo_cols], on="geoid", how="left")
            for label, col in _DEMO_COLOR_OPTIONS.items():
                if col in demo_cols:
                    color_options[label] = col

    with ctrl_color:
        color_label = st.selectbox("Color by", list(color_options.keys()), key="area_emb_color")
        color_col = color_options[color_label]

    pc1_pct, pc2_pct = var[0] * 100, var[1] * 100
    feature_noun = "high-level categories" if feature_set == "category" else "individual service types"
    st.caption(
        f"The first two principal components capture **{pc1_pct:.0f}%** (PC1) and "
        f"**{pc2_pct:.0f}%** (PC2) of the variation in {feature_noun} usage mix — "
        f"**{pc1_pct + pc2_pct:.0f}% combined**. That's a moderate but real signal: "
        "read clusters and trajectories here as suggestive groupings, not a "
        "complete description of how these areas differ."
    )

    is_categorical = color_col == "Dominant service category"
    years_sorted = sorted(int(y) for y in embedding["year"].unique())

    fig = px.scatter(
        embedding.sort_values("year"),
        x="x", y="y",
        animation_frame="year",
        animation_group="geoid",
        color=color_col,
        hover_name="geoid",
        labels={"x": "PC1", "y": "PC2", color_col: color_label},
        category_orders={"year": years_sorted},
        color_continuous_scale="Viridis" if not is_categorical else None,
    )
    fig.update_traces(marker=dict(size=10, opacity=0.8, line=dict(width=0.5, color="white")))
    fig.update_layout(
        height=640,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
        margin=dict(l=10, r=10, t=10, b=10),
    )

    # Fix axis ranges across frames: the PCA is fit once on the pooled matrix, so
    # the space itself is stable. Without an explicit range, Plotly autoscales
    # each frame to its own points and trajectories appear to jitter even when
    # an area hasn't actually moved.
    x_pad = (embedding["x"].max() - embedding["x"].min()) * 0.05
    y_pad = (embedding["y"].max() - embedding["y"].min()) * 0.05
    fig.update_xaxes(range=[embedding["x"].min() - x_pad, embedding["x"].max() + x_pad])
    fig.update_yaxes(range=[embedding["y"].min() - y_pad, embedding["y"].max() + y_pad])

    # Open on the year selected elsewhere in the dashboard rather than always the
    # earliest — swap the initial trace data to that frame and move the slider
    # knob to match, so the view a reader lands on matches their current context.
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

    st.plotly_chart(fig, use_container_width=True)

    st.caption(
        "Hover a point for its geography ID; press the play button below the "
        "chart, or drag the slider, to step through years one at a time."
    )
