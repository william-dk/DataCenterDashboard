# Investment Research Workflow OS

Status: product design v0.1. Date: 2026-10-12, America/New_York.

This document defines the core product workflow for the AI Infrastructure research dashboard. The dashboard is a research operating system first and a visual dashboard second.

The workflow is grounded in the user's Notion notes, especially the `Putnam ER笔记` section in [研究方法](https://app.notion.com/p/39ca26d5202180c5aecacb8e6abfafb3), supplemented by [Fundamental Investment Research Workflow](https://app.notion.com/p/3dca26d520218061bd8ee656d8f72b9e) and [Evercore ER notes](https://app.notion.com/p/2b5a26d520218030bb36ccb8e7db10e1).

## Product north star

Build a source-traceable research workflow that turns new information into tested earnings assumptions, valuation changes and thesis updates.

The core chain is:

```text
Information intake
→ Industry / company selection: Data Center related Power and Infra Sector in this case
→ Business and earnings drivers
→ Projected earnings
→ Key debates
→ Evidence weighting
→ Original thesis
→ Catalysts and KPI gates
→ New information monitoring
→ Model / thesis review
→ Backtesting and learning
```

The system has three responsibilities:

- **Deterministic system:** facts, identity, storage, transformations, calculations, workflow state, versions, permissions and auditability.
- **LLM intelligence:** reading language, extracting candidates, connecting claims to evidence, identifying changes, challenging assumptions and drafting review material.
- **Analyst control:** approving evidence, weighting information, changing assumptions, approving theses, deciding action and sizing risk.

An LLM output is a proposal until an analyst approves it. It cannot silently write a fact, forecast, valuation or thesis conclusion into the approved research state.

## Canonical research objects

Every workflow stage should create or update explicit objects with stable IDs:

- `source`: document or dataset, URL, source type, license, publication date, availability date, retrieval date and content hash.
- `entity`: company, security, segment, subsector, industry or geography.
- `observation`: a sourced fact with metric, raw value, normalized value, unit, currency, period, locator, revision and quality status.
- `driver`: an operating variable such as capacity, market share, utilization, price, backlog conversion, margin or CapEx.
- `forecast`: versioned revenue, cost, EBITDA/EBIT, CapEx, FCF, ROIC and balance-sheet projection.
- `debate`: an investable question with competing views, evidence, affected drivers and resolution KPIs.
- `assumption`: analyst-controlled value, scenario, rationale, evidence references, status and version.
- `thesis`: original thesis, pillars, consensus gap, catalysts, KPI gates, invalidation risks and versions.
- `event`: new information mapped to company, debate, driver, materiality and review status.
- `review_proposal`: LLM or rule-generated suggested observation, event, assumption change or thesis impact awaiting review.
- `backtest`: historical cutoff, information set, forecast, thesis, outcome and error attribution.

## Workflow 1 — Information intake and research triage

### Objective

Capture new information in a reproducible way, populate fields that can be determined mechanically, and identify the language content that needs research review. The initial question is: **What arrived, what can be recorded automatically, and what deserves analyst attention?**

Workflow 1 has two intake lanes. They share the same source registry and review queue but use different processing rules.

### Lane A — Structured deterministic ingestion

Use this lane whenever the source already contains machine-readable facts or stable metadata. Examples include SEC submissions metadata, filing dates and forms, CIK/ticker mappings, XBRL company facts, reported units, statement periods, share counts, debt, cash, revenue and other standard tags.

The program should:

- fetch the permitted endpoint or filing artifact;
- validate HTTP response, schema, entity identifier, units and period context;
- map standard tags to the KPI dictionary;
- preserve the raw fact, normalized value, source, locator, period, revision and availability time;
- detect duplicates, amendments and restatements;
- calculate derived fields only through declared transformations;
- quarantine missing, conflicting or non-comparable facts.

These outputs can become approved `observation` records when they pass deterministic validation rules. LLM review is unnecessary for a standard XBRL revenue fact whose entity, unit and period are valid. An analyst may still review material or unusual mappings.

Example: 
SEC XBRL:
Revenue = 10,000,000 USD
Period = 2025-01-01 to 2025-12-31
Entity = PWR
Form = 10-K

### Lane B — Unstructured semantic triage

Use this lane for filing text, footnotes, MD&A, risk factors, earnings calls, presentations, regulatory language, project documents, news and analyst notes. The program can deterministically download, hash, parse, segment and index the document, but semantic interpretation is probabilistic.

The LLM may propose:

- candidate KPI values that are not exposed through standard tags;
- management guidance and changes in wording;
- contract, backlog, capacity, utilization and pricing disclosures;
- events such as orders, delays, permits, outages and financing;
- claims, debate links, driver links and evidence gaps;
- differences between the current and prior document.

These remain `review_proposal` objects until an analyst confirms the entity, period, definition, unit, locator and classification as fact, guidance, consensus, assumption or hypothesis.

The key distinction is:

```text
SEC XBRL fact with valid context
→ deterministic observation

Filing sentence about demand, pricing or execution
→ LLM candidate claim / event / KPI
→ analyst review
→ approved observation or research object
```

### Inputs

- SEC filings, earnings releases, investor presentations and transcripts.
- Company IR and regulatory/project documents.
- EIA, FERC, NERC, ISO/RTO, DOE/LBNL and state PUC data.
- Licensed price, consensus, news or industry data when entitlement permits.
- Analyst notes, conference notes and approved public meeting notes.

### Deterministic work

- Register the source before using its contents.
- Store URL, publication date, availability date, retrieval time, source type, license note and hash.
- Deduplicate documents and retain amended or restated versions.
- Associate the source with a company, security, segment, subsector, geography and period when known.
- Apply point-in-time availability and retrieval-failure status.
- Create a document queue ordered by source priority, materiality and freshness.

### LLM work

- Classify document type and likely research relevance.
- Identify sections containing demand, capacity, pricing, backlog, utilization, margin, CapEx, financing, regulation or risk information.
- Extract candidate claims and quotes with locators.
- Propose affected company, debate and driver links.
- Summarize what changed relative to the previous document.

### Analyst decisions

- Confirm the source is usable and licensed.
- Confirm entity and period mapping.
- Approve or reject candidate observations and claims.
- Decide whether the item is context, a review item or material enough to update the model.

### Outputs

- Registered `source`.
- Candidate `observation` records.
- Candidate `event` record.
- `review_proposal` with quote, locator, confidence and reason for review.

### Acceptance criteria

- Every accepted fact has a primary source or a documented reason for using secondary evidence.
- The source, period, unit and locator can be opened from the dashboard.
- A failed retrieval is visible as a failure and never treated as an unchanged successful refresh.

## Workflow 2 — AI infrastructure coverage mapping

### Objective

Map the businesses that capture economics across the data-center and AI infrastructure value chain. This is a focused coverage workflow, not a generic stock screener. Energy & Grid is the Phase 1 pilot, but the operating system must support the full seven-layer taxonomy.

The seven layers are:

```text
L01 Energy & Grid
L02 Data Center Facilities
L03 Compute & Semiconductors
L04 Networking & Optical Infrastructure
L05 Storage
L06 Cloud & Orchestration
L07 Data Infrastructure
```

Demand and economics flow across layers: downstream workloads create compute demand; compute drives facilities, networking and storage requirements; facilities require power and grid capacity; cloud and data infrastructure monetize workloads and feed demand back into the system. A company may map to multiple layers and Energy subsectors. It is never treated as a pure play merely because it appears in one layer.

// NEED REVISION
### Inputs

- AI workload, compute, data-center, power, networking and storage questions.
- Candidate companies already present in the master universe.
- Company segments, customers, geographies and business models.
- Capacity, utilization, pricing, orders, backlog, contracts, software usage and infrastructure evidence.
- Security identity, listing, liquidity and data availability.

### Deterministic work

- Maintain many-to-many company, segment, layer, Energy subsector and geography exposure.
- Verify security identity, ticker, exchange, currency and valid dates.
- Tag exposure as direct, adjacent, indirect, provisional or unsupported.
- Store revenue / earnings relevance, geographic relevance and evidence coverage.
- Calculate coverage, data quality and source availability indicators.
- Store selection, rejection and revisit reasons.
- Filter for investable bottleneck or monetization exposure, liquidity, business model and research fit.

### LLM work

- Summarize a company's role in one or more of the seven layers.
- Identify the specific bottleneck or monetization mechanism it may capture: power availability, facility capacity, compute performance, networking bandwidth, storage, cloud usage or data workflow.
- Explain cross-layer dependencies and where demand originates.
- Separate industry demand evidence from issuer-level revenue evidence.
- Identify likely competitors and the relevant economic profit pool.
- Convert broad AI infrastructure demand into a small number of investable debates.
- Recommend research priority based on bottleneck relevance, earnings materiality and evidence quality.

### Analyst decisions

- Approve the focused seven-layer coverage universe and primary company.
- Confirm whether the relevant segment is material enough to affect earnings.
- Confirm whether the evidence reaches the company level or remains industry context.
- Define the layer-specific bottleneck question and expected decision use.

### Outputs

- Seven-layer AI infrastructure value-chain map.
- Company / segment / security / layer mapping.
- Coverage matrix with bottleneck or monetization mechanism, revenue relevance, evidence quality and status.
- Small candidate debate list.
- Research brief for each selected company.

### Acceptance criteria

- No diversified ticker is labeled pure play without segment evidence.
- Each selected company is linked to a specific layer and bottleneck or monetization mechanism.
- Industry demand, MW, GPU shipments, cloud usage or workload statistics are not treated as issuer revenue evidence.
- Cross-layer dependencies are explicit; demand is not assumed to flow one-for-one into every upstream company.
- Selection can be reconstructed from the information available at the selection cutoff.
- Each selected company has a stated earnings question and at least one potential catalyst.

## Workflow 3 — Business model and earnings-driver mapping

### Objective

Explain how the company makes money before forecasting it.

### Inputs

- Primary filings and IR materials.
- Segment revenue, cost, capacity, contract, backlog and capital-allocation data.
- Industry demand and competitive evidence.

### Deterministic work

- Map financial statement lines to segments and metrics.
- Store KPI definitions, denominator, unit, period and issuer-specific reconciliation rules.
- Select a business-model template:
  - Market size × market share.
  - Capacity × utilization × price.
  - Rate base × allowed return.
  - Backlog × conversion rate × margin.
  - Project cash flow / NAV.
- Create driver dependencies and sign conventions.
- MORE STEPS TO BE DETERMINED

### LLM work

- Extract how management describes products, customers, contracts and pricing.
- Identify changes in KPI definitions and scope.
- Link qualitative statements to candidate drivers.
- Flag language that is vague, promotional or unsupported by disclosed numbers.
- Propose competitor and substitute relationships.

### Analyst decisions

- Confirm the correct business-model template.
- Approve driver definitions and boundaries.
- Decide what cannot be measured and preserve it as missing.

### Outputs

- Driver tree.
- Segment economics map.
- KPI dictionary additions.
- Evidence-backed business-model brief.

### Acceptance criteria

- Every material forecast line has an identified operating driver or an explicit analyst assumption.
- Capacity, utilization, price, backlog and CapEx definitions are not mixed.
- Missing KPIs are null with reasons.

## Workflow 4 — Historical financials and operating model
//THIS SECTION IS LARGELY DETERMINISTIC WITH CLEAR VALUATION FRAMEWORK

### Objective

Build a reconciled historical base and project earnings.

### Inputs

- SEC/XBRL facts and filing tables.
- Issuer-reported adjusted metrics.
- Segment and operating KPIs.
- Capital structure and dated market data when available.

### Deterministic work

- Normalize annual, quarterly, YTD, TTM and instant periods.
- Preserve GAAP, adjusted, reported, guidance, consensus and analyst forecast classifications.
- Reconcile revenue, EBIT/EBITDA, CFO, CapEx, debt, cash, shares and working capital.
- Apply restatement and amendment logic.
- Calculate forecast revenue, costs, EBITDA/EBIT, CapEx, FCF, leverage and ROIC.
- Separate maintenance and growth CapEx only when disclosed or explicitly estimated.
- Create bull/base/bear scenario versions.

### LLM work

- Extract non-standard KPIs and footnote explanations.
- Explain changes between periods and filings.
- Identify management language that may justify changing an assumption.
- Suggest which assumptions need a sensitivity or scenario.
- Draft an earnings bridge from the model outputs.

### Analyst decisions

- Approve historical reconciliation.
- Set analyst assumptions and evidence references.
- Approve scenario definitions and forecast version.

### Outputs

- Historical financial dataset.
- Operating model.
- Forecast version.
- Assumption register.
- Reconciliation and quality report.

### Acceptance criteria

- Independent calculation agrees with the model for key outputs.
- YTD is not mixed with quarterly data.
- Duplicate, restated or late-available facts are handled explicitly.
- Every forecast assumption has a source, rationale or clearly marked analyst judgment.

## Workflow 5 — Key debates and evidence weighting

### Objective

Turn industry information into a falsifiable question that can change projected earnings or valuation.

### Inputs

- Driver tree and forecast.
- Primary and secondary evidence.
- Management guidance and licensed consensus when available.
- Macro, geopolitical, regulatory and market context.

### Deterministic work

- Store debate question, competing views, affected companies and drivers.
- Link evidence and assumptions to each debate.
- Define measurable KPI gates and catalyst windows.
- Store evidence type and source quality.
- Calculate the gap between consensus, management and team forecast where data exists.

### LLM work

- Cluster documents into debate families.
- Summarize consensus and opposing arguments.
- Identify which evidence is being overweighted or underweighted.
- Generate bear case and alternative explanations.
- Detect claims that jump from industry demand directly to company revenue.
- Propose tests that could resolve the debate.

### Analyst decisions

- Select three to five material debates.
- Decide the information weighting and variant view.
- Approve KPI gates, catalyst timing and invalidation conditions.

### Outputs

- Debate map.
- Consensus-versus-team forecast bridge.
- Evidence-weighting memo.
- KPI gates and catalyst plan.

### Acceptance criteria

- Each debate follows: **Claim → Evidence → Earnings impact → Catalyst**.
- Each debate is falsifiable.
- No consensus figure is invented when unavailable.
- The largest forecast divergence is identified and explained.

## Workflow 6 — Original thesis and valuation

### Objective

Create an original, versioned investment view whose claims are connected to earnings and valuation.

### Inputs

- Approved forecast and assumptions.
- Debate map and evidence-weighting memo.
- Consensus and dated market data.
- Business-appropriate valuation methods.

### Deterministic work

- Run trading comps, DCF, reverse DCF, NAV, P/AFFO or other approved methods by business model.
- Calculate price target, implied upside/downside and sensitivities.
- Align price, shares, debt, cash, leases and minority interest to a common date.
- Store thesis version, model version and valuation version together.
- Record catalysts, KPI gates, risks and invalidation conditions.

### LLM work

- Draft thesis pillars from approved claims and evidence.
- Check that every pillar has a model driver and catalyst.
- Generate a structured bear case.
- Challenge whether valuation reflects the forecast and whether the variant view is already priced in.
- Draft investment memo and pitch outline using cited evidence.

### Analyst decisions

- Approve thesis wording, rating, target price and risk framing.
- Decide whether the thesis is investable, watchlist-only or rejected.
- Record what would prove or break the thesis.

### Outputs

- Approved thesis version.
- Valuation package.
- Target price and sensitivity.
- Catalyst calendar.
- Risk and invalidation register.

### Acceptance criteria

- Every thesis pillar maps to an earnings assumption.
- Every material assumption has supporting evidence.
- Valuation is business-model appropriate.
- The system can reproduce the exact model and evidence used at approval time.

## Workflow 7 — New information, catalyst and thesis monitoring

### Objective

Test the original thesis as new information arrives instead of rewriting it opportunistically.

### Inputs

- New filings, releases, transcripts, regulatory decisions, project announcements, price moves and consensus revisions.
- Existing thesis, debate, KPI gates and model version.

### Deterministic work

- Detect new sources and compare numeric values with prior versions.
- Trigger rules for guidance changes, KPI threshold breaks, estimate revisions and stale data.
- Assign event dates and point-in-time availability.
- Queue the event for review.

### LLM work

- Summarize what changed and what did not.
- Map the event to a debate and model driver.
- Explain possible revenue, margin, CapEx, FCF or valuation impact.
- Classify thesis impact as strengthen, weaken, unchanged or unresolved.
- Draft proposed assumption or thesis update with evidence.

### Analyst decisions

- Approve, reject or defer the proposed update.
- Change the model and create a new version when justified.
- Preserve the original thesis and record the reason for any revision.

### Outputs

- Event record.
- Review proposal.
- Model-change proposal or approved update.
- Thesis monitoring history.

### Acceptance criteria

- No event directly overwrites an approved thesis.
- Every update states which debate, driver and KPI it affects.
- Non-material information remains context and does not create artificial churn.

## Workflow 8 — Communication and research copilot
//OPTIONAL, MIGHT BE MORE WAYS TO DO THIS

### Objective

Make the analyst faster while keeping the research traceable.

### Inputs

- Approved sources, observations, forecasts, debates, thesis versions and events.
- Analyst question or requested output format.

### Deterministic work

- Retrieve only permitted and point-in-time-valid evidence.
- Apply company, period, source, status and version filters.
- Run calculations through the model engine.
- Attach source references and data cutoff to the response.

### LLM work

- Answer questions over the approved research graph.
- Generate weekly summary, earnings quick take, company update or debate brief.
- Prepare management and analyst questions.
- Explain model changes in plain language.
- Draft pitch narrative, Q&A and research meeting agenda.
- Identify unresolved evidence gaps and next-best research tasks.

### Analyst decisions

- Decide whether the output is for internal review, formal memo, client communication or presentation.
- Edit and approve any external or investment-facing language.

### Outputs

- Cited research brief.
- Model-change summary.
- Review queue and next actions.
- Draft communication artifact.

### Acceptance criteria

- Every material claim has a source or is labeled as an assumption/hypothesis.
- The answer states the cutoff and uncertainty.
- The copilot cannot access or expose data outside the user's entitlement.

## Workflow 9 — Fundamental backtesting and learning
//OPTIONAL

### Objective

Measure whether the research process was right for the right reasons, not merely whether the stock price moved.

### Inputs

- Historical cutoff snapshot.
- Original forecast, valuation and thesis.
- Actual filings, KPI outcomes, price and valuation changes.

### Deterministic work

- Reconstruct the information set available at the original cutoff.
- Compare forecast versus actual revenue, margin, CapEx, FCF, ROIC and valuation.
- Attribute error to data, period, driver, timing, model, weighting or thesis.
- Record realized catalyst timing and KPI gate outcomes.

### LLM work

- Explain why the forecast missed.
- Identify which evidence was ignored, overweighted or misunderstood.
- Compare the original thesis with the actual outcome.
- Suggest changes to the research checklist, KPI dictionary or debate framework.
- Draft a post-mortem that separates luck from process quality.

### Analyst decisions

- Approve the error attribution.
- Decide whether a methodology or data rule should change.
- Preserve the original forecast and thesis while creating a new methodology version.

### Outputs

- Backtest report.
- Forecast-error attribution.
- Thesis post-mortem.
- Updated research checklist or methodology proposal.

### Acceptance criteria

- The original information cutoff is preserved.
- Actual outcomes are not backfilled into the original decision state.
- Process quality and investment outcome are analyzed separately.

## MVP implementation order

### MVP-1: deterministic research loop

Implement source registry, company/security mapping, observations, one issuer's historical financials, driver tree, forecast, valuation, debate and thesis versioning. Use manual source intake first. The system should run without an LLM.

### MVP-2: LLM review queue

Add document classification, candidate KPI extraction, filing-change summary, event proposals, evidence-gap detection and cited research briefs. All LLM outputs remain proposed until analyst review.

### MVP-3: thesis monitoring

Add debate mapping, model-impact proposals, KPI gate alerts, catalyst review and versioned thesis updates.

### MVP-4: backtesting and learning

Add point-in-time snapshots, forecast-error attribution, thesis post-mortems and methodology improvements.

## Non-negotiable controls

- No invented financial values, consensus or company exposure.
- No direct LLM write access to approved observations, assumptions, valuations or theses.
- No mixing of quarterly, YTD, annual and TTM periods.
- No use of industry demand as a proxy for issuer revenue.
- No announced capacity treated as funded, executable or commissioned capacity.
- No external communication or scheduled provider job without authorization.
- Every approved conclusion remains reproducible from its source, cutoff, model and version history.
