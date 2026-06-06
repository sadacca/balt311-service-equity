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

- [x] **P1-6: Re-run pipeline with Census API key** — `requests_per_1k` now populated for all years via backfill workflow (P3-6).

- [x] **P1-7: Historical data 2016–2022** — switched to `311_Customer_Service_Requests_Yearly/FeatureServer/{layer}` (layer 0=2016 through 6=2022). Lat/Lon coercion added for string fields in historical layers. All years ingested and processed via backfill workflow. See TD-1.

---

## Phase 2 — App MVP

- [x] **P2-1: Mapbox token** — obtained, stored in Streamlit Cloud Secrets. `.streamlit/secrets.toml.example` committed; actual token never in repo.

- [x] **P2-2: App deployed** — live at https://balt311equity.streamlit.app/. Year, geo level, SRType, metric selectors all working.

- [x] **P2-3: SRType filter** — sidebar multiselect filters equity tab map; Operations tab uses independent SRType selection via table click.

- [x] **P2-4: On-time rate metric** — `is_on_time`, `due_date_gap_days` computed in `metrics.py`; `on_time_rate` in `aggregate_tract()` and `rollup_to_csa()`.

- [x] **P2-5: Color scale** — diverging RdBu_r centered on citywide median implemented in `map_view.py`.

- [x] **P2-6: Streamlit Community Cloud deployment** — auto-redeploys on push to main.

---

## Phase 2b — Demographic Equity Summaries + Multi-Year Foundation

- [x] **P2b-1: Fetch tract-level race and income from ACS** — `stage_demographics()` in `scripts/pipeline.py`. Fetches ACS 2023 5-year variables B02001 (race) and B19013 (income). Output: `tract_demographics.csv` with geoid, pct_black, pct_white, median_income.

- [x] **P2b-2: Roll up demographics to CSA level** — `rollup_demographics_to_csa()` in `src/balt311/metrics.py`. Population-weighted mean of tract values. Output: `csa_demographics.csv`.

- [x] **P2b-3: Demographic files committed** — both CSVs in `data/processed/`. Pipeline skips regeneration if both files already exist.

- [x] **P2b-4: `app/components/equity_distributions.py`** — box-and-strip charts for race and income group comparisons. Uses Mann-Whitney probability-of-superiority overlap score (see note). Score thresholds: >0.7 → "not bad", >0.4 → "could be better", <0.4 → "needs review".

- [x] **P2b-5: Wire into `app/app.py`** — demographics loaded and passed to equity distributions; soft-fails with caption if CSV absent.

- [x] **P2b-6: Equity trend chart** — `app/components/equity_trend.py`. Year-over-year overlap score line chart for each metric; one chart per demographic dimension (race / income). Shared `overlap_score()` in `app/components/utils.py`.

  **Note on overlap score implementation**: Final implementation uses Mann-Whitney probability of superiority (`1 - 2 * |P(A>B) - 0.5|`) rather than IQR band overlap as originally specified. More sensitive to tail differences and systematic shifts when medians are close. References in this document to "IQR overlap" should be read as "Mann-Whitney overlap score."

---

## Phase 3 — Operations Tab

- [x] **P3-0: Tab restructure** — `st.tabs(["Operations", "Equity"])` in `app.py`. Year selector inline above tabs as horizontal radio (`st.radio`). Sidebar redesigned as dashboard overview in P3-14; all filters moved inline.

- [x] **P3-1: Per-SRType aggregate table** — `srtype_metrics_{year}.parquet` with total_requests, closed_requests, closure_rate, median_days_to_close, on_time_rate, pct_resident_initiated. `--stage srtype` in pipeline CLI; step added to Actions `process` job.

- [x] **P3-2: Headline KPI bar** — 4 metrics (requests, median days to close, closure rate, on-time rate) with year-over-year delta badges. All deltas shown as neutral color (`delta_color="off"`) — direction of change is context-dependent.

- [x] **P3-3: City-level time series** — interactive line chart; selected year highlighted red. Clicking a point updates the year selector via `st.session_state`. `displayModeBar: False` on all non-map charts.

- [x] **P3-4: SRType breakdown** — horizontal bar chart approach replaced by selectable performance table (P3-5). Category pills (`st.pills`) above the table filter by hyphen-prefix category (SW-, HCD-, TRS-, etc.). Clicking any row selects that type for detail charts and map.

- [x] **P3-5: SRType performance table** — `st.dataframe(on_select="rerun", selection_mode="single-row")`. Columns: Type, Requests, Closure rate, Median days, On-time rate, % Resident. Row click triggers year-over-year detail charts below.

- [x] **P3-6: Year-over-year SRType detail charts** — two side-by-side bar charts for selected type: total requests by year and median days to close by year. Selected year highlighted red. Driven by table row selection.

- [x] **P3-7: Geographic distribution map in Operations** — choropleth of request count by geography. Filtered to selected SRType if a table row is selected. Loaded from `{geo_key}_srtype_metrics_{year}.parquet`; cells with fewer than 5 requests suppressed in UI (`_MIN_GEO_SRTYPE_N = 5`) without requiring pipeline rerun.

- [x] **P3-8: Scope banner** *(superseded by P3-11/P3-12)* — originally a 3-column tile row showing All/Equity subset/Excluded counts. Replaced by: (a) KPI bar sourced from all-requests data, (b) citizen-initiated sub-row inside each KPI tile. The scope-banner component remains in code for potential reuse by the equity/source-analysis tabs.

- [x] **P3-9: Backfill workflow** — `.github/workflows/backfill.yml`. Sequential loop over configurable year list; commits after each year; 180s default pause between ingests to limit ESRI server load; skips year on ingest failure rather than aborting; cleans raw/interim between years to keep runner disk use flat.

- [x] **P3-10: Geo × SRType metrics aggregation** — `tract_srtype_metrics_{year}.parquet` and `csa_srtype_metrics_{year}.parquet`. Columns: geoid, SRType, total_requests, closed_requests, closure_rate, median_days_to_close. Replaces `tract_srtype_totals_{year}` (total_requests only). `_geo_srtype_agg()` helper in pipeline avoids code duplication between tract and CSA.

- [x] **P3-11: KPI bar all-requests data source** — ops tab KPI bar now reads from `srtype_metrics_{year}.parquet` (all requests) via `_build_timeseries()`. Previously read equity-filtered subset. Metric label updated from "Requests analyzed" → "Requests received". Scope banner removed; its information is now implicit in the KPI bar.

- [x] **P3-12: Citizen-initiated sub-row in KPI bar** — each KPI tile shows a small gray caption immediately below with the citizen-initiated (equity subset) equivalent: count, days, closure rate, on-time rate. Sourced from a new `_build_equity_citywide_ts()` helper that aggregates `tract_metrics_*.parquet` files into population-weighted citywide totals. Caption is written into the same `st.columns` slot as the metric for correct mobile stacking.

- [x] **P3-13: Dual-line time series** — time series chart shows two traces: solid blue "All requests" from `srtype_metrics` and dashed orange "Citizen-initiated" from `_build_equity_citywide_ts()`. Legend appears above chart when citizen-initiated data is available. Both traces support click-to-navigate year.

- [x] **P3-14: Sidebar redesigned as dashboard overview** — all sidebar filter controls (geo level, SRType multiselect, metric selectbox) removed. Sidebar now contains a static description: dashboard purpose, what each tab shows, data sources, note about methodology docs. Controls moved inline (see P3-15).

- [x] **P3-15: Inline controls in each tab** — geo toggle and metric selector moved out of sidebar into contextual positions. Ops tab: compact horizontal radio for metric selection above the time series; "View as: Census Tract / CSA" radio above the geographic map. Equity tab: three inline columns above the choropleth — geo toggle, metric selectbox, SRType filter (top-request-type multiselect). Geo toggles sync via `st.session_state["geo_level"]` and trigger `st.rerun()` on change.

- [x] **P3-16: Category pills — full-name legend and TEST exclusion** — `_CATEGORY_NAMES` dict maps department prefix abbreviations to full names (SW = Solid Waste, HCD = Housing & Community Development, TRS = Transportation, etc.). A `st.caption` row below the pills displays the legend for all visible categories. "TEST" prefix excluded from pills via `_EXCLUDED_CATEGORIES` constant.

- [x] **P3-17: Ops geographic map sequential colorscale** — ops geographic distribution map uses sequential Blues scale from 0 → max (was diverging RdBu_r centered at median). `build_choropleth()` gains `sequential: bool = False` flag. Equity tab choropleth unchanged — still diverging, centered at citywide median.

---

## Phase 4 — SRType-Stratified Equity Analysis *(next release)*

**Goal**: answer "is service delivery equitable when you account for what's being requested?". The key insight: aggregate equity scores can be misleading because neighborhoods differ in their mix of request types, and different types have structurally different resolution times.

> **Implementation note**: the unchecked app additions below (P4-1b through P4-6) are detailed and staged as concrete tab builds in **Phase 4d**. Build them there, not as standalone items — this list stays as the conceptual record.

### Conceptual framing
Two equity questions at different levels:
1. **Within-type equity**: for a given SRType (e.g. "Pothole Repair"), do majority-Black tracts wait longer than majority-White tracts? This is the cleanest equity signal — it controls for type mix differences.
2. **Type-mix equity**: are certain high-demand types (bulk trash, rodent control) disproportionately concentrated in lower-income or majority-Black neighborhoods, and are those types systematically slower? This is a structural question about service design, not just delivery.

### Pipeline additions

- [x] **P4-1a: Geo × SRType metrics pipeline** — `tract_srtype_metrics_{year}.parquet` and `csa_srtype_metrics_{year}.parquet` produced by `stage_srtype`. Contains total_requests, closed_requests, closure_rate, median_days_to_close. *(Done in P3-10; listed here because it unblocks P4-1b.)*

- [ ] **P4-1b: Within-type equity scoring** — for each (SRType, geo) with sufficient coverage, compute race-based and income-based Mann-Whitney overlap scores using `tract_srtype_metrics` joined to demographics. Minimum threshold: ≥5 requests per cell (UI-enforced) and ≥10 tracts per demographic group (for meaningful score). Output: `srtype_equity_{year}.parquet` — one row per SRType with overlap scores for each metric.

- [ ] **P4-2: Adjusted city equity score** — volume-weighted mean of within-type overlap scores across all covered SRTypes. More defensible than aggregate score for policy use.

### App additions

- [ ] **P4-3: SRType equity ranking panel** — table or dot-plot of SRTypes ranked by within-type overlap score. Color-coded by score band. Click a row to see the full distribution comparison for that type. Answers: "which services are delivered most inequitably?"

- [ ] **P4-4: Adjusted vs. aggregate equity score display** — show both scores with explanation of the difference.

- [ ] **P4-5: BNIA Vital Signs direct integration for CSA demographics** — replace population-weighted ACS rollup with authoritative BNIA CSA indicators (`pct_nhblk`, `pct_nhwht`, `mhhi`). Compare against ACS rollup to validate.

- [ ] **P4-6: Regression panel** — OLS: `log(days_to_close)` ~ pct_black + median_income + SRType FE + month FE. Displays race and income coefficients with 95% CI.

---

## Phase 4c — Request Source Analysis Tab *(medium-term)*

**Goal**: a dedicated tab sitting between Operations and Equity that answers "what is actually coming in through 311, and from whom?" before asking how well it's being handled. Currently the Operations tab shows the equity-filtered subset (resident-initiated, non-ECC, geocoded) and the SRType table covers all requests — this incongruity is intentional but not explained. A separate tab makes the split explicit and gives it analytical depth.

**Value for ops managers and citywide officials**: understanding the composition of 311 demand — how much is resident-driven vs. city-proactive, which service types skew one way, whether that mix is changing year over year — is prerequisite context for interpreting performance metrics.

### App additions

- [ ] **P4c-1: Request source volume split** — stacked bar or area chart by year showing citizen-initiated (Phone/API/Mail/Email) vs. system/proactive (System/Internal) vs. excluded (ECC-prefix) volumes. Makes the scope-banner math explicit in a visual and historical context.

- [ ] **P4c-2: Source mix by SRType** — horizontal bar chart of `pct_resident_initiated` by SRType, sorted. Answers: which service types are purely reactive (resident demand) vs. proactive (staff-driven inspections)? Contextualises why some types have systematically shorter close times.

- [ ] **P4c-3: Source mix by geography** — choropleth of `pct_resident_initiated` by tract/CSA. Are certain neighborhoods driving more proactive city activity vs. resident-reported issues?

- [ ] **P4c-4: Year-over-year source trend** — for each major source category, how has volume trended across 2016–2025? Are residents using 311 more or less over time? Is proactive activity growing?

### Pipeline additions

- None required — `srtype_metrics_{year}.parquet` already includes `pct_resident_initiated`; `tract_srtype_metrics` can support geographic source mix if `is_resident` is passed through (currently not in the geo-level aggregation — minor pipeline addition needed).

---

## Phase 4b — Area Analysis Tab *(candidate for next release)*

**Goal**: a "middle view" between Operations (city-wide) and Equity (demographic disparity) aimed at area managers and district supervisors. The core question: are there geographies that look similar — in demographics, request mix, or both — but produce meaningfully different service outcomes? Gives managers a peer-comparison lens to self-check their area without needing to interpret equity scores.

> **Implementation note**: P4b-2's "peer similarity index" is reframed and detailed in **Phase 4d** as a visual PCA embedding (Tab 3 — Area Embedding) rather than a nearest-neighbor list — it answers the same question (which areas look alike?) but lets the user see the whole structure (continuous vs. clustered) at once, in both service-usage space and demographic space, and names the clusters into reusable peer groups. P4b-1, P4b-3 through P4b-5 remain open future work once the embedding view validates which peer groupings are meaningful.

### Concept

Two geographies are "peers" if they share similar inputs (demographic profile, SRType volume mix) but may differ on outputs (closure rate, median days to close). Surfacing outliers within peer groups is more actionable than a citywide ranking, because it controls for structural differences in what's being requested and by whom.

### App additions

- [ ] **P4b-1: Area overview panel** — for any selected tract or CSA, a summary card showing all key metrics alongside citywide and peer-group benchmarks. Replaces the current summary panel's raw numbers with contextualised comparisons.

- [ ] **P4b-2: Peer similarity index** — compute a simple distance metric across geographies using: demographic profile (pct_black, pct_white, median_income) + request mix (SRType share vector). Identify the N closest peers (N=5 default) for any selected geography. Computed in-app from existing processed files — no new pipeline output required for an initial version.

- [ ] **P4b-3: Peer comparison chart** — for a selected area and its peers, show side-by-side bar or dot-plot of each outcome metric. Highlight the selected area. Helps a manager answer: "areas like mine are getting X closure rate — why am I at Y?"

- [ ] **P4b-4: Outcome outlier map** — choropleth of residual between observed outcome and peer-group expected outcome. Areas that over- or under-perform relative to similar peers show as diverging colors. This is more signal-rich than a raw metric map for identifying where operational intervention is warranted.

- [ ] **P4b-5: SRType mix view** — bar chart of the top request types for the selected geography vs. its peer group. Helps distinguish "we get different requests" from "we handle the same requests worse."

### Dependencies

- Requires demographics CSV and geo×SRType metrics files (both available).
- Peer similarity computation is O(n²) over geographies — fine for ~200 tracts, trivial for ~55 CSAs. No pipeline changes needed for MVP.
- Peer count N and weighting of demographic vs. request-mix dimensions should be tunable via UI sliders or sidebar controls, not hardcoded.

---

## Phase 4d — Six-Tab Narrative Arc: Operations → Category → Area Embedding → Equity → Category Equity → Mix-Adjusted Equity *(next release)*

**Goal**: give every audience a single, walkable path from "how is the city doing operationally" to "is it equitable, and why" — no conceptual jumps between tabs. Confirmed final tab order and the story each step adds (2026-06-06):

| # | Tab | Status | What it adds to the story |
|---|---|---|---|
| 1 | **Operations** | existing | High-level operational view: citywide volume, performance, trends, geography. Always first. |
| 2 | **Services** *(in-app label; planning name "Service Category Explorer")* | ✅ live | Detailed *operational* view: how do individual service categories perform, how do they differ from one another and across the years in this dataset — **with no race, income, or equity framing at all**. The pure manager's drill-down; the missing rung between citywide Operations and the equity-flavored tabs that follow. |
| 3 | **Area Embedding** *(aka "Service Category Usage by Geographic Area")* | **NEW — build here** | The bridge: where do areas cluster — by what they request, and by who lives there — in two complementary, mutually-colorable spaces, named into reusable peer groups. Pivots the story from "what's happening" to "does it relate to who, and where." |
| 4 | **Equity** | existing | High-level *equity* view: citywide race/income comparisons by metric, with year-over-year trend. |
| 5 | **Service Equity** *(in-app label; planning name "Service Category Equity Explorer", renamed — see note)* | ✅ live | Detailed equity view: does the citywide equity picture in (4) hold up — or differ — among and within individual service categories? **Confirmed yes** — see redesign note below: scored within categories and within individual subtypes, equity scores run substantially higher than the citywide-pooled aggregate, direct evidence of a usage-mix effect (though some disparity persists even at that finer grain). |
| 6 | **Equity Adjusted for Service Mix** | **NEW — build here** | The most nuanced equity view: are the gaps surfaced in (4)/(5) explained by *which* services an area requests (some structurally slower to resolve), or by *how the same service* is delivered to different areas? Stratified scores + regression — the payoff the whole arc has been building to. |

> **Naming note**: an earlier draft of this phase sketched a single "Service Category Explorer" that combined a citywide ranking with a within-category race/income comparison. That tab's content is fundamentally an *equity* tool — it always asks "...and does this differ by race or income?" — so it was **renamed to "Service Category Equity Explorer" (Tab 5)**, unchanged in scope (its task list below is the original P4d-1 through P4d-4, renumbered). **Tab 2, also called "Service Category Explorer," is a different and simpler tool**: pure operational comparison among and within categories — usage rates, time to close, trend across years — with **zero** demographic content. The two stayed strictly separate in implementation (different files, different framing, no shared "equity score" UI in Tab 2). Both have since shipped with shorter in-app display titles — **"Services"** and **"Service Equity"** — to match the dashboard's terser tab-label convention; this document keeps the longer planning names as the conceptual record, with the live display name noted alongside.

This phase consolidates and gives concrete, ordered shape to P4-1b, P4-2, P4-3, P4-4, P4-6, and the Phase 4b peer-similarity concept (P4b-2). Those items stay listed in their original phases as the conceptual record; build them here as part of these tabs, not separately.

### Stage 0 — Data generation *(✅ already satisfied — verified 2026-06-06)*

> **Status update**: this was flagged as a blocker because `data/processed/` in this working copy only had 2024/2025 base metrics. That was a sync gap, not a real gap — `main` already has the full backfill (`pipeline: backfill processed data for 2016`–`2025`, PRs #33–37) including `srtype_metrics_*`, `tract/csa_srtype_metrics_*`, and both demographics CSVs for **all years 2016–2025**. Merged `main` into this branch (commit `289e002`) and confirmed locally: `srtype_metrics_2024` (295 SRTypes × 7 cols), `tract_srtype_metrics_2024` (29,719 rows × 6 cols: `geoid, SRType, total_requests, closed_requests, closure_rate, median_days_to_close`), `tract_demographics.csv` (199 tracts × 7 cols incl. `pct_black, pct_white, median_income`). All ten years present for both tract and CSA grain. **Tabs 1–3 can be built directly against committed data — no pipeline run needed.**

- [x] **P4d-0a: Geo×SRType + citywide SRType metrics for all years** — `srtype_metrics_{2016..2025}.parquet`, `tract_srtype_metrics_{2016..2025}.parquet`, `csa_srtype_metrics_{2016..2025}.parquet` all committed on `main` and now merged into this branch.
- [x] **P4d-0b: Demographics CSVs** — `tract_demographics.csv`, `csa_demographics.csv` committed on `main` and merged into this branch.
- [x] **P4d-0c: Verify outputs** — schemas confirmed as above; `total_requests` cross-check against Operations KPI figures and the TD-2 demographic spot-checks remain good due-diligence before relying on these numbers in the new tabs, but are no longer a blocker to starting the build.
- [ ] **P4d-0d: Graceful degradation, still worth keeping** — even though all years are now present, keep the `@st.cache_data` loaders returning `None`/empty `DataFrame` on missing files (mirror `load_demographics` in `app.py`, `_load_geo_srtype_metrics` in `operations_panel.py`) with an `st.info()` pointing at the generating pipeline command — protects against future years being added to `tract_metrics_*` before their `srtype`/demographics counterparts land.

### Tab 2 — Service Category Explorer, operations-only (`app/components/category_explorer.py`)

*The "truer" category explorer — pure operational drill-down on service types, **no race/income/equity content**. Sits directly after Operations as the detailed-operations rung of the arc; sets up Tab 5 (the equity-flavored sibling) by establishing the categories and baseline performance picture first, cleanly, before any demographic lens is introduced.*

- [x] **P4d-1: Shared SRType scaffolding** — category pills, department-name legend, cached SRType-history loaders shared between the Operations tab and this one. *Done — `_CATEGORY_NAMES`, `_EXCLUDED_CATEGORIES`, `extract_categories()`, `category_pills()`, `load_srtype_history()`, `load_geo_srtype_metrics()`, `MIN_GEO_SRTYPE_N` were promoted out of `operations_panel.py` into a new shared module `app/components/srtype_shared.py` — both `operations_panel.py` and `category_explorer.py` import from there.*
- [x] **P4d-2: Among-category comparison** — three categories-side-by-side rankings so differences *among* categories are visible at a glance on usage, service rate, and time-to-close — e.g. "rodent control runs 3x longer than streetlight repair." No demographic split. *Done — `_category_aggregates()` rolls SRType rows up to department-prefix categories for the selected year (volume summed, rates volume-weighted via `_wmean()`); `_ranked_bar_fig()` renders each as a horizontal bar ranking — three panels side by side: **Usage** (total requests), **Service rate** (closure rate), **Speed** (median days to close).*
- [x] **P4d-3: Category selection → composite year-over-year + within-category subtype breakdown** — refactored away from the table/bubble-chart/choropleth drill-down toward a fully time-series-driven design per direct user redirect ("there's no actual new content aside from the scatter plot… let's fully refactor this page to present wholly new content from the previous tab"). Selecting a category (via `category_pills()`) now shows, directly below the selector: (a) a composite pair of year-over-year line graphs — category-average total requests and median days to close, selected year highlighted in red against blue (`_yearly_aggregate()` + `_line_fig()`, mirroring the established `_timeseries_fig` convention) — followed by (b) three within-category multi-line time series, one each for request volume, closure rate, and median days to close, with every subcategory (SRType) plotted across years. Categories with many subtypes (e.g. Solid Waste's 63) plot the `_TOP_SUBTYPES_N = 10` highest-volume subtypes individually (`_short_label()` strips the redundant prefix for legend display) and fold the remainder into one volume-weighted "All other {cat} types (N)" dotted-gray aggregate line (`_subtype_multiline_fig()`). The geographic choropleth was removed entirely from this tab — geography lives in Operations and the future Area Embedding tab; this tab now shows **zero** map content, keeping it wholly distinct from both its own v1 and from Operations. *Done.*
- [x] **P4d-4: Wire into `app.py` as the second tab** — insert this tab immediately after `"Operations"` in `st.tabs([...])`, displayed with the shorter in-app title `"Services"` (see naming note above). *Done — `render_category_explorer()` wired in at `app.py` with a simplified `(data_dir, year)` signature (no `geojson`/`featureidkey`/`mapbox_token`/`demographics` — the removal of all geographic and equity content from this tab is now explicit in the function signature itself); sidebar tab description added; verified via `streamlit.testing.v1.AppTest` (renders all three tabs with no exceptions; among-category panels, category-selection composite lines, and within-category subtype breakdowns all render correctly for 2025 data, including the top-N + "Other" folding for high-cardinality categories like SW).*

### Tab 3 — Area Embedding, aka "Service Category Usage by Geographic Area" (`app/components/area_embedding.py`)

*Reframes Phase 4b's "peer similarity index" (P4b-2) as a visual embedding the user can read at a glance — continuous vs. clustered — rather than a nearest-neighbor list, and pairs it with its inverse so both "what areas use" and "who areas are" can be explored side by side.*

Two complementary embeddings, switchable by the user, over the **same** set of geographies:

> **Refinement note (2026-06-06)**: a planning discussion sharpened the usage-space embedding considerably beyond the original "one point per geography, per-year" sketch. Three decisions reshape P4d-5 below: (1) build feature matrices at **both** the high-level-category and top-100-individual-SRType grain, toggle between them — the choice materially changes whether peer groups read as "similar departments" or "similar specific services"; (2) support **both** geographic grains via the shared `geo_level` toggle, matching every other tab's convention; (3) fit PCA **once**, on data pooled across *all* years, so every `(geo, year)` point lives in one stable, common coordinate system — re-fitting per year would let the axes themselves drift, making real movement and axis rotation visually indistinguishable. An animated year slider then makes that pooled space's trajectories — "how do tracts and CSAs covary and move over time?" — directly readable. P4d-6's demographic-space embedding stays scoped to the existing single-snapshot ACS profile for now, with an expanded variable set (P4d-6a); a true year-over-year demographic-trajectory companion awaits Census PDB ingestion, deliberately tracked as a separate, non-blocking follow-on (P4d-6b) since PDB ships at irregular multi-year vintages and needs its own alignment design.

- [x] **P4d-5: Pooled, common-space service-usage embedding** — built in `app/components/area_embedding.py` (`compute_usage_embedding`, `_usage_share_matrix`, `_clr`). Stacks a `(geoid, year)` × feature usage-share matrix from `load_geo_srtype_history` across all available years (`MIN_GEO_SRTYPE_N`-suppressed cells, `_MIN_GEO_YEAR_TOTAL = 50`-suppressed sparse geo-years), with a **feature-set toggle** between *high-level categories* (top 15 by mean share) and *top-100 individual SRTypes by pooled citywide volume* (top 30 by mean share). Empirical validation (throwaway scripts, since removed) showed raw row-normalized shares + `StandardScaler` explained only ~20-27% of variance in 2D — compositional (sum-to-1) data violates PCA's Euclidean assumptions — so the shipped methodology is **top-K-by-mean-share + centered-log-ratio (CLR) transform + `StandardScaler`**, raising variance explained to 29-49% with PC1 loadings landing on substantively meaningful categories (HCD, Traffic, Health, Transportation Maintenance) rather than noise. `StandardScaler` + `PCA(n_components=2)` is fit **once on the full pooled matrix** (`@st.cache_data def compute_usage_embedding`), so every `(geoid, year)` point shares one fixed coordinate system. Both geographic grains supported via the shared `geo_level` toggle — CSA outperforms tract at every setting (denser cells, less suppression-driven sparsity), confirming the CSA-first sequencing. **Validation gate passed and surfaced in-app**: an explicit "PC1 X% / PC2 Y% / Z% combined" caption reports the moderate-but-real variance captured, so a 2D read isn't over-trusted. *Done.*
- [x] **P4d-5b: Animated year-by-year trajectory view** — `plotly.express.scatter(..., animation_frame="year", animation_group="geoid")` steps through years in the common space (axis ranges fixed across frames so a stable area doesn't appear to jitter; opens on the dashboard's currently-selected year via a frame-swap + slider-position sync). Color-by is user-selectable: dominant usage category (categorical, from each row's largest CLR-space share) or a demographic dimension (race, income) when `demographics` is available. Answers: *are areas continuous or clustered in what they request, is that stable or shifting year to year, and do demographically similar areas move together or apart?* *Done.*
- [x] **P4d-6: Demographic-space embedding — the inverse view (single-snapshot, ACS 2023)** — `compute_demographic_embedding` + `_render_demographic_view` in `area_embedding.py`. A light PCA (`StandardScaler` + `PCA(2)`, since the input is low-dimensional — currently `pct_black`, `pct_white`, `median_income`) places each geography once (year-independent ACS 2023 snapshot, no animation), colored by user-selectable service-side measures from the *currently selected year*: predominant SRType (categorical), `requests_per_1k`, or `median_days_to_close`. With only 3 input features the first two components capture ~99% of the variance (89% PC1 + 10% PC2 at CSA grain) — reported via the same variance-explained caption convention as the usage view. Answers the inverse question: *do areas that look alike demographically also look alike in how they use and experience 311?* *Done — P4d-6a will broaden and sharpen the input feature set; the view already picks up new demographic columns automatically once they land.*
- [ ] **P4d-6a: Expand the demographic feature set** — `{tract,csa}_demographics.csv` today carries only `pct_black`, `pct_white`, `median_income`. Extend the ACS pull in `metrics.py`'s demographics stage to add: age-group shares, Hispanic/Latino ethnicity share (`pct_hispanic` — distinct from race in Census conventions; a tract can be majority-White *and* majority-Hispanic, so this isn't redundant with the existing race split), bachelor's-degree-or-higher attainment rate, and 1-2 more ACS variables (candidates: poverty rate, owner-occupied housing share, vehicle access — whichever rounds out a "who lives here and how" picture without overlapping what's already there). Year-independent, one-time pipeline change — same `--stage demographics` pattern, more columns; feeds both P4d-6's embedding (`_DEMO_FEATURE_COLS` in `area_embedding.py` already picks up any of these that land in the CSV with no further code change) and gives Tab 4/5's existing race/income split richer company. *Blocked in this environment — `CENSUS_API_KEY` isn't set here; the ACS fetch needs to run where the GitHub Actions secret is available (`update_data.yml` / `backfill.yml` runners).*
- [ ] **P4d-6b *(separate, non-blocking follow-on)*: Census PDB ingestion + year-over-year demographic trajectories** — Census Planning Database ships at irregular multi-year vintages, not a clean annual series like 311 data, so this needs its own design pass: a new pipeline stage to ingest PDB and align its vintages to the years the embedding covers (interpolation, or a documented "most recent vintage as of year X" rule), then the same pooled-common-space + animated-trajectory treatment as P4d-5/5b — but tracking demographic drift instead of service-usage drift. The natural payoff once both exist side by side: *"did this area's demographics shift before, after, or alongside its service-usage shift?"* — extending the embedding's covariance framing to both halves of the equity question.
- [x] **P4d-7: Shared view-switch and adaptive color-by controls** — a top-level `st.radio("View", ["Service usage", "Demographic profile"])` in `render_area_embedding` toggles between the two embeddings (geographic-unit toggle stays shared above both, synced two-way with `geo_level`); each view's color-by selector independently adapts — service-usage view offers dominant-category / demographic colors, demographic view offers predominant-SRType / requests-per-1k / median-days-to-close colors — so the two read as one connected exploration rather than two separate tools. *Done.*
- [ ] **P4d-7b: Cluster the embedding into named peer groups — the real payoff of building this view** — run a clustering algorithm (start with `sklearn.cluster.KMeans` or `AgglomerativeClustering`, k chosen via silhouette score or a user-facing slider) on the 2D embedding (or the pre-PCA feature matrix — try both, prefer whichever gives more stable, interpretable groups) in *both* spaces. With the pooled common space now in hand, there's a richer choice than before: cluster a single year's snapshot ("areas that look alike right now"), or cluster on *trajectories* — direction and magnitude of movement through the space — surfacing "areas moving the same way" as a distinct peer concept. Auto-generate a short descriptive label per cluster from its dominant features (e.g. "High solid-waste demand tracts" from top SRType shares alone, or "Majority-Black, mixed-income" from demographic skew) and let the user rename/accept labels. Persist the assignment as `geoid → peer_group` so it becomes a reusable categorical dimension exposed as a filter/group-by option elsewhere — mind the Tab 2 boundary, though: **clusters drawn from the service-usage space are purely operational** (no demographic input) and can safely flow into Services (Tab 2) and Operations alongside the existing category-pill pattern; **clusters drawn from the demographic space inherently carry a demographic framing** and belong with the equity-flavored tabs — Equity, Service Equity (Tab 5), and Equity Adjusted — alongside the existing top-SRType filter pattern there. This turns the embedding from a one-off visualization into the analytical backbone for "compare areas like mine" across the app — directly fulfilling Phase 4b's peer-comparison goal (P4b-1, P4b-3 through P4b-5) without a separate nearest-neighbor system.
- [ ] **P4d-8: Optional SRType×SRType correlation heatmap** — secondary panel (e.g. `np.corrcoef` on the usage matrix) showing which service categories tend to be requested together across geographies; show only when ≥5 SRTypes are present.
- [x] **P4d-9: Wire into `app.py` as the third tab + new dependency** — `"Areas"` inserted between `"Services"` and `"Equity"` in `st.tabs([...])` (and the sidebar's tab-by-tab description list); `scikit-learn>=1.3.0` added to `app/requirements.txt` (`PCA` + `StandardScaler` + clustering, all in the same package — no extra dependency needed for P4d-7b). Note `umap-learn` remains a future enhancement once the PCA structure is validated further — its `numba`/LLVM dependency makes it a much heavier install. *Done.*

### Tab 5 — Service Equity *(in-app label; planning name "Service Category Equity Explorer")* (`app/components/category_equity_explorer.py`)

*This is the tab originally sketched as "Service Category Explorer" — renamed (see naming note above) because its content is fundamentally about equity, not pure operations. Gives concrete shape to P4-3 (ranking panel) and is the first instance of "within-type equity" (P4-1b).*

> **Redesign note (2026-06-06)**: the original P4d-10→12 draft paired a citywide SRType ranking table with a within-category choropleth and a single-year race/income comparison. User review (echoed in the discussion that produced this redesign) flagged both the choropleth and the table as redundant — Operations already has an SRType-filterable geographic map (P3-7) and a full SRType performance table (P3-5), and Tab 2 already ranks categories operationally; a third map and table would repeat content rather than add equity *signal* (geography there is a proxy for demographics, not the thing itself). The redesign instead **mirrors Tab 2's among/within structure exactly**, swapping the ranked metric from operational (volume/speed/closure rate) to equity (Mann-Whitney overlap score), and — the genuine payoff — adds *equity scores broken down by category and subtype, through time*: a dimension that exists nowhere else in the app (the existing `equity_trend.py` shows only the citywide aggregate trend). No map, no flat ranking table; purely the time-series equity-score story. Old items P4d-10→12 are superseded by P4d-10a→12b below; P4d-13 (wiring) is unchanged in spirit, renumbered P4d-13.
>
> **Build complete + headline finding confirmed (2026-06-06)**: the redesign above shipped in full (see completed items below, PR #51) and was polished further per direct user follow-up — both category tabs got shorter in-app titles ("Services" / "Service Equity"), the Tab 5 baseline series was relabeled "All categories" (was "Citywide"), and the static preamble caption was replaced with a data-driven analysis paragraph (`compute_subtype_score_summary()` in `category_equity_explorer.py`) that states, for the selected year and metric, the citywide-pooled score vs. the average within-category score vs. the average within-subtype score. **The pattern these three numbers trace is the headline finding the whole arc was building toward**: scores rise substantially at each finer grain (e.g. 2025 closure-rate/race: 0.227 citywide → 0.752 within-category → 0.809 within-subtype) — the signature of a usage-mix effect, not a delivery-difference one. Disparity doesn't fully close at finer grain (within-type scores mostly land 0.75–0.86, not 1.0), so the citywide number still matters — it just needs Tab 5's view to interpret correctly. This finding is now surfaced in-app (Tab 5's analysis paragraph, a short Equity-tab intro caption, and the sidebar narrative) and in the README; it also **strengthens the case for Tab 6** (P4d-14 onward) — Tab 5 shows the usage-mix effect is real and substantial *informally*; Tab 6's stratified, volume-weighted score is the formal version of the same separation, with a regression panel as independent corroboration.

- [x] **P4d-10a: Per-category, per-year overlap-score computation** — new cached helper (e.g. `_category_equity_scores(tract_srtype, demographics, categories)`) that, for each (department-prefix category, year), rolls up that category's `tract_srtype_metrics` rows (after `_MIN_GEO_SRTYPE_N` suppression), joins to demographics, splits into majority-Black/White and above/below-median-income groups, and computes `overlap_score()` (reuse `utils.overlap_score`) for the chosen metric (default: median days to close). Mirrors the in-app aggregation pattern `equity_trend.py` already uses citywide — no new pipeline stage required. *(implements the (category × year) half of P4-1b)* *Done — `compute_category_equity_history()` and the shared `_dimension_scores()` helper.*
- [x] **P4d-10b: Among-category equity trend** — two multi-line charts (race, income — mirroring Tab 2's `_multi_category_line_fig` almost exactly, one line per top-N category, dotted vertical guide on the selected year, transparent horizontal legend), but plotting overlap **score** on a fixed `[0, 1]` axis with `equity_trend.py`'s green/amber/red threshold bands (`add_hrect`) drawn behind the lines instead of a log-scale operational metric. Answers: *"across the years in this dataset, which service categories have run the widest — or narrowest — race/income equity gaps, and has that ranking shifted?"* This is the direct equity-flavored counterpart to Tab 2's "How categories compare over time" panel — same chart language, different metric. *(implements P4-3 at the category grain, trended)* *Done — `_multi_category_score_fig()`, baseline series labeled "All categories".*
- [x] **P4d-11a: Category selection → that category's own equity-score trend** — selecting a category (via shared `category_pills()`) renders its race and income overlap-score trend lines (mirrors `equity_trend.py`'s `_trend_fig` — threshold bands, `[0,1]` axis — scoped to one category, selected year highlighted per `_line_fig` convention) with the **citywide trend overlaid as a dashed reference** (same "Citywide average" pattern Tab 2 uses in `_multi_category_line_fig`, reusing the citywide series `equity_trend._compute_trend` already produces). Answers: *"has the equity picture for this category been improving, worsening, or holding steady — and does it track or diverge from the citywide trend?"* *Done — `_category_score_trend_fig()`, reference line labeled "All categories".*
- [x] **P4d-11b: Per-subtype, per-year overlap-score computation** — extend the P4d-10a helper (or a sibling) to compute overlap scores at (SRType × year) grain for the subtypes within a selected category, with the same suppression/grouping logic. Expect meaningful `NaN` coverage here — sparse SRType×year×geo cells will routinely fall under the `overlap_score()` n≥3 threshold; surface this as "insufficient data" rather than blank gaps (reuse `score_label()`'s handling). *(implements the (SRType × year) half of P4-1b)* *Done — `compute_subtype_equity_history()`, plus `compute_subtype_score_summary()` for the year-level all-subtype average that powers the headline-finding paragraph.*
- [x] **P4d-12a: Within-category subtype equity breakdown over time** — multi-line time series of subtype-level overlap scores (race and income, two panels or a toggle), using the same top-N + "all other" folding convention as Tab 2's `_subtype_multiline_fig` (reuse `_TOP_SUBTYPES_N`, `_short_label()`). Answers: *"which specific service types inside this category drive its equity gap, and is any one of them getting better or worse over time?"* This is the tab's central payoff — the place where "does the citywide picture hold up within categories" gets a concrete, navigable answer. *Done — `_subtype_score_multiline_fig()`.*
- [x] **P4d-12b: Single-year within-type comparison detail (optional secondary view)** — for a subtype the user wants to inspect closely, an expandable `_comparison_fig()` box-and-strip pair (race, income) for the selected year — the same pattern `equity_distributions.py` uses citywide, scoped to one SRType. Keep this secondary/collapsed by default so the trend views (P4d-11a/12a) — the genuinely new content — stay the visual focus; this view mainly answers "show me the raw distributions behind that score" for a skeptical reader. *Done.*
- [x] **P4d-13: Wire into `app.py` as the fifth tab** — insert this tab immediately after `"Equity"`, displayed with the shorter in-app title `"Service Equity"` (see naming note above); pass through `demographics`, `DATA_DIR`, `geo_key`, `year`. No `geojson`/`featureidkey`/`MAPBOX_TOKEN` needed — like the redesigned Tab 2, this tab carries no map content (see redesign note above for why the choropleth was dropped). *Done — wired in as `render_category_equity_explorer(DATA_DIR, demographics, geo_key, year)`, displayed with the shorter in-app title **"Service Equity"**; verified via `streamlit.testing.v1.AppTest` with zero exceptions and zero `build_choropleth` references on the tab.*

> **Follow-up additions (post-launch, 2026-06-06)**: direct user review of the shipped tab prompted two further additions, both now live and documented in the README:
> - **"Where equity review is most warranted"** — a Race/Income-toggleable ranking of the worst-scoring *individual service types* citywide (eligibility-filtered on geo coverage, volume, and years of history, then ranked strictly by the selected dimension's score so the flagged set is guaranteed consistent with the histogram shown), paired with a distribution histogram and year-over-year trend lines. This is the concrete realization of **P4-3**'s "SRType equity ranking panel" concept, arriving here rather than in Tab 6 — `compute_concerning_subtypes()`, `_concern_distribution_fig()`.
> - **CSA as the app-wide default geographic unit** — changed `app.py`'s shared `geo_level` initial value from `"Census Tract"` to `"CSA"`; CSA carries less sparse-cell suppression, so its equity scores are a more reliable starting point across every tab, not just this one.
>
> A **bug fix** accompanied the ranking feature: the original version ranked types by a worse-of-{Race, Income} composite but displayed only the toggled dimension's score, so a type flagged for a low Race score could display a high Income value (and vice versa) — producing a histogram whose flagged bars clustered at high scores instead of low ones. Fixed by ranking strictly on the displayed dimension. A duplicated per-SRType Mann-Whitney pass across `compute_subtype_score_summary()` and `compute_concerning_subtypes()` was also factored into one shared cached helper, `_subtype_current_year_scores()`.

### Tab 6 — Equity Adjusted for Service Mix (`app/components/equity_adjusted.py`)

*The payoff tab — the arc has built from pure operations (Tab 2), through where-areas-cluster (Tab 3), through citywide equity (Tab 4) and category-level equity (Tab 5), to the final question this whole phase exists to answer. Gives concrete shape to P4-1b, P4-2, P4-3 (ranking by within-type score), P4-4, and P4-6.*

- [ ] **P4d-14: Stratified, volume-weighted "adjusted" equity score** — for each SRType with sufficient coverage, compute race- and income-based `overlap_score()` (reuse `utils.overlap_score`) within that type alone, then combine into a citywide "adjusted" score weighted by each type's request volume. Display side-by-side with the existing raw citywide score (`equity_distributions`/`equity_trend`), with a plain-language caption: a higher adjusted score than raw means part of the gap is mix-driven (disadvantaged areas request structurally slower-to-resolve services more often); a similar score means the gap is in how the *same* service gets delivered. *(implements P4-1b, P4-2, P4-4)*
- [ ] **P4d-15: SRType equity ranking panel** — dot-plot or table of SRTypes ranked by within-type overlap score, color-coded via `score_label()`; clicking a type shows its full distribution comparison (reuse `_comparison_fig`). Answers *"which services are delivered most inequitably?"* — directly comparable to Tab 5's per-type equity views and Tab 2's per-type operational ranking, closing the loop across the whole arc. *(implements P4-3)* *Build-order note: now sequenced after Tab 3, so this can optionally expose `peer_group` (once P4d-7b lands) as a group-by/filter dimension — "which services are delivered most inequitably, and does that ranking hold across peer groups or concentrate in a few?"*
- [ ] **P4d-16: Regression panel** — OLS `log(median_days_to_close) ~ pct_black + median_income + SRType FE + year FE` over the stacked tract×SRType×year panel (an aggregate-level approximation of the original record-level spec — label it clearly, since record-level data isn't in `data/processed/`). Show a coefficient table + 95% CI plot for `pct_black`/`median_income` plus an auto-generated plain-language interpretation. Add `statsmodels>=0.14.0` to `app/requirements.txt`. *(implements P4-6)*
- [ ] **P4d-17: Wire into `app.py` as the sixth (final) tab** — append `"Equity Adjusted for Service Mix"` after `"Service Equity"`; receive the active `metric_col`/`metric_label` from the Equity tab's selector so scores and regression stay aligned with what the user is already looking at.

### Suggested build order

Data is already in place (Stage 0 ✅). Build roughly in final tab order so each step's reuse opportunities are fresh when you reach the next:

**Tab 2 / Services** (P4d-1 → 4, pure operations — the simplest, and establishes shared category-table/pill scaffolding) → **Tab 5 / Service Equity** (P4d-10 → 13, directly extends Tab 2's table with the equity comparison pattern from `equity_distributions.py`) → **Tab 3 / Area Embedding** (P4d-5 → 9, independent of the category tabs once Stage 0 data is in hand; fit and validate the pooled common-space PCA — feature-set and geo-grain combinations — *then* layer on the animated trajectory view and cluster into peer groups at P4d-7b once the spaces are stable) → **Tab 6 / Equity Adjusted** (P4d-14 → 17, stratified scores generalize Tab 5's single-category comparison to every category and add the regression panel; reordered after Tab 3 so its ranking panel — P4d-15 — can reuse `peer_group` as a grouping dimension once P4d-7b lands, rather than being built before that dimension exists) → propagate `peer_group` back into Operations, Services, Service Equity, and Equity per the space-appropriate boundary noted at P4d-7b → wire the two remaining new tabs into `app.py` as one coordinated change to the tab list (in final order: Operations, Services, Area Embedding, Equity, Service Equity, Equity Adjusted for Service Mix), imports, and sidebar description.

> **Status (2026-06-06)**: Tabs 2 and 5 (✅ **Services** and **Service Equity**) have shipped — both verified via `AppTest`, merged to `main`. Remaining build order is now **Tab 3** (P4d-5 → 9) → **Tab 6** (P4d-14 → 17) — reordered ahead of Tab 6 per direct user direction, which also has the side benefit of letting Tab 6's ranking panel (P4d-15) reuse `peer_group` once it exists — → re-order/insert both into `app.py`'s `st.tabs([...])` and the sidebar.

### Verification

- **Stage 0**: ✅ done — confirmed all `srtype_metrics_*`, `tract/csa_srtype_metrics_*` (2016–2025), and both demographics CSVs are present and schema-correct after merging `main` (commit `289e002`); `total_requests` cross-check against the Operations KPI bar is still good practice before relying on these numbers in the new tabs.
- **Tab 2 / Services**: ✅ verified — among-category comparison and category drill-down render with no demographic content anywhere on the tab (spot-checked: zero matches for "Black"/"income"/"equity"); selecting a category shows its composite year-over-year lines (volume + days to close) and the within-category subtype multi-line breakdown (top-N + "all other" folding); **no choropleth or map content** — geography was deliberately removed from this tab per the P4d-3 redesign and now lives only in Operations (and, eventually, Area Embedding).
- **Tab 3**: ✅ verified via `AppTest` — both views (`Service usage` ↔ `Demographic profile`, via the `View` radio) render with no exceptions across every toggle combination (feature-set, color-by, geo-level). Usage view: animated scatter renders one point per `(geoid, year)`, variance-explained caption non-trivial (e.g. CSA/categories: 24% PC1 + 17% PC2; tract: 16% + 13%, confirming CSA's denser-cell advantage), color-by switches between dominant usage category and demographic dimensions, geo-level toggle re-renders with the right point count and re-fit space. Demographic view: one static point per geography (single ACS 2023 snapshot, no animation), color-by switches among predominant SRType / requests-per-1k / median-days-to-close, variance-explained caption reports ~99% combined (89% PC1 + 10% PC2 at CSA grain) reflecting the current 3-feature input — expected to redistribute once P4d-6a broadens the profile.
- **Tab 3 — peer groups (P4d-7b)**: cluster count is stable across re-runs (or seeded for reproducibility); auto-generated labels plausibly describe each cluster's dominant features; `peer_group` filter/group-by, once wired into Operations / Services / Service Equity / Equity (respecting the usage-space-vs-demographic-space boundary), narrows those views to the expected subset of geographies and updates their charts accordingly.
- **Tab 5 / Service Equity**: ✅ verified — among-category equity trend and category-selection trend (with "All categories" dashed reference line) render correctly on the fixed `[0,1]` axis with threshold bands; within-category subtype equity breakdown over time follows the same top-N + "all other" folding as Tab 2; sparse SRType×year cells show "insufficient data" gracefully (NaN score, `score_label()`) rather than blank gaps or errors; **no map and no flat ranking table anywhere on the tab** (confirmed zero `build_choropleth` references); the data-driven analysis paragraph (citywide vs. within-category vs. within-subtype averages) renders for both available metrics and matches the underlying numbers; the tab's framing and visual rhythm read as the equity-flavored mirror of Tab 2, not a repeat of Operations or the Equity tab.
- **Tab 6**: raw vs. adjusted scores both display and differ meaningfully; ranking dot-plot is color-coded by `score_label()` and is directly comparable to Tab 5's per-type views; regression table shows non-null `pct_black`/`median_income` coefficients with CIs; missing-file states show `st.info()`, not errors.
- **Whole arc**: read the six tabs in order start to finish — each one should follow naturally from the last with no "wait, why are we suddenly talking about X" moments. If a reader gets lost between any two adjacent tabs, that's a signal to add a one-line bridging caption (e.g. at the top of Tab 3: "The last tab showed how individual services perform — this one asks whether *areas* cluster in how they use those services, or in who lives there").

---

## Phase 5 — Cross-Municipality Comparison *(medium-term)*

**Goal**: place Baltimore's 311 performance and equity in context against peer cities. Two levels of depth.

### Level 1 — High-level ops benchmarking

- [ ] **P5-1: Identify peer municipalities** — select 4–6 cities with publicly accessible 311 open data and comparable population/density profiles (candidates: DC, Philadelphia, Chicago, NYC, Louisville). Confirm field compatibility (request type taxonomy, open/close timestamps, geocoding).

- [ ] **P5-2: Summary metrics compilation** — for each peer city, extract citywide median days to close, closure rate, and requests per 1k residents for the most recent comparable year. Initially manual/semi-manual; automate if field schemas are compatible enough. Output: `data/processed/peer_city_metrics.csv`.

- [ ] **P5-3: Benchmarking panel** — new section in Operations tab (or separate tab) showing Baltimore's headline KPIs alongside peer city values. Bar chart or dot plot; Baltimore highlighted. Contextualizes whether Baltimore's performance is strong, average, or lagging relative to comparable cities.

### Level 2 — Reference city deep dive

- [ ] **P5-4: Select 1–2 reference cities** — prioritize cities with: (a) similar demographic composition to Baltimore, (b) well-structured open 311 data, (c) known best or worst practice in equitable service delivery. Requires research; candidates TBD after Level 1 benchmarking.

- [ ] **P5-5: Reference city pipeline** — adapt `scripts/pipeline.py` to support a `--city` flag routing to each city's FeatureServer or Socrata endpoint. Field mapping layer required (each city uses different column names). Output: parallel `{city}_{geo_key}_metrics_{year}.parquet` files.

- [ ] **P5-6: Side-by-side equity comparison** — for each reference city: same equity distribution charts and Mann-Whitney scores as Baltimore. Allows direct comparison of disparity magnitude, not just headline performance.

---

## Phase 6 — Seasonality Tab *(Long-term)*

**Goal**: answer "when do requests spike, and does seasonal surge affect equitable delivery?"

**Goal**: answer "when do requests spike, and does seasonal surge affect equitable delivery?"

- [ ] **P6-1: Monthly pipeline aggregation** — new pipeline output `{geo_key}_srtype_monthly_{year}.parquet`: geo × SRType × month with total_requests, closure_rate, median_days_to_close. Larger files — implement only when a seasonality view is planned.
- [ ] **P6-2: Seasonality tab** — citywide and per-type monthly volume trends; seasonal peaks (bulk trash in spring, pothole in winter). Year-over-year overlay to distinguish seasonal pattern from year-level trend.
- [ ] **P6-3: Seasonal equity check** — does closure time worsen during peak months, and does the worsening fall disproportionately on lower-income neighborhoods?

---

## Pending Items

| Question / Gap | Status |
|---|---|
| Duplicate `SRRecordID`s across years? | Still pending — need cross-year dedup check |
| 2025 `requests_per_1k` missing (Census API key not set at run time) | Resolved via backfill rerun |
| 2016–2022 historical data | Resolved — see TD-1 and P1-7 |

---

## To-Do — Investigation Required

- [x] **TD-1: Locate pre-2023 historical 311 data**
  - Resolved: `311_Customer_Service_Requests_Yearly/FeatureServer/{layer}` service confirmed, layer 0=2016 through 6=2022
  - Schema compatible with annual service; Lat/Lon coercion added for string fields in historical layers
  - 2016–2022 endpoints live in `ENDPOINTS` dict; all years processed via backfill workflow

- [x] **TD-3: Personas and use-case review** — see `personas.md`
  - Five personas defined: Interested Citizen, Citizen Journalist, Citywide Official, Local Official (council), Department Ops Manager
  - Summary matrix maps each phase to persona value
  - Key finding: Phase 4b (Area Analysis) is highest-value next step for council and ops personas; Phase 5 (cross-municipal) unlocks journalist and citywide official use cases; citizen persona is underserved and needs a dedicated accessibility pass before public launch
  - Revisit after actual stakeholder interviews

- [ ] **TD-4: Cross-year duplicate SRRecordID check**
  - Load all processed interim parquets and check for SRRecordIDs appearing in multiple years
  - Determine whether duplicates are true re-submissions, amended records, or data artifacts
  - Decide whether cross-year deduplication is needed and at what stage

- [ ] **TD-2: Manual validation of Mann-Whitney overlap scores and demographic calculations**
  - Spot-check `overlap_score()` against hand-calculated values for at least two metric × year × geo-level combinations
  - Verify demographic classification thresholds: confirm majority-Black (>50%) and majority-White (>50%) counts are plausible given Baltimore's demographic makeup (~63% Black citywide)
  - Confirm `pct_black`/`pct_white` values in `tract_demographics.csv` are in expected range (0–1); check for tracts with unexpected nulls
  - Validate CSA rollup: pick 2–3 CSAs and manually re-aggregate from tract data to confirm weighted race % and income match `csa_demographics.csv`
  - Cross-check `median_income` values against published ACS tables for a sample of tracts (e.g. Roland Park should be high, Sandtown-Winchester low)
  - Verify trend chart direction is interpretable: rising overlap = narrowing disparity (confirm with a manually computed year-pair comparison)

---

*Last updated: May 2026. Mark items `[x]` when done.*
