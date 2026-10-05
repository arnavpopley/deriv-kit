# Changelog

All notable changes to this project are documented here.

## Unreleased

- C++ back end: a second random number generator, chosen with `rng="fast"`
  (`european(spec, cfg, backend="cpp", rng="fast")`; `european_adaptive` and
  `arithmetic_asian` take it too). It is xoshiro256++ seeded through SplitMix64,
  with a 256-layer ziggurat sampler for the normal draw
- The default is still `rng="reproducible"` (mt19937_64 + Box-Muller). It is
  unchanged and still reproduces the pure-Python results for the same seed
- `rng="fast"` is repeatable for a seed, but it is a different stream: its
  prices agree with `python`, `numpy` and the reproducible generator within
  the standard error, not digit for digit. Asking for it on a back end other
  than `cpp` raises `ValueError`
- `derivkit.compare(..., backends=[..., "cpp/fast"])` and
  `python -m derivkit compare --backends ... cpp/fast` measure it beside the
  three back ends; the default comparison is unchanged
- `benchmarks/rng_speed.cpp` times the two generators on their own, and
  `benchmarks/where_time_goes.cpp` profiles the kernel with each
- Measured in one session (battery, Low Power Mode off; see
  `benchmarks/RESULTS.md`): normal draws on their own are 6.6 times faster with
  the fast generator, and the kernel runs 1.66 to 1.94 times faster, at 0.88 to
  0.91 times the speed of `numpy`. The largest remaining cost is `exp`, which
  this change leaves alone
- An extension built before this change is reported as out of date, with the
  command to rebuild it, instead of failing with an `AttributeError`
- CI builds the extension with GCC and Clang on Python 3.11, 3.12 and 3.13 with
  warnings as errors, and runs the suite again under AddressSanitizer and
  UndefinedBehaviorSanitizer on the same combinations

## 2.1.0 - 2026-10-05

- Monte Carlo back ends: `european`, `european_adaptive` and
  `arithmetic_asian` take `backend="python"` (default), `"numpy"` or `"cpp"`
- NumPy-vectorised back end (optional dependency)
- C++20 back end behind a pybind11 extension, built with CMake (optional);
  reproduces the pure-Python results for the same seed
- `derivkit.compare`, `derivkit.accuracy_per_second` and
  `python -m derivkit compare`: accuracy and speed of the back ends side by
  side, with measured results in `benchmarks/RESULTS.md`
- The pure-Python Monte Carlo loop computes its per-call constants once
  instead of once per path; results are unchanged
- CI builds the extension with GCC and Clang and tests all three back ends, and builds
  and installs a wheel
- CI also runs the core suite on Python 3.13
- Fixed: `pip install .` and wheel builds failed because the NIFTY fixture was added to
  the wheel twice

## 2.0.0 - 2026-09-16

Python 3.11 package. Numerical engines, tests, and the Groww example keep
the same formulas, residuals, and NSE clock as 1.x. Monte Carlo uses
mt19937_64 + Box-Muller.

- Black-76 on a forward, with an identity to Black-Scholes-Merton when
  `F = S e^{(r-q)T}` and `DF = e^{-rT}`
- Implied forward from put-call parity (weighted OLS on `C - P = DF (F - K)`)
- NSE F&O calendar: session snap to last close, Ganesh Chaturthi 2026-09-14,
  Muhurat 2026-11-08 counted as a trading day
- `groww_chain` prices with Black-76, `T_vol` = trading days / 252, `T_rate` =
  ACT/365.25, residuals in rupees and vol points

## 1.0.0 - 2026-09-12

First public release.

- Black-Scholes-Merton European vanillas, full first- and second-order Greeks
- Discrete geometric-average Asian (Kemna-Vorst) closed form
- Implied volatility: Newton on vega with a residual-controlled bisection fallback
- Binomial trees: Cox-Ross-Rubinstein, Jarrow-Rudd, Leisen-Reimer
- Trinomial trees: Kamrad-Ritchken
- American exercise on every lattice
- Richardson extrapolation and adaptive step doubling
- Monte Carlo with exact GBM sampling, antithetic variates, and control variates
- Arithmetic Asian Monte Carlo controlled by the geometric Asian
- Groww Trading API example: live NIFTY / BANKNIFTY / equity option chains
