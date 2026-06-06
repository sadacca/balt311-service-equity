# Baltimore 311 Service Equity

Baltimore's 311 system receives hundreds of thousands of resident service requests each year — potholes, bulk trash, water leaks, rodent control. This dashboard provides operational visibility into those interactions for two audiences:

- **Citizens and advocates** — what requests are coming in, from where, and how does service delivery compare year over year and across neighborhood types
- **Internal stakeholders** — department managers tracking their service types and citywide leadership asking whether performance is improving, equitable, and competitive with peer cities

Four comparison axes structure the analysis:

1. **Historical** — how does this year compare to prior years (2016–2025)?
2. **Geographic** — which neighborhoods get faster or slower service, and why?
3. **Cross-municipal** — how does Baltimore compare to peer cities on the same metrics?
4. **Equity** — does service quality differ systematically by race or income of the requesting neighborhood?

The equity lens is not the only lens — operational clarity for managers is equally important and is the first tab.

**[Live dashboard → balt311equity.streamlit.app](https://balt311equity.streamlit.app/)**

---

## How this dashboard tells its story

311 data answers very different questions depending on who's asking. A council member wants to know whether the gaps in their district are typical, or worse, than similar neighborhoods elsewhere. A department manager wants to know how their service type is performing — without wading through demographic framing that isn't theirs to interpret. A journalist or citywide official wants a defensible answer to "is service delivery equitable, and if not, which services and neighborhoods are driving that gap?" Rather than build one view that tries to answer all of these at once, the dashboard is structured as a sequence of lenses, each a complete answer for one audience that also sets up the next. Four tabs are live today, in the order the app presents them; two more are planned for a future release (`Phase 4d`/`4e`, see `TASKS.md`) to complete the arc:

1. **Operations** *(live — first tab)* — the citywide health check: KPIs, year-over-year trends, and a request-volume map answer "how is the city doing, overall, this year vs. prior years?" The landing view for anyone — resident, manager, or official — who wants the big picture before drilling into anything else.
2. **Services** *(live)* — the operations manager's deep dive, with the equity framing deliberately stripped out: how does my service category compare to others, and how has it performed across time? The tool a department head reaches for when the question is "how am I doing," not "how does this break down by race or income."
3. **Area Embedding — service usage by geography** *(planned, aka "Service Category Usage by Geographic Area")* — the bridge from *what* to *where*, and the dashboard's answer to the most commonly requested comparison: "areas like mine." Every tract or CSA is placed in two complementary spaces — what services it requests, and who lives there — and each space is clustered into named, reusable peer groups. That turns "compare my area to the citywide average" into "compare my area to the handful of neighborhoods that actually resemble it," for council members and managers alike.
4. **Equity** *(live)* — the citywide equity check: does service quality differ systematically by race or income, citywide, this year and over time? The headline question for journalists, advocates, and citywide leadership, answered with maps, distribution comparisons, and a multi-year trend of the Mann-Whitney overlap score.
5. **Service Equity** *(live)* — does the citywide equity picture hold up within individual service categories, or does it mask very different stories for potholes vs. bulk trash vs. rodent control? It turns out to mask something real: scored within individual categories — and within individual service types — equity scores run substantially higher than the citywide aggregate, evidence that a meaningful share of the apparent citywide gap reflects *which* services different neighborhoods request (a usage-mix effect) rather than *how* any one service is delivered once requested. The improvement isn't total, though — some disparity persists even at that finer grain, so the citywide number still matters; it just needs this view to interpret correctly. The tool a journalist reaches for when the citywide number raises more questions than it answers.
6. **Equity Adjusted for Service Mix** *(planned)* — the most defensible version of the equity claim, formalizing what tab 5 already surfaces informally: are the gaps explained by *which* services an area happens to request (a structural, type-mix effect), or by *how* the same service is delivered to different neighborhoods (the cleaner equity signal)? A stratified, volume-weighted score paired with a regression panel gives citywide officials and journalists two independent lines of evidence for the same conclusion — the kind of rigor a contested public claim needs to hold up.

Read top to bottom, the live tabs already trace a meaningful arc: an **operational overview** anyone can use, an **operational deep-dive** built for the people who run individual services, a **citywide equity check**, and then that same equity lens re-scored by service category — where the most important finding surfaces so far. **Area Embedding** and **Equity Adjusted for Service Mix** remain planned and would extend the arc further: a peer-grouped geographic understanding of the city ("neighborhoods like mine"), and a formal separation of the type-mix effect from the cleaner delivery-equity signal tab 5's analysis already hints at. No two adjacent tabs require a conceptual leap; each answers a real, documented need (see `personas.md` for the five personas and the gaps each tab closes) and hands the reader naturally to the next question — several different lenses for several different audiences, all aimed at the same underlying question: is Baltimore delivering 311 service in a way that's fast, fair, and consistent across every neighborhood, and where it isn't, exactly where and why?

---

## What it shows

### Operations tab

The default tab answers "how is Baltimore 311 performing overall?" before asking equity questions.

**City-wide Performance**

A KPI bar shows four headline metrics — Requests received, Median days to close, Closure rate, On-time rate — each with a year-over-year delta badge (neutral color). Directly beneath each tile, a small caption shows the citizen-initiated equivalent (Phone / API / Mail / Email requests only), so both the all-requests picture and the resident-experience picture are visible at a glance. A `Δ vs. {year}` caption notes the comparison year.

An inline metric selector (horizontal radio) above the time series switches between Median days to close, Closure rate, and On-time rate. Below it, a dual-trace time series shows both "All requests" (solid blue) and "Citizen-initiated" (dashed orange) for the selected metric across all available years (2016–2025). Clicking any point navigates to that year.

**Breakdown by Request Type**

Category pills (SW, HCD, TRS, etc.) filter the table by service department prefix. The performance table shows every SRType with request volume, closure rate, median days to close, on-time rate, and percent resident-initiated. Clicking any row selects that type and populates two year-over-year bar charts below: total requests by year and median days to close by year, with the selected year highlighted in red.

**Geographic Distribution**

A choropleth map at the bottom shows request volume by census tract or CSA. A "View as: Census Tract / CSA" toggle above the map switches the geographic unit. The map uses a sequential Blues colorscale from 0 to the maximum count (not a diverging scale). When a table row is selected the map filters to show counts for that specific SRType only (sourced from `{geo_key}_srtype_metrics_{year}.parquet`). Cells with fewer than 5 requests are suppressed to avoid displaying statistically unreliable counts.

---

### Services tab

A pure operational drill-down into Baltimore's service categories — usage volume, closure rate, time to close — with no race or income framing. Built for department managers and anyone who wants to compare how individual service types perform, independent of demographic context.

**Among-category comparison** — year-over-year multi-line trends for the highest-volume categories: usage (log scale, since volume spans orders of magnitude across departments), closure rate, and median days to close, each with a dashed citywide-average reference line so a category can be read against the city as a whole, not just its peers.

**Category drill-down** — a two-tier selector (top categories shown by acronym with a legend, the rest tucked behind an expander and labeled by full department name) reveals that category's own year-over-year trend (volume + days to close), plus a within-category breakdown by subtype: the highest-volume types individually, with the remainder folded into "all other types" so high-cardinality categories like Solid Waste stay readable.

---

### Equity tab — Map

Three inline controls above the map: geographic unit toggle (Census Tract / CSA), metric selectbox (Color map by), and an optional filter by the geography's top request type. Four equity metrics are available:

| Metric | Description |
|---|---|
| Median days to close | How long closed requests took, at the tract/CSA median |
| Closure rate | Share of requests that reached closed status |
| On-time rate | Share of closed requests resolved by their SRType due date |
| Requests per 1,000 residents | Normalized demand; highlights under- and over-served areas |

Clicking any tract or CSA opens a summary panel. The color scale is centered on the citywide median so above/below-average areas read immediately.

**Scope**: resident-initiated requests only (MethodReceived ∈ Phone, API, Mail, Email). ECC information calls, city-proactive inspections, and staff-logged requests are excluded — they don't reflect resident-experienced service delivery.

### Equity by Demographics

Below the map, two side-by-side distribution panels compare each metric across demographic groups for the selected year and geography level:

- **Race**: majority-Black geographies (>50% Black population) vs. majority-White (>50% White population)
- **Income**: geographies below vs. above the citywide median household income

Each panel shows a box-and-strip chart — individual tracts or CSAs as points, with the interquartile range (25th–75th percentile) and median marked. A **Mann-Whitney overlap score** summarizes how similar the two distributions are across the full range of values (not just the middle):

| Score | Label | Meaning |
|---|---|---|
| > 0.7 | not bad | Distributions substantially interleaved |
| 0.4–0.7 | could be better | Meaningful separation; warrants monitoring |
| < 0.4 | needs review | Substantial disparity between groups |

The score and charts update automatically when the metric selector changes.

### Equity Trend

A year-over-year line chart tracks the Mann-Whitney overlap score for each metric across all available years (2016–2025), separately for race-based and income-based comparisons. Rising scores indicate narrowing disparity; falling scores indicate widening disparity.

---

### Service Equity tab

The equity-flavored mirror of the Services tab: the same multi-line trend language — top-N categories, top-N subtypes folded into an "all other" remainder, a two-tier selector, a dotted year guide — but tracking the **Mann-Whitney equity score** (race and income overlap, on the same fixed 0–100% scale and green/amber/red bands as the Equity Trend chart) instead of operational metrics.

**The headline finding**: scored citywide across every service type pooled together, equity scores can run notably lower than the same metric scored within individual categories, or within individual service types — direct evidence that part of the apparent citywide gap reflects *which* services different neighborhoods request (a usage-mix effect) rather than *how* any one service is delivered once requested. The improvement at finer grain is real but not total — some disparity persists even after accounting for service mix, so the citywide number still matters; it just needs this finer-grained view to interpret correctly. The tab states this comparison directly, with the current year's actual scores, right where the panels begin.

**Among-category equity trend** — multi-line equity-score trends for the highest-volume categories, read against a dashed "All categories" reference line and the same threshold bands as the citywide Equity Trend.

**Category drill-down** — select a category (the same two-tier selector as the Services tab) to see its own equity-score trend against the all-categories baseline, plus a within-category breakdown of equity scores by subtype.

---

## Data sources

| Source | What | How accessed |
|---|---|---|
| [Baltimore Open Data](https://data.baltimorecity.gov) | 311 service requests 2016–2025 | ArcGIS FeatureServer REST API (annual files 2023+; `311_Customer_Service_Requests_Yearly` layers for 2016–2022) |
| [Census Bureau GENZ2023](https://www.census.gov/geographies/mapping-files/time-series/geo/cartographic-boundary.html) | Census tract boundaries (2020 definitions) | Cartographic boundary shapefile ZIP |
| [BNIA VitalSigns](https://github.com/BNIA/VitalSigns) | Tract → CSA crosswalk | GitHub raw CSV |
| [Census ACS 2023 5-Year](https://www.census.gov/data/developers/data-sets/acs-5year.html) | Tract population (B01003), race (B02001), median household income (B19013) | Census Data API |

---

## Architecture

```
GitHub Actions (manual trigger)
        │
        ▼
┌─────────────────────────────────────────────────────────┐
│ Job 1 — Ingest                                          │
│  ArcGIS FeatureServer → raw Parquet → workflow artifact │
└───────────────────┬─────────────────────────────────────┘
                    │ artifact
                    ▼
┌─────────────────────────────────────────────────────────┐
│ Job 2 — Process                                         │
│  Clean → spatial join (tracts) → aggregate              │
│  + ACS population → requests_per_1k                     │
│  + ACS race + income → tract/csa_demographics.csv       │
│  + BNIA crosswalk → CSA rollup                          │
│  + srtype stage → srtype_metrics + geo×SRType metrics   │
│  Commits data/processed/ to main                        │
└─────────────────────────────────────────────────────────┘
                    │
                    ▼
         Streamlit Community Cloud
         reads data/processed/ from main
```

The two-job design lets the process stage be re-run independently (Actions → Re-run failed jobs) without re-fetching the full dataset. Demographic reference files (`tract_demographics.csv`, `csa_demographics.csv`) are generated once and committed — the pipeline skips regeneration on subsequent runs.

A separate **backfill workflow** (`backfill.yml`) processes multiple years in one dispatch: sequential loop, 180-second pause between years to limit ESRI server load, commits after each year so partial runs are preserved.

---

## Repository layout

```
app/
  app.py                    # Streamlit entrypoint — tabs, year selector, data loading
  requirements.txt          # App-only deps (streamlit≥1.39, pandas, plotly, pyarrow)
  components/
    map_view.py             # Plotly choropleth_mapbox builder
    summary_panel.py        # Click-to-select detail panel (Equity tab)
    equity_distributions.py # Race + income distribution comparison charts
    equity_trend.py         # Year-over-year overlap score trend chart
    operations_panel.py     # Operations tab: KPI bar, time series, SRType table, map
    utils.py                # Shared: overlap_score, score_label, format_metric

data/
  processed/                # Committed — read by the app at runtime
    tract_metrics_{year}.parquet          # Tract-level equity metrics
    csa_metrics_{year}.parquet            # CSA-level equity metrics
    srtype_metrics_{year}.parquet         # City-wide metrics per SRType
    tract_srtype_metrics_{year}.parquet   # Tract × SRType: requests + performance
    csa_srtype_metrics_{year}.parquet     # CSA × SRType: requests + performance
    tract_boundaries.geojson
    csa_boundaries.geojson
    tract_demographics.csv  # ACS race + income by tract (year-independent)
    csa_demographics.csv    # CSA rollup of tract demographics
  raw/                      # Gitignored — rebuilt by pipeline
  interim/                  # Gitignored — rebuilt by pipeline

scripts/
  pipeline.py               # Headless pipeline: --stage ingest/process/srtype/demographics

src/balt311/
  ingest.py                 # ArcGIS FeatureServer pagination
  metrics.py                # Cleaning, aggregation, CSA rollup, demographics rollup

notebooks/
  01_ingest.ipynb
  02_clean.ipynb
  03_aggregate.ipynb

.github/workflows/
  update_data.yml           # Single-year manual-trigger workflow
  backfill.yml              # Multi-year sequential backfill workflow
```

---

## Updating the data

**Single year**: Actions → Update 311 processed data → Run workflow. Select the year and whether it is a live (partial) year. For a live current year, enable **"Live current-year file"** — this applies 30-day right-censoring to exclude recently-created requests that haven't had time to close.

**Multiple years (backfill)**: Actions → Backfill 311 data — multiple years → Run workflow. Default processes all years 2016–2025 sequentially with a 180-second pause between each to limit ESRI server load. Editable at dispatch time — trim the year list or adjust the pause as needed.

The demographic reference files (`tract_demographics.csv`, `csa_demographics.csv`) are generated automatically on the first process run and do not need to be regenerated annually — they are committed to the repo and reused across all years.

Required repository secrets:

| Secret | Purpose |
|---|---|
| `CENSUS_API_KEY` | Census Data API key for ACS population, race, and income download — free at [api.census.gov/data/key_signup.html](https://api.census.gov/data/key_signup.html) |

---

## Running locally

```bash
git clone https://github.com/sadacca/balt311-service-equity
cd balt311-service-equity

pip install -r requirements.txt

# Add your Mapbox token
cp .streamlit/secrets.toml.example .streamlit/secrets.toml
# edit .streamlit/secrets.toml

streamlit run app/app.py
```

To run the full pipeline locally (requires the ArcGIS endpoints to be reachable):

```bash
python scripts/pipeline.py --year 2025
python scripts/pipeline.py --year 2026 --live   # current-year with right-censoring
```

---

## Metric definitions

**Equity subset**: resident-initiated (MethodReceived ∈ {Phone, API, Mail, Email}), non-ECC-prefix SRType, geocoded, not right-censored.

**Median days to close**: computed on closed requests only; sub-second negatives (timestamp precision artifacts in same-day closures) are floored to 0. At CSA level: population-weighted mean of tract medians.

**Closure rate**: closed / total requests. "Closed (Transferred)" counts as closed.

**On-time rate**: closed requests with CloseDate ≤ DueDate, as a share of all closed requests where DueDate > CreatedDate. SRTypes where DueDate < CreatedDate are excluded (known data artifact). Open requests are not counted as late.

**Requests per 1,000 residents**: total equity-subset requests / ACS 2023 5-year tract population × 1,000.

**Mann-Whitney overlap score**: `1 - 2 × |P(A > B) - 0.5|` across all pairwise comparisons between the two demographic groups. Score of 1.0 means the groups are perfectly interleaved; 0.0 means one group is entirely above the other. More sensitive than IQR overlap to tail differences and systematic shifts when medians are close. Requires ≥ 3 non-null values per group; returns NaN otherwise. Computed separately for race-based and income-based comparisons, for each equity metric.

**Demographic classification**: race groups require >50% of tract/CSA population identifying as a single race (mixed tracts excluded from race comparison). Income groups split at the citywide median of the tract/CSA distribution for the selected year and geography level.
