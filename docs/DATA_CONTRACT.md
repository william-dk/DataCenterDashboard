# Research and platform data contract v0.1

Stable IDs: L01–L07 layers, E01–E08 Energy subsectors, company_id distinct from security/ticker, metric_id, source_id, observation_id, assumption_id, thesis_id, event_id. Tickers can change; segment exposure can overlap.

## Observations

Store company/segment or industry region, metric, numeric/raw value, unit, currency, reporting period start/end and period type (instant/quarter/YTD/annual/TTM), published_at, available_at and retrieved_at, source ID/URL/locator, transformation and quality status. UTC timestamps are ISO 8601; user-facing planning dates use America/New_York.

Observation grain: entity + segment/region + metric + period + source + revision. Preserve each observation and prior version; retrieval is not publication. Point-in-time views exclude observations available after the analysis cutoff. Append-only storage is an ingestion rule; SQL alone does not enforce immutability.

Missing values are null plus missing_reason. Zero requires reported or derived zero evidence. Separate raw and normalized values; record multipliers, original currency and FX source/date. No automatic FX or unit conversion without explicit transformation.

## Comparability

Do not mix quarterly and YTD values. Derive Q4 or TTM only from consistent statements and disclose formula. Separate GAAP vs adjusted metrics by definition; preserve issuer adjustments. Align EV to dated price, shares, debt, cash, minority interests and leases as appropriate. Classify guidance, consensus and forecasts distinctly with as-of dates.

FCF_CFO = CFO − total cash CapEx (positive spend convention), reconciled to issuer presentation. FCFF = EBIT × (1−tax) + D&A − CapEx − ΔNWC; no interest deduction. Maintenance/growth split is unavailable unless disclosed or explicitly estimated; don't fabricate it from total CapEx. ROIC requires explicit NOPAT/invested-capital convention; WACC is an analyst assumption.

MW is power; MWh is energy; storage requires MW and MWh. Define capacity as gross/net/nameplate/available/contracted/energized/IT/facility. PUE and utilization are explicit separate assumptions. Queue, announced, awarded, funded, executable and commissioned capacity/backlog are distinct stages.

## Analyst-controlled objects

Assumptions: version, scenario, value/unit, rationale, evidence references, created_by/at, approval status and approved_by/at. Approved revisions append, never replace history.
Theses: original text, version, claims, evidence, model driver, consensus gap, catalysts, KPI gates, invalidation risks and approval status.
Events: source/time, company/subsector links, extracted claim, evidence locator, affected debate/driver, materiality explanation and review status. LLM extraction is a proposal until evidence checked.

## Ingestion acceptance

Verify security/entity mapping; required provenance; period/unit consistency; finite numeric values; duplicate/revision handling; source retrieval failures; missingness; freshness; licensing and point-in-time availability. Quarantine failures. No partial failures represented as success or unchanged current values. Store credentials outside repository; provider entitlement must be checked before storing/redistributing data.
