"""Seattle — Seattle Open Data Customer Service Requests (Socrata `5ngg-rpne`, Find It Fix It).

Uses `5ngg-rpne` ("Customer Service Requests", 2013-present, ~714k rows, with created/closed/
lat/lon) — NOT `43nw-pkdq` ("...Tracking Data"), which is a status snapshot with only an
`updateddate` and no created/closed timestamp, so it can't support delivery metrics."""
from .socrata import SocrataAdapter


class SeattleAdapter(SocrataAdapter):
    city = "Seattle, WA"
    fips = "53033"          # King County (fallback — far larger than the city)
    place_fips = "5363000"  # city of Seattle
    portal_url = "https://data.seattle.gov/dataset/Customer-Service-Requests/5ngg-rpne"
    domain = "data.seattle.gov"
    dataset_id = "5ngg-rpne"
    closure_definition = (
        "Closed = a close timestamp present or terminal status. Non-ECC, geocoded. Field names "
        "auto-discovered; per-1k uses the Seattle place population (King County is much larger)."
    )
