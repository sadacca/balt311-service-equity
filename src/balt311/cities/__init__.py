"""Per-city 311 adapters for the cross-city comparison (Phase 5).

Baltimore is one adapter among many; the within-Baltimore pipeline is untouched. New
cities register their adapter class in `ADAPTERS` and are then ingestible by
`scripts/peer_city.py` with no other changes.
"""
from .baltimore import BaltimoreAdapter
from .base import CityAdapter
from .dc import DCAdapter

# Registry keyed by the short slug used on the command line / in the workflow.
ADAPTERS: dict[str, type[CityAdapter]] = {
    "baltimore": BaltimoreAdapter,
    "dc": DCAdapter,
}

__all__ = ["CityAdapter", "BaltimoreAdapter", "DCAdapter", "ADAPTERS"]
