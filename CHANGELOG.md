# Changelog

All notable changes to this project are documented here.

## Unreleased

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
- Groww Trading API example: live NIFTY / BANKNIFTY / equity option chains priced
  with Black-Scholes, Leisen-Reimer, and optional Monte Carlo, with a bundled
  fixture when no API token is set
