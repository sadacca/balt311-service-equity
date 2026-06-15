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
    days = days.where(days >= 0, 0.0)  # floor sub-second negatives (same-day closures)
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
