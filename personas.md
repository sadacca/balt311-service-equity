# User Personas — Baltimore 311 Service Equity Dashboard

Five primary personas drive feature prioritization. For each: who they are, what question brings them to the dashboard, what they need to leave with, what currently serves them, and what gaps remain.

---

## Persona 1 — The Interested Citizen

**Profile**: Baltimore resident, non-technical, occasional visitor. May have submitted a 311 request and wondered what happened to it, or heard about service disparities in the news and wants to see for themselves. Uses the dashboard on a phone or tablet, not a desktop.

**Primary question**: "Is my neighborhood getting the same level of service as others? Are things getting better or worse?"

**Needs to leave with**: A simple, legible answer to whether their area is above or below average, and whether that gap is widening or closing over time. Doesn't need statistical rigor — needs confidence that the picture is honest.

**Currently served by**:
- Choropleth map with click-to-select tract or CSA
- Summary panel showing key metrics for their selected geography
- Color scale centered on citywide median (above/below average reads immediately)
- Year selector to compare across time

**Key gaps**:
- SRType names are city jargon (e.g. "SW-Dirty Alley") — no plain-language translation
- Equity scores (overlap score, "needs review") require interpretation most residents won't have
- No address search — resident must visually locate their neighborhood on the map
- No narrative summary: "Your area closes requests X days faster / slower than average"
- Mobile layout untested; map interaction may be difficult on small screens

**Roadmap relevance**: TD-3 (personas review) should validate whether plain-language overlays or a simplified "how is my neighborhood doing?" card is worth building. Low priority for Phase 4 work; could be a Phase 4b addition if the area summary panel is built out.

---

## Persona 2 — The Citizen Journalist

**Profile**: Reporter, blogger, or policy advocate doing research. Moderately data-literate — comfortable reading charts and understanding methodology, but not writing code. Looking for a story: an inequity, a trend, a comparison that the city hasn't publicized.

**Primary question**: "Is Baltimore improving? Which neighborhoods are consistently underserved? How does Baltimore compare to what other cities are doing? Is there a demonstrable equity problem here?"

**Needs to leave with**: Defensible, citable findings. Trend direction over multiple years. A comparison that contextualizes Baltimore's numbers (vs. prior years, vs. other cities). Confidence in the methodology — or at least a pointer to it.

**Currently served by**:
- Operations time series (2016–2025 trend visible)
- Equity distribution charts with overlap scores and plain-language labels
- Equity trend chart (year-over-year score trajectory)
- Methodology documentation in README (overlap score definition, equity subset definition)

**Key gaps**:
- No peer city comparison (Phase 5) — biggest gap for contextualization
- No data export or "download this chart's underlying data" function
- Regression evidence (Phase 4-6) would make equity claims more defensible than distribution comparison alone
- Overlap score thresholds (>0.7 = "not bad") are somewhat arbitrary — journalist may challenge them
- No way to see which specific SRTypes drive aggregate equity gaps

**Roadmap relevance**: Strongly validates Phase 5 (cross-municipal benchmarking) and Phase 4-6 (regression panel). Phase 4-1b (within-type equity scores) also useful — "SW-Dirty Alley is the most inequitably delivered service type in Baltimore" is a more specific and publishable claim than an aggregate score.

---

## Persona 3 — The Citywide Official

**Profile**: CDO, Mayor's Office staff, city director, or performance management analyst. Strategic view, not operational. Visits the dashboard to check overall health, prepare for briefings, or identify whether a specific concern (raised by a council member, press inquiry, or internal audit) is visible in the data.

**Primary question**: "Are there systemic problems with service identification or delivery across the city? Are we equitable? Are we trending in the right direction? Do I need to act, and if so, where?"

**Needs to leave with**: Confidence that the city's headline numbers are sound, a sense of trend direction, identification of any service types or geographies that are outliers, and a peer context for whether Baltimore's performance is strong or lagging.

**Currently served by**:
- Operations KPI bar with year-over-year deltas
- City-wide time series for each metric
- Equity overlap scores with plain-language labels ("needs review")
- Scope banner making the equity subset explicit (prevents misreading total volume as equity-subset volume)

**Key gaps**:
- No adjusted equity score (Phase 4-2/4-4) — the current aggregate score can be misleading if the city's type mix changed
- No peer city context (Phase 5) — "our closure rate is 87%" means nothing without a benchmark
- No executive summary view or exportable one-pager
- Equity trend direction is visible but not statistically tested — a declining score could be noise
- Phase 4-3 (SRType equity ranking) would let this persona quickly identify which types are driving aggregate disparity

**Roadmap relevance**: Validates Phase 4 (adjusted equity score is the most defensible number for a citywide briefing), Phase 5 (benchmarking is the "are we good?" answer), and TD-3 (use-case review should confirm whether a dedicated executive summary view is worth building).

---

## Persona 4 — The Local Official

**Profile**: City council member or district staff. Accountable to constituents in a specific geographic area (a council district, which spans several CSAs or dozens of tracts). Uses the dashboard to prepare for budget hearings, respond to constituent complaints, or challenge administration claims about service delivery.

**Primary question**: "How is my district being served relative to the rest of the city? Are my constituents getting fair service? Which service types or areas in my district are the biggest problems?"

**Needs to leave with**: A clear comparison of their district to the citywide baseline, identification of specific underperforming areas within their district, and evidence they can bring to a department head or budget negotiation.

**Currently served by**:
- Map click-to-select (can explore tracts within their district)
- Equity distributions (shows whether majority-Black or lower-income areas in the city get worse service)
- SRType performance table (can identify which types are slowest citywide)
- Geographic distribution map filtered by SRType

**Key gaps**:
- No district-level aggregation — council districts don't map cleanly to tracts or CSAs; user must manually click through their area
- Summary panel shows raw numbers but no "vs. citywide average" framing
- No "areas like mine" comparison — are the gaps in my district typical for similar neighborhoods elsewhere?
- Equity distributions are citywide; can't see equity within their district specifically
- Phase 4b (Area Analysis / peer comparison) is the most direct answer to "is my area getting what it deserves relative to similar areas?"

**Roadmap relevance**: Strongest validator of Phase 4b (area analysis). Also motivated by Phase 4-3 (within-type equity ranking) — a council member in a majority-Black district can ask "which specific service types are inequitably delivered in my area?"

---

## Persona 5 — The Department Operations Manager

**Profile**: Agency manager, department director, or operations analyst within a city department (e.g. DPW, Housing, DOT). Responsible for service delivery for a specific set of SRTypes. Uses the dashboard regularly — weekly or monthly — to track performance, identify backlogs, and make staffing or process decisions.

**Primary question**: "What's my biggest backlog? Which of my request types are hardest to close, and where? How am I trending year over year? What should I focus on to improve?"

**Needs to leave with**: SRType-level performance breakdown for their department, geographic distribution of their workload and problem areas, year-over-year trend to distinguish improvement from regression, and a clear view of where resolution is struggling.

**Currently served by**:
- Operations SRType table with category pills filtering to their department prefix
- Year-over-year bar charts for selected type (volume + median days to close)
- Geographic distribution map filtered to selected SRType
- Time series chart for citywide metric trends

**Key gaps**:
- No staffing or capacity normalization — can't distinguish "high volume and slow" from "understaffed"
- No "within my department, which areas are outliers?" — geographic map shows counts, not performance (closure rate, median days) by area for their type
- Phase 4b (Area Analysis) would surface: "tract X has similar request mix to tract Y but takes twice as long to close — what's different?"
- No drill-down to individual request records — can identify a problem geography but can't investigate what's in it
- Phase 4-1b (within-type equity scoring) could reveal whether their service type has a geographic equity problem they're responsible for addressing
- Seasonal patterns (Phase 6) would directly inform staffing planning

**Roadmap relevance**: Heaviest user of Phase 4b (area analysis is a direct operational tool) and Phase 6 (seasonality informs staffing). Phase 4-3 (equity ranking) is relevant but may land as a compliance/oversight tool rather than a day-to-day operational one for this persona.

---

## Summary Matrix

| Feature / Phase | Citizen | Journalist | Citywide Official | Council Member | Ops Manager |
|---|---|---|---|---|---|
| Map + click-to-select | ★★★ | ★★ | ★★ | ★★★ | ★★ |
| Operations KPI + time series | ★ | ★★★ | ★★★ | ★★ | ★★★ |
| SRType table + detail charts | ★ | ★★ | ★★ | ★★ | ★★★ |
| Equity distributions + score | ★ | ★★★ | ★★★ | ★★ | ★ |
| Equity trend chart | ★ | ★★★ | ★★★ | ★★ | ★ |
| **Phase 4**: Within-type equity scoring | ★ | ★★★ | ★★★ | ★★ | ★★ |
| **Phase 4b**: Area analysis / peer comparison | ★★ | ★★ | ★★ | ★★★ | ★★★ |
| **Phase 5**: Cross-municipal benchmarking | ★ | ★★★ | ★★★ | ★★ | ★★ |
| **Phase 6**: Seasonality tab | ★ | ★ | ★★ | ★ | ★★★ |

★★★ = primary use case &nbsp;&nbsp; ★★ = useful &nbsp;&nbsp; ★ = marginal

---

## Key Takeaways for Roadmap

1. **Phase 4b (Area Analysis) is the highest-value next step for the two most operationally engaged personas** — council members and ops managers. Both need a "how does my area compare to similar areas" answer that the current dashboard can't give.

2. **Phase 5 (cross-municipal) unlocks the journalist and citywide official use cases** — both need external context to make "Baltimore is doing well / poorly" a defensible claim rather than a raw number.

3. **Phase 4 equity scoring (P4-1b through P4-4) serves the journalist and citywide official** but is less compelling for the ops manager or citizen unless it's translated into plain language.

4. **The citizen persona is underserved by the current dashboard** — the biggest gaps (address search, plain-language summaries, mobile layout) are outside the current roadmap. Worth a dedicated accessibility pass before any public launch or press coverage.

5. **Phase 6 (seasonality) is uniquely valuable to the ops manager** and is the only phase that speaks directly to staffing and process planning.

---

*Created: May 2026. Revisit after TD-3 validation with actual stakeholder interviews.*
