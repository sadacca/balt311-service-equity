"""Reusable Socrata (SODA) client + base adapter for the cross-city comparison.

Socrata powers most large US 311 portals (NYC, Chicago, SF, Austin, Nashville, KC, …). SoQL
has no `median` aggregate, so we cannot compute the canonical pooled median server-side;
instead we pull **lean record-level** rows — only the ~6 mapped columns (`$select`), filtered
to the year (`$where`), offset-paged — which is the same record-level basis as the ArcGIS and
Carto cities and is what keeps the pooled median comparable across the cohort.

Robustness: 311 schemas vary in column naming across cities, and Socrata 403s anonymous schema
introspection from some clients, so each adapter declares candidate names per canonical field.
At fetch time (in CI, where the portals are reachable) the client probes one row to learn the
dataset's real columns, then resolves each canonical field to the first candidate that exists —
a slightly-off guess degrades that one field to null rather than 400-ing the whole pull.

`SOCRATA_APP_TOKEN` (env) is sent as `X-App-Token` when present, lifting anonymous throttling.
"""
import json
import os
import time
import urllib.parse
import urllib.request

from .base import CityAdapter, apply_field_map

PAGE_SIZE = 50000
TIMEOUT = 120
RETRIES = 6

# Ordered candidate raw column names per canonical field; first present one wins.
CANDIDATES: dict[str, list[str]] = {
    "CreatedDate": ["created_date", "requested_datetime", "creation_date", "open_date_time",
                    "date_time_opened", "open_dt", "opened_date", "sr_created_date"],
    "CloseDate": ["closed_date", "close_date", "closed_datetime", "resolved_date",
                  "date_time_closed", "closed_dt", "sr_closed_date"],
    "SRType": ["complaint_type", "sr_type", "service_name", "request_type", "issue_type",
               "issue_sub_type", "sr_type_desc", "category", "type", "case_title", "reason"],
    "Latitude": ["latitude", "lat", "y_coordinate"],
    "Longitude": ["longitude", "long", "x_coordinate"],
    "status": ["status", "status_description", "sr_status", "case_status", "current_status"],
}


def _headers() -> dict:
    h = {"User-Agent": "Mozilla/5.0 (balt311-cross-city)", "Accept": "application/json"}
    token = os.environ.get("SOCRATA_APP_TOKEN", "").strip()
    if token:
        h["X-App-Token"] = token
    return h


def _get(url: str) -> list[dict]:
    for attempt in range(1, RETRIES + 1):
        try:
            req = urllib.request.Request(url, headers=_headers())
            with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
                return json.loads(r.read())
        except Exception as exc:
            if attempt == RETRIES:
                raise
            wait = min(2 ** attempt, 30)
            print(f"  socrata attempt {attempt} failed ({exc}); retrying in {wait}s")
            time.sleep(wait)
    return []


def discover_columns(domain: str, dataset_id: str) -> list[str]:
    """Field names present in the dataset (probed from one record)."""
    rows = _get(f"https://{domain}/resource/{dataset_id}.json?$limit=1")
    return list(rows[0].keys()) if rows else []


def resolve_field_map(columns: list[str], overrides: dict[str, str] | None = None) -> dict[str, str]:
    """Build a raw→canonical map by picking, per canonical field, the first candidate that
    actually exists in `columns`. `overrides` (canonical→raw) take precedence when present."""
    cols = set(columns)
    overrides = overrides or {}
    field_map: dict[str, str] = {}
    for canon, cands in CANDIDATES.items():
        raw = overrides.get(canon)
        if raw and raw in cols:
            field_map[raw] = canon
            continue
        for cand in cands:
            if cand in cols:
                field_map[cand] = canon
                break
    return field_map


def fetch_rows(domain: str, dataset_id: str, select: list[str], where: str,
               order: str, page_size: int = PAGE_SIZE) -> list[dict]:
    """Offset-paged record pull. `order` must be a stable column (or `:id`) for deterministic paging."""
    base = f"https://{domain}/resource/{dataset_id}.json"
    records: list[dict] = []
    offset = 0
    while True:
        params = {
            "$select": ",".join(select),
            "$where": where,
            "$order": order,
            "$limit": page_size,
            "$offset": offset,
        }
        url = f"{base}?{urllib.parse.urlencode(params)}"
        rows = _get(url)
        if not rows:
            break
        records.extend(rows)
        print(f"  socrata {dataset_id} offset={offset:>8,}  +{len(rows):>6,}  total={len(records):>8,}")
        if len(rows) < page_size:
            break
        offset += page_size
    return records


class SocrataAdapter(CityAdapter):
    """Base for Socrata 311 cities. A concrete city sets `city`, `fips`, `domain`,
    `dataset_id`, `closure_definition`, and optionally `field_overrides` (canonical→raw)."""

    domain: str = ""
    dataset_id: str = ""
    field_overrides: dict[str, str] = {}

    def fetch(self, year: int) -> list[dict]:
        cols = discover_columns(self.domain, self.dataset_id)
        if not cols:
            print(f"  {self.city}: no columns discovered for {self.dataset_id}; skipping")
            return []
        field_map = resolve_field_map(cols, self.field_overrides)
        created = next((raw for raw, canon in field_map.items() if canon == "CreatedDate"), None)
        if not created:
            raise RuntimeError(f"{self.city}: no created-date column among {cols}")
        where = (f"{created} >= '{year}-01-01T00:00:00' "
                 f"AND {created} < '{year + 1}-01-01T00:00:00'")
        print(f"  {self.city} {year} → socrata {self.dataset_id} (created={created})")
        rows = fetch_rows(self.domain, self.dataset_id, select=list(field_map),
                          where=where, order=created)
        return apply_field_map(rows, field_map)

    def is_closed(self, df):
        # A Socrata request is closed iff it carries a close timestamp (the cohort-wide rule);
        # fall back to a status column only if no CloseDate was mapped.
        import pandas as pd
        if "CloseDate" in df.columns and df["CloseDate"].notna().any():
            return df["CloseDate"].notna()
        if "status" in df.columns:
            return df["status"].astype(str).str.strip().str.lower().eq("closed")
        return pd.Series(False, index=df.index)
