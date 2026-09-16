# Contributing

This is a small numerical library. Changes that land should preserve the
error-control contract: every numerical engine reports a diagnostic
(`PricingResult.error_estimate`) that a caller can actually check.

## Build the tests

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest
```

## Style

- Python 3.11+, four-space indent, 100-column wrap.
- Raise `ValueError` for contract violations; do not return NaN as a silent failure.
- New engines go through `PricingResult` so examples and tests stay uniform.

## Numerical changes

If you touch a formula, add a regression against a published or independently
computed reference (Haug, Hull, or a high-resolution run of an existing
engine). State the tolerance and why it is justified - 1 x 10^-12 for analytic
identities, a few standard errors for Monte Carlo, the observed truncation
order for trees.
