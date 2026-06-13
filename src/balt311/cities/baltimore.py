"""Baltimore adapter — wraps the existing, proven `ingest.fetch_year` so Baltimore is
just one adapter among many in the cross-city comparison. The within-Baltimore pipeline
is untouched; this only re-exposes Baltimore's records under the adapter contract.

`ingest.fetch_year` already returns records in the canonical field names (SRType,
CreatedDate, CloseDate, Latitude, Longitude), so no field map is needed.
"""
from balt311 import ingest

from .base import CityAdapter


class BaltimoreAdapter(CityAdapter):
    city = "Baltimore, MD"
    fips = "24510"
    portal_url = "https://data.baltimorecity.gov"
    closure_definition = (
        "Closed = a CloseDate is present (the uniform cross-city rule). The "
        "within-Baltimore tabs use SRStatus instead, so these figures may differ slightly."
    )

    def fetch(self, year: int) -> list[dict]:
        return ingest.fetch_year(year)
