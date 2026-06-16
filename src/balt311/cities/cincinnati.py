"""Cincinnati — Open Data Cincinnati 311 Non-Emergency Service Requests (Socrata `4cjh-bm8b`).

Open311-style schema (requested_datetime / closed_date / service_name), 2012-present, daily.

data.cincinnati-oh.gov is a Tyler Data & Insights portal. Its /resource/ SODA endpoint
requires portal-specific credentials and returns 403 anonymously. The /api/views/ rows
endpoint is publicly accessible and accepts the same SODA query parameters."""
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

    def _endpoint_url(self, dataset_id: str) -> str:
        # Tyler Data & Insights portals expose /api/views/{id}/rows.json publicly;
        # /resource/{id}.json on this portal returns 403 without portal-specific auth.
        return f"https://{self.domain}/api/views/{dataset_id}/rows.json"
