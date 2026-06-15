"""Seattle — Seattle Open Data Customer Service Requests (Socrata `43nw-pkdq`, Find It Fix It)."""
from .socrata import SocrataAdapter


class SeattleAdapter(SocrataAdapter):
    city = "Seattle, WA"
    fips = "53033"          # King County (fallback — far larger than the city)
    place_fips = "5363000"  # city of Seattle
    portal_url = "https://data.seattle.gov/City-Administration/Customer-Service-Request-Tracking-Data/43nw-pkdq"
    domain = "data.seattle.gov"
    dataset_id = "43nw-pkdq"
    closure_definition = (
        "Closed = a close timestamp present or terminal status. Non-ECC, geocoded. Field names "
        "auto-discovered; per-1k uses the Seattle place population (King County is much larger)."
    )
