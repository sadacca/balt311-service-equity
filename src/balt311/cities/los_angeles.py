"""Los Angeles — MyLA311 Service Request Data (Socrata, one dataset per year).

LA publishes a separate dataset per calendar year and names columns without underscores
(`createddate` / `closeddate` / `requesttype`), so it sets both `datasets_by_year` and
explicit `field_overrides`."""
from .socrata import SocrataAdapter


class LosAngelesAdapter(SocrataAdapter):
    city = "Los Angeles, CA"
    fips = "06037"          # Los Angeles County (fallback — ~10M, vastly larger than the city)
    place_fips = "0644000"  # city of Los Angeles
    portal_url = "https://data.lacity.org/City-Infrastructure-Service-Requests/MyLA311-Service-Request-Data-2024/b7dx-7gc3"
    domain = "data.lacity.org"
    datasets_by_year = {2023: "4a4x-mna2", 2024: "b7dx-7gc3", 2025: "h73f-gn57"}
    field_overrides = {
        "CreatedDate": "createddate", "CloseDate": "closeddate",
        "SRType": "requesttype", "Latitude": "latitude",
        "Longitude": "longitude", "status": "status",
    }
    closure_definition = (
        "Closed = closeddate present or status 'Closed'. Non-ECC, geocoded. One Socrata dataset "
        "per year; per-1k uses the LA place population (LA County is ~2.5x the city)."
    )
