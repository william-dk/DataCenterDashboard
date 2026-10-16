"""Historical price retrieval and fixed-cohort value-chain indices."""
from datetime import datetime, timezone
from threading import Lock, local
from time import monotonic, sleep

import numpy as np
import pandas as pd
import streamlit as st
from curl_cffi.requests import Session
from local_store import remembered


class BoundedYahooSession(Session):
    """Use per-thread sessions and space Yahoo requests to reduce 429s."""
    def request(self, method, url, **kwargs):
        global _last_yahoo_request
        kwargs.setdefault('timeout', 20)
        # Yahoo throttles bursty requests, especially from shared cloud IPs.
        # Space request starts across all worker threads in this process.
        with _yahoo_request_lock:
            delay = _YAHOO_MIN_INTERVAL - (monotonic() - _last_yahoo_request)
            if delay > 0:
                sleep(delay)
            _last_yahoo_request = monotonic()
        return super().request(method, url, **kwargs)


_yahoo_request_lock = Lock()
_last_yahoo_request = 0.0
_yahoo_thread_state = local()
_YAHOO_MIN_INTERVAL = 1.25


def yahoo_session():
    # curl_cffi sessions are not shared between concurrent Streamlit workers.
    session = getattr(_yahoo_thread_state, 'session', None)
    if session is None:
        session = BoundedYahooSession(impersonate='chrome')
        _yahoo_thread_state.session = session
    return session


def fetch_prices(ticker, previous=None, previous_source=None):
    import yfinance as yf

    stock = yf.Ticker(ticker, session=yahoo_session())
    incremental = previous is not None and not previous.empty
    window = {'start': previous.index.max().date().isoformat()} if incremental else {'period': 'max'}
    history = stock.history(**window, interval='1d', auto_adjust=False,
                            actions=False, timeout=20, raise_errors=True)
    if stock.get_history_metadata().get('currency') != 'USD':
        raise ValueError('Price currency unavailable or non-USD; FX normalization is not configured.')
    if history.empty or not {'Close', 'Adj Close'}.issubset(history.columns):
        raise ValueError('Historical closing prices unavailable.')
    history = history[['Close', 'Adj Close']].copy()
    # Preserve exchange-session dates rather than shifting sessions across UTC dates.
    history.index = pd.to_datetime(history.index).tz_localize(None).normalize()
    history = history.apply(pd.to_numeric, errors='coerce')
    history = history.where(np.isfinite(history) & (history > 0))
    if history.index.duplicated().any():
        raise ValueError('Duplicate trading dates returned.')
    history.index.name = 'Date'
    adjustments = {}
    if incremental:
        overlap = history.index.intersection(previous.index)
        if overlap.empty:
            raise ValueError('No overlap to reconcile split/dividend adjustments; saved history retained.')
        old = previous.copy()
        for field in ('Close', 'Adj Close'):
            matches = overlap[(history.loc[overlap, field].notna() & old.loc[overlap, field].notna()).values]
            if not len(matches):
                raise ValueError('Adjustment baseline missing; saved history retained.')
            anchor = matches[-1]
            factor = float(history.loc[anchor, field] / old.loc[anchor, field])
            old[field] *= factor
            adjustments[field] = factor
        history = pd.concat([old, history])
        history = history.loc[~history.index.duplicated(keep='last')]
    return history.sort_index(), {
        'source': f'https://finance.yahoo.com/quote/{ticker}/history/',
        'retrieved_at': datetime.now(timezone.utc).isoformat(timespec='seconds'),
        'basis': 'Yahoo Close and dividend/split-adjusted Adj Close; daily exchange-session dates',
        'request_mode': 'Incremental with one saved trading date for adjustment reconciliation' if incremental else 'Initial maximum history',
        'request_start': window.get('start'), 'prior_retrieved_at': (previous_source or {}).get('retrieved_at'),
        'historical_adjustment_factors': adjustments,
    }


def price_matrix(snapshot, tickers, field='Adj Close'):
    series = {ticker: snapshot['prices'][ticker][field]
              for ticker in tickers if ticker in snapshot['prices']}
    return pd.DataFrame(series).sort_index() if series else pd.DataFrame()


def window_prices(frame, window):
    if frame.empty:
        return frame
    # Window anchored to the last available trading date, not a future calendar day.
    end = frame.index.max()
    if window == 'Max':
        return frame
    start = pd.Timestamp(year=end.year, month=1, day=1) if window == 'YTD' else end - pd.DateOffset(
        months={'1M': 1, '3M': 3, '6M': 6, '1Y': 12, '3Y': 36, '5Y': 60}[window])
    return frame.loc[frame.index >= start]


def normalized_prices(frame):
    """One common baseline and fixed members; no averaging over missing constituents."""
    if frame.empty:
        return frame
    complete = frame.dropna(how='any')
    if complete.empty:
        return frame.iloc[:0]
    base_date = complete.index[0]
    return frame.loc[base_date:].div(complete.iloc[0]).mul(100)


def chart_price_history(snapshot, tickers, key):
    st.markdown('**Historical prices and group performance**')
    window = remembered('selectbox', 'Price history range', ['1M', '3M', '6M', 'YTD', '1Y', '3Y', '5Y', 'Max'], index=4, key=f'window_{key}')
    matrix = window_prices(price_matrix(snapshot, tickers), window)
    if matrix.empty:
        st.info('Price history unavailable for this group. Use refresh to retry.')
        return
    selected = remembered('selectbox', 'Company price chart', list(matrix.columns), key=f'price_company_{key}')
    failed = [ticker for ticker in tickers if ticker in snapshot['price_errors'] and ticker in snapshot['prices']]
    if failed:
        st.warning(f"Price update failed for {', '.join(failed)}; previously saved histories are shown.")
    individual = snapshot['prices'][selected][['Close']]
    individual = window_prices(individual, window)
    st.line_chart(individual, y_label='Closing price (USD)', x_label='Trading date',
                  alt=f'{selected} historical closing price in US dollars')
    st.caption(f"{selected} · Yahoo Close (split-adjusted, not dividend-adjusted) · {snapshot['price_sources'][selected]['source']} · fetched {snapshot['price_sources'][selected]['retrieved_at']}")
    normalized = normalized_prices(matrix)
    if normalized.empty:
        st.info('No common price date exists for the available members.')
        return
    series = normalized.copy()
    series['Group equal-weight index'] = normalized.mean(axis=1, skipna=False)
    st.line_chart(series, y_label='Adjusted-price index (start = 100)', x_label='Trading date',
                  alt='Individual adjusted-price indices and the fixed-cohort equal-weight group index')
    st.caption(f"Baseline {normalized.index[0].date()} · members {', '.join(matrix.columns)} · coverage {len(matrix.columns)}/{len(tickers)}. Group index = mean(100 × adjusted price / baseline adjusted price), initially equal dollars, buy-and-hold, no rebalancing. Missing member prices leave a gap; no forward-fill. Latest quotes and historical daily bars have different timestamps.")
    st.caption('Uses current sample members and Yahoo dividend/split adjustments; this is a descriptive basket with survivorship bias, not a historical investable sector index or historical valuation multiple.')
    st.download_button('Download price indices', series.to_csv(), f'{key}_price_indices.csv', 'text/csv', key=f'price_csv_{key}')


@st.fragment
def render_group_comparison(snapshot, groups):
    st.subheader('Energy value-chain performance')
    chosen = remembered('multiselect', 'Compare value-chain groups', [item['id'] for item in groups], key='compare_groups',
                            default=[item['id'] for item in groups],
                            format_func=lambda code: next(f"{item['id']} · {item['name']}" for item in groups if item['id'] == code))
    window = remembered('selectbox', 'Comparison range', ['1M', '3M', '6M', 'YTD', '1Y', '3Y', '5Y', 'Max'], index=4, key='comparison_range')
    required = sorted({ticker.strip() for item in groups if item['id'] in chosen for ticker in item['companies'].split('·')})
    matrix = window_prices(price_matrix(snapshot, required), window)
    normalized = normalized_prices(matrix)
    if normalized.empty:
        st.info('Select groups with available history to compare performance.')
        return
    indices, coverage = {}, []
    for item in groups:
        if item['id'] not in chosen:
            continue
        members = [ticker.strip() for ticker in item['companies'].split('·')]
        included = [ticker for ticker in members if ticker in normalized]
        if included:
            indices[f"{item['id']} · {item['name']}"] = normalized[included].mean(axis=1, skipna=False)
        coverage.append({'Group': item['id'], 'Included / mapped': f'{len(included)}/{len(members)}',
                         'Members': ', '.join(included), 'Unavailable': ', '.join(set(members) - set(included)) or 'None'})
    if indices:
        frame = pd.DataFrame(indices)
        # Native line_chart puts a long eight-item legend on one horizontal row,
        # which clips the later subsectors on narrower screens. Use an explicit
        # Altair legend with multiple rows and full labels instead.
        import altair as alt
        long = frame.rename_axis('Trading date').reset_index().melt(
            id_vars='Trading date', var_name='Value-chain group', value_name='Index')
        chart = alt.Chart(long).mark_line(strokeWidth=2).encode(
            x=alt.X('Trading date:T', title='Trading date'),
            y=alt.Y('Index:Q', title='Adjusted-price basket index (start = 100)'),
            color=alt.Color('Value-chain group:N', title='Energy subsector',
                            legend=alt.Legend(orient='bottom', columns=2,
                                               labelLimit=320, labelFontSize=12,
                                               symbolSize=90, rowPadding=5)),
            tooltip=[alt.Tooltip('Trading date:T', title='Date'),
                     alt.Tooltip('Value-chain group:N', title='Subsector'),
                     alt.Tooltip('Index:Q', format=',.1f')],
        ).properties(height=390)
        with alt.data_transformers.disable_max_rows():
            st.altair_chart(chart, width='stretch',
                            alt='Equal-weight adjusted-price basket performance across all Energy value-chain groups')
        st.caption(f"Common baseline: {frame.index[0].date()}. Current sample memberships; all displayed groups start on the same date. Max starts when the youngest included listing has data. Companies can appear in several groups. Missing constituent data produces gaps; failed downloads are listed in coverage.")
        st.dataframe(pd.DataFrame(coverage), hide_index=True, width='stretch')
        st.download_button('Download group comparison', frame.to_csv(), 'energy_group_indices.csv', 'text/csv')
