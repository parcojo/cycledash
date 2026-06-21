"""GDP cyclical vs non-cyclical signal (the one v0 indicator).

Reconstructs EPB's *approach* to splitting GDP into cyclical and non-cyclical
demand. This is a faithful approximation of the framework, not an exact replica
of EPB's line-item membership.

Current-dollar (nominal) only, on purpose: nominal GDP components are additive,
so they can be summed and differenced. Chained-dollar (real) components are NOT
additive without BEA contribution series, which is why this framework uses
nominal. Real is out of scope for v0 (spec §4).
"""
from __future__ import annotations

import pandas as pd

from indicators import Indicator, View

# FRED series IDs (all quarterly, SAAR, billions of current $, except USREC).
GDP = "GDP"                       # Gross Domestic Product (nominal)
PCE = "PCE"                       # Personal Consumption Expenditures
PCEDG = "PCEDG"                   # PCE: durable goods                (cyclical)
EQUIP = "Y033RC1Q027SBEA"         # Nonresidential equipment invest.  (cyclical)
PRFI = "PRFI"                     # Private residential fixed invest. (cyclical)
PNFI = "PNFI"                     # Private nonresidential fixed invest.
CBI = "CBI"                       # Change in private inventories     (noise — stripped)
NETEXP = "NETEXP"                 # Net exports                       (noise — stripped)
GCE = "GCE"                       # Govt consumption + gross investment
USREC = "USREC"                   # NBER recession flag (0/1, monthly)

SERIES_IDS = [GDP, PCE, PCEDG, EQUIP, PRFI, PNFI, CBI, NETEXP, GCE, USREC]

# Economic (quarterly) series — everything except the monthly recession flag.
_ECON = [GDP, PCE, PCEDG, EQUIP, PRFI, PNFI, CBI, NETEXP, GCE]

# Series-label strings used in tidy output / chart legends / metric strip.
CYCLICAL = "Cyclical"
NONCYCLICAL = "Non-Cyclical"
CORE = "Core GDP"
CYCLICAL_SHARE = "Cyclical share"
CYCLICAL_SHARE_ROC = "Cyclical share Δ"
DURABLES = "Durable goods"
EQUIPMENT = "Business equipment"
RESIDENTIAL = "Residential"


def compute_levels(df: pd.DataFrame) -> pd.DataFrame:
    """Wide df of raw levels -> quarterly df of derived *levels* (billions $).

    Columns: core, cyclical, noncyclical, plus passthrough GDP/NETEXP/CBI/PCE/
    PNFI/PRFI/GCE used by the reconciliation test. Index = quarter-start.

    Derivations (spec §4):
        core        = GDP - NETEXP - CBI        (≡ PCE + PNFI + PRFI + GCE)
        cyclical    = PCEDG + EQUIP + PRFI
        noncyclical = core - cyclical           (residual — do NOT sum sub-series)
    """
    # Align quarterly economic series to quarter-start. They already arrive
    # quarterly from FRED; resample('QS') just guarantees the canonical index.
    econ = df[_ECON].resample("QS").mean().dropna(how="all")

    out = pd.DataFrame(index=econ.index)
    out.index.name = "date"
    out["core"] = econ[GDP] - econ[NETEXP] - econ[CBI]
    out["cyclical"] = econ[PCEDG] + econ[EQUIP] + econ[PRFI]
    out["noncyclical"] = out["core"] - out["cyclical"]

    # Passthrough levels: GDP/NETEXP/CBI/PCE/PNFI/PRFI/GCE for the reconciliation
    # test's accounting identities; PCEDG/EQUIP for the component-share view.
    for col in (GDP, NETEXP, CBI, PCE, PNFI, PRFI, GCE, PCEDG, EQUIP):
        out[col] = econ[col]
    return out


def _yoy(s: pd.Series) -> pd.Series:
    """Year-over-year (4-quarter) percent growth."""
    return s.pct_change(4, fill_method=None) * 100.0


def _tidy(wide: pd.DataFrame) -> pd.DataFrame:
    """Wide df (index=date, one col per line) -> tidy [date, series_label, value]."""
    return (
        wide.reset_index()
        .melt(id_vars="date", var_name="series_label", value_name="value")
        .dropna(subset=["value"])
        .sort_values(["series_label", "date"])
        .reset_index(drop=True)
    )


def transform_cyclical_share(df: pd.DataFrame) -> pd.DataFrame:
    """Primary view: cyclical demand as a share of total GDP (%)."""
    lv = compute_levels(df)
    return _tidy(pd.DataFrame({CYCLICAL_SHARE: lv["cyclical"] / lv[GDP] * 100.0}))


def transform_cyclical_share_roc(df: pd.DataFrame) -> pd.DataFrame:
    """Companion strip under the cyclical-share view: YoY (4-quarter) point change
    of the share, in percentage points. Zero-crossing = the share rolling over.

    Using the 4-quarter change rather than quarter-over-quarter is an inherent
    smoother: a 4-quarter moving average of the QoQ change telescopes exactly to
    Δ₄/4, so the two are the same signal up to scale — no separate MA needed.
    """
    lv = compute_levels(df)
    share = lv["cyclical"] / lv[GDP] * 100.0
    return _tidy(pd.DataFrame({CYCLICAL_SHARE_ROC: share.diff(4)}))


def transform_component_shares(df: pd.DataFrame) -> pd.DataFrame:
    """Diagnostic view: each cyclical component as a share of GDP (%)."""
    lv = compute_levels(df)
    return _tidy(
        pd.DataFrame(
            {
                DURABLES: lv[PCEDG] / lv[GDP] * 100.0,
                EQUIPMENT: lv[EQUIP] / lv[GDP] * 100.0,
                RESIDENTIAL: lv[PRFI] / lv[GDP] * 100.0,
            }
        )
    )


def transform_growth(df: pd.DataFrame) -> pd.DataFrame:
    """Context view: YoY growth of Cyclical, Non-Cyclical, and Core GDP.

    Always emits all three lines; the UI toggles Core GDP's visibility (it's a
    faint reference). Cyclical turns down hard into recessions; non-cyclical
    stays comparatively stable.
    """
    lv = compute_levels(df)
    return _tidy(
        pd.DataFrame(
            {
                CYCLICAL: _yoy(lv["cyclical"]),
                NONCYCLICAL: _yoy(lv["noncyclical"]),
                CORE: _yoy(lv["core"]),
            }
        )
    )


indicator = Indicator(
    name="gdp_cyclical",
    title="GDP (Cyclical vs Non-Cyclical)",
    description=(
        "Splits nominal GDP into cyclical demand (durables + equipment + "
        "residential investment, ~20%) and the non-cyclical remainder (~80%).  \n"
        "Cyclical share rolling over is the earliest tell; components show which "
        "sector drives it; growth mirrors the 'consumer is fine until it isn't' contrast."
    ),
    series_ids=SERIES_IDS,
    views=[
        View("cyclical_share", "Cyclical Share of GDP", "% of GDP", transform_cyclical_share),
        View("component_shares", "Cyclical Components", "% of GDP", transform_component_shares),
        View("growth", "Cyclical vs Non-Cyclical Growth (YoY)", "YoY % growth", transform_growth),
    ],
)
