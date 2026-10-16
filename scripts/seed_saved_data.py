"""One-off current-universe download. Safe to repeat: saved histories are extended."""
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
import ast
import json
import logging
import os
import sys
import tomllib
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import pandas as pd
from company_financials import retrieve_member, restore_members
import electricity as e
from local_store import preference, save_preference, save_snapshot, latest_snapshot, atomic_json


def seed_electricity():
    key = os.getenv('EIA_API_KEY')
    secrets = ROOT / '.streamlit' / 'secrets.toml'
    if not key and secrets.exists():
        key = tomllib.loads(secrets.read_text(encoding='utf-8-sig')).get('EIA_API_KEY')
    if not key:
        return {'status': 'No key; saved data retained'}
    parent = preference('widget:eia_area', 'TVA')
    sub = preference('widget:eia_sub_' + parent)
    preset = preference('widget:eia_range', '1M') or '1M'
    tz = preference('widget:eia_timezone', 'America/New_York')
    today = datetime.now(timezone.utc).astimezone(ZoneInfo(tz)).date()
    end = today
    start = end - timedelta(days={'1M': 29, '3M': 89, '1Y': 364, '5Y': 1825}.get(preset, 29))
    if preset == 'Custom':
        saved = preference('eia_custom_dates')
        if saved:
            start, end = [date.fromisoformat(value) for value in saved]
    save_preference('eia_anchor_date', today.isoformat())
    for name, value in [('eia_area', parent), ('eia_range', preset), ('eia_timezone', tz)]:
        save_preference('widget:' + name, value)
    try:
        if latest_snapshot('eia_catalog', 'areas') is None:
            save_snapshot('eia_catalog', 'areas', e.areas(key))
        if parent in e.SUBREGION_PARENTS and latest_snapshot('eia_catalog', parent) is None:
            save_snapshot('eia_catalog', parent, e.subregions(key, parent))
    except ValueError:
        pass  # Saved catalogs / built-in labels still work offline.
    lo = pd.Timestamp(start).tz_localize(tz).tz_convert('UTC')
    hi = pd.Timestamp(end + timedelta(days=1)).tz_localize(tz).tz_convert('UTC')
    if preset == 'All':
        lo = pd.Timestamp('2019-01-01', tz='UTC').tz_convert(tz).normalize().tz_convert('UTC')
    e.import_saved_months(parent, sub)
    try:
        frame, meta = e.fetch_history(key, parent, sub, lo+pd.Timedelta(hours=1), hi,
            lambda progress: print(f'EIA {parent}: {progress:.0%}', flush=True), refresh=True)
        return {'status': 'Downloaded', 'area': parent, 'rows': len(frame), 'source_retrieved_at': meta['retrieved_at']}
    except (ValueError, OSError) as exc:
        saved = e.restore_history(parent, sub, lo, hi)
        return {'status': 'Partial download retained', 'area': parent, 'rows': len(saved[0]) if saved else 0,
                'error': str(exc)}


def main():
    logging.getLogger('yfinance').setLevel(logging.CRITICAL)
    tree = ast.parse((ROOT / 'app.py').read_text(encoding='utf-8'))
    groups = next(ast.literal_eval(node.value) for node in tree.body if isinstance(node, ast.Assign)
                  and any(isinstance(target, ast.Name) and target.id == 'ENERGY_BREAKDOWN' for target in node.targets))
    tickers = sorted({ticker.strip() for group in groups for ticker in group['companies'].split('·')})
    report = {'started_at': datetime.now(timezone.utc).isoformat(), 'companies': {}}
    with ThreadPoolExecutor(max_workers=1) as eia_pool, ThreadPoolExecutor(max_workers=3) as company_pool:
        jobs = {company_pool.submit(retrieve_member, ticker): ticker for ticker in tickers}
        eia_job = eia_pool.submit(seed_electricity)
        for index, job in enumerate(as_completed(jobs), 1):
            ticker = jobs[job]
            try:
                member = job.result()
                report['companies'][ticker] = {'financials': 'financials' in member, 'prices': 'prices' in member,
                    'financial_error': member.get('financial_error'), 'price_error': member.get('price_error')}
            except Exception as exc:
                report['companies'][ticker] = {'error': type(exc).__name__}
            print(f'Companies {index}/{len(tickers)}: {ticker} {report["companies"][ticker]}', flush=True)
            atomic_json(ROOT/'data'/'saved'/'initial_download_report.json', report)
        report['electricity'] = eia_job.result()
    restored = restore_members(tickers)
    report.update(completed_at=datetime.now(timezone.utc).isoformat(), financials_saved=len(restored['rows']),
                  histories_saved=len(restored['prices']), mapped_tickers=len(tickers))
    atomic_json(ROOT/'data'/'saved'/'initial_download_report.json', report)
    print(json.dumps({key: value for key, value in report.items() if key != 'companies'}), flush=True)


if __name__ == '__main__':
    main()
