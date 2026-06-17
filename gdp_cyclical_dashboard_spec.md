# Macro Dashboard — v0 Spec (GDP Cyclical Signal)

## 1. Goal & Scope
Build a Streamlit web dashboard that reconstructs the EPB "cyclical vs non-cyclical GDP" framework from FRED data, deployed free on Streamlit Community Cloud so I can check the business-cycle signal each quarter from any device.

If you need it, here is the video link that inspired the idea: https://youtu.be/UDQkWg3DZbs?si=VKyMolrMlET7zcTY

**v0 ships exactly one indicator** (`gdp_cyclical`). The codebase is structured so adding future indicators = one config entry + one transform function. **No speculative features beyond that seam.**

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
app.py                  # Streamlit entrypoint: pick indicator from registry, render
fred_client.py          # cached FRED fetch: list[series_id] -> tidy DataFrame
indicators/
  __init__.py           # REGISTRY: dict[name -> Indicator]
  gdp_cyclical.py        # the one v0 indicator
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

**Indicator contract** (each indicator implements this; registry maps name -> instance):
```python
@dataclass
class Indicator:
    name: str                 # "gdp_cyclical"
    title: str                # display title
    description: str          # short blurb shown in UI
    series_ids: list[str]     # FRED series to fetch
    transform: Callable[[pd.DataFrame], pd.DataFrame]
        # input: wide df of raw levels (index=quarter, cols=series_ids)
        # output: tidy df ready to plot (e.g. cols: date, series_label, value)
```
Adding an indicator later = new module + append to `REGISTRY`. That's the whole extension story. Do not build a plugin loader, base classes beyond this dataclass, or config files.

## 4. Data Spec (the core logic — current dollars / nominal only)

### Series to fetch (FRED IDs, quarterly, SAAR, billions $)
| Role | Series ID | Description |
|---|---|---|
| GDP | `GDP` | Gross Domestic Product (nominal) |
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
> Dropped `GPDI` (Gross Private Domestic Investment): it's the headline investment aggregate from the standard identity `GDP = PCE + GPDI + GCE + NETEXP`, but `GPDI = PNFI + PRFI + CBI`. This framework works one level below the aggregate (PRFI as cyclical, CBI stripped, PNFI in the additive check), so the GPDI parent is redundant and unused.

### Derivations
- **Core GDP** = `GDP − NETEXP − CBI`  (≡ `PCE + PNFI + PRFI + GCE`)
- **Cyclical (≈20%)** = `PCEDG + Y033RC1Q027SBEA + PRFI`
- **Non-cyclical (≈80%)** = `Core GDP − Cyclical`  *(derive as residual; do NOT sum many sub-series)*
- **Plotted metric:** year-over-year % growth (4-quarter) of Cyclical and Non-cyclical.

### Why nominal only
Current-dollar components are additive; chained-dollar (real) components are **not** — they cannot be summed without contribution series. The framework uses nominal precisely to avoid this. Real is explicitly out of scope for v0.

### Methodology note (put in code comment)
This reconstructs EPB's *approach*; their exact line-item membership may differ slightly. Treat as a faithful approximation, not an exact replica.

## 5. UI / Charts
- Sidebar: indicator selector (single entry in v0), optional date-range start.
- Main panel for `gdp_cyclical`:
  1. **Primary chart:** YoY % growth of Cyclical vs Non-cyclical, two lines, recession bands shaded from `USREC`. This is the money chart (mirrors the video's −9%/+6% comparison).
  2. **Context:** latest values + last-quarter delta for each line (simple metric row).
  3. (Optional) Core GDP YoY as a faint reference line.
- Recession shading: convert `USREC` runs of 1s into start/end spans, draw as Plotly vrects.
- Resample/align everything to quarter-start; forward-fill `USREC` to quarterly.

## 6. Caching
- `fred_client.fetch(series_ids)` wrapped in `st.cache_data(ttl=86400)` (data is quarterly; daily refresh is plenty).
- Cache key = sorted series_ids.

## 7. Tests / Definition of Done
- `test_reconciliation.py`: for the latest N quarters, assert the GDP accounting identities hold within tolerance (0.5%). Two checks:
  - **Spec identity:** `Cyclical + NonCyclical + NETEXP + CBI ≈ GDP`. Note this is tautological once `NonCyclical` is built as the residual (`Core − Cyclical`), so it only catches a broken/missing `GDP`/`NETEXP`/`CBI`, not a renamed cyclical component.
  - **Stronger additive identity:** `GDP − NETEXP − CBI ≈ PCE + PNFI + PRFI + GCE`. This genuinely validates the component IDs (`PCE`/`PNFI`/`PRFI`/`GCE`) — fails loudly if one is renamed.
  - Also `test_identity_synthetic`: runs the derivation math against a fabricated frame **offline** (no key/network), so the logic is testable without FRED.
- `test_smoke.py`: fetch returns non-empty frames for all series; transform yields the expected columns with no NaNs in the plotted range.
- Live tests (anything hitting FRED) **skip automatically** when no `FRED_API_KEY` is available, so `pytest` is green offline; they run when a key is present via secrets or env var.
- **Done when:** runs locally via `streamlit run` *and* is deployed on Community Cloud at a public URL that loads on your phone; primary chart renders with recession shading; both tests pass; deps pinned; README documents the FRED key + local-run + deploy steps.

## 8. Open decisions (confirm/adjust before build)
1. ~~Deploy target~~ — RESOLVED: Streamlit Community Cloud (free, public repo, phone-accessible).
2. History window: default x-axis start for the YoY chart. **Full history (~1960)** best serves the framework's "compare to past recessions" step; **2000+** is cleaner/less busy. Recommend default full, user-zoomable.
3. Recession source: `USREC` (NBER) lags in real time — NBER dates recessions retrospectively, so it only ever shades *past* recessions, never lights up live. Correct for historical shading; the live read comes from the cyclical line, not this. OK as-is.

## 9. Explicit non-goals (guard against scope creep)
No real-dollar mode, no extra indicators, no alerting/email, no persistence layer, no auth, no custom theming, no Docker/devcontainer. Ship the one chart, deployed on Community Cloud, tested.
