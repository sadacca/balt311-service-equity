"""Philadelphia adapter — OpenDataPhilly 311 service requests (Carto SQL API).

The first non-ArcGIS city, and the reason the adapter layer exists: it exercises the Carto
client and ISO-8601 timestamps (vs ArcGIS ms-epoch), proving the cross-city machinery
generalizes across data platforms. Table `public_cases_fc` holds one row per request;
`requested_datetime` / `closed_datetime` are ISO strings (`peer_metrics._parse_dt` handles
them), and closure is the `status` field ("Closed"). No ECC equivalent and no resident
channel, so the base scope (non-ECC, geocoded) applies as for DC.
"""
import pandas as pd

from . import carto
from .base import CityAdapter, apply_field_map

SQL_API = "https://phl.carto.com/api/v2/sql"
TABLE = "public_cases_fc"

# Raw Carto column → Baltimore canonical name. `status` is kept (not canonical) for is_closed.
FIELD_MAP = {
    "service_name": "SRType",
    "requested_datetime": "CreatedDate",
    "closed_datetime": "CloseDate",
    "lat": "Latitude",
    "lon": "Longitude",
    "status": "status",
}


class PhiladelphiaAdapter(CityAdapter):
    city = "Philadelphia, PA"
    fips = "42101"
    portal_url = "https://opendataphilly.org/"
    closure_definition = (
        "Closed = status is 'Closed'. Non-ECC, geocoded service requests; median days = "
        "closed_datetime − requested_datetime. Channel isn't published, so (like DC) no "
        "resident-only filter is applied."
    )

    def fetch(self, year: int) -> list[dict]:
        where = (
            f"requested_datetime >= '{year}-01-01' "
            f"AND requested_datetime < '{year + 1}-01-01'"
        )
        print(f"  Philadelphia {year} → carto {TABLE}")
        rows = carto.fetch_table_keyset(SQL_API, TABLE, list(FIELD_MAP), where=where)
        return apply_field_map(rows, FIELD_MAP)

    def is_closed(self, df: pd.DataFrame) -> pd.Series:
        if "status" in df.columns:
            return df["status"].astype(str).str.strip().str.lower().eq("closed")
        return super().is_closed(df)
