"""Streamlit entrypoint: pick an indicator + view from the registry, render it."""
from __future__ import annotations

import pandas as pd
import streamlit as st

import charts
from fred_client import fetch
from indicators import REGISTRY
from indicators.gdp_cyclical import CORE, USREC, transform_cyclical_share_roc

st.set_page_config(page_title="Macro Dashboard", layout="wide")

# Views whose latest share readings feed the persistent context strip.
_CONTEXT_KEYS = ("cyclical_share", "component_shares")


def _context_strip(tidy_by_key: dict[str, pd.DataFrame]) -> None:
    """Latest value + last-quarter delta for cyclical share and each component."""
    frames = [tidy_by_key[k] for k in _CONTEXT_KEYS if k in tidy_by_key]
    if not frames:
        return
    combined = pd.concat(frames, ignore_index=True)
    labels = list(dict.fromkeys(combined["series_label"]))  # preserve order
    for col, label in zip(st.columns(len(labels)), labels):
        g = combined[combined["series_label"] == label].sort_values("date")
        if g.empty:
            continue
        latest = g["value"].iloc[-1]
        delta = latest - g["value"].iloc[-2] if len(g) >= 2 else None
        ts = pd.to_datetime(g["date"].iloc[-1])  # %q is not a Python strftime code
        as_of = f"{ts.year} Q{ts.quarter}"
        col.metric(
            label=f"{label} — % of GDP ({as_of})",
            value=f"{latest:.1f}%",
            delta=None if delta is None else f"{delta:+.2f} pp vs prior qtr",
        )


def main() -> None:
    # Trim Streamlit's large default top padding (~6rem) above the title so the
    # context strip isn't pushed off-screen.
    st.markdown(
        "<style>.block-container{padding-top:1rem;}</style>",
        unsafe_allow_html=True,
    )
    st.title("Macro Dashboard")

    # Sidebar: indicator -> view -> chart start (-> Core GDP toggle for growth).
    choice = st.sidebar.selectbox(
        "Indicator", list(REGISTRY), format_func=lambda n: REGISTRY[n].title
    )
    indicator = REGISTRY[choice]

    view_keys = [v.key for v in indicator.views]
    view_titles = {v.key: v.title for v in indicator.views}
    view_key = st.sidebar.selectbox(
        "View", view_keys, format_func=lambda k: view_titles[k]
    )
    view = next(v for v in indicator.views if v.key == view_key)

    try:
        raw = fetch(indicator.series_ids)
    except RuntimeError as e:
        st.error(str(e))
        st.stop()

    # One cached fetch serves every view; transforms are trivial, so run all
    # three (the context strip needs the share views regardless of selection).
    tidy_by_key = {v.key: v.transform(raw) for v in indicator.views}

    # The share view also displays the rate-of-change strip; compute it now so
    # the default start accounts for it (and reuse it when rendering below).
    roc = transform_cyclical_share_roc(raw) if view_key == "cyclical_share" else None
    displayed = [tidy_by_key[view_key]] + ([roc] if roc is not None else [])

    # Default start = earliest quarter where ALL displayed signals have data, so
    # no line shows a ragged blank left edge (series begin at different dates, and
    # the rate-of-change strip loses its first 4 quarters to differencing).
    # min_value stays at the global earliest so the user can still zoom back.
    earliest = min(t["date"].min() for t in displayed).date()
    latest = max(t["date"].max() for t in displayed).date()
    default_start = max(
        t.groupby("series_label")["date"].min().max() for t in displayed
    ).date()
    start = st.sidebar.date_input(
        "Chart start",
        value=default_start,
        min_value=earliest,
        max_value=latest,
        key=f"start_{view_key}",  # per-view, so the default recomputes on switch
    )

    # Core GDP is a faint reference line, relevant only to the growth view.
    show_core = True
    if view_key == "growth":
        show_core = st.sidebar.checkbox("Show Core GDP reference", value=True)

    st.subheader(indicator.title)
    st.caption(indicator.description)

    tidy = tidy_by_key[view_key]
    if view_key == "growth" and not show_core:
        tidy = tidy[tidy["series_label"] != CORE]

    spans = charts.recession_spans(raw[USREC]) if USREC in raw.columns else []

    # The cyclical-share view shrinks 25% to make room for a rate-of-change strip
    # (~1/3 height) below it; total footprint stays ~the same.
    main_height = 315 if view_key == "cyclical_share" else 520
    fig = charts.line_chart(
        tidy, title=view.title, y_title=view.y_title, spans=spans,
        start=pd.Timestamp(start), height=main_height,
    )
    st.plotly_chart(fig, use_container_width=True)

    if view_key == "cyclical_share":
        roc_fig = charts.line_chart(
            roc, title="Rate of Change (YoY Δ, percentage points)",
            y_title="Δ pp", spans=spans, start=pd.Timestamp(start), height=200,
        )
        st.plotly_chart(roc_fig, use_container_width=True)

    st.markdown("**Latest readings**")
    _context_strip(tidy_by_key)

    st.caption(
        "Nominal (current-dollar) decomposition. Recession bands: NBER (USREC), "
        "dated retrospectively — they only shade *past* recessions. The live read "
        "comes from the cyclical share rolling over, not the shading."
    )


if __name__ == "__main__":
    main()
