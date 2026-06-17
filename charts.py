"""Plotly helpers: YoY line chart + NBER recession shading."""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go

# Line styling. Cyclical/Non-Cyclical are the money lines; Core GDP is a faint
# dashed reference.
_STYLE = {
    "Cyclical": dict(color="#d62728", width=2.5),
    "Non-Cyclical": dict(color="#1f77b4", width=2.5),
    "Core GDP": dict(color="#7f7f7f", width=1.2, dash="dot"),
}


def recession_spans(usrec: pd.Series) -> list[tuple[pd.Timestamp, pd.Timestamp]]:
    """Monthly 0/1 NBER series -> list of (start, end) timestamps for runs of 1s."""
    s = usrec.dropna().astype(int).sort_index()
    spans: list[tuple[pd.Timestamp, pd.Timestamp]] = []
    start: pd.Timestamp | None = None
    for date, val in s.items():
        if val == 1 and start is None:
            start = date
        elif val == 0 and start is not None:
            spans.append((start, date))
            start = None
    if start is not None:  # recession still open at the end of the series
        spans.append((start, s.index[-1]))
    return spans


def yoy_chart(
    tidy: pd.DataFrame,
    spans: list[tuple[pd.Timestamp, pd.Timestamp]] | None = None,
    start: pd.Timestamp | None = None,
) -> go.Figure:
    """Tidy df [date, series_label, value] -> YoY line chart with recession bands."""
    data = tidy.copy()
    data["date"] = pd.to_datetime(data["date"])
    if start is not None:
        start = pd.Timestamp(start)
        data = data[data["date"] >= start]

    fig = go.Figure()

    # Fixed y-range with a little padding, so the "contraction zone" band below
    # reaches the bottom of the plot and stays put when the start date changes.
    y_range = None
    vals = data["value"]
    if not vals.empty:
        ymin, ymax = float(vals.min()), float(vals.max())
        pad = max((ymax - ymin) * 0.06, 0.5)
        y_range = [ymin - pad, ymax + pad]
        # Faint red band over the negative region = "in the red" / contraction.
        if y_range[0] < 0:
            fig.add_hrect(
                y0=y_range[0],
                y1=0,
                fillcolor="#d62728",
                opacity=0.06,
                line_width=0,
                layer="below",
            )

    # Recession bands first so lines render on top.
    for span_start, span_end in spans or []:
        if start is not None:
            if span_end < start:
                continue
            span_start = max(span_start, start)
        fig.add_vrect(
            x0=span_start,
            x1=span_end,
            fillcolor="gray",
            opacity=0.15,
            line_width=0,
            layer="below",
        )

    for label in ("Non-Cyclical", "Cyclical", "Core GDP"):
        g = data[data["series_label"] == label]
        if g.empty:
            continue
        fig.add_trace(
            go.Scatter(
                x=g["date"],
                y=g["value"],
                name=label,
                mode="lines",
                line=_STYLE.get(label, {}),
                hovertemplate=f"{label}: %{{y:.1f}}%<br>%{{x|%Y-Q%q}}<extra></extra>",
            )
        )

    # Light, thick baseline so it reads clearly on a dark theme and stands apart
    # from the faint gridlines.
    fig.add_hline(y=0, line_width=2.5, line_color="rgba(255,255,255,0.7)", layer="below")
    fig.update_layout(
        title=dict(
            text="Year-over-Year Growth: Cyclical vs Non-Cyclical GDP",
            y=0.97,
            yanchor="top",
        ),
        yaxis=dict(title="YoY % growth", range=y_range),
        xaxis_title=None,
        hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0),
        margin=dict(l=10, r=10, t=80, b=10),
        height=520,
    )
    return fig
