import numpy as np
import pandas as pd
import streamlit as st

from components.utils import format_metric

DISPLAY_METRICS: list[tuple[str, str, str]] = [
    # (label, column, format_type)
    ("Median days to close", "median_days_to_close", "float1"),
    ("Closure rate", "closure_rate", "pct"),
    ("On-time rate", "on_time_rate", "pct"),
    ("Requests / 1k residents", "requests_per_1k", "float1"),
    ("Total requests", "total_requests", "int"),
]

_PEER_FEATURE_COLS = ["pct_black", "pct_white", "median_income"]
_N_PEERS = 3


def _fmt(val, fmt: str) -> str:
    if pd.isna(val):
        return "—"
    if fmt == "pct":
        return f"{val:.1%}"
    if fmt == "float1":
        return f"{val:.1f}"
    if fmt == "int":
        return f"{int(val):,}"
    return str(val)


def _find_peers(
    selected_geoid: str,
    demographics: pd.DataFrame,
    n: int = _N_PEERS,
) -> list[str]:
    """Return geoids of the n most demographically similar geographies."""
    feat_cols = [c for c in _PEER_FEATURE_COLS if c in demographics.columns]
    if not feat_cols:
        return []
    df = demographics.dropna(subset=feat_cols).copy()
    if selected_geoid not in df["geoid"].values:
        return []

    X = df[feat_cols].copy().astype(float)
    for col in feat_cols:
        rng = X[col].max() - X[col].min()
        if rng > 0:
            X[col] = (X[col] - X[col].min()) / rng

    sel_vec = X.loc[df["geoid"] == selected_geoid].iloc[0].values
    others_mask = df["geoid"] != selected_geoid
    dists = np.linalg.norm(X[others_mask].values - sel_vec, axis=1)
    return df[others_mask].assign(_d=dists).nsmallest(n, "_d")["geoid"].tolist()


def render(row: pd.Series | None) -> None:
    st.subheader("Selected area")

    if row is None:
        st.caption("Click a tract or CSA on the map to see its summary statistics.")
        return

    geo_name = row.get("geo_label", row.iloc[0])
    st.markdown(f"**{geo_name}**")
    st.divider()

    for label, col, fmt in DISPLAY_METRICS:
        if col not in row.index:
            continue
        val = row[col]
        if pd.isna(val):
            continue
        if fmt == "pct":
            st.metric(label, f"{val:.1%}")
        elif fmt == "float1":
            st.metric(label, f"{val:.1f}")
        elif fmt == "int":
            st.metric(label, f"{int(val):,}")

    if "top_sr_type" in row.index and pd.notna(row["top_sr_type"]):
        st.divider()
        st.caption("Top request type")
        st.markdown(f"**{row['top_sr_type']}**")


def render_peer_comparison(
    selected_row: pd.Series,
    df: pd.DataFrame,
    demographics: pd.DataFrame,
) -> None:
    """Full-width panel: 3 most demographically similar neighborhoods with their metrics."""
    selected_geoid = selected_row.get("geoid", None)
    if selected_geoid is None or "geoid" not in selected_row.index:
        return

    peers = _find_peers(str(selected_geoid), demographics)
    if not peers:
        return

    st.subheader("Demographically similar neighborhoods")
    st.caption(
        "Neighborhoods with the most similar racial composition and median household income — "
        "a rough peer group for comparing service delivery."
    )

    # Build comparison table: selected + peers
    compare_geoids = [str(selected_geoid)] + peers
    compare_rows = df[df["geoid"].isin(compare_geoids)].set_index("geoid")

    rows_out: dict[str, list] = {"Neighborhood": []}
    for label, col, fmt in DISPLAY_METRICS:
        if col not in compare_rows.columns:
            continue
        rows_out[label] = []

    for geoid in compare_geoids:
        label_str = str(geoid)
        if geoid == str(selected_geoid):
            label_str = f"★ {geoid}"  # mark selected
        rows_out["Neighborhood"].append(label_str)
        if geoid in compare_rows.index:
            prow = compare_rows.loc[geoid]
            for lbl, col, fmt in DISPLAY_METRICS:
                if lbl in rows_out:
                    rows_out[lbl].append(_fmt(prow.get(col, float("nan")), fmt))
        else:
            for lbl in rows_out:
                if lbl != "Neighborhood":
                    rows_out[lbl].append("—")

    st.dataframe(
        pd.DataFrame(rows_out),
        use_container_width=True,
        hide_index=True,
    )
