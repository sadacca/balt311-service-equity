# Baltimore 311 Data Catalog

**Last verified:** May 2026  
**Data span:** 2010 – present (16+ years)  
**Min year:** 2010 (via legacy Socrata combined feed)  
**Max year:** 2026 (live, daily updates)

---

## Platform History

Baltimore operates two overlapping open data platforms. Understanding the split is essential before writing any pipeline code.

| Era | Platform | Base URL | API Style |
|---|---|---|---|
| ~2010–2020 | Socrata (legacy) | `data.baltimorecity.gov` | SODA (`/resource/<id>.json`) |
| 2021–present | ArcGIS Hub | `data.baltimorecity.gov` (new UI) + `services1.arcgis.com/UWYHeuuJISiGmgXx` | ArcGIS FeatureServer REST (`/query`) |

The Socrata endpoints remain queryable but likely no longer receive live updates post-2020. The ArcGIS FeatureServer layers are the current authoritative source.

---

## Annual Vintage Index

### ArcGIS-era Annual Snapshots (2019–2026)

These are the primary sources for the equity analysis. Annual slices are static after year-end; the current-year layer updates daily.

| Year | Dataset Name | ArcGIS Item ID | FeatureServer Endpoint | Approx. Rows | Geometry | Notes |
|---|---|---|---|---|---|---|
| 2019 | 311 Customer Service Requests 2019 | (CSV-backed hosted layer) | `https://opendata.baltimorecity.gov/egis/rest/services/Hosted/311_Customer_Service_Requests_2019_csv/FeatureServer/0` | ~900K–1M | None (tabular) | Lat/lon as numeric fields; no Point geometry |
| 2020 | 311 Customer Service Requests 2020 | `d401bc43e7714a5893ad20cadc43f88a` | `https://opendata.baltimorecity.gov/egis/rest/services/hosted/311_customer_service_requests_2020_csv/featureserver/0` | ~900K–1M | None (tabular) | Lat/lon as numeric fields; no Point geometry |
| 2021–present | 311 CSR Spatialized – 2021 through Present | `d01d3c388f704a10bb5636c2a7fa6286` | `https://egis.baltimorecity.gov/egis/rest/services/GeoSpatialized_Tables/ServiceRequest_311/FeatureServer/0` | 4M+ (cumulative, growing) | Point (EPSG:2248) | Rolling combined layer; use for 2021–2022 data since no standalone annual files exist for those years |
| 2023 | 311 Customer Service Requests 2023 | `e002bef8e17d44788f0d01025a20127e` | `https://services1.arcgis.com/UWYHeuuJISiGmgXx/arcgis/rest/services/311_Customer_Service_Requests_2023/FeatureServer/0` | ~1,000,000 | Point | Static annual snapshot |
| 2024 | 311 Customer Service Requests 2024 | `68a1136acff444bba6c93e845dfc00e1` | `https://services1.arcgis.com/UWYHeuuJISiGmgXx/arcgis/rest/services/311_Customer_Service_Requests_2024/FeatureServer/0` | ~1,050,000 | Point | Static annual snapshot |
| 2025 | 311 Customer Service Requests 2025 | (via Hub slug) | `https://services1.arcgis.com/UWYHeuuJISiGmgXx/arcgis/rest/services/311_Customer_Service_Requests_2025/FeatureServer/0` | ~1,086,000 | Point | Static or near-complete |
| 2026 | 311 Customer Service Requests 2026 (current) | `de0ddaef68624e32a84e5197c5ac1829` | `https://services1.arcgis.com/UWYHeuuJISiGmgXx/arcgis/rest/services/311_Customer_Service_Requests_current/FeatureServer/0` | ~400K+ (YTD) | Point | Live; updates daily |

**Hub landing pages** follow the pattern:
`https://data.baltimorecity.gov/datasets/baltimore::311-customer-service-requests-<year>/about`

---

### Legacy Socrata Combined Feeds (2010–~2020)

Use these to access 2010–2018 data, which has no dedicated ArcGIS annual files.

| Dataset | Socrata ID | SODA Endpoint | Coverage | Notes |
|---|---|---|---|---|
| 311 Customer Service Requests (primary) | `9agw-sxsr` | `https://data.baltimorecity.gov/resource/9agw-sxsr.json` | ~2010–present | Main combined feed; query by `createddate` to isolate years |
| 311 Customer Service Requests (alt) | `ni4d-8w7k` | `https://data.baltimorecity.gov/resource/ni4d-8w7k.json` | ~2010–present | Older combined endpoint; may be a view of `9agw-sxsr` |
| 311 Customer Service Requests (SWP) | `mjhy-uwb9` | `https://data.baltimorecity.gov/resource/mjhy-uwb9.json` | Unknown | Filtered view; possibly Solid Waste Programs only |
| Baltimore Open-311 Requests | `sfqf-p98v` | `https://data.baltimorecity.gov/resource/sfqf-p98v.json` | Unknown | GeoReport v2 / Open-311 format; different schema |
| 311 Customer Service Requests 2011 | (ArcGIS Hub slug) | `https://data.baltimorecity.gov/datasets/311-customer-service-requests-2011-1` | Jan–Dec 2011 | Earliest confirmed standalone annual file |

---

### Coverage Map by Year

| Year | Source | Standalone File | Notes |
|---|---|---|---|
| 2010 | Socrata `9agw-sxsr` | No | Filter by `createddate` |
| 2011 | ArcGIS Hub (slug: `311-customer-service-requests-2011-1`) + Socrata | Yes | Earliest standalone |
| 2012–2018 | Socrata `9agw-sxsr` | No | Filter by `createddate`; no ArcGIS annual files found |
| 2019 | ArcGIS FeatureServer (CSV-backed) | Yes | Tabular; no geometry |
| 2020 | ArcGIS FeatureServer (CSV-backed) | Yes | Tabular; no geometry |
| 2021 | ArcGIS spatialized rolling layer (`d01d3c388f704a10bb5636c2a7fa6286`) | No standalone | Filter rolling layer by `CreatedDate` |
| 2022 | ArcGIS spatialized rolling layer | No standalone | Filter rolling layer by `CreatedDate` |
| 2023 | ArcGIS annual (`e002bef8e17d44788f0d01025a20127e`) | Yes | Point geometry |
| 2024 | ArcGIS annual (`68a1136acff444bba6c93e845dfc00e1`) | Yes | Point geometry |
| 2025 | ArcGIS annual (Hub slug) | Yes | Point geometry |
| 2026 | ArcGIS "current" live layer (`de0ddaef68624e32a84e5197c5ac1829`) | Live | Point geometry; daily updates |

---

## Schema Reference

### Core Fields — ArcGIS Era (2019–2026, PascalCase)

All ArcGIS-era vintages share this schema. Field casing is PascalCase. The 2019–2020 tabular layers omit the `Shape` geometry column.

| Field Name | Alias | Type | Key for Analysis |
|---|---|---|---|
| `OBJECTID` | OBJECTID | OID | ArcGIS internal; not stable across exports |
| `SRRecordID` | SR Record ID | String | Primary key; use for deduplication across files |
| `ServiceRequestNum` | Service Request Number | String | Human-readable request number |
| `SRType` | Service Request Type | String | Request category (e.g., "Pothole", "Bulk Trash") |
| `MethodReceived` | Method Received | String | Intake channel (phone, web, app, staff) — **use for resident-vs-staff ratio** |
| `CreatedDate` | Created Date | Date | Request submission timestamp |
| `SRStatus` | Status | String | Current status (Open, Closed, In Progress) |
| `StatusDate` | Status Date | Date | Date of last status change |
| `DueDate` | Due Date | Date | Target resolution date |
| `CloseDate` | Close Date | Date | Closure timestamp — **use to compute `days_to_close`** |
| `Agency` | Agency | String | Responsible city agency |
| `LastActivity` | Last Activity | String | Description of last action |
| `LastActivityDate` | Last Activity Date | Date | Date of last action |
| `Outcome` | Outcome | String | Resolution outcome description |
| `Address` | Address | String | Street address |
| `ZipCode` | Zip Code | String | 5-digit ZIP |
| `Neighborhood` | Neighborhood | String | Baltimore neighborhood name (NSA level) |
| `CouncilDistrict` | Council District | String | City council district number |
| `PoliceDistrict` | Police District | String | BPD district name |
| `PolicePost` | Police Post | String | BPD post number |
| `Latitude` | Latitude | Double | WGS84 decimal degrees |
| `Longitude` | Longitude | Double | WGS84 decimal degrees |
| `GeoLocation` | GeoLocation | String | Concatenated lat/lon string (Socrata compatibility) |
| `Shape` / `geometry` | Geometry | Point | Present in 2021+ spatialized layers; EPSG:2248 (MD State Plane) |

### Socrata-Era Fields (2010–2020, `9agw-sxsr`, lowercase)

Field names are lowercase/underscore. Mapping to ArcGIS equivalents:

| Socrata Field | ArcGIS Equivalent | Notes |
|---|---|---|
| `servicerequestnum` | `ServiceRequestNum` | |
| `type` | `SRType` | |
| `methodreceived` | `MethodReceived` | |
| `createddate` | `CreatedDate` | |
| `statusdate` | `StatusDate` | |
| `srstatus` | `SRStatus` | |
| `closedate` | `CloseDate` | |
| `streetaddress` | `Address` | |
| `zipcode` | `ZipCode` | |
| `neighborhood` | `Neighborhood` | |
| `policedistrict` | `PoliceDistrict` | |
| `councildistrict` | `CouncilDistrict` | |
| `latitude` | `Latitude` | |
| `longitude` | `Longitude` | |

`SRRecordID` does not have a confirmed Socrata equivalent — use `servicerequestnum` as the join/dedup key when combining Socrata and ArcGIS data.

---

## Key Schema Differences Across Eras

| Dimension | Socrata era (2010–2020) | ArcGIS tabular (2019–2020) | ArcGIS spatialized (2021+) |
|---|---|---|---|
| Field casing | lowercase | PascalCase | PascalCase |
| Geometry column | None | None | Point (EPSG:2248) |
| Lat/lon fields | `latitude`, `longitude` | `Latitude`, `Longitude` | `Latitude`, `Longitude` + `Shape` |
| Primary key field | `servicerequestnum` | `SRRecordID` | `SRRecordID` |
| API style | SODA | ArcGIS REST | ArcGIS REST |
| `DueDate` present | Unconfirmed | Yes | Yes |
| `Outcome` present | Unconfirmed | Yes | Yes |

**Overlap period (2019–2020):** Both Socrata and ArcGIS layers exist. Use the ArcGIS layers as the authoritative source for 2019–2020 to maintain schema consistency with 2021+.

---

## API Access Patterns

### ArcGIS FeatureServer Query

```
GET <endpoint>/query
  ?where=1=1
  &outFields=*
  &resultOffset=0
  &resultRecordCount=2000
  &f=json
```

Paginate using `resultOffset`. Max page size is typically 2,000 records; confirm per-layer limit via `<endpoint>?f=json` (`maxRecordCount` field).

Filter by year:
```
?where=CreatedDate >= '2024-01-01' AND CreatedDate < '2025-01-01'
&outFields=*&f=json
```

Get count only:
```
?where=1=1&returnCountOnly=true&f=json
```

Get earliest and latest records:
```
?where=1=1&outFields=CreatedDate&orderByFields=CreatedDate ASC&resultRecordCount=1&f=json
?where=1=1&outFields=CreatedDate&orderByFields=CreatedDate DESC&resultRecordCount=1&f=json
```

### Socrata SODA Query (legacy years 2010–2018)

```
GET https://data.baltimorecity.gov/resource/9agw-sxsr.json
  ?$where=createddate >= '2015-01-01T00:00:00' AND createddate < '2016-01-01T00:00:00'
  &$limit=50000
  &$offset=0
  &$order=createddate ASC
```

App token header (recommended to avoid throttling):
```
X-App-Token: <your-token>
```

---

## Ancillary / Summary Datasets

| Dataset | Socrata ID | URL | Use |
|---|---|---|---|
| 311 Request Totals by Type | `bud9-7vhc` | `https://data.baltimorecity.gov/resource/bud9-7vhc.json` | Sanity-check row counts by request type |
| Most Frequent 311 Request Types | `3d2f-s73p` | `https://data.baltimorecity.gov/resource/3d2f-s73p.json` | Quick type frequency reference |

---

## Known Gaps and Caveats

1. **2012–2018:** No dedicated annual ArcGIS files. Access via Socrata `9agw-sxsr` filtered by `createddate`. Schema will differ from 2019+ (lowercase fields, no `SRRecordID`).

2. **2021–2022:** No confirmed standalone annual ArcGIS items. Use the rolling spatialized layer (`d01d3c388f704a10bb5636c2a7fa6286`) and filter by `CreatedDate`. Because this layer is cumulative and growing, row counts for 2021–2022 are not fixed.

3. **Reopen status:** No `reopen_count` or status-history table has been identified. The `SRStatus`, `LastActivity`, and `Outcome` fields are current-state snapshots only. Reopen detection requires a heuristic proxy (see requirements §5).

4. **`MethodReceived` for staff vs. resident analysis:** This field exists in the schema but its value set has not been verified against the actual data. Confirm whether "staff", "inspector", or similar values appear before relying on it for the resident-to-staff ratio metric.

5. **Coordinate system:** The spatialized layers use EPSG:2248 (Maryland State Plane, NAD83, US feet) for the Point geometry. For spatial joins with Census/BNIA layers (typically EPSG:4326 or EPSG:26918), reproject before joining.

6. **OBJECTID instability:** `OBJECTID` is an ArcGIS-assigned row number; it is not stable across exports or service refreshes. Use `SRRecordID` as the durable primary key.

7. **Socrata retirement:** The legacy Socrata platform (`data.baltimorecity.gov` old UI) may be decommissioned. Treat Socrata as read-only archival access; do not depend on it for the 2019+ data that also exists in ArcGIS.

---

*Update this file when: a new annual vintage is published, Open Baltimore changes a FeatureServer endpoint, or schema inspection of downloaded data reveals field discrepancies from this catalog.*
