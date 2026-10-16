import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import pandas as pd
from streamlit.testing.v1 import AppTest
import local_store as store
import company_financials as c
import electricity as e
from market_history import fetch_prices, yahoo_session


def financial_row(ticker='SO'):
    row = {key: 1.0 for key in ['Price ($)', 'Market cap ($bn)', 'Enterprise value ($bn)', 'P/E (TTM, x)',
        'EV / EBITDA (FY, x)', 'Revenue (FY, $bn)', 'EBITDA (FY, $bn)', 'CFO (FY, $bn)', 'CapEx (FY, $bn)',
        'FCF (FY, $bn)', 'FCF yield (FY, %)', 'FCF margin (FY, %)']}
    return row | {'Ticker': ticker, 'Company': ticker, 'Fiscal year end': '2025-12-31',
                  'Quote time (UTC)': '2026-10-15T20:00:00+00:00', 'Retrieved (UTC)': '2026-10-15T20:05:00+00:00',
                  'Annual retrieved (UTC)': '2026-10-15T20:05:00+00:00', 'Source': 'fixture', 'Status': 'fixture'}


class RestoreTests(unittest.TestCase):
    def test_yahoo_sessions_are_not_shared_between_threads(self):
        from concurrent.futures import ThreadPoolExecutor
        main_session = yahoo_session()
        with ThreadPoolExecutor(max_workers=1) as pool:
            worker_session = pool.submit(yahoo_session).result()
        self.assertIsNot(main_session, worker_session)

    def test_rate_limit_message_is_actionable_and_typeerror_keeps_detail(self):
        rate_error = c.retrieval_error(type('YFRateLimitError', (Exception,), {})('Too Many Requests'), 'Financial data unavailable')
        type_error = c.retrieval_error(TypeError("unexpected 'foo' argument"), 'Financial data unavailable')
        self.assertIn('Wait a few minutes', rate_error)
        self.assertIn("unexpected 'foo' argument", type_error)

    def test_partial_company_download_persists_and_failed_update_keeps_it(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(store, 'STORE', Path(folder)), patch.object(c, 'fetch_company', return_value=financial_row()), patch.object(c, 'fetch_prices', side_effect=ValueError('offline')):
            member = c.retrieve_member('SO')
            snap = c.restore_members(['SO'])
            self.assertIn('SO', snap['rows'])
            self.assertIn('SO', snap['price_errors'])
            c.apply_member(snap, 'SO', {'financial_error': 'offline', 'price_error': 'offline'})
            self.assertEqual(snap['rows']['SO']['Retrieved (UTC)'], financial_row()['Retrieved (UTC)'])
            self.assertIn('financials', member)

    def test_saved_prices_roundtrip_and_incremental_adjustment(self):
        old = pd.DataFrame({'Close': [10., 11.], 'Adj Close': [9., 10.]}, index=pd.to_datetime(['2026-10-13', '2026-10-14']))
        old.index.name = 'Date'
        new = pd.DataFrame({'Close': [11., 12.], 'Adj Close': [9., 10.]}, index=pd.to_datetime(['2026-10-14', '2026-10-15']))
        with patch('yfinance.Ticker') as ticker:
            ticker.return_value.history.return_value = new
            ticker.return_value.get_history_metadata.return_value = {'currency': 'USD'}
            merged, source = fetch_prices('SO', previous=old)
            self.assertEqual(ticker.return_value.history.call_args.kwargs['start'], '2026-10-14')
            self.assertEqual(len(merged), 3)
            self.assertAlmostEqual(merged.iloc[0]['Adj Close'], 8.1)
        with tempfile.TemporaryDirectory() as folder, patch.object(store, 'STORE', Path(folder)):
            store.save_snapshot('prices', 'SO', {'data': json.loads(merged.reset_index().to_json(orient='split', date_format='iso')), 'source': source})
            pd.testing.assert_frame_equal(c.restore_members(['SO'])['prices']['SO'], merged, check_dtype=False)

    def test_unchanged_fiscal_year_reuses_saved_annuals(self):
        info = {'quoteType': 'EQUITY', 'regularMarketTime': 1792094400, 'currency': 'USD',
                'regularMarketPrice': 20, 'marketCap': 2e9, 'enterpriseValue': 3e9,
                'lastFiscalYearEnd': int(pd.Timestamp('2025-12-31', tz='UTC').timestamp())}
        with patch('yfinance.Ticker') as ticker:
            ticker.return_value.get_info.return_value = info
            row = c.fetch_company('SO', financial_row())
            ticker.return_value.get_cash_flow.assert_not_called()
            ticker.return_value.get_income_stmt.assert_not_called()
            self.assertEqual(row['Annual retrieved (UTC)'], financial_row()['Annual retrieved (UTC)'])
            self.assertEqual(row['EV / EBITDA (FY, x)'], 3.)

    def test_fresh_app_session_restores_without_network_and_remembers_navigation(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(store, 'STORE', Path(folder)/'saved'), patch.object(e, 'EIA_FOLDER', Path(folder)/'eia'), patch.object(e, 'CHUNK_CACHE', Path(folder)/'eia'/'months'), patch.object(e, 'request_eia', side_effect=AssertionError('Unexpected network')), patch.object(c, 'retrieve_member', side_effect=AssertionError('Unexpected network')):
            store.save_snapshot('financials', 'SO', financial_row())
            app = AppTest.from_file('app.py').run(timeout=30)
            self.assertFalse(app.exception)
            self.assertIn('SO', app.session_state['market_snapshot']['rows'])
            self.assertNotIn('market_jobs', app.session_state)
            app.selectbox(key='infrastructure_layer').select('L03').run(timeout=30)
            self.assertFalse(app.exception)
            reopened = AppTest.from_file('app.py').run(timeout=30)
            self.assertFalse(reopened.exception)
            self.assertEqual(reopened.selectbox(key='infrastructure_layer').value, 'L03')

    def test_electricity_focus_restores_without_key_or_network(self):
        from datetime import date
        with tempfile.TemporaryDirectory() as folder, patch.object(store, 'STORE', Path(folder)/'saved'), patch.object(e, 'EIA_FOLDER', Path(folder)/'eia'), patch.object(e, 'CHUNK_CACHE', Path(folder)/'eia'/'months'), patch.object(e, 'request_eia', side_effect=AssertionError('Unexpected network')):
            for key, value in [('widget:eia_range','Custom'), ('eia_custom_dates',['2025-01-01','2025-01-10'])]:
                store.save_preference(key, value)
            month = pd.Timestamp('2025-01-01', tz='UTC')
            rows = [{'period': t.strftime('%Y-%m-%dT%H'), 'respondent':'TVA', 'type':'D', 'value':10000,
                     'value-units':'megawatthours'} for t in pd.date_range(month, month+pd.Timedelta(days=30,hours=23),freq='h')]
            with patch.object(e,'fetch_slice',return_value=rows):
                e.month_chunk('fixture','TVA',None,month)
            script = "import electricity as e\ne.render_electricity(None)"
            app = AppTest.from_string(script).run(timeout=20)
            self.assertFalse(app.exception)
            month_select = next(widget for widget in app.selectbox if widget.label=='Month')
            month_select.select(pd.Period('2025-01', freq='M')).run()
            week_select = next(widget for widget in app.selectbox if widget.label=='Week')
            week_select.select(date(2025,1,6)).run()
            reopened = AppTest.from_string(script).run(timeout=20)
            self.assertFalse(reopened.exception)
            self.assertEqual(next(widget for widget in reopened.selectbox if widget.label=='Week').value, date(2025,1,6))
            self.assertEqual(next(m.value for m in reopened.metric if m.label=='Hours reported'), '100.0%')


if __name__ == '__main__':
    unittest.main()
