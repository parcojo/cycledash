"""Indicator registry.

The Indicator dataclass IS the whole extension contract. Adding an indicator
later = new module under indicators/ + one line appended to REGISTRY below.
No plugin loader, no base-class hierarchy, no config files (see spec §3).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import pandas as pd


@dataclass(frozen=True)
class View:
    key: str                                       # "cyclical_share"
    title: str                                     # chart title shown in UI
    y_title: str                                   # y-axis label, e.g. "% of GDP"
    transform: Callable[[pd.DataFrame], pd.DataFrame]
    # transform input:  wide df of raw levels (index=date, cols=series_ids)
    # transform output: tidy df with columns [date, series_label, value]


@dataclass(frozen=True)
class Indicator:
    name: str                                      # registry key, e.g. "gdp_cyclical"
    title: str                                     # display title
    description: str                               # short blurb shown in UI
    series_ids: list[str]                          # FRED series to fetch (once, shared across views)
    views: list[View]                              # rendered one at a time via the sidebar selector


# Defined above the import so gdp_cyclical can `from indicators import Indicator`
# without a circular-import failure.
from indicators.gdp_cyclical import indicator as _gdp_cyclical  # noqa: E402

REGISTRY: dict[str, Indicator] = {_gdp_cyclical.name: _gdp_cyclical}
