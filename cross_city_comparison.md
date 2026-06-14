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

## 0. A word of credit — openness is the precondition for all of this

Before a single peer comparison or critical finding, one fact deserves to lead: **a
cross-city analysis of this depth is only possible because some cities — Baltimore
foremost — publish their 311 data openly, completely, and at the record level.** Baltimore
was the **first US city to run a 311 system (1996)**, pioneered **CitiStat (1999)** — the
data-driven performance-management model the rest of the country adopted — and was an **early
adopter of the Open311 GeoReport v2 standard (~2011)**, a standard that, even today, only on
the order of a dozen US cities have implemented, putting Baltimore ahead of many far larger
cities. The §2 matrix below makes the same point in reverse: of the thousands of US
municipalities, only a few dozen publish 311 data mature enough to support delivery *and*
equity comparison at all.

This creates an uncomfortable asymmetry the project should name explicitly: **the more openly
a city publishes, the more it exposes itself to criticism, while less-transparent cities
escape scrutiny by default.** If openness is rewarded only with critique, cities are
disincentivized from being open. So the stance taken here is deliberate — **evaluating
Baltimore's performance is, simultaneously, a tribute to Baltimore's openness.** Most US
cities could not be evaluated this way; Baltimore can, and that is to its credit. The
cross-city maturity index (Phase 5.8) is built precisely to make that credit explicit and
measurable rather than incidental — recognition first, critique second.

---

## 1. What "comparison" means here (and what it does not)

Three distinct comparisons, in increasing difficulty:

| Comparison | Unit compared | Portability | Difficulty |
|---|---|---|---|
| **Overall volume** | City-level totals + per-1k-resident rates | High — every city publishes counts; ACS population is national | Low |
| **Service delivery** | City-level median days to close, closure rate, (on-time rate where derivable) | Medium — timestamps are universal but "closed"/"resolved" semantics differ | Medium |
| **Service equity** | Each city's *own internal* **mix-adjusted** race/income disparity score, then the **scores** compared across cities | High for the adjusted overall score — ACS tract demographics and TIGER tract boundaries are national, every candidate has lat/lon, and no shared taxonomy is needed | Medium (adjusted overall) → High (within-type) |

**Critical conceptual point for the equity tab:** we do **not** compare Baltimore tracts
to DC tracts directly — they are not the same places. Instead we compute *each city's
internal equity score* (does the majority-Black / lower-income half of the city wait longer
than the majority-White / higher-income half?), then compare those **scores** across cities.
The question the tab answers is "is Baltimore more or less equitable in its own service
delivery than its peers are in theirs?" — not "does Baltimore tract 2604 resemble DC
tract X." This makes the equity comparison genuinely portable: it rides entirely on
nationally-uniform data sources (Census ACS API + TIGER/Line tracts) plus the lat/lon
every candidate city already publishes.

**Use the *mix-adjusted* score, not the raw score (this matters).** This repository's own
headline finding is that **much of the apparent citywide equity gap is a service-*mix* effect**
— *which* services a neighborhood requests — rather than unequal delivery of the *same*
service (see `requirements.md` §3.5 / Tab 5). So comparing **raw** equity scores across cities
would confound two different things: real differences in how equitably each city *delivers*,
and mere differences in what each city's residents *request*. The cross-city equity comparison
therefore uses the **mix-adjusted overall score** — the volume-weighted mean of each city's
within-service-category overlap scores (the Tab 6 "adjusted" score) — as its primary metric,
keeping the raw score only as a secondary reference. The adjusted *overall* score is fully
portable and needs **no shared taxonomy**: each city scores within its *own* categories, and
only the final volume-weighted scalar is compared (P5.5-3). A wide raw↔adjusted gap for a city
is itself informative — it means that city's disparity is mostly mix-driven.

**What stays hard:** comparing the *same* request type across cities (do majority-Black areas
wait longer for pothole repair *specifically*, city by city?) requires harmonizing each city's
request-type taxonomy to a shared ontology. That is the Phase 5.7 stretch goal, deliberately
last. A *cross-city analysis of service-mix composition itself* is interesting but an explicit
**non-goal** of these dashboards — the equity tab isolates delivery equity, not demand mix.

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
| **5.5 Equity methodology** | Portable ACS-tract + TIGER equity join per city; per-city **mix-adjusted** overall overlap scores (raw kept as reference) | — | §6.5 — per-city adjusted + raw scores, raw↔adjusted gap, validation vs. Baltimore in-app numbers |
| **5.6 Equity tab (cohort)** | **Cross-City Service Equity** tab — each city's internal **mix-adjusted** race/income score (raw as reference), Baltimore as reference | ✅ Tab 8 | §6.6 — cross-city equity findings |
| **5.7 Within-type (stretch)** | Request-type taxonomy crosswalk; within-type equity comparison for shared categories | (extends Tab 8) | §6.7 — taxonomy mapping coverage + within-type findings |
| **5.8 Maturity index (enhancement)** | 311 open-data maturity scorecard over the cohort; Baltimore's rank + per-dimension gap profile; "credit where due" framing | optional in-app panel | §6.8 — scorecard, Baltimore rank, gap profile |

**Recommended cohort waves** (each wave = one adapter family coming online):

- **Wave 0 (MVP):** Baltimore + **DC** (ArcGIS — reuse existing client)
- **Wave 1:** **Philadelphia** (Carto — strongest demographic peer, first new adapter)
- **Wave 2:** **NYC, Chicago, San Francisco** (Socrata — leading-practice benchmarks; one adapter unlocks all three)
- **Wave 3 (optional):** **Detroit** (strong demographic peer, channel-scope caveat), then evaluate **St. Louis / Louisville**
- **Deferred:** **Boston** (revisit after the mid-2026 backend migration stabilizes)

The two-tab end state: **Tab 7 — Cross-City Service Delivery** and **Tab 8 — Cross-City
Service Equity**, both with Baltimore as the fixed reference.

> **Placement decision — RESOLVED (June 2026, ahead of 5.2).** The cross-city views live
> in a **dedicated "Compare cities" group, not appended to the within-Baltimore arc.** The
> app is now organized as two nested-tab groups — **🏙️ Within Baltimore** (the sequenced
> six-step story) and **🌐 Compare cities** — chosen because the two families are
> structurally different (cross-city is city-level only, has no tract/CSA `geo_level`, carries
> heavy comparability caveats, and shares almost no components), so blending them into one
> tab strip would conflate two different kinds of question and overflow the bar as the
> cross-city group grows. The shell shipped ahead of Phase 5: the "Compare cities" group
> already exists with placeholder inner tabs (**Service Delivery**, **Service Equity**, and a
> **Maturity Index** for §8) in `app/components/cross_city.py`, fronted by a comparability-
> caveat header. Phase 5 fills in those render bodies; the navigation and framing do not need
> to change. The design keeps the door open to migrating to `st.navigation` grouped sidebar
> pages later if the group grows large, since the render functions are already decoupled.

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

### 6.1 — Adapter + MVP pair (Phase 5.1) — _code shipped 2026-06-13; data run pending_

**Built:** the `src/balt311/cities/` adapter package (`base`, `arcgis`, `dc`, `baltimore`),
`peer_metrics` (uniform per-(city,year) metrics + ACS county population + upsert),
`scripts/peer_city.py`, and the `peer_city.yml` workflow. DC endpoint confirmed:
`maps2.dcgis.dc.gov/dcgis/rest/services/DCGIS_DATA/ServiceRequests/FeatureServer`, one
layer per year; **layer ids are not a clean year offset** (2023=15, 2024=16, 2025=18), so
the adapter discovers the layer by name at fetch time rather than hardcoding ids. Field
map: `SERVICECODEDESCRIPTION→SRType`, `ADDDATE→CreatedDate`, `RESOLUTIONDATE→CloseDate`,
`LATITUDE/LONGITUDE`. Uniform closure rule across cities: **closed iff a CloseDate is
present** (Baltimore's native SRStatus rule differs slightly — footnoted, not used here).

**First run (2026-06-14) surfaced a scoping bug, now fixed.** The MVP pair ran, but
Baltimore's `median_days_to_close` came back ≈0.0045 d (~6 min) and volume ≈1.08M
(per-1k 1874 vs DC's 628), while DC looked sane. Root cause: the aggregator ran over
*all* Baltimore records, so **ECC information-calls (closed instantly) and system /
non-resident records** dominated — exactly what the within-Baltimore `filter_equity_subset`
+ `aggregate_tract` exclude. DC's feed has no ECC/instant-close equivalent, so it was
unaffected. **Fix:** per-adapter `scope()` / `is_closed()` hooks (`cities/base.py`).
Baltimore now mirrors the within-Baltimore equity subset (resident-initiated, non-ECC,
geocoded) and SRStatus-based closure; DC keeps the generic defaults (non-ECC, geocoded;
closed = CloseDate present). Verified on synthetic data: contamination reproduced the
≈0 median, the scoped path recovers a clean multi-day median.

**Methodology caveat (intentional asymmetry):** the resident-initiated filter is applied
to Baltimore (where `MethodReceived` exists) but not DC (no channel field). So Baltimore's
cross-city scope equals its within-app equity subset, while DC's is all geocoded service
requests. Footnoted in the closure-definition expander.

**Cross-check (2026-06-14, on the corrected 2025 rows — 2024 still backfilling):** the
cross-city Baltimore figures agree with the within-Baltimore tabs up to two *intentional,
quantified* methodology differences — confirmed not to be bugs:

| 2025 Baltimore | cross-city tab | within-app | why |
|---|---|---|---|
| median days-to-close | **2.99** (record-level pooled) | 3.12 (Operations “citizen-initiated”: volume-weighted mean of per-tract medians) | different aggregation of the same records (~3 h apart) |
| total requests | **471,504** (resident, non-ECC, lat/lon present) | 459,905 (equity subset: same, but geocoded = spatially joined to a tract) | ~2.5% of records have coordinates that fall outside tract polygons |

The cross-city tab **must** use the pooled median: it is the correct citywide statistic and
the only one DC can match (no tract join). Real finding, 2025: Baltimore vs DC — median
~2.97 vs 2.90 d (comparable), closure 92% vs 99% (DC closes more), ~797 vs 648 requests per
1k residents (Baltimore higher demand per capita).

**Update (2026-06-14) — reconciled via single source of truth.** Rather than leaving the
~3-hour / ~2.5% gap documented, the pooled median is now the canonical citywide figure:
`metrics.citywide_pooled_metrics` writes `citywide_metrics_{year}.parquet` in the `process`
stage; the Operations citizen-initiated figure reads it (`_build_equity_citywide_ts`, legacy
weighted-mean fallback for un-regenerated years) and the cross-city Baltimore row reads the
*same* file (`BaltimoreAdapter.precomputed`, which also skips the ~12-min re-fetch). So Tab 1
and Tab 7 now agree by construction. The Operations "all requests" headline stays a
geographic weighted-mean (a pooled median over all requests is ~0 — ECC instant-closes). DC
tract join deferred to Phase 5.5. **Requires re-running the `process` stage for each year**
(citywide files don't exist until then; both consumers fall back gracefully meanwhile).

**Still pending:** the multi-year backfill (`peer_city_backfill.yml --force`) is in progress
to overwrite the remaining stale rows (2024 still shows the pre-fix 0.004-day / 1.08M row);
re-confirm each year as it lands.

**Backfill cross-check (2026-06-14):** all 10 `citywide_metrics_{year}` (2016–2025) present;
DC 2023–2025 sane and stable (~422–441k requests, 2.9–3.6 d median, 99% closure); 2024's
pre-fix garbage row is gone (now 514k / 3.16 d). **One gap found:** the cross-city Baltimore
rows do *not* yet equal the pooled `citywide_metrics` files — ~2.5% higher volume / a hair
lower median (the lat/lon-vs-tract-join signature), because the cross-city backfill ran
*before* the pooled files + `precomputed` code were on `main`, so it used the old fetch path.
Fix: re-run the cross-city backfill with `cities=baltimore, force=true` — Baltimore then reads
the pooled files (instant, no fetch) and Tab 1 == Tab 7 exactly. Canonical 2025 figures
(pooled): Baltimore 459,906 requests, 3.04 d median, 92.2% closure, ~797 per 1k; DC 440,600,
2.89 d, 98.8%, 656 per 1k.

### 6.2 — Delivery tab, MVP (Phase 5.2) — _tab shipped 2026-06-13; findings pending data_

**Built:** `app/components/city_delivery.py` (`render_city_delivery`) wired into the
"Compare cities" group's Service Delivery tab — metric toggle (requests-per-1k, median
days, closure rate, on-time rate), horizontal ranked bar with **Baltimore highlighted**,
rates-only, per-city closure-definition expander, soft-degrade for null metrics and for
years not shared across cities, and a "run the workflow" notice until `peer_city_metrics`
exists. **Findings (what Baltimore-vs-DC actually shows) pending the data run.**

### 6.3 — Cohort expansion (Phase 5.3) — _Philadelphia adapter shipped 2026-06-14; data run pending_

**First non-ArcGIS city — proves the adapter layer generalizes across platforms.**
Philadelphia 311 lives on **Carto** (OpenDataPhilly SQL API), not ArcGIS, so this added a
reusable Carto client (`cities/carto.py`, keyset paging on `cartodb_id`, mirroring
`arcgis.py`) and the `PhiladelphiaAdapter` (`cities/philadelphia.py`: table
`public_cases_fc`; `service_name→SRType`, `requested_datetime→CreatedDate`,
`closed_datetime→CloseDate`, `lat/lon`, `status`; closed = status 'Closed'; FIPS 42101).
Carto returns **ISO-8601 timestamps** rather than ArcGIS ms-epoch, so
`peer_metrics._parse_dt` now accepts both (inspecting the first non-null value, since a
`CloseDate` with open requests is object-dtype even when numeric; `format="mixed"` for
robustness). Registered in `ADAPTERS` as `philadelphia` and added to both workflows' default
city list. **Pending:** the CI ingest run (`peer_city_backfill.yml`, default cities now
`baltimore,dc,philadelphia`) — Carto is unreachable from the dev sandbox, same as ArcGIS.
Unit-tested: ISO+ms parsing, Carto keyset paging, Philly scope/closure, ms-epoch regression.

### 6.4 — Delivery tab, cohort (Phase 5.4) — _tab already N-city; verified with 3 cities_

The delivery component was built city-count-agnostic (ranked bars, Baltimore highlighted,
null-metric soft-degrade), so Philadelphia appears with no code change once its data lands —
confirmed by rendering the tab with a synthetic 3-city table (Baltimore stays the red
reference, peers gray, ranked by the selected metric).

### 6.5 — Equity methodology (Phase 5.5) — _pending_

### 6.6 — Equity tab, cohort (Phase 5.6) — _pending_

### 6.7 — Within-type comparison (Phase 5.7) — _pending_

### 6.8 — 311 open-data maturity index (Phase 5.8) — _pending_

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

**Coverage-census aggregators (§8.1 — used to survey the largest US cities):**
- National 311 Data Portal (catalog of city 311 datasets) — https://andrew-friedman.github.io/jkan/
- US City Open Data Census — Service Requests (311) — http://us-city.census.okfn.org/dataset/service-requests.html
- Open Data SA — 311 All Service Calls (San Antonio) — https://data.sanantonio.gov/dataset/311-all-service-calls
- Get It Done 311 (San Diego) — https://data.sandiego.gov/datasets/get-it-done-311/
- Dallas 311 Service Requests — https://www.dallasopendata.com/Services/311-Service-Requests/gc4d-8a49
- Austin 311 Public Data — https://data.austintexas.gov/Utilities-and-City-Services/Austin-311-Public-Data/xwdj-i9he/data
- Service Requests 311, City of Charlotte — https://data.charlottenc.gov/datasets/charlotte::service-requests-311/about
- 311 Service Requests, Denver Open Data — https://opendata-geospatialdenver.hub.arcgis.com/datasets/311-service-requests

**Baltimore open-data leadership (Phase 5.8 maturity context):**
- Baltimore 311 history (first US 311 system, 1996) — https://localwiki.org/baltimore/311_Non-Emergency_Services
- "311 Pioneering Baltimore Continues to Lead with Open311" (~2011 GeoReport v2 adoption) — https://www.open311.org/2011/09/baltimore/
- Open311 GeoReport v2 ecosystem & adopters — https://www.open311.org/2015/06/highlights-from-the-open311-ecosystem/
- What Works Cities — Baltimore (Silver certification, 2021) — https://whatworkscities.bloomberg.org/cities/baltimore-maryland-usa/

---

## 8. 311 Open-Data Maturity Index — scoring rubric (Phase 5.8)

**Purpose.** Rank Baltimore's 311 *open-data publishing maturity* against the set of US cities
that publish 311 open data — and, equally, **credit** the cities whose openness makes analysis
like this repository possible. This is recognition with a measurement attached, not a gotcha.

**Two caveats baked into every use of the index:**

1. **It measures publishing maturity, not service quality.** A city can publish beautifully and
   still deliver inequitably — indeed, only the open cities can even be *evaluated* for delivery
   or equity. A high maturity score is a precondition for accountability, not a substitute for it.
2. **"All US cities" is scoped to "US cities with public 311 open data"** — a few dozen — the only
   defensible denominator. Ranking against all ~19,000 municipalities is neither feasible nor
   meaningful; most run no 311 system, and most that do publish nothing.

**Baltimore's standing (the reference point):** first US 311 system (1996); CitiStat pioneer
(1999); early Open311 GeoReport v2 adopter (~2011, among only ~a dozen US cities); What Works
Cities **Silver** certification (2021). A genuine pioneer — and, on the *publishing* axis
specifically, a strong mid-tier performer that the Socrata leaders (NYC/Chicago/SF) now edge out
on unification, update cadence, and documentation (see §2). The index is designed to show both
truths honestly.

**Rubric** — score each cohort city 0–N per dimension (weights set in P5.8-1):

| Dimension | What it measures | Observable from |
|---|---|---|
| Availability & license | Is 311 published as open data under an open license? | Portal listing + license field |
| Granularity | Record-level per-request vs. aggregates only | Dataset schema |
| History depth | Years of continuous coverage | Earliest record / dataset range |
| Update cadence | Daily/nightly vs. annual vs. manual | Portal metadata |
| API access | Programmatic API (SODA / ArcGIS REST / Carto SQL) vs. download-only | Endpoint type |
| Standardization | Open311 GeoReport v2 compliance | Open311 endpoint presence |
| Field completeness | created + closed timestamps, geo, type, status, channel, reopen, cost | Field inventory |
| Geocoding coverage | % of requests with valid lat/lon | Computed during onboarding |
| Documentation | Data dictionary / metadata quality | Portal docs |

Most of these are already assessed during city onboarding (Phases 5.1 / 5.3), so the index is
nearly free to populate — it formalizes the §2 matrix into a scored, rankable form, and
produces a **per-dimension gap profile** for Baltimore that maps one-to-one onto
`requirements.md` §5 Gap Dependencies (turning "publish better data" into a measured,
prioritized list).

### 8.1 Coverage census — which of the largest US cities can be scored *at all*

The maturity index ranks the cities that *can* be scored. Equally important is naming the
ones that **cannot** — because the inability to run this analysis is itself the most striking
finding. An open-data evaluation of 311 service delivery and equity requires, at minimum,
**record-level requests with created + closed timestamps and geocoordinates**. Most large US
cities do not publish that. The census below surveys the ~40 largest US cities; it is a
**provisional first pass** (built from the two aggregators in §7 plus direct portal checks)
to be hardened in task P5.8-2.

**Status legend:**
- ✅ **Scoreable** — open, record-level 311 with timestamps + lat/lon; both delivery *and* equity analysis possible (a Baltimore-class capability).
- 🟡 **Partial / limited** — open data exists but constrained: short rolling history, app-channel subset only, aggregate-only, no API, or missing key fields.
- ❔ **None found / unconfirmed** — no open record-level 311 located in this pass. Provisional: this flags either a genuine gap *or* a discoverability problem — and under a maturity lens, hard-to-find data is itself a low score.

| Rank | City | Status | Note (provisional) |
|---|---|---|---|
| 1 | New York, NY | ✅ | Socrata `erm2-nwe9`; 24M+ records, daily |
| 2 | Los Angeles, CA | ✅ | MyLA311 on Socrata, per-year datasets |
| 3 | Chicago, IL | ✅ | Socrata `v6vf-nfxy`, unified since 2018 |
| 4 | Houston, TX | 🟡 | Open data portal exists; full record-level 311 appears limited (subset datasets) |
| 5 | Phoenix, AZ | 🟡 | Limited 311 publishing; verify scope |
| 6 | Philadelphia, PA | ✅ | Carto `public_cases_fc`, since 2014 |
| 7 | San Antonio, TX | ✅ | Open Data SA "311 All Service Calls," 2011–present |
| 8 | San Diego, CA | ✅ | "Get It Done 311" open dataset (app-channel) |
| 9 | Dallas, TX | ✅ | Socrata, 2018–present, 400+ types |
| 10 | San Jose, CA | 🟡 | 311 dataset on portal; confirm fields/history |
| 11 | Austin, TX | ✅ | "Austin 311 Public Data" on Socrata |
| 12 | Jacksonville, FL | ❔ | No open record-level 311 found this pass |
| 13 | Fort Worth, TX | ❔ | Open data portal; 311 record-level unconfirmed |
| 14 | Columbus, OH | 🟡 | 311 map present; record-level/API unconfirmed |
| 15 | Charlotte, NC | ✅ | "Service Requests 311" w/ type, lat/long, date (WWC Gold city) |
| 16 | San Francisco, CA | ✅ | Socrata `vw6y-z8j6`, since 2008, nightly |
| 17 | Indianapolis, IN | 🟡 | RequestIndy; open scope unconfirmed |
| 18 | Seattle, WA | ✅ | Customer Service Requests open data |
| 19 | Denver, CO | 🟡 | 311 dataset is **rolling 12 months only** — limited history |
| 20 | Oklahoma City, OK | ❔ | Unconfirmed |
| 21 | Nashville, TN | ✅ | hubNashville on Socrata |
| 22 | Washington, DC | ✅ | Open Data DC, per-year ArcGIS layers *(MVP pair)* |
| 23 | El Paso, TX | ❔ | Unconfirmed |
| 24 | Boston, MA | ✅ | Analyze Boston / CKAN *(mid-2026 backend migration)* |
| 25 | Detroit, MI | 🟡 | Improve Detroit = app-channel subset, not full 311 |
| 26 | Portland, OR | 🟡 | Limited; verify |
| 27 | Memphis, TN | ❔ | Unconfirmed |
| 28 | Louisville, KY | ✅ | Metro Open Data, ArcGIS, Open311-based |
| 29 | **Baltimore, MD** | ✅ | **Reference** — ArcGIS per-year layers, 2016–present |
| 30 | Milwaukee, WI | ❔ | Unconfirmed |
| 31 | Albuquerque, NM | 🟡 | Verify |
| 32 | Sacramento, CA | ✅ | Sacramento 311 on Socrata |
| 33 | Kansas City, MO | ✅ | data.kcmo.org / Socrata (since 2021 system) |
| 34 | Atlanta, GA | 🟡 | ATL311 exists; open record-level 311 not clearly published |
| 35 | Colorado Springs, CO | ❔ | Unconfirmed |
| 36 | Fresno, CA | ❔ | Unconfirmed |
| 37 | Tucson, AZ | 🟡 | Verify |
| 38 | Mesa, AZ | ❔ | Unconfirmed |
| 39 | Omaha, NE | ❔ | Unconfirmed |
| 40 | Raleigh, NC | ✅ | Raleigh open data 311 |

**Strong mid-size enablers worth crediting alongside the giants** (below the top 40 by
population but with mature, scoreable open 311 — several are close demographic peers of
Baltimore): Cincinnati ✅, Pittsburgh ✅ (WPRDC), Minneapolis ✅, New Orleans ✅, St. Louis ✅.

**What the census shows.** Of the ~40 largest US cities, only on the order of **half publish
311 open data mature enough to support this analysis**, and a smaller subset match Baltimore's
combination of **record-level data + a decade of history + an open API**. The rest — including
several cities far larger than Baltimore — simply **cannot be evaluated this way**: the data
isn't open, isn't record-level, or doesn't exist publicly at all. That is the point worth
underscoring. When this dashboard scrutinizes Baltimore, it is scrutinizing one of the
relatively few American cities that has *chosen to be scrutinizable*. The cities that score
✅ here — Baltimore foremost, as a first-mover — deserve credit precisely for accepting the
exposure that openness brings; the ❔ rows are not "better" cities, only less visible ones.
