import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from components.utils import format_metric, hex_to_rgba, overlap_score, score_label

# Colors: dark red for disadvantaged group, steel blue for advantaged group
_COLOR_A = "#8B2020"  # majority-Black / below-median-income
_COLOR_B = "#1F4E8C"  # majority-White / above-median-income

_N_OUTLIERS = 5  # neighborhoods shown in the worst-performer table


def _fmt_geoid(geoid: str) -> str:
    """Format 11-digit tract GEOID as 'Tract XXXX.XX'; leave CSA names unchanged."""
    s = str(geoid)
    if s.isdigit() and len(s) == 11:
        t = s[5:]
        return f"Tract {t[:4]}.{t[4:]}"
    return s


def _render_outlier_table(df: pd.DataFrame, metric_col: str, metric_label: str) -> None:
    """Show the N neighborhoods with the most extreme (worst) metric values."""
    valid = df[["geoid", metric_col]].dropna(subset=[metric_col]).copy()
    if len(valid) < _N_OUTLIERS + 1:
        return

    # "Worst": highest days-to-close / requests_per_1k; lowest closure/on-time rate
    ascending = metric_col not in ("closure_rate", "on_time_rate")
    worst = valid.nlargest(_N_OUTLIERS, metric_col) if ascending else valid.nsmallest(_N_OUTLIERS, metric_col)
    worst["Neighborhood"] = worst["geoid"].map(_fmt_geoid)

    if metric_col in ("closure_rate", "on_time_rate"):
        worst[metric_label] = worst[metric_col].apply(lambda x: f"{x:.1%}")
    else:
        worst[metric_label] = worst[metric_col].apply(lambda x: f"{x:.1f}")

    direction = "longest wait" if metric_col == "median_days_to_close" else (
        "lowest rate" if metric_col in ("closure_rate", "on_time_rate") else "highest count"
    )
    st.markdown(f"**Neighborhoods most in need of attention** ({direction})")
    st.dataframe(
        worst[["Neighborhood", metric_label]].reset_index(drop=True),
        use_container_width=True,
        hide_index=True,
    )


def _box_trace(
    values: pd.Series,
    name: str,
    color: str,
) -> go.Box:
    return go.Box(
        y=values.dropna(),
        name=name,
        boxpoints="all",
        jitter=0.4,
        pointpos=0,
        marker=dict(color=color, size=5, opacity=0.45),
        line=dict(color=color, width=2),
        fillcolor=hex_to_rgba(color, 0.15),
        whiskerwidth=0.4,
    )


def _comparison_fig(
    group_a: pd.Series,
    label_a: str,
    group_b: pd.Series,
    label_b: str,
    metric_col: str,
    key: str,
) -> None:
    """Render a two-group box comparison plus overlap score badge."""
    n_a, n_b = len(group_a.dropna()), len(group_b.dropna())

    fig = go.Figure([
        _box_trace(group_a, f"{label_a} (n={n_a})", _COLOR_A),
        _box_trace(group_b, f"{label_b} (n={n_b})", _COLOR_B),
    ])
    fig.update_layout(
        height=300,
        margin={"t": 8, "b": 8, "l": 50, "r": 8},
        showlegend=True,
        legend=dict(orientation="h", yanchor="bottom", y=1.01, xanchor="right", x=1, font_size=11),
        yaxis=dict(gridcolor="#eeeeee", zeroline=False),
        plot_bgcolor="white",
        paper_bgcolor="white",
    )

    chart_col, badge_col = st.columns([3, 1])
    with chart_col:
        st.plotly_chart(fig, use_container_width=True, key=key, config={"displayModeBar": False})

    with badge_col:
        score = overlap_score(group_a, group_b)
        label, css_color = score_label(score)

        st.markdown("**Equity score**")
        if not np.isnan(score):
            st.markdown(
                f"<span style='font-size:1.6rem;font-weight:700;color:{css_color}'>"
                f"{score:.0%}</span>",
                unsafe_allow_html=True,
            )
        st.markdown(
            f"<span style='color:{css_color};font-weight:600'>{label}</span>",
            unsafe_allow_html=True,
        )
        st.caption("100% = no gap · 0% = complete separation")

        med_a = group_a.median()
        med_b = group_b.median()
        if not (np.isnan(med_a) or np.isnan(med_b)):
            diff = abs(med_a - med_b)
            worse_label = label_a if med_a > med_b else label_b
            # For closure/on-time rate, higher is better; for days and requests_per_1k, lower is better
            if metric_col in ("closure_rate", "on_time_rate"):
                worse_label = label_a if med_a < med_b else label_b
            st.caption(
                f"{worse_label} trails by {format_metric(diff, metric_col)}"
            )


def render_equity_distributions(
    df: pd.DataFrame,
    demographics: pd.DataFrame,
    metric_col: str,
    metric_label: str,
) -> None:
    st.subheader("Equity by Demographics")
    st.caption(
        f"How does **{metric_label}** compare across race and income groups? "
        "Each chart shows the range of outcomes for two types of neighborhoods side by side — "
        "the closer the distributions, the more equitable the picture. "
        "Equity score: 100% = no gap · >70% = not bad · 40–70% = could be better · <40% = needs review."
    )

    merged = df.merge(demographics, on="geoid", how="left")
    valid = merged.dropna(subset=[metric_col])

    if valid.empty:
        st.info("No metric data available for equity analysis.")
        return

    col_race, col_income = st.columns(2)

    # ── Race comparison ───────────────────────────────────────────────────────
    with col_race:
        st.markdown("**Race — majority-Black vs. majority-White geographies**")
        race_valid = valid.dropna(subset=["pct_black", "pct_white"])
        black_group = race_valid[race_valid["pct_black"] > 0.5][metric_col]
        white_group = race_valid[race_valid["pct_white"] > 0.5][metric_col]

        if len(black_group.dropna()) >= 3 and len(white_group.dropna()) >= 3:
            _comparison_fig(
                black_group, "Maj. Black",
                white_group, "Maj. White",
                metric_col,
                key=f"dist_race_{metric_col}",
            )
        else:
            st.caption(
                f"Too few majority-race geographies to compare "
                f"(Black n={len(black_group)}, White n={len(white_group)})."
            )

    # ── Income comparison ─────────────────────────────────────────────────────
    with col_income:
        st.markdown("**Income — below vs. above median household income**")
        income_valid = valid.dropna(subset=["median_income"])
        city_median = income_valid["median_income"].median()
        below = income_valid[income_valid["median_income"] <= city_median][metric_col]
        above = income_valid[income_valid["median_income"] > city_median][metric_col]

        if len(below.dropna()) >= 3 and len(above.dropna()) >= 3:
            _comparison_fig(
                below, "Below median income",
                above, "Above median income",
                metric_col,
                key=f"dist_income_{metric_col}",
            )
        else:
            st.caption(
                f"Too few geographies with income data "
                f"(below n={len(below)}, above n={len(above)})."
            )

    st.divider()
    _render_outlier_table(valid, metric_col, metric_label)
