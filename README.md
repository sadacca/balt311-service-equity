# Baltimore 311 Service Equity

Baltimore's 311 system receives hundreds of thousands of resident service requests each year — potholes, bulk trash, water leaks, rodent control — but whether those requests get resolved at the same speed regardless of neighborhood is an open question. This dashboard makes that question answerable. It maps resolution metrics at the census tract and community level and tests directly whether outcomes differ between majority-Black and majority-White neighborhoods, and between lower- and higher-income areas.

**[Live dashboard → balt311equity.streamlit.app](https://balt311equity.streamlit.app/)**

---

## What it shows

### Map

Four equity metrics, switchable from the sidebar:

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

Each panel shows a box-and-strip chart — individual tracts or CSAs as points, with the interquartile range (25th–75th percentile) and median marked. An **IQR overlap score** summarizes how similar the two distributions are:

| Score | Label | Meaning |
|---|---|---|
| > 60% | not bad | The two groups' middle ranges largely overlap |
| 30–60% | could be better | Meaningful separation; warrants monitoring |
| < 30% | needs review | Substantial disparity between groups |

The score and charts update automatically when the metric selector changes.

### Equity Trend

A year-over-year line chart tracks the IQR overlap score for each metric from 2023 onward, separately for race-based and income-based comparisons. Rising scores indicate narrowing disparity; falling scores indicate widening disparity.

---

## Data sources

| Source | What | How accessed |
|---|---|---|
| [Baltimore Open Data](https://data.baltimorecity.gov) | 311 service requests 2023–2025 | ArcGIS FeatureServer REST API |
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
│  Commits data/processed/ to main                        │
└─────────────────────────────────────────────────────────┘
                    │
                    ▼
         Streamlit Community Cloud
         reads data/processed/ from main
```

The two-job design lets the process stage be re-run independently (Actions → Re-run failed jobs) without re-fetching the full dataset. Demographic reference files (`tract_demographics.csv`, `csa_demographics.csv`) are generated once and committed — the pipeline skips regeneration on subsequent runs.

---

## Repository layout

```
app/
  app.py                    # Streamlit entrypoint
  requirements.txt          # App-only deps (streamlit, pandas, plotly, pyarrow)
  components/
    map_view.py             # Plotly choropleth_mapbox builder
    summary_panel.py        # Click-to-select detail panel
    equity_distributions.py # Race + income distribution comparison charts
    equity_trend.py         # Year-over-year overlap score trend chart
    utils.py                # Shared: overlap_score, score_label, format_metric

data/
  processed/                # Committed — read by the app
    tract_metrics_{year}.parquet
    csa_metrics_{year}.parquet
    tract_boundaries.geojson
    csa_boundaries.geojson
    tract_demographics.csv  # ACS race + income by tract (year-independent)
    csa_demographics.csv    # CSA rollup of tract demographics
  raw/                      # Gitignored — rebuilt by pipeline
  interim/                  # Gitignored — rebuilt by pipeline

scripts/
  pipeline.py               # Headless pipeline (ingest / process / all)

src/balt311/
  ingest.py                 # ArcGIS FeatureServer pagination
  metrics.py                # Cleaning, aggregation, CSA rollup, demographics rollup

notebooks/
  01_ingest.ipynb
  02_clean.ipynb
  03_aggregate.ipynb

.github/workflows/
  update_data.yml           # Manual-trigger Actions workflow
```

---

## Updating the data

Trigger the workflow manually from **Actions → Update 311 processed data → Run workflow**. Select the year and whether it is a live (partial) year.

For a live current year, enable **"Live current-year file"** — this applies 30-day right-censoring to exclude recently-created requests that haven't had time to close, which would otherwise deflate closure rates.

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

**IQR overlap score**: for any two demographic groups, the fraction of the combined interquartile range that the two IQR bands share. 0% = no overlap (complete separation); 100% = identical distributions. Computed separately for race-based and income-based comparisons, for each equity metric.

**Demographic classification**: race groups require >50% of tract/CSA population identifying as a single race (mixed tracts excluded from race comparison). Income groups split at the citywide median of the tract/CSA distribution for the selected year and geography level.
