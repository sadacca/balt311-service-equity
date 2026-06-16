"""Dallas — Dallas OpenData 311 Service Request Based (Socrata `wwr9-8ha7`, Oct 2018-present).

Uses `wwr9-8ha7` (the full "311 Service Request Based" feed) — NOT `gc4d-8a49`, which returns
only ~7k rows/year (a small subset with no close-date field), nor `kc9e-h3nc` (a rolling
30-day boxcar)."""
from .socrata import SocrataAdapter


class DallasAdapter(SocrataAdapter):
    city = "Dallas, TX"
    fips = "48113"          # Dallas County (fallback)
    place_fips = "4819000"  # city of Dallas (spans several counties)
    portal_url = "https://www.dallasopendata.com/Services/311-Service-Request-Based/wwr9-8ha7"
    domain = "www.dallasopendata.com"
    dataset_id = "wwr9-8ha7"
    closure_definition = (
        "Closed = a close timestamp present or terminal status. Non-ECC, geocoded. Since Oct "
        "2018; field names auto-discovered; per-1k uses the Dallas place population."
    )
