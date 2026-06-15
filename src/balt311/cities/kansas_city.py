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
        "Closed = current_status 'resolved' (KC's terminal state — no 'closed' value) or a "
        "resolved_date present. Non-ECC, geocoded. Median days = resolved_date − open_date_time "
        "(KC populates resolved_date sparsely, so the median covers the timestamped subset). "
        "2021+ system; per-1k uses Jackson County (city-proxy)."
    )
    field_overrides = {
        "CreatedDate": "open_date_time", "CloseDate": "resolved_date",
        "SRType": "issue_type", "Latitude": "latitude",
        "Longitude": "longitude", "status": "current_status",
    }
