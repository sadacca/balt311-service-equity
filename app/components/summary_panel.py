import pandas as pd
import streamlit as st


DISPLAY_METRICS: list[tuple[str, str, str]] = [
    # (label, column, format_type)
    ("Median days to close", "median_days_to_close", "float1"),
    ("Closure rate", "closure_rate", "pct"),
    ("Reopen rate", "reopen_rate", "pct"),
    ("Requests / 1k residents", "requests_per_1k", "float1"),
    ("Total requests", "total_requests", "int"),
]


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
