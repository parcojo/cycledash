# Macro Dashboard — v0 Spec (GDP Cyclical Signal)

## 1. Goal & Scope
Build a Streamlit web dashboard that reconstructs the EPB "cyclical vs non-cyclical GDP" framework from FRED data, deployed free on Streamlit Community Cloud so I can check the business-cycle signal each quarter from any device.

If you need it, here is the video link that inspired the idea: https://youtu.be/UDQkWg3DZbs?si=VKyMolrMlET7zcTY
Supporting article (adds the share + component views): https://blog.epbresearch.com/p/the-20-of-the-economy-that-drives

**v0 ships exactly one indicator** (`gdp_cyclical`), which renders **three views off a single data fetch** (see §5): cyclical share, component shares, and growth. The codebase is structured so adding future indicators = one module + one registry entry. **No speculative features beyond that seam.**

Out of scope for v0: real (chained-dollar) decomposition, multiple indicators, auth, databases, alerts, backtesting.

## 2. Stack & Deployment
- **Language/UI:** Python 3.11+, Streamlit, Plotly. No Docker/devcontainer — not needed.
- **Data:** FRED via `fredapi`. Free API key via `st.secrets["FRED_API_KEY"]` (never hardcoded/committed).
- **Local dev:** plain venv + `pip install -r requirements.txt`, then `streamlit run app.py` → `localhost:8501`. Key lives in gitignored `.streamlit/secrets.toml`.
- **Deploy:** Streamlit Community Cloud (free). Push to a **public** GitHub repo, link it in Community Cloud, paste `FRED_API_KEY` into the app's Secrets. Public URL = phone access. (Private repo also works but needs a broader GitHub OAuth scope; public is the zero-friction path and fine for public FRED data.)
- **Behavior to expect:** app sleeps after 12h of no traffic and wakes (~30s) on visit — irrelevant for quarterly check-ins.
- **Reproducibility:** pin all deps incl. `streamlit` in `requirements.txt` (Community Cloud auto-upgrades unpinned Streamlit).

## 3. Architecture (the extensibility seam — keep it thin)
```
app.py                  # Streamlit entrypoint: pick indicator + view from registry, render the selected view
fred_client.py          # cached FRED fetch: list[series_id] -> tidy DataFrame
indicators/
  __init__.py           # REGISTRY: dict[name -> Indicator]
  gdp_cyclical.py        # the one v0 indicator (3 views)
charts.py               # plotly helpers (line + recession shading)
tests/
  test_reconciliation.py
  test_smoke.py
.streamlit/
  secrets.toml          # gitignored; FRED_API_KEY for local dev
.gitignore              # ignores .streamlit/secrets.toml
requirements.txt        # pin everything incl. streamlit
README.md
```

**Indicator contract** (each indicator fetches one set of series, then renders an ordered list of views):
```python
@dataclass
class View:
    key: str                  # "cyclical_share"
    title: str                # chart title shown in UI
    y_title: str              # y-axis label, e.g. "% of GDP" or "YoY % growth"
    transform: Callable[[pd.DataFrame], pd.DataFrame]
        # input: wide df of raw levels (index=quarter, cols=series_ids)
        # output: tidy df ready to plot (cols: date, series_label, value)
    # all v0 views are line charts with recession shading; no chart-kind field yet
    # (y_title is display metadata the view owns — not a chart-kind discriminator)

@dataclass
class Indicator:
    name: str                 # "gdp_cyclical"
    title: str                # display title
    description: str          # short blurb shown in UI
    series_ids: list[str]     # FRED series to fetch (once, shared across views)
    views: list[View]         # rendered top-to-bottom in THIS order
```
Adding an indicator later = new module + append to `REGISTRY`. Adding a view to an existing indicator = append a `View`. That's the whole extension story. Do not build a plugin loader, a chart-kind registry, or base classes beyond these two dataclasses until a second indicator actually needs them.

## 4. Data Spec (the core logic — current dollars / nominal only)

### Series to fetch (FRED IDs, quarterly, SAAR, billions $)
| Role | Series ID | Description |
|---|---|---|
| GDP | `GDP` | Gross Domestic Product (nominal) — share denominator |
| PCE | `PCE` | Personal Consumption Expenditures |
| PCE durables | `PCEDG` | Durable goods consumption *(cyclical)* |
| Nonres equipment | `Y033RC1Q027SBEA` | Nonresidential equipment investment *(cyclical)* — VERIFIED |
| Residential inv | `PRFI` | Private Residential Fixed Investment *(cyclical)* |
| Nonres fixed inv | `PNFI` | Private Nonresidential Fixed Investment |
| Δ inventories | `CBI` | Change in Private Inventories (noise — strip) |
| Net exports | `NETEXP` | Net Exports (noise — strip) |
| Government | `GCE` | Govt Consumption + Gross Investment |
| Recession flag | `USREC` | NBER recession indicator (0/1, monthly) |

> Note: `PCEDG` and `PRFI` are standard but verify on first run; the reconciliation test (below) will fail loudly if any ID is wrong.
>
> No new series were needed to add the share/component views — every chart is built from series already in this table. Shares are just `component ÷ GDP`.
>
> Dropped `GPDI` (Gross Private Domestic Investment): it's the headline investment aggregate from the standard identity `GDP = PCE + GPDI + GCE + NETEXP`, but `GPDI = PNFI + PRFI + CBI`. This framework works one level below the aggregate (PRFI as cyclical, CBI stripped, PNFI in the additive check), so the GPDI parent is redundant and unused.

### Derivations
- **Core GDP** = `GDP − NETEXP − CBI`  (≡ `PCE + PNFI + PRFI + GCE`)
- **Cyclical (≈20%)** = `PCEDG + Y033RC1Q027SBEA + PRFI`
- **Non-cyclical (≈80%)** = `Core GDP − Cyclical`  *(derive as residual; do NOT sum many sub-series)*
- **Cyclical share** = `Cyclical / GDP × 100`  *(denominator is total GDP, per the article)*
- **Component shares** = each of `PCEDG`, `Y033RC1Q027SBEA`, `PRFI` `/ GDP × 100`
- **Growth** = year-over-year % change (4-quarter) of Cyclical and Non-cyclical levels

Each view in §5 is one of these derivations; all share the single fetched frame.

### Why nominal only
Current-dollar components are additive; chained-dollar (real) components are **not** — they cannot be summed without contribution series. The framework uses nominal precisely to avoid this. Real is explicitly out of scope for v0.

### Methodology note (put in code comment)
This reconstructs EPB's *approach*; their exact line-item membership may differ slightly. Treat as a faithful approximation, not an exact replica.

## 5. UI / Charts
- **Sidebar**, in order: indicator selector (single entry in v0) → **view selector** (the three views below) → date-range start (applies to the shown chart; **defaults to the earliest quarter where every displayed line has data** — series begin at different dates and the rate-of-change strip loses its first 4 quarters to differencing — so there's no ragged blank left edge. `min_value` stays at the global earliest, so the user can still zoom back). One view is shown at a time at full size — no vertical shrinking. (A view dropdown beats stacking all three or a multipage app: same "one chart per screen" feel, preserves aspect ratio, and keeps the single cached fetch trivially shared.)
- The three selectable views for `gdp_cyclical`:
  1. **Cyclical share of GDP** *(primary — the leading indicator)*: single line, `Cyclical / GDP × 100`, recession shading. When this share rolls over, rate-sensitive demand is slowing — the earliest tell. Beneath it (≈⅓ height; the share chart shrinks ~25% so total footprint is unchanged) a **rate-of-change strip**: the YoY (4-quarter) point change of the share, in pp, with the zero-baseline/contraction band — its zero-crossing makes the rollover explicit. Uses the 4q change rather than QoQ because a 4q MA of the QoQ change telescopes to Δ₄/4 (same signal, inherently smoothed) — no separate moving-average needed.
  2. **Component shares**: three lines — durable goods (orange), business equipment (green), residential (blue), each as `% of GDP`, recession shading. Diagnostic: shows *which* cyclical sector is driving (e.g. equipment carrying the others on AI capex).
  3. **Cyclical vs Non-cyclical growth** *(context)*: two lines, YoY % growth, recession shading. Mirrors the video's −9%/+6% framing; the "consumer is fine until it isn't" contrast. A faint **Core GDP** reference line is toggleable via a checkbox (default on), shown only when this view is selected.
- **Context strip** (below the chart): latest value + last-quarter delta for cyclical share and each component (4 metrics). Persists regardless of which view is selected — computing all three transforms per render is trivial off the one cached fetch.
- **Contraction band / zero baseline:** the faint red below-zero band and white zero-baseline draw only when the data actually goes negative (gated on raw `min < 0`, not the padded axis range — avoids a spurious sliver for views that hug just above zero). So the growth view gets them; the always-positive share views render clean. If a future view ever needs a zero reference without negatives (or vice versa), promote it to an explicit `View` flag then — not before.
- Recession shading: convert `USREC` runs of 1s into start/end spans, draw as Plotly vrects (shared helper across all views).
- Resample/align everything to quarter-start; forward-fill `USREC` to quarterly.

## 6. Caching
- `fred_client.fetch(series_ids)` wrapped in `st.cache_data(ttl=86400)` (data is quarterly; daily refresh is plenty).
- Cache key = sorted series_ids. One fetch serves all three views.

## 7. Tests / Definition of Done
- `test_reconciliation.py`: for the latest N quarters, assert the GDP accounting identities hold within tolerance (0.5%). Two checks:
  - **Spec identity:** `Cyclical + NonCyclical + NETEXP + CBI ≈ GDP`. Note this is tautological once `NonCyclical` is built as the residual (`Core − Cyclical`), so it only catches a broken/missing `GDP`/`NETEXP`/`CBI`, not a renamed cyclical component.
  - **Stronger additive identity:** `GDP − NETEXP − CBI ≈ PCE + PNFI + PRFI + GCE`. This genuinely validates the component IDs (`PCE`/`PNFI`/`PRFI`/`GCE`) — fails loudly if one is renamed.
  - Also `test_identity_synthetic`: runs the derivation math (including the share and growth transforms) against a fabricated frame **offline** (no key/network), so the logic is testable without FRED.
- `test_smoke.py`: fetch returns non-empty frames for all series; each view's transform yields the expected columns with no NaNs in the plotted range.
- Live tests (anything hitting FRED) **skip automatically** when no `FRED_API_KEY` is available, so `pytest` is green offline; they run when a key is present via secrets or env var.
- **Done when:** runs locally via `streamlit run` *and* is deployed on Community Cloud at a public URL that loads on your phone; all three views render with recession shading; tests pass; deps pinned; README documents the FRED key + local-run + deploy steps.

## 8. Open decisions (confirm/adjust before build)
1. ~~Deploy target~~ — RESOLVED: Streamlit Community Cloud (free, public repo, phone-accessible).
2. ~~View order~~ — RESOLVED: a sidebar view selector lists cyclical share (primary, default) → component shares → growth (context); one shown at a time.
3. ~~History window~~ — RESOLVED: default x-axis start = the earliest quarter where every displayed signal has data (data-availability bound, not a fixed year), keeping past recessions in view without a ragged left edge; user can zoom back to the global earliest or forward.
4. Recession source: `USREC` (NBER) lags in real time — NBER dates recessions retrospectively, so it only ever shades *past* recessions, never lights up live. Correct for historical shading; the live read comes from the cyclical share, not this. OK as-is.

## 9. Explicit non-goals (guard against scope creep)
No real-dollar mode, no extra indicators, no alerting/email, no persistence layer, no auth, no custom theming, no Docker/devcontainer. Ship the three views of the one indicator, deployed on Community Cloud, tested.

> Theming carve-out: one CSS rule trims Streamlit's oversized default top padding (`.block-container{padding-top:2rem}`) so the title sits near the top and the context strip fits on screen. Layout fix, not styling — the "no custom theming" line still holds for colors/fonts/etc.

## 10. Backlog — labor-market indicators (post-v0, not in scope yet)
The GDP indicator reads rate-sensitive *demand* but is blind to the labor market — exactly the dimension NBER weighs most, and the channel that turns a demand air-pocket into an official recession. Two future indicators would fill that gap. Each is a new module + one `REGISTRY` entry (the existing seam).

**Unlock gate — start the labor work only once all three hold:**
1. Deployed to Community Cloud, public URL verified on phone. — ✅ live as of 2026-06-21.
2. Used through ≥1 real quarterly check-in, or a few days' soak: mobile layout readable, sleep/wake + data-refresh behave. — *in progress.*
3. No known open bugs. — ✅ currently.

Rationale: the deploy environment is the least-tested surface, and adding a second indicator before the first is proven in the wild is the "premature expansion" failure mode. Real usage also settles an open design choice below (YoY-growth vs share form for the labor split).

### 10.1 `labor_sahm` — Sahm Rule recession trigger
- **Why:** a pure labor signal *and* a near-real-time recession trigger, so it also patches the `USREC`-lags-in-real-time weakness (decision 8.4).
- **Rule:** recession has historically begun once the 3-month average unemployment rate rises **≥ 0.5 pp** above its lowest 3-month average of the prior 12 months.
- **Series:** `UNRATE` (monthly U-3). Optionally also fetch FRED's prebuilt `SAHMCURRENT` purely to validate the computed series in a reconciliation test (parallel to the GDP identity tests).
- **Transform:**
  ```
  u3_3mo    = UNRATE.rolling(3).mean()
  trail_min = u3_3mo.rolling(12).min().shift(1)   # lowest prior 12mo, excl. current
  sahm      = u3_3mo - trail_min                   # plot; trigger hline at 0.5
  ```
- **View:** single line + a `0.5` threshold hline (reuse the existing hline/recession-band machinery). New wrinkle vs v0: it's **monthly**, so the quarter-start resample assumption needs a per-indicator override.

### 10.2 `labor_cyclical` — cyclical vs non-cyclical *employment* (EPB labor split) — PLACEHOLDER
- **Why:** the labor-side analogue of the GDP framework — split payroll employment into cycle-sensitive vs defensive industries and compare YoY growth, same as the GDP growth view. Cyclical employment rolls over before defensive.
- **Exact line-item membership TBD** — confirm against the EPB video before building; treat the construction below as a faithful approximation, same caveat as the GDP indicator.
- **Obvious construction to start from** (CES industry payrolls, monthly SA, FRED):
  - *Cyclical:* construction `USCONS` + manufacturing `MANEMP` + temporary-help `TEMPHELPS` (the most rate/cycle-sensitive; temp help leads). Candidate add: trade/transport-warehousing.
  - *Non-cyclical / defensive:* education & health `USEHS` + government `USGOVT` (candidate add: utilities).
  - Plot YoY % growth of each bucket with recession shading — mirrors the GDP growth view.
- **Open:** whether to express as YoY growth (matches GDP view) or as share-of-total-payrolls (matches the cyclical-share view); decide when building.