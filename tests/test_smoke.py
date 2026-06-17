"""Smoke test (live FRED): fetch is non-empty for all series, transform yields
the expected columns with no NaNs in the plotted range.

Skipped automatically when no FRED_API_KEY is available.
"""
from __future__ import annotations

import os

import pytest

from indicators.gdp_cyclical import SERIES_IDS, indicator


def _has_key() -> bool:
    if os.environ.get("FRED_API_KEY"):
        return True
    try:
        import streamlit as st

        return bool(st.secrets["FRED_API_KEY"])
    except Exception:
        return False


needs_key = pytest.mark.skipif(not _has_key(), reason="no FRED_API_KEY available")


@needs_key
def test_fetch_non_empty() -> None:
    from fred_client import fetch

    raw = fetch(SERIES_IDS)
    assert not raw.empty
    for sid in SERIES_IDS:
        assert sid in raw.columns, f"missing column {sid}"
        assert raw[sid].notna().any(), f"series {sid} is entirely NaN"


@needs_key
def test_transform_columns_and_no_nans() -> None:
    from fred_client import fetch

    tidy = indicator.transform(fetch(SERIES_IDS))
    assert list(tidy.columns) == ["date", "series_label", "value"]
    assert set(tidy["series_label"]) == {"Cyclical", "Non-Cyclical", "Core GDP"}
    # dropna in transform guarantees no NaN in the plotted range.
    assert tidy["value"].notna().all()
    assert not tidy.empty
