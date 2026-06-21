"""Plotly helpers: generic line chart + NBER recession shading.

One `line_chart` serves all views (shares and growth) — they're all line charts
with recession bands. Per-series color/width lives in `_STYLE`, keyed by the
series_label the transforms emit.
"""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go

_STYLE = {
    # Growth view
    "Cyclical": dict(color="#d62728", width=2.5),
    "Non-Cyclical": dict(color="#1f77b4", width=2.5),
    "Core GDP": dict(color="#7f7f7f", width=1.2, dash="dot"),
    # Cyclical-share view (single line, ties to the cyclical red)
    "Cyclical share": dict(color="#d62728", width=2.5),
    "Cyclical share Δ": dict(color="#d62728", width=2.0),
    # Component-shares view
    "Durable goods": dict(color="#ff7f0e", width=2.2),
    "Business equipment": dict(color="#2ca02c", width=2.2),
    "Residential": dict(color="#1f77b4", width=2.2),
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


def line_chart(
    tidy: pd.DataFrame,
    title: str,
    y_title: str,
    spans: list[tuple[pd.Timestamp, pd.Timestamp]] | None = None,
    start: pd.Timestamp | None = None,
    height: int = 520,
) -> go.Figure:
    """Tidy df [date, series_label, value] -> line chart with recession bands.

    The contraction band + white zero-baseline are drawn only when the data
    actually goes negative (gated on raw min < 0, so always-positive share views
    render clean and a sliver of padding can't trigger a spurious band).

    `height < 260` switches to a compact layout (tighter top margin, smaller
    title) for the short companion strips. The legend is hidden for single-line
    charts, where the title already names the series.
    """
    compact = height < 260
    data = tidy.copy()
    data["date"] = pd.to_datetime(data["date"])
    if start is not None:
        start = pd.Timestamp(start)
        data = data[data["date"] >= start]

    fig = go.Figure()

    # Fixed y-range with a little padding so the contraction band reaches the
    # bottom and stays put when the start date changes.
    y_range = None
    has_negative = False
    vals = data["value"]
    if not vals.empty:
        ymin, ymax = float(vals.min()), float(vals.max())
        pad = max((ymax - ymin) * 0.06, 0.5)
        y_range = [ymin - pad, ymax + pad]
        has_negative = ymin < 0
        if has_negative:
            # Faint red band over the negative region = "in the red" / contraction.
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

    for label in sorted(data["series_label"].unique()):
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

    if has_negative:
        # Light, thick baseline: reads clearly on dark theme, stands apart from
        # the faint gridlines, sits behind the data lines.
        fig.add_hline(
            y=0, line_width=2.5, line_color="rgba(255,255,255,0.7)", layer="below"
        )

    fig.update_layout(
        title=dict(
            text=title,
            y=0.99 if compact else 0.97,
            yanchor="top",
            font=dict(size=14) if compact else None,
        ),
        yaxis=dict(title=y_title, range=y_range),
        xaxis_title=None,
        hovermode="x unified",
        showlegend=data["series_label"].nunique() > 1,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0),
        margin=dict(l=10, r=10, t=46 if compact else 80, b=10),
        height=height,
    )
    return fig
