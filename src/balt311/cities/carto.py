"""Reusable Carto SQL client for the cross-city comparison.

The Carto/CartoDB platform (Philadelphia's OpenDataPhilly, and others) exposes data through
a SQL API rather than ArcGIS FeatureServer queries. This mirrors `arcgis.py`: keyset
pagination on a sequential id column (Carto's `cartodb_id`), so large tables page reliably
regardless of depth, and the rest of the cross-city machinery is unchanged.
"""
import json
import time
import urllib.parse
import urllib.request

DEFAULT_PAGE_SIZE = 5000
FETCH_TIMEOUT = 120
DEFAULT_RETRIES = 6
_HEADERS = {"User-Agent": "Mozilla/5.0 (balt311-cross-city)"}


def fetch_sql(api_url: str, query: str, retries: int = DEFAULT_RETRIES) -> list[dict]:
    """Run one SQL statement against a Carto SQL API and return its rows, with retries."""
    url = f"{api_url}?{urllib.parse.urlencode({'q': query, 'format': 'json'})}"
    for attempt in range(1, retries + 1):
        try:
            req = urllib.request.Request(url, headers=_HEADERS)
            with urllib.request.urlopen(req, timeout=FETCH_TIMEOUT) as r:
                data = json.loads(r.read())
            if "rows" not in data:
                raise RuntimeError(str(data.get("error") or data)[:200])
            return data["rows"]
        except Exception as exc:
            if attempt == retries:
                raise
            wait = min(2 ** attempt, 30)
            print(f"  carto query attempt {attempt} failed ({exc}); retrying in {wait}s")
            time.sleep(wait)
    return []


def fetch_table_keyset(api_url: str, table: str, columns: list[str], where: str = "1=1",
                       id_col: str = "cartodb_id", page_size: int = DEFAULT_PAGE_SIZE) -> list[dict]:
    """All rows matching `where`, paged by `id_col > last` (indexed, cheap at any depth).
    The id column is added to the SELECT if absent so paging can track the last id; it is
    harmless downstream (adapters keep only mapped fields)."""
    cols = list(columns) + ([] if id_col in columns else [id_col])
    select = ", ".join(cols)
    records: list[dict] = []
    last_id = -1
    while True:
        query = (
            f"SELECT {select} FROM {table} "
            f"WHERE ({where}) AND {id_col} > {last_id} "
            f"ORDER BY {id_col} ASC LIMIT {page_size}"
        )
        rows = fetch_sql(api_url, query)
        if not rows:
            break
        records.extend(rows)
        last_id = max(int(r[id_col]) for r in rows)
        print(f"  carto {id_col}>{last_id}  +{len(rows):>5,}  total={len(records):>7,}")
        if len(rows) < page_size:
            break
    return records
