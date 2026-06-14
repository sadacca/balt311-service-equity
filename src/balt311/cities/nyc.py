"""New York City — NYC OpenData 311 (Socrata `erm2-nwe9`)."""
from .socrata import SocrataAdapter


class NYCAdapter(SocrataAdapter):
    city = "New York, NY"
    fips = "36005,36047,36061,36081,36085"  # Bronx, Kings, New York, Queens, Richmond
    portal_url = "https://data.cityofnewyork.us/Social-Services/311-Service-Requests-from-2020-to-Present/erm2-nwe9"
    domain = "data.cityofnewyork.us"
    dataset_id = "erm2-nwe9"
    closure_definition = (
        "Closed = closed_date present. Non-ECC, geocoded. Median days = closed_date − "
        "created_date. No resident-only filter (channel not modeled), as for DC."
    )
    field_overrides = {
        "CreatedDate": "created_date", "CloseDate": "closed_date",
        "SRType": "complaint_type", "Latitude": "latitude",
        "Longitude": "longitude", "status": "status",
    }
