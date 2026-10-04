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

## Monte Carlo back ends

The default `python` back end needs nothing beyond the standard library, and
the plain `pytest` run above must keep passing without NumPy or a compiler.
To work on the optional back ends:

```bash
pip install -e ".[dev,numpy,cpp]"
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release -DDERIVKIT_WERROR=ON
cmake --build build
DERIVKIT_REQUIRE_BACKENDS=numpy,cpp pytest
```

`DERIVKIT_REQUIRE_BACKENDS` turns a missing back end into a test failure
instead of a skip. A back end only runs the path loop; validation, the
control-variate estimate and result naming belong in `monte_carlo.py`, shared
by all three. The `cpp` back end must keep reproducing the `python` numbers
for the same seed (`tests/test_monte_carlo_golden.py`).

Timings in `benchmarks/RESULTS.md` are regenerated, never edited by hand:

```bash
python -m derivkit compare --paths 1e5 1e6 1e7 --vr all --budgets 0.1 1 10 \
    --report benchmarks/RESULTS.md --plot benchmarks/accuracy_vs_time.png
```

## Style

- Python 3.11+, four-space indent, 100-column wrap.
- C++20, standard library only (pybind11 for the binding), no `-ffast-math`.
- Raise `ValueError` for contract violations; do not return NaN as a silent failure.
- New engines go through `PricingResult` so examples and tests stay uniform.

## Numerical changes

If you touch a formula, add a regression against a published or independently
computed reference (Haug, Hull, or a high-resolution run of an existing
engine). State the tolerance and why it is justified - 1 x 10^-12 for analytic
identities, a few standard errors for Monte Carlo, the observed truncation
order for trees.
