# Changelog

All notable changes to this project are documented here.

## 1.0.0 — 2026-09-12

First public release.

- Black–Scholes–Merton European vanillas, full first- and second-order Greeks
- Discrete geometric-average Asian (Kemna–Vorst) closed form
- Implied volatility: Newton on vega with a residual-controlled bisection fallback
- Binomial trees: Cox–Ross–Rubinstein, Jarrow–Rudd, Leisen–Reimer
- Trinomial trees: Kamrad–Ritchken
- American exercise on every lattice
- Richardson extrapolation and adaptive step doubling
- Monte Carlo with exact GBM sampling, antithetic variates, and control variates
- Arithmetic Asian Monte Carlo controlled by the geometric Asian
- Adaptive Monte Carlo that grows the path count until a standard-error tolerance is met
