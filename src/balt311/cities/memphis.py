"""Memphis — Memphis Data Hub 311 Generated Service Requests (Socrata `gvei-zwui`).

Open311-style schema (requested_datetime / closed_date / service_name), 2016-present, daily.
Dataset was previously at `5r9g-bwpp`; migrated to `gvei-zwui` (same domain, new view)."""
from .socrata import SocrataAdapter


class MemphisAdapter(SocrataAdapter):
    city = "Memphis, TN"
    fips = "47157"          # Shelby County (fallback)
    place_fips = "4748000"  # city of Memphis (Memphis is ~2/3 of Shelby)
    portal_url = "https://data.memphistn.gov/Good-Government/311-Generated-Service-Requests/gvei-zwui"
    domain = "data.memphistn.gov"
    dataset_id = "gvei-zwui"
    closure_definition = (
        "Closed = a close timestamp present or terminal status. Non-ECC, geocoded. "
        "Field names auto-discovered; per-1k uses the Memphis place population."
    )
