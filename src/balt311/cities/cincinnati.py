"""Cincinnati — Open Data Cincinnati 311 Non-Emergency Service Requests (Socrata `4cjh-bm8b`).

Open311-style schema (requested_datetime / closed_date / service_name), 2012-present, daily."""
from .socrata import SocrataAdapter


class CincinnatiAdapter(SocrataAdapter):
    city = "Cincinnati, OH"
    fips = "39061"          # Hamilton County (fallback)
    place_fips = "3915000"  # city of Cincinnati (Hamilton County is ~3x the city)
    portal_url = "https://data.cincinnati-oh.gov/thriving-neighborhoods/Cincinnati-311-Non-Emergency-Service-Requests/4cjh-bm8b"
    domain = "data.cincinnati-oh.gov"
    dataset_id = "4cjh-bm8b"
    closure_definition = (
        "Closed = closed_date present or terminal status. Non-ECC, geocoded. Open311-style "
        "schema; 2012-present; per-1k uses the Cincinnati place population."
    )
