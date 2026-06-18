"""Baltimore adapter — wraps the existing, proven `ingest.fetch_year` so Baltimore is
just one adapter among many in the cross-city comparison. The within-Baltimore pipeline
is untouched; this only re-exposes Baltimore's records under the adapter contract.

`ingest.fetch_year` returns the full raw record set (SRType, CreatedDate, CloseDate,
Latitude, Longitude, **plus SRStatus and MethodReceived**), so the adapter can reproduce
the within-Baltimore equity subset and SRStatus-based closure exactly — otherwise ECC
information-calls and system records would inflate volume ~2.5x and pull median
days-to-close to nearly zero (the bug that surfaced in the first MVP run).
"""
from pathlib import Path

import pandas as pd

from balt311 import ingest
from balt311.metrics import RESIDENT_METHODS

from .base import CityAdapter

# Matches metrics.aggregate_tract — what the within-Baltimore tabs count as closed.
_CLOSED_STATUSES = {"closed", "closed (transferred)"}


class BaltimoreAdapter(CityAdapter):
    city = "Baltimore, MD"
    fips = "24510"
    portal_url = "https://data.baltimorecity.gov"
    closure_definition = (
        "Same figures as the within-Baltimore tabs (single source of truth): equity subset "
        "— resident-initiated (Phone/API/Mail/Email), non-ECC, tract-geocoded; closed = "
        "SRStatus 'Closed' / 'Closed (Transferred)'; record-level pooled median."
    )

    def precomputed(self, year: int, proc_dir) -> dict | None:
        """Read the within-app canonical pooled metrics so the cross-city Baltimore row is
        identical to the Operations tab (and no 12-min re-fetch is needed). Falls back to
        fetch+compute if the file is missing (e.g. that year not yet (re)processed)."""
        path = Path(proc_dir) / f"citywide_metrics_{year}.parquet"
        if not path.exists():
            return None
        df = pd.read_parquet(path)
        df = df[df["year"] == year] if "year" in df.columns else df
        if df.empty:
            return None
        r = df.iloc[0]
        num = lambda v: float(v) if pd.notna(v) else None
        return {
            "total_requests": int(r["total_requests"]),
            "median_days_to_close": num(r.get("median_days_to_close")),
            "closure_rate": num(r.get("closure_rate")),
            "on_time_rate": num(r.get("on_time_rate")),
        }

    def precomputed_tract_srtype(self, year: int, proc_dir) -> pd.DataFrame | None:
        """Read the within-app `tract_srtype_metrics_{year}.parquet` directly — same
        shape the cross-city join produces for the fetch-fresh cities, and the source the
        within-Baltimore tabs already trust, so no re-fetch/re-join is needed."""
        path = Path(proc_dir) / f"tract_srtype_metrics_{year}.parquet"
        if not path.exists():
            return None
        df = pd.read_parquet(path)
        return df if not df.empty else None

    def precomputed_tract(self, year: int, proc_dir) -> pd.DataFrame | None:
        """Read the within-app `tract_metrics_{year}.parquet` directly — the raw,
        pooled-across-SRType grain the Phase 5.5-3 income equity score compares against
        `precomputed_tract_srtype`'s within-category figure. Its columns are a superset
        of `peer_metrics.compute_tract_metrics`'s shape (geoid, total_requests,
        closed_requests, closure_rate, median_days_to_close), so no re-fetch/re-join."""
        path = Path(proc_dir) / f"tract_metrics_{year}.parquet"
        if not path.exists():
            return None
        df = pd.read_parquet(path)
        return df if not df.empty else None

    def fetch(self, year: int) -> list[dict]:
        return ingest.fetch_year(year)

    def scope(self, df: pd.DataFrame) -> pd.DataFrame:
        df = super().scope(df)  # non-ECC + geocoded
        if "MethodReceived" in df.columns:
            df = df[df["MethodReceived"].isin(RESIDENT_METHODS)]
        return df

    def is_closed(self, df: pd.DataFrame) -> pd.Series:
        return df["SRStatus"].astype(str).str.strip().str.lower().isin(_CLOSED_STATUSES)

    def schema_fields(self, year: int) -> list[str] | None:
        from . import arcgis

        url = ingest.ENDPOINTS.get(year)
        return arcgis.layer_field_names(url) if url else None
