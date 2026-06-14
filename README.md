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

## Why this analysis is possible — credit where it's due

Before any of the findings below, one fact deserves to lead: **this entire repository exists only because Baltimore publishes its 311 data openly, completely, and at the record level.** Baltimore was the **first US city to deploy a 311 non-emergency system (1996)**, pioneered **CitiStat (1999)** — the data-driven performance-management model the rest of the country went on to copy — and was an **early adopter of the Open311 GeoReport v2 standard (~2011)**, a standard that even today only on the order of a dozen US cities have implemented, putting Baltimore ahead of many far larger cities. That open posture is exactly what lets a resident, journalist, or researcher evaluate the city in the depth and breadth this dashboard does.

There is an uncomfortable irony worth naming: the more openly a city publishes, the more it exposes itself to scrutiny, while less-transparent cities escape criticism by default. Most US cities simply could not be analyzed this way — the data isn't there. So this dashboard holds two things at once: it evaluates Baltimore's performance *and* it is a tribute to Baltimore's openness. Every critical finding here should be read in that light. Openness invites criticism, and that is precisely why it deserves praise — a city willing to be measured this honestly is doing something most are not, and that willingness is itself a civic achievement.

---

## How this dashboard tells its story

311 data answers very different questions depending on who's asking. A council member wants to know whether the gaps in their district are typical, or worse, than similar neighborhoods elsewhere. A department manager wants to know how their service type is performing — without wading through demographic framing that isn't theirs to interpret. A journalist or citywide official wants a defensible answer to "is service delivery equitable, and if not, which services and neighborhoods are driving that gap?" Rather than build one view that tries to answer all of these at once, the dashboard is structured as a sequence of lenses, each a complete answer for one audience that also sets up the next. Six tabs are live today, in the order the app presents them, completing the within-Baltimore arc:

1. **Operations** *(live — first tab)* — the citywide health check: KPIs, year-over-year trends, and a request-volume map answer "how is the city doing, overall, this year vs. prior years?" The landing view for anyone — resident, manager, or official — who wants the big picture before drilling into anything else.
2. **Services** *(live)* — the operations manager's deep dive, with the equity framing deliberately stripped out: how does my service category compare to others, and how has it performed across time? The tool a department head reaches for when the question is "how am I doing," not "how does this break down by race or income."
3. **Area Service Usage** *(live)* — the bridge from *what* to *where*: which neighborhoods use 311 similarly, and which neighborhoods look alike demographically? Two complementary 2D embeddings — service-request mix and demographic profile — place every tract and CSA into a shared coordinate space, with CSA bubbles floating above their constituent tract dots. Quadrant backgrounds group neighborhoods into four named regions; an animated year slider traces how usage patterns shift over time; cross-coloring (income on the usage chart, service type on the demographic chart) tests whether demographically similar areas also request similar services. For council members and managers alike: the neighborhoods your area actually resembles.
4. **Equity** *(live)* — the citywide equity check: does service quality differ systematically by race or income, citywide, this year and over time? The headline question for journalists, advocates, and citywide leadership, answered with maps, distribution comparisons, and a multi-year trend of the Mann-Whitney overlap score.
5. **Service Equity** *(live)* — does the citywide equity picture hold up within individual service categories, or does it mask very different stories for potholes vs. bulk trash vs. rodent control? It turns out to mask something real: scored within individual categories — and within individual service types — equity scores run substantially higher than the citywide aggregate, evidence that a meaningful share of the apparent citywide gap reflects *which* services different neighborhoods request (a usage-mix effect) rather than *how* any one service is delivered once requested. The improvement isn't total, though — some disparity persists even at that finer grain, so the citywide number still matters; it just needs this view to interpret correctly. The tool a journalist reaches for when the citywide number raises more questions than it answers.
6. **Mix-Adjusted Equity** *(live)* — the most defensible version of the equity claim, formalizing what tab 5 surfaces informally: are the gaps explained by *which* services an area happens to request (a structural, type-mix effect), or by *how* the same service is delivered to different neighborhoods (the cleaner equity signal)? A year-over-year trend of the raw vs. mix-adjusted citywide score, a per-neighborhood map and raw-vs-adjusted scatter that reweight every area to the citywide service mix, a within-type equity ranking, and a fixed-effects regression give citywide officials and journalists several independent lines of evidence for the same conclusion — the kind of rigor a contested public claim needs to hold up.

Read top to bottom, the six live tabs trace a complete arc: an **operational overview** anyone can use → an **operational deep-dive** for the people who run individual services → **where** those services land, and which neighborhoods share a common 311 character → a **citywide equity check** → that same equity lens re-scored within individual service categories, where the most important finding surfaces → and finally a **mix-adjusted view** that formally separates the type-mix effect from the cleaner delivery-equity signal tab 5 hints at, in time and in space. No two adjacent tabs require a conceptual leap; each answers a real, documented need (see `personas.md`) and hands the reader naturally to the next question.

---

## What it shows

### Operations tab

*A citywide health check: request volume and performance trends.* The default tab — the landing view that answers "how is Baltimore 311 performing overall?" before asking equity questions.

**City-wide Performance**

A KPI bar shows four headline metrics — Requests received, Median days to close, Closure rate, On-time rate — each with a year-over-year delta badge (neutral color). Directly beneath each tile, a small caption shows the citizen-initiated equivalent (Phone / API / Mail / Email requests only), so both the all-requests picture and the resident-experience picture are visible at a glance. A `Δ vs. {year}` caption notes the comparison year.

An inline metric selector (horizontal radio) above the time series switches between Median days to close, Closure rate, and On-time rate. Below it, a dual-trace time series shows both "All requests" (solid blue) and "Citizen-initiated" (dashed orange) for the selected metric across all available years (2016–2025). Clicking any point navigates to that year.

**Breakdown by Request Type**

Category pills (SW, HCD, TRS, etc.) filter the table by service department prefix. The performance table shows every request type with its full department name, a plain-language service subtype label, request volume, closure rate, median days to close, and on-time rate. Clicking any row selects that type and populates two year-over-year bar charts below: total requests by year and median days to close by year, with the selected year highlighted in red.

**Geographic Distribution**

A choropleth map at the bottom shows request volume by census tract or CSA. A "View as: Census Tract / CSA" toggle above the map switches the geographic unit. The map uses a sequential Blues colorscale from 0 to the maximum count (not a diverging scale). When a table row is selected the map filters to show counts for that specific SRType only (sourced from `{geo_key}_srtype_metrics_{year}.parquet`). Cells with fewer than 5 requests are suppressed to avoid displaying statistically unreliable counts.

---

### Services tab

*How individual service categories perform and compare.* A pure operational drill-down — usage volume, closure rate, time to close, on-time rate — with no race or income framing. Built for department managers and anyone who wants to compare how individual service types perform, independent of demographic context.

**Among-category comparison** — year-over-year multi-line trends for the highest-volume categories: usage (log scale, since volume spans orders of magnitude across departments), closure rate, and median days to close, each with a dashed citywide-average reference line so a category can be read against the city as a whole, not just its peers.

**Category drill-down** — a two-tier selector (top categories shown by acronym with a legend, the rest tucked behind an expander and labeled by full department name) reveals that category's own year-over-year trend (volume + days to close), plus a within-category breakdown by subtype: the highest-volume types individually, with the remainder folded into "all other types" so high-cardinality categories like Solid Waste stay readable.

---

### Area Service Usage tab

*Which neighborhoods use 311 similarly, and which neighborhoods look alike demographically?* The bridge between the operational and equity halves of the arc.

A **View** toggle at the top switches between two complementary 2D embeddings — both fit once on the union of tract and CSA data so both geo levels share a single, stable coordinate system. Tracts appear as small dots; CSAs as larger labeled bubbles sitting near the centroid of their constituent tracts. A ~10% subsample of tracts are labeled with their NSA neighborhood name (farthest-point sampled for even coverage, minimum 3 per quadrant); all CSAs are plotted and hoverable.

Four light-filled **quadrant backgrounds** (UL / UR / LL / LR — upper-left, upper-right, lower-left, lower-right, divided at median x and median y) group the embedding into named regions. Each geography's quadrant is determined by its mean position across all years, so the grouping is stable even as individual year-points shift.

**Service-usage view** — geographies positioned by what their residents call 311 about (CLR-transformed high-level category shares, QuantileTransformer, PCA). Colored by median household income. An animated year slider traces each geography's trajectory through the shared space across all available years (2016–2025), showing which neighborhoods' 311 character shifts and which stays constant.

**Demographic view** — geographies positioned by ACS 2023 demographic profile: race, income, poverty, age, education (RobustScaler + PCA). Colored by the predominant 311 service type for the selected year. No year animation — ACS demographics are a single snapshot. Cross-coloring answers: *do areas that look alike demographically call 311 for the same things?*

Below the scatter, two additional panels appear for both views:

- **Predominant-subtype bar** — for each quadrant, what % of tracts have each specific SRType (e.g. "SW-Dirty Street", "HCD-Rodents") as their single most-requested service. Only subtypes that dominate at least one tract appear; top 8 globally + Other
- **Neighborhood list** — CSA names in two columns by quadrant, for quick identification of which named neighborhoods fall in each group

---

### Equity tab — Map

*Does service quality differ systematically by where it's delivered and who it's delivered to?* Differences here can reflect *which* services an area requests as much as delivery quality — the Service Equity tab investigates that distinction directly.

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

*Does the citywide equity picture hold up or differ within individual service categories and types?* The equity-flavored mirror of the Services tab: the same multi-line trend language — top-N categories, top-N subtypes folded into an "all other" remainder, a two-tier selector, a dotted year guide — but tracking the **Mann-Whitney equity score** (race and income overlap, on the same fixed 0–100% scale and green/amber/red bands as the Equity Trend chart) instead of operational metrics. CSA is the default geographic unit here (and across the app) — it carries less sparse-cell suppression than census tracts, so its equity scores are the more reliable starting point.

**The headline finding — three grains, side by side**: a pair of bar charts (race, income) opens the tab with the current year's actual scores at three grains: citywide-pooled, the average within-category score, and the average within-individual-type score. Scores climb substantially at each finer grain — direct evidence that part of the apparent citywide gap reflects *which* services different neighborhoods request (a usage-mix effect) rather than *how* any one service is delivered once requested. The improvement is real but not total — disparity persists even at the finest grain, so the citywide number still matters; it just needs this view to interpret correctly.

**Among-category equity trend** — multi-line equity-score trends for the highest-volume categories, read against a dashed "All categories" reference line and the same threshold bands as the citywide Equity Trend.

**Where equity review is most warranted** — a Race/Income toggle ranks the worst-scoring *individual service types* (deliberately not high-level categories — a category can read "not bad" overall while one of its own subtypes is the one actually driving disparity), restricted to types that meet minimum data standards (geographic coverage, request volume, and years of history) so a thin or noisy sample can't crowd out a type with a real, well-supported low score. Ranking is by the selected dimension specifically, so a flagged type is guaranteed to score low on the dimension shown — not just on whichever of its two scores happens to be lower. A histogram overlays the flagged types (red) on the full distribution of eligible scores (gray) — showing whether they're a separated tail or just the lower edge of one continuous spread — paired with each flagged type's year-over-year score trend.

**Category drill-down** — select a category (the same two-tier selector as the Services tab) to see its own equity-score trend against the all-categories baseline, plus a within-category breakdown of equity scores by subtype.

---

### Mix-Adjusted Equity tab

*How much of the citywide gap is about which services an area requests versus how the same service is delivered?* The payoff of the equity arc, formalizing tab 5's finding in time and in space, then checking it against a regression.

**Normalized equity, year over year** — the citywide equity score computed two ways across every year: the **raw** geo-level score (the Equity tab's number) and the **mix-adjusted** score (the same comparison run *within* each service type, then volume-weighted across types). The gap between the two lines is the part of the disparity that reflects *which* services neighborhoods request rather than how any one is delivered. Race and income panels, on the same fixed 0–100% scale and threshold bands as the Equity Trend.

**Mix-adjusted delivery across neighborhoods** — every geography reweighted so its service-type mix matches the citywide mix (**direct standardization**, computed record-level in the pipeline — the only sound way to mix-adjust a median, since a median does not decompose into a weighted mean of per-type medians). Shown as a residual choropleth (blue = better than the citywide norm for that mix, red = worse) and a **raw-vs-adjusted scatter** (x = the verified rollup value, identical to the Equity tab; y = the mix-adjusted value; the diagonal is where the mix made no difference), shaded by median income, with the two halves split by the diagonal labeled where neighborhoods come out faster/slower (or better/worse) than they appear once mix is held constant. Below them, a sortable, searchable **neighborhood index** lists every geography (census tracts resolved to their NSA neighborhood names) with its raw, mix-adjusted, and Δ-vs-city values. A neighborhood that asks for structurally slow services isn't penalized for that here — only for delivering the citywide service mix faster or slower than the city as a whole.

**Which service types are delivered most unequally** — every eligible service type ranked by its within-type equity score (the gap that remains after the mix effect is stripped out), with a drill-down to the raw race/income distributions behind any one type.

**Regression** — a weighted least-squares panel of `log(1 + median days to close)` on neighborhood race and income with service-type and year fixed effects, as an independent corroboration of the overlap-score story: does a race or income gap survive once *what* is requested and *when* are held constant?

---

### Compare cities

*Baltimore against a cohort of peer cities, at the city level.* A separate tab group — different data, different caveats — so city-to-city comparison never gets confused with the within-Baltimore story. The cohort spans **four data platforms** through a pluggable per-city adapter layer: ArcGIS (Baltimore, DC), Carto (Philadelphia), Socrata (NYC, Chicago, San Francisco, Austin, Nashville, Kansas City), and CKAN (Boston).

**Service Delivery** *(live)* — Baltimore against the cohort on the same delivery metrics — requests per 1,000 residents, median days to close, closure rate, on-time rate — shown as **rates, never raw counts**, with Baltimore highlighted and a city multiselect to focus the comparison. Median days-to-close is a **record-level pooled median computed identically for every city**, the same canonical figure the Operations tab reports for Baltimore's citizen-initiated median, so the cross-city row and the within-Baltimore figure never disagree. Each city's closure definition and channel scope is footnoted, because native 311 semantics differ.

**Open-Data Maturity** *(live)* — how maturely each city *publishes* its 311 open data (not how well it delivers service). A scored 9-dimension rubric ranks the cohort, with Baltimore's rank and a per-dimension **gap profile** naming the specific practice that would close each gap. A **coverage census** of the 40 largest US cities (plus mid-size enablers) records which can be evaluated at all — scoreable / partial / unconfirmed — each tagged with an **evidence tier** (live API check, city portal, or third-party). The framing leads with credit: openness is the precondition for accountability, and the cities that publish openly deserve recognition for accepting the scrutiny that brings.

**Service Equity** *(coming next)* — each city's own race/income service-delivery gaps, on the same overlap-score basis as the within-Baltimore Equity tab. Requires per-city demographic joins and is still being built.

---

## Data sources

| Source | What | How accessed |
|---|---|---|
| [Baltimore Open Data](https://data.baltimorecity.gov) | 311 service requests 2016–2025 | ArcGIS FeatureServer REST API (annual files 2023+; `311_Customer_Service_Requests_Yearly` layers for 2016–2022) |
| [Census Bureau GENZ2023](https://www.census.gov/geographies/mapping-files/time-series/geo/cartographic-boundary.html) | Census tract boundaries (2020 definitions) | Cartographic boundary shapefile ZIP |
| [BNIA VitalSigns](https://github.com/BNIA/VitalSigns) | Tract → CSA crosswalk | GitHub raw CSV |
| [Census ACS 2023 5-Year](https://www.census.gov/data/developers/data-sets/acs-5year.html) | Tract population (B01003), race (B02001), median household income (B19013) | Census Data API |
| **Cross-city 311** (peer cohort) | DC, Philadelphia, NYC, Chicago, San Francisco, Austin, Nashville, Kansas City, Boston | Per-city adapters over ArcGIS REST, Carto SQL, Socrata SODA, and CKAN DataStore APIs |
| [Census ACS county population](https://www.census.gov/data/developers/data-sets/acs-5year.html) | Per-city denominator for requests-per-1k (B01003, county; NYC = 5-borough sum) | Census Data API |

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
│  + adjusted stage → mix-standardized adjusted metrics   │
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
    category_explorer.py    # Services tab: operational category drill-down
    area_embedding.py       # Area Service Usage tab: PCA usage + demographic embeddings
    category_equity_explorer.py # Service Equity tab: among/within-category equity trends
    equity_adjusted.py      # Mix-Adjusted Equity tab: normalized trend, residual map/scatter, ranking, regression
    srtype_shared.py        # Shared SRType loaders + category-pill scaffolding
    utils.py                # Shared: overlap_score, score_label, format_metric

data/
  processed/                # Committed — read by the app at runtime
    tract_metrics_{year}.parquet          # Tract-level equity metrics
    csa_metrics_{year}.parquet            # CSA-level equity metrics
    srtype_metrics_{year}.parquet         # City-wide metrics per SRType
    tract_srtype_metrics_{year}.parquet   # Tract × SRType: requests + performance
    csa_srtype_metrics_{year}.parquet     # CSA × SRType: requests + performance
    tract_adjusted_metrics_{year}.parquet # Tract: mix-standardized median + closure (Tab 6)
    csa_adjusted_metrics_{year}.parquet   # CSA rollup of tract adjusted metrics
    tract_boundaries.geojson
    csa_boundaries.geojson
    tract_demographics.csv  # ACS race + income by tract (year-independent)
    csa_demographics.csv    # CSA rollup of tract demographics
  raw/                      # Gitignored — rebuilt by pipeline
  interim/                  # Gitignored — rebuilt by pipeline

scripts/
  pipeline.py               # Headless pipeline: --stage ingest/process/srtype/adjusted/demographics

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

**Mix-adjusted metrics** (Tab 6): each geography's requests reweighted by **direct standardization** so its service-type mix matches the citywide mix, then the metric is read off — `adj_median_days_to_close` as an interpolated weighted median of the geography's closed records (weight `citywide_closed_count(type) / geo_closed_count(type)`), `adj_closure_rate` as the citywide-request-weighted mean of its per-type closure rates. Computed record-level in the pipeline `adjusted` stage on the same equity subset as the raw rollups; the residual a geography shows on the map is `adjusted − citywide reference`. This is the statistically correct way to mix-adjust a median — a median does not decompose into a weighted mean of per-type medians, so a per-type-median reconstruction is unsound.

**On-time rate**: closed requests with CloseDate ≤ DueDate, as a share of all closed requests where DueDate > CreatedDate. SRTypes where DueDate < CreatedDate are excluded (known data artifact). Open requests are not counted as late.

**Requests per 1,000 residents**: total equity-subset requests / ACS 2023 5-year tract population × 1,000.

**Mann-Whitney overlap score**: `1 - 2 × |P(A > B) - 0.5|` across all pairwise comparisons between the two demographic groups. Score of 1.0 means the groups are perfectly interleaved; 0.0 means one group is entirely above the other. More sensitive than IQR overlap to tail differences and systematic shifts when medians are close. Requires ≥ 3 non-null values per group; returns NaN otherwise. Computed separately for race-based and income-based comparisons, for each equity metric.

**Demographic classification**: race groups require >50% of tract/CSA population identifying as a single race (mixed tracts excluded from race comparison). Income groups split at the citywide median of the tract/CSA distribution for the selected year and geography level.
