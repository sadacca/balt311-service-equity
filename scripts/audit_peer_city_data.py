#!/usr/bin/env python3
"""Cross-city data audit (internal tooling — not surfaced on any Streamlit tab).

Answers two questions per cohort city before a missing/implausible metric gets reported as
"this city's data just doesn't support that metric":

  Tier 1 (no network — runs anywhere, anytime): does the metric look structurally missing or
  implausible in the data already committed to `data/processed/`? (null/near-zero median
  days-to-close, near-0%/100% closure rate, high same-day-close share, implausible per-1k.)

  Tier 2 (network — CI only): does the live portal's *full* raw schema contain a better-fitting
  column than the one each adapter actually mapped, or has a previously-mapped column
  disappeared? Uses the `CityAdapter.schema_fields(year)` hook (full raw column list, not just
  the ~6 canonical fields each adapter selects) so a "missing" metric can be told apart from a
  mis-mapped or renamed one.

Usage:
    python scripts/audit_peer_city_data.py                  # Tier 1 only, all cities
    python scripts/audit_peer_city_data.py --year 2024 --live-schema   # + Tier 2 (network)
    python scripts/audit_peer_city_data.py --cities chicago,memphis --live-schema

Writes a JSON report to data/audit/ (gitignored — diagnostic, not app-consumed) and prints a
human-readable summary to stdout.
"""
import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import pandas as pd

from balt311.cities import ADAPTERS
from balt311.cities import boston as boston_mod
from balt311.cities import dc as dc_mod
from balt311.cities import memphis as memphis_mod
from balt311.cities import nashville as nashville_mod
from balt311.cities import philadelphia as philadelphia_mod
from balt311.cities import socrata as socrata_mod
from balt311.cities.socrata import SocrataAdapter

PROC = ROOT / "data" / "processed"
AUDIT_DIR = ROOT / "data" / "audit"

# Module-level raw→canonical mappings for the non-Socrata adapters, keyed by adapter class —
# needed because (unlike Socrata's runtime `resolve_field_map`) these are fixed at import time
# or built by a per-module `_resolve()` helper, not a method on the adapter instance.
_STATIC_FIELD_MAPS = {
    "DCAdapter": dc_mod.FIELD_MAP,
    "PhiladelphiaAdapter": philadelphia_mod.FIELD_MAP,
    "BostonAdapter": boston_mod.FIELD_MAP,
}
_RESOLVERS = {
    "MemphisAdapter": memphis_mod._resolve,
    "NashvilleAdapter": nashville_mod._resolve,
}


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


# ---------------------------------------------------------------------------
# Tier 1 — local, no-network fill-rate / plausibility checks
# ---------------------------------------------------------------------------

def audit_metrics_table(year: int | None = None) -> list[dict]:
    """Flag implausible/missing delivery metrics already committed to peer_city_metrics.parquet."""
    path = PROC / "peer_city_metrics.parquet"
    if not path.exists():
        log(f"no {path} — Tier 1 skipped")
        return []
    df = pd.read_parquet(path)
    if year is not None:
        df = df[df["year"] == year]
    if df.empty:
        return []
    # latest year per city if multiple and no --year filter
    latest = df.sort_values("year").groupby("city").tail(1)

    findings = []
    for _, r in latest.iterrows():
        flags = []
        if pd.isna(r.get("median_days_to_close")):
            flags.append("median_days_to_close is null")
        if pd.isna(r.get("closure_rate")):
            flags.append("closure_rate is null")
        elif r["closure_rate"] >= 0.99:
            flags.append(f"closure_rate implausibly high ({r['closure_rate']:.2%})")
        elif r["closure_rate"] <= 0.01:
            flags.append(f"closure_rate implausibly low ({r['closure_rate']:.2%})")
        pct_sd = r.get("pct_same_day_close")
        if pd.notna(pct_sd) and pct_sd >= 0.5:
            flags.append(f"pct_same_day_close high ({pct_sd:.2%}) — auto-close contamination risk")
        mdtc = r.get("median_days_to_close")
        if pd.notna(mdtc) and mdtc < 1:
            flags.append(f"median_days_to_close sub-day ({mdtc:.2f})")
        p1k = r.get("requests_per_1k")
        if pd.isna(p1k):
            flags.append("requests_per_1k is null (population lookup failed)")
        elif p1k < 20:
            flags.append(f"requests_per_1k implausibly low ({p1k:.0f})")
        if flags:
            findings.append({
                "city": r["city"], "year": int(r["year"]), "tier": 1, "flags": flags,
            })
    return findings


def audit_tract_srtype_fill(year: int | None = None) -> list[dict]:
    """Flag cities whose tract×SRType breakdown is mostly null on median_days_to_close —
    the Chicago/Memphis pattern: the column exists in the schema but is populated for almost
    no records, so it reads as "missing" rather than "present but empty"."""
    path = PROC / "peer_city_tract_srtype_metrics.parquet"
    if not path.exists():
        log(f"no {path} — tract×SRType fill check skipped")
        return []
    df = pd.read_parquet(path)
    if year is not None:
        df = df[df["year"] == year]
    if df.empty:
        return []
    findings = []
    for city, g in df.groupby("city"):
        fill_rate = g["median_days_to_close"].notna().mean()
        if fill_rate < 0.5:
            findings.append({
                "city": city, "year": int(g["year"].iloc[0]), "tier": 1,
                "flags": [
                    f"median_days_to_close populated for only {fill_rate:.1%} of "
                    f"{len(g):,} tract×SRType rows — likely a sparse/empty close-date "
                    "field rather than a missing one"
                ],
            })
    return findings


# ---------------------------------------------------------------------------
# Tier 2 — live schema introspection / mis-mapping check (network, CI only)
# ---------------------------------------------------------------------------

def _selected_raw_fields(adapter, schema: list[str]) -> dict[str, str] | None:
    """Canonical→raw mapping this adapter would actually pick, given the live `schema`.
    Returns None if the adapter's mapping strategy isn't recognized (mapping check skipped,
    but the raw schema is still reported)."""
    cls = type(adapter).__name__
    if isinstance(adapter, SocrataAdapter):
        raw_map = socrata_mod.resolve_field_map(schema, adapter.field_overrides)
        return {canon: raw for raw, canon in raw_map.items()}
    if cls in _STATIC_FIELD_MAPS:
        raw_map = _STATIC_FIELD_MAPS[cls]  # raw -> canonical
        return {canon: raw for raw, canon in raw_map.items() if raw in schema}
    if cls in _RESOLVERS:
        raw_map = _RESOLVERS[cls](schema)  # raw -> canonical
        return {canon: raw for raw, canon in raw_map.items()}
    return None


def audit_live_schema(year: int, cities: list[str]) -> list[dict]:
    findings = []
    for slug in cities:
        if slug not in ADAPTERS:
            continue
        adapter = ADAPTERS[slug]()
        try:
            schema = adapter.schema_fields(year)
        except Exception as exc:
            findings.append({
                "city": adapter.city, "year": year, "tier": 2,
                "flags": [f"schema_fields() raised: {exc!r}"],
            })
            continue
        if schema is None:
            log(f"  {adapter.city}: schema introspection not implemented for this adapter")
            continue

        flags = []
        selected = _selected_raw_fields(adapter, schema)
        if selected is None:
            flags.append(f"mapping strategy for {type(adapter).__name__} not recognized by "
                         "the audit — schema only, no mis-mapping check run")
        else:
            for canon in ("CreatedDate", "CloseDate", "SRType", "Latitude", "Longitude"):
                if canon not in selected:
                    flags.append(f"no raw field resolved for canonical '{canon}' — schema has "
                                 f"{schema}")
            mapped_raw = set(selected.values())
            unmapped = sorted(set(schema) - mapped_raw)
            if unmapped:
                flags.append(f"unmapped raw columns (review for a better fit): {unmapped}")

        findings.append({
            "city": adapter.city, "year": year, "tier": 2,
            "schema": schema, "selected_mapping": selected, "flags": flags,
        })
    return findings


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------

def run(year: int | None, cities: list[str], live_schema: bool) -> None:
    findings = audit_metrics_table(year) + audit_tract_srtype_fill(year)
    if live_schema:
        if year is None:
            log("--live-schema requires --year; skipping Tier 2")
        else:
            findings += audit_live_schema(year, cities)

    AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = AUDIT_DIR / f"audit_{year or 'latest'}.json"
    out_path.write_text(json.dumps(findings, indent=2, default=str))
    log(f"Wrote {len(findings)} findings → {out_path}")

    print("\n=== Cross-city data audit ===")
    if not findings:
        print("No issues flagged.")
        return
    for f in findings:
        print(f"\n[{f['city']} {f['year']}] (tier {f['tier']})")
        for flag in f["flags"]:
            print(f"  - {flag}")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Internal cross-city data validation/audit")
    p.add_argument("--year", type=int, help="Year to audit (required for --live-schema)")
    p.add_argument("--cities", default=",".join(ADAPTERS),
                   help="Comma-separated city slugs (default: all registered)")
    p.add_argument("--live-schema", action="store_true",
                   help="Also run Tier 2 (network): live raw-schema mapping check")
    args = p.parse_args()
    run(args.year, [c.strip() for c in args.cities.split(",") if c.strip()], args.live_schema)
