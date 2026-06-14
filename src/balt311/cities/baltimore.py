"""Baltimore adapter — wraps the existing, proven `ingest.fetch_year` so Baltimore is
just one adapter among many in the cross-city comparison. The within-Baltimore pipeline
is untouched; this only re-exposes Baltimore's records under the adapter contract.

`ingest.fetch_year` returns the full raw record set (SRType, CreatedDate, CloseDate,
Latitude, Longitude, **plus SRStatus and MethodReceived**), so the adapter can reproduce
the within-Baltimore equity subset and SRStatus-based closure exactly — otherwise ECC
information-calls and system records would inflate volume ~2.5x and pull median
days-to-close to nearly zero (the bug that surfaced in the first MVP run).
"""
import pandas as pd

from balt311 import ingest
from balt311.metrics import RESIDENT_METHODS

from .base import CityAdapter

# Matches metrics.aggregate_tract — what the within-Baltimore tabs count as closed.
_CLOSED_STATUSES = {"closed", "closed (transferred)"}


class BaltimoreAdapter(CityAdapter):
    city = "Baltimore, MD"
    fips = "24510"
    portal_url = "https://data.baltimorecity.gov"
    closure_definition = (
        "Scope matches the within-Baltimore equity subset: resident-initiated "
        "(Phone/API/Mail/Email), non-ECC, geocoded. Closed = SRStatus is "
        "'Closed' / 'Closed (Transferred)'."
    )

    def fetch(self, year: int) -> list[dict]:
        return ingest.fetch_year(year)

    def scope(self, df: pd.DataFrame) -> pd.DataFrame:
        df = super().scope(df)  # non-ECC + geocoded
        if "MethodReceived" in df.columns:
            df = df[df["MethodReceived"].isin(RESIDENT_METHODS)]
        return df

    def is_closed(self, df: pd.DataFrame) -> pd.Series:
        return df["SRStatus"].astype(str).str.strip().str.lower().isin(_CLOSED_STATUSES)
