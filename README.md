# Baltimore 311 Service Equity

An interactive dashboard exploring whether Baltimore City's 311 service request resolution varies by neighborhood. Resident-initiated requests are mapped and aggregated at the census tract and Community Statistical Area (CSA) level, with metrics designed to surface disparities in responsiveness across the city.

**[Live dashboard → balt311equity.streamlit.app](https://balt311equity.streamlit.app/)**

---

## What it shows

Four equity metrics, switchable from the sidebar:

| Metric | Description |
|---|---|
| Median days to close | How long closed requests took, at the tract/CSA median |
| Closure rate | Share of requests that reached closed status |
| On-time rate | Share of closed requests resolved by their SRType due date |
| Requests per 1,000 residents | Normalized demand; highlights under- and over-served areas |

Clicking any tract or CSA opens a summary panel. The color scale is centered on the citywide median so above/below average areas read immediately.

**Scope**: resident-initiated requests only (MethodReceived ∈ Phone, API, Mail, Email). ECC information calls, city-proactive inspections, and staff-logged requests are excluded — they don't reflect resident-experienced service delivery.

---

## Data sources

| Source | What | How accessed |
|---|---|---|
| [Baltimore Open Data](https://data.baltimorecity.gov) | 311 service requests 2024–2025 | ArcGIS FeatureServer REST API |
| [Census Bureau GENZ2023](https://www.census.gov/geographies/mapping-files/time-series/geo/cartographic-boundary.html) | Census tract boundaries (2020 definitions) | Cartographic boundary shapefile ZIP |
| [BNIA VitalSigns](https://github.com/BNIA/VitalSigns) | Tract → CSA crosswalk | GitHub raw CSV |
| [Census ACS 2023 5-Year](https://www.census.gov/data/developers/data-sets/acs-5year.html) | Tract population (B01003) | Census Data API |

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
│  + BNIA crosswalk → CSA rollup                          │
│  Commits data/processed/ to main                        │
└─────────────────────────────────────────────────────────┘
                    │
                    ▼
         Streamlit Community Cloud
         reads data/processed/ from main
```

The two-job design lets the process stage be re-run independently (Actions → Re-run failed jobs) without re-fetching the full dataset.

---

## Repository layout

```
app/
  app.py                    # Streamlit entrypoint
  requirements.txt          # App-only deps (streamlit, pandas, plotly, pyarrow)
  components/
    map_view.py             # Plotly choropleth_mapbox builder
    summary_panel.py        # Click-to-select detail panel

data/
  processed/                # Committed — read by the app
    tract_metrics_{year}.parquet
    csa_metrics_{year}.parquet
    tract_boundaries.geojson
    csa_boundaries.geojson
  raw/                      # Gitignored — rebuilt by pipeline
  interim/                  # Gitignored — rebuilt by pipeline

scripts/
  pipeline.py               # Headless pipeline (ingest / process / all)

src/balt311/
  ingest.py                 # ArcGIS FeatureServer pagination
  metrics.py                # Cleaning, aggregation, CSA rollup

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

Required repository secrets:

| Secret | Purpose |
|---|---|
| `CENSUS_API_KEY` | Census Data API key for ACS population download — free at [api.census.gov/data/key_signup.html](https://api.census.gov/data/key_signup.html) |

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
