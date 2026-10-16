"""EIA demand explorer: paginated history, regional detail and calendar aggregation."""
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
import json
import hashlib
import time
import uuid
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import requests
import streamlit as st
from local_store import latest_snapshot, save_snapshot, preference, save_preference, remembered, read_json

BASE = 'https://api.eia.gov/v2/electricity/rto/'
ABOUT = 'https://www.eia.gov/electricity/930-content/about.html'
SUBREGION_PARENTS = {'CISO', 'ERCO', 'MISO', 'ISNE', 'NYIS', 'PJM', 'PNM', 'SWPP'}


def request_eia(key, route, params):
    # Never surface request URLs or exception bodies: URLs contain the API key.
    try:
        response = requests.get(BASE + route, params={'api_key': key, **params}, timeout=(10, 90))
    except requests.RequestException:
        raise ValueError('EIA connection failed or timed out. Retry after checking connectivity.') from None
    if not response.ok:
        raise ValueError(f'EIA returned HTTP {response.status_code}. Check key validity or retry later.')
    try:
        payload = response.json()
        if 'response' not in payload:
            raise ValueError()
        return payload['response']
    except (ValueError, KeyError):
        raise ValueError('EIA did not return the expected data structure.') from None


@st.cache_data(ttl=86400, max_entries=40, show_spinner=False)
def areas(key):
    payload = request_eia(key, 'region-data/facet/respondent/', {'length': 5000})
    return sorted(payload['facets'], key=lambda row: row['name'])


@st.cache_data(ttl=86400, max_entries=40, show_spinner=False)
def subregions(key, parent):
    payload = request_eia(key, 'region-sub-ba-data/facet/subba/', {
        'facets[parent][]': parent, 'length': 5000,
    })
    # Facet responses may include codes from other parents; aliases identify the parent.
    return sorted([row for row in payload['facets'] if row.get('alias', '').startswith(parent + ':')],
                  key=lambda row: row['name'])


def query_for(parent, subregion=None):
    if subregion:
        return 'region-sub-ba-data/data/', {'facets[parent][]': parent, 'facets[subba][]': subregion}
    return 'region-data/data/', {'facets[respondent][]': parent, 'facets[type][]': 'D'}


def hourly_params(filters):
    return {'frequency': 'hourly', 'data[0]': 'value',
            'sort[0][column]': 'period', 'sort[0][direction]': 'asc', **filters}


EIA_FOLDER = Path(__file__).parent / 'data' / 'eia'
CHUNK_CACHE = EIA_FOLDER / 'months_v1'


def month_starts(start, end):
    cursor = start.normalize().replace(day=1)
    while cursor <= end:
        yield cursor
        cursor += pd.offsets.MonthBegin(1)


def fetch_slice(key, route, filters, start, end):
    """Bound the server query, splitting transient failures down to daily requests."""
    params = hourly_params(filters) | {'start': start.strftime('%Y-%m-%dT%H'),
                                      'end': end.strftime('%Y-%m-%dT%H'), 'length': 5000}
    if end - start < pd.Timedelta(days=32):
        # One entity has <=768 hourly rows: no pagination or expensive server
        # ordering is needed. Validate uniqueness and sort locally afterwards.
        params.pop('sort[0][column]')
        params.pop('sort[0][direction]')
    for attempt in range(2):
        try:
            rows, offset, expected = [], 0, None
            while True:
                page = request_eia(key, route, params | {'offset': offset})
                batch = page.get('data', [])
                if expected is None:
                    expected = int(page.get('total', len(batch)))
                if not batch and offset < expected:
                    raise ValueError('EIA pagination ended early. Retry; incomplete retrieval is not saved.')
                rows.extend(batch)
                offset += len(batch)
                if offset >= expected:
                    return rows
        except ValueError as exc:
            transient = any(term in str(exc) for term in ('timed out', 'HTTP 429', 'HTTP 5', 'pagination ended early'))
            if not transient:
                raise
            if end - start >= pd.Timedelta(days=2):
                midpoint = start + pd.Timedelta(hours=int((end-start)/pd.Timedelta(hours=1)) // 2)
                return (fetch_slice(key, route, filters, start, midpoint)
                        + fetch_slice(key, route, filters, midpoint + pd.Timedelta(hours=1), end))
            if attempt:
                raise
            time.sleep(1)


def month_chunk(key, parent, subregion, month, refresh=False):
    route, filters = query_for(parent, subregion)
    end = month + pd.offsets.MonthBegin(1) - pd.Timedelta(hours=1)
    identity = json.dumps([route, filters, month.isoformat()], sort_keys=True)
    path = CHUNK_CACHE / (hashlib.sha256(identity.encode()).hexdigest() + '.json')
    cached = read_json(path, {}) or {}
    old_rows = cached.get('rows', [])
    if cached and not refresh:
        return old_rows, cached['retrieved_at']
    cutoff = min(end, pd.Timestamp.now(tz='UTC').floor('h'))
    present = {pd.Timestamp(row['period'], tz='UTC') for row in old_rows
               if pd.notna(pd.to_numeric(row.get('value'), errors='coerce'))
               and np.isfinite(float(row['value'])) and float(row['value']) >= 0}
    missing = [stamp for stamp in pd.date_range(month, cutoff, freq='h') if stamp not in present]
    spans = []
    for stamp in missing:
        if spans and stamp == spans[-1][1] + pd.Timedelta(hours=1):
            spans[-1] = (spans[-1][0], stamp)
        else:
            spans.append((stamp, stamp))
    if not spans and cached:
        return old_rows, cached['retrieved_at']
    rows = []
    for start, stop in spans:
        rows.extend(fetch_slice(key, route, filters, start, stop))
    # Validate before caching: an invalid response must not poison future loads.
    required = {'period', 'value', 'value-units'} | ({'parent', 'subba'} if subregion else {'respondent', 'type'})
    periods = set()
    for row in rows:
        if not required.issubset(row):
            raise ValueError('EIA schema is incomplete; retrieval was not accepted.')
        entity_ok = (row['parent'] == parent and row['subba'] == subregion) if subregion else (row['respondent'] == parent and row['type'] == 'D')
        stamp = pd.Timestamp(row['period'], tz='UTC')
        if not entity_ok or row['period'] in periods or not month <= stamp <= end:
            raise ValueError('EIA returned conflicting entity or duplicate-hour records; retrieval quarantined.')
        if row['value-units'].lower() != 'megawatthours':
            raise ValueError('Unexpected EIA units; only hourly integrated megawatthours are supported.')
        periods.add(row['period'])
    retrieved = datetime.now(timezone.utc).isoformat()
    combined = {row['period']: dict(row, retrieved_at=row.get('retrieved_at', cached.get('retrieved_at'))) for row in old_rows}
    combined.update({row['period']: dict(row, retrieved_at=retrieved) for row in rows})
    rows = sorted(combined.values(), key=lambda row: row['period'])
    CHUNK_CACHE.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.' + uuid.uuid4().hex + '.tmp')
    temporary.write_text(json.dumps({'rows': rows, 'retrieved_at': retrieved}), encoding='utf-8')
    if path.exists():
        # Retain prior raw snapshots when EIA revises a month.
        path.with_name(path.stem + '_' + uuid.uuid4().hex + '.snapshot.json').write_bytes(path.read_bytes())
    temporary.replace(path)
    return rows, retrieved


def bounds(key, parent, subregion, refresh=False):
    import_saved_months(parent, subregion)
    # EIA-930 API history begins in 2019; earlier downloadable files are separate.
    months = list(month_starts(pd.Timestamp('2019-01-01', tz='UTC'), pd.Timestamp.now(tz='UTC')))
    first = last = None
    for month in months:
        rows, _ = month_chunk(key, parent, subregion, month, refresh)
        if rows:
            first = min(pd.Timestamp(row['period'], tz='UTC') for row in rows)
            break
    if first is not None:
        for month in reversed(months):
            rows, _ = month_chunk(key, parent, subregion, month, refresh)
            if rows:
                last = max(pd.Timestamp(row['period'], tz='UTC') for row in rows)
                break
    if first is None or last is None:
        raise ValueError('No history returned for the selected area.')
    return first, last


def fetch_history(key, parent, subregion, start, end, progress=None, refresh=False):
    import_saved_months(parent, subregion)
    route, filters = query_for(parent, subregion)
    rows, chunk_sources = [], []
    months = list(month_starts(start, end))
    retrieved_start = datetime.now(timezone.utc).isoformat()
    for index, month in enumerate(months):
        try:
            batch, retrieved_at = month_chunk(key, parent, subregion, month, refresh)
        except ValueError as exc:
            raise ValueError(f'{month:%B %Y}: {exc} Completed months are saved; Retry saved progress to continue.') from None
        chunk_sources.append({'month': month.strftime('%Y-%m'), 'retrieved_at': retrieved_at})
        for row in batch:
            if start <= pd.Timestamp(row['period'], tz='UTC') <= end:
                rows.append(dict(row, retrieved_at=row.get('retrieved_at', retrieved_at)))
        if progress:
            progress((index + 1) / len(months))
    if not rows:
        raise ValueError('No observations in this date range. Try an earlier end date or different area.')
    frame = pd.DataFrame(rows)
    required = {'parent', 'subba'} if subregion else {'respondent', 'type'}
    if not (required | {'period', 'value', 'value-units'}).issubset(frame.columns):
        raise ValueError('EIA schema is incomplete; retrieval was not accepted.')
    if subregion:
        correct = frame['parent'].eq(parent) & frame['subba'].eq(subregion)
    else:
        correct = frame['respondent'].eq(parent) & frame['type'].eq('D')
    if not correct.all() or frame['period'].duplicated().any():
        raise ValueError('EIA returned conflicting entity or duplicate-hour records; retrieval quarantined.')
    if set(frame['value-units'].str.lower()) != {'megawatthours'}:
        raise ValueError('Unexpected EIA units; only hourly integrated megawatthours are supported.')
    frame['hour_end_utc'] = pd.to_datetime(frame['period'], utc=True, errors='raise')
    frame['raw_value'] = frame['value']
    frame['demand_mw'] = pd.to_numeric(frame['value'], errors='coerce')
    frame.loc[~np.isfinite(frame['demand_mw']) | (frame['demand_mw'] < 0), 'demand_mw'] = np.nan
    frame = frame.sort_values('hour_end_utc')
    retrieved = datetime.now(timezone.utc).isoformat()
    metadata = {'source_id': 'eia-930-demand', 'source_url': BASE + route,
                'documentation': ABOUT, 'parent': parent, 'subregion': subregion,
                'request_start_utc': start.isoformat(), 'request_end_utc': end.isoformat(),
                'retrieval_started_at': retrieved_start, 'retrieved_at': retrieved,
                'rows': len(frame), 'api_total': len(frame), 'month_sources': chunk_sources,
                'retrieval_method': 'Bounded UTC months without server sorting; local sort and disk cache; adaptive splitting on transient failures.',
                'raw_unit': 'megawatthours per one-hour interval',
                'first_hour_end_utc': frame['hour_end_utc'].min().isoformat(),
                'last_hour_end_utc': frame['hour_end_utc'].max().isoformat(),
                'invalid_or_missing_values': int(frame['demand_mw'].isna().sum()),
                'transformation': 'Hourly integrated MWh / 1h = mean MW; bucket by interval start (hour ending minus 1h).',
                'published_at': None, 'publication_note': 'Per-row publication timestamps not supplied by this endpoint.'}
    return frame, metadata


def import_saved_months(parent, subregion):
    """Seed incremental caches from CSV snapshots produced by earlier versions."""
    route, filters = query_for(parent, subregion)
    for source in EIA_FOLDER.glob('*.json'):
        meta = read_json(source, {})
        if meta.get('parent') != parent or meta.get('subregion') != subregion:
            continue
        try:
            frame = pd.read_csv(source.with_suffix('.csv'))
            if not {'period', 'value', 'value-units'}.issubset(frame):
                continue
            if subregion:
                correct = frame['parent'].eq(parent) & frame['subba'].eq(subregion)
            else:
                correct = frame['respondent'].eq(parent) & frame['type'].eq('D')
            frame = frame.loc[correct & frame['value-units'].str.lower().eq('megawatthours')].copy()
            if 'retrieved_at' not in frame:
                frame['retrieved_at'] = meta['retrieved_at']
            frame['_month'] = pd.to_datetime(frame['period'], utc=True).dt.strftime('%Y-%m-01')
            fields = ['period', 'value', 'value-units', 'retrieved_at'] + (['parent','subba'] if subregion else ['respondent','type'])
            for month_text, part in frame.groupby('_month'):
                month = pd.Timestamp(month_text, tz='UTC')
                identity = json.dumps([route, filters, month.isoformat()], sort_keys=True)
                path = CHUNK_CACHE / (hashlib.sha256(identity.encode()).hexdigest() + '.json')
                cached = read_json(path, {}) or {}
                rows = {row['period']: row for row in cached.get('rows', [])}
                changed = False
                for row in json.loads(part[fields].to_json(orient='records')):
                    prior = rows.get(row['period'])
                    if prior is None or str(row['retrieved_at']) > str(prior.get('retrieved_at', cached.get('retrieved_at', ''))):
                        rows[row['period']] = row
                        changed = True
                if changed:
                    CHUNK_CACHE.mkdir(parents=True, exist_ok=True)
                    if path.exists():
                        path.with_name(path.stem + '_' + uuid.uuid4().hex + '.snapshot.json').write_bytes(path.read_bytes())
                    from local_store import atomic_json
                    atomic_json(path, {'rows': sorted(rows.values(), key=lambda row: row['period']),
                        'retrieved_at': max(str(row.get('retrieved_at', meta['retrieved_at'])) for row in rows.values())})
        except (OSError, ValueError, KeyError):
            continue


def restore_history(parent, subregion, start, end):
    """Read completed snapshots and interrupted monthly downloads, with no HTTP."""
    frames, months = [], set()
    route, filters = query_for(parent, subregion)
    for month in month_starts(start + pd.Timedelta(hours=1), end):
        identity = json.dumps([route, filters, month.isoformat()], sort_keys=True)
        path = CHUNK_CACHE / (hashlib.sha256(identity.encode()).hexdigest() + '.json')
        payload = read_json(path)
        if payload and isinstance(payload.get('rows'), list):
            months.add(month.strftime('%Y-%m'))
            if payload['rows']:
                part = pd.DataFrame(payload['rows'])
                if 'retrieved_at' not in part:
                    part['retrieved_at'] = payload['retrieved_at']
                frames.append(part)
    # Backwards-compatible import of snapshots created before startup restore.
    for path in EIA_FOLDER.glob('*.json'):
        meta = read_json(path, {})
        if meta.get('parent') != parent or meta.get('subregion') != subregion:
            continue
        try:
            part = pd.read_csv(path.with_suffix('.csv'))
            if 'retrieved_at' not in part:
                part['retrieved_at'] = meta['retrieved_at']
            frames.append(part)
        except (OSError, ValueError, KeyError):
            continue
    if not frames:
        return None
    frame = pd.concat(frames, ignore_index=True)
    required = {'period', 'value', 'value-units', 'retrieved_at'}
    if not required.issubset(frame):
        return None
    correct = (frame.get('parent', pd.Series(index=frame.index, dtype=str)).eq(parent)
               & frame.get('subba', pd.Series(index=frame.index, dtype=str)).eq(subregion)) if subregion else (
                   frame.get('respondent', pd.Series(index=frame.index, dtype=str)).eq(parent)
                   & frame.get('type', pd.Series(index=frame.index, dtype=str)).eq('D'))
    frame['hour_end_utc'] = pd.to_datetime(frame['period'], utc=True, errors='coerce')
    frame = frame.loc[correct & frame['value-units'].str.lower().eq('megawatthours')
                      & frame['hour_end_utc'].gt(start) & frame['hour_end_utc'].le(end)].copy()
    if frame.empty:
        return None
    frame['raw_value'] = frame['value']
    frame['demand_mw'] = pd.to_numeric(frame['value'], errors='coerce')
    frame.loc[~np.isfinite(frame['demand_mw']) | frame['demand_mw'].lt(0), 'demand_mw'] = np.nan
    frame = frame.sort_values('retrieved_at').drop_duplicates('hour_end_utc', keep='last').sort_values('hour_end_utc')
    expected = int((end-start) / pd.Timedelta(hours=1))
    meta = {'source_id': 'eia-930-demand', 'source_url': BASE + route, 'documentation': ABOUT,
            'parent': parent, 'subregion': subregion, 'retrieved_at': str(frame['retrieved_at'].max()),
            'oldest_retrieval_at': str(frame['retrieved_at'].min()), 'rows': len(frame),
            'restored_from_disk': True, 'saved_months': len(months),
            'partial': int(frame['demand_mw'].notna().sum()) < expected,
            'request_start_utc': (start+pd.Timedelta(hours=1)).isoformat(), 'request_end_utc': end.isoformat(),
            'transformation': 'Hourly integrated MWh / 1h = mean MW; bucket by interval start (hour ending minus 1h).',
            'published_at': None}
    return frame, meta, start, end


def aggregate_history(frame, start, end, tz, frequency):
    """Calendar bins in selected timezone; expected hours include DST and missing hours."""
    # Full local calendar range; no forward-fill or fabricated zero demand.
    grid = pd.date_range(start, end, freq='h', inclusive='left')
    values = frame.set_index(frame['hour_end_utc'] - pd.Timedelta(hours=1))['demand_mw']
    local = values.reindex(grid).tz_convert(tz)
    if frequency == 'Hourly':
        return pd.DataFrame({'Period start': local.index,
                             'Average demand (MW)': local.values,
                             'Peak demand (MW)': local.values,
                             'Observed energy (MWh)': local.values,
                             'Complete-period energy (MWh)': local.values,
                             'Coverage (%)': np.where(local.notna(), 100.0, 0.0),
                             'Valid hours': local.notna().astype(int).values, 'Expected hours': 1})
    rule = {'Daily': 'D', 'Weekly': 'W-MON', 'Monthly': 'MS', 'Yearly': 'YS'}[frequency]
    grouped = local.resample(rule, label='left', closed='left')
    valid = grouped.count()
    energy = grouped.sum(min_count=1)
    expected = []
    for stamp in valid.index:
        if frequency == 'Daily':
            next_stamp = stamp + pd.DateOffset(days=1)
        elif frequency == 'Weekly':
            next_stamp = stamp + pd.DateOffset(weeks=1)
        elif frequency == 'Monthly':
            next_stamp = stamp + pd.offsets.MonthBegin(1)
        else:
            next_stamp = stamp + pd.offsets.YearBegin(1)
        expected.append(int((next_stamp.tz_convert('UTC') - stamp.tz_convert('UTC')) / pd.Timedelta(hours=1)))
    result = pd.DataFrame({'Average demand (MW)': grouped.mean(), 'Peak demand (MW)': grouped.max(),
                           'Observed energy (MWh)': energy, 'Valid hours': valid, 'Expected hours': expected})
    result['Coverage (%)'] = result['Valid hours'] / result['Expected hours'] * 100
    result['Complete-period energy (MWh)'] = energy.where(result['Valid hours'].eq(result['Expected hours']))
    return result.rename_axis('Period start').reset_index()


def focus_window(first_day, last_day, widget_key):
    """Two direct selectors instead of a separate zoom mode plus extra controls."""
    month_col, week_col = st.columns(2)
    with month_col:
        months = list(pd.period_range(first_day, last_day, freq='M'))
        month = remembered('selectbox', 'Month', [None] + months,
                            format_func=lambda value: 'All months in range' if value is None else value.strftime('%B %Y'),
                            key='month_v3_' + widget_key)
    lo = max(first_day, month.start_time.date()) if month is not None else first_day
    hi = min(last_day, month.end_time.date()) if month is not None else last_day
    monday = lo - timedelta(days=lo.weekday())
    weeks = [stamp.date() for stamp in pd.date_range(monday, hi, freq='W-MON')]
    def week_label(value):
        if value is None:
            return 'All weeks in range'
        a, b = max(lo, value), min(hi, value + timedelta(days=6))
        return f'{a:%d %b} – {b:%d %b %Y}'
    with week_col:
        week = remembered('selectbox', 'Week', [None] + weeks, format_func=week_label,
                            key='week_v3_' + widget_key + str(month))
    if week is not None:
        lo, hi = max(lo, week), min(hi, week + timedelta(days=6))
    return lo, hi, month is not None, week is not None


def demand_chart(view, measure, frequency):
    """Explicit series, units and partial-period labels for the demand explorer."""
    import altair as alt

    plot = view.copy()
    formats = {'Hourly':'%d %b %Y %H:%M %Z', 'Daily':'%d %b %Y',
               'Weekly':'%d %b %Y', 'Monthly':'%b %Y', 'Yearly':'%Y'}
    plot['Period'] = plot['Period start'].dt.strftime(formats[frequency])
    plot['Local period start'] = plot['Period start'].dt.strftime('%d %b %Y %H:%M %Z')
    plot['Average demand (GW)'] = plot['Average demand (MW)'] / 1000
    plot['Peak demand (GW)'] = plot['Peak demand (MW)'] / 1000
    plot['Recorded energy (GWh)'] = plot['Observed energy (MWh)'] / 1000
    plot['Period status'] = np.where(plot['Coverage (%)'].ge(100), 'Complete period', 'Partial period')
    x = alt.X('Period:N', sort=plot['Period'].tolist(),
              title='Week beginning' if frequency == 'Weekly' else 'Period',
              axis=alt.Axis(labelAngle=0, labelOverlap='greedy', labelLimit=110, ticks=False))
    tip = [alt.Tooltip('Local period start:N', title='Local time'),
           alt.Tooltip('Coverage (%):Q', format='.1f'),
           alt.Tooltip('Valid hours:Q'), alt.Tooltip('Expected hours:Q')]
    base = alt.Chart(plot)
    if measure == 'Energy':
        return base.mark_bar().encode(
            x=x, y=alt.Y('Recorded energy (GWh):Q', title='Recorded energy (GWh)'),
            color=alt.Color('Period status:N', title=None,
                            scale=alt.Scale(domain=['Complete period','Partial period'], range=['#2563eb','#cbd5e1'])),
            tooltip=[alt.Tooltip('Recorded energy (GWh):Q', format=',.2f'),
                     alt.Tooltip('Period status:N')] + tip,
        ).properties(height=330)
    return base.transform_fold(
        ['Average demand (GW)', 'Peak demand (GW)'], as_=['Series', 'Demand (GW)']
    ).mark_line(point=True, strokeWidth=2).encode(
        x=x, y=alt.Y('Demand (GW):Q', title='Electricity demand (GW)', scale=alt.Scale(zero=False)),
        color=alt.Color('Series:N', title=None,
                        scale=alt.Scale(domain=['Average demand (GW)','Peak demand (GW)'], range=['#2563eb','#94a3b8'])),
        tooltip=[alt.Tooltip('Series:N'), alt.Tooltip('Demand (GW):Q', format=',.2f')] + tip,
    ).properties(height=330)


@st.fragment
def render_electricity(key):
    st.subheader('Electricity history explorer')
    catalog = latest_snapshot('eia_catalog', 'areas') or [
        {'id': code, 'name': name} for code, name in [
            ('TVA','Tennessee Valley Authority'), ('PJM','PJM Interconnection'),
            ('ERCO','ERCOT'), ('MISO','Midcontinent ISO'), ('CISO','California ISO'),
            ('NYIS','New York ISO'), ('ISNE','ISO New England'), ('SWPP','Southwest Power Pool'),
            ('BPAT','Bonneville Power Administration')]]
    saved_parent = preference('widget:eia_area')
    if saved_parent and saved_parent not in {row['id'] for row in catalog}:
        catalog.append({'id': saved_parent, 'name': saved_parent})
    labels = {row['id']: f"{row['name']} ({row['id']})" for row in catalog}
    favorites = [code for code in ['TVA','PJM','ERCO','MISO','CISO','NYIS','ISNE','SWPP','BPAT'] if code in labels]
    codes = favorites + [row['id'] for row in catalog if row['id'] not in favorites]
    names, sub = {}, None

    with st.container(border=True):
        region_col, sub_col = st.columns(2)
        with region_col:
            parent = remembered('selectbox', 'Grid area', codes, format_func=labels.get, key='eia_area',
                                  help='An electricity operating area; its boundaries can cross state lines.')
        with sub_col:
            if parent in SUBREGION_PARENTS:
                names = {row['id']:row['name'] for row in (latest_snapshot('eia_catalog', parent) or [])}
                saved_sub = preference('widget:eia_sub_' + parent)
                if saved_sub and saved_sub not in names:
                    names[saved_sub] = saved_sub
                sub = remembered('selectbox', 'Local zone', [None]+list(names), key='eia_sub_'+parent,
                                    format_func=lambda value: 'Entire grid area' if value is None else names[value])
                if not names and st.button('Load local zones', disabled=not bool(key)):
                    try:
                        save_snapshot('eia_catalog', parent, subregions(key,parent))
                        st.rerun(scope='fragment')
                    except ValueError as exc:
                        st.error(str(exc))
            else:
                st.selectbox('Local zone', ['Entire grid area'], disabled=True,
                              help='EIA does not provide a finer demand zone for this grid area.')
        window_col, refresh_col, settings_col = st.columns([4,1,1], vertical_alignment='bottom')
        with window_col:
            range_labels = {'1M':'30 days','3M':'90 days','1Y':'1 year','5Y':'5 years','All':'All history','Custom':'Custom'}
            preset = remembered('segmented_control', 'Time window', list(range_labels), format_func=range_labels.get,
                                           default='1M', key='eia_range') or '1M'
        with refresh_col:
            refresh = st.button('Refresh', icon=':material/refresh:', width='stretch',
                                disabled=not bool(key), help='Fetch missing hours only. Saved observations remain available if the update fails.')
        with settings_col:
            with st.popover('Settings', width='stretch'):
                tz = remembered('selectbox', 'Calendar timezone', ['America/New_York','America/Chicago','America/Denver','America/Los_Angeles','UTC'], key='eia_timezone')
                st.caption('Weeks start Monday. Calendar boundaries follow this timezone.')
                if st.button('Update area list', disabled=not bool(key)):
                    try:
                        areas.clear()
                        save_snapshot('eia_catalog', 'areas', areas(key))
                        st.rerun(scope='fragment')
                    except ValueError as exc:
                        st.error(str(exc))
        today = datetime.now(timezone.utc).astimezone(ZoneInfo(tz)).date()
        if refresh:
            save_preference('eia_anchor_date', today.isoformat())
        end_date = date.fromisoformat(preference('eia_anchor_date', today.isoformat()))
        save_preference('eia_anchor_date', end_date.isoformat())
        start_date = end_date-timedelta(days={'1M':30,'3M':90,'1Y':365,'5Y':1826}.get(preset,30)-1)
        if preset == 'Custom':
            saved_dates = preference('eia_custom_dates', [start_date.isoformat(), end_date.isoformat()])
            dates = st.date_input('Choose dates', value=tuple(date.fromisoformat(value) for value in saved_dates), min_value=date(2015,1,1), max_value=today, key='eia_custom_dates')
            if len(dates) != 2:
                return
            start_date,end_date = dates
            save_preference('eia_custom_dates', [value.isoformat() for value in dates])

    signature = (parent,sub,preset,str(start_date),str(end_date),tz)
    views = st.session_state.setdefault('eia_views',{})
    failures = st.session_state.setdefault('eia_failures',{})
    lo = pd.Timestamp(start_date).tz_localize(tz).tz_convert('UTC')
    hi = pd.Timestamp(end_date+timedelta(days=1)).tz_localize(tz).tz_convert('UTC')
    if preset == 'All':
        lo = pd.Timestamp('2019-01-01', tz='UTC').tz_convert(tz).normalize().tz_convert('UTC')
    if signature not in views:
        restored = restore_history(parent, sub, lo, hi)
        if restored is not None:
            views[signature] = restored
    incomplete = signature not in views or views[signature][1].get('partial', False)
    resume = incomplete and st.button('Load missing history' if signature not in failures else 'Retry saved progress',
        key='eia_resume', disabled=not bool(key), help='Reuse saved months and download the unfinished range.')
    if refresh or resume:
        try:
            with st.spinner('Loading electricity history…'):
                if preset == 'All':
                    first,last = bounds(key,parent,sub,refresh=refresh)
                    lo = (first-pd.Timedelta(hours=1)).tz_convert(tz).normalize().tz_convert('UTC')
                    hi = ((last-pd.Timedelta(hours=1)).tz_convert(tz).normalize()+pd.DateOffset(days=1)).tz_convert('UTC')
                st.caption('History downloads one month at a time. Completed months are saved locally; the first full-history download can take several minutes.')
                progress = st.progress(0.0,text='Loading monthly batches…')
                try:
                    frame,meta = fetch_history(key,parent,sub,lo+pd.Timedelta(hours=1),hi,
                        lambda value: progress.progress(value,text=f'Loading monthly batches… {value:.0%}'),refresh=True)
                finally:
                    progress.empty()
                meta.update(calendar_timezone=tz,area_name=labels[parent],subregion_name=names.get(sub))
                folder = EIA_FOLDER
                folder.mkdir(parents=True,exist_ok=True)
                path = folder/f"{parent}_{sub or 'whole'}_{uuid.uuid4().hex}"
                frame.to_csv(str(path)+'.csv',index=False)
                Path(str(path)+'.json').write_text(json.dumps(meta,indent=2),encoding='utf-8')
                views[signature]=(frame,meta,lo,hi)
                failures.pop(signature,None)
                if len(views)>12:
                    views.pop(next(iter(views)))
        except (ValueError,OSError) as exc:
            failures[signature]=str(exc)
            # Newly completed months remain useful even when the next month fails.
            restored = restore_history(parent, sub, lo, hi)
            if restored is not None:
                views[signature] = restored
    if signature in failures:
        st.error(failures[signature])
        if signature not in views:
            st.caption('Use Retry saved progress to continue; saved hours will be reused.')
            return
        st.warning('Refresh failed. The previous snapshot is shown with its original timestamp.')
    if signature not in views:
        st.info('No saved electricity data for this selection. Click Load missing history for the first download.')
        if not key:
            st.caption('Add an EIA API key to download new data. Saved data can be viewed without a key.')
        return
    frame,meta,lo,hi = views[signature]
    if meta.get('restored_from_disk'):
        st.caption(f"Showing saved data · latest source retrieval {meta['retrieved_at']}. Updates run only when requested.")
    if meta.get('partial'):
        st.warning('Saved history is incomplete for the selected range. Available hours are shown below; missing hours remain blank. Use Load missing history to continue.')
    first_day=lo.tz_convert(tz).date()
    last_day=(hi.tz_convert(tz)-pd.Timedelta(seconds=1)).date()
    focus_start,focus_end,has_month,has_week = focus_window(first_day,last_day,str((parent,sub,preset,tz)))
    lo_focus=pd.Timestamp(focus_start).tz_localize(tz).tz_convert('UTC')
    hi_focus=pd.Timestamp(focus_end+timedelta(days=1)).tz_localize(tz).tz_convert('UTC')
    hourly=aggregate_history(frame,lo_focus,hi_focus,tz,'Hourly')
    valid=hourly['Average demand (MW)'].dropna()
    expected=int((hi_focus-lo_focus)/pd.Timedelta(hours=1))
    coverage=len(valid)/max(expected,1)
    title = names.get(sub) or labels[parent]
    st.markdown(f"**{title}**")
    st.caption(f"{focus_start:%d %b %Y} – {focus_end:%d %b %Y} · {tz}")
    avg_col,peak_col,energy_col,coverage_col = st.columns(4)
    avg_col.metric('Average load', f"{valid.mean()/1000:,.2f} GW" if len(valid) else 'Unavailable')
    peak_col.metric('Peak load', f"{valid.max()/1000:,.2f} GW" if len(valid) else 'Unavailable')
    energy_col.metric('Recorded energy', f"{valid.sum()/1000:,.1f} GWh" if len(valid) else 'Unavailable',
                      help='Energy from reported valid hours only; missing hours are excluded.')
    coverage_col.metric('Hours reported',f"{coverage:.1%}",help=f'{len(valid):,} valid hours out of {expected:,} calendar hours.')
    plot_col,summary_col=st.columns([2,1])
    with plot_col:
        measure=remembered('segmented_control', 'Chart', ['Demand','Energy'], default='Demand',key='eia_chart_v3') or 'Demand'
    default_frequency = 'Hourly' if has_week else 'Daily' if has_month or preset in ['1M','3M'] else 'Monthly'
    with summary_col:
        frequency=remembered('selectbox', 'Summarize by',['Hourly','Daily','Weekly','Monthly','Yearly'],
                               index=['Hourly','Daily','Weekly','Monthly','Yearly'].index(default_frequency),
                               key='eia_summary_'+preset+str(has_month)+str(has_week),
                               help='Changes chart granularity; does not download new data.')
    view=aggregate_history(frame,lo_focus,hi_focus,tz,frequency)
    if valid.empty:
        st.info('No valid hours have been reported for this selection.')
    else:
        st.markdown(f"**{frequency} {'average and peak demand' if measure=='Demand' else 'recorded electricity use'}**")
        import altair as alt
        with alt.data_transformers.disable_max_rows():
            st.altair_chart(demand_chart(view,measure,frequency),width='stretch',
                            alt=f'{frequency} {measure.lower()} with period coverage for the selected grid area')
    latest=frame['hour_end_utc'].max().tz_convert(tz)
    st.caption(f"Source: EIA-930 · Latest reported hour: {latest:%d %b %Y %H:%M %Z} · Loaded: {meta['retrieved_at']}")
    if coverage<1:
        st.caption('Some hours are not yet reported or are missing. Averages use available hours; energy is a partial total. Today and boundary weeks/months can be incomplete.')
    st.caption('Demand = average power required over reported intervals (GW). Energy = electricity used over time (GWh). 1 GW = 1,000 MW; weeks start Monday.')

    with st.expander('Period details and CSV download'):
        formatted=view.copy()
        formatted['Period start']=formatted['Period start'].dt.strftime('%d %b %Y %H:%M %Z')
        numeric=formatted.select_dtypes(include='number').columns
        formatted[numeric]=formatted[numeric].round(2)
        st.dataframe(formatted,hide_index=True,width='stretch')
        st.download_button('Download selected periods',view.to_csv(index=False),'electricity_periods.csv','text/csv')
        st.download_button('Download all loaded hours',frame.to_csv(index=False),'electricity_hourly.csv','text/csv')
    with st.expander('Source coverage and more detailed electricity resources'):
        st.markdown(f'[EIA-930 source and geographic definitions]({ABOUT})')
        st.caption('All history retrieves the full available API series. Earlier downloadable files, plant-level data and nodal prices require separate imports. Local zones are electricity reporting areas, not individual data centers.')
        st.markdown('- [EIA-860: generating assets and locations](https://www.eia.gov/electricity/data/eia860/)\n'
                    '- [EIA-923: monthly plant generation and fuel consumption](https://www.eia.gov/electricity/data/eia923/index.php)\n'
                    '- [PJM Data Miner: local load and market prices](https://www.pjm.com/markets-and-operations/etools/data-miner-2)')
        st.json(meta)
