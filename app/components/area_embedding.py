"""Area Embedding — Tab 3.

Each geography embedded by demographic profile or by service-request mix.
Switch views and color by the opposite dimension to see how areas that differ
demographically request different 311 services.

Both census tracts and CSAs are projected into the *same* 2D space — the PCA
is fit once on the combined share matrix so tracts and their containing CSA
occupy comparable positions.  CSAs naturally cluster near the centroid of their
constituent tracts because their category shares are population-weighted
aggregates.  This lets the scatter carry two layers of legibility at once:
the granular tract point cloud and the coarser CSA labels.
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

_MIN_GEO_YEAR_TOTAL = 200
_TOP_K_CATEGORIES = 15
_PSEUDOCOUNT = 1e-4
_N_CLUSTERS = 3
_TOP_SRTYPE_SHOW = 12
_BAR_TOP_N = 5

# Marker area values passed to Plotly's size= parameter.
# With size_max=16, CSA → ≈16 px diameter; Tract → ≈6 px diameter.
_SZ_CSA = 200
_SZ_TRACT = 30

_PCT_COLS = {
    "pct_black", "pct_white", "pct_hispanic", "pct_poverty",
    "pct_bachelors_plus", "pct_under18", "pct_65plus",
}

_DEMO_HOVER_NAMES: dict[str, str] = {
    "pct_black":          "Black pop.",
    "pct_white":          "White pop.",
    "pct_hispanic":       "Hispanic pop.",
    "pct_poverty":        "Poverty rate",
    "pct_bachelors_plus": "Bachelor's+",
    "pct_under18":        "Under 18",
    "pct_65plus":         "Age 65+",
    "median_income":      "Median income",
    "median_age":         "Median age",
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

_SERVICE_COLOR_OPTIONS = {
    "Predominant service type": "top_sr_type",
    "Median days to close":     "median_days_to_close",
    "Closure rate":             "closure_rate",
    "Requests per 1,000 residents": "requests_per_1k",
}

_VIEWS = {
    "Demographic profile": "demographic",
    "Service usage":       "usage",
}

_CLUSTER_LETTERS = ["A", "B", "C"]


# ── Data loaders (cached so fragments don't re-read disk) ─────────────────────

@st.cache_data
def _load_demographics(data_dir: Path, geo_key: str) -> pd.DataFrame | None:
    path = data_dir / f"{geo_key}_demographics.csv"
    return pd.read_csv(path, dtype={"geoid": str}) if path.exists() else None


@st.cache_data
def _load_metrics(data_dir: Path, geo_key: str, year: int) -> pd.DataFrame | None:
    path = data_dir / f"{geo_key}_metrics_{year}.parquet"
    return pd.read_parquet(path) if path.exists() else None


# ── Share-matrix & CLR helpers ────────────────────────────────────────────────

def _usage_share_matrix(history: pd.DataFrame) -> pd.DataFrame:
    """Wide (geoid, year) × category share matrix — each row sums to 1."""
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


def _geo_type(geoid: str) -> str:
    """'Tract' if the geoid is an 11-digit census FIPS code, else 'CSA'."""
    s = str(geoid)
    return "Tract" if (s.isdigit() and len(s) == 11) else "CSA"


# ── Combined embeddings ───────────────────────────────────────────────────────

@st.cache_data
def compute_combined_usage_embedding(
    data_dir: Path,
) -> tuple[pd.DataFrame, list[str], tuple[float, float]]:
    """Embed tracts and CSAs in one shared 2D service-usage space.

    The PCA is fit once on the union of both geo levels' share matrices so
    both coordinate systems are identical — a CSA point sits near the centroid
    of its constituent tracts because its category shares are their aggregate.

    Returns (embedding, feature_cols, (pc1_var, pc2_var)).
    embedding has columns: geoid, year, <feature_cols>, x, y, geo_type.
    """
    tract_hist = load_geo_srtype_history(data_dir, "tract")
    csa_hist = load_geo_srtype_history(data_dir, "csa")

    tract_sh = _usage_share_matrix(tract_hist) if not tract_hist.empty else pd.DataFrame()
    csa_sh = _usage_share_matrix(csa_hist) if not csa_hist.empty else pd.DataFrame()

    if tract_sh.empty and csa_sh.empty:
        return pd.DataFrame(), [], (float("nan"), float("nan"))

    # Align to union of categories; rows already sum to 1 so fill=0 is correct
    all_cats = sorted(set(
        (tract_sh.columns.tolist() if not tract_sh.empty else []) +
        (csa_sh.columns.tolist() if not csa_sh.empty else [])
    ))
    if not tract_sh.empty:
        tract_sh = tract_sh.reindex(columns=all_cats, fill_value=0.0)
    if not csa_sh.empty:
        csa_sh = csa_sh.reindex(columns=all_cats, fill_value=0.0)

    combined = pd.concat(
        [df for df in [tract_sh, csa_sh] if not df.empty], axis=0,
    )
    if combined.empty or combined.shape[1] < _TOP_K_CATEGORIES:
        return pd.DataFrame(), [], (float("nan"), float("nan"))

    transformed, feature_cols = _clr(combined, _TOP_K_CATEGORIES)
    n_q = min(len(combined), 300)
    X = QuantileTransformer(
        n_quantiles=n_q, output_distribution="normal", random_state=42,
    ).fit_transform(transformed)
    pca = PCA(n_components=2)
    xy = pca.fit_transform(X)

    emb = combined[feature_cols].reset_index()
    emb["x"] = xy[:, 0]
    emb["y"] = xy[:, 1]
    emb["geo_type"] = emb["geoid"].map(_geo_type)
    var = (float(pca.explained_variance_ratio_[0]), float(pca.explained_variance_ratio_[1]))
    return emb, feature_cols, var


@st.cache_data
def compute_combined_demographic_embedding(
    data_dir: Path,
) -> tuple[pd.DataFrame, list[str], tuple[float, float]]:
    """Embed tracts and CSAs in one shared 2D demographic space (ACS 2023).

    Returns (embedding, feature_cols, (pc1_var, pc2_var)).
    embedding has columns: geoid, geo_type, <feature_cols>, x, y.
    """
    demo_tract = _load_demographics(data_dir, "tract")
    demo_csa = _load_demographics(data_dir, "csa")

    dfs = []
    if demo_tract is not None:
        d = demo_tract.copy(); d["geo_type"] = "Tract"; dfs.append(d)
    if demo_csa is not None:
        d = demo_csa.copy(); d["geo_type"] = "CSA"; dfs.append(d)
    if not dfs:
        return pd.DataFrame(), [], (float("nan"), float("nan"))

    combined = pd.concat(dfs, ignore_index=True)
    cols = [c for c in _DEMO_FEATURE_COLS if c in combined.columns]
    df_clean = combined.dropna(subset=cols) if cols else combined.iloc[0:0]
    if len(cols) < 2 or len(df_clean) < 3:
        return pd.DataFrame(), [], (float("nan"), float("nan"))

    X = RobustScaler().fit_transform(df_clean[cols].to_numpy())
    pca = PCA(n_components=2)
    xy = pca.fit_transform(X)

    emb = df_clean[["geoid", "geo_type"] + cols].reset_index(drop=True)
    emb["x"] = xy[:, 0]
    emb["y"] = xy[:, 1]
    var = (float(pca.explained_variance_ratio_[0]), float(pca.explained_variance_ratio_[1]))
    return emb, cols, var


@st.cache_data
def _top_srtype_combined(data_dir: Path) -> pd.DataFrame:
    """Top individual SRType per (geoid, year) for both geo levels."""
    frames = []
    for geo_key in ("tract", "csa"):
        history = load_geo_srtype_history(data_dir, geo_key)
        if history.empty:
            continue
        df = history[
            (history["total_requests"] >= MIN_GEO_SRTYPE_N)
            & history["SRType"].astype(str).str.contains("-")
            & ~history["SRType"].astype(str).str.startswith("ECC-")
        ].copy()
        if df.empty:
            continue
        top = (
            df.sort_values("total_requests", ascending=False)
            .drop_duplicates(subset=["geoid", "year"])
            [["geoid", "year", "SRType"]]
            .rename(columns={"SRType": "top_srtype"})
        )
        frames.append(top)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(
        columns=["geoid", "year", "top_srtype"]
    )


# ── Cluster assignment ────────────────────────────────────────────────────────

def _assign_clusters(embedding: pd.DataFrame, n_clusters: int = _N_CLUSTERS) -> pd.DataFrame:
    """Assign each geoid to a cluster by its mean (x, y) across all years.

    Sorted left-to-right by mean x so letters (A/B/C) are consistent across runs.
    Returns DataFrame with [geoid, cluster_label].
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


# ── Chart helpers ─────────────────────────────────────────────────────────────

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
    """Pin legend/colorbar to the top of the chart in all colour modes."""
    if is_categorical:
        return dict(
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
            margin=dict(l=10, r=10, t=10, b=10),
        )
    return dict(
        coloraxis_colorbar=dict(
            orientation="h", yanchor="bottom", y=1.02,
            xanchor="center", x=0.5, thickness=15, len=0.6,
            title=dict(side="bottom"),
        ),
        margin=dict(l=10, r=10, t=10, b=10),
    )


def _scale_pct_cols(df: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    """Return a copy of df with fraction (0–1) columns scaled to 0–100."""
    df = df.copy()
    for col in cols:
        if col in _PCT_COLS and col in df.columns:
            df[col] = (df[col] * 100).round(1)
    return df


def _add_hover_fmt(
    df: pd.DataFrame, cols: list[str],
) -> tuple[pd.DataFrame, dict[str, str]]:
    """Add pre-formatted string columns for hover; return {original: hover_col}.

    Call after _scale_pct_cols() so pct values are already 0–100.
    Pct → "52.4%"; income → "$45,000".  % appears in the value, not the label.
    """
    df = df.copy()
    col_map: dict[str, str] = {}
    for col in cols:
        if col not in df.columns:
            continue
        if col in _PCT_COLS:
            hcol = f"_fmt_{col}"
            df[hcol] = df[col].round(1).astype(str) + "%"
            col_map[col] = hcol
        elif col == "median_income":
            hcol = f"_fmt_{col}"
            df[hcol] = df[col].apply(lambda x: f"${int(x):,}" if pd.notna(x) else "—")
            col_map[col] = hcol
        else:
            col_map[col] = col
    return df, col_map


def _add_viz_cols(emb: pd.DataFrame) -> pd.DataFrame:
    """Add _sz (bubble area) and _text (CSA label, blank for tracts)."""
    emb = emb.copy()
    is_csa = emb["geo_type"] == "CSA"
    emb["_sz"] = np.where(is_csa, _SZ_CSA, _SZ_TRACT)
    emb["_text"] = emb["geoid"].where(is_csa, "")
    return emb


# ── Cluster bar ───────────────────────────────────────────────────────────────

def _render_cluster_bar(
    embedding: pd.DataFrame, feature_cols: list[str], year: int,
) -> None:
    """100% stacked bar — top-5 category share per cluster for tracts in `year`.

    Uses tract rows only (CSAs are aggregates of tracts; excluding avoids
    double-counting and gives a more granular per-cluster profile).
    """
    year_df = embedding[
        (embedding["year"] == year) & (embedding["geo_type"] == "Tract")
    ] if "geo_type" in embedding.columns else embedding[embedding["year"] == year]

    if year_df.empty or "cluster_label" not in year_df.columns:
        st.info(f"No tract data for {year}.")
        return

    cluster_sizes = year_df.groupby("cluster_label").size().to_dict()
    cluster_shares = year_df.groupby("cluster_label")[feature_cols].mean().reset_index()

    global_mean = year_df[feature_cols].mean()
    top_cols = global_mean.sort_values(ascending=False).head(_BAR_TOP_N).index.tolist()
    other_cols = [c for c in feature_cols if c not in top_cols]
    if other_cols:
        cluster_shares["Other"] = cluster_shares[other_cols].sum(axis=1)
    display_cols = top_cols + (["Other"] if other_cols else [])

    row_totals = cluster_shares[display_cols].sum(axis=1).replace(0, np.nan)
    cluster_shares[display_cols] = cluster_shares[display_cols].div(row_totals, axis=0)

    dominant = cluster_shares.set_index("cluster_label")[top_cols].idxmax(axis=1)
    dominant_name = dominant.map(lambda c: CATEGORY_NAMES.get(c, c))
    cluster_shares["Cluster"] = cluster_shares["cluster_label"].map(
        lambda c: f"Cluster {c} · {dominant_name.get(c, '')}  (n={cluster_sizes.get(c, 0)} tracts)"
    )

    melted = cluster_shares.melt(
        id_vars=["cluster_label", "Cluster"],
        value_vars=display_cols, var_name="category", value_name="share",
    )
    melted["Category"] = melted["category"].map(lambda c: CATEGORY_NAMES.get(c, c))
    cat_order = (
        melted.groupby("Category")["share"].mean()
        .sort_values(ascending=False).index.tolist()
    )
    cluster_order = sorted(
        cluster_shares["Cluster"].tolist(), key=lambda s: s.split("·")[0].strip(),
    )

    fig = px.bar(
        melted, x="Cluster", y="share", color="Category",
        category_orders={"Category": cat_order, "Cluster": cluster_order},
        labels={"share": "", "Cluster": ""},
        color_discrete_sequence=px.colors.qualitative.Safe,
    )
    fig.update_yaxes(tickformat=".0%")
    fig.update_layout(
        barmode="stack", height=420,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
        margin=dict(l=10, r=10, t=10, b=10),
        yaxis_title="Share of requests",
    )
    st.plotly_chart(fig, use_container_width=True)


# ── View renderers ────────────────────────────────────────────────────────────

@st.fragment
def _render_usage_view(data_dir: Path, year: int) -> None:
    st.caption(
        "Every tract and CSA projected into a single shared 2D space by service-request "
        "mix — fit once across all years so movement between frames reflects real "
        "change. CSAs (large labeled markers) sit near the centroid of their tracts. "
        "Press play to trace trajectories."
    )

    embedding, feature_cols, var = compute_combined_usage_embedding(data_dir)
    if embedding.empty:
        st.info("Not enough usage history to build the embedding.")
        return

    embedding = embedding.copy()
    cluster_df = _assign_clusters(embedding)
    embedding = embedding.merge(cluster_df, on="geoid", how="left")

    top_srtype_df = _top_srtype_combined(data_dir)
    embedding = embedding.merge(top_srtype_df, on=["geoid", "year"], how="left")

    srtype_freq = embedding["top_srtype"].value_counts()
    top_n = srtype_freq.head(_TOP_SRTYPE_SHOW).index.tolist()
    embedding["srtype_color"] = embedding["top_srtype"].where(
        embedding["top_srtype"].isin(top_n), "Other"
    )
    has_other = embedding["srtype_color"].eq("Other").any()
    srtype_order = top_n + (["Other"] if has_other else [])

    # Demographic colour options — combine both levels
    demo_tract = _load_demographics(data_dir, "tract")
    demo_csa = _load_demographics(data_dir, "csa")
    demo_frames = [d for d in [demo_tract, demo_csa] if d is not None]
    demo_combined = pd.concat(demo_frames, ignore_index=True) if demo_frames else None

    color_options: dict[str, str] = {"Top service type": "srtype_color"}
    demo_cols: list[str] = []
    if demo_combined is not None:
        demo_cols = [c for c in _DEMO_COLOR_OPTIONS.values() if c in demo_combined.columns]
        if demo_cols:
            embedding = embedding.merge(
                demo_combined[["geoid"] + demo_cols], on="geoid", how="left",
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
        f"PC2 **{pc2_pct:.0f}%** · combined **{pc1_pct + pc2_pct:.0f}%** — "
        f"{embedding['geo_type'].eq('Tract').sum() // len(embedding['year'].unique())} tracts "
        f"+ {embedding['geo_type'].eq('CSA').sum() // len(embedding['year'].unique())} CSAs"
    )

    years_sorted = sorted(int(y) for y in embedding["year"].unique())
    display_df = _scale_pct_cols(embedding, demo_cols)
    display_df, demo_hover_map = _add_hover_fmt(display_df, demo_cols)
    display_df = _add_viz_cols(display_df)

    hover_labels: dict[str, str] = {
        "x": "PC1", "y": "PC2",
        color_col: color_label,
        "cluster_label": "Cluster",
        "top_srtype": "Top type",
        "geo_type": "Level",
        "_sz": "", "_text": "",  # suppress display columns from hover
        **{hcol: _DEMO_HOVER_NAMES.get(orig, orig) for orig, hcol in demo_hover_map.items()},
    }

    hover_data: dict[str, bool] = {
        "cluster_label": True,
        "top_srtype": True,
        "geo_type": True,
        "srtype_color": False,
        "_sz": False,
        "_text": False,
        **{hcol: True for hcol in demo_hover_map.values()},
    }

    fig = px.scatter(
        display_df.sort_values(["geo_type", "year"]),  # tracts first → CSAs on top
        x="x", y="y",
        animation_frame="year",
        animation_group="geoid",
        color=color_col,
        size="_sz",
        size_max=16,
        text="_text",
        hover_name="geoid",
        hover_data=hover_data,
        labels=hover_labels,
        category_orders=(
            {"year": years_sorted, color_col: srtype_order}
            if is_categorical else {"year": years_sorted}
        ),
        color_continuous_scale="Viridis" if not is_categorical else None,
    )
    fig.update_traces(
        textposition="top center",
        textfont=dict(size=8),
        marker=dict(opacity=0.8, line=dict(width=0.5, color="white")),
    )
    fig.update_layout(height=660, **_top_legend_layout(is_categorical))

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
    st.caption(
        "Large labeled markers = CSAs · small dots = tracts. "
        "Hover for cluster, level, and top service type."
    )

    # ── Cluster profiles ──────────────────────────────────────────────────────
    st.subheader(f"Cluster Profiles — {year}")
    year_tract_df = embedding[
        (embedding["year"] == year) & (embedding["geo_type"] == "Tract")
    ]
    n_by_cluster = year_tract_df.groupby("cluster_label").size().to_dict() if not year_tract_df.empty else {}
    summary = "  ·  ".join(
        f"**{ltr}** {n_by_cluster.get(ltr, 0)} tracts"
        for ltr in _CLUSTER_LETTERS[:_N_CLUSTERS]
    )
    st.caption(
        f"Clusters by mean position across all years ({summary}). "
        "Bars show tract-level category mix per cluster in the selected year."
    )
    _render_cluster_bar(embedding, feature_cols, year)


@st.fragment
def _render_demographic_view(data_dir: Path, year: int) -> None:
    st.caption(
        "Tracts and CSAs placed by *who lives there* — ACS 2023 demographic profile. "
        f"Color by a **{year}** service metric to test whether demographic similarity "
        "predicts service experience."
    )

    embedding, feature_cols, var = compute_combined_demographic_embedding(data_dir)
    if embedding.empty:
        st.info(
            "Demographic files not found in `data/processed/`. "
            "Run `regen_demographics.yml` to generate them."
        )
        return

    embedding = embedding.copy()
    cluster_df = _assign_clusters(embedding)
    embedding = embedding.merge(cluster_df, on="geoid", how="left")

    # Load service metrics for both levels for colour options
    df_tract = _load_metrics(data_dir, "tract", year)
    df_csa = _load_metrics(data_dir, "csa", year)
    df_combined = pd.concat(
        [d for d in [df_tract, df_csa] if d is not None], ignore_index=True,
    ) if (df_tract is not None or df_csa is not None) else None

    color_options: dict[str, str] = {}
    if df_combined is not None:
        for label, col in _SERVICE_COLOR_OPTIONS.items():
            if col in df_combined.columns:
                color_options[label] = col

    color_col = color_label = None
    is_categorical = False
    if color_options:
        color_label = st.selectbox(
            "Color by (service metric)", list(color_options.keys()),
            key="area_emb_demo_color",
        )
        color_col = color_options[color_label]
        if df_combined is not None and color_col in df_combined.columns:
            embedding = embedding.merge(
                df_combined[["geoid", color_col]], on="geoid", how="left",
            )
        is_categorical = color_col == "top_sr_type"

    pc1_pct, pc2_pct = var[0] * 100, var[1] * 100
    _topic = {
        "pct_black": "race", "pct_white": "race", "pct_hispanic": "ethnicity",
        "median_income": "income/poverty", "pct_poverty": "income/poverty",
        "pct_bachelors_plus": "education",
        "pct_under18": "age", "pct_65plus": "age", "median_age": "age",
    }
    feature_phrase = " and ".join(dict.fromkeys(_topic.get(c, c) for c in feature_cols))
    n_tracts = embedding["geo_type"].eq("Tract").sum()
    n_csas = embedding["geo_type"].eq("CSA").sum()
    st.caption(
        f"PC1 **{pc1_pct:.0f}%** · PC2 **{pc2_pct:.0f}%** · "
        f"combined **{pc1_pct + pc2_pct:.0f}%** of variation in {feature_phrase} "
        f"across {n_tracts} tracts + {n_csas} CSAs."
    )

    display_df = _scale_pct_cols(embedding, feature_cols)
    display_df, feat_hover_map = _add_hover_fmt(display_df, feature_cols)
    display_df = _add_viz_cols(display_df)

    hover_labels: dict[str, str] = {
        "x": "PC1", "y": "PC2",
        "cluster_label": "Cluster",
        "geo_type": "Level",
        "_sz": "", "_text": "",
        **({color_col: color_label} if color_col else {}),
        **{hcol: _DEMO_HOVER_NAMES.get(orig, orig) for orig, hcol in feat_hover_map.items()},
    }

    fig = px.scatter(
        display_df.sort_values("geo_type"),  # tracts first → CSAs on top
        x="x", y="y",
        color=color_col,
        size="_sz",
        size_max=16,
        text="_text",
        hover_name="geoid",
        hover_data={
            "cluster_label": True,
            "geo_type": True,
            "_sz": False, "_text": False,
            **{hcol: True for hcol in feat_hover_map.values()},
        },
        labels=hover_labels,
        color_continuous_scale="RdYlGn_r" if not is_categorical else None,
    )
    fig.update_traces(
        textposition="top center",
        textfont=dict(size=8),
        marker=dict(opacity=0.85, line=dict(width=0.5, color="white")),
    )
    fig.update_layout(height=620, **_top_legend_layout(is_categorical))
    _dedup_legend(fig)
    st.plotly_chart(fig, use_container_width=True)
    st.caption("Large labeled markers = CSAs · small dots = tracts. Hover for cluster and demographic values.")

    # ── Cluster service-mix bar ───────────────────────────────────────────────
    usage_emb, usage_feat_cols, _ = compute_combined_usage_embedding(data_dir)
    if not usage_emb.empty and usage_feat_cols:
        year_usage = (
            usage_emb[usage_emb["year"] == year]
            [["geoid", "geo_type"] + usage_feat_cols].copy()
        )
        year_usage["year"] = year
        year_usage = year_usage.merge(
            embedding[["geoid", "cluster_label"]], on="geoid", how="inner",
        )
        if not year_usage.empty:
            st.subheader(f"Cluster Service Mix — {year}")
            n_by_cluster = (
                year_usage[year_usage["geo_type"] == "Tract"]
                .groupby("cluster_label").size().to_dict()
            )
            summary = "  ·  ".join(
                f"**{ltr}** {n_by_cluster.get(ltr, 0)} tracts"
                for ltr in _CLUSTER_LETTERS[:_N_CLUSTERS]
            )
            st.caption(
                f"Neighborhoods grouped by demographic similarity ({summary}). "
                f"Bars show what each cluster asks 311 for in **{year}**."
            )
            _render_cluster_bar(year_usage, usage_feat_cols, year)


# ── Public entry point ────────────────────────────────────────────────────────

def render_area_embedding(data_dir: Path, year: int) -> None:
    """Render Tab 3 — Area Embedding.  Loads all data from data_dir internally."""
    st.caption(
        "Each geography embedded by demographic profile or by service-request mix. "
        "Switch views and color by the opposite dimension to see how areas that differ "
        "demographically request different 311 services."
    )

    if "area_emb_view" not in st.session_state:
        st.session_state["area_emb_view"] = "Demographic profile"

    view_label = st.radio(
        "View", list(_VIEWS.keys()), horizontal=True, key="area_emb_view",
    )
    view = _VIEWS[view_label]

    st.divider()

    if view == "usage":
        _render_usage_view(data_dir, year)
    else:
        _render_demographic_view(data_dir, year)
