"""Reconciliation: catch wrong/renamed FRED series IDs via accounting identities.

Two layers:
  * test_identity_synthetic — offline, no key/network. Validates the derivation
    math against a fabricated frame.
  * test_reconciliation_live / test_core_additive_identity_live — hit FRED,
    skipped automatically when no FRED_API_KEY is available.

Note on the spec's stated check (Cyclical + NonCyclical + NETEXP + CBI ≈ GDP):
because non-cyclical is built as the residual (core - cyclical), that sum is
GDP by construction and would pass even if PCEDG/EQUIP/PRFI were wrong. We keep
it (it still catches NaN/missing GDP/NETEXP/CBI) AND add the stronger additive
identity GDP - NETEXP - CBI ≈ PCE + PNFI + PRFI + GCE, which genuinely catches
renamed PCE/PNFI/PRFI/GCE/NETEXP/CBI.
"""
from __future__ import annotations

import os

import numpy as np
import pandas as pd
import pytest

from indicators.gdp_cyclical import (
    CBI,
    GCE,
    GDP,
    NETEXP,
    PNFI,
    PRFI,
    SERIES_IDS,
    compute_levels,
)

TOL = 0.005  # 0.5%


def _has_key() -> bool:
    if os.environ.get("FRED_API_KEY"):
        return True
    try:
        import streamlit as st

        return bool(st.secrets["FRED_API_KEY"])
    except Exception:
        return False


needs_key = pytest.mark.skipif(not _has_key(), reason="no FRED_API_KEY available")


def _synthetic_raw() -> pd.DataFrame:
    """Fabricated wide frame satisfying the GDP accounting identity exactly:
    GDP = PCE + PNFI + PRFI + GCE + NETEXP + CBI."""
    idx = pd.date_range("2015-01-01", periods=12, freq="QS")
    rng = np.random.default_rng(0)
    pce = pd.Series(14000 + rng.normal(0, 100, len(idx)).cumsum(), index=idx)
    pnfi = pd.Series(2500 + rng.normal(0, 20, len(idx)).cumsum(), index=idx)
    prfi = pd.Series(700 + rng.normal(0, 10, len(idx)).cumsum(), index=idx)
    gce = pd.Series(3300 + rng.normal(0, 15, len(idx)).cumsum(), index=idx)
    netexp = pd.Series(-600 + rng.normal(0, 10, len(idx)).cumsum(), index=idx)
    cbi = pd.Series(rng.normal(50, 20, len(idx)), index=idx)
    pcedg = pce * 0.12
    equip = pnfi * 0.4
    gdp = pce + pnfi + prfi + gce + netexp + cbi
    return pd.DataFrame(
        {
            GDP: gdp, "PCE": pce, "PCEDG": pcedg, "Y033RC1Q027SBEA": equip,
            PRFI: prfi, PNFI: pnfi, CBI: cbi, NETEXP: netexp, GCE: gce,
        }
    )


def test_identity_synthetic() -> None:
    lv = compute_levels(_synthetic_raw())

    # Spec identity: cyclical + noncyclical + NETEXP + CBI == GDP.
    lhs = lv["cyclical"] + lv["noncyclical"] + lv[NETEXP] + lv[CBI]
    assert np.allclose(lhs, lv[GDP])

    # Stronger additive identity: core == PCE + PNFI + PRFI + GCE.
    rhs = lv["PCE"] + lv[PNFI] + lv[PRFI] + lv[GCE]
    assert np.allclose(lv["core"], rhs)


@needs_key
def test_reconciliation_live() -> None:
    from fred_client import fetch

    lv = compute_levels(fetch(SERIES_IDS)).dropna().tail(8)
    assert not lv.empty, "no overlapping quarters fetched"

    recon = lv["cyclical"] + lv["noncyclical"] + lv[NETEXP] + lv[CBI]
    rel_err = ((recon - lv[GDP]).abs() / lv[GDP].abs())
    assert (rel_err < TOL).all(), f"max rel err {rel_err.max():.4%} exceeds {TOL:.2%}"


@needs_key
def test_core_additive_identity_live() -> None:
    from fred_client import fetch

    lv = compute_levels(fetch(SERIES_IDS)).dropna().tail(8)
    rhs = lv["PCE"] + lv[PNFI] + lv[PRFI] + lv[GCE]
    rel_err = ((lv["core"] - rhs).abs() / lv["core"].abs())
    assert (rel_err < TOL).all(), (
        f"core != PCE+PNFI+PRFI+GCE (max rel err {rel_err.max():.4%}); "
        "a component series ID is likely wrong/renamed"
    )
