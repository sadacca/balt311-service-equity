"""Per-city 311 adapter contract for the cross-city comparison (Phase 5).

Each adapter knows how to fetch one city's raw 311 records for a year and map them to
Baltimore's canonical field names, so the city-agnostic aggregator
(`peer_metrics.compute_city_metrics`) treats every city identically.

Canonical fields — Baltimore's own names, adopted as the shared vocabulary:
    SRType, CreatedDate, CloseDate, Latitude, Longitude
`CreatedDate` / `CloseDate` are either millisecond-epoch integers (ArcGIS — Baltimore, DC)
or ISO 8601 strings (Carto/Socrata — Philadelphia); `peer_metrics._parse_dt` accepts both.
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
    place_fips: str = ""         # optional 7-digit state+place FIPS for the city-proper
                                 # per-1k denominator (Chicago "1714000"); falls back to `fips`
                                 # (county) when unset — used where county ≈ city (SF, Philly)
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

    def precomputed_tract_srtype(self, year: int, proc_dir) -> pd.DataFrame | None:
        """Optional tract×SRType metrics already computed elsewhere (Phase 5.5-2), to avoid
        a redundant fetch + spatial join. Baltimore overrides this to read its own
        within-app `tract_srtype_metrics_{year}.parquet` so the cross-city equity input
        matches the within-Baltimore tabs exactly. Returns None by default — most cities
        fetch + join fresh in `peer_city.py`.

        Columns when returned: geoid, SRType, total_requests, closed_requests,
        closure_rate, median_days_to_close — the same shape
        `peer_metrics.compute_tract_srtype_metrics` produces for the fetch-fresh cities."""
        return None

    def precomputed_tract(self, year: int, proc_dir) -> pd.DataFrame | None:
        """Optional non-stratified (pooled across SRType) tract metrics, the raw grain
        the Phase 5.5-3 income equity score compares against the within-category
        `precomputed_tract_srtype` figure. Baltimore overrides this to read its own
        within-app `tract_metrics_{year}.parquet`. Returns None by default.

        Columns when returned: geoid, total_requests, closed_requests, closure_rate,
        median_days_to_close — the same shape `peer_metrics.compute_tract_metrics`
        produces for the fetch-fresh cities."""
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
