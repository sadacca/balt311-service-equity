# Baltimore 311 Service Equity — Open Task List

The **living, forward-looking** task list, organized by topic. Completed work and the full
build/decision history (Phases 0–5 core, every shipped tab, each done item with its
implementation notes) are preserved in **`TASKS_ARCHIVE.md`** — item IDs like `P5.7-1` or
`P4e-3` cross-reference it. Roadmap context: `personas.md` (audience priorities),
`cross_city_comparison.md` (cross-city methodology + results log), `requirements.md` (spec).

**Status at a glance (2026-06-19):** all six within-Baltimore tabs and all three cross-city
tabs are live; the cross-city data layer is fully populated; the central `theme.py`
design-token pass shipped. **Nothing below is blocking** — every item is an enhancement,
a documentation write-up, deferred/stretch, or long-term.

---

## 1. UI / UX & Performance

Follow-on to the design-consistency pass (`app/components/theme.py`). Recommended order:
Tier 1 → Tier 2 → Tier 3.

**Tier 1 — Quick wins (low risk):**
- [ ] **Migrate off the deprecated `width` API** — swap ~49 `use_container_width=True` →
  `width="stretch"` across `app/` (Streamlit removed it after 2025-12-31).
- [ ] **Slim the sidebar** — `app.py` lines ~36–167 are ~132 lines of per-tab prose; trim to
  a thin nav + one `st.popover("About")`.
- [ ] **Modernize global controls** — Year + geo-unit `st.radio` → `st.pills` /
  `st.segmented_control`.
- [ ] **Help-expanders → `st.popover`** — inline ⓘ popovers in place of ~19 expanders.
- [ ] **Loading affordances** — `st.spinner(...)` around the Areas embedding and the
  Mix-Adjusted regression.

**Tier 2 — Snappiness (performance):**
- [x] **Gate within-Baltimore tabs** — *done, then superseded by the `st.navigation` reorg
  below: each view is its own page, so only the active page's body runs. Measured warm cost
  on the Operations landing dropped from ~sum-of-all-six (~5.3s) to just the active tab.*
- [ ] **Lean on `@st.fragment`** — wrap each page render so in-tab interactions don't rerun the
  whole script (only 2 fragments exist today, both in `area_embedding.py`). Smaller win now
  that pages are gated; needs per-page care (e.g. Operations' click-a-year-point relies on a
  full-script rerun that fragment-scoping would break).

**Tier 3 — Larger redesign (modern structure + visual system):**
- [x] **`st.navigation` + `st.Page` multipage** — *done. `app.py` is an entry script (shared
  year/geo state + masthead/sidebar) dispatching nine page-function wrappers via
  `st.navigation`; per-view URLs + browser back/forward, only the active page runs. `eq_metric`
  re-committed in the entry script so it survives the Equity→Mix-Adjusted page hop.*
- [x] **CSS layer + cards** — *done via `theme.inject_global_css()` (single static `<style>`):
  Inter + Space Grotesk display headings, soft rounded cards, pill nav, transparent toolbar,
  editorial masthead band, tighter type scale.*
- [x] **Custom metric cards** — *done: bordered, token-colored KPI cards with a primary accent
  top-edge, hover lift, and delta-as-pill — all `theme.py`-driven.*

---

## 2. Cross-City Documentation Checkpoints

Code + all eight `peer_city_*` data files are shipped and the three tabs are live; what
remains is recording the **actual cohort findings** into `cross_city_comparison.md` §6.x
(several sections exist but still read "findings pending data").

- [ ] **§6.1 (P5.1-6)** — DC schema quirks, closure semantics, row counts, Baltimore cross-check.
- [ ] **§6.2 (P5.2-4)** — Baltimore-vs-DC delivery findings + placement decision.
- [ ] **§6.3 (P5.3-5)** — one entry per onboarded city (quirks, comparability, validation).
- [ ] **§6.4 (P5.4-3)** — cohort delivery findings: where Baltimore lands on each metric.
- [ ] **§6.5/§6.6 (P5.6-5)** — cross-city equity cohort numbers + ranking.
- [ ] **§6.8 (P5.8-5)** — maturity scorecard, Baltimore rank, gap profile, credit framing.
- [ ] **§8 (P5.9-5)** — full-ranking methodology, per-dimension anchors, plausibility flag, headline.
- [ ] **Per-city onboarding QA (P5.3-4)** — spot-validate each city against its own published
  figure; record closure definition + channel scope.

---

## 3. Cross-City (Phase 5) — Deferred & Stretch

- [ ] **Race-based cross-city score (P5.6-6)** — revisit with a per-city group definition
  (income-only shipped); document coverage gaps where no defensible split exists.
- [ ] **Within-type comparison (P5.7-1/2/3)** *(stretch)* — shared request-type taxonomy
  crosswalk (anchor on Open311 categories), per-city within-type overlap scores, §6.7 checkpoint.
- [~] **Schema-probe depth (P5.9-4)** — *partial*: the 10-city cohort is scored against real
  schema/history; extend `scripts/verify_census.py` into a lightweight probe for the ~15
  derived scoreable cities (field count, history depth, cadence, geocoded share), run it in
  CI, and have `score_maturity.py` consume the results.
- [ ] **Plausibility flag in the league table (P5.9-6)** — annotate cities with implausible
  delivery figures (≥50% same-day, sub-day median, ≥99% closure) via
  `city_delivery._quality_flags`; surface a ⚠ reason column. Folds in the `field_completeness`
  "schema presence ≠ fill rate" fix (the Chicago/Memphis finding).
- [ ] **Census endpoint canvass — remaining ~20 cities (P5.8 follow-up)** —
  `scripts/verify_census.py` now rewrites Socrata/CKAN dataset pages and resolves ArcGIS
  Hub/Open Data pages via their `.geojson` download proxy (no item-id lookup needed), on top
  of the original ArcGIS FeatureServer `?f=json` fix. A live CI `--write` run surfaced four more
  fixable bugs in the prober itself (not the census data): a generic urllib User-Agent 403'd on
  several Hub domains (Charlotte, Indianapolis, Denver, Detroit, Atlanta — fixed with a real
  browser UA), a 1-row probe under-reported fields that were null on the sampled row (fixed by
  unioning keys across ~20 rows for Socrata/CKAN/ArcGIS/Hub), Dallas's correct dataset id
  returned nothing (likely anonymous throttling — fixed by sending `$$app_token` /
  `SOCRATA_APP_TOKEN`), and ArcGIS/GeoJSON store coordinates structurally (a `geometry` object)
  rather than in a named field, so several geocoded cities (NYC, Chicago, Boston, Memphis, KC,
  Raleigh, Pittsburgh) read as "no geo" until geometry-presence became its own signal. Cincinnati
  additionally got a `/api/views/{id}/rows.json` fallback mirroring its adapter's documented
  Tyler-portal workaround, though the census `note` already records that as of June 2026 the
  portal blocks *all* API paths without login — likely unfixable until that changes.
  San Diego/Phoenix/San Antonio/Houston/Louisville/Sacramento still errored (404/500/empty) on
  existing recorded URLs even after CKAN+Hub support landed; a web canvass didn't turn up a
  clearly-different correct URL for any of them (Houston's specific FeatureServer dataset may
  be stale — search turned up a "deprecated effective April 2025, see Calls for Service
  (Consolidated)" note, but no confirmed replacement URL) — needs a live re-run to see how many
  of today's prober fixes already resolve them before further URL guessing.

  **June 21 live re-run (`maturity_refresh.yml` → `verify_census.py --write`)** surfaced 9
  api-tier regressions, all real prober bugs (not data rot): the geometry-hint fix never
  fired for plain ArcGIS REST FeatureServer/MapServer URLs (Memphis) because `_to_api_url`'s
  `?f=json` only ever returns layer *metadata* (schema, no `features`) — fixed by adding
  `_arcgis_rest_fields()`, which resolves to a layer and hits `/query?...&f=json` for real
  records, mirroring `cities/arcgis.py`'s live request shape. Separately, the created/closed
  field-name heuristics missed real production field names — `open_date_time` (Kansas City),
  `requestdate` (Memphis), `resolution_date`/`completion_date` — because the substrings
  weren't contiguous in those names; fixed by grounding `_CREATED`/`_CLOSED` in the actual
  `CANDIDATES`/`field_overrides` lists the live adapters (`socrata.py`, `memphis.py`,
  `nashville.py`, `dc.py`) already match against real data. Also found `maturity_refresh.yml`
  never passed `SOCRATA_APP_TOKEN` to the verify step, so every Socrata-platform probe ran
  anonymously-throttled (Dallas's "no records returned" is the textbook symptom) — now wired
  through. Genuinely unresolved (stale/unconfirmed URLs, not a prober bug): Raleigh, Pittsburgh,
  New Orleans, St. Louis, Minneapolis, Louisville — consistent with the leads below not yet
  confirming a replacement URL. Needs another live re-run to confirm these fixes close out
  Memphis/Kansas City/Dallas and to see the net regression count drop.

  The fixes above cover every census row whose `endpoint_url` already names a specific
  dataset. The cities below only have a portal
  *homepage* recorded, so there's no dataset-specific URL to rewrite — each needs a human (or
  an agent with real network access; this sandbox blocks all outbound fetches, including
  `WebFetch`, to literally every external host tested) to open the portal and find the actual
  dataset. Leads gathered via web search, **unconfirmed, do not trust without a live probe**:
  - **Sacramento** — current view `data.cityofsacramento.org/datasets/5b9a9448663f41b1898643b6d91201c4_0/data`
    (older yearly snapshots also exist for 2014-2016; this is the "current" one).
  - **Indianapolis** — `data-indygis.opendata.arcgis.com/datasets/mayors-action-center-request-indy-service-requests`
    (Mayor's Action Center — Indy's name for 311).
  - **Raleigh** — `data-wake.opendata.arcgis.com/datasets/ral::ask-raleigh-requests`
    ("Ask Raleigh" — Raleigh's name for 311).
  - **New Orleans** — Socrata `data.nola.gov` resource `3iz8-nghx`, but documented as
    "Historic Data: 2012-2018" — likely superseded by a newer dataset; needs checking, not a
    straight swap.
  - **Minneapolis** — confirmed on ArcGIS Hub (`opendata.minneapolismn.gov`), one
    FeatureServer per year named `Public_311_YYYY`, but the org-specific service host (the
    `services#.arcgis.com/<org-hash>/...` part) wasn't found via search — needs a live
    browse to get the real service URL.
  - **St. Louis** — has a documented Open311 GeoReport v2 API, but it requires an API key
    (not anonymously fetchable) — needs a registered key, not a URL fix.
  - **Phoenix, San Jose, Tucson** — portal is plausibly CKAN/ArcGIS already (Phoenix and San
    Jose's recorded URLs already match the new CKAN `/dataset/<slug>` rewrite and will be
    auto-probed), but no specific 311 resource/dataset id could be confirmed via search.
  - **Milwaukee, Atlanta, Colorado Springs, Fresno, Mesa, Omaha, Jacksonville, Fort Worth,
    Columbus, Oklahoma City, El Paso** — only the portal homepage is confirmed; no specific
    311 dataset id surfaced.

---

## 4. Equity Analysis Enhancements

- [ ] **Adjusted metrics in the Equity tab (P4e-3/4/5)** — surface the shipped
  `*_adjusted_metrics_*` columns: add "Adjusted closure rate / days to close" to
  `map_view.METRIC_OPTIONS` (diverging scale centered on the citywide norm), to
  `equity_distributions.py` (adjusted overlap score beside raw), and to `equity_trend.py`
  (dashed adjusted series). **Data already exists — the most actionable feature work.**
- [ ] **BNIA direct CSA demographics (P4-5)** — replace the population-weighted ACS rollup with
  authoritative BNIA CSA indicators (`pct_nhblk`, `pct_nhwht`, `mhhi`); validate against the rollup.

---

## 5. Area Analysis & Peer Groups

- [~] **Cluster the embedding into named peer groups (P4d-7b)** — *partial*: quadrant grouping
  (UL/UR/LL/LR) shipped; remaining = algorithm-selected cluster labels (KMeans/Agglomerative +
  auto-generated labels) and cross-tab `geoid → peer_group` propagation into the other tabs.
- [ ] **Area-analysis panels (P4b-1/3/4/5)** — area overview card with peer benchmarks, peer
  comparison chart, outcome-outlier (residual-vs-peers) map, SRType mix-vs-peers view. (P4b-2's
  peer index already shipped as the Areas embedding.)
- [ ] **SRType×SRType correlation heatmap (P4d-8)** *(optional)* — which service categories
  co-occur across geographies.
- [ ] **Census PDB demographic trajectories (P4d-6b)** — ingest the Planning Database, align its
  multi-year vintages, and animate demographic drift in the embedding alongside service-usage drift.

---

## 6. New Tabs / Views

- [ ] **Request Source Analysis tab (P4c-1/2/3/4)** — citizen vs. system/proactive vs. ECC
  volume split, source mix by SRType, source mix by geography (needs `is_resident` passed
  through the geo aggregation), and a YoY source trend. Makes the scope-banner split explicit.
- [ ] **Seasonality tab (P6-1/2/3)** *(long-term)* — monthly pipeline aggregation
  (`{geo}_srtype_monthly_{year}.parquet`), citywide/per-type seasonal trends, and a seasonal
  equity check (does peak-month slowdown fall harder on lower-income areas?).

---

## 7. Data Validation & Technical Debt

- [ ] **TD-2** — manually validate the Mann-Whitney overlap scores + demographic calcs
  (majority-group counts, CSA rollups, ACS income vs. published tables, trend-direction sanity).
- [ ] **TD-4** — cross-year duplicate `SRRecordID` check.

---

## 8. Future Work / Blocked

- [ ] **Council-district overlay + district equity (P4f-5/6)** — *blocked on external data*:
  needs the Baltimore City council-district boundary GeoJSON + a tract→district crosswalk; then
  a `stage_council_crosswalk()` modeled on the BNIA/NSA `geopandas.sjoin_nearest` pattern, a
  toggle layer on the Equity choropleth, and district-filtered distributions. Highest-value
  council-member feature once the boundary data lands.

**Persona-gap enhancements** *(post-v2.0.0, from `personas.md`):*
- [ ] **Citizen** — address/neighborhood search (geocode → tract, auto-select on map);
  simplified mobile report card (✓/⚠/✗ per metric, shareable via `?geo=<geoid>`).
- [ ] **Citizen journalist** — CSV export buttons (`st.download_button`); a YoY change-summary
  panel at the top of the Equity tab.
- [ ] **Citywide official** — executive / print view (`?view=executive`, single-screen, print-friendly).
- [ ] **HS civics / stats student** — guided-tour mode (`?tour=1`); a per-tab plain-language
  narrative callout computed from live data; a "cite this data" block in the sidebar.
- [ ] **Ops manager** — geographic performance choropleth for a selected SRType
  (volume/closure/days toggle); SRType geographic outlier table (top/bottom-5 CSAs).

---

*Living todo — reorganized by topic 2026-06-19. Full completed-work history and detailed
specs: `TASKS_ARCHIVE.md`. Mark items `[x]` when done; move substantial completions (with
their implementation notes) into the archive to keep this list forward-looking.*
