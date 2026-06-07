# Release Notes

## 2026-06-07 — Area Service Usage tab + NSA neighborhood labels

This release delivers the **Area Service Usage** tab (previously a stub), a
Baltimore neighborhood name crosswalk for tract-level scatter labels, and a
series of UX refinements to the scatter plot and existing tabs.

---

### New: Area Service Usage tab (Tab 3)

A fully built embedded-geography explorer with two complementary views,
both sharing a single PCA coordinate system so tract and CSA positions are
directly comparable.

**Service usage view**
- Every census tract and CSA projected into 2D by their mix of 311 service
  request categories (CLR transform → QuantileTransformer → PCA), fit once
  across all available years so year-to-year movement represents real change
- Animated year slider lets you trace neighborhood trajectories through the
  embedding space (2016–2025)
- Colored by median household income (Viridis)

**Demographic profile view**
- Geographies placed by ACS 2023 demographic profile: race, income, age
  structure, Hispanic/Latino ethnicity, educational attainment, and poverty
  rate (RobustScaler → PCA) — nine features, making the space meaningfully
  multi-dimensional
- Colored by predominant 311 service type for the selected year
- Cross-coloring between views lets you test whether demographic similarity
  predicts service-usage similarity

**Quadrant grouping**
- 2D space divided at median x and median y into four quadrants: UL / UR /
  LL / LR (upper-left, upper-right, lower-left, lower-right)
- Labels are positional embedding dimensions, not geographic compass bearings
- Light background fills distinguish quadrants; labels are stable across years
  (assigned by each geography's mean position)

**Below the scatter**
- Predominant-subtype bar: for each quadrant, what % of tracts have each
  specific SRType (e.g. "SW-Dirty Street") as their single most-called service
- Neighborhood list: CSA names in two columns by quadrant, small text, updates
  with the active embedding view

---

### New: NSA neighborhood name labels on scatter dots

Baltimore's ~278 Neighborhood Statistical Areas (NSAs) are now mapped to
individual census tracts and displayed as scatter text labels.

- New pipeline stage: `python scripts/pipeline.py --stage nsa`
  Downloads NSA boundary polygons from Baltimore City Open Data (Open
  Baltimore ArcGIS Hub), spatial-joins tract centroids to NSA polygons via
  GeoPandas, and writes `data/processed/tract_to_nsa.csv`
- New GitHub Actions workflow: **Build NSA crosswalk** (`nsa_crosswalk.yml`)
  Manual dispatch — runs the spatial join in CI and commits the crosswalk
  file. No API key required.
- Labels are subsampled (≈10% of tracts, minimum 3 per quadrant) using
  farthest-point sampling to maximize spatial spread and avoid clutter
- Hover tooltip title shows **"Neighborhood · Tract XXXX.XX"** (Census
  standard tract number format) for immediate identification

---

### New: Expanded ACS demographic feature set

The demographic embedding (and `tract_demographics.csv` / `csa_demographics.csv`)
now includes nine ACS 2023 5-year variables, up from three:

| Variable | Source |
|---|---|
| % Black, % White | B02001 |
| Median household income | B19013 |
| % Hispanic/Latino | B03003 |
| % Under 18, % 65+, Median age | B01001 / B01002 |
| % Bachelor's or higher | B15003 |
| % Below poverty line | B17001 |

Use `regen_demographics.yml` (GitHub Actions) to regenerate both CSVs.

---

### UX refinements — Area Service Usage tab

- Scatter viewport padded at 27% of the 5th–95th percentile range on each
  axis (up from 8%), giving labels room to render without clipping
- Text label font size increased (8 → 11px), dark near-black color for
  legibility against light quadrant backgrounds
- Quadrant labels renamed NW/NE/SW/SE → UL/UR/LL/LR to avoid geographic
  cardinal-direction confounds
- Neighborhood list condensed from four equal columns to two columns with
  smaller text
- Category-mix stacked bar removed; the predominant-subtype bar is more
  specific and sufficient

---

### UX refinements — existing tabs

**Services tab**
- Storytelling scaffolding added to the category explorer: section headers and
  bridging captions make the analysis arc more explicit
- Chart readability improvements (legend background, category trend lines)

**Service Equity tab**
- Race/income dimension toggle added to the concerning-types review panel
- Tract/CSA grain toggle for the geographic breakdown
- Concerning-subtype ranking refactored to flag the worst performers on the
  selected equity dimension rather than overall

**Sidebar and tab labels**
- Tab labels tightened across all five tabs
- Sidebar blurbs updated to reflect current feature set for each tab
- Arc narrative updated to acknowledge that within-category equity gaps are
  substantially smaller than citywide gaps — evidence the citywide signal
  partly reflects service-mix differences, not only delivery disparities

---

### Pipeline and infrastructure

| Addition | Purpose |
|---|---|
| `--stage nsa` | Build tract → NSA name crosswalk (year-independent) |
| `nsa_crosswalk.yml` | CI workflow for NSA spatial join |
| `regen_demographics.yml` | CI workflow for ACS demographic CSVs |
| Browser User-Agent on NSA fetch | ArcGIS Hub returns 403 to Python's default agent |

---

### Files added to `data/processed/`

| File | Contents |
|---|---|
| `tract_to_nsa.csv` | geoid → nsa_name crosswalk (200 tracts) |
| `tract_demographics.csv` | Updated — 9 ACS features (was 3) |
| `csa_demographics.csv` | Updated — population-weighted rollup of 9 features |
