"""Area Embedding — Tab 3.

Each geography embedded by demographic profile or by service-request mix.
Tracts and CSAs share one PCA coordinate space and are displayed together:
tract dots form the point cloud, CSA bubbles (labeled) sit near the centroid
of their constituent tracts.
"""
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st
from sklearn.decomposition import PCA
from sklearn.preprocessing import QuantileTransformer, RobustScaler

from components.srtype_shared import MIN_GEO_SRTYPE_N, load_geo_srtype_history

_MIN_GEO_YEAR_TOTAL = 200
_TOP_K_CATEGORIES = 15
_PSEUDOCOUNT = 1e-4
_TOP_SRTYPE_SHOW = 12
_CSA_LABEL_FRAC         = 0.10  # fraction of CSA markers to label; farthest-point sampled
_CSA_LABEL_MIN_PER_QUAD = 3     # guaranteed minimum CSA labels per quadrant
_SRTYPE_BAR_TOP_N  = 8    # individual SRTypes to show in the predominant-subtype bar

# Plotly bubble area values — with size_max=16, CSA → ~16px, Tract → ~6px.
_SZ_CSA   = 200
_SZ_TRACT = 30

# Quadrant labels: UL/UR/LL/LR (upper-left, upper-right, lower-left, lower-right).
# Avoids geographic cardinal-direction confounds — these are embedding dimensions, not compass bearings.
_QUADRANT_COLORS = {
    "UL": "rgba(100, 149, 237, 0.08)",
    "UR": "rgba(60,  179, 113, 0.08)",
    "LL": "rgba(255, 165,   0, 0.08)",
    "LR": "rgba(218, 112, 214, 0.08)",
}
_QUADRANT_ORDER = ["UL", "UR", "LL", "LR"]

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


@st.cache_data
def _load_tract_nsa(data_dir: Path) -> dict[str, str]:
    """Load tract→NSA name crosswalk. Returns empty dict if file not yet generated."""
    path = data_dir / "tract_to_nsa.csv"
    if not path.exists():
        return {}
    df = pd.read_csv(path, dtype={"geoid": str, "nsa_name": str}).fillna({"nsa_name": ""})
    return dict(zip(df["geoid"], df["nsa_name"]))


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
    X   = QuantileTransformer(
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

    combined = pd.concat(dfs, ignore_index=True)
    cols     = [c for c in _DEMO_FEATURE_COLS if c in combined.columns]
    df_clean = combined.dropna(subset=cols) if cols else combined.iloc[0:0]
    if len(cols) < 2 or len(df_clean) < 3:
        return pd.DataFrame(), [], (float("nan"), float("nan"))

    X   = RobustScaler().fit_transform(df_clean[cols].to_numpy())
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
    """Divide 2D space at median x / median y → UL | UR | LL | LR per geoid."""
    mean_pos = embedding.groupby("geoid")[["x", "y"]].mean().reset_index()
    x_mid    = float(mean_pos["x"].median())
    y_mid    = float(mean_pos["y"].median())

    conds = [
        (mean_pos["x"] <  x_mid) & (mean_pos["y"] >= y_mid),
        (mean_pos["x"] >= x_mid) & (mean_pos["y"] >= y_mid),
        (mean_pos["x"] <  x_mid) & (mean_pos["y"] <  y_mid),
    ]
    mean_pos["cluster_label"] = np.select(conds, ["UL", "UR", "LL"], default="LR")
    return mean_pos[["geoid", "cluster_label"]], x_mid, y_mid


# ── Chart helpers ─────────────────────────────────────────────────────────────

def _subsample_labels(
    emb: pd.DataFrame,
    geo_type_filter: str = "Tract",
    frac: float = _CSA_LABEL_FRAC,
    min_per_quad: int = _CSA_LABEL_MIN_PER_QUAD,
    require_col: str | None = None,
) -> set:
    """Farthest-point sample geoids for scatter text labels.

    Guarantees at least min_per_quad labels per quadrant (phase 1), then fills
    the remaining budget globally (phase 2). When require_col is set, only rows
    with a non-empty value in that column are eligible.
    """
    rows = emb[emb["geo_type"] == geo_type_filter]
    if require_col and require_col in rows.columns:
        rows = rows[rows[require_col].notna() & (rows[require_col] != "")]
    if rows.empty:
        return set()

    mean_pos = (
        rows.groupby("geoid")[["x", "y"]].mean().reset_index()
        if "year" in rows.columns
        else rows[["geoid", "x", "y"]].drop_duplicates("geoid")
    ).reset_index(drop=True)

    if "cluster_label" in rows.columns:
        mean_pos = mean_pos.merge(
            rows[["geoid", "cluster_label"]].drop_duplicates("geoid"),
            on="geoid", how="left",
        ).reset_index(drop=True)

    n_target = min(
        len(mean_pos),
        max(round(len(mean_pos) * frac), min_per_quad * len(_QUADRANT_ORDER)),
    )

    pts     = mean_pos[["x", "y"]].to_numpy()
    geoids  = mean_pos["geoid"].tolist()
    sel_set: set[str]  = set()
    sel_idx: list[int] = []

    def _pick_farthest(candidate_idx: list[int]) -> int | None:
        avail = [i for i in candidate_idx if geoids[i] not in sel_set]
        if not avail:
            return None
        if not sel_idx:
            centroid = pts[avail].mean(axis=0)
            scores = np.linalg.norm(pts[avail] - centroid, axis=1)
        else:
            scores = np.min(
                np.linalg.norm(pts[avail][:, None] - pts[sel_idx][None], axis=2), axis=1,
            )
        return avail[int(np.argmax(scores))]

    # Phase 1: guarantee min_per_quad from each quadrant
    if "cluster_label" in mean_pos.columns:
        for q in _QUADRANT_ORDER:
            q_idx = mean_pos.index[mean_pos["cluster_label"] == q].tolist()
            for _ in range(min(min_per_quad, len(q_idx))):
                best = _pick_farthest(q_idx)
                if best is None:
                    break
                sel_set.add(geoids[best])
                sel_idx.append(best)

    # Phase 2: fill remaining budget globally
    all_idx = list(range(len(mean_pos)))
    while len(sel_set) < n_target:
        best = _pick_farthest(all_idx)
        if best is None:
            break
        sel_set.add(geoids[best])
        sel_idx.append(best)

    return sel_set


def _fmt_geoid(geoid: str) -> str:
    """Format 11-digit tract GEOID as 'Tract XXXX.XX'; leave CSA names unchanged."""
    s = str(geoid)
    if s.isdigit() and len(s) == 11:
        t = s[5:]  # last 6 digits are the tract number
        return f"Tract {t[:4]}.{t[4:]}"
    return s


def _add_viz_cols(
    emb: pd.DataFrame,
    labeled_tracts: set | None = None,
    label_col: str = "nsa_name",
) -> pd.DataFrame:
    """Add _sz, _text (NSA name on sampled tract dots), and _hover_title."""
    emb    = emb.copy()
    is_csa = emb["geo_type"] == "CSA"
    emb["_sz"] = np.where(is_csa, _SZ_CSA, _SZ_TRACT)

    # Scatter text: NSA name on the sampled labeled tract dots only
    if labeled_tracts is not None and label_col in emb.columns:
        is_labeled_tract = (~is_csa) & emb["geoid"].isin(labeled_tracts)
        emb["_text"] = emb[label_col].where(is_labeled_tract, "")
    else:
        emb["_text"] = ""

    # Hover title: "NSA Name · Tract XXXX.XX" for tracts with a name,
    # "Tract XXXX.XX" for tracts without, CSA name for CSAs.
    tract_id = emb["geoid"].map(_fmt_geoid)
    if label_col in emb.columns:
        has_name = emb[label_col].notna() & (emb[label_col] != "")
        emb["_hover_title"] = np.where(
            ~is_csa & has_name,
            emb[label_col] + "  ·  " + tract_id,
            np.where(~is_csa, tract_id, emb["geoid"]),
        )
    else:
        emb["_hover_title"] = np.where(~is_csa, tract_id, emb["geoid"])

    return emb


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
    quads = {
        "UL": (x_range[0], x_mid,      y_mid,      y_range[1]),
        "UR": (x_mid,      x_range[1], y_mid,      y_range[1]),
        "LL": (x_range[0], x_mid,      y_range[0], y_mid),
        "LR": (x_mid,      x_range[1], y_range[0], y_mid),
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


# ── Neighborhood list ─────────────────────────────────────────────────────────

def _render_neighborhood_list(embedding: pd.DataFrame) -> None:
    """Two-column table of CSA names by quadrant affiliation, small text."""
    if "cluster_label" not in embedding.columns or "geo_type" not in embedding.columns:
        return
    unique = (
        embedding[["geoid", "geo_type", "cluster_label"]]
        .drop_duplicates("geoid")
    )
    csas = unique[unique["geo_type"] == "CSA"].sort_values(["cluster_label", "geoid"])
    if csas.empty:
        return

    st.subheader("Neighborhoods by Quadrant")
    # Two columns, two quadrants each: (UL, UR) left / (LL, LR) right
    col_left, col_right = st.columns(2)
    pairs = [(_QUADRANT_ORDER[0], _QUADRANT_ORDER[1]), (_QUADRANT_ORDER[2], _QUADRANT_ORDER[3])]
    for col, (q1, q2) in zip([col_left, col_right], pairs):
        with col:
            for q in (q1, q2):
                names = csas[csas["cluster_label"] == q]["geoid"].tolist()
                items = "".join(f"<li>{n}</li>" for n in names)
                st.markdown(
                    f"<p style='margin-bottom:2px'><strong>{q}</strong> ({len(names)})</p>"
                    f'<ul style="font-size:0.78em; margin-top:0; margin-bottom:12px; '
                    f'padding-left:1.4em; line-height:1.5;">{items}</ul>',
                    unsafe_allow_html=True,
                )


# ── Predominant subtype bar ───────────────────────────────────────────────────

def _render_quadrant_srtype_bar(
    embedding: pd.DataFrame, data_dir: Path, year: int,
) -> None:
    """Stacked bar: % of tracts per quadrant whose top service call is each specific SRType.

    Only SRTypes that appear as the predominant type for at least one tract are
    included — so the segments are drawn from the universe of 'dominant' subtypes
    rather than every SRType that exists in the dataset.
    """
    if "cluster_label" not in embedding.columns or "geo_type" not in embedding.columns:
        return

    top_df   = _top_srtype_combined(data_dir)
    top_year = top_df[top_df["year"] == year] if "year" in top_df.columns else pd.DataFrame()
    if top_year.empty:
        return

    unique = embedding[["geoid", "geo_type", "cluster_label"]].drop_duplicates("geoid")
    tracts = unique[unique["geo_type"] == "Tract"]
    df     = tracts.merge(top_year[["geoid", "top_srtype"]], on="geoid", how="left")
    df     = df.dropna(subset=["top_srtype", "cluster_label"])
    if df.empty:
        return

    # Distribution of top_srtype within each quadrant
    counts = df.groupby(["cluster_label", "top_srtype"]).size().reset_index(name="n")
    totals = df.groupby("cluster_label").size().reset_index(name="total")
    counts = counts.merge(totals, on="cluster_label")
    counts["pct"] = counts["n"] / counts["total"]

    # Top N by global tract count, rest → Other
    global_rank = df["top_srtype"].value_counts()
    top_types   = global_rank.head(_SRTYPE_BAR_TOP_N).index.tolist()
    counts["SRType"] = counts["top_srtype"].where(counts["top_srtype"].isin(top_types), "Other")
    plot_df = counts.groupby(["cluster_label", "SRType"])["pct"].sum().reset_index()

    srtype_order = top_types + (["Other"] if plot_df["SRType"].eq("Other").any() else [])
    quad_order   = [q for q in _QUADRANT_ORDER if q in plot_df["cluster_label"].values]

    fig = px.bar(
        plot_df, x="cluster_label", y="pct", color="SRType",
        category_orders={"cluster_label": quad_order, "SRType": srtype_order},
        labels={"pct": "", "cluster_label": "", "SRType": ""},
        color_discrete_sequence=px.colors.qualitative.Bold,
    )
    fig.update_yaxes(tickformat=".0%")
    fig.update_layout(
        barmode="stack", height=440,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
        margin=dict(l=10, r=10, t=10, b=10),
        yaxis_title="% of tracts",
    )
    st.plotly_chart(fig, use_container_width=True)


# ── View renderers ────────────────────────────────────────────────────────────

@st.fragment
def _render_usage_view(data_dir: Path, year: int) -> None:
    st.caption(
        "Every geography projected into a shared 2D space by service-request mix — "
        "fit once across all years so movement between frames is real change. "
        "Large labeled markers = CSAs · small dots = tracts. Press play."
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

    # Color by median income (fixed)
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

    pc1_pct, pc2_pct = var[0] * 100, var[1] * 100
    n_tracts = embedding["geo_type"].eq("Tract").sum() // max(len(embedding["year"].unique()), 1)
    n_csas   = embedding["geo_type"].eq("CSA").sum()   // max(len(embedding["year"].unique()), 1)
    st.caption(
        f"PC1 **{pc1_pct:.0f}%** · PC2 **{pc2_pct:.0f}%** · "
        f"combined **{pc1_pct + pc2_pct:.0f}%** — {n_tracts} tracts + {n_csas} CSAs"
    )

    pad    = 0.14
    x5, x95 = np.percentile(embedding["x"], [5, 95])
    y5, y95 = np.percentile(embedding["y"], [5, 95])
    x_range = [x5 - (x95 - x5) * pad, x95 + (x95 - x5) * pad]
    y_range = [y5 - (y95 - y5) * pad, y95 + (y95 - y5) * pad]

    tract_nsa = _load_tract_nsa(data_dir)
    embedding["nsa_name"] = embedding["geoid"].map(tract_nsa).fillna("")

    labeled_tracts = _subsample_labels(embedding, "Tract", require_col="nsa_name")
    years_sorted   = sorted(int(y) for y in embedding["year"].unique())
    display_df     = _scale_pct_cols(embedding, demo_cols)
    display_df, demo_hover_map = _add_hover_fmt(display_df, demo_cols)
    display_df     = _add_viz_cols(display_df, labeled_tracts=labeled_tracts)

    has_nsa = bool(tract_nsa)
    hover_labels: dict[str, str] = {
        "x": "PC1", "y": "PC2",
        color_col:        color_label,
        "cluster_label":  "Quadrant",
        "top_srtype":     "Top type",
        "geo_type":       "Level",
        "_sz": "", "_text": "", "_hover_title": "",
        **{hcol: _DEMO_HOVER_NAMES.get(orig, orig) for orig, hcol in demo_hover_map.items()},
    }
    hover_data: dict[str, bool] = {
        "cluster_label":  True,
        "top_srtype":     True,
        "geo_type":       True,
        "_sz": False, "_text": False, "_hover_title": False,
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
        hover_name="_hover_title",
        hover_data=hover_data,
        labels=hover_labels,
        category_orders={"year": years_sorted},
        color_continuous_scale="Viridis",
    )
    fig.update_traces(
        textposition="top center",
        textfont=dict(size=11, color="rgba(20,20,20,0.9)"),
        marker=dict(opacity=0.8, line=dict(width=0.5, color="white")),
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
    nsa_note = (
        f"~{round(_CSA_LABEL_FRAC * 100):.0f}% of tract NSA names labeled (min {_CSA_LABEL_MIN_PER_QUAD} per quadrant, farthest-point sampled). "
        "Hover any marker for neighborhood, quadrant, and service details."
        if has_nsa else
        "Run `python scripts/pipeline.py --stage nsa` to add neighborhood name labels. Hover for details."
    )
    st.caption(nsa_note)

    st.subheader(f"Predominant Service Type by Quadrant — {year}")
    n_by_quad = (
        embedding[(embedding["year"] == year) & (embedding["geo_type"] == "Tract")]
        .groupby("cluster_label").size().to_dict()
    )
    summary = "  ·  ".join(f"**{q}** {n_by_quad.get(q, 0)}" for q in _QUADRANT_ORDER)
    st.caption(
        f"Tract counts by quadrant: {summary}. "
        "Bars show the % of tracts in each quadrant whose top service call is each specific type."
    )
    _render_quadrant_srtype_bar(embedding, data_dir, year)

    st.divider()
    _render_neighborhood_list(embedding)


@st.fragment
def _render_demographic_view(data_dir: Path, year: int) -> None:
    st.caption(
        "Geographies placed by *who lives there* — ACS 2023 demographic profile. "
        "Colored by predominant service type in the selected year to test whether "
        "demographic similarity predicts what 311 is used for. "
        "Large labeled markers = CSAs · small dots = tracts."
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

    # Color by predominant service type (fixed)
    df_tract    = _load_metrics(data_dir, "tract", year)
    df_csa      = _load_metrics(data_dir, "csa",   year)
    df_combined = pd.concat(
        [d for d in [df_tract, df_csa] if d is not None], ignore_index=True,
    ) if (df_tract is not None or df_csa is not None) else None

    is_categorical = True
    srtype_order: list[str] = []
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
    has_other    = embedding["srtype_color"].eq("Other").any()
    srtype_order = top_n + (["Other"] if has_other else [])
    color_col    = "srtype_color"
    color_label  = "Predominant service type"

    pc1_pct, pc2_pct = var[0] * 100, var[1] * 100
    _topic = {
        "pct_black": "race", "pct_white": "race", "pct_hispanic": "ethnicity",
        "median_income": "income/poverty", "pct_poverty": "income/poverty",
        "pct_bachelors_plus": "education",
        "pct_under18": "age", "pct_65plus": "age", "median_age": "age",
    }
    feature_phrase = " and ".join(dict.fromkeys(_topic.get(c, c) for c in feature_cols))
    n_tracts = embedding["geo_type"].eq("Tract").sum()
    n_csas   = embedding["geo_type"].eq("CSA").sum()
    st.caption(
        f"PC1 **{pc1_pct:.0f}%** · PC2 **{pc2_pct:.0f}%** · "
        f"combined **{pc1_pct + pc2_pct:.0f}%** of variation in {feature_phrase} "
        f"across {n_tracts} tracts + {n_csas} CSAs."
    )

    pad    = 0.14
    x5, x95 = np.percentile(embedding["x"], [5, 95])
    y5, y95 = np.percentile(embedding["y"], [5, 95])
    x_range = [x5 - (x95 - x5) * pad, x95 + (x95 - x5) * pad]
    y_range = [y5 - (y95 - y5) * pad, y95 + (y95 - y5) * pad]

    tract_nsa = _load_tract_nsa(data_dir)
    embedding["nsa_name"] = embedding["geoid"].map(tract_nsa).fillna("")

    labeled_tracts = _subsample_labels(embedding, "Tract", require_col="nsa_name")
    display_df     = _scale_pct_cols(embedding, feature_cols)
    display_df, feat_hover_map = _add_hover_fmt(display_df, feature_cols)
    display_df     = _add_viz_cols(display_df, labeled_tracts=labeled_tracts)

    has_nsa = bool(tract_nsa)
    hover_labels: dict[str, str] = {
        "x": "PC1", "y": "PC2",
        "cluster_label":  "Quadrant",
        "geo_type":       "Level",
        color_col:        color_label,
        "top_sr_type":    "Top type",
        "_sz": "", "_text": "", "_hover_title": "",
        **{hcol: _DEMO_HOVER_NAMES.get(orig, orig) for orig, hcol in feat_hover_map.items()},
    }

    fig = px.scatter(
        display_df.sort_values("geo_type"),  # tracts first → CSAs on top
        x="x", y="y",
        color=color_col,
        size="_sz",
        size_max=16,
        text="_text",
        hover_name="_hover_title",
        hover_data={
            "cluster_label":  True,
            "geo_type":       True,
            "top_sr_type":    True,
            "srtype_color":   False,
            "_sz": False, "_text": False, "_hover_title": False,
            **{hcol: True for hcol in feat_hover_map.values()},
        },
        labels=hover_labels,
        category_orders={color_col: srtype_order},
    )
    fig.update_traces(
        textposition="top center",
        textfont=dict(size=11, color="rgba(20,20,20,0.9)"),
        marker=dict(opacity=0.85, line=dict(width=0.5, color="white")),
    )
    fig.update_layout(height=620, **_top_legend_layout(is_categorical))
    fig.update_xaxes(range=x_range)
    fig.update_yaxes(range=y_range)
    _add_quadrant_backgrounds(fig, x_mid, y_mid, x_range, y_range)
    _dedup_legend(fig)
    st.plotly_chart(fig, use_container_width=True)
    nsa_note = (
        f"~{round(_CSA_LABEL_FRAC * 100):.0f}% of tract NSA names labeled (min {_CSA_LABEL_MIN_PER_QUAD} per quadrant). "
        "Hover any marker for neighborhood, quadrant, and demographic details."
        if has_nsa else
        "Run `python scripts/pipeline.py --stage nsa` to add neighborhood name labels. Hover for details."
    )
    st.caption(nsa_note)

    st.subheader(f"Predominant Service Type by Quadrant — {year}")
    n_by_quad = (
        embedding[embedding["geo_type"] == "Tract"]
        .groupby("cluster_label").size().to_dict()
    )
    summary = "  ·  ".join(f"**{q}** {n_by_quad.get(q, 0)}" for q in _QUADRANT_ORDER)
    st.caption(
        f"Tract counts by demographic quadrant: {summary}. "
        "Bars show the % of tracts in each quadrant whose top service call is each specific type."
    )
    _render_quadrant_srtype_bar(embedding, data_dir, year)

    st.divider()
    _render_neighborhood_list(embedding)


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
