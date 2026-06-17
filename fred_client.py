"""Cached FRED fetch: list[series_id] -> wide DataFrame of raw levels.

Returns one column per series on a unioned datetime index (NaN where a series
has no observation for a given date). Per-indicator alignment/resampling is the
transform's job, not this layer's.
"""
from __future__ import annotations

import os

import pandas as pd
import streamlit as st
from fredapi import Fred


def _get_api_key() -> str:
    """Prefer Streamlit secrets (local + Community Cloud); fall back to env var
    so tests can run with `FRED_API_KEY=... pytest` and no secrets.toml."""
    try:
        key = st.secrets["FRED_API_KEY"]
        if key:
            return key
    except Exception:
        pass
    key = os.environ.get("FRED_API_KEY")
    if not key:
        raise RuntimeError(
            "FRED_API_KEY not found. Add it to .streamlit/secrets.toml "
            "(see secrets.toml.example) or export it as an environment variable."
        )
    return key


def fetch(series_ids: list[str]) -> pd.DataFrame:
    """Public entrypoint. Normalizes (sort + dedupe) so the cache key is
    order-independent, then delegates to the cached fetch."""
    return _fetch_cached(tuple(sorted(set(series_ids))))


@st.cache_data(ttl=86400)
def _fetch_cached(series_ids: tuple[str, ...]) -> pd.DataFrame:
    fred = Fred(api_key=_get_api_key())
    cols = {sid: fred.get_series(sid) for sid in series_ids}
    df = pd.DataFrame(cols)
    df.index = pd.to_datetime(df.index)
    df.index.name = "date"
    return df.sort_index()
