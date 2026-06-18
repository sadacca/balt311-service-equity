"""Memphis — 311 Service Requests (OPM), ArcGIS FeatureServer.

Memphis's Socrata open-data portal (data.memphistn.gov) was retired — every dataset id on
that domain now redirects to hub.arcgis.com/legacy regardless of the id requested. The
City's Office of Performance Management publishes the live 311 feed directly as an ArcGIS
FeatureServer instead (no Socrata-style dataset migration page, no item id to resolve).
Single layer, all years; same case-insensitive auto-discovery pattern as Nashville so a
field-name guess that's slightly off degrades to a clear "no created-date field; layer has
[...]" error rather than a silent wrong mapping.
"""
from . import arcgis
from .base import CityAdapter, apply_field_map

SERVICE_URL = "https://maps.memphistn.gov/mapping/rest/services/OPM/COM_311_REQUESTS_OPM/FeatureServer"
LAYER = 0

# canonical → ordered candidate raw field names (matched case-insensitively to the layer).
CANDIDATES = {
    "CreatedDate": ["createdate", "created_date", "requestdate", "request_date", "datetimeinit",
                    "date_time_opened", "opendate", "open_date", "dateopened", "date_opened",
                    "submitdate", "submit_date"],
    "CloseDate": ["closedate", "close_date", "resolveddate", "resolved_date", "datetimeclosed",
                  "date_time_closed", "completeddate", "completed_date", "dateclosed",
                  "date_closed"],
    "SRType": ["requesttype", "request_type", "servicename", "service_name", "category",
               "type", "issuetype", "issue_type", "problemtype", "problem_type"],
    "Latitude": ["latitude", "lat", "y"],
    "Longitude": ["longitude", "long", "lon", "x"],
    "status": ["status", "requeststatus", "request_status", "currentstatus", "current_status"],
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


class MemphisAdapter(CityAdapter):
    city = "Memphis, TN"
    fips = "47157"          # Shelby County (fallback)
    place_fips = "4748000"  # city of Memphis (Memphis is ~2/3 of Shelby)
    portal_url = "https://maps.memphistn.gov/mapping/rest/services/OPM/COM_311_REQUESTS_OPM/FeatureServer"
    closure_definition = (
        "Closed = a close/resolved timestamp is present or a terminal status. Non-ECC, "
        "geocoded. Field names auto-discovered; per-1k uses the Memphis place population. "
        "Migrated from the retired Socrata portal to this ArcGIS FeatureServer."
    )

    def fetch(self, year: int) -> list[dict]:
        layer_url = f"{SERVICE_URL}/{LAYER}"
        field_map = _resolve(arcgis.layer_field_names(layer_url))
        created = next((raw for raw, canon in field_map.items() if canon == "CreatedDate"), None)
        if not created:
            raise RuntimeError(f"Memphis: no created-date field; layer has {list(field_map)}")
        print(f"  Memphis {year} → {layer_url} (created={created}, fields={field_map})")
        where = (f"{created} >= TIMESTAMP '{year}-01-01 00:00:00' "
                 f"AND {created} < TIMESTAMP '{year + 1}-01-01 00:00:00'")
        raw = arcgis.fetch_layer_keyset(layer_url, out_fields=",".join(field_map), where=where)
        return apply_field_map(raw, field_map)

    def schema_fields(self, year: int) -> list[str] | None:
        return arcgis.layer_field_names(f"{SERVICE_URL}/{LAYER}")
