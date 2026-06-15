"""Chicago — Chicago Data Portal 311 (Socrata `v6vf-nfxy`, unified system since 2018)."""
from .socrata import SocrataAdapter


class ChicagoAdapter(SocrataAdapter):
    city = "Chicago, IL"
    fips = "17031"          # Cook County (fallback)
    place_fips = "1714000"  # city of Chicago — Cook County is ~2× the city, so use the place
    portal_url = "https://data.cityofchicago.org/Service-Requests/311-Service-Requests/v6vf-nfxy"
    domain = "data.cityofchicago.org"
    dataset_id = "v6vf-nfxy"
    closure_definition = (
        "Closed = closed_date present. Non-ECC, geocoded. Median days = closed_date − "
        "created_date. Unified 311 dataset (2018+); per-1k uses Cook County population."
    )
    field_overrides = {
        "CreatedDate": "created_date", "CloseDate": "closed_date",
        "SRType": "sr_type", "Latitude": "latitude",
        "Longitude": "longitude", "status": "status",
    }
