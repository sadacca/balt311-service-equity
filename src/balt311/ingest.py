import json
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed

# ArcGIS FeatureServer endpoints by year
ENDPOINTS: dict[int, str] = {
    2024: (
        "https://services1.arcgis.com/UWYHeuuJISiGmgXx/arcgis/rest/services"
        "/311_Customer_Service_Requests_2024/FeatureServer/0"
    ),
    2025: (
        "https://services1.arcgis.com/UWYHeuuJISiGmgXx/arcgis/rest/services"
        "/311_Customer_Service_Requests_2025/FeatureServer/0"
    ),
    2026: (
        "https://services1.arcgis.com/UWYHeuuJISiGmgXx/arcgis/rest/services"
        "/311_Customer_Service_Requests_2026/FeatureServer/0"
    ),
}

FIELDS = (
    "SRRecordID,ServiceRequestNum,SRType,MethodReceived,"
    "CreatedDate,SRStatus,StatusDate,DueDate,CloseDate,"
    "LastActivity,LastActivityDate,Outcome,"
    "Latitude,Longitude,Neighborhood,Agency"
)

DEFAULT_PAGE_SIZE = 2000
DEFAULT_WORKERS = 8


def _query_max_record_count(base_url: str) -> int:
    """Query the server's maxRecordCount to use the largest safe page size."""
    url = f"{base_url}?f=json"
    try:
        with urllib.request.urlopen(url, timeout=15) as r:
            info = json.loads(r.read())
        return int(info.get("maxRecordCount", DEFAULT_PAGE_SIZE))
    except Exception:
        return DEFAULT_PAGE_SIZE


def _query_total_count(base_url: str) -> int | None:
    """Return the server's reported total record count (used to pre-compute offsets)."""
    params = urllib.parse.urlencode({"where": "1=1", "returnCountOnly": "true", "f": "json"})
    url = f"{base_url}/query?{params}"
    try:
        with urllib.request.urlopen(url, timeout=15) as r:
            data = json.loads(r.read())
        return int(data.get("count", 0)) or None
    except Exception:
        return None


def fetch_page(
    base_url: str,
    offset: int,
    page_size: int = DEFAULT_PAGE_SIZE,
    retries: int = 4,
) -> list[dict]:
    params = urllib.parse.urlencode({
        "where": "1=1",
        "outFields": FIELDS,
        "resultOffset": offset,
        "resultRecordCount": page_size,
        "orderByFields": "CreatedDate DESC",
        "f": "json",
    })
    url = f"{base_url}/query?{params}"
    for attempt in range(1, retries + 1):
        try:
            with urllib.request.urlopen(url, timeout=30) as r:
                data = json.loads(r.read())
            return [f["attributes"] for f in data.get("features", [])]
        except Exception as exc:
            if attempt == retries:
                raise
            wait = 2 ** attempt
            print(f"  offset={offset} attempt {attempt} failed ({exc}); retrying in {wait}s")
            time.sleep(wait)
    return []  # unreachable; satisfies type checkers


def fetch_year(
    year: int,
    page_size: int | None = None,
    workers: int = DEFAULT_WORKERS,
) -> list[dict]:
    if year not in ENDPOINTS:
        raise ValueError(f"No endpoint configured for year {year}. Add it to ENDPOINTS.")
    base = ENDPOINTS[year]

    # Use the server's maxRecordCount if no explicit page size given
    if page_size is None:
        server_max = _query_max_record_count(base)
        page_size = min(server_max, 2000)  # cap at 2000 for safety
        print(f"  Server maxRecordCount={server_max}; using page_size={page_size}")

    # Pre-fetch total count so we can dispatch all pages up front
    total = _query_total_count(base)
    if total is not None:
        offsets = list(range(0, total + page_size, page_size))
        print(f"  Total records reported: {total:,} → {len(offsets)} pages (workers={workers})")
    else:
        offsets = None
        print(f"  Total count unavailable — will fall back to sequential fetch (workers={workers})")

    if offsets is not None:
        return _fetch_parallel(base, offsets, page_size, workers)
    else:
        return _fetch_sequential(base, page_size)


def _fetch_parallel(
    base_url: str,
    offsets: list[int],
    page_size: int,
    workers: int,
) -> list[dict]:
    """Fetch all pages concurrently; reassemble in offset order."""
    results: dict[int, list[dict]] = {}
    t0 = time.time()

    with ThreadPoolExecutor(max_workers=workers) as pool:
        future_to_offset = {
            pool.submit(fetch_page, base_url, off, page_size): off
            for off in offsets
        }
        for future in as_completed(future_to_offset):
            off = future_to_offset[future]
            page = future.result()  # propagates exceptions
            results[off] = page
            fetched = sum(len(v) for v in results.values())
            elapsed = time.time() - t0
            print(
                f"  offset={off:>7,}  page={len(page):>5,}  "
                f"total_so_far={fetched:>7,}  elapsed={elapsed:.0f}s"
            )

    # Reassemble in original offset order, drop empty trailing pages
    records: list[dict] = []
    for off in sorted(results):
        records.extend(results[off])
    return records


def _fetch_sequential(base_url: str, page_size: int) -> list[dict]:
    """Fallback sequential fetch when total count is unavailable."""
    records: list[dict] = []
    offset = 0
    while True:
        page = fetch_page(base_url, offset, page_size)
        records.extend(page)
        print(f"  offset={offset:>7,}  +{len(page):>5,}  total={len(records):>7,}")
        if len(page) < page_size:
            break
        offset += page_size
    return records
