"""Kansas City — Open Data KC 311 Call Center Reported Issues (Socrata `d4px-6rwg`).

Current Salesforce-era system (2021+). KC spans several counties; Jackson is the primary
city-proxy denominator."""
from .socrata import SocrataAdapter


class KansasCityAdapter(SocrataAdapter):
    city = "Kansas City, MO"
    fips = "29095"  # Jackson County (primary; KC also spans Clay/Platte/Cass)
    portal_url = "https://data.kcmo.org/311/311-Call-Center-Reported-Issues/d4px-6rwg"
    domain = "data.kcmo.org"
    dataset_id = "d4px-6rwg"
    closure_definition = (
        "Closed = closed date present. Non-ECC, geocoded. Median days = closed_date − "
        "creation_date. 2021+ system; per-1k uses Jackson County (city-proxy)."
    )
    field_overrides = {
        "CreatedDate": "creation_date", "CloseDate": "closed_date",
        "SRType": "request_type", "Latitude": "latitude",
        "Longitude": "longitude", "status": "status",
    }
