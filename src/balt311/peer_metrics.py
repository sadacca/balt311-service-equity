"""City-agnostic cross-city delivery metrics (Phase 5.1).

One row per (city, year), computed identically for every adapter's canonical records so
cities are comparable. Rates only — never raw counts (NYC dwarfs Baltimore). The closure
rule is uniform across cities ("closed = has a CloseDate"); each city's native semantics
are recorded in `closure_definition` and footnoted in the tab.
"""
import json
import os
import time
import urllib.request

import pandas as pd

from balt311.equity_stats import overlap_score, wmean

METRIC_COLUMNS = [
    "city", "year", "total_requests", "requests_per_1k",
    "median_days_to_close", "median_days_to_close_excl_same_day",
    "closure_rate", "on_time_rate",
    "pct_same_day_close", "population", "closure_definition",
]


def _parse_dt(values) -> pd.Series:
    """Parse a created/closed column to UTC datetime, accepting either ArcGIS millisecond
    epochs (numeric — Baltimore, DC) or ISO 8601 strings (Carto/Socrata — Philadelphia).
    Cohort cities span platforms, so the aggregator stays format-agnostic.

    Inspects the first non-null value rather than the column dtype: a `CloseDate` with open
    requests is object-dtype even when its values are ms-epoch ints, so a dtype check would
    misparse those ints as nanoseconds."""
    s = pd.Series(values)
    nonnull = s.dropna()
    if nonnull.empty:
        return pd.to_datetime(s, utc=True, errors="coerce")
    if pd.api.types.is_number(nonnull.iloc[0]):
        return pd.to_datetime(pd.to_numeric(s, errors="coerce"), unit="ms", utc=True, errors="coerce")
    # format="mixed" parses each string independently, tolerating rows that vary in tz
    # suffix / precision rather than coercing the odd one out to NaT.
    return pd.to_datetime(s, utc=True, errors="coerce", format="mixed")


def compute_city_metrics(
    records: list[dict],
    *,
    city: str,
    year: int,
    population: float | None = None,
    right_censor_days: int = 0,
    closure_definition: str = "",
    scope_fn=None,
    closed_fn=None,
) -> dict:
    """Delivery metrics for one city-year from canonical records.

    `scope_fn(df) -> df` restricts to the city's comparable "real service request" set
    (e.g. Baltimore's non-ECC, resident-initiated, geocoded subset) — without it, ECC
    information-calls inflate Baltimore's volume and drag median days-to-close to ~0.
    `closed_fn(df) -> bool Series` defines closure (Baltimore uses SRStatus; default is
    "CloseDate present"). `right_censor_days` drops requests created within that many days
    of the latest request (Baltimore's live-year rule). `population` (ACS county total)
    yields requests-per-1k. `on_time_rate` is null in the MVP — not every city publishes a
    due-date standard.
    """
    base = {
        "city": city, "year": int(year), "total_requests": 0,
        "requests_per_1k": None, "median_days_to_close": None,
        "median_days_to_close_excl_same_day": None, "closure_rate": None,
        "on_time_rate": None, "pct_same_day_close": None,
        "population": population, "closure_definition": closure_definition,
    }
    if not records:
        return base

    df = pd.DataFrame(records)
    df["_created"] = _parse_dt(df.get("CreatedDate"))
    df["_closed"] = _parse_dt(df.get("CloseDate"))

    if scope_fn is not None:
        df = scope_fn(df)

    if right_censor_days and df["_created"].notna().any():
        cutoff = df["_created"].max() - pd.Timedelta(days=right_censor_days)
        df = df[df["_created"] <= cutoff]

    total = int(len(df))
    if total == 0:
        return base

    is_closed = closed_fn(df) if closed_fn is not None else df["_closed"].notna()
    days = (df["_closed"] - df["_created"]).dt.total_seconds() / 86400.0
    # Floor only genuine sub-second *negatives* (close just before open) to 0; leave NaN as NaN
    # — a record closed-by-status but missing a close timestamp (e.g. KC's resolved-without-
    # resolved_date) has no valid duration and must be excluded from the median, not counted as
    # a 0-day closure (which would fake auto-close contamination).
    days = days.mask(days < 0, 0.0)
    closed_days = days[is_closed.astype(bool)].dropna()

    nonzero_days = closed_days[closed_days > 0]
    base.update(
        total_requests=total,
        requests_per_1k=(total / population * 1000.0) if population else None,
        median_days_to_close=float(closed_days.median()) if not closed_days.empty else None,
        # "Clean" median that drops 0-day (same-instant / auto-close) closures, for a more
        # comparable delivery figure across cities that auto-close referral/duplicate/invalid
        # records. Shown alongside the raw median (which stays flagged), never as a replacement.
        median_days_to_close_excl_same_day=float(nonzero_days.median()) if not nonzero_days.empty else None,
        closure_rate=float(is_closed.astype(bool).mean()),
        # Share of CLOSED requests that close the same instant they open — a direct measure of
        # auto-close / same-timestamp contamination. A high value means median days-to-close and
        # closure rate are inflated by instantly-resolved (often referral/duplicate/invalid)
        # records rather than real service delivery; the delivery tab flags it.
        pct_same_day_close=float((closed_days == 0).mean()) if not closed_days.empty else None,
    )
    return base


def _fetch_state_counties_pop(state: str, counties: list[str], acs_year: int, api_key: str) -> float | None:
    """Summed ACS 5-year population (B01003) for one or more counties in a single state."""
    url = (
        f"https://api.census.gov/data/{acs_year}/acs/acs5"
        f"?get=B01003_001E&for=county:{','.join(counties)}&in=state:{state}"
        + (f"&key={api_key}" if api_key else "")
    )
    for attempt in range(1, 5):
        try:
            req = urllib.request.Request(url, headers={"Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=30) as resp:
                rows = json.loads(resp.read().decode("utf-8"))
            return float(sum(float(r[0]) for r in rows[1:]))  # skip header row
        except Exception:
            if attempt == 4:
                return None
            time.sleep(2 ** attempt)
    return None


def fetch_county_population(fips: str, acs_year: int = 2023) -> float | None:
    """ACS 5-year total population (B01003) for a 5-digit state+county FIPS, or the SUM across
    several comma-separated FIPS (e.g. NYC's five boroughs "36005,36047,36061,36081,36085").
    Reads CENSUS_API_KEY from the environment if set. Returns None on failure (per-1k omitted)."""
    parts = [f.strip() for f in str(fips).split(",") if f.strip()]
    if not parts:
        return None
    api_key = os.environ.get("CENSUS_API_KEY", "").strip()
    by_state: dict[str, list[str]] = {}
    for f in parts:
        by_state.setdefault(f[:2], []).append(f[2:])
    total = 0.0
    for state, counties in by_state.items():
        pop = _fetch_state_counties_pop(state, counties, acs_year, api_key)
        if pop is None:
            return None
        total += pop
    return total


def fetch_place_population(place_fips: str, acs_year: int = 2023) -> float | None:
    """ACS 5-year total population (B01003) for a 7-digit state+place FIPS ("SSPPPPP", e.g.
    Chicago "1714000"). The **city-proper** denominator — correct for a city 311 system, and
    far more accurate than the county for cities that are a small part of their county
    (Chicago ⊂ Cook, Austin ⊂ Travis). Returns None on failure (caller falls back to county)."""
    fips = str(place_fips).strip()
    if len(fips) != 7:
        return None
    state, place = fips[:2], fips[2:]
    api_key = os.environ.get("CENSUS_API_KEY", "").strip()
    url = (
        f"https://api.census.gov/data/{acs_year}/acs/acs5"
        f"?get=B01003_001E&for=place:{place}&in=state:{state}"
        + (f"&key={api_key}" if api_key else "")
    )
    for attempt in range(1, 5):
        try:
            req = urllib.request.Request(url, headers={"Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=30) as resp:
                rows = json.loads(resp.read().decode("utf-8"))
            return float(rows[1][0])  # header row, then the single place row
        except Exception:
            if attempt == 4:
                return None
            time.sleep(2 ** attempt)
    return None


_ACS_MISSING = {"-666666666", -666666666}  # Census's sentinel for "no sample/undefined" cells


def _fetch_state_county_tract_income(state: str, county: str, acs_year: int,
                                      api_key: str) -> list[dict]:
    """Median household income (B19013_001E) for every tract in one state+county."""
    url = (
        f"https://api.census.gov/data/{acs_year}/acs/acs5"
        f"?get=B19013_001E&for=tract:*&in=state:{state}%20county:{county}"
        + (f"&key={api_key}" if api_key else "")
    )
    for attempt in range(1, 5):
        try:
            req = urllib.request.Request(url, headers={"Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=30) as resp:
                rows = json.loads(resp.read().decode("utf-8"))
            out = []
            for income_raw, st, co, tract in rows[1:]:  # skip header row
                income = None if income_raw in _ACS_MISSING else float(income_raw)
                out.append({"geoid": f"{st}{co}{tract}", "median_income": income})
            return out
        except Exception:
            if attempt == 4:
                raise
            time.sleep(2 ** attempt)
    return []


def fetch_tract_median_income(fips: str, acs_year: int = 2023) -> pd.DataFrame:
    """Tract-level median household income for a 5-digit state+county FIPS, or several
    comma-separated FIPS (NYC's five boroughs). Same retry/env-key conventions as
    `fetch_county_population`. Returns a DataFrame with `geoid` (11-digit tract GEOID) and
    `median_income` (NaN for tracts ACS couldn't estimate — typically near-zero population,
    e.g. parkland or industrial tracts). Raises on failure (caller decides whether to skip
    the city) rather than silently returning an empty/partial table."""
    parts = [f.strip() for f in str(fips).split(",") if f.strip()]
    api_key = os.environ.get("CENSUS_API_KEY", "").strip()
    by_state: dict[str, list[str]] = {}
    for f in parts:
        by_state.setdefault(f[:2], []).append(f[2:])
    rows: list[dict] = []
    for state, counties in by_state.items():
        for county in counties:
            rows.extend(_fetch_state_county_tract_income(state, county, acs_year, api_key))
    return pd.DataFrame(rows, columns=["geoid", "median_income"])


_TRACT_SRTYPE_COLS = ["geoid", "SRType", "total_requests", "closed_requests",
                      "closure_rate", "median_days_to_close"]
_TRACT_COLS = ["geoid", "total_requests", "closed_requests",
              "closure_rate", "median_days_to_close"]


def _join_records_to_tracts(records: list[dict], *, tracts, scope_fn=None,
                            closed_fn=None) -> pd.DataFrame:
    """Shared point-in-polygon join behind `compute_tract_srtype_metrics` and
    `compute_tract_metrics` — scope, geocode-filter, and spatial-join records to
    `tracts` once, annotated with `_is_closed`/`_days`, so a driver computing both
    grains pays for one TIGER join, not two. Returns an empty DataFrame (no `geoid`
    column) if there's nothing to join."""
    if not records:
        return pd.DataFrame()

    import geopandas as gpd

    df = pd.DataFrame(records)
    df["_created"] = _parse_dt(df.get("CreatedDate"))
    df["_closed"] = _parse_dt(df.get("CloseDate"))
    if scope_fn is not None:
        df = scope_fn(df)

    lat = pd.to_numeric(df.get("Latitude"), errors="coerce")
    lon = pd.to_numeric(df.get("Longitude"), errors="coerce")
    geocoded = df[lat.notna() & lon.notna() & (lat != 0) & (lon != 0)].copy()
    if geocoded.empty:
        return pd.DataFrame()

    gdf = gpd.GeoDataFrame(
        geocoded,
        geometry=gpd.points_from_xy(
            pd.to_numeric(geocoded["Longitude"]), pd.to_numeric(geocoded["Latitude"])
        ),
        crs="EPSG:4326",
    )
    joined = gpd.sjoin(gdf, tracts[["GEOID", "geometry"]], how="left", predicate="within")
    joined = pd.DataFrame(joined.drop(columns=["geometry", "index_right"], errors="ignore"))
    joined = joined.rename(columns={"GEOID": "geoid"})

    is_closed = closed_fn(joined) if closed_fn is not None else joined["_closed"].notna()
    joined["_is_closed"] = is_closed.astype(bool)
    days = (joined["_closed"] - joined["_created"]).dt.total_seconds() / 86400.0
    joined["_days"] = days.mask(days < 0, 0.0)
    return joined


def _aggregate_tract(joined: pd.DataFrame, group_cols: list[str], out_cols: list[str]) -> pd.DataFrame:
    """Groupby `group_cols` (`["geoid"]` or `["geoid", "SRType"]`) over an already-joined
    frame from `_join_records_to_tracts`, producing total/closed requests, closure rate,
    and median days to close — the shared aggregation behind both tract grains."""
    base = joined.dropna(subset=group_cols)
    if base.empty:
        return pd.DataFrame(columns=out_cols)

    agg = (
        base.groupby(group_cols)
        .agg(total_requests=(group_cols[0], "size"), closed_requests=("_is_closed", "sum"))
        .reset_index()
    )
    agg["closure_rate"] = agg["closed_requests"] / agg["total_requests"].replace(0, float("nan"))
    dtc = (
        base[base["_is_closed"]].dropna(subset=["_days"])
        .groupby(group_cols)["_days"].median()
        .reset_index(name="median_days_to_close")
    )
    agg = agg.merge(dtc, on=group_cols, how="left")
    return agg[out_cols]


def compute_tract_srtype_metrics(records: list[dict], *, tracts, scope_fn=None,
                                  closed_fn=None) -> pd.DataFrame:
    """City-agnostic tract×SRType metrics — mirrors Baltimore's own
    `tract_srtype_metrics_{year}.parquet` shape (geoid, SRType, total_requests,
    closed_requests, closure_rate, median_days_to_close), the input Phase 5.5-3's
    within-category equity scoring needs (joined against `peer_city_tract_income.parquet`
    on `geoid`). `tracts` is this city's TIGER tract boundaries (`balt311.tiger.
    fetch_city_tracts`); requests are point-in-polygon joined to tracts, same as the
    within-Baltimore pipeline (`scripts/pipeline.py` stage 2). `scope_fn`/`closed_fn`
    are the adapter's own hooks (`CityAdapter.scope`/`is_closed`), so the same
    "real service request" subset and closure rule feeds both the city-level delivery
    metrics (`compute_city_metrics`) and this tract-level breakdown.

    Returns an empty (but correctly-columned) DataFrame if there are no records, no
    geocoded records after scoping, or no rows that fall inside `tracts`."""
    joined = _join_records_to_tracts(records, tracts=tracts, scope_fn=scope_fn, closed_fn=closed_fn)
    if joined.empty:
        return pd.DataFrame(columns=_TRACT_SRTYPE_COLS)
    return _aggregate_tract(joined, ["geoid", "SRType"], _TRACT_SRTYPE_COLS)


def compute_tract_and_srtype_metrics(records: list[dict], *, tracts, scope_fn=None,
                                     closed_fn=None) -> tuple[pd.DataFrame, pd.DataFrame]:
    """`compute_tract_metrics` and `compute_tract_srtype_metrics` together, joining
    records to `tracts` once rather than twice — the driver (`scripts/peer_city.py`)
    needs both grains per city-year (the raw and within-category Phase 5.5-3 income
    equity score), and the TIGER spatial join is the expensive part of either call.
    Returns `(tract_df, tract_srtype_df)`."""
    joined = _join_records_to_tracts(records, tracts=tracts, scope_fn=scope_fn, closed_fn=closed_fn)
    if joined.empty:
        return pd.DataFrame(columns=_TRACT_COLS), pd.DataFrame(columns=_TRACT_SRTYPE_COLS)
    tract_df = _aggregate_tract(joined, ["geoid"], _TRACT_COLS)
    srtype_df = _aggregate_tract(joined, ["geoid", "SRType"], _TRACT_SRTYPE_COLS)
    return tract_df, srtype_df


def compute_tract_metrics(records: list[dict], *, tracts, scope_fn=None,
                          closed_fn=None) -> pd.DataFrame:
    """City-agnostic tract metrics pooled across service type (geoid, total_requests,
    closed_requests, closure_rate, median_days_to_close) — the **raw**, non-stratified
    grain the Phase 5.5-3 income equity score compares against the within-category
    mix-adjusted score, mirroring how the within-Baltimore Equity tab's raw geo-level
    score is read from `tract_metrics_{year}.parquet` rather than re-derived from the
    SRType-stratified table (a median doesn't decompose into a weighted mean of
    per-type medians). Same join/scope/closure conventions as
    `compute_tract_srtype_metrics`; pass it the same `_join_records_to_tracts` output
    to avoid a second TIGER fetch + spatial join for the same city/year."""
    joined = _join_records_to_tracts(records, tracts=tracts, scope_fn=scope_fn, closed_fn=closed_fn)
    if joined.empty:
        return pd.DataFrame(columns=_TRACT_COLS)
    return _aggregate_tract(joined, ["geoid"], _TRACT_COLS)


EQUITY_COLUMNS = [
    "city", "year", "adj_income_score", "raw_income_score",
    "raw_median_days_gap", "n_tracts", "n_srtypes_scored",
]


def compute_income_equity_score(
    tract_srtype: pd.DataFrame,
    tract_metrics: pd.DataFrame,
    tract_income: pd.DataFrame,
    *, min_geo_srtype_n: int = 5,
) -> dict:
    """One city-year's income-only equity score (Phase 5.5-3) — income-only per the
    TASKS.md Phase 5.5 scope decision (race needs a city-appropriate group definition
    that doesn't generalize the way income's self-relative above/below-own-median split
    does). Mirrors the within-Baltimore Tab 6 (`equity_adjusted.compute_adjusted_scores`)
    pattern but reuses `balt311.equity_stats.overlap_score`/`wmean` directly rather than
    Streamlit-cached helpers, so this runs in the headless pipeline.

    `tract_srtype` is this city-year's `compute_tract_srtype_metrics` output (or the
    within-app `tract_srtype_metrics_{year}.parquet` for Baltimore); `tract_metrics` is
    the matching `compute_tract_metrics` (non-stratified) output; `tract_income` is this
    city's (year-independent) `peer_city_tract_income.parquet` rows. Tracts are split
    above/below *this city's own* median income — self-relative, so no group is ever
    empty (unlike a fixed national income cutoff).

    - `raw_income_score` — `overlap_score` over each tract's pooled (all-SRType) median
      days to close, split by income group. The citywide, non-stratified figure.
    - `adj_income_score` — `overlap_score` computed **within each SRType** (>= `min_geo_
      srtype_n` requests in that tract×SRType cell, the same sparse-cell suppression the
      within-Baltimore tabs use), then combined volume-weighted across types — isolates
      *how* the same service is delivered from *which* services an area requests more.
    - `raw_median_days_gap` — below-median-income tracts' median days minus above's; a
      positive gap means lower-income areas wait longer.

    Returns `None` for any score that can't be computed (e.g. no valid income data, or
    no SRType has enough coverage), never raises."""
    income = tract_income.dropna(subset=["median_income"]) if tract_income is not None else pd.DataFrame()
    base = {
        "adj_income_score": None, "raw_income_score": None, "raw_median_days_gap": None,
        "n_tracts": 0, "n_srtypes_scored": 0,
    }
    if income.empty:
        return base
    city_median = income["median_income"].median()
    below_geoids = set(income.loc[income["median_income"] <= city_median, "geoid"])
    above_geoids = set(income.loc[income["median_income"] > city_median, "geoid"])

    if tract_metrics is not None and not tract_metrics.empty:
        tm = tract_metrics.dropna(subset=["median_days_to_close"])
        below = tm.loc[tm["geoid"].isin(below_geoids), "median_days_to_close"]
        above = tm.loc[tm["geoid"].isin(above_geoids), "median_days_to_close"]
        score = overlap_score(below, above)
        base["raw_income_score"] = score if score == score else None
        if len(below.dropna()) and len(above.dropna()):
            base["raw_median_days_gap"] = float(below.median() - above.median())
        base["n_tracts"] = int(tm["geoid"].nunique())

    if tract_srtype is not None and not tract_srtype.empty:
        eligible = tract_srtype[tract_srtype["total_requests"] >= min_geo_srtype_n]
        eligible = eligible.dropna(subset=["median_days_to_close"])
        per_type = []
        for srtype, grp in eligible.groupby("SRType"):
            below = grp.loc[grp["geoid"].isin(below_geoids), "median_days_to_close"]
            above = grp.loc[grp["geoid"].isin(above_geoids), "median_days_to_close"]
            score = overlap_score(below, above)
            if score == score:
                per_type.append({"SRType": srtype, "score": score, "volume": grp["total_requests"].sum()})
        if per_type:
            per_df = pd.DataFrame(per_type)
            adj = wmean(per_df, "score", "volume")
            base["adj_income_score"] = adj if adj == adj else None
            base["n_srtypes_scored"] = len(per_type)

    return base


def upsert_metrics(existing: pd.DataFrame, new_rows: list[dict]) -> pd.DataFrame:
    """Merge freshly computed (city, year) rows into the metrics table, replacing any
    existing row for the same city-year, and return it sorted."""
    new_df = pd.DataFrame(new_rows, columns=METRIC_COLUMNS)
    if existing is None or existing.empty:
        combined = new_df
    else:
        keys = set(zip(new_df["city"], new_df["year"]))
        kept = existing[~existing.apply(lambda r: (r["city"], r["year"]) in keys, axis=1)]
        combined = pd.concat([kept, new_df], ignore_index=True)
    return combined.sort_values(["city", "year"]).reset_index(drop=True)
