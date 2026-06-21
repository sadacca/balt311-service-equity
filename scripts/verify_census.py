"""Re-verify the 311 open-data coverage census by probing each city's live API.

The maturity census (`data/processed/peer_city_coverage_census.csv`) records, per city, a
`status` (scoreable / partial / unconfirmed) and an `evidence` tier describing HOW it was
verified — `api` (we hit the live dataset endpoint, the strongest), `city_docs` (the city's
own portal page), `third_party` (an aggregator / news), or `none`. This script makes the
`api` tier reproducible and re-runnable down the chain (Claude → GitHub Actions → a local
machine): for every row that carries an `endpoint` URL it fetches one record and reports
which of the analysis-critical fields — a created timestamp, a closed timestamp, and
geocoordinates — are actually present.

Run:
    python scripts/verify_census.py                 # probe every endpoint, print a report
    python scripts/verify_census.py --strict        # exit 1 if any api-tier endpoint regressed
    python scripts/verify_census.py --write          # refresh the `api_checked` / `api_fields` columns

It deliberately uses only the stdlib so it runs anywhere (CI, a bare container, a laptop)
with no install step.
"""
import argparse
import csv
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

CENSUS = Path(__file__).resolve().parents[1] / "data" / "processed" / "peer_city_coverage_census.csv"
# A generic urllib UA gets a flat 403 from several ArcGIS Hub / Open Data domains (Charlotte,
# Indianapolis, Denver, Detroit, Atlanta) that otherwise serve the same .geojson proxy fine to a
# browser — they're doing basic UA sniffing, not real bot defense, so a realistic browser UA
# string is enough to get through.
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )
}
TIMEOUT = 45
# Sampling more than one row and unioning field keys avoids false "missing field" negatives on
# Socrata/CKAN, whose JSON omits a key entirely (rather than emitting it as null) when that row's
# value for it is empty — a single-row probe can easily land on a row where e.g. closed_date is
# null even though the field exists and is usually populated.
_PROBE_LIMIT = 20
_SOCRATA_TOKEN = os.environ.get("SOCRATA_APP_TOKEN", "").strip()

# Heuristic field-name matchers — open-311 schemas vary in naming across platforms. Grounded in
# the actual CANDIDATES/field_overrides lists the production adapters (socrata.py, memphis.py,
# nashville.py, dc.py, ...) already match against live data, not guesswork: a live CI run found
# real schemas this missed — "open_date_time" (Kansas City), "requestdate" (Memphis) — neither
# "opened" nor "requested" catches them since the words aren't contiguous substrings.
_CREATED = ("created", "requested", "opened", "open_dt", "open_date", "start", "intake", "init",
            "receiv", "requestdate", "request_date", "submit", "creation", "adddate")
_CLOSED = ("closed", "resolved", "completed", "close_dt", "closeddate", "resolution_dt",
           "resolution", "completion")
_GEO = ("lat", "lon", "latitude", "longitude", "the_geom", "geom", "point", "shape", "x_coord", "y_coord")
# Depth signals for the maturity rubric's field-completeness dimension (P5.9-4).
_CHANNEL = ("channel", "source", "method_received", "report_source", "intake", "requestsource")
_AGENCY = ("agency", "department", "owner", "work_group", "dept", "bureau", "responsible")


# Socrata dataset pages end in a 4-4 alphanumeric resource id (e.g. .../erm2-nwe9) — the
# census records the human-facing landing page, but the SODA API lives at /resource/{id}.json.
_SOCRATA_ID = re.compile(r"([a-z0-9]{4}-[a-z0-9]{4})/?$", re.IGNORECASE)
# CKAN dataset pages: /dataset/<slug> (singular) — package_show resolves the slug to a package.
_CKAN_DATASET = re.compile(r"/dataset/([^/]+)/?$")
# ArcGIS Hub/Open Data dataset pages: /datasets/<owner::slug> (plural) — Hub serves a
# `<page>.geojson` download proxy that resolves the friendly slug to its FeatureServer query
# without needing the item id, so no separate Hub Search API call is required.
_HUB_DATASET = re.compile(r"^(.*/datasets/[^/]+)")


def _socrata_resource_url(netloc: str, dataset_id: str) -> str:
    url = f"https://{netloc}/resource/{dataset_id}.json?$limit={_PROBE_LIMIT}"
    if _SOCRATA_TOKEN:
        url += f"&$$app_token={urllib.parse.quote(_SOCRATA_TOKEN, safe='')}"
    return url


def _to_api_url(url: str) -> str:
    """Best-effort rewrite of a recorded (often human-facing) endpoint into a callable JSON
    API URL. Handles the platforms this census can detect from the URL shape alone — Socrata
    dataset pages — mirroring the request construction `cities/socrata.py` already uses for the
    live cohort. ArcGIS FeatureServer/MapServer/Hub and CKAN pages need a multi-step lookup and
    are handled separately in `_first_record_fields`. Generic portal homepages with no
    dataset-specific path are returned unchanged — there's nothing in the URL to rewrite.
    """
    parsed = urllib.parse.urlsplit(url)
    m = _SOCRATA_ID.search(parsed.path)
    if m:
        return _socrata_resource_url(parsed.netloc, m.group(1))
    return url


def _arcgis_rest_fields(url: str) -> tuple[list[str], bool] | None:
    """`None` if `url` isn't a plain ArcGIS REST FeatureServer/MapServer URL (the Hub/Open Data
    proxy is handled separately by `_arcgis_hub_fields`); otherwise `(fields, geo_hint)` from an
    actual `/query` against the first layer — mirroring `cities/arcgis.py`'s live request shape.
    A bare `?f=json` on the service root or a numbered layer only returns *metadata* (the layer's
    schema / the service's layer list), never a `features` array, so it can never see real
    geometry — that under-reported `geo` as missing for every plain-REST city (e.g. Memphis)
    even though the live data is fully geocoded."""
    if "FeatureServer" not in url and "MapServer" not in url:
        return None
    layer_url = re.sub(r"\?.*$", "", url.rstrip("/"))
    if not re.search(r"/\d+$", layer_url):
        meta = _fetch_json(f"{layer_url}?f=json")
        layers = meta.get("layers") or []
        if not layers:
            raise RuntimeError("ArcGIS service root has no layers")
        layer_url = f"{layer_url}/{layers[0].get('id', 0)}"
    query_url = f"{layer_url}/query?where=1%3D1&outFields=*&resultRecordCount={_PROBE_LIMIT}&f=json"
    data = _fetch_json(query_url)
    feats = (data.get("features") or [])[:_PROBE_LIMIT]
    if not feats:
        raise RuntimeError("no features in arcgis query response")
    keys: dict[str, None] = {}
    for feat in feats:
        keys.update(dict.fromkeys((feat.get("attributes") or {}).keys()))
    geo_hint = any(feat.get("geometry") for feat in feats)
    return list(keys), geo_hint


def _socrata_views_fields(netloc: str, dataset_id: str) -> list[str]:
    """Some Socrata-branded portals (Tyler Data & Insights, e.g. Cincinnati's
    data.cincinnati-oh.gov) 403 the standard SODA `/resource/{id}.json` endpoint without
    portal-specific credentials but leave the older `/api/views/{id}/rows.json` endpoint public
    — see `cities/cincinnati.py`'s adapter override, which already relies on this fallback in
    production. Its payload shape is `{"meta": {"view": {"columns": [...]}}, "data": [[...]]}`
    (positional rows), so field names come from the column metadata, not the row values."""
    data = _fetch_json(f"https://{netloc}/api/views/{dataset_id}/rows.json?$limit={_PROBE_LIMIT}")
    columns = (data.get("meta") or {}).get("view", {}).get("columns", [])
    return [c.get("fieldName") or c.get("name") or "" for c in columns]


def _ckan_fields(url: str) -> list[str] | None:
    """`None` if `url` isn't a CKAN dataset page; otherwise the union of field names across
    several rows of its first DataStore-active resource (package_show → datastore_search),
    mirroring `cities/ckan.py`. Unioning rows (rather than trusting one) avoids a false
    "missing field" negative when that field happens to be null/absent on the sampled row."""
    parsed = urllib.parse.urlsplit(url)
    m = _CKAN_DATASET.search(parsed.path)
    if not m:
        return None
    slug = m.group(1)
    api_base = f"https://{parsed.netloc}/api/3/action"
    pkg = _fetch_json(f"{api_base}/package_show?{urllib.parse.urlencode({'id': slug})}")
    if not pkg.get("success"):
        raise RuntimeError(f"ckan package_show failed: {str(pkg.get('error'))[:100]}")
    last_exc: Exception | None = None
    for res in pkg.get("result", {}).get("resources", []):
        rid = res.get("id")
        if not rid:
            continue
        try:
            ds = _fetch_json(
                f"{api_base}/datastore_search?"
                f"{urllib.parse.urlencode({'resource_id': rid, 'limit': _PROBE_LIMIT})}"
            )
        except Exception as exc:
            last_exc = exc
            continue
        if not ds.get("success"):
            continue
        records = ds.get("result", {}).get("records", [])
        if records:
            keys: dict[str, None] = {}
            for rec in records:
                keys.update(dict.fromkeys(rec.keys()))
            return list(keys)
        fields = ds.get("result", {}).get("fields", [])
        if fields:
            return [f["id"] for f in fields if f.get("id") != "_id"]
    if last_exc:
        raise last_exc
    raise RuntimeError("no DataStore-active resource found in package")


def _arcgis_hub_fields(url: str) -> tuple[list[str], bool] | None:
    """`None` if `url` isn't an ArcGIS Hub/Open Data dataset page; otherwise `(fields, geo_hint)`
    — property names (unioned across several features) from the dataset's `.geojson` download
    proxy (no item-id lookup needed — Hub resolves the friendly `Owner::slug` page URL itself),
    plus whether any sampled feature actually carries a structural `geometry` object. GeoJSON
    stores coordinates as a top-level `geometry` key, never as a named property, so a
    property-name geo check alone would always read as "no geo" even for fully geocoded data."""
    m = _HUB_DATASET.search(url)
    if not m:
        return None
    geo_url = m.group(1) + ".geojson"
    data = _fetch_json(geo_url)
    feats = (data.get("features") or [])[:_PROBE_LIMIT]
    if not feats:
        raise RuntimeError("no features in hub .geojson export")
    keys: dict[str, None] = {}
    for feat in feats:
        keys.update(dict.fromkeys((feat.get("properties") or {}).keys()))
    geo_hint = any(feat.get("geometry") for feat in feats)
    return list(keys), geo_hint


def _fetch_json(url: str):
    req = urllib.request.Request(url, headers=_HEADERS)
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return json.loads(r.read())


def _first_record_fields(endpoint: str) -> tuple[list[str], bool]:
    """Fetch records from a Socrata / ArcGIS / Carto / CKAN / ArcGIS Hub endpoint and return
    `(field_names, geo_hint)` — `geo_hint` is True when the response structurally carries
    coordinates (ArcGIS `geometry`/`x`/`y`) even if no field is *named* like a coordinate."""
    ckan = _ckan_fields(endpoint)
    if ckan is not None:
        return ckan, False
    hub = _arcgis_hub_fields(endpoint)
    if hub is not None:
        return hub
    arcgis_rest = _arcgis_rest_fields(endpoint)
    if arcgis_rest is not None:
        return arcgis_rest
    parsed = urllib.parse.urlsplit(endpoint)
    socrata_id = _SOCRATA_ID.search(parsed.path)
    if socrata_id:
        try:
            data = _fetch_json(_socrata_resource_url(parsed.netloc, socrata_id.group(1)))
        except urllib.error.HTTPError as exc:
            if exc.code != 403:
                raise
            return _socrata_views_fields(parsed.netloc, socrata_id.group(1)), False
    else:
        data = _fetch_json(_to_api_url(endpoint))
    if isinstance(data, list):                       # Socrata: [ {field: val, ...} ]
        keys: dict[str, None] = {}
        for rec in data:
            keys.update(dict.fromkeys(rec.keys()))
        return list(keys), False
    if isinstance(data, dict):
        if "rows" in data and data["rows"]:           # Carto: {rows:[{...}]}
            keys = {}
            for row in data["rows"][:_PROBE_LIMIT]:
                keys.update(dict.fromkeys(row.keys()))
            return list(keys), False
    return [], False


def _has(fields: list[str], needles: tuple[str, ...]) -> bool:
    low = [f.lower() for f in fields]
    return any(any(n in f for f in low) for n in needles)


def probe(endpoint: str) -> dict:
    blank = {"ok": False, "created": False, "closed": False, "geo": False,
             "channel": False, "agency": False, "n_fields": 0}
    try:
        fields, geo_hint = _first_record_fields(endpoint)
    except Exception as exc:
        return {**blank, "error": str(exc)[:140]}
    if not fields:
        return {**blank, "error": "no records returned"}
    return {
        "ok": True, "error": "",
        "created": _has(fields, _CREATED),
        "closed": _has(fields, _CLOSED),
        "geo": _has(fields, _GEO) or geo_hint,
        "channel": _has(fields, _CHANNEL),   # intake-channel field → field-completeness signal
        "agency": _has(fields, _AGENCY),
        "n_fields": len(fields),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--strict", action="store_true", help="exit 1 if any api-tier endpoint regressed")
    ap.add_argument("--write", action="store_true", help="write api_checked / api_fields back to the census")
    args = ap.parse_args()

    if not CENSUS.exists():
        print(f"census not found: {CENSUS}", file=sys.stderr)
        return 2
    rows = list(csv.DictReader(CENSUS.open()))
    cols0 = rows[0].keys() if rows else []
    ep_col = "endpoint_url" if "endpoint_url" in cols0 else ("endpoint" if "endpoint" in cols0 else None)
    if ep_col is None:
        print("census has no endpoint_url/endpoint column — nothing to probe.", file=sys.stderr)
        return 0

    regressions = 0
    print(f"{'city':28} {'status':11} {'evidence':11} created closed geo   result")
    print("-" * 92)
    for row in rows:
        endpoint = (row.get(ep_col) or "").strip()
        if not endpoint:
            continue
        res = probe(endpoint)
        flags = "".join("  ✓   " if res[k] else "  ·   " for k in ("created", "closed", "geo"))
        verdict = "OK" if res["ok"] else f"FAIL: {res['error']}"
        if res["ok"] and not (res["created"] and res["geo"]):
            verdict = "THIN (missing created/geo)"
        print(f"{row['city']:28} {row.get('status',''):11} {row.get('evidence',''):11} {flags} {verdict}")
        # an api-tier scoreable row that no longer returns the core fields is a regression
        if row.get("evidence") == "api" and row.get("status") == "scoreable" and not (
            res["ok"] and res["created"] and res["geo"]
        ):
            regressions += 1
        if args.write:
            row["api_checked"] = "ok" if res["ok"] else "fail"
            row["api_fields"] = "+".join(k for k in ("created", "closed", "geo") if res.get(k))
            # Depth signals for score_maturity.py's field-completeness dimension (P5.9-4).
            row["field_count"] = res.get("n_fields", 0)
            row["has_channel"] = "y" if res.get("channel") else ""
            row["has_agency"] = "y" if res.get("agency") else ""

    if args.write:
        cols = list(rows[0].keys())
        for extra in ("api_checked", "api_fields", "field_count", "has_channel", "has_agency"):
            if extra not in cols:
                cols.append(extra)
        with CENSUS.open("w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=cols)
            w.writeheader()
            w.writerows(rows)
        print(f"\nwrote api_checked / api_fields to {CENSUS.name}")

    print(f"\n{regressions} api-tier regression(s).")
    return 1 if (args.strict and regressions) else 0


if __name__ == "__main__":
    raise SystemExit(main())
