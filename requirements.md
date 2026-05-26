# Requirements: 311 Service Equity Dashboard

**Status:** Draft v1.1  
**Date:** May 2026  
**Confidence:** High — all primary data sources verified as active and publicly available  
**Estimated Effort:** Low-Medium (2–4 weeks for analyst with Python/GIS skills)  
**Strategic Value:** Highest of all six initiatives — motivates Tier 1 data publication and is immediately politically legible

**Architecture decisions (v1.1):**
- **Primary output:** Interactive Streamlit dashboard deployed on Streamlit Community Cloud
- **Primary geographic unit:** Census tracts (~200 in Baltimore City); CSA as secondary roll-up for BNIA Vital Signs comparison
- **Tech stack:** Python · Streamlit ≥1.39 · Plotly · Mapbox (free tier, token required)
- **Update model:** GitHub Actions — single-year (`update_data.yml`) and multi-year backfill (`backfill.yml`) workflows; analyst triggers manually and pushes nothing directly
- **Phase 2 scope (not MVP):** Full drill-down to individual requests, multi-tract comparison, Dash migration if interactivity demands it

---

## 1. Goal

Provide operational visibility into Baltimore's 311 service request system for two audiences:

- **Citizens and advocates** — what requests are coming in, from where, and how does service delivery compare year over year and across neighborhood types
- **Internal stakeholders** — department managers tracking their service types and citywide leadership asking whether performance is improving, equitable, and competitive with peer cities

Four comparison axes structure the analysis and drive prioritization of features:

1. **Historical** — how does this year compare to prior years (2016–2025)?
2. **Geographic** — which neighborhoods get faster or slower service, and why?
3. **Cross-municipal** — how does Baltimore compare to peer cities on the same metrics?
4. **Equity** — does service quality differ systematically by race or income of the requesting neighborhood?

The equity lens is not the only lens — operational clarity for managers is equally important and is the default landing view. The output should also function as a demonstration of what becomes possible when the city adds resolution time and cost-of-service fields to its daily 311 feed.

**Primary Questions:**
1. What request types are coming in, where, and in what volume — and how does this compare to prior years?
2. How quickly and completely are requests being resolved, by type and by geography?
3. Does median time-to-close differ significantly across neighborhoods, and does it correlate with race or income?
4. Are certain request types resolved faster or more reliably in wealthier neighborhoods?
5. How does Baltimore's overall performance compare to peer municipalities?
6. What is the composition of 311 demand — how much is resident-driven vs. city-proactive, and does that mix vary by type, geography, or year? *(Phase 4c — Request Source Analysis tab)*

---

## 2. Data Sources

### 2.1 Primary Datasets

| Dataset | Source | URL | Update Frequency | Format |
|---|---|---|---|---|
| 311 Customer Service Requests (2016–2022) | Open Baltimore | data.baltimorecity.gov | Annual historical files via `311_Customer_Service_Requests_Yearly` FeatureServer | ArcGIS REST API |
| 311 Customer Service Requests (2023–2025) | Open Baltimore | data.baltimorecity.gov | Annual files; 2026 live file accumulates from Jan 1 | ArcGIS REST API |
| Neighborhood Statistical Areas (NSA) Boundaries | Open Baltimore | data.baltimorecity.gov | Stable | Shapefile / GeoJSON |
| Community Statistical Areas (CSA) Boundaries | BNIA-JFI / Open Baltimore | vital-signs-bniajfi.hub.arcgis.com | Stable | Shapefile / GeoJSON |

### 2.2 Benchmark / Overlay Datasets

| Dataset | Source | URL | Key Fields Needed |
|---|---|---|---|
| BNIA Vital Signs (150+ indicators) | BNIA-JFI | vital-signs-bniajfi.hub.arcgis.com | Median household income, percent poverty, racial composition, housing cost burden — by CSA |
| ACS 5-Year Estimates (Tract level) | U.S. Census Bureau | census.gov/programs-surveys/acs | Income, race/ethnicity, renter vs. owner rate — for regression controls |
| Employee Salary Data | Open Baltimore | data.baltimorecity.gov | Department staffing levels — for capacity normalization |

---

## 3. Methodology

### 3.1 Data Preparation

1. **Load 311 data** — combine 2024 and 2026 annual files; deduplicate on request ID.
2. **Parse timestamps** — `CreatedDate` and `CloseDate` fields; compute `days_to_close = CloseDate - CreatedDate` for closed requests.
3. **Flag reopen events** — identify requests with status history indicating reopening after closure (if status field supports this; otherwise flag requests with `days_to_close` outliers as a proxy).
4. **Classify request source** — identify requests logged by city staff vs. resident-initiated (source channel field, if available in the dataset).
5. **Spatial join to census tracts** — point-in-polygon join of request coordinates to TIGER/Line tract boundary layer. Flag requests that fail the join (coordinate errors or out-of-boundary). Roll up to CSA using the BNIA tract→CSA crosswalk for Vital Signs comparison.

### 3.2 Core Metrics (per census tract, with CSA roll-up)

| Metric | Calculation | Notes |
|---|---|---|
| Median days to close | Median of `days_to_close` by CSA | Use median not mean; skewed by outliers |
| Closure rate | `closed_requests / total_requests` | Exclude requests < 30 days old to avoid right-censoring |
| Reopen rate | `reopened_requests / closed_requests` | Proxy for resolution quality |
| Request rate per 1,000 residents | `request_count / (CSA_population / 1000)` | Requires ACS population by CSA |
| Resident-to-staff request ratio | `resident_initiated / staff_initiated` | Only computable if source field available |
| Top 3 request types by volume | Ranked by count | Identifies neighborhood-specific service patterns |

### 3.3 Equity Analysis

1. **Bivariate correlation** — Spearman rank correlation between `median_days_to_close` and CSA-level median household income. Report r and p-value.
2. **Request type stratification** — Repeat the correlation for the five highest-volume request types separately (e.g., bulk trash, pothole, streetlight, rodent control). Some types may show stronger disparities than the aggregate.
3. **Quartile comparison** — Divide CSAs into income quartiles; compare mean closure rates and reopen rates across quartiles using ANOVA or Kruskal-Wallis.
4. **Map output** — Choropleth maps of: (a) median days to close, (b) closure rate, (c) income quartile. Side-by-side comparison is the core deliverable.

### 3.4 Regression Controls (Optional, Medium Effort)

Run an OLS regression of `log(days_to_close)` on:
- CSA median income (continuous)
- Percent renter-occupied (ACS)
- Request type (fixed effects)
- Month/year (seasonal controls)
- Distance from downtown (proxy for infrastructure age)

This isolates income effect from confounders and produces a defensible claim about whether disparity is income-driven vs. structurally driven.

---

## 4. Output Specifications

### 4.1 Deliverables

| Output | Format | Audience |
|---|---|---|
| **Interactive Streamlit dashboard** *(primary)* | Web app (Streamlit Community Cloud) | CDO briefing, agency managers, press, public |
| Tract / CSA summary tables | Parquet (auto-generated by pipeline) | Analyst, data.baltimorecity.gov publication |
| Methodology and code | Pipeline notebooks 01–03 + this repo | Reproducibility / audit |
| Executive summary (1 page) | PDF / Markdown | Mayor's Office, City Council |

### 4.2 Dashboard Design Principles

- **Primary unit:** Census tracts. CSA view available via toggle for BNIA Vital Signs comparison.
- **Equity maps** use a diverging color scheme centered at the citywide median so above/below-average performance is immediately visible. **Operations count maps** use a sequential colorscale from 0 to the maximum value.
- Click-to-select geography: clicking a tract or CSA polygon shows a summary panel with all key metrics for that area.
- **Sidebar**: static dashboard overview (description of each tab, data sources). No interactive filters in sidebar — all controls are inline in context.
- **Inline controls**: geo toggle (Census Tract / CSA) appears above each tab's map; metric selector appears above the time series in Operations and above the choropleth in Equity; SRType filter in Equity tab only.
- Include a data vintage note on every visualization (e.g., "311 data 2024 · Census Tracts · Demographics from ACS 2023 5-Year Estimates").
- Dashboard is updated annually: analyst re-runs pipeline notebooks and pushes updated `data/processed/` files; Streamlit Cloud redeploys automatically on push.
- Mapbox free tier for basemap (light style). Token stored as Streamlit secret, never in repo.

### 4.3 MVP Interactivity (Phase 1)

| Feature | Implementation |
|---|---|
| Year filter | `st.radio(horizontal=True)` — discovers available years from `data/processed/`; inline above tabs |
| SRType filter | `st.multiselect` — equity tab only; filters geographies by top request type |
| Tract / CSA toggle | `st.radio` — inline above each tab's map, not in sidebar; synced via `st.session_state["geo_level"]` |
| Metric selector | `st.radio(horizontal=True)` in Ops (above time series); `st.selectbox` in Equity (above choropleth); independent per tab |
| Click-to-select geography | `st.plotly_chart(on_select="rerun")` — returns clicked polygon's data |
| Summary panel | Shows all metrics for selected geography in right column |
| City-wide summary bar | Four headline numbers across top of Operations tab |
| Dual-line time series | All-requests + citizen-initiated traces; click point to navigate year |
| Citizen-initiated sub-stats | Caption row inside each KPI tile; citizen-initiated equivalents for all 4 metrics |
| Category pill legend | Full department names shown as caption below category pills; TEST prefix excluded |

### 4.4 Phase 2 Scope (post-MVP)

- Full drill-down to individual request records for a selected tract
- Multi-tract comparison (select two or more, side-by-side)
- Equity trend view (year-over-year for selected geography)
- Regression output panel (income coefficient, confidence interval)
- Evaluate migration to Plotly Dash if Phase 2 interactivity exceeds Streamlit's event model

---

## 5. Gap Dependencies

These gaps limit the analysis but do not block it. They are documented here to support the case for Tier 1 data publication.

| Gap | Impact on This Analysis | Recommendation |
|---|---|---|
| No `time_to_close` field in raw 311 data | Must compute from `CreatedDate` / `CloseDate`; possible but requires data cleaning | Add as derived field to daily feed |
| No reopen flag in raw 311 data | Cannot definitively identify reopened requests; must use heuristic proxies | Add `reopen_count` field to feed |
| No cost-of-service field | Cannot compute cost equity across neighborhoods | Add estimated labor cost by request type |
| No source channel field | **Partially resolved**: `MethodReceived` field in raw data distinguishes Phone/API/Mail/Email (resident-initiated) from System/Internal (staff/proactive). Citizen-initiated subset computable and shown as sub-row in KPI bar and second trace in time series. Full source analysis tab (P4c) remains future work. | Add `request_source` field (phone, app, staff) |
| No staff-to-district assignment data | Cannot normalize by inspector capacity | Publish district-level staffing counts |

---

## 6. Validation and Quality Checks

- [ ] Confirm coordinate coverage: what percentage of 311 requests have valid lat/lon? Flag and report the remainder.
- [ ] Check for duplicate request IDs across annual files.
- [ ] Validate that `days_to_close` distribution is plausible (no negative values; investigate extreme outliers >365 days).
- [ ] Cross-check total request count against published Open Baltimore dataset record counts.
- [ ] Confirm CSA boundary vintage matches BNIA Vital Signs edition used for income data.

---

## 7. Open Questions

1. Does the 311 dataset include a `request_source` field distinguishing app, phone, and staff-initiated entries? If so, the resident-to-staff ratio analysis is immediately executable.
2. Is there a status history table or status change log, or only a current status snapshot? Reopen analysis depends on this.
3. What is the city's definition of "closed" vs. "resolved"? Some 311 systems auto-close requests after a time period regardless of actual resolution.
4. ~~Does the 2026 daily file include all historical records from January 2026 forward, or only a rolling window?~~ **RESOLVED**: Accumulates from Jan 1 of each year — oldest record in the 2026 endpoint is 2026-01-01 00:09:36 UTC. All annual files follow the same pattern. For live-year analysis, exclude requests created within the last 30 days to avoid right-censoring (recently opened requests haven't had time to close, which deflates closure rate and inflates days-to-close).
5. Should the analysis include requests that span multiple agencies (e.g., a streetlight request involving both DOT and BGE)? How are these coded?

---

## 8. Technical Architecture

```
Stage 1 — Pipeline (GitHub Actions, output committed to repo)
  scripts/pipeline.py --stage ingest      → ArcGIS FeatureServer → data/raw/
  scripts/pipeline.py --stage process     → clean + spatial join + aggregate → data/processed/
                                            (tract/CSA metrics, boundaries, demographics,
                                             requests_per_1k via Census ACS API)
  scripts/pipeline.py --stage srtype      → per-SRType + geo×SRType metrics → data/processed/
  scripts/pipeline.py --stage demographics→ ACS race + income → data/processed/ (run once)

  .github/workflows/update_data.yml  → single-year manual trigger
  .github/workflows/backfill.yml     → multi-year sequential backfill, staggered for ESRI

Stage 2 — App (reads only from data/processed/, no network dependencies at runtime)
  app/app.py                           → Streamlit entrypoint, tabs, year selector
  app/components/operations_panel.py   → Operations tab (KPI bar, time series, SRType table, map)
  app/components/map_view.py           → Plotly choropleth_mapbox builder
  app/components/summary_panel.py      → selected-geography summary card (Equity tab)
  app/components/equity_distributions.py → race + income distribution comparison
  app/components/equity_trend.py       → year-over-year overlap score trend
  app/components/utils.py              → overlap_score (Mann-Whitney), score_label, format_metric
  src/balt311/ingest.py                → FeatureServer pagination logic
  src/balt311/metrics.py               → parse_timestamps, compute_days_to_close,
                                          aggregate_tract, rollup_to_csa, rollup_demographics_to_csa
```

**Repository layout:**
```
balt311-service-equity/
├── data/
│   ├── raw/          # .gitignored — downloaded FeatureServer exports + boundary files
│   ├── interim/      # .gitignored — cleaned per-record files
│   └── processed/    # committed — tract/CSA aggregates that the app reads
├── notebooks/
│   ├── 01_ingest.ipynb
│   ├── 02_clean.ipynb
│   ├── 03_aggregate.ipynb
│   └── validate_2025_sample.ipynb
├── app/
│   ├── app.py
│   └── components/
├── src/balt311/
│   ├── ingest.py
│   └── metrics.py
├── .streamlit/
│   ├── config.toml
│   └── secrets.toml.example
└── requirements.txt
```

**Hosting:** Streamlit Community Cloud (free). Push to `main` triggers auto-redeploy.
Set `mapbox.token` in the Streamlit Cloud Secrets manager (not in the repo).

---

## 9. References

| Source | URL |
|---|---|
| Open Baltimore — 311 Customer Service Requests | data.baltimorecity.gov |
| BNIA Vital Signs Open Data Portal | vital-signs-bniajfi.hub.arcgis.com |
| Baltimore NSA/CSA Boundary Files | data.baltimorecity.gov |
| ACS 5-Year Estimates | census.gov/programs-surveys/acs |

---

*This document is a living requirements baseline. Update when 311 data schema changes or when BNIA releases a new Vital Signs edition.*
