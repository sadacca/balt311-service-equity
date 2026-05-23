import json
import time
import urllib.parse
import urllib.request

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
}

FIELDS = (
    "SRRecordID,ServiceRequestNum,SRType,MethodReceived,"
    "CreatedDate,SRStatus,StatusDate,DueDate,CloseDate,"
    "LastActivity,LastActivityDate,Outcome,"
    "Latitude,Longitude,Neighborhood,Agency"
)


def fetch_page(
    base_url: str,
    offset: int,
    page_size: int = 2000,
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


def fetch_year(year: int, page_size: int = 2000) -> list[dict]:
    if year not in ENDPOINTS:
        raise ValueError(f"No endpoint configured for year {year}. Add it to ENDPOINTS.")
    base = ENDPOINTS[year]
    records: list[dict] = []
    offset = 0
    while True:
        page = fetch_page(base, offset, page_size)
        records.extend(page)
        print(f"  offset={offset:>7,}  +{len(page):>5,}  total={len(records):>7,}")
        if len(page) < page_size:
            break
        offset += page_size
        time.sleep(0.25)  # polite pause; slightly longer for CI stability
    return records
