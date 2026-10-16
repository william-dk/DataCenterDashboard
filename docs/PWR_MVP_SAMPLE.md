# PWR MVP Sample

Status: illustrative fixture, pending primary-source verification.

This sample tests the smallest useful research loop before building adapters or a dashboard UI. It is deliberately conservative: unresolved identity, segment, security and financial values remain `null` with an explicit reason. The fixture is not a financial model and does not represent an approved investment view.

The sample is in [`config/pwr_mvp_fixture.json`](../config/pwr_mvp_fixture.json).

## What the sample proves

1. **Taxonomy**: PWR can be associated provisionally with `L01 Energy & Grid` and `E06 Grid Infrastructure, Transmission & EPC` without treating it as a pure play.
2. **Company / security / segment**: identity fields are separate from the exposure hypothesis; listing and segment details remain pending until verified.
3. **Exposure**: the mapping records layer, subsector, economic role, evidence source and review status.
4. **Source**: a source record exists before facts are used. Missing URL and dates are visible rather than invented.
5. **Observation / research queue**: structured facts and language-derived questions use separate statuses. A revenue fact can later be approved through deterministic extraction; backlog language remains a review proposal until the definition and locator are checked.

## PWR walkthrough across the workflows

### Workflow 1: information intake

- Register the issuer filing or IR document as a `source`.
- Deterministically extract standard financial facts such as revenue, period, unit and filing availability.
- Create an `observation` only when entity, period, unit and locator checks pass.
- Send backlog, contract, project and demand language to the research queue as proposed claims or KPI candidates.
- Analyst confirms whether each item is fact, management guidance, calculation or hypothesis.

### Workflow 2: coverage mapping

- Verify the issuer-reported segment before finalizing exposure.
- Map the relevant segment to one or more AI-infrastructure layers and Energy subsectors.
- Record direct, adjacent, indirect or provisional exposure and the economic bottleneck it may capture.
- Record the earnings question: which disclosed segment economics could convert grid/data-center demand into revenue, margin, cash flow or returns?

### Minimal acceptance test

The fixture passes the product-design test if a reviewer can answer, without opening another undocumented file:

- What entity is being researched?
- Which layer and subsector are currently proposed?
- What evidence supports the mapping?
- Which values are approved facts versus unresolved proposals?
- What is the next analyst action?

The next implementation step is to replace the pending source with one verified PWR filing, populate one annual observation and one reviewed operating KPI, then compare the resulting records with the existing SQL schema.
