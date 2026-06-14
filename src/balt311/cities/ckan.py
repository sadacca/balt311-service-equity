"""Reusable CKAN DataStore client for the cross-city comparison.

CKAN powers Analyze Boston (data.boston.gov) and other municipal portals. Unlike Socrata's
single dataset id, CKAN splits 311 into one *resource* (UUID) per year inside a *package*, so
the client first resolves the year's resource via `package_show`, then pages it with
`datastore_search` (limit/offset). Returns plain record dicts, like the Socrata/Carto clients.
"""
import json
import time
import urllib.parse
import urllib.request

PAGE_SIZE = 32000  # CKAN datastore_search default cap is 32k; page under it
TIMEOUT = 120
RETRIES = 6
_HEADERS = {"User-Agent": "Mozilla/5.0 (balt311-cross-city)", "Accept": "application/json"}


def _get(url: str) -> dict:
    for attempt in range(1, RETRIES + 1):
        try:
            req = urllib.request.Request(url, headers=_HEADERS)
            with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
                data = json.loads(r.read())
            if not data.get("success", False):
                raise RuntimeError(str(data.get("error"))[:200])
            return data["result"]
        except Exception as exc:
            if attempt == RETRIES:
                raise
            wait = min(2 ** attempt, 30)
            print(f"  ckan attempt {attempt} failed ({exc}); retrying in {wait}s")
            time.sleep(wait)
    return {}


def find_resource_for_year(api_base: str, package_id: str, year: int) -> str | None:
    """Resource id whose name contains the year (e.g. Boston's per-year 311 resources)."""
    result = _get(f"{api_base}/package_show?{urllib.parse.urlencode({'id': package_id})}")
    for res in result.get("resources", []):
        name = str(res.get("name", ""))
        if str(year) in name:
            return res.get("id")
    return None


def fetch_resource(api_base: str, resource_id: str, page_size: int = PAGE_SIZE) -> list[dict]:
    """All records in a DataStore resource, paged by limit/offset."""
    records: list[dict] = []
    offset = 0
    while True:
        params = {"resource_id": resource_id, "limit": page_size, "offset": offset}
        result = _get(f"{api_base}/datastore_search?{urllib.parse.urlencode(params)}")
        rows = result.get("records", [])
        if not rows:
            break
        records.extend(rows)
        print(f"  ckan {resource_id[:8]} offset={offset:>8,}  +{len(rows):>6,}  total={len(records):>8,}")
        if len(rows) < page_size:
            break
        offset += page_size
    return records
