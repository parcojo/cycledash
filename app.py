"""Streamlit entrypoint: pick an indicator from the registry, fetch, render."""
from __future__ import annotations

import pandas as pd
import streamlit as st

import charts
from fred_client import fetch
from indicators import REGISTRY
from indicators.gdp_cyclical import CYCLICAL, NONCYCLICAL, USREC

st.set_page_config(page_title="Macro Dashboard", layout="wide")


def _metric_row(tidy: pd.DataFrame) -> None:
    """Latest YoY value + last-quarter delta for the two main lines."""
    cols = st.columns(2)
    for col, label in zip(cols, (CYCLICAL, NONCYCLICAL)):
        g = tidy[tidy["series_label"] == label].sort_values("date")
        if g.empty:
            continue
        latest = g["value"].iloc[-1]
        delta = latest - g["value"].iloc[-2] if len(g) >= 2 else None
        as_of = pd.to_datetime(g["date"].iloc[-1]).strftime("%Y Q%q")
        col.metric(
            label=f"{label} YoY (as of {as_of})",
            value=f"{latest:.1f}%",
            delta=None if delta is None else f"{delta:+.1f} pp vs prior qtr",
        )


def main() -> None:
    st.title("Macro Dashboard")

    # Sidebar: indicator selector (single entry in v0) + optional start date.
    names = list(REGISTRY)
    choice = st.sidebar.selectbox(
        "Indicator", names, format_func=lambda n: REGISTRY[n].title
    )
    indicator = REGISTRY[choice]

    try:
        raw = fetch(indicator.series_ids)
    except RuntimeError as e:
        st.error(str(e))
        st.stop()

    tidy = indicator.transform(raw)

    # Default x-axis: full history (~1960) so past recessions are comparable.
    min_date = pd.to_datetime(tidy["date"]).min().date()
    max_date = pd.to_datetime(tidy["date"]).max().date()
    start = st.sidebar.date_input(
        "Chart start", value=min_date, min_value=min_date, max_value=max_date
    )

    st.subheader(indicator.title)
    st.caption(indicator.description)

    _metric_row(tidy)

    spans = charts.recession_spans(raw[USREC]) if USREC in raw.columns else []
    fig = charts.yoy_chart(tidy, spans, start=pd.Timestamp(start))
    st.plotly_chart(fig, use_container_width=True)

    st.caption(
        "Nominal (current-dollar) decomposition. Recession bands: NBER (USREC), "
        "which is dated retrospectively — it only shades *past* recessions. The "
        "live read comes from the cyclical line, not the shading."
    )


if __name__ == "__main__":
    main()
