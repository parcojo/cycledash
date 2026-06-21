# CycleDash

This project is **spec-driven**. The single source of truth is:

**[`gdp_cyclical_dashboard_spec.md`](./gdp_cyclical_dashboard_spec.md)** — read it before making changes.

## Working rules
- Treat the spec as authoritative for scope, architecture, and design decisions.
  If a request conflicts with the spec, flag it before implementing.
- Respect the v0 scope boundary: ship exactly one indicator (`gdp_cyclical`) with
  its three views. Don't add features beyond the extensibility seam (§3) unless
  the spec is updated first.
- When scope or design genuinely needs to change, update the spec in the same
  change so code and spec don't drift.
