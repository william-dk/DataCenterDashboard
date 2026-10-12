# Dashboard foundations and implementation boundary

Reference: `sources/drive/2026-10-11/dashboard-brief.md`.

## Intended product

Company selection should expose business economics, sourced financial history, operating KPIs, peer context, analyst assumptions, scenarios/valuation and the evidence testing a thesis.

Modules: market overview; company fundamentals; valuation; industry/bottlenecks; news/catalyst monitor; thesis tracker and source-grounded copilot. Current work establishes their shared data contracts, not a working application.

## Suggested architecture (not installed)

Python adapters → immutable raw source artifacts → normalization/validation → timestamped observations → operating/valuation models → Streamlit/Plotly UI and review queue. DuckDB for analytical MVP; PostgreSQL if concurrent writes/service needs justify it. FastAPI/React is a later option.

`schema.sql` is a portable SQLite-validated starter, not the final DuckDB implementation. Preserve semantics when migrating; add migrations and engine-specific types deliberately.

## Incremental delivery

1. P1: taxonomy, company master, KPI/source definitions and schema. Gate: workspace validator passes and candidate status is explicit.
2. P2a: one issuer SEC/IR history with period/units/revisions reconciled; no consensus masquerading as guidance.
3. P2b: six candidate pilot names after security verification; fundamentals screen and business-appropriate comps, then operating model and valuation scenarios.
4. P2c: expand verified Energy universe to 15–25 names after data coverage/quality checks.
5. P3: filings/events ingestion, extraction, materiality and analyst review queue; historical thesis versions.
6. P4: all seven layers with sector-specific models and many-to-many segment exposure.

## Refresh design

- Prices: provider-licensed daily/intraday schedule, exchange calendar and delay badge.
- Financial/KPI: on official release; retain filing amendment and restatements.
- Industry: release-driven, dataset-specific freshness expectations.
- News: periodic after authorized scheduler/provider setup; deduplicate at source/event level.
- Assumptions and conclusions: analyst-directed, versioned changes only.

No scheduled automation is created by these files. UI must display missing/stale data and source/period details rather than synthetic populated charts.

## Valuation routing

- Utilities: rate-base/regulatory economics and earnings; P/E cross-check.
- IPPs/operating nuclear: plant/contract cash flow, normalized EBITDA/FCF and merchant sensitivity.
- Turbine/electrical equipment/EPC: EBIT/EBITDA cross-checks, working capital, cycle-normalized margins and DCF.
- Renewables/storage: distinguish project ownership from equipment supply; project cash flow/NAV or supplier earnings.
- Pre-revenue SMR: probability-weighted project scenarios, runway, financing/dilution; no current earnings multiple.
- BTM: route by equipment/service/owned power contract; reliable delivered MW and lifecycle cost.

Apply FCFF/WACC or equity cash flow/cost of equity consistently; models must reject inconsistent periods, currencies and share counts.
