# Cross-City 311 Comparison — Feasibility, Plan, and Results Log

**Status:** Planning baseline v1.0 · **Date:** June 2026 · **Owner:** Phase 5 (Cross-Municipality Comparison)

This document is the home for the cross-city comparison initiative described in
`requirements.md` §3.6 / §4.6 and `TASKS.md` Phase 5. It serves three roles:

1. **Feasibility assessment** — which cities have publicly accessible, mature 311 open
   data, how hard each is to integrate given Baltimore's existing pipeline, and how
   likely a delivery-metric and an equity comparison are to succeed for each (§1–§4).
2. **The phased rollout** — one pair city → a cohort, with two new tabs (cross-city
   service *delivery* and cross-city service *equity*), Baltimore as the reference in
   both (§5).
3. **A running results log** — each phase ends with a documentation checkpoint that
   appends its findings here (§6). This is the "pause at each step and record results"
   discipline the plan is built around: do not start a phase before the prior phase's
   checkpoint entry exists.

The detailed, checkbox-tracked task list lives in `TASKS.md` Phase 5. This document
holds the reasoning, the evidence, and the accumulating findings.

---

## 1. What "comparison" means here (and what it does not)

Three distinct comparisons, in increasing difficulty:

| Comparison | Unit compared | Portability | Difficulty |
|---|---|---|---|
| **Overall volume** | City-level totals + per-1k-resident rates | High — every city publishes counts; ACS population is national | Low |
| **Service delivery** | City-level median days to close, closure rate, (on-time rate where derivable) | Medium — timestamps are universal but "closed"/"resolved" semantics differ | Medium |
| **Service equity** | Each city's *own internal* race/income disparity score (Mann-Whitney overlap), then the **scores** compared across cities | High for the aggregate score — ACS tract demographics and TIGER tract boundaries are national, every candidate has lat/lon | Medium (aggregate) → High (within-type) |

**Critical conceptual point for the equity tab:** we do **not** compare Baltimore tracts
to DC tracts directly — they are not the same places. Instead we compute *each city's
internal equity score* using the identical methodology already in `utils.overlap_score()`
(does the majority-Black / lower-income half of the city wait longer than the
majority-White / higher-income half?), then compare those **scores** across cities. The
question the tab answers is "is Baltimore more or less equitable in its own service
delivery than its peers are in theirs?" — not "does Baltimore tract 2604 resemble DC
tract X." This makes the equity comparison genuinely portable: it rides entirely on
nationally-uniform data sources (Census ACS API + TIGER/Line tracts) plus the lat/lon
every candidate city already publishes.

**What stays hard:** *within-type* equity comparison (do majority-Black areas wait longer
for pothole repair specifically, in each city?) requires harmonizing each city's request-type
taxonomy to a shared ontology. That is the Phase 5.7 stretch goal, deliberately last.

---

## 2. Candidate cities — evaluation matrix

Baltimore reference profile: ~565k residents, ~62% Black, high poverty, post-industrial
East Coast legacy city, ArcGIS-based 311 open data (per-year FeatureServer layers).

Demographic/structural similarity is rated relative to *that* profile. "Integration
effort" is rated relative to **Baltimore's existing `src/balt311/ingest.py`**, which already
speaks ArcGIS FeatureServer REST.

| City | Portal / API technology | Endpoint shape | Key temporal + geo fields | Open-data maturity | Demographic peer fit | Integration effort | Delivery-cmp success | Equity-cmp success |
|---|---|---|---|---|---|---|---|---|
| **Washington, DC** | Open Data DC — **ArcGIS FeatureServer REST** | one layer per calendar year (`311 City Service Requests in YYYY`) | `ADDDATE`, `RESOLUTIONDATE`, `SERVICECODE`/`SERVICECODEDESCRIPTION`, `WARD`, `LATITUDE`/`LONGITUDE` | High | Moderate — large Black pop & regional neighbor, but gentrified/higher-income | **Lowest — reuses existing ArcGIS client almost verbatim** | High | High |
| **Philadelphia** | OpenDataPhilly — **Carto SQL API** (`phl.carto.com/api/v2/sql`) | single table `public_cases_fc`, 2014→present | `requested_datetime`, `closed_datetime`, `service_name`, `lat`/`lon`, `council_district` | High | **Strong** — post-industrial NE, large Black pop, high poverty | Medium — new Carto SQL adapter (one clean endpoint) | High | High |
| **New York City** | NYC Open Data — **Socrata SODA** (`erm2-nwe9`) | single dataset, 2010→present, 24M+ rows | `created_date`, `closed_date`, `complaint_type`, `agency`, `borough`, community board, `latitude`/`longitude` | Very high | Leading benchmark — scale far larger; not a size peer | Medium — Socrata adapter; **must aggregate server-side** (do not pull 24M rows) | High | High |
| **Chicago** | Chicago Data Portal — **Socrata** (`v6vf-nfxy`) | unified system since 12/2018, 90+ types in one dataset | `created_date`, `closed_date`, `sr_type`, `community_area`, `ward`, `latitude`/`longitude` | Very high | Leading benchmark — much larger | Medium — Socrata adapter (shared with NYC/SF) | High | High |
| **San Francisco** | DataSF — **Socrata** (`vw6y-z8j6`) | single dataset since 2008, 3.8M+ rows, nightly | `opened`, `closed`, `service_name`, `point`/lat-lon, `neighborhood` | Very high | Weak demographically (low Black %, very high income) — value is as a leading-practice benchmark | Medium — Socrata adapter | High | High |
| **Detroit** | Detroit Open Data — ArcGIS/Socrata ("Improve Detroit Issues") | rolling dataset | created/closed timestamps, lat/lon | Moderate | **Strong** — majority-Black, post-industrial | Medium — note "Improve Detroit" is the **app-channel subset**, not full 311; scope caveat | Medium (channel-limited) | High |
| **Louisville** | Louisville Metro Open Data — ArcGIS (per-year) | per-year layers, Open311 GeoReport-based, weekly refresh | created/closed, lat/lon | Moderate | Moderate | Medium — ArcGIS family, reuses client | Medium | High |
| **Boston** | Analyze Boston — **CKAN datastore** (per-year resources) | per-year CSV/Datastore SQL | `open_dt`, `closed_dt`, `type`, `neighborhood`, `latitude`/`longitude` | High **but mid-migration** | Moderate | Medium — CKAN adapter **— DEFER: backend migration Oct 2025 → mid-2026, schema in flux** | Medium (after migration settles) | High |
| **Kansas City** | data.kcmo.org — Socrata | new system since 2021 (short history) | created/closed | Moderate | Moderate | Medium — Socrata adapter | Medium (short history) | High |
| **St. Louis** | stlouis-mo.gov — **bespoke CSB API** | custom endpoint; coords in EPSG:3857 (projected) | request open/close, projected X/Y | Moderate | **Strong** — segregated legacy city, population decline | Higher — bespoke API + reprojection | Medium | High |

Notes on the success ratings:

- **Equity-cmp success is "High" for every geocoded city** because it depends only on
  lat/lon (present everywhere) + national ACS/TIGER data — not on the city's own
  demographic publishing. This is the single most important feasibility finding: the
  equity comparison is *more* portable than the delivery comparison, not less.
- **Delivery-cmp success "Medium"** flags a comparability caveat (closure semantics,
  channel scope, or short history), not a technical blocker.

---

## 3. Integration effort follows three API families

The cohort is deliberately sequenced so that each new **adapter** unlocks several cities,
rather than picking cities ad hoc:

1. **ArcGIS FeatureServer family** — Baltimore (built), **DC**, Louisville, (Detroit partial).
   Reuses `src/balt311/ingest.py` almost verbatim; only field names and the per-year
   layer/endpoint map change.
2. **Carto SQL family** — **Philadelphia**. One `phl.carto.com/api/v2/sql` endpoint;
   supports server-side aggregation via SQL, so we can pull pre-aggregated metrics
   rather than raw rows.
3. **Socrata SODA family** — **NYC, Chicago, San Francisco**, Kansas City. One adapter
   with `$select`/`$where`/`$group` server-side aggregation handles all of them; only
   the domain + dataset id + column names differ.

A fourth family (**CKAN**, Boston) is documented but deferred until Boston's backend
migration completes (mid-2026).

This is why the MVP pair is **Baltimore + DC**: it proves the entire cross-city
abstraction (a per-city adapter contract, a normalized cross-city schema, the comparison
tab, the portable ACS-tract equity join) while reusing the ArcGIS client we already have —
so the MVP spends its effort on the *genuinely new* parts, not on a second API client.
Philadelphia (the strongest analytical peer, and the first Carto source) is the very next
addition.

---

## 4. Normalization challenges to resolve in the adapter layer

Documented up front so each city onboarding checks against the same list:

1. **Closure semantics** — "closed" vs. "resolved" differ; some systems auto-close after a
   fixed window regardless of resolution. Record each city's definition; footnote it in the
   tab. Median-days-to-close is comparable only with this caveat surfaced.
2. **Request-type taxonomy** — no shared vocabulary across cities. *Aggregate* delivery and
   equity metrics need no taxonomy. *Within-type* comparison (Phase 5.7) needs a crosswalk
   to a shared ontology — anchor on the Open311 service-category list where possible.
3. **Source / channel** — Baltimore's resident-vs-staff split (`MethodReceived`) is not
   uniformly available. The safe common denominator is **all geocoded requests**; apply
   Baltimore's resident-initiated subset only where the channel field exists, and label it.
4. **Right-censoring** — apply Baltimore's existing 30-day live-year exclusion per city so a
   city queried mid-year is not penalized for recently-opened, not-yet-closed requests.
5. **Volume scale** — never compare raw counts (NYC dwarfs Baltimore). Compare **rates**
   (per-1k-resident, closure rate, median days). For Socrata giants, aggregate **server-side**
   (`$group` + `$select`) so we transfer thousands of summary rows, not tens of millions of
   raw rows.
6. **Geographic grain** — delivery metrics compared at the **city** level. Equity computed at
   each city's **tract** level internally, then the **scores** compared (see §1). Tract→city
   joins use TIGER state+county FIPS, identical mechanics to Baltimore's existing tract join.
7. **Year alignment** — cities have different available year ranges. The tabs compare on the
   set of overlapping years; default to the most recent year present in all cohort cities.

---

## 5. Phased rollout (summary — full tasks in `TASKS.md` Phase 5)

| Sub-phase | Deliverable | New tab? | Documentation checkpoint |
|---|---|---|---|
| **5.0 Feasibility** | This document (§1–§4): city matrix, success likelihoods, adapter families | — | ✅ §6.0 below |
| **5.1 Adapter + MVP pair** | Per-city adapter contract; ArcGIS adapter for **DC**; normalized `peer_city_*` schema; Baltimore+DC delivery metrics | — | §6.1 — DC schema quirks, closure semantics, row counts |
| **5.2 Delivery tab (MVP)** | **Cross-City Service Delivery** tab — Baltimore vs. DC, Baltimore as reference | ✅ Tab 7 | §6.2 — what the pair comparison shows |
| **5.3 Cohort expansion** | Carto adapter (**Philadelphia**) + Socrata adapter (**NYC, Chicago, SF**); cohort metrics table | — | §6.3 — one entry per city onboarded (quirks, comparability) |
| **5.4 Delivery tab (cohort)** | Delivery tab generalized to N cities, Baltimore highlighted as reference | (Tab 7 grows) | §6.4 — cohort delivery findings |
| **5.5 Equity methodology** | Portable ACS-tract + TIGER equity join per city; per-city internal overlap scores | — | §6.5 — per-city equity scores + validation vs. Baltimore in-app numbers |
| **5.6 Equity tab (cohort)** | **Cross-City Service Equity** tab — each city's internal race/income score, Baltimore as reference | ✅ Tab 8 | §6.6 — cross-city equity findings |
| **5.7 Within-type (stretch)** | Request-type taxonomy crosswalk; within-type equity comparison for shared categories | (extends Tab 8) | §6.7 — taxonomy mapping coverage + within-type findings |

**Recommended cohort waves** (each wave = one adapter family coming online):

- **Wave 0 (MVP):** Baltimore + **DC** (ArcGIS — reuse existing client)
- **Wave 1:** **Philadelphia** (Carto — strongest demographic peer, first new adapter)
- **Wave 2:** **NYC, Chicago, San Francisco** (Socrata — leading-practice benchmarks; one adapter unlocks all three)
- **Wave 3 (optional):** **Detroit** (strong demographic peer, channel-scope caveat), then evaluate **St. Louis / Louisville**
- **Deferred:** **Boston** (revisit after the mid-2026 backend migration stabilizes)

The two-tab end state: **Tab 7 — Cross-City Service Delivery** and **Tab 8 — Cross-City
Service Equity**, both with Baltimore as the fixed reference. Whether they live as the final
two tabs of the existing arc or in a dedicated "Compare cities" section is decided at 5.2
(see `TASKS.md` P5.2-3).

---

## 6. Results log

> Append one subsection per completed sub-phase. Do not begin a sub-phase until the
> previous sub-phase's entry exists here. Each entry records: what was built, what the data
> actually showed, surprises/quirks, and any revision to the plan above.

### 6.0 — Feasibility (Phase 5.0) — ✅ recorded June 2026

- **Reviewed** ten candidate cities across four API families (ArcGIS REST, Carto SQL,
  Socrata SODA, CKAN). Matrix in §2; family sequencing in §3; normalization risks in §4.
- **MVP pair decision: Baltimore + Washington, DC.** Rationale: DC's Open Data DC publishes
  311 as per-year ArcGIS FeatureServer layers — the *same* technology
  `src/balt311/ingest.py` already paginates — so the MVP reuses the existing client and
  spends its effort on the new abstraction (adapter contract, normalized schema, comparison
  tab, portable equity join) rather than a second API integration. DC is a credible regional
  peer; Philadelphia is the strongest *demographic* peer and is the first cohort addition
  (Wave 1, Carto).
- **Headline feasibility finding:** the **equity comparison is more portable than the
  delivery comparison.** Aggregate equity scoring rides entirely on nationally-uniform data
  (Census ACS API + TIGER tracts) plus the lat/lon every candidate already publishes, so it
  is rated "High" success for every geocoded city. Delivery comparison is rated "Medium" for
  several cities only because of closure-semantics / channel-scope / short-history
  comparability caveats — technical, not blocking.
- **Hardest deferred piece:** within-type equity comparison (Phase 5.7) needs a request-type
  taxonomy crosswalk; everything before it works on aggregate metrics with no shared
  taxonomy required.
- **Cohort sequencing:** Wave 0 DC (ArcGIS) → Wave 1 Philadelphia (Carto) → Wave 2 NYC /
  Chicago / SF (Socrata) → Wave 3 optional Detroit + evaluate St. Louis/Louisville; Boston
  deferred pending its mid-2026 backend migration.
- **No revision to the plan** resulting from feasibility review — proceed to 5.1.

### 6.1 — Adapter + MVP pair (Phase 5.1) — _pending_

### 6.2 — Delivery tab, MVP (Phase 5.2) — _pending_

### 6.3 — Cohort expansion (Phase 5.3) — _pending_

### 6.4 — Delivery tab, cohort (Phase 5.4) — _pending_

### 6.5 — Equity methodology (Phase 5.5) — _pending_

### 6.6 — Equity tab, cohort (Phase 5.6) — _pending_

### 6.7 — Within-type comparison (Phase 5.7) — _pending_

---

## 7. Sources (feasibility review, June 2026)

- NYC 311 Service Requests (`erm2-nwe9`), NYC Open Data / Socrata SODA — https://data.cityofnewyork.us/Social-Services/311-Service-Requests-from-2020-to-Present/erm2-nwe9
- Chicago 311 Service Requests (`v6vf-nfxy`), Chicago Data Portal / Socrata — https://data.cityofchicago.org/Service-Requests/311-Service-Requests/v6vf-nfxy
- 311 City Service Requests, Open Data DC (per-year ArcGIS layers) — https://datahub-dc-dcgis.hub.arcgis.com/datasets/DCGIS::311-city-service-requests-in-2024
- 311 Service and Information Requests (`public_cases_fc`, Carto SQL), OpenDataPhilly — https://opendataphilly.org/datasets/311-service-and-information-requests/
- 311 Cases (`vw6y-z8j6`), DataSF / Socrata — https://data.sfgov.org/City-Infrastructure/311-Cases/vw6y-z8j6
- 311 Service Requests, Analyze Boston / CKAN — https://data.boston.gov/dataset/311-service-requests
- Improve Detroit Issues, Detroit Open Data Portal — https://data.detroitmi.gov/datasets/detroitmi::improve-detroit-issues
- Metro 311 Service Request, Louisville Open Data — https://louisville-metro-opendata-lojic.hub.arcgis.com/
- 311 Requests, Open Data KC — https://data.kcmo.org/
- CSB Service Requests (311), City of St. Louis — https://www.stlouis-mo.gov/data/datasets/dataset.cfm?id=5
</content>
</invoke>
