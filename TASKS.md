# Task List: 311 Service Equity Dashboard

Ordered by dependency. Complete data investigation tasks before building on their findings.

---

## Phase 0 — Data Investigation (run locally, network required)

- [ ] **P0-1: Run `validate_2025_sample.ipynb`** — execute all cells and record outputs
  - What is the `MethodReceived` value set? Is staff-vs-resident distinction present?
  - What percentage of records have valid lat/lon?
  - Do any `LastActivity` values signal reopen events?
  - What is the `days_to_close` distribution? Any negative values?
  - Does `SRStatus` == "Closed" correlate cleanly with `CloseDate` presence?

- [ ] **P0-2: Run `01_ingest.ipynb` for 2024** — download full 2024 dataset to `data/raw/`
  - Record total record count
  - Confirm all fields from the validation notebook are present

- [ ] **P0-3: Run `01_ingest.ipynb` for 2025** — download full 2025 dataset to `data/raw/`
  - Note: 2025 FeatureServer may be the "current year / rolling" endpoint

- [ ] **P0-4: Download census tract boundaries** — TIGER/Line for Baltimore City (FIPS 24510)
  - Save to `data/raw/baltimore_tracts.geojson`
  - One-time command in `02_clean.ipynb` → markdown cell 3

- [ ] **P0-5: Download CSA boundaries** — from BNIA or Open Baltimore
  - Save to `data/raw/baltimore_csas.geojson`
  - See `geo_reference.md` for source URLs

- [ ] **P0-6: Build tract→CSA crosswalk** — columns: `geoid, csa_name, population`
  - Save to `data/raw/tract_to_csa.csv`
  - BNIA provides the canonical mapping; ACS B01003 supplies tract populations
  - See `geo_reference.md` for construction method

---

## Phase 1 — Pipeline (run locally after P0)

- [ ] **P1-1: Run `02_clean.ipynb` for 2024**
  - Verify spatial join yield (expect ≥ 95% of geocoded records matched to a tract)
  - Check `days_to_close` negatives and outliers
  - Output: `data/interim/requests_2024_clean.parquet`

- [ ] **P1-2: Run `03_aggregate.ipynb` for 2024**
  - Enable ACS merge (uncomment Census API cells; obtain free key)
  - Verify `requests_per_1k` is computable for all tracts
  - Output: `data/processed/tract_metrics_2024.parquet`, `csa_metrics_2024.parquet`

- [ ] **P1-3: Copy boundary GeoJSONs to `data/processed/`**
  - `data/processed/tract_boundaries.geojson`
  - `data/processed/csa_boundaries.geojson`
  - (Done automatically by last cell of `03_aggregate.ipynb`)

- [ ] **P1-4: Commit `data/processed/` files to the repo**
  - These are the only data files checked in; raw and interim remain gitignored
  - Verify files are under 50 MB total (GitHub limit per push is 100 MB)

---

## Phase 2 — App Development

- [ ] **P2-1: Obtain Mapbox free-tier token**
  - Create account at mapbox.com → Tokens page → copy default public token
  - Create `.streamlit/secrets.toml` locally (gitignored) using the `.example` template

- [ ] **P2-2: Install dependencies and run app locally**
  - `pip install -r requirements.txt`
  - `streamlit run app/app.py`
  - Verify map renders with tract data, click-to-select works, filters update the map

- [ ] **P2-3: Validate SRType filter behavior**
  - The current SRType filter uses `top_sr_type` (top type per tract) as a proxy
  - Decide: filter on top type per tract, OR aggregate separately per (tract, SRType) pair
  - If per-type aggregation is needed, add a `sr_type` column to the aggregate and
    produce separate Parquet files per type, or a multi-index Parquet

- [ ] **P2-4: Add reopen rate metric to pipeline**
  - Define `reopen_rate` heuristic based on `validate_2025_sample.ipynb` findings
    (P0-1 will determine if `LastActivity` provides a reliable signal)
  - Add to `aggregate_tract()` in `src/balt311/metrics.py`

- [ ] **P2-5: Tune color scale and map aesthetics**
  - Verify diverging `RdBu_r` scale looks good for closure rate (0–1) vs. days (0–N)
  - Consider separate scales: percentage metrics use 0–1 midpoint; time metrics use citywide median

- [ ] **P2-6: Deploy to Streamlit Community Cloud**
  - Connect GitHub repo at share.streamlit.io
  - Set `mapbox.token` in the app's Secrets manager
  - Verify public URL loads correctly

---

## Phase 3 — Analysis and Outputs

- [ ] **P3-1: Run equity analysis (from `requirements.md` Section 3.3)**
  - Spearman correlation: `median_days_to_close` vs. CSA median household income
  - Stratified by top 5 SRTypes
  - Quartile comparison (ANOVA / Kruskal-Wallis on closure rate)

- [ ] **P3-2: Regression (optional, medium effort)**
  - OLS: `log(days_to_close)` ~ income + renter rate + SRType FE + month FE
  - Add results summary to a notebook or Markdown doc

- [ ] **P3-3: Write executive summary**
  - 1-page, key findings with inline map thumbnails
  - Audience: Mayor's Office, City Council, CDO

---

## Pending Data Investigation Decisions

These questions from `requirements.md` Section 7 must be resolved before P1 or P2 tasks
that depend on them can proceed.

| Question | Depends on | Blocks |
|---|---|---|
| Does `MethodReceived` distinguish staff vs. resident? | P0-1 | P1-1 (source classification), P3-1 (ratio metric) |
| Is there a reopen signal in `LastActivity`? | P0-1 | P2-4 (reopen rate metric) |
| What is the `SRStatus` == "Closed" / `CloseDate` consistency? | P0-1 | P1-1 (closure rate definition) |
| Does the 2025 file cover full year or rolling window? | P0-3 | P1-2 (whether to combine years) |
| Are there duplicate `SRRecordID`s across years? | P0-2, P0-3 | P1-1 (deduplication logic) |
| What percentage of records are geocodeable? | P0-1 | P1-1 (spatial join yield estimate) |

---

*Update this file as tasks are completed. Mark items `[x]` when done.*
