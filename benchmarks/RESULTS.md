# Monte Carlo back-end comparison

Every number in this file was measured on the machine described below by the command shown. Nothing is estimated or carried over from another machine.

## How this was produced

```bash
python -m derivkit compare --paths 1e5 1e6 1e7 --vr all --budgets 0.1 1 10 --report benchmarks/RESULTS.md --plot benchmarks/accuracy_vs_time.png
```

Run finished 2026-10-04 22:23 BST. The environment below was recorded when the run started.

| Item | Value |
| --- | --- |
| CPU | Apple M5 (10 logical cores, arm64) |
| OS | macOS-27.0.1-arm64-arm-64bit-Mach-O |
| Python | CPython 3.13.13 (Clang 19.1.7) |
| NumPy | 2.5.3 (generator PCG64, BLAS accelerate) |
| C++ compiler | Apple clang 21.0.0 (clang-2100.1.1.101) |
| C++ build | Release, flags `-O3 -DNDEBUG -std=c++20 -ffp-contract=off`, pybind11 3.1.0 |
| Power | battery, Low Power Mode on |
| derivkit | 2.0.0 (commit 61f073a) |

## What was priced

European call, S = 100, K = 100, r = 5.00%, q = 0.00%, vol = 20.00%, T = 1. Black-Scholes closed form = 10.450583572186.

## Method

- Every back end is called through the same public function, `derivkit.monte_carlo.european(spec, cfg, backend=...)`, with the same option, seed, path count and variance-reduction setting.
- python and cpp use the same generator (mt19937_64 + Box-Muller), so with one seed they produce the same price. numpy uses its own generator (PCG64), so its price differs within the standard error.
- Single thread. BLAS and OpenMP were pinned to one thread before NumPy was imported. The CPU / wall column is process CPU time divided by wall time: 1.00 means one busy thread.
- Timer: `time.perf_counter()` around the call. Garbage collection is left on.
- Abs. error vs BS is the error of that one run. It is a single draw from a distribution whose width is the standard error, so the standard error is the steadier measure of accuracy.
- Fixed path counts: 1 untimed warm-up run, then 7 timed runs; the table shows the median, minimum and maximum. Paths / s is paths divided by the median.
- Time budgets: the paths-per-second rate is measured first (1 warm-up, then the median of 7 runs, shown in the calibration table). Each budget is then one run of rate x budget paths; the table shows the time that run really took.

## Accuracy per second (the main result)

![Standard error against time budget](accuracy_vs_time.png)

**Standard error reached in a fixed time** (smaller is better)

| Variance reduction | Time budget | python | numpy | cpp |
| --- | --- | ---: | ---: | ---: |
| No variance reduction | 0.1 s | 5.87 x 10^-2 | 5.02 x 10^-3 | 7.32 x 10^-3 |
| No variance reduction | 1 s | 1.85 x 10^-2 | 1.59 x 10^-3 | 2.32 x 10^-3 |
| No variance reduction | 10 s | 5.87 x 10^-3 | 5.02 x 10^-4 | 7.32 x 10^-4 |
| Antithetic | 0.1 s | 3.10 x 10^-2 | 2.93 x 10^-3 | 4.03 x 10^-3 |
| Antithetic | 1 s | 9.80 x 10^-3 | 9.25 x 10^-4 | 1.27 x 10^-3 |
| Antithetic | 10 s | 3.10 x 10^-3 | 2.93 x 10^-4 | 4.03 x 10^-4 |
| Control variate | 0.1 s | 2.25 x 10^-2 | 1.91 x 10^-3 | 2.79 x 10^-3 |
| Control variate | 1 s | 7.09 x 10^-3 | 6.05 x 10^-4 | 8.82 x 10^-4 |
| Control variate | 10 s | 2.24 x 10^-3 | 1.91 x 10^-4 | 2.79 x 10^-4 |
| Antithetic + control variate | 0.1 s | 8.39 x 10^-3 | 7.74 x 10^-4 | 1.07 x 10^-3 |
| Antithetic + control variate | 1 s | 2.62 x 10^-3 | 2.45 x 10^-4 | 3.37 x 10^-4 |
| Antithetic + control variate | 10 s | 8.27 x 10^-4 | 7.74 x 10^-5 | 1.06 x 10^-4 |

**Detail of each budget run**

| Variance reduction | Time budget | Back end | Paths | Measured time (s) | Price | Std. error | Abs. error vs BS |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: |
| No variance reduction | 0.1 s | python | 62,995 | 0.1017 | 10.412257 | 5.87 x 10^-2 | 3.83 x 10^-2 |
| No variance reduction | 0.1 s | numpy | 8,613,520 | 0.09989 | 10.455337 | 5.02 x 10^-3 | 4.75 x 10^-3 |
| No variance reduction | 0.1 s | cpp | 4,039,782 | 0.09977 | 10.451177 | 7.32 x 10^-3 | 5.93 x 10^-4 |
| No variance reduction | 1 s | python | 629,952 | 1.007 | 10.441908 | 1.85 x 10^-2 | 8.68 x 10^-3 |
| No variance reduction | 1 s | numpy | 86,135,209 | 0.9983 | 10.452254 | 1.59 x 10^-3 | 1.67 x 10^-3 |
| No variance reduction | 1 s | cpp | 40,397,820 | 1.001 | 10.446760 | 2.32 x 10^-3 | 3.82 x 10^-3 |
| No variance reduction | 10 s | python | 6,299,527 | 9.919 | 10.454535 | 5.87 x 10^-3 | 3.95 x 10^-3 |
| No variance reduction | 10 s | numpy | 861,352,093 | 9.982 | 10.450510 | 5.02 x 10^-4 | 7.34 x 10^-5 |
| No variance reduction | 10 s | cpp | 403,978,204 | 10.01 | 10.449696 | 7.32 x 10^-4 | 8.87 x 10^-4 |
| Antithetic | 0.1 s | python | 56,413 | 0.1013 | 10.401623 | 3.10 x 10^-2 | 4.90 x 10^-2 |
| Antithetic | 0.1 s | numpy | 6,318,333 | 0.1001 | 10.445998 | 2.93 x 10^-3 | 4.59 x 10^-3 |
| Antithetic | 0.1 s | cpp | 3,330,337 | 0.09962 | 10.449060 | 4.03 x 10^-3 | 1.52 x 10^-3 |
| Antithetic | 1 s | python | 564,132 | 0.996 | 10.453937 | 9.80 x 10^-3 | 3.35 x 10^-3 |
| Antithetic | 1 s | numpy | 63,183,336 | 1.001 | 10.450411 | 9.25 x 10^-4 | 1.72 x 10^-4 |
| Antithetic | 1 s | cpp | 33,303,376 | 0.9967 | 10.450877 | 1.27 x 10^-3 | 2.94 x 10^-4 |
| Antithetic | 10 s | python | 5,641,323 | 10.13 | 10.449242 | 3.10 x 10^-3 | 1.34 x 10^-3 |
| Antithetic | 10 s | numpy | 631,833,360 | 9.999 | 10.450834 | 2.93 x 10^-4 | 2.50 x 10^-4 |
| Antithetic | 10 s | cpp | 333,033,769 | 9.968 | 10.450676 | 4.03 x 10^-4 | 9.28 x 10^-5 |
| Control variate | 0.1 s | python | 62,559 | 0.1006 | 10.423432 | 2.25 x 10^-2 | 2.72 x 10^-2 |
| Control variate | 0.1 s | numpy | 8,612,514 | 0.09988 | 10.447197 | 1.91 x 10^-3 | 3.39 x 10^-3 |
| Control variate | 0.1 s | cpp | 4,048,441 | 0.09998 | 10.448218 | 2.79 x 10^-3 | 2.37 x 10^-3 |
| Control variate | 1 s | python | 625,590 | 1.002 | 10.447822 | 7.09 x 10^-3 | 2.76 x 10^-3 |
| Control variate | 1 s | numpy | 86,125,143 | 0.9986 | 10.450661 | 6.05 x 10^-4 | 7.70 x 10^-5 |
| Control variate | 1 s | cpp | 40,484,419 | 1 | 10.450992 | 8.82 x 10^-4 | 4.08 x 10^-4 |
| Control variate | 10 s | python | 6,255,900 | 9.923 | 10.449588 | 2.24 x 10^-3 | 9.96 x 10^-4 |
| Control variate | 10 s | numpy | 861,251,437 | 9.986 | 10.450727 | 1.91 x 10^-4 | 1.44 x 10^-4 |
| Control variate | 10 s | cpp | 404,844,195 | 10.02 | 10.450590 | 2.79 x 10^-4 | 6.62 x 10^-6 |
| Antithetic + control variate | 0.1 s | python | 55,337 | 0.1001 | 10.433109 | 8.39 x 10^-3 | 1.75 x 10^-2 |
| Antithetic + control variate | 0.1 s | numpy | 6,314,150 | 0.1 | 10.449176 | 7.74 x 10^-4 | 1.41 x 10^-3 |
| Antithetic + control variate | 0.1 s | cpp | 3,334,340 | 0.09998 | 10.448682 | 1.07 x 10^-3 | 1.90 x 10^-3 |
| Antithetic + control variate | 1 s | python | 553,376 | 0.9972 | 10.449029 | 2.62 x 10^-3 | 1.55 x 10^-3 |
| Antithetic + control variate | 1 s | numpy | 63,141,508 | 0.9999 | 10.450316 | 2.45 x 10^-4 | 2.67 x 10^-4 |
| Antithetic + control variate | 1 s | cpp | 33,343,402 | 0.998 | 10.450247 | 3.37 x 10^-4 | 3.37 x 10^-4 |
| Antithetic + control variate | 10 s | python | 5,533,764 | 9.913 | 10.449138 | 8.27 x 10^-4 | 1.45 x 10^-3 |
| Antithetic + control variate | 10 s | numpy | 631,415,089 | 9.995 | 10.450552 | 7.74 x 10^-5 | 3.11 x 10^-5 |
| Antithetic + control variate | 10 s | cpp | 333,434,020 | 9.987 | 10.450508 | 1.06 x 10^-4 | 7.55 x 10^-5 |

**Calibration behind the budgets**

| Variance reduction | Back end | Calibration paths | Run time, median (s) | min (s) | max (s) | Paths / s |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| No variance reduction | python | 126,347 | 0.2006 | 0.1983 | 0.2115 | 0.63 M |
| No variance reduction | numpy | 7,712,701 | 0.08954 | 0.08934 | 0.08968 | 86.14 M |
| No variance reduction | cpp | 7,265,580 | 0.1799 | 0.1794 | 0.1803 | 40.40 M |
| Antithetic | python | 111,482 | 0.1976 | 0.1968 | 0.1991 | 0.56 M |
| Antithetic | numpy | 6,875,321 | 0.1088 | 0.1087 | 0.109 | 63.18 M |
| Antithetic | cpp | 5,896,800 | 0.1771 | 0.1765 | 0.1788 | 33.30 M |
| Control variate | python | 125,854 | 0.2012 | 0.2003 | 0.2026 | 0.63 M |
| Control variate | numpy | 8,231,163 | 0.09557 | 0.09522 | 0.09642 | 86.13 M |
| Control variate | cpp | 6,676,871 | 0.1649 | 0.1649 | 0.1652 | 40.48 M |
| Antithetic + control variate | python | 107,996 | 0.1952 | 0.1941 | 0.1965 | 0.55 M |
| Antithetic + control variate | numpy | 6,933,406 | 0.1098 | 0.1097 | 0.1101 | 63.14 M |
| Antithetic + control variate | cpp | 5,895,722 | 0.1768 | 0.1763 | 0.1772 | 33.34 M |

## Fixed path counts

**No variance reduction**

| Back end | Paths | Price | Std. error | Abs. error vs BS | Run time, median (s) | min (s) | max (s) | Paths / s | CPU / wall |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| python | 100,000 | 10.386439 | 4.64 x 10^-2 | 6.41 x 10^-2 | 0.1613 | 0.1591 | 0.1636 | 0.62 M | 1.00 |
| numpy | 100,000 | 10.357758 | 4.64 x 10^-2 | 9.28 x 10^-2 | 0.001209 | 0.001192 | 0.001237 | 82.70 M | 1.00 |
| cpp | 100,000 | 10.386439 | 4.64 x 10^-2 | 6.41 x 10^-2 | 0.002398 | 0.002352 | 0.002562 | 41.70 M | 1.00 |
| python | 1,000,000 | 10.448058 | 1.47 x 10^-2 | 2.53 x 10^-3 | 1.6 | 1.59 | 1.609 | 0.63 M | 1.00 |
| numpy | 1,000,000 | 10.427599 | 1.47 x 10^-2 | 2.30 x 10^-2 | 0.01171 | 0.01166 | 0.01217 | 85.40 M | 1.00 |
| cpp | 1,000,000 | 10.448058 | 1.47 x 10^-2 | 2.53 x 10^-3 | 0.0249 | 0.02485 | 0.02527 | 40.17 M | 1.00 |
| python | 10,000,000 | 10.454013 | 4.66 x 10^-3 | 3.43 x 10^-3 | 15.97 | 15.88 | 16.06 | 0.63 M | 1.00 |
| numpy | 10,000,000 | 10.455593 | 4.66 x 10^-3 | 5.01 x 10^-3 | 0.1174 | 0.1165 | 0.1237 | 85.19 M | 1.00 |
| cpp | 10,000,000 | 10.454013 | 4.66 x 10^-3 | 3.43 x 10^-3 | 0.2505 | 0.2501 | 0.2514 | 39.91 M | 1.00 |

**Antithetic**

| Back end | Paths | Price | Std. error | Abs. error vs BS | Run time, median (s) | min (s) | max (s) | Paths / s | CPU / wall |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| python | 100,000 | 10.424722 | 2.33 x 10^-2 | 2.59 x 10^-2 | 0.1817 | 0.1812 | 0.1853 | 0.55 M | 1.00 |
| numpy | 100,000 | 10.412200 | 2.32 x 10^-2 | 3.84 x 10^-2 | 0.001623 | 0.001616 | 0.001639 | 61.62 M | 1.00 |
| cpp | 100,000 | 10.424722 | 2.33 x 10^-2 | 2.59 x 10^-2 | 0.002925 | 0.002873 | 0.00297 | 34.19 M | 1.00 |
| python | 1,000,000 | 10.457104 | 7.36 x 10^-3 | 6.52 x 10^-3 | 1.811 | 1.806 | 1.83 | 0.55 M | 1.00 |
| numpy | 1,000,000 | 10.429434 | 7.35 x 10^-3 | 2.11 x 10^-2 | 0.01593 | 0.01589 | 0.01644 | 62.78 M | 1.00 |
| cpp | 1,000,000 | 10.457104 | 7.36 x 10^-3 | 6.52 x 10^-3 | 0.03009 | 0.02987 | 0.03026 | 33.24 M | 1.00 |
| python | 10,000,000 | 10.452261 | 2.33 x 10^-3 | 1.68 x 10^-3 | 18.16 | 18.08 | 18.46 | 0.55 M | 1.00 |
| numpy | 10,000,000 | 10.447247 | 2.32 x 10^-3 | 3.34 x 10^-3 | 0.1598 | 0.1592 | 0.1669 | 62.59 M | 0.99 |
| cpp | 10,000,000 | 10.452261 | 2.33 x 10^-3 | 1.68 x 10^-3 | 0.3016 | 0.3008 | 0.3035 | 33.16 M | 1.00 |

**Control variate**

| Back end | Paths | Price | Std. error | Abs. error vs BS | Run time, median (s) | min (s) | max (s) | Paths / s | CPU / wall |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| python | 100,000 | 10.430875 | 1.78 x 10^-2 | 1.97 x 10^-2 | 0.1591 | 0.1566 | 0.1626 | 0.63 M | 1.00 |
| numpy | 100,000 | 10.427545 | 1.77 x 10^-2 | 2.30 x 10^-2 | 0.001205 | 0.001191 | 0.001253 | 82.99 M | 1.00 |
| cpp | 100,000 | 10.430875 | 1.78 x 10^-2 | 1.97 x 10^-2 | 0.002429 | 0.002357 | 0.002612 | 41.17 M | 1.00 |
| python | 1,000,000 | 10.455303 | 5.61 x 10^-3 | 4.72 x 10^-3 | 1.601 | 1.579 | 1.66 | 0.62 M | 1.00 |
| numpy | 1,000,000 | 10.434512 | 5.61 x 10^-3 | 1.61 x 10^-2 | 0.01167 | 0.01162 | 0.01179 | 85.71 M | 1.00 |
| cpp | 1,000,000 | 10.455303 | 5.61 x 10^-3 | 4.72 x 10^-3 | 0.02474 | 0.02471 | 0.02502 | 40.42 M | 1.00 |
| python | 10,000,000 | 10.451439 | 1.77 x 10^-3 | 8.55 x 10^-4 | 15.77 | 15.74 | 15.89 | 0.63 M | 1.00 |
| numpy | 10,000,000 | 10.447184 | 1.77 x 10^-3 | 3.40 x 10^-3 | 0.1162 | 0.1161 | 0.1162 | 86.07 M | 1.00 |
| cpp | 10,000,000 | 10.451439 | 1.77 x 10^-3 | 8.55 x 10^-4 | 0.247 | 0.2467 | 0.2476 | 40.48 M | 1.00 |

**Antithetic + control variate**

| Back end | Paths | Price | Std. error | Abs. error vs BS | Run time, median (s) | min (s) | max (s) | Paths / s | CPU / wall |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| python | 100,000 | 10.436425 | 6.25 x 10^-3 | 1.42 x 10^-2 | 0.1794 | 0.1783 | 0.1818 | 0.56 M | 1.00 |
| numpy | 100,000 | 10.446439 | 6.17 x 10^-3 | 4.14 x 10^-3 | 0.001643 | 0.001623 | 0.001698 | 60.87 M | 1.00 |
| cpp | 100,000 | 10.436425 | 6.25 x 10^-3 | 1.42 x 10^-2 | 0.002896 | 0.002873 | 0.002984 | 34.53 M | 1.00 |
| python | 1,000,000 | 10.451274 | 1.95 x 10^-3 | 6.90 x 10^-4 | 1.806 | 1.777 | 1.812 | 0.55 M | 1.00 |
| numpy | 1,000,000 | 10.444566 | 1.95 x 10^-3 | 6.02 x 10^-3 | 0.01591 | 0.01587 | 0.01615 | 62.84 M | 1.00 |
| cpp | 1,000,000 | 10.451274 | 1.95 x 10^-3 | 6.90 x 10^-4 | 0.03003 | 0.02991 | 0.03013 | 33.30 M | 1.00 |
| python | 10,000,000 | 10.449937 | 6.15 x 10^-4 | 6.46 x 10^-4 | 18.31 | 17.88 | 18.41 | 0.55 M | 1.00 |
| numpy | 10,000,000 | 10.449700 | 6.15 x 10^-4 | 8.84 x 10^-4 | 0.1585 | 0.1582 | 0.1592 | 63.09 M | 1.00 |
| cpp | 10,000,000 | 10.449937 | 6.15 x 10^-4 | 6.46 x 10^-4 | 0.2998 | 0.2993 | 0.3003 | 33.36 M | 1.00 |

**Speed ratios** (same paths; above 1 means the first back end is faster)

| Variance reduction | Paths | cpp vs numpy | cpp vs python | numpy vs python |
| --- | ---: | ---: | ---: | ---: |
| No variance reduction | 100,000 | 0.50x | 67.3x | 133x |
| No variance reduction | 1,000,000 | 0.47x | 64.3x | 137x |
| No variance reduction | 10,000,000 | 0.47x | 63.8x | 136x |
| Antithetic | 100,000 | 0.55x | 62.1x | 112x |
| Antithetic | 1,000,000 | 0.53x | 60.2x | 114x |
| Antithetic | 10,000,000 | 0.53x | 60.2x | 114x |
| Control variate | 100,000 | 0.50x | 65.5x | 132x |
| Control variate | 1,000,000 | 0.47x | 64.7x | 137x |
| Control variate | 10,000,000 | 0.47x | 63.8x | 136x |
| Antithetic + control variate | 100,000 | 0.57x | 62.0x | 109x |
| Antithetic + control variate | 1,000,000 | 0.53x | 60.2x | 113x |
| Antithetic + control variate | 10,000,000 | 0.53x | 61.1x | 115x |
