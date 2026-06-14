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
| 3 | **Area Embedding** *(aka "Service Category Usage by Geographic Area")* | ✅ live | The bridge: where do areas cluster — by what they request, and by who lives there — in two complementary, mutually-colorable spaces, named into reusable peer groups. Pivots the story from "what's happening" to "does it relate to who, and where." |
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

> **Implementation note**: the shipped implementation differs from earlier planning notes in several respects. `compute_combined_usage_embedding` and `compute_combined_demographic_embedding` fit **one PCA on the union of tract and CSA rows simultaneously** — both geo levels share a single coordinate space (not separate fits per grain). The service-usage view uses **QuantileTransformer** (not StandardScaler) after the CLR transform. There is **no feature-set toggle** between high-level categories and individual SRType grain — the view uses high-level category shares only. The Areas tab **manages its own data loading internally** and does not participate in the shared `geo_level` session state — there is no geo_level toggle in this tab. Both views have **fixed colors**: service-usage view is colored by median income; demographic view is colored by predominant service type for the selected year. No user-selectable color-by dropdown exists in either view.

- [x] **P4d-5: Pooled, common-space service-usage embedding** — built in `app/components/area_embedding.py` (`compute_combined_usage_embedding`, `_usage_share_matrix`, `_clr`). Stacks a `(geoid, year)` × feature usage-share matrix from all available years (`MIN_GEO_SRTYPE_N`-suppressed cells, `_MIN_GEO_YEAR_TOTAL = 50`-suppressed sparse geo-years), using **high-level category shares only** (no individual-SRType grain). Empirical validation showed raw row-normalized shares violated PCA's Euclidean assumptions — so the shipped methodology is **top-K-by-mean-share + centered-log-ratio (CLR) transform + `QuantileTransformer`**. PCA is fit **once on the union of tract and CSA rows simultaneously** (`@st.cache_data def compute_combined_usage_embedding`), so tracts and CSAs share one fixed coordinate system and every `(geoid, year)` point is directly comparable across geo levels. The scatter displays tracts (small dots) and CSAs (large labeled bubbles) together; ~10% of CSA names are labeled via farthest-point sampling. Color is **fixed to median income** — no user-selectable color-by. **Validation gate passed and surfaced in-app**: an explicit "PC1 X% / PC2 Y% / Z% combined" caption reports the variance captured. *Done.*
- [x] **P4d-5b: Animated year-by-year trajectory view** — `plotly.express.scatter(..., animation_frame="year", animation_group="geoid")` steps through years in the common space (axis ranges fixed across frames so a stable area doesn't appear to jitter; opens on the dashboard's currently-selected year via a frame-swap + slider-position sync). Color is **fixed to median income** (no user-selectable color-by dropdown). Answers: *are areas continuous or clustered in what they request, is that stable or shifting year to year?* *Done.*
- [x] **P4d-6: Demographic-space embedding — the inverse view (single-snapshot, ACS 2023)** — `compute_combined_demographic_embedding` + `_render_demographic_view` in `area_embedding.py`. PCA is fit on the **union of tract and CSA rows simultaneously** (`RobustScaler` + `PCA(2)`), using **9 ACS demographic features**: `pct_black`, `pct_white`, `pct_hispanic`, `median_income`, `pct_poverty`, `pct_bachelors_plus`, `pct_under18`, `pct_65plus`, `median_age`. Places each geography once (year-independent ACS 2023 snapshot, no animation), colored by **fixed: predominant SRType for the selected year** (categorical) — no user-selectable color-by dropdown. The scatter displays tracts (small dots) and CSAs (large labeled bubbles) together in the same coordinate space. Answers the inverse question: *do areas that look alike demographically also look alike in how they use and experience 311?* *Done — P4d-6a broadens the feature set further; the view picks up new demographic columns automatically once they land in the CSVs.*
- [x] **P4d-6a: Expand the demographic feature set** — code-level done: `_DEMO_FEATURE_COLS` in `area_embedding.py` already specifies the 9-column feature set (`pct_black`, `pct_white`, `pct_hispanic`, `median_income`, `pct_poverty`, `pct_bachelors_plus`, `pct_under18`, `pct_65plus`, `median_age`), and the `regen_demographics.yml` workflow was created to regenerate the CSVs with the extended ACS pull. **CSVs still need a pipeline run** on a runner with `CENSUS_API_KEY` set (GitHub Actions secret) — the committed CSVs have only 3 columns; until regenerated, P4d-6 uses the available subset and the embedding picks up the full 9 features automatically once the CSVs land. *Done at code level; pending runner execution.*
- [ ] **P4d-6b *(separate, non-blocking follow-on)*: Census PDB ingestion + year-over-year demographic trajectories** — Census Planning Database ships at irregular multi-year vintages, not a clean annual series like 311 data, so this needs its own design pass: a new pipeline stage to ingest PDB and align its vintages to the years the embedding covers (interpolation, or a documented "most recent vintage as of year X" rule), then the same pooled-common-space + animated-trajectory treatment as P4d-5/5b — but tracking demographic drift instead of service-usage drift. The natural payoff once both exist side by side: *"did this area's demographics shift before, after, or alongside its service-usage shift?"* — extending the embedding's covariance framing to both halves of the equity question.
- [x] **P4d-7: Shared view-switch control** — a top-level `st.radio("View", ["Demographic profile", "Service usage"])` in `render_area_embedding` toggles between the two embeddings. Both views use **fixed colors** (no adaptive color-by dropdowns): service-usage view is always colored by median income; demographic view is always colored by predominant SRType for the selected year. The Areas tab does not participate in the shared `geo_level` session state — no geographic-unit toggle appears in this tab. *Done.*
- [~] **P4d-7b: Cluster the embedding into named peer groups — the real payoff of building this view** — *Partially done*: **quadrant-based spatial grouping is implemented** — the scatter is divided at median x and median y into UL/UR/LL/LR quadrants with light-filled background rectangles; each geography's quadrant assignment is derived from its mean (x, y) across all years for stability; a neighborhood list at the bottom groups CSA names by quadrant. What remains open: full algorithm-selected cluster labels (KMeans/AgglomerativeClustering, k via silhouette or user slider, auto-generated descriptive labels), and cross-tab `peer_group` propagation — persisting `geoid → peer_group` as a reusable categorical dimension for Operations / Services / Service Equity / Equity (respecting the usage-space-vs-demographic-space boundary noted in P4d-7). The quadrant neighborhood list provides the grouping UI in the current implementation; full cluster labeling and cross-tab propagation remain open.
- [ ] **P4d-8: Optional SRType×SRType correlation heatmap** — secondary panel (e.g. `np.corrcoef` on the usage matrix) showing which service categories tend to be requested together across geographies; show only when ≥5 SRTypes are present.
- [x] **P4d-9: Wire into `app.py` as the third tab + new dependency** — `"Areas"` inserted between `"Services"` and `"Equity"` in `st.tabs([...])` (and the sidebar's tab-by-tab description list); `scikit-learn>=1.3.0` added to `app/requirements.txt` (`PCA` + `RobustScaler` + `QuantileTransformer` + clustering, all in the same package — no extra dependency needed for P4d-7b). The tab is wired as `render_area_embedding(DATA_DIR, year)` — it manages its own data loading internally and does not share `geo_level` session state with other tabs (no geographic-unit toggle in this tab). Note `umap-learn` remains a future enhancement once the PCA structure is validated further — its `numba`/LLVM dependency makes it a much heavier install. *Done.*

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

- [x] **P4d-14: Stratified, volume-weighted "adjusted" equity score** — for each SRType with sufficient coverage, compute race- and income-based `overlap_score()` (reuse `utils.overlap_score`) within that type alone, then combine into a citywide "adjusted" score weighted by each type's request volume. Display side-by-side with the existing raw citywide score (`equity_distributions`/`equity_trend`), with a plain-language caption: a higher adjusted score than raw means part of the gap is mix-driven (disadvantaged areas request structurally slower-to-resolve services more often); a similar score means the gap is in how the *same* service gets delivered. *(implements P4-1b, P4-2, P4-4)* *Done — `compute_adjusted_scores()` reuses Tab 5's cached `_subtype_current_year_scores`, weights by each type's citywide volume (`_wmean`). CSA 2024: race 0.44→0.80, income 0.74→0.80 — the formal version of Tab 5's informal finding.* **Redesigned per user review (2026-06-13):** the original static raw-vs-adjusted twin-bar opener was duplicative of Tab 5's three-grain bar, so it was replaced by (a) **`compute_adjusted_equity_trend()` + `_norm_trend_fig()`** — the raw vs. mix-adjusted overall score trended across all years (race + income), the form that is genuinely new and that doubles as the cross-city scalar (Phase 5), and (b) the per-geography normalized displays below. The volume-weighted adjusted scalar still drives the trend and the ranking.
- [x] **P4d-15: SRType equity ranking panel** — dot-plot or table of SRTypes ranked by within-type overlap score, color-coded via `score_label()`; clicking a type shows its full distribution comparison (reuse `_comparison_fig`). Answers *"which services are delivered most inequitably?"* — directly comparable to Tab 5's per-type equity views and Tab 2's per-type operational ranking, closing the loop across the whole arc. *(implements P4-3)* *Done — Race/Income-toggleable horizontal dot-plot (`_ranking_fig`) of the worst `_RANK_TOP_N` of all eligible types (coverage + volume filtered via `_eligible_types`); a drill-down selectbox over every eligible type renders that type's raw race + income box-strip distributions through the imported `_comparison_fig`. `peer_group` grouping deferred until P4d-7b's cluster labels land.*
- [x] **P4d-16: Regression panel** — OLS `log(median_days_to_close) ~ pct_black + median_income + SRType FE + year FE` over the stacked tract×SRType×year panel (an aggregate-level approximation of the original record-level spec — label it clearly, since record-level data isn't in `data/processed/`). Show a coefficient table + 95% CI plot for `pct_black`/`median_income` plus an auto-generated plain-language interpretation. Add `statsmodels>=0.14.0` to `app/requirements.txt`. *(implements P4-6)* *Done — `compute_regression()` fits a WLS (weighted by request count) of `log1p(median_days_to_close)` on `pct_black + income_10k + C(SRType) + C(year)`, dropping the rare-type tail (`_REG_MIN_TYPE_ROWS`) to bound the design matrix; returns a small cache-friendly coef frame, rendered as a forest plot (`_coef_fig`) + table + `_regression_interpretation()` prose. With the FE in place both demographic coefficients shrink to ~0 / non-significant — independent corroboration of the mix-driven story. `statsmodels>=0.14.0` added to `app/requirements.txt`.*
- [x] **P4d-17: Wire into `app.py` as the sixth (final) tab** — append `"Equity Adjusted for Service Mix"` after `"Service Equity"`; receive the active `metric_col`/`metric_label` from the Equity tab's selector so scores and regression stay aligned with what the user is already looking at. *Done — wired as `render_equity_adjusted(DATA_DIR, demographics, geo_key, year, eq_metric_label=st.session_state.get("eq_metric"))`, displayed with the terser in-app title **"Mix-Adjusted Equity"** (matching the dashboard's short-label convention; full planning name kept here). The Equity tab's metric carries over when it exists at the service-type grain (median days / closure rate); on-time-rate / requests-per-1k fall back to median days with an in-tab note. Sidebar narrative + six-tab arc caption updated. Verified end to end via `streamlit.testing.v1.AppTest`: full app renders all six tabs with zero exceptions; the tab in isolation renders all three sections at CSA and tract grain (~12s tract incl. regression) with the metric-fallback path exercised.*

### Suggested build order

Data is already in place (Stage 0 ✅). Build roughly in final tab order so each step's reuse opportunities are fresh when you reach the next:

**Tab 2 / Services** (P4d-1 → 4, pure operations — the simplest, and establishes shared category-table/pill scaffolding) → **Tab 5 / Service Equity** (P4d-10 → 13, directly extends Tab 2's table with the equity comparison pattern from `equity_distributions.py`) → **Tab 3 / Area Embedding** (P4d-5 → 9, independent of the category tabs once Stage 0 data is in hand; fit and validate the pooled common-space PCA — feature-set and geo-grain combinations — *then* layer on the animated trajectory view and cluster into peer groups at P4d-7b once the spaces are stable) → **Tab 6 / Equity Adjusted** (P4d-14 → 17, stratified scores generalize Tab 5's single-category comparison to every category and add the regression panel; reordered after Tab 3 so its ranking panel — P4d-15 — can reuse `peer_group` as a grouping dimension once P4d-7b lands, rather than being built before that dimension exists) → propagate `peer_group` back into Operations, Services, Service Equity, and Equity per the space-appropriate boundary noted at P4d-7b → wire the two remaining new tabs into `app.py` as one coordinated change to the tab list (in final order: Operations, Services, Area Embedding, Equity, Service Equity, Equity Adjusted for Service Mix), imports, and sidebar description.

> **Status (2026-06-13, updated)**: Tabs 2, 3, 5, and **Tab 6** (✅ **Services**, **Area Embedding**, **Service Equity**, **Mix-Adjusted Equity**) have shipped and **Tab 6 is merged to `main`** — all verified via `AppTest`. The full six-tab arc (Operations → Services → Area Service Usage → Equity → Service Equity → Mix-Adjusted Equity) renders end to end with zero exceptions. **Post-merge redesign (per user review):** Tab 6's opener — originally a static raw-vs-adjusted twin-bar (duplicative of Tab 5's three-grain bar) — was replaced by (1) a **year-over-year normalized equity trend** (raw vs. mix-adjusted score across all years) and (2) a **per-neighborhood mix-adjusted map + raw-vs-adjusted scatter**. The first per-neighborhood draft computed the residual in-app as a weighted mean of per-type medians, which is **unsound for a median** (it can rank-reverse across demographic groups — it made things look *less* equal while the within-type top-line showed the opposite); diagnostics traced it to the median's non-decomposability, and it was replaced by the proper **record-level direct-standardization stage (P4e-1/P4e-2, ✅ done)**. The within-type ranking (P4d-15) and regression (P4d-16) remain below. P4d-7b's `peer_group` may still optionally feed the ranking. Backfill is running to populate `{geo}_adjusted_metrics_{year}.parquet`; until then the per-neighborhood view shows a "run the adjusted stage" notice.

### Verification

- **Stage 0**: ✅ done — confirmed all `srtype_metrics_*`, `tract/csa_srtype_metrics_*` (2016–2025), and both demographics CSVs are present and schema-correct after merging `main` (commit `289e002`); `total_requests` cross-check against the Operations KPI bar is still good practice before relying on these numbers in the new tabs.
- **Tab 2 / Services**: ✅ verified — among-category comparison and category drill-down render with no demographic content anywhere on the tab (spot-checked: zero matches for "Black"/"income"/"equity"); selecting a category shows its composite year-over-year lines (volume + days to close) and the within-category subtype multi-line breakdown (top-N + "all other" folding); **no choropleth or map content** — geography was deliberately removed from this tab per the P4d-3 redesign and now lives only in Operations (and, eventually, Area Embedding).
- **Tab 3 / Area Embedding**: ✅ verified — both views (`Service usage` ↔ `Demographic profile`) render with no exceptions. Combined tract+CSA scatter in a single shared PCA space; tract dots labeled with NSA neighborhood names (~10%, min 3 per quadrant, farthest-point sampled); hover title shows "Neighborhood · Tract XXXX.XX". Quadrant backgrounds (UL/UR/LL/LR, divided at median x/y) render correctly. Below the scatter: predominant-SRType distribution bar (% of tracts per quadrant whose top call is each specific subtype) and two-column CSA neighborhood list by quadrant. Usage view: animated scatter (one point per `(geoid, year)`), color fixed to median income. Demographic view: static snapshot (ACS 2023, no animation), color fixed to predominant SRType for the selected year. NSA crosswalk generated via `--stage nsa` / `nsa_crosswalk.yml` workflow and committed to `data/processed/tract_to_nsa.csv`.
- **Tab 5 / Service Equity**: ✅ verified — among-category equity trend and category-selection trend (with "All categories" dashed reference line) render correctly on the fixed `[0,1]` axis with threshold bands; within-category subtype equity breakdown over time follows the same top-N + "all other" folding as Tab 2; sparse SRType×year cells show "insufficient data" gracefully (NaN score, `score_label()`) rather than blank gaps or errors; **no map and no flat ranking table anywhere on the tab** (confirmed zero `build_choropleth` references); the data-driven analysis paragraph (citywide vs. within-category vs. within-subtype averages) renders for both available metrics and matches the underlying numbers; the tab's framing and visual rhythm read as the equity-flavored mirror of Tab 2, not a repeat of Operations or the Equity tab.
- **Tab 6**: raw vs. adjusted scores both display and differ meaningfully; ranking dot-plot is color-coded by `score_label()` and is directly comparable to Tab 5's per-type views; regression table shows non-null `pct_black`/`median_income` coefficients with CIs; missing-file states show `st.info()`, not errors.
- **Whole arc**: read the six tabs in order start to finish — each one should follow naturally from the last with no "wait, why are we suddenly talking about X" moments. If a reader gets lost between any two adjacent tabs, that's a signal to add a one-line bridging caption (e.g. at the top of Tab 3: "The last tab showed how individual services perform — this one asks whether *areas* cluster in how they use those services, or in who lives there").

---

## Phase 4e — Updated Equity Baseline: Per-Geography Adjusted Metrics *(stage shipped — P4e-3→5 open)*

**Goal**: compute a within-service-type normalized performance score for each geography — the most defensible version of "is this neighborhood being served equitably" because it controls for what services the neighborhood requests. A neighborhood that requests structurally slow-to-close services shouldn't be penalized for that in its equity score.

**The key computation (as built)**: **direct standardization** — for each geography, reweight its own requests so its service-type mix matches the citywide mix, then read off the metric (interpolated weighted median for days; weighted mean for closure). This supersedes the originally-sketched `actual / citywide_mean_for_type` ratio, which was unsound for medians (a median does not decompose into a weighted mean of per-type medians and can rank-reverse across groups). Implemented in `compute_adjusted_geo_metrics()` and consumed by Tab 6; see P4e-1 below. P4e-3→5 (surfacing the same adjusted columns in the Equity tab map / distributions / trend) remain open.

### Pipeline additions

> **History (2026-06-13)**: a first in-app version computed the per-geography normalized metric as `actual − expected` where `expected` was a volume-weighted mean of per-type values. That was **unsound for the median**: a median does not decompose into a weighted mean of per-type medians (mean-of-medians overweights slow-tail types and can even rank-reverse across groups), so median-days residuals were artifactual — they showed neighborhoods as *less* equal after adjustment while the within-type top-line showed the opposite. Diagnostics (closure rate, which decomposes cleanly, + a within-type signed-gap tally) confirmed the artifact. Replaced by the proper **record-level direct-standardization stage** below (Option C).

- [x] **P4e-1: Per-geography adjusted metrics stage** — `stage_adjusted(year, is_live)` in `scripts/pipeline.py` + `compute_adjusted_geo_metrics()` / `weighted_median()` in `src/balt311/metrics.py`. Reads the record-level interim file, filters to the **same equity subset** as the Equity-tab rollups, and for each geography **directly standardizes** its requests to the citywide service mix: `adj_median_days_to_close` is an interpolated weighted median of the geography's closed records (each weighted `citywide_closed_count(type) / geo_closed_count(type)`), `adj_closure_rate` is the citywide-request-weighted mean of its per-type closure rates. Writes `{tract,csa}_adjusted_metrics_{year}.parquet` with `n_obs`, the two `adj_*` columns, and the citywide `ref_*` baselines (so the app maps residual = adjusted − citywide without record-level data). Suppression: `MIN_GEO_SRTYPE_N = 5`, ≥3 types per geography. CSA = population-weighted rollup of tract adjusted values (matches the raw CSA basis). *Done — validated with synthetic Simpson-reversal tests: a neighborhood slow only because of its mix collapses to ≈ citywide after adjustment, while one that genuinely under-delivers the dominant type stays high. The app's `compute_normalized_geo_metrics()` now reads these files (raw from `*_metrics_*`, adjusted + ref from the new file); the residual map + raw-vs-adjusted scatter use them, with a "run the adjusted stage" notice until the files exist.*
- [x] **P4e-2: Add to pipeline CLI + Actions workflow** — `--stage adjusted` added to the CLI; called after `--stage srtype` in both `update_data.yml` (with `--live` passthrough) and `backfill.yml`. *Done — run the backfill workflow once to populate all years; per-year update_data also generates it going forward.*

### App additions

- [ ] **P4e-3: Adjusted metric option in Equity tab** — add "Adjusted closure rate" and "Adjusted days to close" to the `METRIC_OPTIONS` dict in `map_view.py`, reading from `*_adjusted_metrics_{year}.parquet`. Color scale centered at 1.0 (city average) rather than the data median; diverging scale where <1 = better than average for this neighborhood's mix, >1 = worse. Caption: "Adjusted for service mix — scores below 1.0 mean this neighborhood is served better than expected given what it requests; above 1.0 means worse."
- [ ] **P4e-4: Adjusted equity distributions** — in `equity_distributions.py`, add adjusted metrics to the race/income comparison when the adjusted files are present; show adjusted overlap score alongside raw for direct comparison.
- [ ] **P4e-5: Adjusted equity trend** — in `equity_trend.py`, add adjusted metric series to the year-over-year trend chart, as a second set of dashed lines alongside the raw series.

---

## Phase 4f — Council Member Features *(after Phase 4e)*

**Goal**: make the dashboard usable for a city council member or district staff who needs to understand how their district is performing — not just how the city overall is performing. The four improvements implemented in June 2026 (see verification below) give council members a multi-neighborhood comparison tool, neighborhood search, worst-performer rankings, and a peer-similarity lens. The council district overlay remains the highest-value open item.

### Implemented (June 2026)

- [x] **P4f-1: Multi-neighborhood comparison widget** — `st.multiselect` expander on the Equity tab (below the map) lets users pick up to 5 CSAs or tracts and see their key metrics side-by-side in a formatted table. Uses already-loaded `df` in-app; no pipeline change. *Done — `app.py` Equity tab section.*
- [x] **P4f-2: Neighborhood highlight search in Area Embedding** — `st.text_input` above the scatter plot in Tab 3; typing any portion of a CSA or NSA neighborhood name adds a gold-ring highlight trace on matching geographies in both views (usage and demographic). *Done — `area_embedding.py` `render_area_embedding()`, `_add_highlight_trace()`, `_render_usage_view(highlight=)`, `_render_demographic_view(highlight=)`.*
- [x] **P4f-3: Worst-performing neighborhoods table** — ranked table of the 5 neighborhoods with the most extreme (worst) metric values, shown below the distribution charts in `equity_distributions.py`. Direction is metric-aware: longest wait for days-to-close, lowest rate for closure/on-time rate. *Done — `_render_outlier_table()` in `equity_distributions.py`.*
- [x] **P4f-4: Peer neighborhood comparison** — when a neighborhood is selected on the Equity tab map, `render_peer_comparison()` (new function in `summary_panel.py`) computes the 3 most demographically similar geographies using Euclidean distance on normalized `pct_black`, `pct_white`, `median_income` features from the demographics CSV, then renders a comparison table: selected neighborhood (★) vs. each peer, all key metrics side by side. No pipeline change — uses already-loaded `*_demographics.csv`. *Done — `summary_panel.py` `_find_peers()`, `render_peer_comparison()`; called from `app.py` after the map columns.*

### Remaining (open)

- [ ] **P4f-5: Council district overlay + filter** — add Baltimore City council district boundaries as a toggle GeoJSON layer on the Equity tab choropleth; a district selector filters the distribution panels and comparison table to tracts within that district. **Blocked on data**: requires council district boundary GeoJSON (available at [Baltimore City Open Data — Council Districts](https://data.baltimorecity.gov/)) and a tract→district spatial crosswalk. Once the GeoJSON is acquired, the pipeline stage (`stage_council_crosswalk()`) can be modeled after the existing BNIA `stage_csa_boundaries()` pattern. The spatial join uses the same `geopandas.sjoin_nearest` approach as the NSA crosswalk.
- [ ] **P4f-6: District-level equity distributions** — when a council district is selected (P4f-5), filter `equity_distributions.py` to show the race/income distribution for only the tracts in that district, with the citywide distribution overlaid as a reference. Answers: "is the equity gap in my district larger or smaller than the citywide average?"

### Verification

- **P4f-1 (compare widget)**: open Equity tab at CSA level; expand "Compare neighborhoods side by side"; select 3 CSAs; confirm a metric × neighborhood table appears with all 5 metrics formatted correctly and "—" for any nulls.
- **P4f-2 (search)**: open Area Service Usage tab; type partial CSA name (e.g. "Canton"); confirm a gold ring appears on the matching bubble in both views; clear the field and confirm ring disappears.
- **P4f-3 (outlier table)**: open Equity tab; change metric selector; confirm "Neighborhoods most in need of attention" table appears below the distribution charts and shows 5 rows with correct direction (longest wait for days-to-close, lowest rate for closure/on-time).
- **P4f-4 (peer comparison)**: click a CSA on the Equity tab map; confirm "Demographically similar neighborhoods" section appears below the map with a 4-row table (★ selected + 3 peers); confirm metrics are populated and demographically the peers make sense (similar pct_black, similar income).

---

## Phase 5 — Cross-Municipality Comparison *(v2.0.0 target)*

**Goal**: place Baltimore's 311 volume, service delivery, and service equity in context
against peer and leading cities, with **Baltimore as the fixed reference**. Once shipped,
Baltimore's numbers become interpretable as strong, average, or lagging rather than raw
figures. The defining feature of **version 2.0.0**.

> **Feasibility & evidence**: the city evaluation matrix, API-maturity assessment,
> success-likelihood ratings, adapter-family sequencing, and normalization rules live in
> **`cross_city_comparison.md`** (§1–§5). Requirements live in `requirements.md` §3.6 (method)
> and §4.6 (the two tabs). This list is the build plan.
>
> **Working discipline — pause and record at every step**: each sub-phase below ends with a
> **documentation checkpoint** that appends its results to `cross_city_comparison.md` §6.
> **Do not start a sub-phase until the previous sub-phase's checkpoint entry exists.** The
> checkpoint records what was built, what the data actually showed, surprises/quirks, and any
> revision to the plan. This is a hard gate, not a courtesy.

**End state — two new tabs, Baltimore as reference in both:**
- **Tab 7 — Cross-City Service Delivery** (volume + delivery metrics, many cities)
- **Tab 8 — Cross-City Service Equity** (each city's *own internal* race/income overlap score, compared)

**Cohort waves** (each wave = one API adapter family coming online): **Wave 0 (MVP)** DC
(ArcGIS, reuses existing client) → **Wave 1** Philadelphia (Carto, strongest demographic
peer) → **Wave 2** NYC / Chicago / SF (Socrata, leading benchmarks) → **Wave 3 (optional)**
Detroit + evaluate St. Louis/Louisville. Boston deferred pending its mid-2026 backend migration.

**Key feasibility finding driving the order**: the *equity* comparison is **more portable**
than the *delivery* comparison — it rides entirely on national ACS + TIGER data plus each
city's lat/lon (success "High" for every geocoded city), whereas delivery comparison carries
closure-semantics caveats. But delivery is built first because it is conceptually simpler and
validates the whole cross-city pipeline that equity then reuses.

---

### Phase 5.0 — City selection & feasibility assessment *(✅ done — June 2026)*

- [x] **P5.0-1: Review peer & leading city options** — ten candidates evaluated across four
  API families (ArcGIS REST, Carto SQL, Socrata SODA, CKAN). Matrix, endpoints, key fields in
  `cross_city_comparison.md` §2.
- [x] **P5.0-2: Assess evaluation-success likelihood by API access + 311 data maturity** —
  per-city delivery-cmp and equity-cmp success ratings recorded (`cross_city_comparison.md` §2).
  Headline: equity-cmp "High" for every geocoded city (national data sources); delivery-cmp
  "Medium" where closure semantics / channel scope / short history apply.
- [x] **P5.0-3: Choose the MVP pair** — **Baltimore + Washington, DC**. DC publishes 311 as
  per-year ArcGIS FeatureServer layers — the same technology `src/balt311/ingest.py` already
  paginates — so the MVP reuses the existing client and spends effort on the new abstraction.
  Rationale in `cross_city_comparison.md` §3.
- [x] **P5.0-4: Documentation checkpoint** — feasibility results recorded in
  `cross_city_comparison.md` §6.0. *(Gate for starting 5.1.)*

---

### Phase 5.1 — Cross-city ingestion abstraction + MVP pair (Baltimore + DC)

> **Status (2026-06-13)**: code for the whole data layer **and** the 5.2 delivery tab shipped together (user chose to build both at once). New `src/balt311/cities/` package — `base.py` (adapter contract + `apply_field_map`), `arcgis.py` (reusable FeatureServer client + name-based per-year layer discovery, since DC's layer ids aren't a clean offset: 2023=15, 2024=16, 2025=18), `dc.py` (DC adapter, `SERVICECODEDESCRIPTION/ADDDATE/RESOLUTIONDATE/LAT/LON` → canonical), `baltimore.py` (wraps `ingest.fetch_year`). `peer_metrics.compute_city_metrics` computes the uniform per-(city,year) row (closure = CloseDate present; rates only), `fetch_county_population` pulls ACS county pop by FIPS, `upsert_metrics` keys on (city,year). Driver `scripts/peer_city.py` + workflow `.github/workflows/peer_city.yml` write `peer_city_metrics.parquet` + `peer_city_meta.csv`. **ArcGIS is unreachable from the dev sandbox (403), so P5.1-5 (run the MVP pair) and the §6.1 / §6.2 checkpoints are pending the first CI workflow run** — the tab soft-degrades to a "run the workflow" notice until the files land. `compute_city_metrics`/`upsert` unit-tested; the delivery tab verified via `AppTest` (chart for the 3 derivable metrics, on-time soft-degrade, year fallback, file-absent notice; full app renders 11 tabs).
>
> **Update (2026-06-14)**: first CI runs done. (1) **Scoping bug fixed** — Baltimore ran over *all* records, so ECC information-calls + system records inflated volume ~2.5× and crushed median days-to-close to ~0; per-adapter `scope()` / `is_closed()` hooks now mirror `filter_equity_subset` + `aggregate_tract` (resident, non-ECC, geocoded; SRStatus closure). (2) **DC ingestion hardened** — switched to keyset (OBJECTID) pagination + `returnGeometry=false` (offset paging timed out at depth on DC's ~440k-row layers); driver now isolates each city so one failure can't discard the others. (3) **Smart reuse** — `peer_city.py` skips `(city,year)` rows already present unless `--force`; new `peer_city_backfill.yml` repopulates years sequentially. (4) **§6.1 cross-check passed** on the corrected 2025 rows: cross-city Baltimore agrees with the within-app numbers up to two documented method differences (record-level pooled median 2.99 d vs the Operations tab's geographic 3.12 d; total 471.5k vs 459.9k from lat/lon-geocoded vs tract-joined). P5.1-5 in progress — backfill running to overwrite remaining stale years (2024 not yet regenerated).

- [x] **P5.1-1: Per-city adapter contract** — define a small adapter interface in
  `src/balt311/cities/` (e.g. `base.py`): each adapter exposes `fetch(year) -> records` and a
  `FIELD_MAP` translating its raw columns to Baltimore's canonical names
  (`SRType`, `CreatedDate`, `CloseDate`, `Latitude`, `Longitude`, channel where available).
  Keep the existing Baltimore pipeline untouched; Baltimore becomes one adapter among many.
- [x] **P5.1-2: ArcGIS adapter + DC config** — generalize the FeatureServer pagination in
  `ingest.py` into a reusable ArcGIS adapter (`cities/arcgis.py`) parameterized by base URL,
  per-year layer map, and field list. Add `cities/dc.py`: per-year `311 City Service Requests
  in YYYY` layers, mapping `ADDDATE`→created, `RESOLUTIONDATE`→closed,
  `SERVICECODEDESCRIPTION`→type, `LATITUDE`/`LONGITUDE`.
- [x] **P5.1-3: Normalized cross-city metrics schema** — define `peer_city_metrics.parquet`
  (or CSV): one row per `(city, year)` with `total_requests`, `requests_per_1k`,
  `median_days_to_close`, `closure_rate`, `on_time_rate` (nullable), plus a `closure_definition`
  note column. Compute via a city-agnostic aggregation that reuses Baltimore's
  `compute_days_to_close` logic and applies the 30-day right-censoring rule.
- [x] **P5.1-4: City population for per-1k** — pull each city's ACS total population by FIPS
  (reuse the existing `ACS_POPULATION_URL` pattern with the city's state+county FIPS). Store in
  a small `peer_city_meta.csv` (city, fips, population, portal_url, closure_definition).
- [ ] **P5.1-5: Run MVP pair** — produce `peer_city_metrics` rows for Baltimore + DC for the
  most recent shared year; cross-check Baltimore's row against the Operations KPI bar (must match).
- [ ] **P5.1-6: Documentation checkpoint** — append `cross_city_comparison.md` §6.1: DC schema
  quirks, closure-semantics finding, row counts, any field-map surprises, Baltimore-row
  cross-check result. *(Gate for starting 5.2.)*

---

### Phase 5.2 — Cross-City Service Delivery tab (MVP: Baltimore + DC)

- [x] **P5.2-1: Delivery comparison component** — `app/components/city_delivery.py`
  (`render_city_delivery(data_dir, year)`). Loads `peer_city_metrics`; renders a metric toggle
  (requests per 1k, median days to close, closure rate, on-time rate) and a ranked dot-plot /
  bar with **Baltimore highlighted**. Compares rates, never raw counts.
- [x] **P5.2-2: Comparability caveat UI** — a caption/banner stating each city's closure
  definition and the shared-year used; soft-degrade when a metric is null for a city (e.g. no
  derivable on-time rate). Reuse the "insufficient data" treatment pattern from the equity tabs.
- [x] **P5.2-3: Decide tab placement** — ✅ **RESOLVED ahead of schedule (June 2026): a
  dedicated "Compare cities" group, not appended to the within-Baltimore arc.** The app is now
  two nested-tab groups — **🏙️ Within Baltimore** and **🌐 Compare cities** — because the two
  families are structurally different (cross-city is city-level only, no `geo_level`, heavy
  caveats, near-zero component reuse). The "Compare cities" group shell already ships with
  placeholder inner tabs (Service Delivery, Service Equity, Maturity Index) in
  `app/components/cross_city.py` + a comparability-caveat header; Phase 5.2 just fills in the
  delivery render body. Rationale recorded in `cross_city_comparison.md` §5. *(The 5.2 build
  still owns wiring the real chart in; only the placement question is closed.)*
- [ ] **P5.2-4: Documentation checkpoint** — append `cross_city_comparison.md` §6.2: what the
  Baltimore-vs-DC delivery comparison shows, screenshots/figures if useful, placement decision.
  *(Gate for starting 5.3.)*

---

### Phase 5.3 — Cohort expansion (Philadelphia, then NYC / Chicago / SF)

- [x] **P5.3-1: Carto adapter + Philadelphia** — `cities/carto.py` (one `phl.carto.com/api/v2/sql`
  endpoint, server-side aggregation via SQL) + `cities/philadelphia.py` mapping
  `requested_datetime`/`closed_datetime`/`service_name`/`lat`/`lon`. Add Philadelphia rows to
  `peer_city_metrics`. *(Wave 1 — strongest demographic peer.)*
- [ ] **P5.3-2: Socrata adapter** — `cities/socrata.py` using SODA `$select`/`$where`/`$group`
  to aggregate **server-side** (never pull raw millions). One adapter, parameterized by domain +
  dataset id + column map.
- [ ] **P5.3-3: Add NYC / Chicago / SF** — `cities/{nyc,chicago,sf}.py` configs over the Socrata
  adapter (`erm2-nwe9`, `v6vf-nfxy`, `vw6y-z8j6`). Add their rows to `peer_city_metrics`. *(Wave 2
  — leading-practice benchmarks.)*
- [ ] **P5.3-4: Per-city onboarding QA** — for each city: confirm year coverage, validate a
  spot metric against the city's own published figure, record closure definition + channel scope.
- [ ] **P5.3-5: Documentation checkpoint** — append `cross_city_comparison.md` §6.3 **one entry
  per city onboarded** (quirks, comparability notes, validation result). *(Gate for starting 5.4.)*

---

### Phase 5.4 — Cross-City Service Delivery tab (cohort)

- [x] **P5.4-1: Generalize Tab 7 to N cities** — the delivery component renders the full cohort,
  Baltimore still highlighted as reference; add a cohort/city multiselect so the user can focus a
  comparison set; sort by the selected metric.
- [ ] **P5.4-2: Year-alignment control** — default to the most recent year present in all
  selected cities; surface which years are shared vs. missing.
- [ ] **P5.4-3: Documentation checkpoint** — append `cross_city_comparison.md` §6.4: cohort
  delivery findings — where Baltimore lands on each metric vs. peers and vs. leading cities.
  *(Gate for starting 5.5.)*

---

### Phase 5.5 — Cross-city equity methodology (portable ACS-tract join)

> **Primary metric is the mix-adjusted score, not the raw score.** The dashboard's own
> headline finding (Tab 5 / Phase 4d) is that **a large share of the apparent citywide equity
> gap is driven by service *mix*** — which services a neighborhood requests — rather than by
> unequal delivery of the *same* service. Comparing **raw** citywide overlap scores *across
> cities* would therefore confound two different things: real differences in delivery equity,
> and mere differences in each city's service-request mix. The cross-city equity comparison
> must instead use the **mix-adjusted overall score** — the volume-weighted mean of each city's
> *within-service-category* overlap scores (the Phase 4d Tab 6 / Phase 4e "adjusted" score,
> P4d-14 / P4e-1) — so the comparison isolates *how the same kinds of services are delivered*
> from *what each city happens to request*. The raw score is retained only as a secondary
> reference line for transparency.
>
> **Portability note**: the mix-adjusted *overall* score needs **no cross-city taxonomy
> harmonization** — each city's within-category scoring happens entirely inside that city using
> its *own* request-type vocabulary, and only the final volume-weighted scalar is compared
> across cities. (Comparing the *same category* across cities — pothole-vs-pothole — is the
> separate Phase 5.7 stretch that *does* need a shared taxonomy.) This means the adjusted
> overall comparison sits cleanly between 5.6-raw and 5.7-within-type and is fully portable.
>
> **Dependency**: P5.5-3 reuses the within-category equity machinery already built for Baltimore
> (`category_equity_explorer.py`: `compute_category_equity_history`) plus the volume-weighted
> combination from Tab 6 (P4d-14). If Tab 6 has not yet shipped, build the volume-weighted
> combiner here and back-port it to Tab 6 — they are the same computation.
>
> **Explicitly out of scope for these dashboards**: a *cross-city service-mix analysis* (how the
> composition of request types itself differs city to city, and what that says about each city's
> service model) is genuinely interesting but is a different study — note it as a non-goal here so
> the equity tab stays focused on delivery equity, not demand composition.

- [ ] **P5.5-1: Per-city tract demographics** — generalize `stage_demographics` to any city by
  parameterizing the ACS query on state+county FIPS; produce `{city}_tract_demographics.csv`
  (`pct_black`, `pct_white`, `median_income`). National ACS API — no per-city portal needed.
- [ ] **P5.5-2: Per-city tract boundaries + point-in-polygon** — pull each city's TIGER tracts
  (state+county FIPS) and assign each geocoded request to a tract (reuse Baltimore's spatial-join
  logic). City-level boundary filter mirrors the existing FIPS-510 filter. Also produce per-city
  `{city}_tract_srtype_metrics` (geo×SRType grain), needed for the within-category scoring below.
- [ ] **P5.5-3: Per-city mix-adjusted overall equity score** *(primary)* — for each city, compute
  the within-service-category race- and income-based `utils.overlap_score()` (each city's own
  categories), then combine into a single volume-weighted **adjusted** overall score per
  `(city, year, metric)` — reusing the Tab 6 / P4d-14 logic. Also compute the **raw** citywide
  score for the same cells as a secondary reference. Output: `peer_city_equity.parquet` — one row
  per `(city, year, metric)` with `adj_race_score`, `adj_income_score`, `raw_race_score`,
  `raw_income_score`, and the raw between-group median-days gap. **Scores are compared across
  cities; tracts are not.**
- [ ] **P5.5-4: Validate against Baltimore in-app numbers** — Baltimore's raw scores here must
  match the Equity tab's existing scores, and its adjusted scores must match Tab 5/Tab 6's
  within-category and volume-weighted figures, for the same year/metric.
- [ ] **P5.5-5: Documentation checkpoint** — append `cross_city_comparison.md` §6.5: per-city
  adjusted **and** raw equity scores (note the gap between them per city — a large gap means that
  city's apparent disparity is mostly mix-driven), the Baltimore validation result, demographic-
  coverage notes. *(Gate for 5.6.)*

---

### Phase 5.6 — Cross-City Service Equity tab (cohort)

- [ ] **P5.6-1: Equity comparison component** — `app/components/city_equity.py`. Plots each
  city's **mix-adjusted** race- and income-based overlap score (the primary metric, per the 5.5
  rationale) on a fixed `[0,1]` axis with the same green/amber/red threshold bands as
  `equity_trend.py`; **Baltimore highlighted**. Plain-language framing: "controlling for what each
  city requests, is Baltimore more or less equitable in *delivering the same services* than its
  peers?"
- [ ] **P5.6-2: Raw-vs-adjusted reference view** — show each city's **raw** citywide score as a
  secondary/reference series alongside its adjusted score (and optionally the raw between-group
  median-days gap), with a caption explaining that a wide raw↔adjusted gap for a city means its
  apparent disparity is largely a service-mix effect, not a delivery-equity one — the same
  raw-vs-adjusted story Tab 6 tells citywide, now told across cities.
- [ ] **P5.6-3: Wire Tab 8 into `app.py`** — add after Tab 7 (placement per the 5.2 decision) +
  sidebar description; soft-degrade when a city's scores are unavailable.
- [ ] **P5.6-4: Documentation checkpoint** — append `cross_city_comparison.md` §6.6: cross-city
  equity findings — how Baltimore's gap ranks against peer and leading cities. *(Gate for 5.7.)*

---

### Phase 5.7 — Within-type cross-city comparison *(stretch)*

- [ ] **P5.7-1: Request-type taxonomy crosswalk** — map each city's request types to a shared
  ontology (anchor on the Open311 service-category list) for a handful of high-volume, clearly
  comparable categories (e.g. illegal dumping, potholes, streetlights, graffiti). Document
  coverage and unmatched-type share per city.
- [ ] **P5.7-2: Within-type equity comparison** — for the shared categories, compute per-city
  within-type overlap scores and compare across cities (extends Tab 8). Surface coverage gaps as
  "insufficient data" rather than implying false comparability.
- [ ] **P5.7-3: Documentation checkpoint** — append `cross_city_comparison.md` §6.7: taxonomy
  mapping coverage and within-type findings; note which categories proved comparable and which did not.

---

### Phase 5.8 — 311 Open-Data Maturity Index *(planned enhancement)*

**Goal**: rank Baltimore's 311 *open-data publishing maturity* against the set of US cities that
publish 311 open data — and, just as importantly, **credit** the cities (Baltimore foremost)
whose openness makes analysis like this repository possible. Framed as recognition, not a
gotcha: penalizing openness with criticism while letting closed cities off the hook would
disincentivize the very transparency this project depends on.

> **Why this belongs in the plan**: the §2 evaluation matrix in `cross_city_comparison.md`
> already assesses most maturity criteria qualitatively during city onboarding. This phase
> formalizes that into a scored, rankable index — nearly free to populate — and produces a
> per-dimension gap profile for Baltimore that maps one-to-one onto `requirements.md` §5 Gap
> Dependencies. Full rubric and the two standing caveats (measures *publishing* maturity, not
> service quality; "all US cities" scoped to "cities with public 311 open data") are in
> `cross_city_comparison.md` §8.

**Baltimore's standing (the reference point)**: first US 311 system (1996); CitiStat pioneer
(1999); early Open311 GeoReport v2 adopter (~2011, among only ~a dozen US cities — ahead of
many far larger ones); What Works Cities Silver (2021). A pioneer that, on the *publishing*
axis specifically, the Socrata leaders now edge out on unification/cadence/documentation — the
index is built to show both truths honestly.

- [x] **P5.8-1: Define the maturity rubric + weights** — finalize the dimension list and 0–N
  scoring scale (`cross_city_comparison.md` §8): availability & open license; granularity
  (record-level vs. aggregate); history depth; update cadence; API access (SODA/ArcGIS/Carto
  vs. download-only); Open311 GeoReport v2 standardization; field completeness (created/closed
  timestamps, geo, type, status, channel, reopen, cost); geocoding coverage; documentation quality.
- [x] **P5.8-2: Score the cohort** — populate a scorecard (one row per city, per-dimension
  subscores + total) from the onboarding assessments (5.1/5.3); fill remaining gaps (geocoding %,
  Open311 compliance check, license). Output: `data/processed/peer_city_maturity.csv`.
- [x] **P5.8-2b: Harden the largest-metros coverage census** — validate and finalize the
  provisional ✅/🟡/❔ census of the ~40 largest US cities in `cross_city_comparison.md` §8.1:
  confirm each city's open-311 status against its portal (record-level? timestamps? geo? API?
  history?), resolve every ❔ to a definite ✅/🟡/❌, and record the headline count ("only N of the
  40 largest can be scored"). This is the inverse of the scorecard — it names the cities that
  *cannot* be evaluated this way, which is what makes the scoreable cities (Baltimore foremost)
  notable. Anchor on the National 311 Data Portal + US City Open Data Census (§7).
- [x] **P5.8-3: Baltimore gap profile** — for each dimension where Baltimore trails the leader,
  name the specific field/practice that would close it; cross-reference `requirements.md` §5.
  Turns "publish better data" into a measured, prioritized list.
- [x] **P5.8-4: "Credit where due" framing in-app and in docs** — surface the standing with
  explicit positive framing: name the enabling openness *before* any critical finding. A small
  panel on the cross-city tabs (or the sidebar) that credits the cities whose openness permits
  the analysis, Baltimore's first-mover and Open311 leadership highlighted. (The README and
  `requirements.md` §1 narrative additions for this already shipped with the plan; this task
  carries the same framing into the app surface.)
- [ ] **P5.8-5: Documentation checkpoint** — append `cross_city_comparison.md` §6.8: the
  scorecard, Baltimore's rank, the gap profile, and the credit framing.

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
  - Six personas defined: Interested Citizen, Citizen Journalist, Citywide Official, Local Official (council), Department Ops Manager, Honors HS Civics/Statistics Student (added June 2026)
  - Summary matrix maps each phase to persona value
  - Key finding: Phase 4b (Area Analysis) is highest-value next step for council and ops personas; Phase 5 (cross-municipal) unlocks journalist and citywide official use cases; citizen persona is underserved and needs a dedicated accessibility pass before public launch
  - June 2026 accessibility improvements (glossary, expanders, lifecycle explainer, civic-hook framing, plain-color labels) directly serve Persona 6 (HS student) and lower the floor for Persona 1 (citizen)
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

## Long-term Enhancements *(post-v2.0.0)*

These improvements address specific persona gaps identified in the June 2026 needs assessment (`personas.md`). None are on the active roadmap; they become relevant once v2.0.0 (Phase 5 / cross-municipal benchmarking) ships and the audience expands beyond super-users.

### For the Interested Citizen (Persona 1)

- **Address / neighborhood search** — text input that resolves a street address to a census tract GEOID (Nominatim geocode or static address→GEOID lookup) and pre-selects that tract on the Equity tab map, automatically opening the summary panel. Zero new data needed; pure UI.
- **Simplified neighborhood report card** — a mobile-first, jargon-free card: ✓/⚠/✗ icon + one plain sentence per metric. Shareable via URL parameter (`?geo=<geoid>`).

### For the Citizen Journalist (Persona 2)

- **CSV export buttons** — `st.download_button` on the equity trend DataFrame, the flagged-type table (Service Equity), and the grain-comparison summary. No new data; serialization only.
- **Year-over-year change summary panel** — a compact table of all metrics × dimensions showing Δ vs. prior year, color-coded by direction and magnitude. Placed at the top of the Equity tab for quick scanning.

### For the Citywide Official (Persona 3)

- **Executive summary / print view** — a `?view=executive` URL parameter that renders a single-screen, print-friendly layout: 4 KPIs + equity trend charts + grain comparison + auto-generated plain-language "key findings" paragraph. No new data; layout-only.

### For the HS Civics / Statistics Student (Persona 6)

- **Guided tour mode** — a `?tour=1` URL parameter that adds a persistent banner above each tab with a sequential civic question and a "next" button. No new data; Streamlit session state + URL query params.
- **Narrative summary callout per tab** — a highlighted `st.info()` block at the top of each tab with a 2–3 sentence plain-English paragraph computed from live data values (e.g. "In 2024, majority-Black neighborhoods waited 11.4 days on average vs. 6.8 days in majority-White neighborhoods"). The single highest-impact change for this persona.
- **"Cite this data" collapsible** — pre-formatted APA citation in the sidebar with the data source, dashboard URL, and access date.

### For the Department Ops Manager (Persona 5)

- **Geographic performance choropleth for selected SRType** — second metric toggle on the Operations tab geographic map: "View by: Volume / Closure rate / Median days." All data already in `tract_srtype_metrics`; `build_choropleth()` already accepts any metric column. This is "which neighborhoods am I serving slowly?" — the manager's most operationally useful question.
- **SRType geographic outlier table** — when a SRType is selected, a ranked table of top-5 and bottom-5 CSAs by closure rate or median days. No pipeline change; filter the already-loaded geo×SRType DataFrame.

---

*Last updated: June 2026. Mark items `[x]` when done.*
