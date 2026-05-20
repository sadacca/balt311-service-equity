# Geographic and Demographic Reference Data Catalog

**Last verified:** May 2026  
**Purpose:** Boundary files, Census demographics, and crosswalks needed to align Baltimore 311 service request data (2010–2026) with neighborhood-level equity indicators.

---

## Vintage Alignment Strategy

The central design decision is which geographic vintages to use across the 16-year 311 span.

| 311 Data Period | Census Tract Vintage | CSA Crosswalk | TIGER File |
|---|---|---|---|
| 2010–2019 | 2010 Census tracts | `CSA2010.csv` (GEOID10 → CSA2010) | `tl_2010_24_tract10.zip` |
| 2020–2026 | 2020 Census tracts | `CSA2020.csv` (GEOID20 → CSA2010 name) | `tl_2020_24_tract.zip` |

**Key fact:** BNIA did not redraw CSA polygon boundaries after the 2020 Census. The same 55 CSA polygons work for the full 2010–2026 period. Only the tract-to-CSA crosswalk assignments changed slightly. Use `CSA2010` as the stable identifier throughout — the 2020 crosswalk maps 2020 tract GEOIDs back to 2010 CSA names for continuity.

**Recommended CRS for analysis:** Reproject all layers to EPSG:4326 (WGS84) for spatial joins and GeoJSON output, or EPSG:32618 (UTM Zone 18N, meters) for distance/area calculations.

---

## 1. Baltimore CSA (Community Statistical Area) Boundaries

**Publisher:** BNIA-JFI (Baltimore Neighborhood Indicators Alliance – Jacob France Institute)  
**Count:** 55 CSAs  
**Boundary stability:** Polygon geometry unchanged since 2010 redistricting. Safe to use one file for all vintages.  
**Native CRS:** EPSG:2248 (Maryland State Plane, NAD83, US feet); ArcGIS REST API auto-reprojects to EPSG:4326 when `f=pgeojson`.

### Endpoints

| Source | URL / ID |
|---|---|
| Open Baltimore Hub page | `https://data.baltimorecity.gov/datasets/9c96ae20e6cc41258015c2fd288716c4` |
| ArcGIS item ID | `9c96ae20e6cc41258015c2fd288716c4` |
| ArcGIS item (arcgis.com) | `https://www.arcgis.com/home/item.html?id=caf6c413e710451c9c4b80bdbcdf3eff` |
| BNIA Mapping Portal (alt) | `https://mapping-bniajfi.opendata.arcgis.com/` (search "Community Statistical Areas 2020") |
| BNIA ArcGIS item ID (alt) | `9be011c4ed2b481ab83e4f2cf2a04b78` |
| FeatureServer REST query | `https://services1.arcgis.com/mVFRs7NF4iFitgbY/ArcGIS/rest/services/Hhchpov/FeatureServer/0/query?where=1%3D1&outFields=*&returnGeometry=true&f=pgeojson` |

Download formats available from the Hub page: **Shapefile (.zip), GeoJSON, CSV (attributes only), KML**.

### Schema

| Field | Type | Description |
|---|---|---|
| `CSA2010` | String | CSA name — **primary join key across all datasets** |
| `Shape__Area` | Double | Polygon area (EPSG:2248 feet²) |
| `Shape__Len` | Double | Perimeter (EPSG:2248 feet) |
| geometry | Polygon | Multi-part polygon |

---

## 2. Baltimore NSA (Neighborhood Statistical Area) Boundaries

**Publisher:** Baltimore City GIS / Open Baltimore  
**Count:** 278 NSAs (sub-CSA neighborhood units)  
**Relationship:** Each NSA maps to exactly one CSA. NSAs are the finest named geographic unit in Baltimore's administrative geography.

### Endpoints

| Source | URL / ID |
|---|---|
| Open Baltimore Hub page | `https://data.baltimorecity.gov/datasets/8112521d3e284518b9fa497a188bfb45` |
| ArcGIS item ID | `8112521d3e284518b9fa497a188bfb45` |
| ArcGIS item (arcgis.com) | `https://www.arcgis.com/home/item.html?id=e7daa4c977d14e1b9e2fa4d7aff81e59` |
| FeatureServer endpoint | `https://opendata.baltimorecity.gov/egis/rest/services/Hosted/Neighborhoods/FeatureServer/0` |
| FeatureServer GeoJSON query | Append `/query?where=1%3D1&outFields=*&returnGeometry=true&f=pgeojson` |

Download formats: **Shapefile, GeoJSON, CSV, KML**.

### Notes
- Demographics attached to this layer are from the 2020 Census.
- NSA names align with the `Neighborhood` field in the 311 data — useful for a direct join without spatial operations, though coordinate-based spatial join is more reliable.

---

## 3. Census TIGER/Line Boundaries

**Publisher:** U.S. Census Bureau  
**Base FTP:** `https://www2.census.gov/geo/tiger/`  
**CRS:** All TIGER/Line shapefiles use **EPSG:4269** (NAD83 geographic, decimal degrees).  
**Access:** No login or API key required.

### Download URLs

#### Census Tracts — Maryland (FIPS: 24) / Baltimore City (FIPS: 24510)

| Vintage | URL | Use for |
|---|---|---|
| 2010 tracts | `https://www2.census.gov/geo/tiger/TIGER2010/TRACT/2010/tl_2010_24_tract10.zip` | 2010–2019 311 data |
| 2020 tracts | `https://www2.census.gov/geo/tiger/TIGER2020/TRACT/tl_2020_24_tract.zip` | 2020–2026 311 data |
| 2023 tracts | `https://www2.census.gov/geo/tiger/TIGER2023/TRACT/tl_2023_24_tract.zip` | ACS 2023 5-yr alignment |
| 2024 tracts | `https://www2.census.gov/geo/tiger/TIGER2024/TRACT/tl_2024_24_tract.zip` | Most current |

#### Block Groups — Maryland

| Vintage | URL |
|---|---|
| 2010 block groups | `https://www2.census.gov/geo/tiger/TIGER2010/BG/2010/tl_2010_24_bg10.zip` |
| 2020 block groups | `https://www2.census.gov/geo/tiger/TIGER2020/BG/tl_2020_24_bg.zip` |
| 2023 block groups | `https://www2.census.gov/geo/tiger/TIGER2023/BG/tl_2023_24_bg.zip` |
| 2024 block groups | `https://www2.census.gov/geo/tiger/TIGER2024/BG/tl_2024_24_bg.zip` |

Interactive selector (any year/layer): `https://www.census.gov/cgi-bin/geo/shapefiles/index.php`

#### TIGERweb REST API (geometry queries without downloading files)
`https://tigerweb.geo.census.gov/arcgis/rest/services/` — supports standard ArcGIS query parameters including GeoJSON output.

### Schema

All TIGER tract and block group shapefiles share this core schema. The 2010 vintage appends a `10` suffix to most field names (e.g., `GEOID10`, `TRACTCE10`); post-2010 vintages omit the suffix.

#### Census Tract Fields

| Field | Type | Width | Description |
|---|---|---|---|
| `STATEFP` | String | 2 | State FIPS (`24` = Maryland) |
| `COUNTYFP` | String | 3 | County FIPS (`510` = Baltimore City) |
| `TRACTCE` | String | 6 | Tract code, zero-padded |
| `GEOID` | String | 11 | `STATEFP` + `COUNTYFP` + `TRACTCE` — **primary join key** |
| `NAME` | String | 7 | Tract number as displayed |
| `NAMELSAD` | String | 20 | Full label, e.g. `Census Tract 10.01` |
| `MTFCC` | String | 5 | Feature class code (`G5020` for tracts) |
| `FUNCSTAT` | String | 1 | Functional status (`S` = statistical) |
| `ALAND` | Integer | 14 | Land area (m²) |
| `AWATER` | Integer | 14 | Water area (m²) |
| `INTPTLAT` | String | 11 | Internal point latitude |
| `INTPTLON` | String | 12 | Internal point longitude |

#### Block Group Additional Fields

| Field | Type | Width | Description |
|---|---|---|---|
| `BLKGRPCE` | String | 1 | Block group number (1–9) |
| `GEOID` | String | 12 | `STATEFP` + `COUNTYFP` + `TRACTCE` + `BLKGRPCE` |
| `NAMELSAD` | String | 13 | e.g. `Block Group 1` |

**Filtering to Baltimore City only:** After loading the Maryland state file, filter to `COUNTYFP == '510'`. Baltimore City and Baltimore County are separate jurisdictions; `510` is the city.

---

## 4. Census Planning Database (PDB)

**Publisher:** U.S. Census Bureau, Research and Methodology Directorate  
**Most recent vintage:** **2024 PDB** (released 2026), based on **2018–2022 ACS 5-year estimates** + 2020 Census operational data.  
**Geography:** Uses **2020 Census** tract and block group definitions.  
**Access:** No login required for CSV download. Free API key required for API access.

### Download URLs (direct, no login)

| File | URL | Size |
|---|---|---|
| Tract-level CSV | `https://www2.census.gov/adrm/PDB/2024/pdb2024tr.csv` | ~186 MB |
| Block group-level CSV | `https://www2.census.gov/adrm/PDB/2024/pdb2024bg.csv` | ~500 MB |
| Documentation PDF | `https://www2.census.gov/adrm/PDB/2024/2024_PDB_Documentation.pdf` | — |

**File dimensions:** Tract file: 85,397 rows × 531 columns. Block group file: 242,337 rows × 385 columns.

### API Endpoints

| Level | Endpoint |
|---|---|
| Tract | `https://api.census.gov/data/2024/pdb/tract` |
| Block group | `https://api.census.gov/data/2024/pdb/blockgroup` |
| Block group docs | `https://api.census.gov/data/2024/pdb/blockgroup.html` |
| Block group examples | `https://api.census.gov/data/2024/pdb/blockgroup/examples.html` |

**Example — block groups in Baltimore City (state=24, county=510):**
```
https://api.census.gov/data/2024/pdb/blockgroup
  ?get=State_name,County_name,Tot_Population_ACS_18_22,Med_HHD_Inc_ACS_18_22,pct_Prs_Blw_Pov_Lev_ACS_18_22
  &for=block%20group:*
  &in=state:24+county:510+tract:*
  &key=YOUR_KEY
```

### Key Variables (2024 PDB; suffix pattern: `_{ACS|CEN}_{start}_{end}`)

| Variable | Description |
|---|---|
| `GEOID` | 11-digit (tract) or 12-digit (BG) FIPS — direct join to TIGER `GEOID` |
| `State_name`, `County_name` | Geographic labels |
| `Tot_Population_ACS_18_22` | Total population |
| `NH_White_alone_ACS_18_22` | Non-Hispanic White population |
| `NH_Black_alone_ACS_18_22` | Non-Hispanic Black population |
| `Hispanic_ACS_18_22` | Hispanic/Latino population |
| `Med_HHD_Inc_ACS_18_22` | Median household income |
| `pct_Prs_Blw_Pov_Lev_ACS_18_22` | Percent persons below poverty level |
| `Renter_Occp_HU_ACS_18_22` | Count renter-occupied housing units |
| `Owner_Occp_HU_ACS_18_22` | Count owner-occupied housing units |
| `pct_Renter_Occp_HU_ACS_18_22` | Percent renter-occupied |
| `Mail_Return_Rate_CEN_2020` | 2020 Census mail return rate (hard-to-count proxy) |
| `Low_Response_Score` | Derived hard-to-count composite index |
| `College_ACS_18_22` | Population with bachelor's degree or higher |

**GEOID join alignment:** The PDB `GEOID` field is byte-for-byte identical to the TIGER shapefile `GEOID` field. No reformatting needed.

**Caveat on ACS lag:** The 2024 PDB uses 2018–2022 estimates. For alignment with 2024–2026 311 data, the ACS 2024 5-year API (2020–2024 estimates) is more current (see Section 5).

---

## 5. ACS 5-Year Estimates API

**Publisher:** U.S. Census Bureau  
**Most recent vintage:** **2024 ACS 5-year** (covers 2020–2024, released January 29, 2026)  
**API key:** Required (free). Register at `https://api.census.gov/data/key_signup.html`

### Endpoints by Vintage

| Vintage | Covers | Endpoint | Best paired with |
|---|---|---|---|
| ACS 2024 5-yr | 2020–2024 | `https://api.census.gov/data/2024/acs/acs5` | 2024–2026 311 data |
| ACS 2023 5-yr | 2019–2023 | `https://api.census.gov/data/2023/acs/acs5` | 2023 311 data |
| ACS 2019 5-yr | 2015–2019 | `https://api.census.gov/data/2019/acs/acs5` | 2019 311 data |
| ACS 2014 5-yr | 2010–2014 | `https://api.census.gov/data/2014/acs/acs5` | 2010–2014 311 data |

All ACS 5-year vintages from 2009 through 2024 are available via the API.

### Example Calls for Baltimore City

**All census tracts — income, poverty, population:**
```
https://api.census.gov/data/2024/acs/acs5
  ?get=NAME,B19013_001E,B17001_002E,B17001_001E,B01003_001E
  &for=tract:*
  &in=state:24+county:510
  &key=YOUR_KEY
```

**All block groups — race/ethnicity and housing tenure:**
```
https://api.census.gov/data/2024/acs/acs5
  ?get=NAME,B03002_001E,B03002_003E,B03002_004E,B03002_012E,B25003_001E,B25003_002E,B25003_003E
  &for=block%20group:*
  &in=state:24+county:510+tract:*
  &key=YOUR_KEY
```

### Key Variables

| Code | Table | Description |
|---|---|---|
| `B01003_001E` | B01003 | Total population |
| `B19013_001E` | B19013 | Median household income (past 12 months) |
| `B17001_001E` | B17001 | Total pop for poverty determination |
| `B17001_002E` | B17001 | Population below poverty level |
| `B03002_001E` | B03002 | Total population (race/ethnicity universe) |
| `B03002_003E` | B03002 | Non-Hispanic White alone |
| `B03002_004E` | B03002 | Non-Hispanic Black or African American alone |
| `B03002_006E` | B03002 | Non-Hispanic Asian alone |
| `B03002_012E` | B03002 | Hispanic or Latino (any race) |
| `B25003_001E` | B25003 | Total occupied housing units |
| `B25003_002E` | B25003 | Owner-occupied housing units |
| `B25003_003E` | B25003 | Renter-occupied housing units |

Each estimate variable `_E` has a corresponding margin of error variable `_M` (e.g., `B19013_001M`).

**Block group availability:** The tables above (B01003, B19013, B17001, B03002, B25003) are all supported at block group level. Not all ACS tables are available below the tract level.

---

## 6. BNIA Vital Signs Data

**Publisher:** BNIA-JFI  
**Most recent edition:** Vital Signs 23 (released 2024, covers data through ~2022)  
**Geography:** CSA level (55 CSAs). No tract or block group breakdown.  
**Access:** No login required.

### Download Access

| Source | URL |
|---|---|
| Excel downloads by chapter | `https://bniajfi.org/vital_signs/data_downloads/` |
| ArcGIS Hub portal | `https://vital-signs-bniajfi.hub.arcgis.com/` |

### Key Indicator Layers on ArcGIS Hub

Each indicator is a separate FeatureServer layer. Query via standard ArcGIS REST API. FeatureServers are hosted at `services1.arcgis.com/mVFRs7NF4iFitgbY/`.

| Indicator | ArcGIS Item ID |
|---|---|
| Median Household Income | `8613366cfbc7447a9efd9123604c65c1` |
| Percent HH Earning <$25K | `7fe6071691a146719b142042fc9760c9` |
| Percent Family HH Below Poverty | `74337e706ee94cd8a8b8272564497946` |
| Racial Diversity Index | `d588f7de06cf4815951e105bb8a390b1` |
| Total Population | `56d5b4e5480049e98315c2732aa48437` |

Hub page URL pattern: `https://vital-signs-bniajfi.hub.arcgis.com/datasets/<item_id>`

### Schema

| Field | Description |
|---|---|
| `CSA2010` | CSA name — join key |
| `<indicator><year>` | Indicator value per year, e.g. `mhhi10`, `mhhi11` … `mhhi22` |
| `Shape__Area`, `Shape__Len` | Geometry attributes |

Vital Signs covers 110+ indicators across: Census Demographics, Economy & Workforce, Housing & Community Development, Crime & Safety, Health, Education, Sustainability.

**Coverage note:** Vital Signs 24 had not been released as of May 2026. The most recent tabular data covers through approximately 2022–2023 depending on indicator source lag.

---

## 7. CSA–Census Tract Crosswalks

All crosswalk CSVs are maintained by BNIA in their public GitHub repository. No login required.

### Files

| File | URL | Use for |
|---|---|---|
| 2010 tracts → CSA2010 | `https://raw.githubusercontent.com/BNIA/VitalSigns/main/CSA2010.csv` | 2010–2019 311 data |
| 2020 tracts → CSA2010 names | `https://raw.githubusercontent.com/BNIA/VitalSigns/main/CSA2020.csv` | 2020–2026 311 data |
| CSA name bridge 2010 ↔ 2020 | `https://raw.githubusercontent.com/BNIA/VitalSigns/main/CSA2010_2020.csv` | Resolving name changes |
| NSAs (2020) → CSAs | `https://mapping-bniajfi.opendata.arcgis.com/datasets/neighborhoods-2020-to-community-statistical-areas` | NSA to CSA lookup |
| 2020 tracts → CSA2020 names (ArcGIS) | `https://arc-gis-hub-home-arcgishub.hub.arcgis.com/datasets/3f15e4aa31cf475f86d4dfd259f629bd_0/about` | Alternative post-2020 |

### Schema

**CSA2010.csv** — for 2010–2019 311 data:

| Field | Description |
|---|---|
| `TRACT10` | 6-digit tract code |
| `GEOID10` | 11-digit FIPS (join to TIGER 2010 `GEOID10`) |
| `CSA2010` | CSA name |

**CSA2020.csv** — for 2020+ 311 data:

| Field | Description |
|---|---|
| `TRACT20` | 6-digit tract code |
| `GEOID20` | 11-digit FIPS (join to TIGER 2020 `GEOID`) |
| `CSA2020` | CSA name (mapped back to 2010 naming convention for continuity) |

**CSA name changes (CSA2010_2020.csv):** Most names are identical. One confirmed rename: `Claremont/Armistead` (2010) → `Orchard Ridge/Armistead` (2020). Use `CSA2010` as the stable identifier throughout the 2010–2026 analysis.

### Recommended Join Strategy

1. **Spatial join (preferred for 311 data):** Point-in-polygon join of 311 request lat/lon coordinates to the CSA polygon layer. Appends `CSA2010` directly to each request record. No census tract required.

2. **Tabular crosswalk join:** If census tract GEOID is already on the record, join `GEOID10`/`GEOID20` → `CSA2010` using the GitHub CSVs above. Faster than a spatial join for large datasets.

3. **Cross-vintage consistency rule:** Always store `CSA2010` as the neighborhood identifier. Apply the 2010 crosswalk for pre-2020 data and the 2020-tracts-to-CSA2010 crosswalk for 2020+ data. This ensures CSA-level time series remain comparable 2010–2026.

---

## 8. Download Checklist

| Dataset | URL | Format | Auth |
|---|---|---|---|
| CSA boundary | `https://data.baltimorecity.gov/datasets/9c96ae20e6cc41258015c2fd288716c4` | SHP / GeoJSON | None |
| NSA boundary | `https://data.baltimorecity.gov/datasets/8112521d3e284518b9fa497a188bfb45` | SHP / GeoJSON | None |
| TIGER 2010 MD tracts | `https://www2.census.gov/geo/tiger/TIGER2010/TRACT/2010/tl_2010_24_tract10.zip` | SHP | None |
| TIGER 2010 MD block groups | `https://www2.census.gov/geo/tiger/TIGER2010/BG/2010/tl_2010_24_bg10.zip` | SHP | None |
| TIGER 2020 MD tracts | `https://www2.census.gov/geo/tiger/TIGER2020/TRACT/tl_2020_24_tract.zip` | SHP | None |
| TIGER 2020 MD block groups | `https://www2.census.gov/geo/tiger/TIGER2020/BG/tl_2020_24_bg.zip` | SHP | None |
| TIGER 2024 MD tracts | `https://www2.census.gov/geo/tiger/TIGER2024/TRACT/tl_2024_24_tract.zip` | SHP | None |
| TIGER 2024 MD block groups | `https://www2.census.gov/geo/tiger/TIGER2024/BG/tl_2024_24_bg.zip` | SHP | None |
| PDB 2024 tract CSV | `https://www2.census.gov/adrm/PDB/2024/pdb2024tr.csv` | CSV | None |
| PDB 2024 block group CSV | `https://www2.census.gov/adrm/PDB/2024/pdb2024bg.csv` | CSV | None |
| PDB 2024 documentation | `https://www2.census.gov/adrm/PDB/2024/2024_PDB_Documentation.pdf` | PDF | None |
| ACS 2024 5-yr API | `https://api.census.gov/data/2024/acs/acs5` | JSON API | Free key |
| ACS 2023 5-yr API | `https://api.census.gov/data/2023/acs/acs5` | JSON API | Free key |
| Census API key signup | `https://api.census.gov/data/key_signup.html` | — | Free |
| BNIA Vital Signs Excel | `https://bniajfi.org/vital_signs/data_downloads/` | Excel | None |
| BNIA Vital Signs ArcGIS Hub | `https://vital-signs-bniajfi.hub.arcgis.com/` | GeoJSON via REST | None |
| Crosswalk: 2010 tracts → CSA | `https://raw.githubusercontent.com/BNIA/VitalSigns/main/CSA2010.csv` | CSV | None |
| Crosswalk: 2020 tracts → CSA | `https://raw.githubusercontent.com/BNIA/VitalSigns/main/CSA2020.csv` | CSV | None |
| CSA name bridge 2010 ↔ 2020 | `https://raw.githubusercontent.com/BNIA/VitalSigns/main/CSA2010_2020.csv` | CSV | None |

---

## 9. Coordinate Reference System Notes

| Source | Native CRS | Notes |
|---|---|---|
| BNIA CSA / NSA boundaries | EPSG:2248 (MD State Plane, NAD83, US feet) | ArcGIS REST API reprojects to EPSG:4326 when `f=pgeojson` |
| TIGER/Line shapefiles | EPSG:4269 (NAD83 geographic, decimal degrees) | Reproject to EPSG:4326 or EPSG:32618 for analysis |
| 311 ArcGIS spatialized layer (2021+) | EPSG:2248 for Point geometry; lat/lon fields are EPSG:4326 | Use lat/lon numeric fields for spatial joins; ignore the `Shape` geometry unless doing native ArcGIS work |
| ACS / PDB | No geometry (tabular only) | Join to TIGER via `GEOID` |
| Recommended analysis CRS | EPSG:32618 (UTM Zone 18N, meters) | Consistent metric units; covers all of Baltimore |

---

*Update this file when: BNIA releases a new Vital Signs edition, Census releases a new TIGER/ACS vintage, or CSA boundary geometry is revised.*
