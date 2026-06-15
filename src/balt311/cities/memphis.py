"""Memphis — Memphis Data Hub 311 Generated Service Requests (Socrata `5r9g-bwpp`)."""
from .socrata import SocrataAdapter


class MemphisAdapter(SocrataAdapter):
    city = "Memphis, TN"
    fips = "47157"          # Shelby County (fallback)
    place_fips = "4748000"  # city of Memphis (Memphis is ~2/3 of Shelby)
    portal_url = "https://data.memphistn.gov/Good-Government/311-Generated-Service-Requests/5r9g-bwpp"
    domain = "data.memphistn.gov"
    dataset_id = "5r9g-bwpp"
    closure_definition = (
        "Closed = a close timestamp present or terminal status. Non-ECC, geocoded. "
        "Field names auto-discovered; per-1k uses the Memphis place population."
    )
