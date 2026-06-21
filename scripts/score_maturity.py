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

# Inspected anchors: the cohort we built ingestion adapters for, so each was scored against its
# **actual published schema and history** (not the census heuristic). Order = DIMS:
# avail, granularity, history, cadence, api, open311, fields, geocode, docs.
# The first six are the original hand-scored leaders; the last four (Austin/Boston/KC/Nashville)
# were promoted off the conservative derived defaults once we'd worked with their real data —
# justification per city in the comment, and carried into the output `note`.
ANCHORS: dict[str, tuple] = {
    "San Francisco, CA": (3, 3, 3, 3, 3, 3, 3, 3, 3),  # Socrata vw6y-z8j6; 2008; nightly; Open311 leader; full field set
    "New York, NY":      (3, 3, 3, 3, 3, 2, 3, 3, 3),  # Socrata erm2-nwe9; 2010; daily; channel + agency fields
    "Chicago, IL":       (3, 3, 2, 3, 3, 2, 3, 3, 3),  # Socrata v6vf-nfxy; unified 2018; daily; rich schema
    "Baltimore, MD":     (3, 3, 3, 2, 3, 3, 3, 2, 2),  # ArcGIS per-year 2016+; first-mover Open311; publishes channel
    "Philadelphia, PA":  (3, 3, 3, 3, 3, 2, 2, 2, 3),  # Carto public_cases_fc; 2014; daily; strong dictionary; no channel
    "Washington, DC":    (3, 3, 2, 3, 3, 1, 2, 3, 3),  # Open Data DC ArcGIS; per-year; no Open311; no channel
    "Boston, MA":        (3, 3, 3, 3, 3, 2, 3, 2, 3),  # Analyze Boston CKAN; since 2011; Open311; source/dept/SLA fields; well-documented
    "Austin, TX":        (3, 3, 3, 3, 3, 1, 3, 2, 2),  # Socrata xwdj-i9he; 2014; half-hourly; publishes method_received (channel)
    "Kansas City, MO":   (3, 3, 2, 3, 3, 1, 3, 2, 2),  # OpenData KC Socrata; 2021; daily; report_source + department + days_to_close
    "Nashville, TN":     (3, 3, 2, 2, 3, 1, 2, 2, 2),  # hubNashville ArcGIS Hub; 2017; core fields, no channel
}
ANCHOR_CITIES = set(ANCHORS)

# City population — so Tab 9's full table can be sorted by size (surfacing the biggest
# cities, which carry the most 311 data, and exposing which large cities publish nothing).
# Cohort cities use our pipeline's own ACS figure (the same number the Service Delivery tab
# reports — one source of truth); every other city uses its 2020 Decennial Census place
# population. Curated here (like ANCHORS) because the runner has no Census network access;
# edit a value and re-run to correct it.
POPULATION: dict[str, int] = {
    # Cohort — exact, from peer_city_metrics.parquet (matches the Service Delivery tab).
    "New York, NY": 8_516_202, "Los Angeles, CA": 3_857_897, "Chicago, IL": 2_707_648,
    "Philadelphia, PA": 1_582_432, "Dallas, TX": 1_299_553, "Austin, TX": 967_862,
    "San Francisco, CA": 836_321, "Seattle, WA": 741_440, "Nashville, TN": 709_846,
    "Washington, DC": 672_079, "Boston, MA": 663_972, "Memphis, TN": 629_063,
    "Baltimore, MD": 577_193, "Kansas City, MO": 508_233,
    # Non-cohort — 2020 Decennial Census place population.
    "Houston, TX": 2_304_580, "Phoenix, AZ": 1_608_139, "San Antonio, TX": 1_434_625,
    "San Diego, CA": 1_386_932, "San Jose, CA": 1_013_240, "Jacksonville, FL": 949_611,
    "Fort Worth, TX": 918_915, "Columbus, OH": 905_748, "Indianapolis, IN": 887_642,
    "Charlotte, NC": 874_579, "Denver, CO": 715_522, "Oklahoma City, OK": 681_054,
    "El Paso, TX": 678_815, "Portland, OR": 652_503, "Detroit, MI": 639_111,
    "Louisville, KY": 633_045, "Milwaukee, WI": 577_222, "Albuquerque, NM": 564_559,
    "Tucson, AZ": 542_629, "Fresno, CA": 542_107, "Sacramento, CA": 524_943,
    "Mesa, AZ": 504_258, "Atlanta, GA": 498_715, "Omaha, NE": 486_051,
    "Colorado Springs, CO": 478_961, "Raleigh, NC": 467_665,
    # Ranks 41–50 — top-50 canvass expansion (2020 Census place population).
    "Long Beach, CA": 466_742, "Virginia Beach, VA": 459_470, "Miami, FL": 442_241,
    "Oakland, CA": 440_646, "Minneapolis, MN": 429_954, "Tulsa, OK": 413_066,
    "Bakersfield, CA": 403_455, "Wichita, KS": 397_532, "Arlington, TX": 394_266,
    "Aurora, CO": 386_261,
    # Mid-size enablers (census rank 0, below the top 50).
    "New Orleans, LA": 383_997, "Cincinnati, OH": 309_317,
    "Pittsburgh, PA": 302_971, "St. Louis, MO": 301_578,
}

# Every anchor is a cohort city, but not every cohort city is exhaustively documented; this set
# is the same 10 and drives the in-cohort flag.
IN_COHORT = set(ANCHORS)


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
            span = 2025 - yr  # rubric anchors: >=10yr -> 3, ~3-9yr -> 2, <3yr -> 1
            s["history_depth"] = 3 if span >= 10 else (2 if span >= 3 else 1)

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

    missing_pop = sorted(set(census["city"]) - set(POPULATION))
    if missing_pop:
        print(f"WARNING: no population for {len(missing_pop)} census cities: {missing_pop}")

    rows = []
    for _, c in census.iterrows():
        city = c["city"]
        if city in ANCHORS:
            scores = dict(zip(DIMS, ANCHORS[city]))
        else:
            scores = derive_scores(c["status"], c.get("evidence", ""), c.get("note", ""))
        rows.append({
            "city": city,
            "population": POPULATION.get(city, pd.NA),
            "in_cohort": city in IN_COHORT,
            "status": c["status"],
            "evidence": c.get("evidence", ""),
            "derived": city not in ANCHORS,
            **scores,
            "note": c.get("note", ""),
        })

    out = pd.DataFrame(rows, columns=["city", "population", "in_cohort", "status", "evidence",
                                      "derived", *DIMS, "note"])
    out["population"] = out["population"].astype("Int64")
    out["total"] = out[DIMS].sum(axis=1)
    out = out.sort_values("total", ascending=False).reset_index(drop=True)
    out.drop(columns="total").to_csv(MATURITY, index=False)

    n_anchor = sum(~out["derived"])
    print(f"Wrote {len(out)} cities to {MATURITY.name} "
          f"({n_anchor} hand-scored anchors, {len(out) - n_anchor} derived; "
          f"{int((out[DIMS].sum(axis=1) == 0).sum())} scored 0 as inaccessible).")


if __name__ == "__main__":
    main()
