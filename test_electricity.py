"""Retrieval regression checks; no network or credentials required."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import electricity as e


def row(stamp):
    return {'period': stamp.strftime('%Y-%m-%dT%H'), 'respondent': 'TVA',
            'type': 'D', 'value': '10000', 'value-units': 'megawatthours'}


class RetrievalTests(unittest.TestCase):
    def test_timeout_splits_without_overlapping_hours(self):
        requested = []
        def request(key, route, params):
            self.assertNotIn('sort[0][column]', params)
            start, end = [pd.Timestamp(params[k], tz='UTC') for k in ('start', 'end')]
            if end-start >= pd.Timedelta(days=2):
                raise ValueError('EIA connection failed or timed out.')
            requested.extend(pd.date_range(start, end, freq='h'))
            rows = [row(t) for t in pd.date_range(start, end, freq='h')]
            return {'data': rows, 'total': len(rows)}
        start, end = pd.Timestamp('2025-01-01', tz='UTC'), pd.Timestamp('2025-01-07T23:00Z')
        with patch.object(e, 'request_eia', side_effect=request):
            rows = e.fetch_slice('unused', 'unused', {}, start, end)
        self.assertEqual(len(rows), 168)
        self.assertEqual(len(set(requested)), 168)
        self.assertEqual(min(requested), start)
        self.assertEqual(max(requested), end)

    def test_resume_reuses_completed_months_and_refresh_fetches_again(self):
        calls, fail = [], [True]
        def request(key, route, filters, start, end):
            calls.append(start.month)
            if start.month == 3 and fail[0]:
                raise ValueError('EIA connection failed or timed out.')
            return [row(t) for t in pd.date_range(start, end, freq='h')]
        start, end = pd.Timestamp('2025-01-15T05:00Z'), pd.Timestamp('2025-03-02T04:00Z')
        with tempfile.TemporaryDirectory() as folder, patch.object(e, 'CHUNK_CACHE', Path(folder)), patch.object(e, 'EIA_FOLDER', Path(folder)), patch.object(e, 'fetch_slice', side_effect=request):
            with self.assertRaisesRegex(ValueError, 'March 2025'):
                e.fetch_history('unused', 'TVA', None, start, end)
            fail[0] = False
            calls.clear()
            frame, meta = e.fetch_history('unused', 'TVA', None, start, end)
            self.assertEqual(calls, [3])
            self.assertEqual(len(frame), len(pd.date_range(start, end, freq='h')))
            self.assertFalse(frame['period'].duplicated().any())
            self.assertEqual(len(meta['month_sources']), 3)
            calls.clear()
            e.fetch_history('unused', 'TVA', None, start, end, refresh=True)
            self.assertEqual(calls, [])
            self.assertEqual(len(list(Path(folder).glob('*.snapshot.json'))), 0)

    def test_incremental_fetch_only_missing_hours_and_restore_partial(self):
        month = pd.Timestamp('2025-01-01', tz='UTC')
        first_end = month + pd.Timedelta(days=4) - pd.Timedelta(hours=1)
        calls = []
        def fetch(key, route, filters, start, end):
            calls.append((start, end))
            stop = first_end if len(calls) == 1 else end
            return [row(t) for t in pd.date_range(start, stop, freq='h')]
        with tempfile.TemporaryDirectory() as folder, patch.object(e, 'CHUNK_CACHE', Path(folder)/'months'), patch.object(e, 'EIA_FOLDER', Path(folder)), patch.object(e, 'fetch_slice', side_effect=fetch):
            e.month_chunk('unused', 'TVA', None, month)
            restored = e.restore_history('TVA', None, month, month + pd.Timedelta(days=10))
            self.assertTrue(restored[1]['partial'])
            self.assertEqual(len(restored[0]), 95)
            e.month_chunk('unused', 'TVA', None, month, refresh=True)
            self.assertEqual(calls[1][0], first_end + pd.Timedelta(hours=1))
            self.assertEqual(len(calls), 2)

    def test_bounds_only_queries_bounded_months(self):
        def chunk(key, parent, subregion, month, refresh):
            if month == pd.Timestamp('2019-01-01', tz='UTC'):
                return [row(month)], 'unused'
            return [row(month + pd.Timedelta(hours=1))], 'unused'
        with patch.object(e, 'import_saved_months'), patch.object(e, 'month_chunk', side_effect=chunk) as mock:
            first, last = e.bounds('unused', 'TVA', None)
        self.assertEqual(first, pd.Timestamp('2019-01-01', tz='UTC'))
        self.assertGreater(last, first)
        self.assertEqual(mock.call_count, 2)

    def test_invalid_entity_is_never_cached(self):
        month = pd.Timestamp('2025-01-01', tz='UTC')
        bad = row(month) | {'respondent': 'PJM'}
        with tempfile.TemporaryDirectory() as folder, patch.object(e, 'CHUNK_CACHE', Path(folder)), patch.object(e, 'fetch_slice', return_value=[bad]):
            with self.assertRaisesRegex(ValueError, 'conflicting entity'):
                e.month_chunk('unused', 'TVA', None, month)
            self.assertEqual(list(Path(folder).iterdir()), [])

    def test_legacy_csv_is_reused_before_incremental_requests(self):
        import json
        month = pd.Timestamp('2025-01-01', tz='UTC')
        with tempfile.TemporaryDirectory() as folder, patch.object(e, 'CHUNK_CACHE', Path(folder)/'months'), patch.object(e, 'EIA_FOLDER', Path(folder)), patch.object(e, 'request_eia', side_effect=AssertionError('Existing hours must not be downloaded')):
            path = Path(folder)/'legacy'
            pd.DataFrame([row(t) for t in pd.date_range(month, month+pd.Timedelta(days=30,hours=23),freq='h')]).to_csv(path.with_suffix('.csv'),index=False)
            path.with_suffix('.json').write_text(json.dumps({'parent':'TVA','subregion':None,'retrieved_at':'2025-02-02T00:00:00+00:00'}))
            e.import_saved_months('TVA',None)
            rows, retrieved = e.month_chunk('unused','TVA',None,month,refresh=True)
            self.assertEqual(len(rows),744)
            self.assertEqual(retrieved,'2025-02-02T00:00:00+00:00')


if __name__ == '__main__':
    unittest.main()
