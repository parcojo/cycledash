"""Reconciliation: catch wrong/renamed FRED series IDs via accounting identities.

Two layers:
  * test_identity_synthetic / test_share_and_growth_transforms_synthetic —
    offline, no key/network. Validate the derivation math and every view
    transform (share + growth) against a fabricated frame.
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
    CYCLICAL,
    CYCLICAL_SHARE,
    CYCLICAL_SHARE_ROC,
    DURABLES,
    EQUIPMENT,
    GCE,
    GDP,
    NETEXP,
    NONCYCLICAL,
    PCEDG,
    PNFI,
    PRFI,
    RESIDENTIAL,
    SERIES_IDS,
    compute_levels,
    transform_component_shares,
    transform_cyclical_share,
    transform_cyclical_share_roc,
    transform_growth,
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


def test_share_and_growth_transforms_synthetic() -> None:
    """Offline: the share + growth view transforms produce the expected columns
    and values (no key/network)."""
    raw = _synthetic_raw()
    lv = compute_levels(raw)

    # Cyclical share: single line, value == cyclical / GDP * 100.
    cs = transform_cyclical_share(raw).sort_values("date")
    assert set(cs["series_label"]) == {CYCLICAL_SHARE}
    share = lv["cyclical"] / lv[GDP] * 100.0
    assert np.allclose(cs["value"].to_numpy(), share.to_numpy())

    # Rate of change: YoY (4q) point change of the share; first 4 quarters drop.
    roc = transform_cyclical_share_roc(raw).sort_values("date")
    assert set(roc["series_label"]) == {CYCLICAL_SHARE_ROC}
    assert np.allclose(roc["value"].to_numpy(), share.diff(4).dropna().to_numpy())

    # Component shares: three lines; spot-check durables == PCEDG / GDP * 100.
    comp = transform_component_shares(raw)
    assert set(comp["series_label"]) == {DURABLES, EQUIPMENT, RESIDENTIAL}
    dg = comp[comp["series_label"] == DURABLES].sort_values("date")
    assert np.allclose(dg["value"].to_numpy(), (lv[PCEDG] / lv[GDP] * 100.0).to_numpy())

    # Growth: three lines (Core toggled in UI, always emitted here); first 4
    # quarters dropped by the 4-quarter YoY shift.
    g = transform_growth(raw)
    assert set(g["series_label"]) == {CYCLICAL, NONCYCLICAL, "Core GDP"}
    assert g["value"].notna().all()


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
