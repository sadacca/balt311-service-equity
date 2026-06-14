"""Nashville — hubNashville (311) Service Requests.

Nashville migrated its open-data portal off Socrata onto ArcGIS Hub, so (unlike the Socrata
cohort) its 311 lives in a single ArcGIS FeatureServer layer spanning 2017–present. The
adapter is configured only by the stable ArcGIS Hub **item id**: at fetch time it resolves the
hosted FeatureServer URL, discovers the layer's field names, maps the canonical fields against
case-insensitive candidates, and year-filters the one layer (ArcGIS dates are ms-epoch, which
`peer_metrics._parse_dt` already handles). Metro Nashville/Davidson is a consolidated
city-county, so the ACS county denominator is exact.
"""
from . import arcgis
from .base import CityAdapter, apply_field_map

# Stable ArcGIS Hub item for "hubNashville (311) Service Requests (2017 - Present)".
ITEM_ID = "9fe11d5a413240ed968f5c8d71877944"
LAYER = 0

# canonical → ordered candidate raw field names (matched case-insensitively to the layer).
CANDIDATES = {
    "CreatedDate": ["date_time_opened", "opened", "date_opened", "created_date", "request_date"],
    "CloseDate": ["date_time_closed", "closed", "date_closed", "closed_date"],
    "SRType": ["request_type", "subrequest_type", "type", "category"],
    "Latitude": ["latitude", "lat", "y"],
    "Longitude": ["longitude", "long", "x"],
    "status": ["status", "request_status", "current_status"],
}


def _resolve(field_names: list[str]) -> dict[str, str]:
    """Raw→canonical map, matching candidates case-insensitively to real field names."""
    by_lower = {f.lower(): f for f in field_names}
    field_map: dict[str, str] = {}
    for canon, cands in CANDIDATES.items():
        for cand in cands:
            if cand in by_lower:
                field_map[by_lower[cand]] = canon
                break
    return field_map


class NashvilleAdapter(CityAdapter):
    city = "Nashville, TN"
    fips = "47037"  # Davidson County = consolidated metro (exact denominator)
    portal_url = "https://data.nashville.gov/datasets/hubnashville-311-service-requests-2017-present"
    closure_definition = (
        "Closed = a close date is present. Non-ECC, geocoded. Median days = closed − opened. "
        "Single ArcGIS layer (2017+), year-filtered. Consolidated city-county, per-1k exact."
    )

    def fetch(self, year: int) -> list[dict]:
        layer_url = f"{arcgis.item_service_url(ITEM_ID)}/{LAYER}"
        field_map = _resolve(arcgis.layer_field_names(layer_url))
        created = next((raw for raw, canon in field_map.items() if canon == "CreatedDate"), None)
        if not created:
            raise RuntimeError(f"Nashville: no created-date field; layer has {list(field_map)}")
        print(f"  Nashville {year} → {layer_url} (created={created}, fields={field_map})")
        where = (f"{created} >= TIMESTAMP '{year}-01-01 00:00:00' "
                 f"AND {created} < TIMESTAMP '{year + 1}-01-01 00:00:00'")
        raw = arcgis.fetch_layer_keyset(layer_url, out_fields=",".join(field_map), where=where)
        return apply_field_map(raw, field_map)
