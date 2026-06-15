"""Dallas — Dallas OpenData 311 Service Requests (Socrata `gc4d-8a49`, since Oct 2018)."""
from .socrata import SocrataAdapter


class DallasAdapter(SocrataAdapter):
    city = "Dallas, TX"
    fips = "48113"          # Dallas County (fallback)
    place_fips = "4819000"  # city of Dallas (spans several counties)
    portal_url = "https://www.dallasopendata.com/Services/311-Service-Requests/gc4d-8a49"
    domain = "www.dallasopendata.com"
    dataset_id = "gc4d-8a49"
    closure_definition = (
        "Closed = a close timestamp present or terminal status. Non-ECC, geocoded. Since Oct "
        "2018; field names auto-discovered; per-1k uses the Dallas place population."
    )
