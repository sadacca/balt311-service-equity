"""Nashville — hubNashville 311 Service Requests (Socrata `7qhx-rexh`).

Metro Nashville/Davidson is a consolidated city-county, so the ACS county denominator is
exact. Fields: `date_time_opened` / `date_time_closed` / `request_type`."""
from .socrata import SocrataAdapter


class NashvilleAdapter(SocrataAdapter):
    city = "Nashville, TN"
    fips = "47037"  # Davidson County = consolidated metro (exact denominator)
    portal_url = "https://data.nashville.gov/Public-Services/hubNashville-311-Service-Requests/7qhx-rexh"
    domain = "data.nashville.gov"
    dataset_id = "7qhx-rexh"
    closure_definition = (
        "Closed = date_time_closed present. Non-ECC, geocoded. Median days = date_time_closed "
        "− date_time_opened. Consolidated city-county, so per-1k is exact."
    )
    field_overrides = {
        "CreatedDate": "date_time_opened", "CloseDate": "date_time_closed",
        "SRType": "request_type", "Latitude": "latitude",
        "Longitude": "longitude", "status": "status",
    }
