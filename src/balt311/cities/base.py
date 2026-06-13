"""Per-city 311 adapter contract for the cross-city comparison (Phase 5).

Each adapter knows how to fetch one city's raw 311 records for a year and map them to
Baltimore's canonical field names, so the city-agnostic aggregator
(`peer_metrics.compute_city_metrics`) treats every city identically.

Canonical fields — Baltimore's own names, adopted as the shared vocabulary:
    SRType, CreatedDate, CloseDate, Latitude, Longitude
`CreatedDate` / `CloseDate` are millisecond-epoch integers (the ArcGIS convention);
`CloseDate` is null/absent for still-open requests. The uniform cross-city closure rule
is "a request is closed iff it has a CloseDate" — recorded per city in
`closure_definition` and footnoted in the tab, because native closure semantics differ.
"""

CANONICAL_FIELDS = ("SRType", "CreatedDate", "CloseDate", "Latitude", "Longitude")


class CityAdapter:
    """Base adapter. Subclasses set the metadata attributes and implement `fetch`."""

    city: str = ""               # display name, e.g. "Washington, DC"
    fips: str = ""               # 5-digit state+county FIPS, e.g. "11001"
    portal_url: str = ""
    closure_definition: str = ""  # how "closed" is determined for this city

    def fetch(self, year: int) -> list[dict]:
        """Return this city's records for `year`, already mapped to canonical fields."""
        raise NotImplementedError


def apply_field_map(raw: list[dict], field_map: dict[str, str]) -> list[dict]:
    """Rename raw column keys to canonical names, keeping only mapped fields."""
    return [{canon: r.get(src) for src, canon in field_map.items()} for r in raw]
