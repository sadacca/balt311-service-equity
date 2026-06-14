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
FETCH_TIMEOUT = 120
DEFAULT_RETRIES = 6
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


def _object_id_field(layer_url: str) -> str:
    """The layer's OID field name (usually OBJECTID) — the stable key for keyset paging."""
    try:
        return _get_json(f"{layer_url}?f=json").get("objectIdField") or "OBJECTID"
    except Exception:
        return "OBJECTID"


def _query_features(layer_url: str, params: dict, retries: int = DEFAULT_RETRIES) -> list[dict]:
    """Run one /query and return its feature attributes, retrying on transient errors.
    Geometry is never requested — we only need attribute fields, and dropping geometry
    sharply cuts payload size and the read timeouts that killed deep DC pages."""
    params = {"returnGeometry": "false", "f": "json", **params}
    url = f"{layer_url}/query?{urllib.parse.urlencode(params)}"
    for attempt in range(1, retries + 1):
        try:
            req = urllib.request.Request(url, headers=_HEADERS)
            with urllib.request.urlopen(req, timeout=FETCH_TIMEOUT) as r:
                data = json.loads(r.read())
            if data.get("error"):
                raise RuntimeError(str(data["error"])[:200])
            return [f["attributes"] for f in data.get("features", [])]
        except Exception as exc:
            if attempt == retries:
                raise
            wait = min(2 ** attempt, 30)
            print(f"  query attempt {attempt} failed ({exc}); retrying in {wait}s")
            time.sleep(wait)
    return []


def fetch_layer_keyset(layer_url: str, out_fields: str = "*",
                       page_size: int | None = None) -> list[dict]:
    """All records via keyset pagination on the OID field (where OID > last, ordered).

    Preferred over offset paging for large layers: ArcGIS re-scans on every `resultOffset`,
    so deep offsets get progressively slower and time out (DC, 440k rows). Keyset uses an
    indexed `OBJECTID > last` filter, so every page is cheap regardless of depth. Sequential
    by nature (each page needs the previous max id), but reliable. The OID is appended to
    `out_fields` if absent and is harmless downstream (adapters keep only mapped fields)."""
    if page_size is None:
        page_size = min(_max_record_count(layer_url), 2000)
    oid = _object_id_field(layer_url)
    fields = out_fields if (out_fields == "*" or oid in out_fields) else f"{out_fields},{oid}"

    records: list[dict] = []
    last_id = -1
    while True:
        page = _query_features(layer_url, {
            "where": f"{oid}>{last_id}", "outFields": fields,
            "orderByFields": f"{oid} ASC", "resultRecordCount": page_size,
        })
        if not page:
            break
        records.extend(page)
        last_id = max(int(r[oid]) for r in page)
        print(f"  keyset {oid}>{last_id - page_size}  +{len(page):>5,}  total={len(records):>7,}")
        if len(page) < page_size:
            break
    return records


def fetch_layer(layer_url: str, out_fields: str = "*", order_by: str = "",
                page_size: int | None = None, workers: int = DEFAULT_WORKERS) -> list[dict]:
    """All records via concurrent offset paging. Faster than keyset when it works, but
    degrades on very large layers (deep offsets); prefer `fetch_layer_keyset` there."""
    if page_size is None:
        page_size = min(_max_record_count(layer_url), 2000)
    total = _total_count(layer_url)

    def page_at(offset: int) -> list[dict]:
        params = {"where": "1=1", "outFields": out_fields,
                  "resultOffset": offset, "resultRecordCount": page_size}
        if order_by:
            params["orderByFields"] = order_by
        return _query_features(layer_url, params)

    if total is None:
        records, offset = [], 0
        while True:
            page = page_at(offset)
            records.extend(page)
            if len(page) < page_size:
                break
            offset += page_size
        return records

    offsets = list(range(0, total + page_size, page_size))
    print(f"  Total reported: {total:,} → {len(offsets)} pages (workers={workers})")
    out: dict[int, list[dict]] = {}
    with ThreadPoolExecutor(max_workers=workers) as pool:
        fut = {pool.submit(page_at, off): off for off in offsets}
        for future in as_completed(fut):
            out[fut[future]] = future.result()
    records = []
    for off in sorted(out):
        records.extend(out[off])
    return records
