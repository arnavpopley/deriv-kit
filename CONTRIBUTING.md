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
by all three. The `cpp` back end, with its default generator, must keep
reproducing the `python` numbers for the same seed
(`tests/test_monte_carlo_golden.py`).

The `cpp` back end has two generators, `rng="reproducible"` (the default) and
`rng="fast"`. The fast one is a different stream on purpose, so it is exempt
from the golden and same-stream tests by name (`SAME_STREAM_RNGS` in
`tests/conftest.py`) and has its own in `tests/test_fast_rng.py`. A new
generator has to be put in one group or the other before the tests pass.

To check the C++ for memory errors and undefined behaviour, build with the
sanitizers into a separate directory and load their run-time library ahead of
Python (the Linux form; `.github/workflows/ci.yml` has both compilers):

```bash
cmake -S . -B build-san -DCMAKE_BUILD_TYPE=RelWithDebInfo -DDERIVKIT_SANITIZE=ON
cmake --build build-san
LD_PRELOAD="$(g++ -print-file-name=libasan.so) $(g++ -print-file-name=libstdc++.so)" \
    ASAN_OPTIONS=detect_leaks=0 pytest
```

This replaces the extension next to the sources with a slow one, so rebuild the
ordinary `build` directory afterwards, and never benchmark a sanitizer build.

Timings in `benchmarks/RESULTS.md` are regenerated, never edited by hand:

```bash
python -m derivkit compare --paths 1e5 1e6 1e7 --vr all --budgets 0.1 1 10 \
    --report benchmarks/RESULTS.md --plot benchmarks/accuracy_vs_time.png
```

That command rewrites the whole file. The section on the fast generator at the
end of it comes from a second run and two C++ programs. The commands are listed
in that section and their output is pasted in unchanged, so after regenerating
the file, run those in the same session and put the section back.

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
