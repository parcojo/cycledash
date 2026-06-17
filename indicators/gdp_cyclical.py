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

from indicators import Indicator

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

CYCLICAL = "Cyclical"
NONCYCLICAL = "Non-Cyclical"
CORE = "Core GDP"


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

    # Passthrough levels for the reconciliation test's accounting identities.
    for col in (GDP, NETEXP, CBI, PCE, PNFI, PRFI, GCE):
        out[col] = econ[col]
    return out


def _yoy(s: pd.Series) -> pd.Series:
    """Year-over-year (4-quarter) percent growth."""
    return s.pct_change(4, fill_method=None) * 100.0


def transform(df: pd.DataFrame) -> pd.DataFrame:
    """Wide df of raw levels -> tidy df [date, series_label, value] of YoY %.

    Emits three lines: Cyclical, Non-Cyclical, and Core GDP (faint reference).
    """
    levels = compute_levels(df)
    yoy = pd.DataFrame(
        {
            CYCLICAL: _yoy(levels["cyclical"]),
            NONCYCLICAL: _yoy(levels["noncyclical"]),
            CORE: _yoy(levels["core"]),
        }
    )
    tidy = (
        yoy.reset_index()
        .melt(id_vars="date", var_name="series_label", value_name="value")
        .dropna(subset=["value"])
        .sort_values(["series_label", "date"])
        .reset_index(drop=True)
    )
    return tidy


indicator = Indicator(
    name="gdp_cyclical",
    title="GDP — Cyclical vs Non-Cyclical",
    description=(
        "Splits nominal GDP into cyclical demand (durables + equipment + "
        "residential investment, ~20%) and the non-cyclical remainder (~80%), "
        "then plots year-over-year growth of each. Cyclical demand turns down "
        "hard going into recessions; non-cyclical stays comparatively stable."
    ),
    series_ids=SERIES_IDS,
    transform=transform,
)
