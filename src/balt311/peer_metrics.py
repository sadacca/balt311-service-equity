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
    "median_days_to_close", "closure_rate", "on_time_rate",
    "population", "closure_definition",
]


def compute_city_metrics(
    records: list[dict],
    *,
    city: str,
    year: int,
    population: float | None = None,
    right_censor_days: int = 0,
    closure_definition: str = "",
) -> dict:
    """Delivery metrics for one city-year from canonical records.

    `right_censor_days` drops requests created within that many days of the latest
    request (Baltimore's live-year rule), so a city queried mid-year isn't penalized for
    recently-opened, not-yet-closed requests. `population` (ACS county total) yields
    requests-per-1k; omit it to leave that metric null. `on_time_rate` is null in the
    MVP — not every city publishes a due-date standard.
    """
    base = {
        "city": city, "year": int(year), "total_requests": 0,
        "requests_per_1k": None, "median_days_to_close": None, "closure_rate": None,
        "on_time_rate": None, "population": population, "closure_definition": closure_definition,
    }
    if not records:
        return base

    df = pd.DataFrame(records)
    created = pd.to_datetime(df.get("CreatedDate"), unit="ms", utc=True, errors="coerce")
    closed = pd.to_datetime(df.get("CloseDate"), unit="ms", utc=True, errors="coerce")

    if right_censor_days and created.notna().any():
        cutoff = created.max() - pd.Timedelta(days=right_censor_days)
        keep = created <= cutoff
        created, closed = created[keep], closed[keep]

    total = int(created.shape[0])
    if total == 0:
        return base

    is_closed = closed.notna()
    days = (closed - created).dt.total_seconds() / 86400.0
    days = days.where(days >= 0, 0.0)  # floor sub-second negatives (same-day closures)

    base.update(
        total_requests=total,
        requests_per_1k=(total / population * 1000.0) if population else None,
        median_days_to_close=float(days[is_closed].median()) if is_closed.any() else None,
        closure_rate=float(is_closed.mean()),
    )
    return base


def fetch_county_population(fips: str, acs_year: int = 2023) -> float | None:
    """ACS 5-year total population (B01003) for a 5-digit state+county FIPS. Reads
    CENSUS_API_KEY from the environment if set. Returns None on failure (per-1k omitted)."""
    state, county = fips[:2], fips[2:]
    api_key = os.environ.get("CENSUS_API_KEY", "").strip()
    url = (
        f"https://api.census.gov/data/{acs_year}/acs/acs5"
        f"?get=B01003_001E&for=county:{county}&in=state:{state}"
        + (f"&key={api_key}" if api_key else "")
    )
    for attempt in range(1, 5):
        try:
            req = urllib.request.Request(url, headers={"Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=30) as resp:
                rows = json.loads(resp.read().decode("utf-8"))
            return float(rows[1][0])  # header row, then the single county row
        except Exception:
            if attempt == 4:
                return None
            time.sleep(2 ** attempt)
    return None


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
