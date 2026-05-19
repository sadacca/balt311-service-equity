# Requirements: 311 Service Equity Dashboard

**Status:** Draft v1.0  
**Date:** May 2026  
**Confidence:** High — all primary data sources verified as active and publicly available  
**Estimated Effort:** Low-Medium (2–4 weeks for analyst with Python/GIS skills)  
**Strategic Value:** Highest of all six initiatives — motivates Tier 1 data publication and is immediately politically legible

---

## 1. Goal

Produce a reproducible, neighborhood-level analysis of whether Baltimore City's 311 service request resolution varies systematically by socioeconomic status of the requesting neighborhood. The output should function both as a standalone equity assessment and as a demonstration of what becomes possible when the city adds resolution time and cost-of-service fields to its daily 311 feed.

**Primary Questions:**
1. Does median time-to-close a 311 request differ significantly across Community Statistical Areas (CSAs)?
2. Are certain request types resolved faster or more reliably in wealthier neighborhoods?
3. What is the ratio of resident-initiated requests to proactive city-initiated inspections by neighborhood — and does this ratio correlate with income or race?
4. Which request types have the highest reopen rates (reopened after initial closure), and where are they concentrated?

---

## 2. Data Sources

### 2.1 Primary Datasets

| Dataset | Source | URL | Update Frequency | Format |
|---|---|---|---|---|
| 311 Customer Service Requests (2024) | Open Baltimore | data.baltimorecity.gov | Annual file (daily-updated 2026 file also available) | CSV / GeoJSON |
| 311 Customer Service Requests (2026) | Open Baltimore | data.baltimorecity.gov | Daily | CSV / GeoJSON |
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
5. **Geocode to CSA** — spatial join of request coordinates to CSA boundary layer. Flag requests that fail the join (coordinate errors or out-of-boundary).

### 3.2 Core Metrics (per CSA)

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
| CSA-level summary table | CSV | Analyst / data.baltimorecity.gov publication |
| Choropleth equity maps (4) | PNG / interactive HTML | CDO briefing, press, public |
| Request type breakdown by CSA | Interactive table | Agency operations managers |
| Methodology and code | Python notebook (Jupyter) | Reproducibility / audit |
| Executive summary (1 page) | PDF / Markdown | Mayor's Office, City Council |

### 4.2 Dashboard Design Principles

- Use CSA as the geographic unit throughout (aligns with BNIA Vital Signs for direct comparison).
- All maps must use a diverging color scheme centered at the citywide median (not at zero), so above/below-average performance is immediately visible.
- Include a data vintage note on every visualization (e.g., "Based on 2024–2026 311 data; CSA demographics from ACS 2023 5-Year Estimates").
- Dashboard should be updatable annually with minimal manual intervention — parameterize the year in all scripts.

---

## 5. Gap Dependencies

These gaps limit the analysis but do not block it. They are documented here to support the case for Tier 1 data publication.

| Gap | Impact on This Analysis | Recommendation |
|---|---|---|
| No `time_to_close` field in raw 311 data | Must compute from `CreatedDate` / `CloseDate`; possible but requires data cleaning | Add as derived field to daily feed |
| No reopen flag in raw 311 data | Cannot definitively identify reopened requests; must use heuristic proxies | Add `reopen_count` field to feed |
| No cost-of-service field | Cannot compute cost equity across neighborhoods | Add estimated labor cost by request type |
| No source channel field | Cannot distinguish resident vs. staff-initiated requests | Add `request_source` field (phone, app, staff) |
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
4. Does the 2026 daily file include all historical records from January 2026 forward, or only a rolling window?
5. Should the analysis include requests that span multiple agencies (e.g., a streetlight request involving both DOT and BGE)? How are these coded?

---

## 8. References

| Source | URL |
|---|---|
| Open Baltimore — 311 Customer Service Requests | data.baltimorecity.gov |
| BNIA Vital Signs Open Data Portal | vital-signs-bniajfi.hub.arcgis.com |
| Baltimore NSA/CSA Boundary Files | data.baltimorecity.gov |
| ACS 5-Year Estimates | census.gov/programs-surveys/acs |

---

*This document is a living requirements baseline. Update when 311 data schema changes or when BNIA releases a new Vital Signs edition.*
