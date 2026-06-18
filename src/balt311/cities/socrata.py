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
import base64
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request

from .base import CityAdapter, apply_field_map

PAGE_SIZE = 50000
TIMEOUT = 120
RETRIES = 6

# Terminal/"closed" status values across the Socrata cohort — they don't agree on the word:
# NYC/SF say "Closed", Chicago "Completed", Kansas City "Resolved". Matched case-insensitively.
CLOSED_STATES = {"closed", "resolved", "completed", "done", "closed - resolved"}

# Ordered candidate raw column names per canonical field; first present one wins. Broad enough
# that most municipal Socrata 311 schemas resolve without per-city overrides; a slug that names
# its columns oddly (LA's no-underscore "createddate") sets `field_overrides`.
CANDIDATES: dict[str, list[str]] = {
    "CreatedDate": ["created_date", "requested_datetime", "creation_date", "open_date_time",
                    "date_time_opened", "open_dt", "opened_date", "sr_created_date",
                    "createddate", "created_dt", "requested_date", "received_date",
                    "date_received", "date_created"],
    "CloseDate": ["closed_date", "close_date", "closed_datetime", "resolved_date",
                  "date_time_closed", "closed_dt", "sr_closed_date", "closeddate",
                  "resolution_date", "completion_date", "date_closed", "date_completed"],
    "SRType": ["complaint_type", "sr_type", "service_name", "request_type", "issue_type",
               "issue_sub_type", "sr_type_desc", "parent_incident_type", "service_request_type",
               "requesttype", "category", "type", "case_title", "reason"],
    "Latitude": ["latitude", "lat", "y_coordinate"],
    "Longitude": ["longitude", "long", "x_coordinate"],
    "status": ["status", "status_description", "sr_status", "case_status", "current_status",
               "request_status", "service_request_status"],
}


_BASE_HEADERS = {"User-Agent": "Mozilla/5.0 (balt311-cross-city)", "Accept": "application/json"}


def _auth_candidates() -> list[tuple[str, dict, str]]:
    """Ordered (label, headers, query_token) auth strategies, strongest first: full API key
    pair (Basic auth + X-App-Token), then a bare app token (key id alone or
    SOCRATA_APP_TOKEN), then anonymous. A misconfigured/revoked key pair 403s some Socrata
    portals outright (observed: every cohort city 403ing the moment SOCRATA_KEY_ID/SECRET were
    set, after succeeding anonymously before) — `_get` falls back down this list on a 403
    rather than trusting credentials it can't verify itself."""
    key_id = os.environ.get("SOCRATA_KEY_ID", "").strip()
    key_secret = os.environ.get("SOCRATA_KEY_SECRET", "").strip()
    token = os.environ.get("SOCRATA_APP_TOKEN", "").strip()

    candidates: list[tuple[str, dict, str]] = []
    if key_id and key_secret:
        creds = base64.b64encode(f"{key_id}:{key_secret}".encode()).decode()
        candidates.append(
            ("API key pair", {"Authorization": f"Basic {creds}", "X-App-Token": key_id}, key_id)
        )
    bare_token = token or key_id
    if bare_token:
        candidates.append(("app token", {"X-App-Token": bare_token}, bare_token))
    candidates.append(("anonymous", {}, ""))
    return candidates


def _with_query_token(url: str, query_token: str) -> str:
    """Append $$app_token as a query param — survives redirects that strip headers."""
    if not query_token:
        return url
    sep = "&" if "?" in url else "?"
    return f"{url}{sep}$$app_token={urllib.parse.quote(query_token, safe='')}"


def _request_once(url: str, headers: dict) -> list[dict]:
    """Single GET, raising on failure (HTTPError / RuntimeError / other) — no retry."""
    req = urllib.request.Request(url, headers={**_BASE_HEADERS, **headers})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        final_url = r.geturl()
        body = r.read()
    if not body or not body.strip():
        raise RuntimeError("empty response body — likely needs auth or the dataset id is wrong")
    try:
        return json.loads(body)
    except json.JSONDecodeError:
        preview = body[:120].decode("utf-8", errors="replace").strip()
        raise RuntimeError(
            f"non-JSON response (HTML/redirect?) requested: {url!r}; landed: {final_url!r}. "
            f"Preview: {preview!r}"
        )


def _get(url: str) -> list[dict]:
    candidates = _auth_candidates()
    last_exc: Exception | None = None
    for i, (label, headers, query_token) in enumerate(candidates):
        req_url = _with_query_token(url, query_token)
        weaker = candidates[i + 1][0] if i + 1 < len(candidates) else None
        for attempt in range(1, RETRIES + 1):
            try:
                return _request_once(req_url, headers)
            except urllib.error.HTTPError as exc:
                body = exc.read()
                if exc.code == 403:
                    # Bad/rejected credentials at this level — retrying with the same auth
                    # is pointless; drop straight to the next weaker strategy.
                    last_exc = exc
                    msg = f"  socrata 403 with {label} auth"
                    print(f"{msg} — falling back to {weaker}" if weaker else f"{msg}; no weaker auth left")
                    break
                if b"must be logged in" in body.lower() or b"\"error\":true" in body.lower():
                    # Dataset requires an authenticated browser session — no token/key pair
                    # satisfies this headlessly, but still let a weaker level get one try.
                    last_exc = RuntimeError(
                        f"HTTP {exc.code}: dataset requires a logged-in user session, not just "
                        f"an app token/API key — not fetchable headlessly. Body: "
                        f"{body[:200].decode('utf-8', errors='replace')!r}"
                    )
                    break
                last_exc = exc
                if attempt == RETRIES:
                    break
                wait = min(2 ** attempt, 30)
                print(f"  socrata attempt {attempt} failed (HTTP {exc.code}); retrying in {wait}s")
                time.sleep(wait)
            except Exception as exc:
                last_exc = exc
                if attempt == RETRIES:
                    break
                wait = min(2 ** attempt, 30)
                print(f"  socrata attempt {attempt} failed ({exc}); retrying in {wait}s")
                time.sleep(wait)
        # Exhausted (or 403'd out of) this auth level — fall through to the next, weaker one.
    if last_exc:
        raise last_exc
    return []


def discover_columns(domain: str, dataset_id: str, base_url: str | None = None) -> list[str]:
    """Field names present in the dataset (probed from one record)."""
    url = base_url or f"https://{domain}/resource/{dataset_id}.json"
    rows = _get(f"{url}?$limit=1")
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
               order: str, page_size: int = PAGE_SIZE, base_url: str | None = None) -> list[dict]:
    """Offset-paged record pull. `order` must be a stable column (or `:id`) for deterministic paging."""
    base = base_url or f"https://{domain}/resource/{dataset_id}.json"
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
    datasets_by_year: dict[int, str] = {}  # for cities that publish one dataset per year (LA)
    field_overrides: dict[str, str] = {}

    def _dataset_for(self, year: int) -> str:
        return self.datasets_by_year.get(year, self.dataset_id)

    def _endpoint_url(self, dataset_id: str) -> str:
        """Base URL for SODA queries. Override for portals that don't serve /resource/."""
        return f"https://{self.domain}/resource/{dataset_id}.json"

    def fetch(self, year: int) -> list[dict]:
        dataset_id = self._dataset_for(year)
        if not dataset_id:
            print(f"  {self.city}: no dataset for {year}; skipping")
            return []
        base_url = self._endpoint_url(dataset_id)
        cols = discover_columns(self.domain, dataset_id, base_url=base_url)
        if not cols:
            print(f"  {self.city}: no columns discovered for {dataset_id}; skipping")
            return []
        field_map = resolve_field_map(cols, self.field_overrides)
        created = next((raw for raw, canon in field_map.items() if canon == "CreatedDate"), None)
        if not created:
            raise RuntimeError(f"{self.city}: no created-date column among {cols}")
        where = (f"{created} >= '{year}-01-01T00:00:00' "
                 f"AND {created} < '{year + 1}-01-01T00:00:00'")
        print(f"  {self.city} {year} → socrata {dataset_id} (created={created})")
        rows = fetch_rows(self.domain, dataset_id, select=list(field_map),
                          where=where, order=created, base_url=base_url)
        return apply_field_map(rows, field_map)

    def is_closed(self, df):
        # Closed if it carries a close timestamp OR a terminal status — combined, because some
        # systems don't reliably populate a close date for resolved records (Kansas City leaves
        # `resolved_date` empty yet marks `current_status` = "resolved"), which otherwise
        # collapses the closure rate to 0. `_closed` is the parsed CloseDate (compute adds it
        # before calling this).
        import pandas as pd
        closed = pd.Series(False, index=df.index)
        if "_closed" in df.columns:
            closed = closed | df["_closed"].notna()
        elif "CloseDate" in df.columns:
            closed = closed | df["CloseDate"].notna()
        if "status" in df.columns:
            closed = closed | df["status"].astype(str).str.strip().str.lower().isin(CLOSED_STATES)
        return closed

    def schema_fields(self, year: int) -> list[str] | None:
        dataset_id = self._dataset_for(year)
        if not dataset_id:
            return None
        return discover_columns(self.domain, dataset_id, base_url=self._endpoint_url(dataset_id))
