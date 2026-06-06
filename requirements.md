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

### 3.5 Service-Mix and Area-Embedding Analysis (Phase 4d)

Three additional analyses bridge the operational (Section 3.2) and equity (Section 3.3) layers, each becoming its own dashboard tab (see §4.5):

1. **Within-type equity stratification** — rather than computing one Mann-Whitney overlap score per metric citywide, compute it *separately within each SRType* (e.g., do majority-Black tracts wait longer than majority-White tracts specifically for pothole repairs?), then combine the per-type scores into a single citywide "adjusted" score weighted by each type's request volume. Comparing this adjusted score to the existing raw citywide score decomposes the equity gap into two parts: how much is explained by *which* services an area happens to request (type-mix effect — some types are structurally slower) versus how much reflects *unequal delivery of the same service* (the cleaner equity signal). This generalizes §3.3's bivariate approach into a controlled, stratified comparison and operationalizes the "within-type vs. type-mix equity" framing already present in `TASKS.md` Phase 4.

2. **Area embedding in two complementary spaces, clustered into named peer groups** — represent each tract/CSA as a point in 2D using dimensionality reduction (PCA, with UMAP as a future option) over two different feature spaces:
   - **Service-usage space**: each geography's vector of SRType request shares (row-normalized geo×SRType volumes). Reveals whether geographies form tight clusters of similar service consumption or vary continuously, and — when colored by demographics — whether demographically similar areas cluster together in what they request.
   - **Demographic space (the inverse view)**: each geography's race/income profile (`pct_black`, `pct_white`, `median_income`). Colored by service-side variables — predominant SRType, request rate (`requests_per_1k`), or speed of resolution (`median_days_to_close`) — this answers the inverse question: do areas that look alike demographically also look alike in how they use and experience 311?

   Viewing both spaces side by side, with synchronized color-by controls, lets a user trace the same set of geographies through "what they request" and "who they are" and see where the two pictures align or diverge.

   **The embedding is an entry point, not an end point**: clustering the points in either space (e.g. k-means or agglomerative clustering, with k chosen via silhouette score or a user control) identifies *named peer groups* of geographies — descriptive labels generated from each cluster's dominant features (e.g. "high solid-waste demand, majority-Black tracts" or "low-volume, mixed-income"). Persisting a `geoid → peer_group` assignment turns the embedding into a reusable categorical dimension: the same peer-group labels can then filter and group charts elsewhere in the dashboard (Operations time series, Category Explorer, Equity distributions/trend), exactly as the existing top-SRType filter and category pills already do. This supersedes the simpler nearest-neighbor "peer similarity index" sketched for Phase 4b (§5) — instead of a one-off ranked list per selected geography, it produces durable, citywide peer categories that work as a first-class filter axis throughout the app.

3. **Mix-adjusted regression** — extends §3.4's regression to the aggregate tract×SRType×year panel available in `data/processed/` (record-level data is not retained): `log(median_days_to_close) ~ pct_black + median_income + SRType fixed effects + year fixed effects`. Reported as a coefficient table with 95% confidence intervals for the race and income terms, paired with the stratified scores above as two independent lines of evidence for the same question — is the *same* service delivered more slowly to disadvantaged areas, controlling for what's being requested and when?

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

### 4.5 Phase 4d Scope — Six-Tab Narrative Arc

Phase 4d adds four new tabs to the existing Operations and Equity tabs, producing a six-tab arc that walks the reader from the highest-level operational view to the most nuanced equity view with no conceptual jumps in between. Confirmed order and scope (detailed staged build plan in `TASKS.md` Phase 4d):

| # | Tab | Core question | Key interactions |
|---|---|---|---|
| 1 | **Operations** *(existing)* | How is the city doing operationally, citywide? | KPI bar, dual-line time series, SRType breakdown, geographic map |
| 2 | **Service Category Explorer** *(new — pure operations, no equity content)* | How does performance differ *among* service categories, and *within* one category across geography and over time — with no race/income framing at all? | Sortable citywide SRType performance table with category pills; among-category comparison chart; selecting a type drives a year-over-year trend view and a plain (non-demographic) choropleth |
| 3 | **Area Embedding** *(new, aka "Service Category Usage by Geographic Area")* | Do similar areas — by what they request, or by who lives there — cluster together, or is the city more of a continuum? Can those clusters become reusable peer groups? | 2D PCA scatter, one point per tract/CSA, switchable between *service-usage space* and *demographic space* (its inverse); color-by control adapts to the active space; clustering names each space's groups into a persisted, reusable `peer_group` filter dimension |
| 4 | **Equity** *(existing)* | Is service delivery equitable by race or income, citywide? | Choropleth, distribution comparisons, year-over-year trend |
| 5 | **Service Category Equity Explorer** *(new — renamed from an earlier "Category Explorer" draft; same scope)* | Does the citywide equity picture in the Equity tab hold up — or differ — among and within individual service categories? | Sortable citywide SRType ranking with category pills; selecting a type drives a within-type choropleth and a within-type race/income equity comparison (reusing the box-and-strip pattern from `equity_distributions.py`) |
| 6 | **Equity Adjusted for Service Mix** *(new)* | Are the equity gaps surfaced in tabs 4–5 explained by *which* services an area requests (mix-driven) or by *how* the same service is delivered (delivery-driven)? | Side-by-side raw vs. volume-weighted "adjusted" overlap scores; SRType equity ranking by within-type score; OLS regression panel with coefficient table and confidence-interval plot |

**Naming clarification**: tabs 2 and 5 sound similar but are deliberately distinct tools — Tab 2 is a pure operational drill-down (a city manager's tool, zero demographic content), while Tab 5 is the equity-flavored sibling that asks "...and does this differ by who's asking" for each category. Keeping them as separate tabs, in separate places in the arc (right after Operations vs. right after Equity), lets each audience find their tool without wading through the other's lens — see the naming note in `TASKS.md` Phase 4d for the full rationale.

**Persona alignment** (full detail in `personas.md`): each new tab closes a documented gap for one of the five personas rather than adding analysis for its own sake. Tab 2 gives the **Department Operations Manager** an equity-free performance drill-down for their own service types — the gap personas.md flags as "wants SRType breakdown without equity framing." Tab 3 gives both the **Local Official/Council Member** and the **Operations Manager** the "areas like mine" comparison personas.md identifies as the single highest-value gap across personas, by turning the embedding into reusable, named peer groups. Tabs 5 and 6 give the **Citizen Journalist** and **Citywide Official** the "which SRTypes drive the aggregate equity gap" and "adjusted equity score" answers personas.md lists as their most significant unmet needs — the two lines of evidence (stratified scores + regression) are deliberately paired so neither claim has to stand alone. Read together, the six tabs trace one continuous arc — operational overview → operational deep-dive → peer-grouped geographic understanding → citywide equity → category-level equity → mix-adjusted equity — so that every persona finds their question answered at the point in the story where they'd naturally ask it.

All four new tabs require `srtype_metrics_{year}.parquet`, `{geo_key}_srtype_metrics_{year}.parquet`, and the demographics CSVs — these are **already committed on `main` for all years 2016–2025** (full backfill, PRs #33–37) and merged into the working branch; the data-availability blocker noted in earlier drafts of this phase was a branch-sync gap, not a real one (see Stage 0 in `TASKS.md` Phase 4d). New runtime dependencies: `scikit-learn` (PCA + clustering for Area Embedding) and `statsmodels` (OLS for Equity Adjusted) — see §8.

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
  app/components/category_explorer.py  → Service Category Explorer tab — Tab 2 (Phase 4d — pure operations, no equity content)
  app/components/area_embedding.py     → Area Embedding tab — Tab 3 (Phase 4d — PCA + clustering in usage & demographic space → peer groups)
  app/components/category_equity_explorer.py → Service Category Equity Explorer tab — Tab 5 (Phase 4d — ranking + within-type equity comparison)
  app/components/equity_adjusted.py    → Equity Adjusted for Service Mix tab — Tab 6 (Phase 4d — stratified scores + regression)
  app/components/map_view.py           → Plotly choropleth_mapbox builder
  app/components/summary_panel.py      → selected-geography summary card (Equity tab)
  app/components/equity_distributions.py → race + income distribution comparison
  app/components/equity_trend.py       → year-over-year overlap score trend
  app/components/utils.py              → overlap_score (Mann-Whitney), score_label, format_metric
  src/balt311/ingest.py                → FeatureServer pagination logic
  src/balt311/metrics.py               → parse_timestamps, compute_days_to_close,
                                          aggregate_tract, rollup_to_csa, rollup_demographics_to_csa
```

**New Phase 4d dependencies** (`app/requirements.txt`):
- `scikit-learn>=1.3.0` — `PCA` + `StandardScaler` for the Area Embedding tab (UMAP considered as a future, heavier-install alternative)
- `statsmodels>=0.14.0` — `OLS` with robust standard errors for the Equity Adjusted regression panel

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
