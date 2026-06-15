# Baltimore 311 Service Equity — Developer Context

## Mission

This dashboard provides operational visibility into Baltimore's 311 service request system for two audiences:

- **Citizens and advocates** — what requests are coming in, from where, and how does service delivery compare year over year and across neighborhood types
- **Internal stakeholders** — department managers (what is my service type doing, where, how fast) and citywide leadership (are we improving, are we equitable, how do we compare to peer cities)

Four comparison axes drive every design decision:
1. **Historical** — how does this year compare to prior years (2016–2025)
2. **Geographic** — which neighborhoods get faster / slower service, and why
3. **Cross-municipal** — how does Baltimore compare to peer cities on the same metrics *(Phase 5 — Service Delivery + Open-Data Maturity tabs live; per-city Service Equity in progress)*
4. **Equity** — does service quality differ systematically by race or income of the requesting neighborhood

The equity lens is not the only lens — operations clarity for managers is equally important and is the first tab.

---

## Active Branch

All current development is on `claude/review-requirements-AlGBm`. Push only to this branch unless told otherwise. The production app auto-deploys from `main` on Streamlit Community Cloud.

---

## App Structure

Streamlit app at `app/app.py`, organized into **two groups** that keep the two fundamentally different kinds of analysis distinct, selected by a top-level **`st.segmented_control`** (not `st.tabs`) so only the active group's body executes — `st.tabs` renders every tab body on every run, which made opening Compare cities pay the full cost of rendering the six within-Baltimore tabs (the Areas PCA embeddings + the Mix-Adjusted regression — ~30s cold) underneath:

- **🏙️ Within Baltimore** — the sequenced six-step story: Operations → Services → Area Service Usage → Equity → Service Equity → Mix-Adjusted Equity.
- **🌐 Compare cities** — *(Phase 5)* city-to-city comparison: Service Delivery → Service Equity → Maturity Index. **Service Delivery (`city_delivery.py`) and Maturity Index (`maturity_index.py`) are live**; Service Equity is still a placeholder (`cross_city.py`). Cohort = 10 cities across four platforms (ArcGIS, Carto, Socrata, CKAN). City-level only, so they do **not** use `geo_level`.

The year selector is global (above both groups) — cross-city data is also city × year. The **geographic-unit toggle (Census Tract / CSA) is a single global control at the top of the Within-Baltimore group**, writing the shared `geo_level` session state every within-Baltimore tab reads (replacing the former per-tab toggles and the two-way-sync hack). The Areas tab manages its own data loading internally and ignores `geo_level` (it shows tracts and CSAs together in one embedding).

### Operations tab (`app/components/operations_panel.py`)
- **Scope banner** — All requests received / Equity subset / Excluded; makes the filter explicit
- **KPI bar** — 4 headline metrics with year-over-year deltas (neutral color — direction is ambiguous)
- **Time series** — selected metric across all available years; clicking a point navigates to that year
- **SRType breakdown** — category pills (hyphen-prefix, e.g. SW-, HCD-) filter a selectable performance table; clicking a row shows two year-over-year bar charts (volume + median days to close) for that type
- **Geographic map** — request volume choropleth, filtered to selected SRType when a table row is active

### Areas tab (`app/components/area_embedding.py`)
- **View toggle** — "Demographic profile" / "Service usage" (horizontal radio); both views share one PCA coordinate space fit once on the union of tract and CSA data so both geo levels are directly comparable
- **Scatter plot** — tracts (small dots) and CSAs (large labeled bubbles) displayed together; ~10% of tract dots labeled with their NSA neighborhood name (min 3 per quadrant, farthest-point sampled); hover title shows "Neighborhood · Tract XXXX.XX". Light-filled quadrant rectangles (UL / UR / LL / LR — upper-left, upper-right, lower-left, lower-right; divided at median x and median y) sit behind the points
- **Service-usage view** — positions geographies by service-request mix (CLR-transformed high-level category shares + QuantileTransformer + PCA); colored by median household income. Animated year slider traces trajectories in a single stable coordinate system across all available years
- **Demographic view** — positions geographies by ACS 2023 demographic profile (race, income, age, education — RobustScaler + PCA); colored by predominant 311 service type for the selected year. No year animation (ACS is a single snapshot)
- **Quadrant assignment** — each geoid's mean (x, y) across all years determines its quadrant (UL / UR / LL / LR); stable even as individual year-points shift. Labels are positional, not geographic compass bearings
- **Predominant-subtype bar** — for each quadrant, % of tracts whose #1 SRType is each specific service subtype (e.g. "SW-Dirty Street"). Only subtypes that dominate at least one tract appear; top 8 globally + Other
- **Neighborhood list** — two-column table of CSA names grouped by quadrant (UL+UR left, LL+LR right); small text; updates with the active embedding view

### Equity tab (`app/app.py` → component calls)
- Choropleth map colored by selected metric; click a tract/CSA to see its summary panel
- Equity distributions — box-and-strip charts comparing majority-Black vs. majority-White geographies and above- vs. below-median income geographies for the selected metric
- Equity trend — year-over-year Mann-Whitney overlap scores for each metric and demographic dimension

---

## Data Pipeline

Headless pipeline at `scripts/pipeline.py`. Four stages, each independently runnable:

```bash
python scripts/pipeline.py --year 2024 --stage ingest        # ArcGIS → data/raw/
python scripts/pipeline.py --year 2024 --stage process       # clean + spatial join + aggregate
python scripts/pipeline.py --year 2024 --stage srtype        # SRType + geo×SRType metrics
python scripts/pipeline.py --year 2024 --stage adjusted      # per-geo mix-standardized metrics (needs process output)
python scripts/pipeline.py --stage demographics              # ACS race + income (run once)
python scripts/pipeline.py --year 2024                       # all stages in sequence
python scripts/pipeline.py --year 2026 --live                # current-year with 30-day right-censoring
```

GitHub Actions workflows:
- `update_data.yml` — single year, manual trigger
- `backfill.yml` — multiple years, sequential, 180s pause between years (configurable), skips year on ingest failure, commits after each year

### Data endpoints
- 2023–present: `311_Customer_Service_Requests_{YEAR}/FeatureServer/0`
- 2016–2022: `311_Customer_Service_Requests_Yearly/FeatureServer/{layer}` where layer = year − 2016
- Historical layers return Latitude/Longitude as strings — pipeline coerces to float

### Equity subset definition
Requests are included in the equity analysis subset if they are:
- **Resident-initiated**: MethodReceived ∈ {Phone, API, Mail, Email}
- **Geocoded**: valid Latitude/Longitude
- **Non-ECC**: SRType does not begin with "ECC-" (information calls, no service delivery)
- **Not right-censored**: CreatedDate more than 30 days before run date (live-year mode only)

Everything else (System/Internal source, ECC types, ungeocoded) is excluded from equity metrics but counted in the "All requests received" scope banner.

---

## Processed File Inventory (`data/processed/`)

| File | Grain | Contents |
|------|-------|----------|
| `tract_metrics_{year}.parquet` | tract × year | total_requests, closure_rate, median_days_to_close, on_time_rate, requests_per_1k, top_sr_type |
| `csa_metrics_{year}.parquet` | CSA × year | same as tract |
| `citywide_metrics_{year}.parquet` | year | canonical **pooled** citywide metrics over the equity subset (total_requests, closed_requests, closure_rate, median_days_to_close, on_time_rate) — single source of truth shared by the Operations citizen-initiated figure and the cross-city Baltimore row |
| `srtype_metrics_{year}.parquet` | SRType × year | total_requests, closed_requests, closure_rate, median_days_to_close, on_time_rate, pct_resident_initiated |
| `tract_srtype_metrics_{year}.parquet` | tract × SRType × year | total_requests, closed_requests, closure_rate, median_days_to_close |
| `csa_srtype_metrics_{year}.parquet` | CSA × SRType × year | same as tract_srtype |
| `tract_adjusted_metrics_{year}.parquet` | tract × year | n_obs, adj_median_days_to_close, adj_closure_rate, ref_median_days_to_close, ref_closure_rate — mix-standardized (direct standardization to citywide mix, record-level) for Tab 6 |
| `csa_adjusted_metrics_{year}.parquet` | CSA × year | same as tract_adjusted; CSA = population-weighted rollup of tract adjusted values |
| `tract_boundaries.geojson` | — | Census 2020 tract boundaries for Baltimore City (FIPS 510) |
| `csa_boundaries.geojson` | — | CSA boundaries dissolved from tract polygons via BNIA crosswalk |
| `tract_demographics.csv` | tract | pct_black, pct_white, median_income (ACS 2023 5-year; year-independent) |
| `csa_demographics.csv` | CSA | population-weighted rollup of tract demographics |
| `peer_city_metrics.parquet` | city × year | cross-city delivery metrics (total_requests, requests_per_1k, median_days_to_close, closure_rate, on_time_rate, pct_same_day_close, population, closure_definition) — Phase 5, built by `scripts/peer_city.py` |
| `peer_city_meta.csv` | city | fips, ACS population, portal_url, closure_definition |
| `peer_city_maturity.csv` | city | 311 open-data publishing maturity scorecard — all 45 metros, 9 rubric dimensions 0–3 + in_cohort/status/evidence/derived; 6 hand-scored anchors, the rest derived from the census by `scripts/score_maturity.py` (inaccessible cities → 0). Phase 5.8/5.9 |
| `peer_city_coverage_census.csv` | city | scoreable/partial/unconfirmed status of the 40 largest US cities + 5 mid-size enablers, each with an `evidence` tier (api/city_docs/third_party/none) and `endpoint_url` — Phase 5.8, verified canvass (`scripts/verify_census.py` re-probes the live endpoints) |

`data/raw/` and `data/interim/` are gitignored and rebuilt by the pipeline.

Geo ID conventions: tract files use 11-digit GEOID strings in a `geoid` column. CSA files use the CSA name string in a `geoid` column (matching `properties.csa_name` in the GeoJSON).

---

## Key Decisions and Conventions

**Overlap score**: Mann-Whitney probability of superiority, `1 − 2 × |P(A > B) − 0.5|`. Ranges 0–1; 1 = fully interleaved distributions, 0 = complete separation. Implemented in `app/components/utils.py:overlap_score()`. Thresholds: >0.7 "not bad", >0.4 "could be better", ≤0.4 "needs review". Requires ≥3 non-null values per group; returns NaN otherwise.

**Delta colors**: all year-over-year deltas in the Operations tab use `delta_color="off"` (neutral). A decrease in days-to-close is good; a decrease in requests could be good or bad. Direction is left for the reader to interpret.

**Auto-close contamination flag (cross-city)**: many open 311 systems close referral/duplicate/invalid records the instant they open (NYC/Chicago have a ~0-day pooled median for exactly this reason — the same instant-close contamination Baltimore excludes via its ECC/scope filter, but other cities have no equivalent prefix to strip). The cross-city median calc is *correct*; the data is contaminated. Rather than apply arbitrary per-city exclusions, `compute_city_metrics` records `pct_same_day_close` (share of closed requests closing in 0 days), and the Service Delivery tab flags any city with ≥50% same-day closes, a sub-day median, or ≥99% closure (`_quality_flags` in `city_delivery.py`) — marked ⚠ on the bar with a per-city reason, so implausible/gamed figures are surfaced, not silently trusted. The metro-ranking work (P5.9) folds the same plausibility check into scoring.

**Sparse cell suppression**: `_MIN_GEO_SRTYPE_N = 5` in `operations_panel.py`. Geo × SRType cells with fewer than 5 requests are filtered out in the UI before map rendering. Threshold is a UI constant — change it without rerunning the pipeline.

**CSA rollup**: at CSA level, metric values are population-weighted means of tract values (not re-aggregated from raw records). This matches BNIA Vital Signs methodology.

**Cross-city per-1k denominator**: a city 311 system serves the city proper, so `requests_per_1k` uses the **Census place** population when an adapter sets `place_fips` (Chicago/Austin/KC/Boston, whose county is much larger than the city), falling back to the **county** (`fips`) where county ≈ city (SF, Philadelphia, Baltimore, DC, Nashville). NYC sums its five boroughs. Driver logic in `peer_city.resolve_population`; `fetch_place_population` / `fetch_county_population` in `peer_metrics`.

**Canonical citywide median is a record-level *pooled* median — one source of truth.** `metrics.citywide_pooled_metrics(df_eq)` computes it over the equity subset in the `process` stage and writes `citywide_metrics_{year}.parquet` ("half of all resident requests close within X days"). Both consumers read that same file, so they never disagree: the Operations tab's **citizen-initiated** figure (`operations_panel._build_equity_citywide_ts`, with a legacy weighted-mean fallback for years not yet regenerated) and the **cross-city** Baltimore row (`BaltimoreAdapter.precomputed` — which also skips the ~12-min re-fetch). DC and other external cities compute the *same* pooled median from their own records. The pooled median is the only measure DC can match (no tract join), and it's more intuitive than the old geographic aggregate, so it is canonical everywhere. **Exception:** the Operations "all requests received" headline stays a geographic weighted-mean of per-SRType medians — a naive pooled median over *all* requests is ~0 because ECC information-calls close instantly (the same contamination the cross-city scope excludes). Requires the pipeline `process` stage to have been re-run; until then the citizen-initiated figure uses the fallback.

**Streamlit version**: must be ≥1.40.0 for `st.pills()` (added in 1.40) and `st.dataframe(on_select="rerun", selection_mode="single-row")`.

**Secrets**: Mapbox token in Streamlit Cloud Secrets (`mapbox.token`), never in repo. Census API key as GitHub Actions secret `CENSUS_API_KEY`, never in repo. `SOCRATA_APP_TOKEN` as an optional GitHub Actions secret — passed to the Socrata cities (NYC/Chicago/SF/Austin/Nashville/KC) to lift anonymous rate-limiting; the adapter works without it (just throttled), so it degrades gracefully if unset.

---

## Roadmap Summary

See `TASKS.md` for full detail. Current phase status:

| Phase | What | Status |
|-------|------|--------|
| 0–3 | Data investigation, pipeline, MVP app, Operations tab | Complete |
| 4 / 4d | SRType-stratified equity — six-tab arc (Services, Areas, Service Equity, Mix-Adjusted Equity) | Complete — all tabs shipped |
| 4e | Per-geography mix-adjusted metrics (record-level direct-standardization `adjusted` stage) | Stage shipped — Tab 6 consumes it; P4e-3→5 (Equity-tab surfacing) open |
| 4b | Area Analysis tab — peer comparison for managers | Candidate next release |
| 5 | Cross-municipality benchmarking | In progress — Delivery + Maturity tabs live; 10-city cohort across 4 platforms (ArcGIS/Carto/Socrata/CKAN); Baltimore+DC+Philadelphia data landed, Socrata/CKAN cities pending CI; per-city Service Equity (5.5/5.6) next |
| 6 | Seasonality tab | Long-term |

Key open investigations before heavy Phase 4 / 5 work:
- **TD-2**: Manually validate Mann-Whitney scores and demographic calculations
- **TD-3**: Personas and use-case review — validates whether regression panel and reference city deep dive are worth building for the actual audience
- **TD-4**: Cross-year duplicate SRRecordID check

---

## Repository Layout

```
app/
  app.py                          # Entrypoint — tabs, year selector, sidebar, data loading
  requirements.txt                # streamlit≥1.39, pandas, plotly, pyarrow
  components/
    map_view.py                   # build_choropleth() — shared by both tabs
    summary_panel.py              # Click-to-select detail card (Equity tab)
    equity_distributions.py       # Race + income distribution comparison
    equity_trend.py               # Year-over-year overlap score trend
    operations_panel.py           # Full Operations tab
    city_delivery.py              # Cross-City Service Delivery tab (Phase 5)
    maturity_index.py             # 311 Open-Data Maturity tab (Phase 5.8)
    utils.py                      # overlap_score, score_label, format_metric, hex_to_rgba

scripts/
  pipeline.py                     # Headless pipeline — all stages (within-Baltimore)
  peer_city.py                    # Cross-city ingestion + metrics (Phase 5)
  score_maturity.py               # Derive the 45-metro maturity scorecard from the census (Phase 5.9)
  verify_census.py                # Re-probe census endpoints to refresh the api evidence tier (Phase 5.8)

src/balt311/
  ingest.py                       # ArcGIS FeatureServer pagination (Baltimore)
  metrics.py                      # Cleaning, aggregation, CSA rollup, demographics rollup
  peer_metrics.py                 # City-agnostic cross-city delivery metrics + ACS county pop
  cities/                         # Per-city adapters: base, arcgis + carto + socrata + ckan (reusable clients),
                                  #   baltimore, dc, philadelphia, nyc, chicago, sf, austin, nashville, kansas_city, boston

.github/workflows/
  update_data.yml                 # Single-year workflow
  backfill.yml                    # Multi-year sequential backfill
  peer_city.yml                   # Cross-city metrics, single year (Phase 5)
  peer_city_backfill.yml          # Cross-city metrics, multi-year sequential (Phase 5)
  peer_city_matrix.yml            # Cross-city metrics, one job PER CITY in parallel + single merge/commit (Phase 5)

data/processed/                   # Committed — app reads only from here
data/raw/                         # Gitignored
data/interim/                     # Gitignored

TASKS.md                          # Full task list and roadmap
personas.md                       # User personas and roadmap priority matrix
requirements.md                   # Original requirements spec (living document)
README.md                         # Public-facing documentation
```
