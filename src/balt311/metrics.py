import numpy as np
import pandas as pd

# Resident-initiated intake channels (excludes System=proactive and Internal=staff)
RESIDENT_METHODS = {"Phone", "API", "Mail", "Email"}

# ECC (Emergency Communications Center) types are informational — no physical address,
# 92-100% missing coordinates, not relevant to service delivery equity analysis.
ECC_PREFIX = "ECC-"


def parse_timestamps(df: pd.DataFrame) -> pd.DataFrame:
    """Convert millisecond-epoch columns to UTC datetime."""
    epoch_cols = ("CreatedDate", "CloseDate", "StatusDate", "DueDate", "LastActivityDate")
    for col in epoch_cols:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], unit="ms", utc=True, errors="coerce")
    return df


def clean_strings(df: pd.DataFrame) -> pd.DataFrame:
    """Strip whitespace from string columns and normalize known encoding artifacts."""
    str_cols = ("Agency", "SRType", "SRStatus", "MethodReceived", "Neighborhood",
                "Outcome", "LastActivity")
    df = df.copy()
    for col in str_cols:
        if col in df.columns:
            df[col] = df[col].str.strip().str.replace(" ", " ", regex=False)
    return df


def flag_request_source(df: pd.DataFrame) -> pd.DataFrame:
    """Add is_resident (bool) based on MethodReceived value set confirmed in validation."""
    df = df.copy()
    df["is_resident"] = df["MethodReceived"].isin(RESIDENT_METHODS)
    return df


def compute_days_to_close(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["days_to_close"] = (
        (df["CloseDate"] - df["CreatedDate"]).dt.total_seconds() / 86400
    )
    # Sub-second negatives are timestamp precision artifacts in same-day closures — floor to 0.
    # True negative values (data errors) have not been observed; keep this as floor not NaN.
    df.loc[df["days_to_close"] < 0, "days_to_close"] = 0.0
    return df


def compute_due_date_gap(df: pd.DataFrame) -> pd.DataFrame:
    """Add due_date_gap_days and is_on_time. Types with negative gaps have bad DueDates — exclude."""
    df = df.copy()
    df["due_date_gap_days"] = (
        (df["DueDate"] - df["CreatedDate"]).dt.total_seconds() / 86400
    )
    # Only evaluate closed records with a valid (positive-gap) DueDate.
    # Open records have no CloseDate and should not count as "late".
    df["is_on_time"] = np.where(
        (df["due_date_gap_days"] > 0) & df["CloseDate"].notna(),
        df["CloseDate"] <= df["DueDate"],
        np.nan,
    )
    return df


def filter_equity_subset(
    df: pd.DataFrame,
    right_censor_days: int = 30,
) -> pd.DataFrame:
    """Return resident-initiated, non-ECC, geocoded requests suitable for equity analysis.

    right_censor_days: exclude requests created within this many days of the data pull date
    to avoid deflating closure rates for still-open recent requests. Set to 0 for annual
    files where the year is complete; use 30 for the live current-year endpoint.
    """
    cutoff = df["CreatedDate"].max() - pd.Timedelta(days=right_censor_days)
    return df[
        df["is_resident"]
        & ~df["SRType"].str.startswith(ECC_PREFIX, na=False)
        & df["tract_geoid"].notna()
        & (df["CreatedDate"] <= cutoff)
    ].copy()


def aggregate_tract(df: pd.DataFrame, geo_col: str = "tract_geoid") -> pd.DataFrame:
    """Return one row per tract with core equity metrics.

    Expects input already filtered to the equity subset (resident, non-ECC, geocoded).
    """
    closed_statuses = {"closed", "closed (transferred)"}
    closed_mask = df["SRStatus"].str.strip().str.lower().isin(closed_statuses)

    base = (
        df.groupby(geo_col)
        .agg(
            total_requests=("SRRecordID", "count"),
            closed_requests=("SRStatus", lambda s: s.str.strip().str.lower().isin(closed_statuses).sum()),
        )
        .reset_index()
    )

    dtc = (
        df.loc[closed_mask]
        .groupby(geo_col)["days_to_close"]
        .median()
        .reset_index(name="median_days_to_close")
    )

    # On-time rate: only for records with a valid (positive-gap) DueDate
    valid_due = df.loc[df["is_on_time"].notna()]
    if not valid_due.empty:
        ontime = (
            valid_due.groupby(geo_col)["is_on_time"]
            .mean()
            .reset_index(name="on_time_rate")
        )
    else:
        ontime = pd.DataFrame(columns=[geo_col, "on_time_rate"])

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
        .merge(ontime, on=geo_col, how="left")
        .merge(top_type, on=geo_col, how="left")
    )
    out["closure_rate"] = out["closed_requests"] / out["total_requests"].replace(0, np.nan)
    return out.rename(columns={geo_col: "geoid"})


def rollup_demographics_to_csa(
    tract_demo_df: pd.DataFrame,
    xwalk_df: pd.DataFrame,
) -> pd.DataFrame:
    """Aggregate tract-level ACS demographics to CSA level.

    Race percentages are recomputed from raw population counts (accurate).
    All other numeric columns (income, age, ethnicity, education, poverty) use
    a population-weighted mean of tract values — standard approximation, same
    methodology as BNIA Vital Signs. New demographic columns in the tract CSV
    are rolled up automatically without requiring changes here.
    """
    merged = tract_demo_df.merge(
        xwalk_df[["geoid", "csa_name"]], on="geoid", how="left"
    )
    merged = merged[merged["csa_name"].notna()].copy()

    # Race: from raw counts — most accurate method
    race_sums = (
        merged.groupby("csa_name")
        .agg(
            total_race_pop=("total_race_pop", "sum"),
            black_pop=("black_pop", "sum"),
            white_pop=("white_pop", "sum"),
        )
        .reset_index()
    )
    denom = race_sums["total_race_pop"].replace(0, float("nan"))
    race_sums["pct_black"] = race_sums["black_pop"] / denom
    race_sums["pct_white"] = race_sums["white_pop"] / denom
    result = race_sums.copy()

    # All other numeric columns: population-weighted mean of tract values.
    # Using total_race_pop as the weight — closely tracks each table's own
    # denominator (age: B01001_001E; education: B15003_001E; poverty: B17001_001E)
    # and is already in the CSV, keeping the rollup self-contained.
    raw_cols = {"geoid", "total_race_pop", "black_pop", "white_pop", "pct_black", "pct_white"}
    wtd_cols = [
        c for c in tract_demo_df.columns
        if c not in raw_cols and pd.api.types.is_numeric_dtype(tract_demo_df[c])
    ]
    for col in wtd_cols:
        valid = merged.dropna(subset=[col, "total_race_pop"])
        if valid.empty:
            result[col] = float("nan")
            continue
        col_wtd = (
            valid.groupby("csa_name")
            .apply(
                lambda g, c=col: np.average(g[c], weights=g["total_race_pop"]),
                include_groups=False,
            )
            .reset_index(name=col)
        )
        result = result.merge(col_wtd, on="csa_name", how="left")

    # Preserve column order: geoid first, then all others in tract CSV order
    ordered = ["csa_name"] + [c for c in tract_demo_df.columns if c != "geoid" and c in result.columns]
    return result[ordered].rename(columns={"csa_name": "geoid"})


def rollup_to_csa(
    tract_df: pd.DataFrame,
    tract_to_csa: pd.DataFrame,
) -> pd.DataFrame:
    """Aggregate tract metrics to CSA level, weighting days-to-close by tract population.

    tract_to_csa must have columns [geoid, csa_name]. Population is taken from
    tract_df (added during pipeline enrichment) so the crosswalk stays minimal.
    """
    merged = tract_df.merge(
        tract_to_csa[["geoid", "csa_name"]],
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

    valid_dtc = merged.dropna(subset=["median_days_to_close"])
    if "population" in merged.columns:
        # Population-weighted mean of tract medians
        pop_valid = valid_dtc.dropna(subset=["population"])
        if not pop_valid.empty:
            wtd = (
                pop_valid.groupby("csa_name")
                .apply(
                    lambda g: np.average(g["median_days_to_close"], weights=g["population"]),
                    include_groups=False,
                )
                .reset_index(name="median_days_to_close")
            )
            sums = sums.merge(wtd, on="csa_name", how="left")
    else:
        # Unweighted median fallback when population is unavailable
        dtc = (
            valid_dtc.groupby("csa_name")["median_days_to_close"]
            .median()
            .reset_index(name="median_days_to_close")
        )
        sums = sums.merge(dtc, on="csa_name", how="left")

    sums["closure_rate"] = sums["closed_requests"] / sums["total_requests"].replace(0, np.nan)

    # on_time_rate: request-weighted mean of tract rates
    valid_otr = merged.dropna(subset=["on_time_rate"])
    if not valid_otr.empty:
        otr = (
            valid_otr.groupby("csa_name")
            .apply(
                lambda g: np.average(g["on_time_rate"], weights=g["total_requests"]),
                include_groups=False,
            )
            .reset_index(name="on_time_rate")
        )
        sums = sums.merge(otr, on="csa_name", how="left")

    # requests_per_1k: CSA total requests / summed tract population
    if "population" in merged.columns:
        pop_sums = (
            merged.groupby("csa_name")["population"]
            .sum()
            .reset_index(name="population")
        )
        sums = sums.merge(pop_sums, on="csa_name", how="left")
        sums["requests_per_1k"] = (
            sums["total_requests"] / sums["population"].replace(0, np.nan) * 1000
        )

    # top_sr_type: most common tract-level top type within each CSA
    if "top_sr_type" in merged.columns:
        top_type = (
            merged.dropna(subset=["top_sr_type"])
            .groupby(["csa_name", "top_sr_type"])
            .size()
            .reset_index(name="n")
            .sort_values("n", ascending=False)
            .drop_duplicates(subset="csa_name")
            [["csa_name", "top_sr_type"]]
        )
        sums = sums.merge(top_type, on="csa_name", how="left")

    return sums.rename(columns={"csa_name": "geoid"})
