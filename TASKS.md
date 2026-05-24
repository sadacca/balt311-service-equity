# Task List: 311 Service Equity Dashboard

Ordered by dependency. Complete data investigation tasks before building on their findings.

---

## Phase 0 — Data Investigation

- [x] **P0-1: Validate 2025 sample** — executed `validate_2025_sample.ipynb` against `data/sample/sample_311_2025.json`
  - **MethodReceived**: Phone 53%, System 27%, API 16%, Internal 3%, Mail 1%, Email <1%. Resident = Phone+API+Mail+Email (~70%). Staff/proactive = System+Internal (~30%). **Distinction is viable.**
  - **Coordinate coverage**: 73% overall; ~99% after excluding ECC- prefix types. ECC types intentionally have no address.
  - **LastActivity reopen signal**: NONE — only 'Service Response' (69%) and NULL (30%). **Reopen metric not computable; dropped from spec.**
  - **days_to_close**: Sub-second negatives are timestamp precision artifacts in same-day closures; floor to 0. p50=0 (driven by proactive types), p90=14d, p99=91d.
  - **SRStatus / CloseDate consistency**: Perfect — zero mismatches.
  - **DueDate**: 100% populated. Standardized per SRType. ECC and proactive types have DueDate < CreatedDate (artifact) — exclude from on-time calculation.
  - **On-time rate**: 53.2% overall; varies dramatically by type. Valid equity metric after ECC/proactive exclusion.
  - **Agency**: Trailing whitespace — strip in pipeline. **Outcome**: Non-breaking space U+00A0 — normalize.
  - **ECC types**: 27.6% of volume. No coordinates, not service delivery — exclude from equity subset.

- [x] **P0-2 / P0-3: Ingest 2024 and 2025 data** — full datasets fetched via parallel ArcGIS FeatureServer pipeline. 2023 endpoint added (May 2026); 2026 endpoint confirmed present. All four years in `ENDPOINTS` dict.

- [x] **P0-4: Census tract boundaries** — `baltimore_tracts.geojson` downloaded from Census GENZ2023 ZIP+SHP, filtered to FIPS 510 (Baltimore City). Committed to `data/processed/`.

- [x] **P0-5: CSA boundaries** — built by dissolving tract polygons by CSA name using BNIA VitalSigns crosswalk. `baltimore_csas.geojson` committed to `data/processed/`.

- [x] **P0-6: Tract → CSA crosswalk** — `tract_to_csa.csv` downloaded from BNIA VitalSigns GitHub raw. Columns: geoid, csa_name. Committed to `data/processed/`.

---

## Phase 1 — Pipeline

- [x] **P1-1 / P1-2: Run clean + aggregate for 2024 and 2025** — headless pipeline `scripts/pipeline.py` built and working. GitHub Actions two-job workflow (ingest → process) committed.

- [x] **P1-3: Boundary GeoJSONs to `data/processed/`** — copied automatically by pipeline stage_process.

- [x] **P1-4: Commit `data/processed/`** — 2024 and 2025 tract/CSA metrics + boundaries committed. Total size within GitHub limits.

- [x] **P1-5: Ingest and process 2023** — endpoint fixed; 2023 data confirmed processed and available.

- [ ] **P1-6: Re-run 2025 pipeline with Census API key** — 2025 was processed before Census API key was configured; `requests_per_1k` likely missing. Trigger fresh workflow run for year=2025.

---

## Phase 2 — App MVP

- [x] **P2-1: Mapbox token** — obtained, stored in Streamlit Cloud Secrets. `.streamlit/secrets.toml.example` committed; actual token never in repo.

- [x] **P2-2: App deployed** — live at https://balt311equity.streamlit.app/. Year, geo level, SRType, metric selectors all working.

- [x] **P2-3: SRType filter** — current filter uses `top_sr_type` as a proxy. Behavior documented; per-type stratification moved to Phase 4 (P4-1).

- [x] **P2-4: On-time rate metric** — `is_on_time`, `due_date_gap_days` computed in `metrics.py`; `on_time_rate` in `aggregate_tract()` and `rollup_to_csa()`.

- [x] **P2-5: Color scale** — diverging RdBu_r centered on citywide median implemented in `map_view.py`.

- [x] **P2-6: Streamlit Community Cloud deployment** — auto-redeploys on push to main.

---

## Phase 2b — Demographic Equity Summaries + Multi-Year Foundation *(in progress)*

Goal: add race and income context below the map — distribution comparisons for the selected metric across demographic groups, with an overlap score and plain-language label. Multi-year data (2023–2025) enables the year-over-year overlap trend chart, moved here from Phase 3 because the data is now ready.

### Data pipeline

- [ ] **P2b-1: Fetch tract-level race and income from ACS**
  - New function `_fetch_tract_demographics(dest: Path)` in `scripts/pipeline.py`
  - ACS 2023 5-year variables (same API call pattern as population, county=510):
    - `B02001_001E` — total race population
    - `B02001_002E` — White alone
    - `B02001_003E` — Black or African American alone
    - `B19013_001E` — median household income
  - Compute `pct_black = B02001_003E / B02001_001E`, `pct_white = B02001_002E / B02001_001E`
  - Output: `data/processed/tract_demographics.csv` — columns: geoid, pct_black, pct_white, median_income
  - Soft-fail (log warning) if Census API unavailable; app handles missing file gracefully

- [ ] **P2b-2: Roll up demographics to CSA level**
  - New function `rollup_demographics_to_csa(tract_demo_df, xwalk_df, pop_df)` in `src/balt311/metrics.py`
  - Race: population-weighted mean of tract pct_black / pct_white across tracts in each CSA
  - Income: population-weighted mean of tract median_income as CSA approximation
    (Note: BNIA Vital Signs publishes authoritative CSA income — integrate in Phase 4 if weighted mean proves insufficient)
  - Output: `data/processed/csa_demographics.csv` — same columns as tract file
  - Call from `stage_process()` in pipeline; commit both CSVs to repo

- [ ] **P2b-3: Re-run pipeline to generate demographic files**
  - Run for 2024 and 2025 (or run standalone `_fetch_tract_demographics` + `rollup_demographics_to_csa` once)
  - Commit `tract_demographics.csv` and `csa_demographics.csv` to `data/processed/`

### App component

- [ ] **P2b-4: Create `app/components/equity_distributions.py`**

  **Classification logic:**
  - Race groups: Black-predominant (pct_black > 50%) vs. White-predominant (pct_white > 50%); drop mixed (neither >50%) from the race comparison
  - Income groups: above-median vs. below-median of the tract/CSA income distribution

  **Visualization** (Plotly, two side-by-side charts — race | income):
  - For each group pair: shaded IQR band (25th–75th percentile) + horizontal median line + individual dot per geography (strip chart style)
  - Color: consistent with map palette (red/blue); dots semi-transparent
  - Axis: metric value (left) vs. group label (bottom)
  - Title shows group sizes (n=X vs n=Y)

  **Overlap scoring** (computed per chart):
  ```
  overlap = max(0, min(q75_A, q75_B) - max(q25_A, q25_B))
  span    = max(q75_A, q75_B) - min(q25_A, q25_B)
  score   = overlap / span   (0 = no overlap, 1 = full overlap)
  ```
  - score > 0.6 → "not bad" (green badge)
  - score 0.3–0.6 → "could be better" (amber badge)
  - score < 0.3 → "needs review" (red badge)

  **Display per chart:** Plotly figure + score badge + one-sentence description of which group performs better and by how much (median difference)

- [ ] **P2b-5: Wire into `app/app.py`**
  - Load `{geo_key}_demographics.csv` from `data/processed/` (cached, soft-fail if absent)
  - Add section below map divider: "Equity by Demographics"
  - Pass current `metric_col` and `metric_label` — section updates automatically on metric filter change
  - Show both race and income charts side by side (two columns)

- [ ] **P2b-6: Equity trend chart — year-over-year overlap scores** *(moved from P3-1; 2023/2024/2025 data ready)*
  - New component `app/components/equity_trend.py`
  - Shared `overlap_score()` utility in `app/components/utils.py` (used by both P2b-4 and P2b-6)
  - Line chart: x=year, y=overlap score, one line per equity metric; one chart for race, one for income
  - Reference bands: green >0.6, amber 0.3–0.6, red <0.3
  - Shows whether disparity is improving, stable, or worsening year over year

---

## Phase 3 — Detail Views and Analysis *(next phase priorities)*

- [ ] **P3-1: Detail scatter toggle**
  - Below the IQR summary charts: toggle button "Show individual geographies"
  - Scatter: x = race % (pct_black) or median income, y = selected equity metric; each point = one tract/CSA
  - Color = same diverging scale as map (above/below citywide median)
  - Hover shows geography name + both axis values
  - Regression line (OLS) overlaid with 95% CI band
  - Separate scatter for race and income (two charts, matching the IQR layout)

- [ ] **P3-3: Equity analysis notebook**
  - `notebooks/04_equity_analysis.ipynb`
  - Spearman rank correlation: each equity metric vs. pct_black and vs. median_income, at both tract and CSA level
  - Quartile comparison (Kruskal-Wallis) for closure rate and days-to-close across income quartiles
  - Top-5 SRType stratification: run same correlation for each major request type
  - Findings table exported to `data/processed/equity_findings.csv` for potential app integration

- [ ] **P3-4: Executive summary**
  - 1-page `docs/executive_summary.md` (or PDF via nbconvert)
  - Key findings with inline map thumbnail references
  - Audience: Mayor's Office, City Council, CDO

---

## Phase 4 — SRType Stratification and Subsequent Priorities

- [ ] **P4-1: Per-SRType tract aggregation**
  - Current SRType sidebar filter uses `top_sr_type` per tract as a proxy — does not enable per-type equity analysis
  - Pipeline change: add `by_srtype` aggregation in `aggregate_tract()` producing `(geoid, sr_type)` rows
  - Output: `data/processed/tract_metrics_{year}_by_srtype.parquet` (multi-index or long format)
  - App change: when an SRType is selected, load the by_srtype file and filter to that type; fall back to all-type aggregate when no filter is active
  - Enables: "does 'Pothole' get resolved faster in wealthier neighborhoods than 'Bulk Trash'?"

- [ ] **P4-2: BNIA Vital Signs direct integration for CSA demographics**
  - Replace population-weighted rollup of tract ACS data with authoritative BNIA CSA indicators
  - BNIA Vital Signs ArcGIS Hub provides CSA-level: `pct_nhblk` (% non-Hispanic Black), `pct_nhwht`, `mhhi` (median household income) — updated with each Vital Signs edition
  - Fetch and cache as `data/processed/csa_demographics_bnia.csv`; compare against ACS rollup to validate

- [ ] **P4-3: Year-over-year comparison panel**
  - Side-by-side map or metric delta view for a selected geography across years
  - Requires 2023 data (P1-5) to make a three-year comparison meaningful

- [ ] **P4-5: Historical data ingest (2016–2022)** *(blocked on TD-1)*
  - Add `fetch_year_socrata()` or equivalent to `src/balt311/ingest.py` once pre-2023 source is confirmed
  - Route `fetch_year()` by year: ArcGIS for 2023+, Socrata (or historical ArcGIS layer) for pre-2023
  - Validate field name consistency between sources — Socrata exports often differ in column casing/naming
  - Run pipeline for each year 2016–2022; commit processed files
  - Payoff: 9-year trend chart (2016–2025) gives a statistically meaningful equity trajectory

- [ ] **P4-4: Regression panel (optional)**
  - OLS: `log(days_to_close)` ~ pct_black + median_income + SRType FE + month FE
  - Displays income and race coefficients with 95% CI
  - Defensible claim about whether disparity is income-driven, race-driven, or structural

---

## Pending Items

| Question / Gap | Status |
|---|---|
| Duplicate `SRRecordID`s across years? | Still pending — need cross-year dedup check |
| 2025 `requests_per_1k` missing (Census API key not set at run time) | Fix via P1-6 re-run |
| 2023 data in progress | Running via Actions |
| 2022 ArcGIS endpoint returns 0 records | Annual FeatureServer naming appears to start at 2023; pre-2023 data likely on Socrata or a consolidated ArcGIS historical layer — see P4-5 |

---

## To-Do — Investigation Required

- [ ] **TD-1: Locate pre-2023 historical 311 data**
  - 2022 ArcGIS endpoint (`311_Customer_Service_Requests_2022/FeatureServer/0`) returns 0 records; annual FeatureServer naming likely started with 2023
  - Two candidates to check on data.baltimorecity.gov:
    1. **Socrata dataset** — city ran on Socrata before ArcGIS migration; search "311" for a multi-year table covering 2016+; note the 4x4 dataset ID (e.g. `9agw-sxsr`) and date range
    2. **Consolidated ArcGIS historical layer** — may exist as `311_Customer_Service_Requests_Historical` or similar in the same ArcGIS organization (`UWYHeuuJISiGmgXx`)
  - Once source is confirmed, add `fetch_year_socrata()` (or equivalent) to `src/balt311/ingest.py` routed by year; same downstream pipeline applies
  - Target coverage: 2016–2022 (7 additional years substantially strengthens the trend chart)

- [ ] **TD-2: Manual validation of IQR overlap scores and demographic calculations**
  - Spot-check `overlap_score()` against hand-calculated values for at least two metric × year × geo-level combinations
  - Verify demographic classification thresholds: confirm majority-Black (>50%) and majority-White (>50%) counts are plausible given Baltimore's demographic makeup (~63% Black citywide)
  - Confirm `pct_black`/`pct_white` values in `tract_demographics.csv` are in expected range (0–1); check for tracts with unexpected nulls
  - Validate CSA rollup: pick 2–3 CSAs and manually re-aggregate from tract data to confirm weighted race % and income match `csa_demographics.csv`
  - Cross-check `median_income` values against published ACS tables for a sample of tracts (e.g. Roland Park should be high, Sandtown-Winchester low)
  - Verify trend chart direction is interpretable: rising overlap = narrowing disparity (confirm with a manually computed year-pair comparison)

---

*Last updated: May 2026. Mark items `[x]` when done.*
