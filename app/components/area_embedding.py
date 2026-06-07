"""Area Embedding — Tab 3.

Each geography embedded by demographic profile or by service-request mix.
Both geo levels share one PCA coordinate space; the radio selects which level
to display so the view stays uncluttered while coordinates remain consistent.
"""
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st
from sklearn.decomposition import PCA
from sklearn.preprocessing import QuantileTransformer, RobustScaler

from components.srtype_shared import CATEGORY_NAMES, MIN_GEO_SRTYPE_N, load_geo_srtype_history

_MIN_GEO_YEAR_TOTAL = 200
_TOP_K_CATEGORIES = 15
_PSEUDOCOUNT = 1e-4
_TOP_SRTYPE_SHOW = 12
_BAR_TOP_N = 5
_CSA_LABEL_FRAC = 0.10   # fraction of CSA markers to label; farthest-point sampled

# Marker sizes (pixels) for each geo level.
_SZ_CSA   = 10
_SZ_TRACT = 5

# Very light quadrant background fills.
_QUADRANT_COLORS = {
    "NW": "rgba(100, 149, 237, 0.08)",
    "NE": "rgba(60,  179, 113, 0.08)",
    "SW": "rgba(255, 165,   0, 0.08)",
    "SE": "rgba(218, 112, 214, 0.08)",
}
_QUADRANT_ORDER = ["NW", "NE", "SW", "SE"]

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

_DEMO_FEATURE_COLS = [
    "pct_black", "pct_white", "pct_hispanic",
    "median_income", "pct_poverty", "pct_bachelors_plus",
    "pct_under18", "pct_65plus", "median_age",
]

_VIEWS = {
    "Demographic profile": "demographic",
    "Service usage":       "usage",
}


# ── Data loaders ──────────────────────────────────────────────────────────────

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
    keep = shares.mean().sort_values(ascending=False).head(top_k).index.tolist()
    sub = shares[keep]
    renorm = sub.div(sub.sum(axis=1), axis=0)
    logs = np.log(renorm.to_numpy() + _PSEUDOCOUNT)
    return logs - logs.mean(axis=1, keepdims=True), keep


def _geo_type(geoid: str) -> str:
    s = str(geoid)
    return "Tract" if (s.isdigit() and len(s) == 11) else "CSA"


# ── Combined embeddings ───────────────────────────────────────────────────────

@st.cache_data
def compute_combined_usage_embedding(
    data_dir: Path,
) -> tuple[pd.DataFrame, list[str], tuple[float, float]]:
    """Fit one PCA on tract + CSA share matrices so both share a coordinate system."""
    tract_hist = load_geo_srtype_history(data_dir, "tract")
    csa_hist   = load_geo_srtype_history(data_dir, "csa")

    tract_sh = _usage_share_matrix(tract_hist) if not tract_hist.empty else pd.DataFrame()
    csa_sh   = _usage_share_matrix(csa_hist)   if not csa_hist.empty   else pd.DataFrame()

    if tract_sh.empty and csa_sh.empty:
        return pd.DataFrame(), [], (float("nan"), float("nan"))

    all_cats = sorted(set(
        (tract_sh.columns.tolist() if not tract_sh.empty else []) +
        (csa_sh.columns.tolist()   if not csa_sh.empty   else [])
    ))
    if not tract_sh.empty:
        tract_sh = tract_sh.reindex(columns=all_cats, fill_value=0.0)
    if not csa_sh.empty:
        csa_sh   = csa_sh.reindex(columns=all_cats, fill_value=0.0)

    combined = pd.concat([df for df in [tract_sh, csa_sh] if not df.empty], axis=0)
    if combined.empty or combined.shape[1] < _TOP_K_CATEGORIES:
        return pd.DataFrame(), [], (float("nan"), float("nan"))

    transformed, feature_cols = _clr(combined, _TOP_K_CATEGORIES)
    n_q = min(len(combined), 300)
    X = QuantileTransformer(
        n_quantiles=n_q, output_distribution="normal", random_state=42,
    ).fit_transform(transformed)
    pca = PCA(n_components=2)
    xy  = pca.fit_transform(X)

    emb = combined[feature_cols].reset_index()
    emb["x"]        = xy[:, 0]
    emb["y"]        = xy[:, 1]
    emb["geo_type"] = emb["geoid"].map(_geo_type)
    var = (float(pca.explained_variance_ratio_[0]), float(pca.explained_variance_ratio_[1]))
    return emb, feature_cols, var


@st.cache_data
def compute_combined_demographic_embedding(
    data_dir: Path,
) -> tuple[pd.DataFrame, list[str], tuple[float, float]]:
    demo_tract = _load_demographics(data_dir, "tract")
    demo_csa   = _load_demographics(data_dir, "csa")

    dfs = []
    if demo_tract is not None:
        d = demo_tract.copy(); d["geo_type"] = "Tract"; dfs.append(d)
    if demo_csa is not None:
        d = demo_csa.copy();   d["geo_type"] = "CSA";   dfs.append(d)
    if not dfs:
        return pd.DataFrame(), [], (float("nan"), float("nan"))

    combined  = pd.concat(dfs, ignore_index=True)
    cols      = [c for c in _DEMO_FEATURE_COLS if c in combined.columns]
    df_clean  = combined.dropna(subset=cols) if cols else combined.iloc[0:0]
    if len(cols) < 2 or len(df_clean) < 3:
        return pd.DataFrame(), [], (float("nan"), float("nan"))

    X  = RobustScaler().fit_transform(df_clean[cols].to_numpy())
    pca = PCA(n_components=2)
    xy  = pca.fit_transform(X)

    emb = df_clean[["geoid", "geo_type"] + cols].reset_index(drop=True)
    emb["x"] = xy[:, 0]
    emb["y"] = xy[:, 1]
    var = (float(pca.explained_variance_ratio_[0]), float(pca.explained_variance_ratio_[1]))
    return emb, cols, var


@st.cache_data
def _top_srtype_combined(data_dir: Path) -> pd.DataFrame:
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


# ── Quadrant assignment ───────────────────────────────────────────────────────

def _assign_quadrants(
    embedding: pd.DataFrame,
) -> tuple[pd.DataFrame, float, float]:
    """Divide 2D space at median x / median y → NW | NE | SW | SE per geoid.

    Uses mean position across years so each geoid gets one stable quadrant.
    Returns (cluster_df[geoid, cluster_label], x_mid, y_mid).
    """
    mean_pos = embedding.groupby("geoid")[["x", "y"]].mean().reset_index()
    x_mid    = float(mean_pos["x"].median())
    y_mid    = float(mean_pos["y"].median())

    conds   = [
        (mean_pos["x"] <  x_mid) & (mean_pos["y"] >= y_mid),  # NW
        (mean_pos["x"] >= x_mid) & (mean_pos["y"] >= y_mid),  # NE
        (mean_pos["x"] <  x_mid) & (mean_pos["y"] <  y_mid),  # SW
    ]
    mean_pos["cluster_label"] = np.select(conds, ["NW", "NE", "SW"], default="SE")
    return mean_pos[["geoid", "cluster_label"]], x_mid, y_mid


# ── Chart helpers ─────────────────────────────────────────────────────────────

def _subsample_csa_labels(emb: pd.DataFrame, frac: float = _CSA_LABEL_FRAC) -> set:
    """Farthest-point sample of CSA geoids for text labels (maximises spatial spread)."""
    csa_rows = emb[emb["geo_type"] == "CSA"]
    if csa_rows.empty:
        return set()

    mean_pos = (
        csa_rows.groupby("geoid")[["x", "y"]].mean().reset_index()
        if "year" in csa_rows.columns
        else csa_rows[["geoid", "x", "y"]].drop_duplicates("geoid")
    )
    n = max(1, round(len(mean_pos) * frac))
    if n >= len(mean_pos):
        return set(mean_pos["geoid"])

    pts    = mean_pos[["x", "y"]].to_numpy()
    geoids = mean_pos["geoid"].tolist()
    centroid = pts.mean(axis=0)
    dists    = np.linalg.norm(pts - centroid, axis=1)
    selected = [int(dists.argmax())]

    for _ in range(n - 1):
        dist_to_nearest = np.min(
            np.linalg.norm(pts[:, None] - pts[selected][None], axis=2), axis=1,
        )
        selected.append(int(dist_to_nearest.argmax()))

    return {geoids[i] for i in selected}


def _dedup_legend(fig) -> None:
    seen: set[str] = set()
    for trace in fig.data:
        name = trace.name or ""
        if name in seen:
            trace.update(showlegend=False)
        else:
            seen.add(name)


def _top_legend_layout(is_categorical: bool) -> dict:
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


def _add_quadrant_backgrounds(
    fig, x_mid: float, y_mid: float,
    x_range: list[float], y_range: list[float],
) -> None:
    """Draw light-filled rectangles and faint quadrant labels behind the scatter."""
    quads = {
        "NW": (x_range[0], x_mid,      y_mid,      y_range[1]),
        "NE": (x_mid,      x_range[1], y_mid,      y_range[1]),
        "SW": (x_range[0], x_mid,      y_range[0], y_mid),
        "SE": (x_mid,      x_range[1], y_range[0], y_mid),
    }
    for name, (x0, x1, y0, y1) in quads.items():
        fig.add_shape(
            type="rect", x0=x0, x1=x1, y0=y0, y1=y1,
            fillcolor=_QUADRANT_COLORS[name], line_width=0, layer="below",
        )
        fig.add_annotation(
            x=(x0 + x1) / 2, y=(y0 + y1) / 2,
            text=name, showarrow=False,
            font=dict(size=13, color="rgba(0,0,0,0.15)"),
        )


def _scale_pct_cols(df: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    df = df.copy()
    for col in cols:
        if col in _PCT_COLS and col in df.columns:
            df[col] = (df[col] * 100).round(1)
    return df


def _add_hover_fmt(
    df: pd.DataFrame, cols: list[str],
) -> tuple[pd.DataFrame, dict[str, str]]:
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


def _add_text_col(
    emb: pd.DataFrame, geo_type_str: str, labeled_csas: set | None = None,
) -> pd.DataFrame:
    """Add _text label column: blank for tracts; sampled subset label for CSAs."""
    emb = emb.copy()
    if geo_type_str == "Tract":
        emb["_text"] = ""
    else:
        if labeled_csas is not None:
            emb["_text"] = emb["geoid"].where(emb["geoid"].isin(labeled_csas), "")
        else:
            emb["_text"] = emb["geoid"]
    return emb


# ── Quadrant bar ──────────────────────────────────────────────────────────────

def _render_quadrant_bar(
    embedding: pd.DataFrame, feature_cols: list[str], year: int, geo_type_str: str,
) -> None:
    """100% stacked bar — top-5 category share per quadrant for `geo_type_str` in `year`."""
    if "year" in embedding.columns:
        year_df = embedding[embedding["year"] == year]
    else:
        year_df = embedding

    if "geo_type" in year_df.columns:
        year_df = year_df[year_df["geo_type"] == geo_type_str]

    if year_df.empty or "cluster_label" not in year_df.columns:
        st.info(f"No {geo_type_str.lower()} data for {year}.")
        return

    geo_label  = "tracts" if geo_type_str == "Tract" else "CSAs"
    quad_sizes = year_df.groupby("cluster_label").size().to_dict()
    quad_shares = year_df.groupby("cluster_label")[feature_cols].mean().reset_index()

    global_mean = year_df[feature_cols].mean()
    top_cols    = global_mean.sort_values(ascending=False).head(_BAR_TOP_N).index.tolist()
    other_cols  = [c for c in feature_cols if c not in top_cols]
    if other_cols:
        quad_shares["Other"] = quad_shares[other_cols].sum(axis=1)
    display_cols = top_cols + (["Other"] if other_cols else [])

    row_totals = quad_shares[display_cols].sum(axis=1).replace(0, np.nan)
    quad_shares[display_cols] = quad_shares[display_cols].div(row_totals, axis=0)

    dominant      = quad_shares.set_index("cluster_label")[top_cols].idxmax(axis=1)
    dominant_name = dominant.map(lambda c: CATEGORY_NAMES.get(c, c))
    quad_shares["Quadrant"] = quad_shares["cluster_label"].map(
        lambda c: f"{c} · {dominant_name.get(c, '')}  (n={quad_sizes.get(c, 0)} {geo_label})"
    )

    melted = quad_shares.melt(
        id_vars=["cluster_label", "Quadrant"],
        value_vars=display_cols, var_name="category", value_name="share",
    )
    melted["Category"] = melted["category"].map(lambda c: CATEGORY_NAMES.get(c, c))
    cat_order = (
        melted.groupby("Category")["share"].mean()
        .sort_values(ascending=False).index.tolist()
    )
    quad_order = sorted(
        quad_shares["Quadrant"].tolist(),
        key=lambda s: next(
            (i for i, q in enumerate(_QUADRANT_ORDER) if s.startswith(q)), 99
        ),
    )

    fig = px.bar(
        melted, x="Quadrant", y="share", color="Category",
        category_orders={"Category": cat_order, "Quadrant": quad_order},
        labels={"share": "", "Quadrant": ""},
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
def _render_usage_view(data_dir: Path, year: int, geo_filter: str) -> None:
    geo_type_str = "Tract" if geo_filter == "Tracts" else "CSA"

    st.caption(
        "Each geography projected into a shared 2D space by service-request mix — "
        "fit once across all years so movement between frames is real change. "
        "Press play to trace trajectories."
    )

    embedding, feature_cols, var = compute_combined_usage_embedding(data_dir)
    if embedding.empty:
        st.info("Not enough usage history to build the embedding.")
        return

    embedding = embedding.copy()
    cluster_df, x_mid, y_mid = _assign_quadrants(embedding)
    embedding = embedding.merge(cluster_df, on="geoid", how="left")

    top_srtype_df = _top_srtype_combined(data_dir)
    embedding = embedding.merge(top_srtype_df, on=["geoid", "year"], how="left")

    # Color by median income (fixed — no dropdown)
    color_col      = "median_income"
    color_label    = "Median income"
    is_categorical = False
    demo_cols: list[str] = []
    demo_tract    = _load_demographics(data_dir, "tract")
    demo_csa      = _load_demographics(data_dir, "csa")
    demo_frames   = [d for d in [demo_tract, demo_csa] if d is not None]
    demo_combined = pd.concat(demo_frames, ignore_index=True) if demo_frames else None
    if demo_combined is not None and color_col in demo_combined.columns:
        demo_cols = [color_col]
        embedding = embedding.merge(
            demo_combined[["geoid", color_col]], on="geoid", how="left",
        )

    # Filter to selected geo level (axes computed on full embedding for consistency)
    display_embedding = embedding[embedding["geo_type"] == geo_type_str].copy()
    if display_embedding.empty:
        st.info(f"No {geo_filter.lower()} data available.")
        return

    pc1_pct, pc2_pct = var[0] * 100, var[1] * 100
    n_shown = len(display_embedding["geoid"].unique()) if "year" not in display_embedding.columns \
        else len(display_embedding.drop_duplicates("geoid"))
    st.caption(
        f"PC1 **{pc1_pct:.0f}%** · PC2 **{pc2_pct:.0f}%** · "
        f"combined **{pc1_pct + pc2_pct:.0f}%** — {len(display_embedding['geoid'].unique())} {geo_filter.lower()}"
    )

    pad  = 0.08
    x5,  x95 = np.percentile(embedding["x"], [5, 95])
    y5,  y95 = np.percentile(embedding["y"], [5, 95])
    x_range  = [x5 - (x95 - x5) * pad, x95 + (x95 - x5) * pad]
    y_range  = [y5 - (y95 - y5) * pad, y95 + (y95 - y5) * pad]

    labeled_csas: set = (
        _subsample_csa_labels(display_embedding) if geo_type_str == "CSA" else set()
    )

    years_sorted = sorted(int(y) for y in display_embedding["year"].unique())
    display_df   = _scale_pct_cols(display_embedding, demo_cols)
    display_df, demo_hover_map = _add_hover_fmt(display_df, demo_cols)
    display_df   = _add_text_col(display_df, geo_type_str, labeled_csas)

    hover_labels: dict[str, str] = {
        "x": "PC1", "y": "PC2",
        color_col:       color_label,
        "cluster_label": "Quadrant",
        "top_srtype":    "Top type",
        "_text":         "",
        **{hcol: _DEMO_HOVER_NAMES.get(orig, orig) for orig, hcol in demo_hover_map.items()},
    }
    hover_data: dict[str, bool] = {
        "cluster_label": True,
        "top_srtype":    True,
        "_text":         False,
        **{hcol: True for hcol in demo_hover_map.values()},
    }

    marker_size = _SZ_CSA if geo_type_str == "CSA" else _SZ_TRACT

    fig = px.scatter(
        display_df.sort_values("year"),
        x="x", y="y",
        animation_frame="year",
        animation_group="geoid",
        color=color_col,
        text="_text",
        hover_name="geoid",
        hover_data=hover_data,
        labels=hover_labels,
        category_orders={"year": years_sorted},
        color_continuous_scale="Viridis",
    )
    fig.update_traces(
        textposition="top center",
        textfont=dict(size=8),
        marker=dict(size=marker_size, opacity=0.8, line=dict(width=0.5, color="white")),
    )
    fig.update_layout(height=660, **_top_legend_layout(is_categorical))
    fig.update_xaxes(range=x_range)
    fig.update_yaxes(range=y_range)
    _add_quadrant_backgrounds(fig, x_mid, y_mid, x_range, y_range)

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
    if geo_type_str == "CSA":
        st.caption(f"~{round(_CSA_LABEL_FRAC * 100):.0f}% of CSA names shown (farthest-point sampled). Hover any marker for details.")

    st.subheader(f"Quadrant Profiles — {year}")
    n_by_quad = (
        display_embedding[display_embedding["year"] == year]
        .groupby("cluster_label").size().to_dict()
        if "year" in display_embedding.columns
        else display_embedding.groupby("cluster_label").size().to_dict()
    )
    summary = "  ·  ".join(
        f"**{q}** {n_by_quad.get(q, 0)}" for q in _QUADRANT_ORDER
    )
    st.caption(f"Quadrant counts ({summary}). Bars show category mix for the selected year.")
    _render_quadrant_bar(display_embedding, feature_cols, year, geo_type_str)


@st.fragment
def _render_demographic_view(data_dir: Path, year: int, geo_filter: str) -> None:
    geo_type_str = "Tract" if geo_filter == "Tracts" else "CSA"

    st.caption(
        "Geographies placed by *who lives there* — ACS 2023 demographic profile. "
        f"Colored by predominant service type in **{year}** to test whether "
        "demographic similarity predicts what 311 is used for."
    )

    embedding, feature_cols, var = compute_combined_demographic_embedding(data_dir)
    if embedding.empty:
        st.info(
            "Demographic files not found in `data/processed/`. "
            "Run `regen_demographics.yml` to generate them."
        )
        return

    embedding = embedding.copy()
    cluster_df, x_mid, y_mid = _assign_quadrants(embedding)
    embedding = embedding.merge(cluster_df, on="geoid", how="left")

    df_tract   = _load_metrics(data_dir, "tract", year)
    df_csa     = _load_metrics(data_dir, "csa",   year)
    df_combined = pd.concat(
        [d for d in [df_tract, df_csa] if d is not None], ignore_index=True,
    ) if (df_tract is not None or df_csa is not None) else None

    # Color by predominant service type (fixed — no dropdown)
    color_label    = "Predominant service type"
    is_categorical = True
    if df_combined is not None and "top_sr_type" in df_combined.columns:
        embedding = embedding.merge(
            df_combined[["geoid", "top_sr_type"]], on="geoid", how="left",
        )
    srtype_freq  = embedding["top_sr_type"].value_counts() if "top_sr_type" in embedding.columns else pd.Series(dtype=int)
    top_n        = srtype_freq.head(_TOP_SRTYPE_SHOW).index.tolist()
    embedding["srtype_color"] = (
        embedding["top_sr_type"].where(embedding["top_sr_type"].isin(top_n), "Other")
        if "top_sr_type" in embedding.columns else "Unknown"
    )
    has_other   = embedding["srtype_color"].eq("Other").any()
    srtype_order = top_n + (["Other"] if has_other else [])
    color_col    = "srtype_color"

    # Filter to selected geo level
    display_embedding = embedding[embedding["geo_type"] == geo_type_str].copy()
    if display_embedding.empty:
        st.info(f"No {geo_filter.lower()} data available.")
        return

    pc1_pct, pc2_pct = var[0] * 100, var[1] * 100
    _topic = {
        "pct_black": "race", "pct_white": "race", "pct_hispanic": "ethnicity",
        "median_income": "income/poverty", "pct_poverty": "income/poverty",
        "pct_bachelors_plus": "education",
        "pct_under18": "age", "pct_65plus": "age", "median_age": "age",
    }
    feature_phrase = " and ".join(dict.fromkeys(_topic.get(c, c) for c in feature_cols))
    st.caption(
        f"PC1 **{pc1_pct:.0f}%** · PC2 **{pc2_pct:.0f}%** · "
        f"combined **{pc1_pct + pc2_pct:.0f}%** of variation in {feature_phrase} "
        f"across {len(display_embedding['geoid'].unique())} {geo_filter.lower()}."
    )

    pad  = 0.08
    x5,  x95 = np.percentile(embedding["x"], [5, 95])
    y5,  y95 = np.percentile(embedding["y"], [5, 95])
    x_range  = [x5 - (x95 - x5) * pad, x95 + (x95 - x5) * pad]
    y_range  = [y5 - (y95 - y5) * pad, y95 + (y95 - y5) * pad]

    labeled_csas: set = (
        _subsample_csa_labels(display_embedding) if geo_type_str == "CSA" else set()
    )

    display_df = _scale_pct_cols(display_embedding, feature_cols)
    display_df, feat_hover_map = _add_hover_fmt(display_df, feature_cols)
    display_df = _add_text_col(display_df, geo_type_str, labeled_csas)

    hover_labels: dict[str, str] = {
        "x": "PC1", "y": "PC2",
        "cluster_label": "Quadrant",
        "_text":         "",
        color_col:       color_label,
        "top_sr_type":   "Top type",
        **{hcol: _DEMO_HOVER_NAMES.get(orig, orig) for orig, hcol in feat_hover_map.items()},
    }

    marker_size = _SZ_CSA if geo_type_str == "CSA" else _SZ_TRACT

    fig = px.scatter(
        display_df.sort_values("geoid"),
        x="x", y="y",
        color=color_col,
        text="_text",
        hover_name="geoid",
        hover_data={
            "cluster_label": True,
            "top_sr_type":   True,
            "srtype_color":  False,
            "_text":         False,
            **{hcol: True for hcol in feat_hover_map.values()},
        },
        labels=hover_labels,
        category_orders={color_col: srtype_order},
    )
    fig.update_traces(
        textposition="top center",
        textfont=dict(size=8),
        marker=dict(size=marker_size, opacity=0.85, line=dict(width=0.5, color="white")),
    )
    fig.update_layout(height=620, **_top_legend_layout(is_categorical))
    fig.update_xaxes(range=x_range)
    fig.update_yaxes(range=y_range)
    _add_quadrant_backgrounds(fig, x_mid, y_mid, x_range, y_range)
    _dedup_legend(fig)
    st.plotly_chart(fig, use_container_width=True)
    if geo_type_str == "CSA":
        st.caption(f"~{round(_CSA_LABEL_FRAC * 100):.0f}% of CSA names shown. Hover any marker for details.")

    # Quadrant service-mix bar
    usage_emb, usage_feat_cols, _ = compute_combined_usage_embedding(data_dir)
    if not usage_emb.empty and usage_feat_cols:
        year_usage = usage_emb[
            (usage_emb["year"] == year) & (usage_emb["geo_type"] == geo_type_str)
        ][["geoid", "geo_type"] + usage_feat_cols].copy()
        year_usage["year"] = year
        year_usage = year_usage.merge(
            display_embedding[["geoid", "cluster_label"]], on="geoid", how="inner",
        )
        if not year_usage.empty:
            st.subheader(f"Quadrant Service Mix — {year}")
            n_by_quad = year_usage.groupby("cluster_label").size().to_dict()
            summary = "  ·  ".join(
                f"**{q}** {n_by_quad.get(q, 0)}" for q in _QUADRANT_ORDER
            )
            st.caption(
                f"Grouped by demographic similarity ({summary}). "
                f"Bars show what each quadrant asks 311 for in **{year}**."
            )
            _render_quadrant_bar(year_usage, usage_feat_cols, year, geo_type_str)


# ── Public entry point ────────────────────────────────────────────────────────

def render_area_embedding(data_dir: Path, year: int) -> None:
    """Render Tab 3 — Area Embedding.  Loads all data from data_dir internally."""
    st.caption(
        "Each geography embedded by demographic profile or by service-request mix. "
        "Switch views and color by the opposite dimension to see how areas that differ "
        "demographically request different 311 services."
    )

    c_view, c_geo = st.columns([3, 2])
    with c_view:
        if "area_emb_view" not in st.session_state:
            st.session_state["area_emb_view"] = "Demographic profile"
        view_label = st.radio(
            "View", list(_VIEWS.keys()), horizontal=True, key="area_emb_view",
        )
    with c_geo:
        geo_filter = st.radio("Show", ["Tracts", "CSAs"], horizontal=True, key="area_emb_geo")

    view = _VIEWS[view_label]
    st.divider()

    if view == "usage":
        _render_usage_view(data_dir, year, geo_filter)
    else:
        _render_demographic_view(data_dir, year, geo_filter)
