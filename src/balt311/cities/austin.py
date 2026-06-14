"""Austin — City of Austin 311 Public Data (Socrata `xwdj-i9he`, since 2014)."""
from .socrata import SocrataAdapter


class AustinAdapter(SocrataAdapter):
    city = "Austin, TX"
    fips = "48453"  # Travis County (city-proxy denominator)
    portal_url = "https://data.austintexas.gov/Utilities-and-City-Services/Austin-311-Public-Data/xwdj-i9he"
    domain = "data.austintexas.gov"
    dataset_id = "xwdj-i9he"
    closure_definition = (
        "Closed = close date present. Non-ECC, geocoded. Median days = close_date − "
        "created_date. Per-1k uses Travis County population."
    )
    field_overrides = {
        "CreatedDate": "created_date", "CloseDate": "close_date",
        "SRType": "sr_type_desc", "Latitude": "latitude",
        "Longitude": "longitude", "status": "sr_status",
    }
