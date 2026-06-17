# Macro Dashboard — GDP Cyclical Signal (v0)

A Streamlit dashboard that reconstructs the EPB "cyclical vs non-cyclical GDP"
framework from FRED data. It splits **nominal** GDP into cyclical demand
(durables + nonresidential equipment + residential investment, ~20% of GDP) and
the non-cyclical remainder (~80%), then plots year-over-year growth of each with
NBER recession shading. Cyclical demand drops sharply heading into recessions;
non-cyclical demand stays comparatively stable.

Inspiration: https://youtu.be/UDQkWg3DZbs

> **Methodology:** this reconstructs EPB's *approach*; exact line-item membership
> may differ slightly. Treat as a faithful approximation, not an exact replica.
> Nominal (current-dollar) only — nominal components are additive; real
> (chained-dollar) components are not, which is why the framework uses nominal.

## Get a FRED API key (free, instant)

1. Create / sign in to a free account: https://fredaccount.stlouisfed.org
2. Request a key: https://fredaccount.stlouisfed.org/apikeys (issued immediately).

## Run locally

```bash
python -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# Provide the key:
cp .streamlit/secrets.toml.example .streamlit/secrets.toml
# then edit .streamlit/secrets.toml and paste your key

streamlit run app.py                 # opens http://localhost:8501
```

## Tests

```bash
pytest -q
```

- `test_identity_synthetic` runs offline (no key/network) and validates the
  derivation math.
- The live tests (`test_reconciliation_*`, `test_smoke`) hit FRED and are
  **skipped automatically** unless a key is available. To run them:

```bash
export FRED_API_KEY=your_key_here    # or rely on .streamlit/secrets.toml
pytest -q
```

The reconciliation test asserts the GDP accounting identities hold for recent
quarters within 0.5% — it fails loudly if a FRED series ID was renamed.

## Deploy to Streamlit Community Cloud (free, phone-accessible)

1. Push this repo to a **public** GitHub repo (public is the zero-friction path
   and fine for public FRED data; private works but needs broader OAuth scope).
2. At https://share.streamlit.io, create an app pointing at this repo / `app.py`.
3. In the app's **Settings → Secrets**, paste:
   ```toml
   FRED_API_KEY = "your_key_here"
   ```
4. The public URL loads on your phone. The app sleeps after ~12h idle and wakes
   (~30s) on next visit — fine for quarterly check-ins.

## Adding an indicator later

The entire extension story (spec §3): add a module under `indicators/` that
builds an `Indicator(...)`, then append it to `REGISTRY` in
`indicators/__init__.py`. No plugin loader, no base classes, no config files.

## Layout

```
app.py                 # Streamlit entrypoint
fred_client.py         # cached FRED fetch
indicators/
  __init__.py          # Indicator dataclass + REGISTRY
  gdp_cyclical.py      # the v0 indicator (series IDs, derivations, transform)
charts.py              # plotly line chart + recession shading
tests/
  test_reconciliation.py
  test_smoke.py
```
