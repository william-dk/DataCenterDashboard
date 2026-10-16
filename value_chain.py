"""Client-side hover details for the existing seven-layer value-chain framework."""
import textwrap

import altair as alt
import pandas as pd
import streamlit as st
from local_store import remembered


# Product/research framework descriptions, not verified issuer observations.
STAGE_DETAILS = {
    'L01': [
        ('Produce dispatchable or intermittent electricity for the grid.', 'Net MW; capacity factor; contracted share; fuel spread', 'How much dependable capacity can meet incremental load?', ['E02', 'E03', 'E04', 'E05']),
        ('Move bulk electricity between generation and regional load centers.', 'Funded backlog; transmission investment; project completion', 'Which constraints delay power delivery and project cash collection?', ['E06']),
        ('Deliver electricity through local networks, transformers and switchgear.', 'Rate base; equipment lead time; price/cost; utilization', 'Does local delivery capacity translate into durable earned returns?', ['E01', 'E07']),
        ('Connect a new load or generator through engineering, approvals and construction.', 'Queue status; funded awards; energization date', 'What separates a request from an executable and funded connection?', ['E01', 'E06', 'E07']),
        ('Turn connected supply into usable power at the customer site.', 'Delivered MW; uptime; delivered cost; service mix', 'When does available power become customer usage and issuer cash flow?', ['E01', 'E08']),
    ],
    'L02': [
        ('Secure a site with usable land and access to infrastructure.', 'Site control; permits; secured power', 'Is the site ready to develop, or still dependent on approvals?'),
        ('Install electrical and thermal systems required to operate the facility.', 'Delivered power; PUE; cooling capacity', 'Which system limits the usable capacity of the facility?'),
        ('Construct and fit out the building for customer equipment.', 'Construction cost/MW; schedule; ready-for-service MW', 'When can built space become revenue-producing capacity?'),
        ('Provide contracted space, power and operating services to customers.', 'Occupied MW; rent/MW; contract term; renewal', 'Can occupancy and pricing cover incremental capital costs?'),
        ('Deliver large campuses with phased capacity for major workloads.', 'Committed MW; phased delivery; customer concentration', 'How much announced campus capacity is funded and contracted?'),
    ],
    'L03': [
        ('Design accelerators and supporting chip architectures.', 'Design wins; performance/watt; product mix', 'Does differentiated performance sustain pricing and margins?'),
        ('Manufacture chips on wafer fabrication processes.', 'Wafer capacity; yield; node mix; utilization', 'Can qualified capacity expand without eroding returns?'),
        ('Integrate dies, memory and interconnects into usable packages.', 'Qualified capacity; yield; lead time', 'Which packaging bottleneck limits system shipments?'),
        ('Assemble accelerators, memory and boards into servers or racks.', 'System shipments; backlog; ASP; gross margin', 'How much value does the system integrator retain?'),
        ('Deploy usable compute resources for AI workloads.', 'Available compute; utilization; cost/workload', 'Will deployed capacity earn adequate cash returns?'),
    ],
    'L04': [
        ('Supply optical devices that transmit and receive signals.', 'Shipment mix; yield; bandwidth generation', 'Which components capture value as bandwidth increases?'),
        ('Connect equipment through cables and optical modules.', 'Units; ASP; attach rate; qualification', 'Does higher port density translate into higher supplier revenue?'),
        ('Route traffic among servers and cluster components.', 'Port shipments; switching capacity; gross margin', 'How does the technology mix affect competitive economics?'),
        ('Join systems and facilities through network links.', 'Link capacity; latency; deployment cost', 'Where does the network become a deployment bottleneck?'),
        ('Coordinate the network that makes a compute cluster usable.', 'Throughput; congestion; utilization', 'Does better networking improve productive compute utilization?'),
    ],
    'L05': [
        ('Manufacture the physical media that holds data.', 'Bits shipped; capacity; price/TB', 'Can supply discipline sustain pricing through the cycle?'),
        ('Package media into drives and storage devices.', 'Units; capacity/device; throughput', 'Which workload requirements support product differentiation?'),
        ('Combine devices into managed storage systems.', 'System sales; utilization; gross margin', 'How much margin is earned above the underlying media?'),
        ('Manage storage access, durability and data movement.', 'Usage; recurring mix; retention', 'Does the service create recurring economics beyond hardware?'),
        ('Serve training data, checkpoints and inference workloads.', 'Data volume; throughput; cost/workload', 'Which storage constraint affects AI workload performance?'),
    ],
    'L06': [
        ('Provide the physical resources that cloud workloads consume.', 'Available capacity; CapEx; useful life', 'Can revenue cover infrastructure investment over its life?'),
        ('Expose physical resources as allocatable services.', 'Utilization; service availability; overhead', 'How efficiently can resources be shared across customers?'),
        ('Schedule jobs and allocate scarce compute resources.', 'Queue time; utilization; workload mix', 'Does better scheduling improve monetization of installed capacity?'),
        ('Offer managed compute and supporting platform capabilities.', 'Consumption; retention; gross margin', 'How much value is captured by managed services?'),
        ('Run customer applications and AI jobs on cloud resources.', 'Workload growth; usage revenue; cost/job', 'Is demand translating into profitable recurring consumption?'),
    ],
    'L07': [
        ('Collect the operational data that applications and models require.', 'Data availability; quality; refresh latency', 'Is the required data usable, current and accessible?'),
        ('Move and transform data between systems.', 'Pipeline volume; reliability; processing cost', 'Where do data movement and transformation create friction?'),
        ('Store data and maintain discoverable metadata.', 'Stored volume; usage; retention', 'Does the platform become essential to customer workflows?'),
        ('Control data access, quality, lineage and permitted use.', 'Policy coverage; quality incidents; adoption', 'Can governance requirements support durable platform adoption?'),
        ('Deliver data to production models and applications.', 'Production workloads; usage; gross margin', 'Does experimental usage convert into sustained production revenue?'),
    ],
}


def map_nodes(layer_id, detail, energy_subsectors):
    lookup = {row['id']: row for row in energy_subsectors}
    nodes = []
    for index, (stage, spec) in enumerate(zip(detail['chain'], STAGE_DETAILS[layer_id], strict=True)):
        role, kpis, question = spec[:3]
        mapped = spec[3] if len(spec) == 4 else []
        companies = sorted({ticker.strip() for code in mapped for ticker in lookup[code]['companies'].split('·')})
        nodes.append({
            'Stage': stage, 'Role': role, 'Key metrics': kpis, 'Research question': question,
            'Sample companies': ', '.join(companies) if companies else 'Issuer mapping not yet populated',
            'Mapped subsectors': ', '.join(mapped) if mapped else 'Outside the Energy pilot',
            'Valuation route': detail['valuation'],
            'label': '\n'.join(textwrap.wrap(stage, width=19, break_long_words=False)),
            'number': f'{index+1:02}', 'left': index, 'right': index+.88, 'center': index+.44,
        })
    return nodes


def hover_map(nodes):
    data = pd.DataFrame(nodes)
    count = len(nodes)
    x_scale = alt.Scale(domain=[-.02, count-.1])
    x = lambda field: alt.X(f'{field}:Q', scale=x_scale, axis=None)
    hover = alt.selection_point(name='stage_hover', fields=['Stage'], on='pointerover',
                                clear='pointerout', empty=False)
    tooltip = [alt.Tooltip(f'{field}:N') for field in
               ['Stage', 'Role', 'Key metrics', 'Sample companies', 'Mapped subsectors', 'Research question', 'Valuation route']]
    base = alt.Chart(data).encode(tooltip=tooltip)
    boxes = base.mark_rect(cornerRadius=8, cursor='help').encode(
        x=x('left'), x2='right:Q', y=alt.value(15), y2=alt.value(130),
        color=alt.condition(hover, alt.value('#dce8ff'), alt.value('#edf2f8')),
        stroke=alt.condition(hover, alt.value('#4169b8'), alt.value('#cad5e3')),
        strokeWidth=alt.condition(hover, alt.value(2), alt.value(1)),
    ).add_params(hover)
    numbers = base.mark_text(fontSize=11, color='#546479', cursor='help').encode(
        x=x('center'), y=alt.value(36), text='number:N')
    titles = base.mark_text(fontSize=13, fontWeight=600, lineBreak='\n', color='#20334d', cursor='help').encode(
        x=x('center'), y=alt.value(68), text='label:N')
    arrows = alt.Chart(pd.DataFrame({'position':[index+.94 for index in range(count-1)]})).mark_text(
        text='→', color='#6a7e99', fontSize=16).encode(x=x('position'), y=alt.value(73))
    return alt.layer(boxes, numbers, titles, arrows).properties(height=145).configure_view(stroke=None)


def render_value_chain(layer_id, detail, energy_subsectors):
    nodes = map_nodes(layer_id, detail, energy_subsectors)
    st.caption('Hover over a step for its role, key metrics, sample companies and research question.')
    st.altair_chart(hover_map(nodes), width='stretch', theme=None,
                    key='value_chain_' + layer_id,
                    alt='Interactive value-chain diagram. Hover over any step to inspect research details.')
    st.caption('Source: project research framework. Arrows indicate economic dependencies; company links are candidate mappings, not verified segment exposure.')
    with st.expander('Keep step details open / keyboard and touch access'):
        stage = remembered('selectbox', 'Value-chain step', [node['Stage'] for node in nodes], key='step_' + layer_id)
        node = next(node for node in nodes if node['Stage'] == stage)
        st.markdown(f"**{node['Stage']}** — {node['Role']}")
        st.markdown(f"**Key metrics:** {node['Key metrics']}")
        st.markdown(f"**Sample companies:** {node['Sample companies']}")
        st.markdown(f"**Research question:** {node['Research question']}")
        st.markdown(f"**Valuation route:** {node['Valuation route']}")
