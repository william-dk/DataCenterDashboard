"""Secondary-source snapshots for an on-demand, personal research demo."""
import math
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import pandas as pd
import streamlit as st
from market_history import fetch_prices, chart_price_history, yahoo_session
from local_store import latest_snapshot, save_snapshot, remembered


def number(value):
    try:
        result = float(value)
        return result if math.isfinite(result) else None
    except (TypeError, ValueError):
        return None


def positive(value):
    value = number(value)
    return value if value is not None and value > 0 else None


def fetch_company(ticker, previous=None):
    import yfinance as yf

    stock = yf.Ticker(ticker, session=yahoo_session())
    info = stock.get_info()
    if info.get('quoteType') != 'EQUITY' or not info.get('regularMarketTime'):
        raise ValueError('No dated equity quote returned by provider.')
    if info.get('currency') != 'USD':
        raise ValueError('Non-USD quote excluded; FX normalization is not configured.')
    quote_time = datetime.fromtimestamp(info['regularMarketTime'], timezone.utc)
    price = positive(info.get('regularMarketPrice'))
    eps = positive(info.get('trailingEps'))
    row = {
        'Ticker': ticker, 'Company': info.get('longName', ticker),
        'Price ($)': price, 'Market cap ($bn)': number(info.get('marketCap')),
        'Enterprise value ($bn)': number(info.get('enterpriseValue')),
        'P/E (TTM, x)': price / eps if price and eps else None,
        'Revenue (FY, $bn)': None, 'CFO (FY, $bn)': None,
        'EBITDA (FY, $bn)': None, 'EV / EBITDA (FY, x)': None,
        'FCF yield (FY, %)': None,
        'CapEx (FY, $bn)': None, 'FCF (FY, $bn)': None,
        'FCF margin (FY, %)': None, 'Fiscal year end': None,
        'Quote time (UTC)': quote_time.isoformat(timespec='seconds'),
        'Retrieved (UTC)': datetime.now(timezone.utc).isoformat(timespec='seconds'),
        'Source': f'https://finance.yahoo.com/quote/{ticker}/',
        'Financial source': f'https://finance.yahoo.com/quote/{ticker}/cash-flow/',
        'Status': 'Secondary provider snapshot; filing reconciliation pending',
    }
    for key in ('Market cap ($bn)', 'Enterprise value ($bn)'):
        if row[key] is not None:
            row[key] /= 1e9
    fiscal_marker = info.get('lastFiscalYearEnd')
    known_year = previous.get('Fiscal year end') if previous else None
    annual_complete = previous and all(previous.get(field) is not None for field in (
        'Revenue (FY, $bn)', 'EBITDA (FY, $bn)', 'CFO (FY, $bn)', 'CapEx (FY, $bn)', 'FCF (FY, $bn)'))
    if annual_complete and fiscal_marker and known_year == str(datetime.fromtimestamp(fiscal_marker, timezone.utc).date()):
        for field, value in previous.items():
            if '(FY,' in field or field in ('Fiscal year end', 'Annual retrieved (UTC)'):
                row[field] = value
        ebitda, fcf = row['EBITDA (FY, $bn)'], row['FCF (FY, $bn)']
        ev, cap = row['Enterprise value ($bn)'], row['Market cap ($bn)']
        row['EV / EBITDA (FY, x)'] = ev / ebitda if ev and ebitda and ebitda > 0 else None
        row['FCF yield (FY, %)'] = fcf / cap * 100 if fcf is not None and cap and cap > 0 else None
        row['Status'] += '; saved annual statements reused after checking latest fiscal year'
        return row
    try:
        cash = stock.get_cash_flow(freq='yearly')
        income = stock.get_income_stmt(freq='yearly')
        if cash.empty:
            raise ValueError('Annual cash flow unavailable')
        period = max(cash.columns)
        row['Fiscal year end'] = str(pd.Timestamp(period).date())
        def fact(table, label):
            return number(table.loc[label, period]) if label in table.index and period in table.columns else None
        cfo = fact(cash, 'OperatingCashFlow')
        capex = fact(cash, 'CapitalExpenditure')
        revenue = fact(income, 'TotalRevenue')
        ebitda = fact(income, 'EBITDA')
        # Yahoo reports cash CapEx as a negative outflow. Unexpected signs are quarantined.
        spend = -capex if capex is not None and capex <= 0 else None
        fcf = cfo - spend if cfo is not None and spend is not None else None
        for key, value in [('Revenue (FY, $bn)', revenue), ('EBITDA (FY, $bn)', ebitda), ('CFO (FY, $bn)', cfo),
                           ('CapEx (FY, $bn)', spend), ('FCF (FY, $bn)', fcf)]:
            row[key] = value / 1e9 if value is not None else None
        row['FCF margin (FY, %)'] = fcf / revenue * 100 if fcf is not None and revenue and revenue > 0 else None
        ev = positive(info.get('enterpriseValue'))
        market_cap = positive(info.get('marketCap'))
        row['EV / EBITDA (FY, x)'] = ev / ebitda if ev and ebitda and ebitda > 0 else None
        row['FCF yield (FY, %)'] = fcf / market_cap * 100 if fcf is not None and market_cap else None
        if fcf is None:
            row['Status'] += '; CFO or negative-signed CapEx unavailable'
    except Exception:
        row['Status'] += '; annual statements unavailable'
    row['Retrieved (UTC)'] = datetime.now(timezone.utc).isoformat(timespec='seconds')
    row['Annual retrieved (UTC)'] = row['Retrieved (UTC)'] if row['Fiscal year end'] else None
    return row


def peer_statistics(frame):
    """Equal-weight statistics; one business group, quote date and FY end per row."""
    records = []
    keys = ['Peer group', 'Quote date', 'Fiscal year end']
    for group, members in frame.groupby(keys, dropna=False):
        for metric in ['P/E (TTM, x)', 'EV / EBITDA (FY, x)', 'Revenue (FY, $bn)', 'FCF (FY, $bn)', 'FCF yield (FY, %)', 'FCF margin (FY, %)']:
            values = pd.to_numeric(members[metric], errors='coerce').dropna()
            records.append(dict(zip(keys, group)) | {
                'Metric': metric, 'Mean': values.mean() if len(values) >= 2 else None,
                'Median': values.median() if len(values) >= 2 else None,
                'Coverage': f'{len(values)}/{len(members)}',
            })
    return pd.DataFrame(records)


def peer_group(subsector, ticker):
    if subsector == 'E04':
        return 'Nuclear components' if ticker == 'BWXT' else 'Diversified generators'
    if subsector == 'E05':
        return 'Storage equipment' if ticker == 'FLNC' else 'Integrated utility / developer'
    if subsector == 'E08':
        return 'Fuel cells' if ticker == 'BE' else 'Diversified engine equipment'
    return subsector


def retrieve_member(ticker):
    result = {'ticker': ticker}
    try:
        old = latest_snapshot('financials', ticker)
        result['financials'] = fetch_company(ticker, previous=old)
        if old and not result['financials'].get('Fiscal year end'):
            for field, value in old.items():
                if '(FY,' in field or field in ('Fiscal year end', 'Annual retrieved (UTC)'):
                    result['financials'][field] = value
            result['financials']['Status'] += '; previous annual snapshot retained with its original period'
        save_snapshot('financials', ticker, result['financials'])
    except Exception as exc:
        result['financial_error'] = f'Retrieval failed ({type(exc).__name__}); use refresh to retry.'
    try:
        prior = restore_members([ticker])
        result['prices'], result['price_source'] = fetch_prices(ticker,
            previous=prior['prices'].get(ticker), previous_source=prior['price_sources'].get(ticker))
        save_snapshot('prices', ticker, {'data': json.loads(result['prices'].reset_index().to_json(orient='split', date_format='iso')),
                                        'source': result['price_source']})
    except Exception as exc:
        result['price_error'] = f'History retrieval failed ({type(exc).__name__}); use refresh to retry.'
    save_snapshot('company_attempts', ticker, {key: value for key, value in result.items() if key.endswith('_error')}
                  | {'attempted_at': datetime.now(timezone.utc).isoformat()})
    return result


def restore_members(tickers):
    snapshot = {'rows': {}, 'prices': {}, 'price_sources': {}, 'financial_errors': {}, 'price_errors': {},
                'last_refresh': 'Not refreshed in this session'}
    for ticker in tickers:
        row = latest_snapshot('financials', ticker)
        if row:
            snapshot['rows'][ticker] = row
        prices = latest_snapshot('prices', ticker)
        if prices:
            try:
                frame = pd.DataFrame(prices['data']['data'], columns=prices['data']['columns'])
                frame['Date'] = pd.to_datetime(frame['Date'])
                snapshot['prices'][ticker] = frame.set_index('Date')
                snapshot['price_sources'][ticker] = prices['source']
            except (KeyError, ValueError, TypeError):
                snapshot['price_errors'][ticker] = 'Saved prices could not be read; refresh to retry.'
        attempt = latest_snapshot('company_attempts', ticker) or {}
        for field, error in [('financial_errors', 'financial_error'), ('price_errors', 'price_error')]:
            if error in attempt:
                snapshot[field][ticker] = attempt[error]
    return snapshot


def load_members(tickers, previous=None):
    snapshot = previous if previous is not None else restore_members(tickers)
    tickers = sorted(set(tickers))
    # Workers persist each successful component immediately, even before polling.
    pool = ThreadPoolExecutor(max_workers=3)
    st.session_state['market_jobs'] = {ticker: pool.submit(retrieve_member, ticker) for ticker in tickers}
    st.session_state['market_pool'] = pool
    st.session_state['market_job_total'] = len(tickers)
    snapshot.setdefault('last_refresh', 'Initial load in progress')
    st.session_state['market_snapshot'] = snapshot
    return snapshot


def apply_member(snapshot, ticker, member):
    for field in ('financial_errors', 'price_errors'):
        snapshot[field].pop(ticker, None)
    if 'financials' in member:
        snapshot['rows'][ticker] = member['financials']
    if 'financial_error' in member:
        snapshot['financial_errors'][ticker] = member['financial_error']
    if 'prices' in member:
        snapshot['prices'][ticker] = member['prices']
        snapshot['price_sources'][ticker] = member['price_source']
    if 'price_error' in member:
        snapshot['price_errors'][ticker] = member['price_error']


@st.fragment(run_every='2s')
def render_market_controls(tickers):
    st.subheader('Company market data')
    requested = tuple(sorted(set(tickers)))
    refresh = st.button('Refresh all financials and prices', type='primary', disabled=bool(st.session_state.get('market_jobs')),
                        help='Check for new quotes and annual periods, and download only new price dates with one overlap date.')
    if 'market_snapshot' not in st.session_state or st.session_state.get('market_universe') != requested:
        st.session_state['market_snapshot'] = restore_members(requested)
        st.session_state['market_universe'] = requested
    if refresh:
        load_members(requested, st.session_state['market_snapshot'])
    snapshot = st.session_state['market_snapshot']
    jobs = st.session_state.get('market_jobs', {})
    changed = False
    for ticker, job in list(jobs.items()):
        if not job.done():
            continue
        try:
            member = job.result()
        except Exception as exc:
            member = {'financial_error': f'Update failed ({type(exc).__name__}); saved data retained.',
                      'price_error': f'Update failed ({type(exc).__name__}); saved data retained.'}
        apply_member(snapshot, ticker, member)
        jobs.pop(ticker)
        changed = True
    if jobs:
        total = st.session_state['market_job_total']
        st.progress((total - len(jobs)) / total, text=f'Company data loading: {total-len(jobs)}/{total}. Electricity tools are ready to use.')
    elif changed:
        st.session_state['market_pool'].shutdown(wait=False)
        snapshot['last_refresh'] = datetime.now(timezone.utc).isoformat(timespec='seconds')
    if changed:
        st.rerun()
    st.caption(f"Saved financials: {len(snapshot['rows'])}/{len(requested)} · saved price histories: {len(snapshot['prices'])}/{len(requested)}. Saved data loads on startup; new provider requests run only when you refresh. Each company retains its original quote, fiscal-period and retrieval dates.")
    if not snapshot['rows'] and not snapshot['prices'] and not jobs:
        st.info('No saved company data yet. Click Refresh all financials and prices for the first download.')
    if snapshot['financial_errors'] or snapshot['price_errors']:
        with st.expander('Company data availability'):
            st.json({'Financial retrieval failures': snapshot['financial_errors'],
                     'Price retrieval failures': snapshot['price_errors']})
    return snapshot


def render_subsector(item):
    st.markdown(f"**Value chain** · {item['value_chain']}")
    st.write(item['economics'])
    st.caption(f"Operating KPIs: {item['kpis']} · Valuation route: {item['valuation']}")
    tickers = [value.strip() for value in item['companies'].split('·')]
    st.caption('Company-wide sample exposure; diversified issuers are not pure plays. Yahoo Finance data may be delayed; financials are latest annual reports, not real-time earnings.')
    snapshot = st.session_state['market_snapshot']
    if st.button('Refresh this group', key=f"load_{item['id']}", disabled=bool(st.session_state.get('market_jobs'))):
        load_members(tickers, snapshot)
        # Re-render the whole page so every overlapping group and comparison updates.
        st.rerun()
    rows = []
    for ticker in tickers:
        if ticker in snapshot['financial_errors'] and ticker in snapshot['rows']:
            st.warning(f'{ticker}: update failed; showing the previously saved financial snapshot.')
        if ticker in snapshot['rows']:
            row = snapshot['rows'][ticker].copy()
            row['Peer group'] = peer_group(item['id'], ticker)
            row['Quote date'] = row['Quote time (UTC)'][:10]
            rows.append(row)
        else:
            if ticker in st.session_state.get('market_jobs', {}):
                st.caption(f'{ticker}: loading…')
            else:
                st.warning(f"{ticker}: {snapshot['financial_errors'].get(ticker, 'Financial data unavailable')}")
    chart_price_history(snapshot, tickers, item['id'])
    if not rows:
        st.info('Company data is loading. Any retrieval failures will appear with a refresh option.' if st.session_state.get('market_jobs') else 'No company data returned. Use Refresh this group to retry.')
        return
    frame = pd.DataFrame(rows)
    st.markdown('**Company financials**')
    st.caption('USD billions except price, multiples and percentages. FCF = annual CFO − cash CapEx; negative FCF is retained. FY multiples use latest annual financials with current provider market cap / EV; EV balance-sheet dates may lag the quote. These are screening metrics pending filing reconciliation.')
    display = ['Ticker', 'Company', 'Peer group', 'Price ($)', 'Market cap ($bn)',
               'Enterprise value ($bn)', 'P/E (TTM, x)', 'EV / EBITDA (FY, x)', 'Revenue (FY, $bn)', 'EBITDA (FY, $bn)',
               'CFO (FY, $bn)', 'CapEx (FY, $bn)', 'FCF (FY, $bn)',
               'FCF yield (FY, %)', 'FCF margin (FY, %)', 'Fiscal year end', 'Quote time (UTC)']
    st.dataframe(frame[display].round(2), hide_index=True, width='stretch')
    st.markdown('**Peer averages and medians**')
    st.caption('Equal weight; split by business group, quote date and fiscal year end. At least two valid values required. Missing values and nonpositive earnings multiples excluded; no pooled average across different groups.')
    stats = peer_statistics(frame)
    st.dataframe(stats.round(2), hide_index=True, width='stretch')
    selected_metric = remembered('selectbox', 'Visualize peer averages', list(stats['Metric'].unique()), key=f"peer_metric_{item['id']}")
    comparable = stats.loc[stats['Metric'].eq(selected_metric)].dropna(subset=['Mean']).copy()
    if not comparable.empty:
        comparable['Comparable peer set'] = comparable.apply(
            lambda row: f"{row['Peer group']} · {row['Quote date']} · FY {row['Fiscal year end']}", axis=1)
        st.bar_chart(comparable, x='Comparable peer set', y=['Mean', 'Median'],
                     y_label=selected_metric, alt=f'Peer mean and median of {selected_metric}')
    else:
        st.caption('This metric has fewer than two comparable valid observations; no average bar is shown.')
    st.markdown('**Company details and sources**')
    selected = remembered('selectbox', 'Company', frame['Ticker'].tolist(), key=f"detail_{item['id']}")
    row = next(row for row in rows if row['Ticker'] == selected)
    st.table(pd.DataFrame([{'Field': key, 'Value': str(value) if value is not None else 'Unavailable from provider'} for key, value in row.items()]))
    st.download_button('Download snapshot and source metadata', frame.to_csv(index=False),
                       file_name=f"{item['id']}_financials.csv", mime='text/csv', key=f"csv_{item['id']}")
