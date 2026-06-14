"""Per-city 311 adapter contract for the cross-city comparison (Phase 5).

Each adapter knows how to fetch one city's raw 311 records for a year and map them to
Baltimore's canonical field names, so the city-agnostic aggregator
(`peer_metrics.compute_city_metrics`) treats every city identically.

Canonical fields — Baltimore's own names, adopted as the shared vocabulary:
    SRType, CreatedDate, CloseDate, Latitude, Longitude
`CreatedDate` / `CloseDate` are millisecond-epoch integers (the ArcGIS convention);
`CloseDate` is null/absent for still-open requests. The uniform cross-city closure rule
is "a request is closed iff it has a CloseDate" — recorded per city in
`closure_definition` and footnoted in the tab, because native closure semantics differ.

Two hooks let a city match its own published methodology so the cross-city numbers agree
with that city's own dashboards:
  - `scope(df)`  — restrict to comparable "real service requests". Default: non-ECC,
    geocoded. Baltimore additionally keeps only resident-initiated requests, mirroring the
    within-Baltimore equity subset (otherwise ECC information-calls and system records
    inflate volume and crush median days-to-close toward zero).
  - `is_closed(df)` — boolean per record. Default: CloseDate present. Baltimore overrides
    to use SRStatus, matching `metrics.aggregate_tract`.
"""
import pandas as pd

CANONICAL_FIELDS = ("SRType", "CreatedDate", "CloseDate", "Latitude", "Longitude")
ECC_PREFIX = "ECC-"


class CityAdapter:
    """Base adapter. Subclasses set the metadata attributes and implement `fetch`."""

    city: str = ""               # display name, e.g. "Washington, DC"
    fips: str = ""               # 5-digit state+county FIPS, e.g. "11001"
    portal_url: str = ""
    closure_definition: str = ""  # how "closed" is determined for this city

    def fetch(self, year: int) -> list[dict]:
        """Return this city's records for `year`, already mapped to canonical fields."""
        raise NotImplementedError

    def precomputed(self, year: int, proc_dir) -> dict | None:
        """Optionally return delivery metrics already computed elsewhere, to avoid a
        redundant fetch. Baltimore overrides this to read the within-app canonical pooled
        metrics (so its cross-city row equals the Operations tab exactly and the ~12-min
        re-fetch is skipped). Returns None by default — most cities fetch + compute.

        The dict, when returned, holds: total_requests, median_days_to_close, closure_rate,
        on_time_rate (population / requests_per_1k are added by the driver)."""
        return None

    def scope(self, df: pd.DataFrame) -> pd.DataFrame:
        """Restrict to comparable "real service requests": non-ECC and geocoded.
        Subclasses extend with city-specific filters (e.g. resident-initiated)."""
        mask = pd.Series(True, index=df.index)
        if "SRType" in df.columns:
            mask &= ~df["SRType"].astype(str).str.startswith(ECC_PREFIX, na=False)
        if "Latitude" in df.columns and "Longitude" in df.columns:
            lat = pd.to_numeric(df["Latitude"], errors="coerce")
            lon = pd.to_numeric(df["Longitude"], errors="coerce")
            mask &= lat.notna() & lon.notna() & (lat != 0) & (lon != 0)
        return df[mask]

    def is_closed(self, df: pd.DataFrame) -> pd.Series:
        """Boolean per record. Default: a CloseDate is present."""
        return df["CloseDate"].notna() if "CloseDate" in df.columns else pd.Series(False, index=df.index)



def apply_field_map(raw: list[dict], field_map: dict[str, str]) -> list[dict]:
    """Rename raw column keys to canonical names, keeping only mapped fields."""
    return [{canon: r.get(src) for src, canon in field_map.items()} for r in raw]
