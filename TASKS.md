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

## Phase 3 — Operations Tab *(next release)*

**Goal**: answer "how is Baltimore 311 doing overall?" before asking "is it equitable?". Restructures the app around two tabs — Operations (default) and Equity (existing content) — sharing the sidebar year/geo/metric selectors. Sets up year-over-year performance tracking and eventual cross-metro comparison.

### Architecture

- [ ] **P3-0: Tab restructure**
  - Replace single-page layout with `st.tabs(["Operations", "Equity"])` in `app.py`
  - Sidebar filters (year, geo level, metric, SRType) remain shared across both tabs
  - All existing map + equity content moves into the Equity tab unchanged
  - Operations tab is the default (first) tab

### Pipeline additions

- [ ] **P3-1: Per-SRType aggregate table**
  - New pipeline output: `data/processed/srtype_metrics_{year}.parquet`
  - One row per `SRType`: total_requests, closed_requests, closure_rate, median_days_to_close, on_time_rate, pct_resident_initiated
  - Covers ALL requests (not filtered to equity subset) — this is the full service delivery picture
  - `pct_resident_initiated`: fraction of requests that are Phone/API/Mail/Email — characterizes type nature (high % = demand-driven; low % = proactive/staff-driven)
  - Add `--stage srtype` to pipeline CLI; add step to Actions workflow

### App additions

- [ ] **P3-2: Headline KPI bar**
  - 4 metrics: total requests · citywide closure rate · citywide median days to close · citywide on-time rate
  - Each shows current year value + YoY delta badge (↑/↓ vs. prior year) when prior year parquet exists
  - Derived by aggregating the existing `{geo_key}_metrics_{year}.parquet` — no new pipeline output needed

- [ ] **P3-3: City-level time series**
  - Line chart below the KPI bar: x = year (all available years), y = citywide value of the **selected metric**
  - Reacts to the sidebar metric selector — same metric shown in map and equity tab
  - Citywide value per year: median of tract/CSA medians (consistent with how headline KPIs are computed)
  - Plotted as a single line with markers; year range auto-expands as more historical data is added

- [ ] **P3-4: SRType volume chart**
  - Horizontal bar chart of total requests by SRType, sorted descending by volume
  - Bars colored by `pct_resident_initiated` (continuous scale: gray = proactive/staff-driven → blue = fully resident-initiated)
  - Contextualizes which types dominate volume and whether they are demand-driven or operational
  - Data source: `srtype_metrics_{year}.parquet`

- [ ] **P3-5: SRType performance table**
  - Sortable `st.dataframe` of all SRTypes with columns: SRType · requests · closure rate · median days to close · on-time rate · % resident-initiated
  - Default sort: total requests descending
  - Formatted: rates as %, days as decimal; color-coded cells for closure rate and on-time rate (green/amber/red relative to citywide values)
  - Data source: `srtype_metrics_{year}.parquet`

---

## Phase 4 — SRType-Stratified Equity Analysis *(Release N+2)*

**Goal**: answer "is service delivery equitable when you account for what's being requested?". The key insight motivating this phase: aggregate equity scores can be misleading because neighborhoods differ in their mix of request types, and different types have structurally different resolution times. A neighborhood that submits many fast-closing requests will look well-served in aggregate even if slower types are handled inequitably there.

### Conceptual framing
Two equity questions at different levels:
1. **Within-type equity**: for a given SRType (e.g. "Pothole Repair"), do majority-Black tracts wait longer than majority-White tracts? This is the cleanest equity signal — it controls for type mix differences.
2. **Type-mix equity**: are certain high-demand types (bulk trash, rodent control) disproportionately concentrated in lower-income or majority-Black neighborhoods, and are those types systematically slower? This is a structural question about service design, not just delivery.

### Pipeline additions

- [ ] **P4-1: Per-(SRType, tract) aggregate table**
  - New pipeline output: `data/processed/tract_srtype_metrics_{year}.parquet`
  - One row per `(tract_geoid, sr_type)`: same equity metrics as `tract_metrics` but scoped to one type
  - Only produces rows for (tract, type) combinations with ≥ 10 requests (suppress sparse cells)
  - Equity subset filter still applies (resident-initiated, non-ECC, geocoded)

- [ ] **P4-2: Within-type IQR overlap scores**
  - For each SRType with sufficient coverage (≥ 20 majority-Black tracts AND ≥ 20 majority-White tracts with data), compute race-based and income-based IQR overlap scores
  - Output: `data/processed/srtype_equity_{year}.parquet` — one row per SRType with overlap scores for each metric
  - Ranks SRTypes from most to least equitable; surfaces which types drive aggregate disparity

### App additions

- [ ] **P4-3: SRType equity ranking panel**
  - Table or dot-plot of all SRTypes ranked by within-type IQR overlap score for the selected metric and demographic dimension (race or income)
  - Color-coded by score band (green/amber/red)
  - Click a row to see the full distribution comparison for that type (same box+strip chart as the aggregate equity panel)
  - Answers: "which services are delivered most inequitably?"

- [ ] **P4-4: Adjusted city equity score**
  - A single composite equity score for the city that controls for service type mix
  - Computed as the volume-weighted mean of within-type overlap scores across all covered SRTypes
  - More defensible than the aggregate score for policy and press use
  - Show alongside the aggregate overlap score so both are visible; explain the difference in a tooltip

- [ ] **P4-5: Historical data ingest (2016–2022)** *(blocked on TD-1)*
  - Add `fetch_year_socrata()` or equivalent once pre-2023 source is confirmed
  - Route `fetch_year()` by year: ArcGIS for 2023+, Socrata for pre-2023
  - Validate field name consistency; run pipeline for each historical year
  - Payoff: 9-year trend chart gives a statistically meaningful equity trajectory

- [ ] **P4-6: BNIA Vital Signs direct integration for CSA demographics**
  - Replace population-weighted rollup of ACS tract data with authoritative BNIA CSA indicators
  - Fetch `pct_nhblk`, `pct_nhwht`, `mhhi` from BNIA Vital Signs ArcGIS Hub
  - Compare against ACS rollup to validate; use as primary for CSA-level analysis

- [ ] **P4-7: Regression panel**
  - OLS: `log(days_to_close)` ~ pct_black + median_income + SRType FE + month FE
  - Displays race and income coefficients with 95% CI
  - Defensible claim about whether disparity is income-driven, race-driven, or structural

---
  - 1-page `docs/executive_summary.md` (or PDF via nbconvert)
  - Key findings with inline map thumbnail references
  - Audience: Mayor's Office, City Council, CDO

---



---

## Pending Items

| Question / Gap | Status |
|---|---|
| Duplicate `SRRecordID`s across years? | Still pending — need cross-year dedup check |
| 2025 `requests_per_1k` missing (Census API key not set at run time) | Fix via P1-6 re-run |
| 2016–2022 historical data | Fixed — switched to `311_Customer_Service_Requests_Yearly` FeatureServer (layer per year); runs validated |

---

## To-Do — Investigation Required

- [x] **TD-1: Locate pre-2023 historical 311 data**
  - Resolved: `311_Customer_Service_Requests_Yearly/FeatureServer/{layer}` service confirmed, layer 0=2016 through 6=2022
  - Schema compatible with annual service; Lat/Lon coercion added for string fields in historical layers
  - 2016–2022 endpoints live in `ENDPOINTS` dict; workflow year choices updated to include all years

- [ ] **TD-2: Manual validation of IQR overlap scores and demographic calculations**
  - Spot-check `overlap_score()` against hand-calculated values for at least two metric × year × geo-level combinations
  - Verify demographic classification thresholds: confirm majority-Black (>50%) and majority-White (>50%) counts are plausible given Baltimore's demographic makeup (~63% Black citywide)
  - Confirm `pct_black`/`pct_white` values in `tract_demographics.csv` are in expected range (0–1); check for tracts with unexpected nulls
  - Validate CSA rollup: pick 2–3 CSAs and manually re-aggregate from tract data to confirm weighted race % and income match `csa_demographics.csv`
  - Cross-check `median_income` values against published ACS tables for a sample of tracts (e.g. Roland Park should be high, Sandtown-Winchester low)
  - Verify trend chart direction is interpretable: rising overlap = narrowing disparity (confirm with a manually computed year-pair comparison)

---

*Last updated: May 2026. Mark items `[x]` when done.*
