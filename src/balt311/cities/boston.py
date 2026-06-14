"""Boston — Analyze Boston 311 Service Requests (CKAN, one resource per year).

The first CKAN city. Boston publishes a per-year resource (UUID) under the `311-service-requests`
package; the adapter resolves the right resource for the requested year, then pages it. Fields:
`open_dt`/`closed_dt`/`type`/`latitude`/`longitude`/`case_status` (closed = case_status 'Closed')."""
import pandas as pd

from . import ckan
from .base import CityAdapter, apply_field_map

API_BASE = "https://data.boston.gov/api/3/action"
PACKAGE_ID = "311-service-requests"

FIELD_MAP = {
    "open_dt": "CreatedDate",
    "closed_dt": "CloseDate",
    "type": "SRType",
    "latitude": "Latitude",
    "longitude": "Longitude",
    "case_status": "status",
}


class BostonAdapter(CityAdapter):
    city = "Boston, MA"
    fips = "25025"  # Suffolk County (city-proxy denominator)
    portal_url = "https://data.boston.gov/dataset/311-service-requests"
    closure_definition = (
        "Closed = case_status 'Closed'. Non-ECC, geocoded. Median days = closed_dt − open_dt. "
        "Per-1k uses Suffolk County (city-proxy). Note: Oct-2025 backend migration may split "
        "later years across legacy/new datasets."
    )

    def fetch(self, year: int) -> list[dict]:
        rid = ckan.find_resource_for_year(API_BASE, PACKAGE_ID, year)
        if not rid:
            print(f"  Boston: no CKAN resource found for {year}; skipping")
            return []
        print(f"  Boston {year} → ckan resource {rid}")
        rows = ckan.fetch_resource(API_BASE, rid)
        return apply_field_map(rows, FIELD_MAP)

    def is_closed(self, df: pd.DataFrame) -> pd.Series:
        if "status" in df.columns:
            return df["status"].astype(str).str.strip().str.lower().eq("closed")
        return super().is_closed(df)
