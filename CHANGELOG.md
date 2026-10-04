# Changelog

All notable changes to this project are documented here.

## Unreleased

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
- CI builds the extension with GCC and Clang and tests all three back ends

## 2.0.0 - 2026-09-16

Python 3.11 package. Numerical engines, tests, and the Groww example keep
the same formulas, residuals, and NSE clock as 1.x. Monte Carlo uses
mt19937_64 + Box-Muller.

## Unreleased (folded into 2.0.0)

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
