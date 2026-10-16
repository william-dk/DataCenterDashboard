# Data Center Dashboard

Research dashboard foundations for the EEIF AI infrastructure project.
The initial focus is Energy & Grid.

## Current status

This repository contains the initial taxonomy, company universe, KPI definitions,
dashboard specification, data contract, starter database schema, and a runnable
Streamlit research demo with EIA history, company snapshots and price charts.
Financial figures are secondary provider observations pending filing reconciliation.

## Repository structure

- `config/` — taxonomy, candidate companies, and KPI definitions
- `dashboard/` — dashboard schema and application code
- `app.py` — Streamlit dashboard entry point
- `company_financials.py` — saved company snapshots, incremental refresh and financials
- `local_store.py` — local versioned snapshots and persistent view preferences
- `market_history.py` — historical price retrieval and value-chain price indices
- `value_chain.py` — interactive value-chain map with hover details for all seven layers
- `requirements.txt` — minimal dashboard runtime dependency
- `docs/` — dashboard specification, data contract, [research workflow operating system](docs/RESEARCH_WORKFLOW_OS.md), and [PWR MVP sample](docs/PWR_MVP_SAMPLE.md)
- `config/pwr_mvp_fixture.json` — offline fixture used to validate the minimum research object model

## Data and secrets

Do not commit API keys, `.env` files, local databases, or raw/licensed datasets.
Check data-sharing permissions before adding research materials.

## Interactive value-chain map

Hover over any step to see its role, operating metrics, mapped Energy subsectors,
candidate companies, research question and valuation framework. All seven layers
have distinct stage descriptions. The detail expander provides persistent text
and a keyboard/touch-accessible selector. Hover is handled in the browser and
does not trigger a new financial or EIA request. Company links are framework
mapping proposals; issuer exposure remains subject to source verification.

## Run the demo

Create a virtual environment, install the requirements, and start Streamlit:

```text
python -m venv .venv
.venv\\Scripts\\activate
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

The app opens locally in a browser. Public provider snapshots and historical
prices are available; no licensed consensus or approved investment model is connected.

## Enable live electricity data

### Company financials

Saved company financials and price histories load from disk on entry, including
partial downloads. Opening the app and changing charts make no provider requests.
Use **Refresh all financials and prices** to check for new observations, or expand
an E01–E08 entry and click **Refresh this group**. Routine chart and widget
changes reuse the saved snapshot. Company, price-range, comparison and navigation
choices persist across sessions. Each completed financial/price component saves
immediately under ignored `data/saved/`, even if the other component fails or
the page closes before its background job completes. Failed updates retain the
last successful data and its original dates. Refreshing an overlapping company updates every group.
Refresh checks quote metadata for a new fiscal year before requesting annual
statements. An unchanged complete annual period is reused; incomplete statements
are retried. Yahoo's annual endpoint returns a bundle of periods when a new report
or missing field must be checked; field-level incremental requests are unavailable.
Yahoo Finance snapshots are fetched through yfinance without another API key.
Details include quote/retrieval timestamps, fiscal year end, sources and CSV export.
Quotes may be delayed; annual financials update on reporting, not intraday.
Secondary-source figures await primary-filing reconciliation.
Yahoo requests are serialized and spaced to reduce rate limits from shared cloud
IP addresses. If Yahoo returns HTTP 429, wait several minutes before retrying;
the app retains successful saved data and displays a short provider error detail.

The panel shows price, market cap, EV, trailing P/E, annual revenue/EBITDA,
CFO, cash CapEx, calculated FCF, FCF margin and FCF yield. FY EV/EBITDA
and FCF yield combine current market values with the labelled annual period.
Means and medians are equal weighted, split by business group, quote date and
fiscal year end, and require two observations. Missing facts are excluded;
negative FCF is retained. Values represent whole issuers, not subsector revenues.

### Historical price charts

The Energy overview compares E01–E08 baskets. Each expanded group also shows
individual company closing prices and a chart of its members against the group
index. Available ranges: 1M, 3M, 6M, YTD, 1Y, 3Y, 5Y and Max.

Individual USD charts use Yahoo Close. Basket charts use dividend/split-adjusted
Adj Close. Each stock starts at 100 on one common date; the basket is the
arithmetic mean of those rebased prices (initial equal-dollar weights,
buy-and-hold, no rebalancing). The cohort is fixed for the selected range;
missing constituent prices leave a gap. Coverage and failed symbols are shown.
Max comparisons start when the youngest included listing has data. Membership
uses today's sample universe, so the comparison has survivorship bias and is
not an investable historical benchmark. This is price performance, not a history
of EV/EBITDA, P/E or intrinsic value. Peer valuation snapshots remain separate.
After the initial maximum-history download, price updates start at the last saved
trading date, with one overlap date to reconcile split/dividend adjustment factors.
Prior snapshot versions are retained. A failed or unreconcilable update keeps the
previous history visible.

Install updated dependencies with `.venv\Scripts\python.exe -m pip install -r requirements.txt`.
Use the snapshots for personal research; review provider terms before shared deployment.

The Energy & Grid view can fetch hourly actual demand from the U.S. Energy
Information Administration's Form EIA-930 API. Register for an EIA API key and
provide it locally through either a Streamlit secrets file or an environment
variable. Never commit the key.

`.streamlit/secrets.toml`:

```toml
EIA_API_KEY = "your-key"
```

Or in PowerShell for the current session:

```powershell
$env:EIA_API_KEY = "your-key"
```

The electricity explorer restores saved observations, the last Grid area / Local
zone, Time window, timezone, custom dates and month/week/chart choices. The saved
date window stays fixed until Refresh advances it. It can display saved history
without an API key or connectivity, including interrupted downloads with explicit
coverage and missing-hour gaps. First use defaults to TVA, 30 days. Use
**Load missing history** / **Retry saved progress** for missing history, or
**Refresh** to advance the rolling end date and request missing hours only.
Neither startup nor selection changes trigger automatic source requests.
Area catalogs are saved locally; Settings → Update area list and Load local zones
explicitly retrieve catalog changes. Available internal zones include CISO, ERCO,
MISO, ISNE, NYIS, PJM, PNM and SWPP.
**All history** discovers
the series' earliest/latest API records using bounded monthly lookups. History is
downloaded one UTC month at a time, sorted locally instead of on EIA's server,
and saved in monthly disk caches. Transient timeouts trigger smaller requests. Completed months
survive interrupted downloads; **Retry saved progress** reuses them. Existing
valid hourly observations are reused without a TTL. Only missing/invalid hours
up to the current UTC hour are requested, grouped into contiguous intervals;
previous raw snapshots and per-row retrieval timestamps are preserved. This
missing-only policy does not automatically discover revisions to previously
reported valid hours. The first multi-year download can take a long time. Earlier pre-API files
are linked but are not imported by this adapter.

After loading, select a **Month** and optionally a **Week** directly. Select
**Summarize by → Hourly / Daily / Weekly / Monthly / Yearly** for chart granularity.
The Demand chart compares average and peak GW; the Energy chart shows recorded
GWh with partial periods distinguished by color. Four metrics summarize the
selected window: average load, peak load, recorded energy and hours reported.
Month/week focus changes and chart controls reuse loaded records.
Calendar timezone lives in Settings; weeks start Monday. EIA hourly
integrated MWh is divided by one hour to give average MW. Average demand, peak
demand and energy are separate measures. Full-period energy is shown only when
all calendar hours are valid, including daylight saving changes; observed partial
totals and completeness are visible. Missing hours are not filled with zero.

Each successful retrieval writes a uniquely named CSV and metadata JSON under
`data/eia/` (ignored by Git). These are retrieval snapshots, not a reconstruction
of historical publication vintages. API keys are excluded from metadata.
Source: [EIA electricity API documentation](https://www.eia.gov/opendata/documentation.php)
and [EIA-930 geography and history](https://www.eia.gov/electricity/930-content/about.html).

For an explicit one-off initial download / incremental top-up of the current 18
mapped companies and the saved EIA selection, run
`.venv\Scripts\python.exe scripts/seed_saved_data.py`. This is not a scheduled job.
Its local completion report is `data/saved/initial_download_report.json`.
