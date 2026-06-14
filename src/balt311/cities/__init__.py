"""Per-city 311 adapters for the cross-city comparison (Phase 5).

Baltimore is one adapter among many; the within-Baltimore pipeline is untouched. New
cities register their adapter class in `ADAPTERS` and are then ingestible by
`scripts/peer_city.py` with no other changes.

Platforms covered: ArcGIS (Baltimore, DC), Carto (Philadelphia), Socrata (NYC, Chicago, SF,
Austin, Nashville, Kansas City), CKAN (Boston).
"""
from .austin import AustinAdapter
from .baltimore import BaltimoreAdapter
from .base import CityAdapter
from .boston import BostonAdapter
from .chicago import ChicagoAdapter
from .dc import DCAdapter
from .kansas_city import KansasCityAdapter
from .nashville import NashvilleAdapter
from .nyc import NYCAdapter
from .philadelphia import PhiladelphiaAdapter
from .sf import SFAdapter

# Registry keyed by the short slug used on the command line / in the workflow.
ADAPTERS: dict[str, type[CityAdapter]] = {
    "baltimore": BaltimoreAdapter,
    "dc": DCAdapter,
    "philadelphia": PhiladelphiaAdapter,
    "nyc": NYCAdapter,
    "chicago": ChicagoAdapter,
    "sf": SFAdapter,
    "austin": AustinAdapter,
    "nashville": NashvilleAdapter,
    "kansas_city": KansasCityAdapter,
    "boston": BostonAdapter,
}

__all__ = [
    "CityAdapter", "BaltimoreAdapter", "DCAdapter", "PhiladelphiaAdapter",
    "NYCAdapter", "ChicagoAdapter", "SFAdapter", "AustinAdapter",
    "NashvilleAdapter", "KansasCityAdapter", "BostonAdapter", "ADAPTERS",
]
