import numpy as np
import pandas as pd


def parse_timestamps(df: pd.DataFrame) -> pd.DataFrame:
    """Convert millisecond-epoch columns to UTC datetime."""
    epoch_cols = ("CreatedDate", "CloseDate", "StatusDate", "DueDate", "LastActivityDate")
    for col in epoch_cols:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], unit="ms", utc=True, errors="coerce")
    return df


def compute_days_to_close(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["days_to_close"] = (
        (df["CloseDate"] - df["CreatedDate"]).dt.total_seconds() / 86400
    )
    # Negative values indicate data error — treat as missing
    df.loc[df["days_to_close"] < 0, "days_to_close"] = np.nan
    return df


def aggregate_tract(df: pd.DataFrame, geo_col: str = "tract_geoid") -> pd.DataFrame:
    """Return one row per tract with core equity metrics."""
    closed_mask = df["SRStatus"].str.strip().str.lower() == "closed"

    base = (
        df.groupby(geo_col)
        .agg(
            total_requests=("SRRecordID", "count"),
            closed_requests=("SRStatus", lambda s: (s.str.strip().str.lower() == "closed").sum()),
        )
        .reset_index()
    )

    dtc = (
        df.loc[closed_mask]
        .groupby(geo_col)["days_to_close"]
        .median()
        .reset_index(name="median_days_to_close")
    )

    top_type = (
        df.groupby([geo_col, "SRType"])
        .size()
        .reset_index(name="n")
        .sort_values("n", ascending=False)
        .drop_duplicates(subset=geo_col)
        [[geo_col, "SRType"]]
        .rename(columns={"SRType": "top_sr_type"})
    )

    out = (
        base
        .merge(dtc, on=geo_col, how="left")
        .merge(top_type, on=geo_col, how="left")
    )
    out["closure_rate"] = out["closed_requests"] / out["total_requests"].replace(0, np.nan)
    return out.rename(columns={geo_col: "geoid"})


def rollup_to_csa(
    tract_df: pd.DataFrame,
    tract_to_csa: pd.DataFrame,
) -> pd.DataFrame:
    """Aggregate tract metrics to CSA level, weighting days-to-close by tract population."""
    merged = tract_df.merge(
        tract_to_csa[["geoid", "csa_name", "population"]],
        on="geoid",
        how="left",
    )

    sums = (
        merged.groupby("csa_name")
        .agg(
            total_requests=("total_requests", "sum"),
            closed_requests=("closed_requests", "sum"),
        )
        .reset_index()
    )

    # Population-weighted mean of tract medians as proxy for CSA median
    valid = merged.dropna(subset=["median_days_to_close", "population"])
    if not valid.empty:
        wtd = (
            valid.groupby("csa_name")
            .apply(
                lambda g: np.average(g["median_days_to_close"], weights=g["population"]),
                include_groups=False,
            )
            .reset_index(name="median_days_to_close")
        )
        sums = sums.merge(wtd, on="csa_name", how="left")

    sums["closure_rate"] = sums["closed_requests"] / sums["total_requests"].replace(0, np.nan)
    return sums.rename(columns={"csa_name": "geoid"})
