#!/usr/bin/env python3
"""Expand the 311 open-data maturity scorecard from the hand-scored anchors to all 45 metros.

The detailed rubric (9 dimensions, 0–3) was hand-scored for 6 anchor cities. This script keeps
those anchors and **derives** numerical scores for every other city in the coverage census from
its verified signals (status / evidence tier / note), so Tab 9 can show a full numerical
evaluation rather than 6 rows beside a coarse ✅/🟡/❔ list. Two rules the user set:

  * cities whose record-level 311 is **inaccessible** (census status "unconfirmed") score **0**
    on every dimension — you cannot credit data you cannot reach;
  * the derived scores are an explicit, documented function of the census (not hand-tuned), and
    are calibrated to sit at or below the hand-scored leaders.

Output: rewrites `data/processed/peer_city_maturity.csv` with all 45 cities, carrying `status`
and `evidence` through so the tab's sortable table can show provenance. Re-run after the census
(`peer_city_coverage_census.csv`) changes.

    python scripts/score_maturity.py
"""
import re
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
PROC = ROOT / "data" / "processed"
CENSUS = PROC / "peer_city_coverage_census.csv"
MATURITY = PROC / "peer_city_maturity.csv"

DIMS = [
    "availability_license", "granularity", "history_depth", "update_cadence", "api_access",
    "standardization", "field_completeness", "geocoding_coverage", "documentation",
]

# The 10 cities whose 311 data is actually ingested into this dashboard.
IN_COHORT = {
    "Baltimore, MD", "Washington, DC", "Philadelphia, PA", "New York, NY", "Chicago, IL",
    "San Francisco, CA", "Austin, TX", "Nashville, TN", "Kansas City, MO", "Boston, MA",
}

# Hand-scored anchors (kept verbatim; the rest are derived). Loaded from the existing maturity
# file at run time so edits to the anchors persist — these are the fallback if it's absent.
ANCHOR_CITIES = {
    "Baltimore, MD", "Washington, DC", "Philadelphia, PA",
    "New York, NY", "Chicago, IL", "San Francisco, CA",
}


def derive_scores(status: str, evidence: str, note: str) -> dict:
    """Map a census row to 0–3 rubric scores. Inaccessible ('unconfirmed') → all zeros."""
    note = (note or "").lower()
    if status == "unconfirmed":
        return {d: 0 for d in DIMS}

    if status == "scoreable":
        s = dict(availability_license=3, granularity=3, history_depth=2, update_cadence=2,
                 api_access=3, standardization=1, field_completeness=2, geocoding_coverage=2,
                 documentation=2)
    else:  # partial / limited
        s = dict(availability_license=2, granularity=2, history_depth=1, update_cadence=1,
                 api_access=1, standardization=0, field_completeness=1, geocoding_coverage=1,
                 documentation=1)

    # History depth — a rolling/short window caps it low; an explicit start year scales it.
    if any(k in note for k in ("rolling", "12 month", "7-day", "7 day", "90 day", "lookback", "weekly cases")):
        s["history_depth"] = 1
    else:
        m = re.search(r"since\s*(20\d{2})|(20\d{2})\s*-\s*present|(20\d{2})\+", note)
        yr = next((int(g) for g in (m.groups() if m else []) if g), None)
        if yr:
            span = 2025 - yr
            s["history_depth"] = 3 if span >= 12 else (2 if span >= 6 else 1)

    # Update cadence — a published fast refresh lifts it.
    if any(k in note for k in ("daily", "nightly", "half-hour", "real-time", "15-min", "several times a day")):
        s["update_cadence"] = 3

    # API access — a live API check is the strongest signal; an aggregator-only/none find caps it.
    if evidence == "api":
        s["api_access"] = 3
    elif evidence in ("third_party", "none"):
        s["api_access"] = min(s["api_access"], 1)

    if "open311" in note:
        s["standardization"] = max(s["standardization"], 2)
    return s


def main() -> None:
    census = pd.read_csv(CENSUS)
    anchors = {}
    if MATURITY.exists():
        cur = pd.read_csv(MATURITY)
        for _, r in cur.iterrows():
            if r["city"] in ANCHOR_CITIES:
                anchors[r["city"]] = {d: int(r[d]) for d in DIMS}

    rows = []
    for _, c in census.iterrows():
        city = c["city"]
        scores = anchors.get(city) or derive_scores(c["status"], c.get("evidence", ""), c.get("note", ""))
        rows.append({
            "city": city,
            "in_cohort": city in IN_COHORT,
            "status": c["status"],
            "evidence": c.get("evidence", ""),
            "derived": city not in anchors,
            **scores,
            "note": c.get("note", ""),
        })

    out = pd.DataFrame(rows, columns=["city", "in_cohort", "status", "evidence", "derived", *DIMS, "note"])
    out["total"] = out[DIMS].sum(axis=1)
    out = out.sort_values("total", ascending=False).reset_index(drop=True)
    out.drop(columns="total").to_csv(MATURITY, index=False)

    n_anchor = sum(~out["derived"])
    print(f"Wrote {len(out)} cities to {MATURITY.name} "
          f"({n_anchor} hand-scored anchors, {len(out) - n_anchor} derived; "
          f"{int((out[DIMS].sum(axis=1) == 0).sum())} scored 0 as inaccessible).")


if __name__ == "__main__":
    main()
