"""Streamlit demo for the EEIF AI infrastructure research dashboard.

Research framework with secondary company snapshots, historical prices and
official EIA electricity history. Company facts await filing reconciliation.
"""

from pathlib import Path
import json
import os

import pandas as pd
import streamlit as st
from company_financials import render_subsector, render_market_controls
from market_history import render_group_comparison
from electricity import render_electricity
from value_chain import render_value_chain
from local_store import remembered


ROOT = Path(__file__).parent


LAYER_DETAILS = {
    "L01": {
        "thesis": "Power availability and grid capacity determine when AI load becomes revenue-generating demand.",
        "chain": ["Fuel / generation", "Transmission", "Distribution", "Interconnection", "Energized load"],
        "drivers": ["Rate base / MW", "Backlog conversion", "Capacity factor", "Lead times", "FCF conversion"],
        "valuation": "Regulated DCF / plant DCF / EV-EBITDA / cycle-normalized FCF",
    },
    "L02": {
        "thesis": "Land, power, cooling and uptime are monetized through delivered capacity and contracted occupancy.",
        "chain": ["Site / land", "Power + cooling", "Shell / fit-out", "Colocation", "Hyperscale campus"],
        "drivers": ["MW capacity", "Utilization", "Rent / MW", "PUE", "Contract term"],
        "valuation": "EV / EBITDA, NAV, contracted-capacity DCF",
    },
    "L03": {
        "thesis": "Accelerator performance, supply and system integration determine compute availability and pricing power.",
        "chain": ["Chip design", "Wafer fabrication", "Packaging", "Systems", "Accelerated compute"],
        "drivers": ["Units / shipments", "ASP", "Performance / watt", "Foundry capacity", "Gross margin"],
        "valuation": "EV / EBITDA, P / E, DCF; cycle-aware margin sensitivity",
    },
    "L04": {
        "thesis": "Bandwidth, latency and switching density connect distributed compute into a usable AI cluster.",
        "chain": ["Optical components", "Cables / transceivers", "Switching", "Interconnect", "Cluster fabric"],
        "drivers": ["Port count", "Bandwidth", "ASP", "Attach rate", "Lead time"],
        "valuation": "EV / EBITDA, P / E, FCF DCF",
    },
    "L05": {
        "thesis": "Training data, checkpoints and inference workloads require scalable capacity, throughput and data durability.",
        "chain": ["Media / NAND", "Devices", "Arrays", "Data services", "AI data layer"],
        "drivers": ["Capacity shipped", "$/TB", "IOPS / throughput", "Utilization", "Service mix"],
        "valuation": "EV / EBITDA, P / E, normalized-cycle DCF",
    },
    "L06": {
        "thesis": "Cloud platforms convert infrastructure into metered compute, managed services and recurring workload revenue.",
        "chain": ["Infrastructure", "Virtualization", "Schedulers", "Managed services", "AI workloads"],
        "drivers": ["Compute consumption", "Revenue / GPU", "Utilization", "Net retention", "CapEx intensity"],
        "valuation": "EV / revenue, EV / EBITDA, FCF DCF",
    },
    "L07": {
        "thesis": "Data pipelines, governance and observability determine whether AI workloads can move from experiments to production.",
        "chain": ["Data sources", "Pipelines", "Storage / catalog", "Governance", "Production AI"],
        "drivers": ["Data volume", "Usage", "Seat / workload", "Retention", "Gross margin"],
        "valuation": "EV / revenue, rule of 40, FCF DCF",
    },
}

ENERGY_BREAKDOWN = [
    {
        "id": "E01",
        "name": "Regulated Utilities",
        "value_chain": "Generation / transmission → rate base → interconnection → customer load",
        "economics": "CapEx enters eligible rate base and earns an allowed return; funding and dilution drive per-share outcomes.",
        "kpis": "Rate base, allowed ROE, earned ROE, growth CapEx",
        "valuation": "Regulatory DCF; P/E and P/B cross-check",
        "companies": "SO · DUK · AEP · NEE",
    },
    {
        "id": "E02",
        "name": "IPPs & Merchant Generation",
        "value_chain": "Fuel / plant → dispatch → contracted power → merchant spread / capacity revenue",
        "economics": "Separate contracted generation, merchant generation and capacity revenues; fuel and power spreads drive cash flow.",
        "kpis": "Net MW, capacity factor, contracted share, maintenance CapEx",
        "valuation": "Plant / contract DCF; normalized EV/EBITDA and FCF",
        "companies": "CEG · VST · NRG",
    },
    {
        "id": "E03",
        "name": "Natural Gas Generation & Turbine Equipment",
        "value_chain": "Orders → backlog → manufacturing → delivery → service / plant operations",
        "economics": "Separate plant ownership from turbine manufacturing; execution and working capital determine conversion.",
        "kpis": "Backlog, book-to-bill, service mix, lead time",
        "valuation": "Equipment EV/EBITDA / P/E; generation cash-flow DCF",
        "companies": "GEV",
    },
    {
        "id": "E04",
        "name": "Nuclear Power & SMRs",
        "value_chain": "Operating fleet / components → licensing → construction → first power → contracted output",
        "economics": "Operating nuclear, component suppliers and pre-revenue developers have different availability, financing and execution risks.",
        "kpis": "Capacity factor, contracted share, first-power date, cash runway",
        "valuation": "Operating DCF; supplier earnings; probability-weighted development NAV",
        "companies": "CEG · VST · BWXT",
    },
    {
        "id": "E05",
        "name": "Renewable Energy & Battery Storage",
        "value_chain": "Resource / equipment → project development → PPA / merchant dispatch → storage spreads",
        "economics": "Separate developers, asset owners and manufacturers; PPA terms, generation profile and storage duration drive returns.",
        "kpis": "Net MW, storage MWh, capacity factor, contracted share",
        "valuation": "Project NAV / DCF / IRR; supplier earnings",
        "companies": "NEE · FLNC",
    },
    {
        "id": "E06",
        "name": "Grid Infrastructure, Transmission & EPC",
        "value_chain": "Awarded work → funded backlog → construction → energization → cash collection",
        "economics": "Backlog conversion and project margin are constrained by labor, execution, permitting and working capital.",
        "kpis": "Backlog, book-to-bill, EBITDA margin, CFO / FCF",
        "valuation": "Earnings multiples and cycle-aware FCF DCF",
        "companies": "PWR · MTZ",
    },
    {
        "id": "E07",
        "name": "Electrical Equipment, Transformers & Switchgear",
        "value_chain": "Components → factory capacity → orders / backlog → shipment → service",
        "economics": "Shipments and price/cost determine margins; transformer capacity and lead times determine scarcity value.",
        "kpis": "Backlog, book-to-bill, lead time, EBIT margin",
        "valuation": "EV/EBITDA or EBIT; ROIC / FCF DCF",
        "companies": "ETN · HUBB · POWL · GEV",
    },
    {
        "id": "E08",
        "name": "Behind-the-Meter, Distributed Generation & Microgrids",
        "value_chain": "Equipment → onsite generation → controls / storage → power-as-a-service",
        "economics": "Equipment and service economics differ from owned power contracts; reliability and time-to-power matter.",
        "kpis": "Net MW, availability, delivered cost/MWh, service mix",
        "valuation": "Equipment comps or project cash-flow DCF",
        "companies": "CAT · CMI · BE",
    },
]


@st.cache_data
def load_company_universe():
    with (ROOT / "config" / "company_universe.json").open(encoding="utf-8") as handle:
        return json.load(handle)


@st.cache_data
def load_taxonomy():
    with (ROOT / "config" / "taxonomy.json").open(encoding="utf-8") as handle:
        return json.load(handle)


def configured_eia_key():
    try:
        secret_key = st.secrets.get("EIA_API_KEY")
    except Exception:
        secret_key = None
    return secret_key or os.getenv("EIA_API_KEY")


st.set_page_config(page_title="AI Infrastructure Research Dashboard", page_icon="", layout="wide")

st.markdown(
    """
    <style>
    .block-container {max-width: 1440px; padding-top: 2rem; padding-bottom: 3rem;}
    .eyebrow {font-size: 0.72rem; letter-spacing: 0.12em; text-transform: uppercase; color: #687385;}
    .muted {color: #687385;}
    .status-chip {display: inline-block; border: 1px solid #d8dee8; border-radius: 999px; padding: 0.18rem 0.5rem; font-size: 0.72rem; color: #687385;}
    </style>
    """,
    unsafe_allow_html=True,
)

taxonomy = load_taxonomy()
company_universe = load_company_universe()
candidate_energy_names = len(company_universe.get("companies", []))
layers = taxonomy["layers"]
layer_ids = [layer["id"] for layer in layers]
layer_names = {layer["id"]: layer["name"] for layer in layers}

with st.sidebar:
    st.markdown('<div class="eyebrow">EEIF · AI Infrastructure Intelligence</div>', unsafe_allow_html=True)
    st.header("Research navigation")
    selected_id = remembered(
        'selectbox', "Infrastructure layer",
        layer_ids,
        key='infrastructure_layer',
        format_func=lambda value: f"{value} · {layer_names[value]}",
        index=0,
    )
    st.divider()
    st.caption("Phase 1 · framework + Energy pilot")
    st.caption("Research demo · public provider data")
    st.info("Saved financials, prices and electricity history load on entry. Use Refresh to request updates. Financials await primary-filing reconciliation.")
    st.divider()
    st.subheader("Live electricity data")
    eia_key = configured_eia_key()
    if eia_key:
        st.success("EIA API key detected")
    else:
        st.warning("Add EIA_API_KEY to .streamlit/secrets.toml or the environment to load live data.")
    st.caption('Choose an area, subregion and date range in the electricity history explorer.')

selected = next(layer for layer in layers if layer["id"] == selected_id)
detail = LAYER_DETAILS[selected_id]

st.markdown('<div class="eyebrow">EEIF · AI Infrastructure Intelligence</div>', unsafe_allow_html=True)
st.title("Research operating dashboard")
st.caption("Map the seven infrastructure layers, trace value-chain economics, and connect valuation to source-backed research.")

market_snapshot = render_market_controls([
    company['candidate_ticker'] for company in company_universe.get('companies', [])
    if company.get('candidate_ticker')
])

if selected_id == 'L01':
    st.divider()
    render_electricity(eia_key)

top_left, top_right = st.columns([2.2, 1], gap="medium")
with top_left:
    st.subheader(f"{selected['id']} · {selected['name']}")
    st.write(detail["thesis"])
with top_right:
    st.metric("Research status", "Framework seeded")
    st.caption("Company snapshots are secondary-source observations; segment exposure verification remains open.")

st.divider()
st.subheader("Value-chain map")
render_value_chain(selected_id, detail, ENERGY_BREAKDOWN)

st.divider()
coverage_left, drivers_right = st.columns([1.65, 1], gap="large")
with coverage_left:
    st.subheader("Research coverage")
    st.caption("Company provider snapshots and EIA history available; issuer-level verification pending")
    st.dataframe(
        [
            {"Research object": "Company / segment mapping", "Status": "Provisional", "Verification needed": "Primary filing review"},
            {"Research object": "Operating KPI coverage", "Status": "Framework", "Verification needed": "KPI dictionary + issuer disclosure"},
            {"Research object": "Current valuation", "Status": "Provider snapshot", "Verification needed": "Capital structure and period reconciliation"},
            {"Research object": "Source coverage", "Status": "Pending", "Verification needed": "SEC / IR / regulatory sources"},
        ],
        width="stretch",
        hide_index=True,
    )
with drivers_right:
    st.subheader("Operating drivers")
    st.caption("Layer-specific variables for future model inputs")
    st.write(" · ".join(detail["drivers"]))
    st.markdown("**Next research question**")
    st.write("Which disclosed operating driver converts layer demand into incremental earnings and free cash flow?")

if selected_id == "L01":
    st.divider()
    render_group_comparison(market_snapshot, ENERGY_BREAKDOWN)

    st.divider()
    st.subheader("Energy value-chain breakdown")
    st.caption("Eight Energy subsectors used for coverage mapping; companies remain candidate universe until security and segment evidence is verified.")
    st.metric("Candidate Energy names in registry", candidate_energy_names)
    for item in ENERGY_BREAKDOWN:
        with st.expander(f"{item['id']} · {item['name']} — {item['companies']}", on_change='rerun') as panel:
            if panel.open:
                render_subsector(item)

    st.subheader("Energy research support data")
    energy_support = pd.DataFrame(
        [
            {"Support field": "Demand anchor", "Current value": "Live EIA hourly demand", "Status": "Available when API key is configured"},
            {"Support field": "Grid constraint", "Current value": "Interconnection / transmission evidence", "Status": "Research queue"},
            {"Support field": "Project execution", "Current value": "Backlog, book-to-bill, lead time", "Status": "Issuer-level verification"},
            {"Support field": "Capital intensity", "Current value": "Growth vs. maintenance CapEx", "Status": "Filing extraction"},
            {"Support field": "Valuation snapshot", "Current value": "Price, EV, EBITDA / FCF", "Status": "Yahoo Finance; source reconciliation pending"},
            {"Support field": "Evidence quality", "Current value": "Primary / secondary / analyst assumption", "Status": "Tracked in source registry"},
        ]
    )
    st.dataframe(energy_support, width="stretch", hide_index=True, alt="Energy research support fields and implementation status")

st.divider()
st.subheader("Company research workspace")
st.caption('All loaded candidate companies · company-wide values · source and period metadata included')
if market_snapshot['rows']:
    st.dataframe(pd.DataFrame(market_snapshot['rows'].values()), width='stretch', hide_index=True,
                 alt='Saved company financial snapshots and source metadata')
else:
    st.info('Company updates are loading in the background.' if st.session_state.get('market_jobs') else 'No saved financial snapshots. Use Refresh all financials and prices to download data.')

st.divider()
st.subheader("Valuation route")
st.write(detail["valuation"])
st.caption("Source: project taxonomy and research workflow OS; quotes, annual financial snapshots and adjusted price history via Yahoo Finance. Financial statements and segment exposures await primary-source reconciliation; no licensed consensus is connected.")
