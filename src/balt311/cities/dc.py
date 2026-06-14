"""Washington, DC adapter — Open Data DC 311 City Service Requests.

ArcGIS FeatureServer with one layer per calendar year ("All Service Requests - YYYY" /
"311 City Service Requests in YYYY"). Layer ids are not a clean offset of the year
(2023=15, 2024=16, 2025=18), so the layer is discovered by name at fetch time. Reuses
the shared ArcGIS client almost verbatim — the cheap-integration city the MVP was built
around.
"""
from . import arcgis
from .base import CityAdapter, apply_field_map

# FeatureServer root holding the per-year layers.
SERVICE_URL = (
    "https://maps2.dcgis.dc.gov/dcgis/rest/services/DCGIS_DATA/ServiceRequests/FeatureServer"
)

# Raw DC column → Baltimore canonical name. DC dates are millisecond-epoch (ArcGIS).
FIELD_MAP = {
    "SERVICECODEDESCRIPTION": "SRType",
    "ADDDATE": "CreatedDate",
    "RESOLUTIONDATE": "CloseDate",
    "LATITUDE": "Latitude",
    "LONGITUDE": "Longitude",
}


class DCAdapter(CityAdapter):
    city = "Washington, DC"
    fips = "11001"
    portal_url = "https://opendata.dc.gov/"
    closure_definition = (
        "Closed = a resolution date (RESOLUTIONDATE) is present. DC auto-resolves some "
        "request types, so median days-to-close is directional, not exact."
    )

    def fetch(self, year: int) -> list[dict]:
        layer_id = arcgis.discover_year_layer(SERVICE_URL, year)
        layer_url = f"{SERVICE_URL}/{layer_id}"
        print(f"  DC {year} → layer {layer_id}")
        # Keyset (OID) paging — DC's ~440k-row layers time out on deep offset paging.
        raw = arcgis.fetch_layer_keyset(layer_url, out_fields=",".join(FIELD_MAP))
        return apply_field_map(raw, FIELD_MAP)
