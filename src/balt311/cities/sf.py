"""San Francisco — DataSF 311 Cases (Socrata `vw6y-z8j6`, since 2008; Open311 leader).

SF uses `lat`/`long` (not latitude/longitude) and `requested_datetime`/`closed_date`."""
from .socrata import SocrataAdapter


class SFAdapter(SocrataAdapter):
    city = "San Francisco, CA"
    fips = "06075"  # San Francisco County = city (exact denominator)
    portal_url = "https://data.sfgov.org/City-Infrastructure/311-Cases/vw6y-z8j6"
    domain = "data.sfgov.org"
    dataset_id = "vw6y-z8j6"
    closure_definition = (
        "Closed = closed_date present. Non-ECC, geocoded. Median days = closed_date − "
        "requested_datetime. County = city, so per-1k is exact."
    )
    field_overrides = {
        "CreatedDate": "requested_datetime", "CloseDate": "closed_date",
        "SRType": "service_name", "Latitude": "lat",
        "Longitude": "long", "status": "status_description",
    }
