"""Local snapshots and view preferences. No credentials or network calls."""
import hashlib
import json
from pathlib import Path
from threading import RLock
import uuid

import streamlit as st

STORE = Path(__file__).parent / 'data' / 'saved'
LOCK = RLock()


def read_json(path, default=None):
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return default


def atomic_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.' + uuid.uuid4().hex + '.tmp')
    temporary.write_text(json.dumps(value, default=str, allow_nan=False), encoding='utf-8')
    temporary.replace(path)


def save_snapshot(kind, entity, payload):
    folder = STORE / kind / hashlib.sha256(entity.encode()).hexdigest()
    with LOCK:
        atomic_json(folder / (uuid.uuid4().hex + '.json'), payload)


def latest_snapshot(kind, entity):
    folder = STORE / kind / hashlib.sha256(entity.encode()).hexdigest()
    try:
        paths = sorted(folder.glob('*.json'), key=lambda path: path.stat().st_mtime_ns, reverse=True)
        for path in paths:
            value = read_json(path)
            if value is not None:
                return value
    except OSError:
        pass
    return None


def preference(key, default=None):
    return (read_json(STORE / 'preferences.json', {}) or {}).get(key, default)


def save_preference(key, value):
    value = json.loads(json.dumps(value, default=str))
    with LOCK:
        path = STORE / 'preferences.json'
        prefs = read_json(path, {}) or {}
        if key not in prefs or prefs[key] != value:
            prefs[key] = value
            atomic_json(path, prefs)


def remembered(widget, label, options, *, key, **kwargs):
    """Restore typed options (including dates/Periods) from plain JSON values."""
    encode = lambda value: json.loads(json.dumps(value, default=str))
    def match(value):
        return next((candidate for candidate in options if encode(candidate) == value), None)
    if key not in st.session_state:
        saved = preference('widget:' + key, {'unset': True})
        if widget == 'multiselect' and isinstance(saved, list):
            st.session_state[key] = [value for item in saved if (value := match(item)) is not None]
        elif any(encode(candidate) == saved for candidate in options):
            st.session_state[key] = match(saved)
    # Options can shrink after filtering or a failed company request.
    if key in st.session_state and widget != 'multiselect' and st.session_state[key] not in options:
        del st.session_state[key]
    if key in st.session_state:
        kwargs.pop('default', None)
        if widget == 'selectbox':
            kwargs['index'] = None
    def changed():
        save_preference('widget:' + key, st.session_state[key])
    value = getattr(st, widget)(label, options, key=key, on_change=changed, **kwargs)
    save_preference('widget:' + key, value)
    return value
