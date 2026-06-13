"""Reusable ArcGIS FeatureServer client for the cross-city comparison.

Generalizes the paginate-by-offset strategy `ingest.py` already uses for Baltimore,
parameterized by layer URL, out-fields, and order-by, so any ArcGIS-hosted city (DC,
and later others) reuses one robust client. Also discovers a city's per-year layer from
a FeatureServer root by name, since layer ids are not a clean offset of the year.
"""
import json
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed

DEFAULT_PAGE_SIZE = 2000
DEFAULT_WORKERS = 4
FETCH_TIMEOUT = 60
# Some ArcGIS hosts (DCGIS among them) reject urllib's default User-Agent.
_HEADERS = {"User-Agent": "Mozilla/5.0 (balt311-cross-city)"}


def _get_json(url: str, timeout: int = 30, retries: int = 4) -> dict:
    for attempt in range(1, retries + 1):
        try:
            req = urllib.request.Request(url, headers=_HEADERS)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read())
        except Exception:
            if attempt == retries:
                raise
            time.sleep(2 ** attempt)
    return {}


def list_layers(service_url: str) -> list[dict]:
    """`[{id, name}, ...]` for a FeatureServer/MapServer root."""
    return _get_json(f"{service_url}?f=json").get("layers", []) or []


def discover_year_layer(service_url: str, year: int) -> int:
    """Layer id whose name contains the 4-digit `year` (e.g. 'All Service Requests -
    2024'). Prefers the shortest matching name to avoid substring collisions. Raises if
    no layer matches, listing the available names for debugging."""
    layers = list_layers(service_url)
    matches = [lyr for lyr in layers if str(year) in str(lyr.get("name", ""))]
    if not matches:
        names = [lyr.get("name") for lyr in layers]
        raise ValueError(f"No layer for {year} in {service_url}. Available: {names}")
    matches.sort(key=lambda lyr: len(str(lyr.get("name", ""))))
    return int(matches[0]["id"])


def _max_record_count(layer_url: str) -> int:
    try:
        return int(_get_json(f"{layer_url}?f=json").get("maxRecordCount", DEFAULT_PAGE_SIZE))
    except Exception:
        return DEFAULT_PAGE_SIZE


def _total_count(layer_url: str) -> int | None:
    params = urllib.parse.urlencode({"where": "1=1", "returnCountOnly": "true", "f": "json"})
    try:
        return int(_get_json(f"{layer_url}/query?{params}", timeout=20).get("count", 0)) or None
    except Exception:
        return None


def _fetch_page(layer_url: str, out_fields: str, order_by: str, offset: int,
                page_size: int, retries: int = 4) -> list[dict]:
    params = {
        "where": "1=1", "outFields": out_fields, "resultOffset": offset,
        "resultRecordCount": page_size, "f": "json",
    }
    if order_by:
        params["orderByFields"] = order_by
    url = f"{layer_url}/query?{urllib.parse.urlencode(params)}"
    for attempt in range(1, retries + 1):
        try:
            req = urllib.request.Request(url, headers=_HEADERS)
            with urllib.request.urlopen(req, timeout=FETCH_TIMEOUT) as r:
                return [f["attributes"] for f in json.loads(r.read()).get("features", [])]
        except Exception as exc:
            if attempt == retries:
                raise
            wait = 2 ** attempt
            print(f"  offset={offset} attempt {attempt} failed ({exc}); retrying in {wait}s")
            time.sleep(wait)
    return []


def fetch_layer(layer_url: str, out_fields: str = "*", order_by: str = "",
                page_size: int | None = None, workers: int = DEFAULT_WORKERS) -> list[dict]:
    """All records from one FeatureServer layer. Pre-fetches the total count to dispatch
    pages concurrently (reassembled in order); falls back to sequential paging when the
    count is unavailable. A stable `order_by` is recommended for consistent offsets."""
    if page_size is None:
        page_size = min(_max_record_count(layer_url), 2000)
    total = _total_count(layer_url)

    if total is None:
        records, offset = [], 0
        while True:
            page = _fetch_page(layer_url, out_fields, order_by, offset, page_size)
            records.extend(page)
            print(f"  offset={offset:>7,}  +{len(page):>5,}  total={len(records):>7,}")
            if len(page) < page_size:
                break
            offset += page_size
        return records

    offsets = list(range(0, total + page_size, page_size))
    print(f"  Total reported: {total:,} → {len(offsets)} pages (workers={workers})")
    out: dict[int, list[dict]] = {}
    with ThreadPoolExecutor(max_workers=workers) as pool:
        fut = {pool.submit(_fetch_page, layer_url, out_fields, order_by, off, page_size): off
               for off in offsets}
        for future in as_completed(fut):
            out[fut[future]] = future.result()
    records = []
    for off in sorted(out):
        records.extend(out[off])
    return records
