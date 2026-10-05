# Monte Carlo back-end comparison

Every number in this file was measured on the machine described below by the command shown. Nothing is estimated or carried over from another machine.

## How this was produced

```bash
python -m derivkit compare --paths 1e5 1e6 1e7 --vr all --budgets 0.1 1 10 --report benchmarks/RESULTS.md --plot benchmarks/accuracy_vs_time.png
```

Run finished 2026-10-04 23:34 BST. The environment below was recorded when the run started.

| Item | Value |
| --- | --- |
| CPU | Apple M5 (10 logical cores, arm64) |
| OS | macOS-27.0.1-arm64-arm-64bit-Mach-O |
| Python | CPython 3.13.13 (Clang 19.1.7) |
| NumPy | 2.5.3 (generator PCG64, BLAS accelerate) |
| C++ compiler | Apple clang 21.0.0 (clang-2100.1.1.101) |
| C++ build | Release, flags `-O3 -DNDEBUG -std=c++20 -ffp-contract=off`, pybind11 3.1.0 |
| Power | battery, Low Power Mode off |
| derivkit | 2.0.0 (commit 2e9dde2) |

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
| No variance reduction | 0.1 s | 4.24 x 10^-2 | 3.62 x 10^-3 | 5.62 x 10^-3 |
| No variance reduction | 1 s | 1.34 x 10^-2 | 1.14 x 10^-3 | 1.78 x 10^-3 |
| No variance reduction | 10 s | 4.25 x 10^-3 | 3.62 x 10^-4 | 5.62 x 10^-4 |
| Antithetic | 0.1 s | 2.27 x 10^-2 | 2.12 x 10^-3 | 2.92 x 10^-3 |
| Antithetic | 1 s | 7.15 x 10^-3 | 6.70 x 10^-4 | 9.24 x 10^-4 |
| Antithetic | 10 s | 2.26 x 10^-3 | 2.12 x 10^-4 | 2.92 x 10^-4 |
| Control variate | 0.1 s | 1.60 x 10^-2 | 1.37 x 10^-3 | 2.02 x 10^-3 |
| Control variate | 1 s | 5.04 x 10^-3 | 4.35 x 10^-4 | 6.38 x 10^-4 |
| Control variate | 10 s | 1.59 x 10^-3 | 1.37 x 10^-4 | 2.02 x 10^-4 |
| Antithetic + control variate | 0.1 s | 6.00 x 10^-3 | 5.73 x 10^-4 | 7.71 x 10^-4 |
| Antithetic + control variate | 1 s | 1.87 x 10^-3 | 1.81 x 10^-4 | 2.44 x 10^-4 |
| Antithetic + control variate | 10 s | 5.91 x 10^-4 | 5.73 x 10^-5 | 7.70 x 10^-5 |

**Detail of each budget run**

| Variance reduction | Time budget | Back end | Paths | Measured time (s) | Price | Std. error | Abs. error vs BS |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: |
| No variance reduction | 0.1 s | python | 119,948 | 0.0986 | 10.399676 | 4.24 x 10^-2 | 5.09 x 10^-2 |
| No variance reduction | 0.1 s | numpy | 16,560,119 | 0.09935 | 10.452729 | 3.62 x 10^-3 | 2.15 x 10^-3 |
| No variance reduction | 0.1 s | cpp | 6,864,302 | 0.09603 | 10.453208 | 5.62 x 10^-3 | 2.62 x 10^-3 |
| No variance reduction | 1 s | python | 1,199,487 | 0.9906 | 10.448566 | 1.34 x 10^-2 | 2.02 x 10^-3 |
| No variance reduction | 1 s | numpy | 165,601,193 | 1.037 | 10.452147 | 1.14 x 10^-3 | 1.56 x 10^-3 |
| No variance reduction | 1 s | cpp | 68,643,022 | 0.9053 | 10.449965 | 1.78 x 10^-3 | 6.19 x 10^-4 |
| No variance reduction | 10 s | python | 11,994,871 | 10.3 | 10.452493 | 4.25 x 10^-3 | 1.91 x 10^-3 |
| No variance reduction | 10 s | numpy | 1,656,011,938 | 10.46 | 10.450845 | 3.62 x 10^-4 | 2.62 x 10^-4 |
| No variance reduction | 10 s | cpp | 686,430,226 | 8.829 | 10.450370 | 5.62 x 10^-4 | 2.14 x 10^-4 |
| Antithetic | 0.1 s | python | 105,752 | 0.09969 | 10.428816 | 2.27 x 10^-2 | 2.18 x 10^-2 |
| Antithetic | 0.1 s | numpy | 12,052,982 | 0.09918 | 10.448795 | 2.12 x 10^-3 | 1.79 x 10^-3 |
| Antithetic | 0.1 s | cpp | 6,334,262 | 0.09865 | 10.450812 | 2.92 x 10^-3 | 2.28 x 10^-4 |
| Antithetic | 1 s | python | 1,057,529 | 0.9796 | 10.457764 | 7.15 x 10^-3 | 7.18 x 10^-3 |
| Antithetic | 1 s | numpy | 120,529,828 | 0.99 | 10.451347 | 6.70 x 10^-4 | 7.63 x 10^-4 |
| Antithetic | 1 s | cpp | 63,342,627 | 0.9919 | 10.451298 | 9.24 x 10^-4 | 7.15 x 10^-4 |
| Antithetic | 10 s | python | 10,575,298 | 10.13 | 10.452796 | 2.26 x 10^-3 | 2.21 x 10^-3 |
| Antithetic | 10 s | numpy | 1,205,298,280 | 10.23 | 10.450642 | 2.12 x 10^-4 | 5.82 x 10^-5 |
| Antithetic | 10 s | cpp | 633,426,274 | 9.857 | 10.450718 | 2.92 x 10^-4 | 1.34 x 10^-4 |
| Control variate | 0.1 s | python | 124,154 | 0.09978 | 10.438639 | 1.60 x 10^-2 | 1.19 x 10^-2 |
| Control variate | 0.1 s | numpy | 16,651,407 | 0.1005 | 10.448099 | 1.37 x 10^-3 | 2.48 x 10^-3 |
| Control variate | 0.1 s | cpp | 7,747,819 | 0.09865 | 10.450824 | 2.02 x 10^-3 | 2.40 x 10^-4 |
| Control variate | 1 s | python | 1,241,544 | 1.002 | 10.452951 | 5.04 x 10^-3 | 2.37 x 10^-3 |
| Control variate | 1 s | numpy | 166,514,073 | 1 | 10.450607 | 4.35 x 10^-4 | 2.30 x 10^-5 |
| Control variate | 1 s | cpp | 77,478,195 | 0.9878 | 10.451389 | 6.38 x 10^-4 | 8.06 x 10^-4 |
| Control variate | 10 s | python | 12,415,444 | 10.12 | 10.451041 | 1.59 x 10^-3 | 4.57 x 10^-4 |
| Control variate | 10 s | numpy | 1,665,140,739 | 10.17 | 10.450540 | 1.37 x 10^-4 | 4.40 x 10^-5 |
| Control variate | 10 s | cpp | 774,781,958 | 9.901 | 10.450738 | 2.02 x 10^-4 | 1.55 x 10^-4 |
| Antithetic + control variate | 0.1 s | python | 108,361 | 0.1002 | 10.436833 | 6.00 x 10^-3 | 1.38 x 10^-2 |
| Antithetic + control variate | 0.1 s | numpy | 11,521,644 | 0.09984 | 10.449799 | 5.73 x 10^-4 | 7.84 x 10^-4 |
| Antithetic + control variate | 0.1 s | cpp | 6,369,427 | 0.09871 | 10.449101 | 7.71 x 10^-4 | 1.48 x 10^-3 |
| Antithetic + control variate | 1 s | python | 1,083,616 | 1.007 | 10.451598 | 1.87 x 10^-3 | 1.01 x 10^-3 |
| Antithetic + control variate | 1 s | numpy | 115,216,440 | 1.112 | 10.450443 | 1.81 x 10^-4 | 1.41 x 10^-4 |
| Antithetic + control variate | 1 s | cpp | 63,694,278 | 0.9987 | 10.450381 | 2.44 x 10^-4 | 2.03 x 10^-4 |
| Antithetic + control variate | 10 s | python | 10,836,166 | 10.97 | 10.449814 | 5.91 x 10^-4 | 7.70 x 10^-4 |
| Antithetic + control variate | 10 s | numpy | 1,152,164,404 | 10.44 | 10.450585 | 5.73 x 10^-5 | 1.41 x 10^-6 |
| Antithetic + control variate | 10 s | cpp | 636,942,788 | 10.89 | 10.450595 | 7.70 x 10^-5 | 1.14 x 10^-5 |

**Calibration behind the budgets**

| Variance reduction | Back end | Calibration paths | Run time, median (s) | min (s) | max (s) | Paths / s |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| No variance reduction | python | 245,588 | 0.2047 | 0.2004 | 0.2296 | 1.20 M |
| No variance reduction | numpy | 33,165,924 | 0.2003 | 0.199 | 0.2046 | 165.60 M |
| No variance reduction | cpp | 9,662,701 | 0.1408 | 0.1355 | 0.1618 | 68.64 M |
| Antithetic | python | 215,513 | 0.2038 | 0.201 | 0.23 | 1.06 M |
| Antithetic | numpy | 22,499,313 | 0.1867 | 0.1862 | 0.1878 | 120.53 M |
| Antithetic | cpp | 11,967,766 | 0.1889 | 0.188 | 0.1917 | 63.34 M |
| Control variate | python | 246,640 | 0.1987 | 0.1982 | 0.1999 | 1.24 M |
| Control variate | numpy | 33,265,474 | 0.1998 | 0.1995 | 0.2002 | 166.51 M |
| Control variate | cpp | 15,173,756 | 0.1958 | 0.1934 | 0.1973 | 77.48 M |
| Antithetic + control variate | python | 215,584 | 0.1989 | 0.1983 | 0.2018 | 1.08 M |
| Antithetic + control variate | numpy | 22,574,458 | 0.1959 | 0.1945 | 0.1994 | 115.22 M |
| Antithetic + control variate | cpp | 12,420,878 | 0.195 | 0.1922 | 0.1971 | 63.69 M |

## Fixed path counts

**No variance reduction**

| Back end | Paths | Price | Std. error | Abs. error vs BS | Run time, median (s) | min (s) | max (s) | Paths / s | CPU / wall |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| python | 100,000 | 10.386439 | 4.64 x 10^-2 | 6.41 x 10^-2 | 0.08424 | 0.08326 | 0.08508 | 1.19 M | 1.00 |
| numpy | 100,000 | 10.357758 | 4.64 x 10^-2 | 9.28 x 10^-2 | 0.000628 | 0.0006214 | 0.0006669 | 159.24 M | 1.00 |
| cpp | 100,000 | 10.386439 | 4.64 x 10^-2 | 6.41 x 10^-2 | 0.001234 | 0.001204 | 0.001263 | 81.02 M | 1.00 |
| python | 1,000,000 | 10.448058 | 1.47 x 10^-2 | 2.53 x 10^-3 | 0.836 | 0.8292 | 0.8399 | 1.20 M | 1.00 |
| numpy | 1,000,000 | 10.427599 | 1.47 x 10^-2 | 2.30 x 10^-2 | 0.006093 | 0.006003 | 0.00618 | 164.13 M | 1.00 |
| cpp | 1,000,000 | 10.448058 | 1.47 x 10^-2 | 2.53 x 10^-3 | 0.01278 | 0.01271 | 0.01297 | 78.27 M | 1.00 |
| python | 10,000,000 | 10.454013 | 4.66 x 10^-3 | 3.43 x 10^-3 | 8.308 | 8.27 | 8.376 | 1.20 M | 1.00 |
| numpy | 10,000,000 | 10.455593 | 4.66 x 10^-3 | 5.01 x 10^-3 | 0.0603 | 0.06017 | 0.06084 | 165.84 M | 1.00 |
| cpp | 10,000,000 | 10.454013 | 4.66 x 10^-3 | 3.43 x 10^-3 | 0.1293 | 0.1291 | 0.1337 | 77.31 M | 1.00 |

**Antithetic**

| Back end | Paths | Price | Std. error | Abs. error vs BS | Run time, median (s) | min (s) | max (s) | Paths / s | CPU / wall |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| python | 100,000 | 10.424722 | 2.33 x 10^-2 | 2.59 x 10^-2 | 0.09519 | 0.0941 | 0.09578 | 1.05 M | 1.00 |
| numpy | 100,000 | 10.412200 | 2.32 x 10^-2 | 3.84 x 10^-2 | 0.0008622 | 0.0008371 | 0.0009339 | 115.99 M | 1.00 |
| cpp | 100,000 | 10.424722 | 2.33 x 10^-2 | 2.59 x 10^-2 | 0.001545 | 0.001494 | 0.001567 | 64.71 M | 1.00 |
| python | 1,000,000 | 10.457104 | 7.36 x 10^-3 | 6.52 x 10^-3 | 0.9426 | 0.9331 | 0.9452 | 1.06 M | 1.00 |
| numpy | 1,000,000 | 10.429434 | 7.35 x 10^-3 | 2.11 x 10^-2 | 0.008262 | 0.008215 | 0.00831 | 121.03 M | 1.00 |
| cpp | 1,000,000 | 10.457104 | 7.36 x 10^-3 | 6.52 x 10^-3 | 0.01548 | 0.0154 | 0.0157 | 64.58 M | 1.00 |
| python | 10,000,000 | 10.452261 | 2.33 x 10^-3 | 1.68 x 10^-3 | 9.268 | 9.228 | 9.396 | 1.08 M | 1.00 |
| numpy | 10,000,000 | 10.447247 | 2.32 x 10^-3 | 3.34 x 10^-3 | 0.08226 | 0.08213 | 0.08277 | 121.56 M | 1.00 |
| cpp | 10,000,000 | 10.452261 | 2.33 x 10^-3 | 1.68 x 10^-3 | 0.1551 | 0.155 | 0.1694 | 64.48 M | 0.99 |

**Control variate**

| Back end | Paths | Price | Std. error | Abs. error vs BS | Run time, median (s) | min (s) | max (s) | Paths / s | CPU / wall |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| python | 100,000 | 10.430875 | 1.78 x 10^-2 | 1.97 x 10^-2 | 0.08227 | 0.08173 | 0.08324 | 1.22 M | 1.00 |
| numpy | 100,000 | 10.427545 | 1.77 x 10^-2 | 2.30 x 10^-2 | 0.0006209 | 0.0006175 | 0.0006703 | 161.06 M | 1.00 |
| cpp | 100,000 | 10.430875 | 1.78 x 10^-2 | 1.97 x 10^-2 | 0.0012 | 0.001186 | 0.001286 | 83.32 M | 1.00 |
| python | 1,000,000 | 10.455303 | 5.61 x 10^-3 | 4.72 x 10^-3 | 0.8167 | 0.8116 | 0.9691 | 1.22 M | 0.99 |
| numpy | 1,000,000 | 10.434512 | 5.61 x 10^-3 | 1.61 x 10^-2 | 0.006058 | 0.006029 | 0.006196 | 165.07 M | 1.00 |
| cpp | 1,000,000 | 10.455303 | 5.61 x 10^-3 | 4.72 x 10^-3 | 0.01278 | 0.01268 | 0.01288 | 78.26 M | 1.00 |
| python | 10,000,000 | 10.451439 | 1.77 x 10^-3 | 8.55 x 10^-4 | 8.175 | 8.144 | 8.585 | 1.22 M | 1.00 |
| numpy | 10,000,000 | 10.447184 | 1.77 x 10^-3 | 3.40 x 10^-3 | 0.06061 | 0.06013 | 0.06101 | 164.98 M | 1.00 |
| cpp | 10,000,000 | 10.451439 | 1.77 x 10^-3 | 8.55 x 10^-4 | 0.1286 | 0.1281 | 0.129 | 77.77 M | 1.00 |

**Antithetic + control variate**

| Back end | Paths | Price | Std. error | Abs. error vs BS | Run time, median (s) | min (s) | max (s) | Paths / s | CPU / wall |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| python | 100,000 | 10.436425 | 6.25 x 10^-3 | 1.42 x 10^-2 | 0.09341 | 0.09219 | 0.09453 | 1.07 M | 1.00 |
| numpy | 100,000 | 10.446439 | 6.17 x 10^-3 | 4.14 x 10^-3 | 0.0008754 | 0.0008457 | 0.0009967 | 114.24 M | 0.99 |
| cpp | 100,000 | 10.436425 | 6.25 x 10^-3 | 1.42 x 10^-2 | 0.001502 | 0.001459 | 0.001583 | 66.58 M | 1.00 |
| python | 1,000,000 | 10.451274 | 1.95 x 10^-3 | 6.90 x 10^-4 | 0.9458 | 0.9357 | 0.9658 | 1.06 M | 1.00 |
| numpy | 1,000,000 | 10.444566 | 1.95 x 10^-3 | 6.02 x 10^-3 | 0.008361 | 0.008265 | 0.008578 | 119.60 M | 1.00 |
| cpp | 1,000,000 | 10.451274 | 1.95 x 10^-3 | 6.90 x 10^-4 | 0.0155 | 0.01545 | 0.01562 | 64.51 M | 1.00 |
| python | 10,000,000 | 10.449937 | 6.15 x 10^-4 | 6.46 x 10^-4 | 9.593 | 9.489 | 9.96 | 1.04 M | 0.99 |
| numpy | 10,000,000 | 10.449700 | 6.15 x 10^-4 | 8.84 x 10^-4 | 0.08281 | 0.08251 | 0.08379 | 120.76 M | 1.00 |
| cpp | 10,000,000 | 10.449937 | 6.15 x 10^-4 | 6.46 x 10^-4 | 0.1557 | 0.1549 | 0.1563 | 64.22 M | 1.00 |

**Speed ratios** (same paths; above 1 means the first back end is faster)

| Variance reduction | Paths | cpp vs numpy | cpp vs python | numpy vs python |
| --- | ---: | ---: | ---: | ---: |
| No variance reduction | 100,000 | 0.51x | 68.3x | 134x |
| No variance reduction | 1,000,000 | 0.48x | 65.4x | 137x |
| No variance reduction | 10,000,000 | 0.47x | 64.2x | 138x |
| Antithetic | 100,000 | 0.56x | 61.6x | 110x |
| Antithetic | 1,000,000 | 0.53x | 60.9x | 114x |
| Antithetic | 10,000,000 | 0.53x | 59.8x | 113x |
| Control variate | 100,000 | 0.52x | 68.5x | 133x |
| Control variate | 1,000,000 | 0.47x | 63.9x | 135x |
| Control variate | 10,000,000 | 0.47x | 63.6x | 135x |
| Antithetic + control variate | 100,000 | 0.58x | 62.2x | 107x |
| Antithetic + control variate | 1,000,000 | 0.54x | 61.0x | 113x |
| Antithetic + control variate | 10,000,000 | 0.53x | 61.6x | 116x |

## The fast generator for the C++ back end

This section was added after the run above and comes from a separate run. Nothing above it
was re-run or edited: those tables are the measurements of 2.0.0. Every row in this
section, including the python, numpy and cpp rows, was measured again in one session, so
compare rows within this section with each other. Compare them with the tables above only
if the Power row below matches the one at the top of this file.

`cpp/fast` is the cpp back end with `rng="fast"`: xoshiro256++ with a ziggurat sampler in
place of mt19937_64 with Box-Muller. The rest of the path loop is the same code. It is
repeatable for a seed, but it is a different stream: for the same seed its price does not
match python, numpy or cpp digit for digit, only within the standard error.

### How this section was produced

```bash
cmake --build build --target _mc_cpp_ext rng_speed where_time_goes
./build/rng_speed
./build/where_time_goes
python -m derivkit compare --backends python numpy cpp cpp/fast --paths 1e7 --vr all --budgets 1 --report out/fast_generator.md
```

Run finished 2026-10-05 22:16 BST. The environment below was recorded when the run started.

| Item | Value |
| --- | --- |
| CPU | Apple M5 (10 logical cores, arm64) |
| OS | macOS-27.0.1-arm64-arm-64bit-Mach-O |
| Python | CPython 3.13.13 (Clang 19.1.7) |
| NumPy | 2.5.3 (generator PCG64, BLAS accelerate) |
| C++ compiler | Apple clang 21.0.0 (clang-2100.1.1.101) |
| C++ build | Release, flags `-O3 -DNDEBUG -std=c++20 -ffp-contract=off`, pybind11 3.1.0 |
| Power | battery, Low Power Mode off |
| derivkit | 2.1.0 (commit bd871de) |

### Method

- Every back end is called through the same public function, `derivkit.monte_carlo.european(spec, cfg, backend=...)`, with the same option, seed, path count and variance-reduction setting.
- python and cpp use the same generator (mt19937_64 + Box-Muller), so with one seed they produce the same price. numpy uses its own generator (PCG64), so its price differs within the standard error. cpp/fast is the cpp back end with `rng="fast"` (xoshiro256++ with a ziggurat sampler): a third stream, repeatable for a seed, whose price also differs within the standard error.
- Single thread. BLAS and OpenMP were pinned to one thread before NumPy was imported. The CPU / wall column is process CPU time divided by wall time: 1.00 means one busy thread.
- Timer: `time.perf_counter()` around the call. Garbage collection is left on.
- Abs. error vs BS is the error of that one run. It is a single draw from a distribution whose width is the standard error, so the standard error is the steadier measure of accuracy.
- Fixed path counts: 1 untimed warm-up run, then 7 timed runs; the table shows the median, minimum and maximum. Paths / s is paths divided by the median.
- Time budgets: the paths-per-second rate is measured first (1 warm-up, then the median of 7 runs, shown in the calibration table). Each budget is then one run of rate x budget paths; the table shows the time that run really took.
- The two C++ programs are built with the same flags as the extension. Each reports the
  median of 7 timed runs after a warm-up, single thread.

### The generators on their own

`./build/rng_speed` draws 2 x 10^7 numbers per measurement with nothing else in the loop:
no exp, no payoff, no statistics. Normals are drawn in blocks of 256, as the kernel draws
them.

| Generator                              | Draw    |    ns | Draws / s |
| ---                                    | ---     |  ---: |      ---: |
| reproducible: mt19937_64 + Box-Muller  | uniform |  1.45 |   691.4 M |
| reproducible: mt19937_64 + Box-Muller  | normal  |  7.02 |   142.4 M |
| fast: xoshiro256++ + ziggurat          | uniform |  0.68 |  1464.9 M |
| fast: xoshiro256++ + ziggurat          | normal  |  1.06 |   942.7 M |

Normal draws: fast is 6.62 times the speed of reproducible.

### Fixed path count: 10^7 paths

**No variance reduction**

| Back end | Paths | Price | Std. error | Abs. error vs BS | Run time, median (s) | min (s) | max (s) | Paths / s | CPU / wall |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| python | 10,000,000 | 10.454013 | 4.66 x 10^-3 | 3.43 x 10^-3 | 8.307 | 8.225 | 8.656 | 1.20 M | 1.00 |
| numpy | 10,000,000 | 10.455593 | 4.66 x 10^-3 | 5.01 x 10^-3 | 0.06056 | 0.06031 | 0.06636 | 165.13 M | 0.99 |
| cpp | 10,000,000 | 10.454013 | 4.66 x 10^-3 | 3.43 x 10^-3 | 0.1297 | 0.1274 | 0.1628 | 77.09 M | 0.98 |
| cpp/fast | 10,000,000 | 10.453574 | 4.66 x 10^-3 | 2.99 x 10^-3 | 0.06689 | 0.06661 | 0.08264 | 149.49 M | 0.99 |

**Antithetic**

| Back end | Paths | Price | Std. error | Abs. error vs BS | Run time, median (s) | min (s) | max (s) | Paths / s | CPU / wall |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| python | 10,000,000 | 10.452261 | 2.33 x 10^-3 | 1.68 x 10^-3 | 9.23 | 9.188 | 9.453 | 1.08 M | 1.00 |
| numpy | 10,000,000 | 10.447247 | 2.32 x 10^-3 | 3.34 x 10^-3 | 0.08207 | 0.08196 | 0.0823 | 121.85 M | 1.00 |
| cpp | 10,000,000 | 10.452261 | 2.33 x 10^-3 | 1.68 x 10^-3 | 0.1542 | 0.1536 | 0.1542 | 64.86 M | 1.00 |
| cpp/fast | 10,000,000 | 10.450036 | 2.32 x 10^-3 | 5.48 x 10^-4 | 0.09295 | 0.09283 | 0.09367 | 107.59 M | 1.00 |

**Control variate**

| Back end | Paths | Price | Std. error | Abs. error vs BS | Run time, median (s) | min (s) | max (s) | Paths / s | CPU / wall |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| python | 10,000,000 | 10.451439 | 1.77 x 10^-3 | 8.55 x 10^-4 | 8.219 | 8.014 | 8.314 | 1.22 M | 1.00 |
| numpy | 10,000,000 | 10.447184 | 1.77 x 10^-3 | 3.40 x 10^-3 | 0.06015 | 0.05993 | 0.06029 | 166.25 M | 1.00 |
| cpp | 10,000,000 | 10.451439 | 1.77 x 10^-3 | 8.55 x 10^-4 | 0.1269 | 0.1268 | 0.1271 | 78.79 M | 1.00 |
| cpp/fast | 10,000,000 | 10.449887 | 1.77 x 10^-3 | 6.96 x 10^-4 | 0.0666 | 0.06643 | 0.06665 | 150.15 M | 1.00 |

**Antithetic + control variate**

| Back end | Paths | Price | Std. error | Abs. error vs BS | Run time, median (s) | min (s) | max (s) | Paths / s | CPU / wall |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| python | 10,000,000 | 10.449937 | 6.15 x 10^-4 | 6.46 x 10^-4 | 9.317 | 9.141 | 9.443 | 1.07 M | 1.00 |
| numpy | 10,000,000 | 10.449700 | 6.15 x 10^-4 | 8.84 x 10^-4 | 0.08193 | 0.0818 | 0.0893 | 122.06 M | 0.99 |
| cpp | 10,000,000 | 10.449937 | 6.15 x 10^-4 | 6.46 x 10^-4 | 0.154 | 0.1537 | 0.1556 | 64.95 M | 1.00 |
| cpp/fast | 10,000,000 | 10.450979 | 6.15 x 10^-4 | 3.95 x 10^-4 | 0.09296 | 0.09271 | 0.09341 | 107.58 M | 1.00 |

**Speed ratios** (same paths; above 1 means the first back end is faster)

| Variance reduction | Paths | cpp vs numpy | cpp vs python | numpy vs python | cpp/fast vs cpp | cpp/fast vs numpy | cpp/fast vs python |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| No variance reduction | 10,000,000 | 0.47x | 64.0x | 137x | 1.94x | 0.91x | 124x |
| Antithetic | 10,000,000 | 0.53x | 59.9x | 112x | 1.66x | 0.88x | 99.3x |
| Control variate | 10,000,000 | 0.47x | 64.8x | 137x | 1.91x | 0.90x | 123x |
| Antithetic + control variate | 10,000,000 | 0.53x | 60.5x | 114x | 1.66x | 0.88x | 100x |

### Standard error reached in 1 s

**Standard error reached in a fixed time** (smaller is better)

| Variance reduction | Time budget | python | numpy | cpp | cpp/fast |
| --- | --- | ---: | ---: | ---: | ---: |
| No variance reduction | 1 s | 1.33 x 10^-2 | 1.14 x 10^-3 | 1.66 x 10^-3 | 1.20 x 10^-3 |
| Antithetic | 1 s | 7.06 x 10^-3 | 6.65 x 10^-4 | 9.13 x 10^-4 | 7.11 x 10^-4 |
| Control variate | 1 s | 5.07 x 10^-3 | 4.34 x 10^-4 | 6.32 x 10^-4 | 4.59 x 10^-4 |
| Antithetic + control variate | 1 s | 1.87 x 10^-3 | 1.76 x 10^-4 | 2.42 x 10^-4 | 1.88 x 10^-4 |

**Detail of each budget run**

| Variance reduction | Time budget | Back end | Paths | Measured time (s) | Price | Std. error | Abs. error vs BS |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: |
| No variance reduction | 1 s | python | 1,226,658 | 0.9934 | 10.448199 | 1.33 x 10^-2 | 2.38 x 10^-3 |
| No variance reduction | 1 s | numpy | 166,950,030 | 1.001 | 10.452206 | 1.14 x 10^-3 | 1.62 x 10^-3 |
| No variance reduction | 1 s | cpp | 78,679,010 | 0.9997 | 10.450183 | 1.66 x 10^-3 | 4.00 x 10^-4 |
| No variance reduction | 1 s | cpp/fast | 150,361,972 | 1.001 | 10.448259 | 1.20 x 10^-3 | 2.32 x 10^-3 |
| Antithetic | 1 s | python | 1,084,916 | 1.004 | 10.457262 | 7.06 x 10^-3 | 6.68 x 10^-3 |
| Antithetic | 1 s | numpy | 122,098,617 | 1 | 10.451389 | 6.65 x 10^-4 | 8.05 x 10^-4 |
| Antithetic | 1 s | cpp | 64,835,079 | 1.003 | 10.451368 | 9.13 x 10^-4 | 7.84 x 10^-4 |
| Antithetic | 1 s | cpp/fast | 107,052,174 | 0.9971 | 10.450124 | 7.11 x 10^-4 | 4.59 x 10^-4 |
| Control variate | 1 s | python | 1,226,702 | 0.9921 | 10.453111 | 5.07 x 10^-3 | 2.53 x 10^-3 |
| Control variate | 1 s | numpy | 166,954,949 | 0.9992 | 10.450602 | 4.34 x 10^-4 | 1.86 x 10^-5 |
| Control variate | 1 s | cpp | 78,830,109 | 0.9994 | 10.451554 | 6.32 x 10^-4 | 9.71 x 10^-4 |
| Control variate | 1 s | cpp/fast | 149,507,930 | 1.001 | 10.450450 | 4.59 x 10^-4 | 1.33 x 10^-4 |
| Antithetic + control variate | 1 s | python | 1,081,585 | 0.9977 | 10.451711 | 1.87 x 10^-3 | 1.13 x 10^-3 |
| Antithetic + control variate | 1 s | numpy | 121,866,909 | 1.476 | 10.450468 | 1.76 x 10^-4 | 1.15 x 10^-4 |
| Antithetic + control variate | 1 s | cpp | 64,679,114 | 1 | 10.450392 | 2.42 x 10^-4 | 1.92 x 10^-4 |
| Antithetic + control variate | 1 s | cpp/fast | 107,050,182 | 0.9981 | 10.450635 | 1.88 x 10^-4 | 5.16 x 10^-5 |

**Calibration behind the budgets**

| Variance reduction | Back end | Calibration paths | Run time, median (s) | min (s) | max (s) | Paths / s |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| No variance reduction | python | 243,964 | 0.1989 | 0.1984 | 0.1993 | 1.23 M |
| No variance reduction | numpy | 33,334,509 | 0.1997 | 0.1994 | 0.2004 | 166.95 M |
| No variance reduction | cpp | 15,769,362 | 0.2004 | 0.2001 | 0.2012 | 78.68 M |
| No variance reduction | cpp/fast | 30,054,940 | 0.1999 | 0.1995 | 0.2009 | 150.36 M |
| Antithetic | python | 218,711 | 0.2016 | 0.1999 | 0.2113 | 1.08 M |
| Antithetic | numpy | 24,402,304 | 0.1999 | 0.1998 | 0.1999 | 122.10 M |
| Antithetic | cpp | 12,952,174 | 0.1998 | 0.1993 | 0.2008 | 64.84 M |
| Antithetic | cpp/fast | 21,392,236 | 0.1998 | 0.1996 | 0.2037 | 107.05 M |
| Control variate | python | 248,464 | 0.2025 | 0.2009 | 0.2035 | 1.23 M |
| Control variate | numpy | 33,314,942 | 0.1995 | 0.1993 | 0.2008 | 166.95 M |
| Control variate | cpp | 15,747,441 | 0.1998 | 0.1996 | 0.2002 | 78.83 M |
| Control variate | cpp/fast | 29,687,416 | 0.1986 | 0.1983 | 0.1997 | 149.51 M |
| Antithetic + control variate | python | 216,521 | 0.2002 | 0.1992 | 0.2008 | 1.08 M |
| Antithetic + control variate | numpy | 24,366,339 | 0.1999 | 0.1995 | 0.2107 | 121.87 M |
| Antithetic + control variate | cpp | 12,928,541 | 0.1999 | 0.199 | 0.202 | 64.68 M |
| Antithetic + control variate | cpp/fast | 21,380,223 | 0.1997 | 0.1992 | 0.2136 | 107.05 M |

### Where the time goes with each generator

`./build/where_time_goes` rebuilds the path loop one step at a time; the cost of a step is
the time it adds. The steps after the draw are the same code for both generators.

| C++ kernel, cost per path                            |     ns |
| ---                                                  |   ---: |
| mt19937_64 draw, converted to a uniform              |   1.45 |
| Box-Muller transform (log, sqrt, sin, cos)           |   5.85 |
| exp for the terminal price                           |   3.77 |
| payoff and Welford update                            |   1.37 |
| whole kernel, one path                               |  12.43 |
| whole kernel, one antithetic pair                    |  15.12 |
| not used: exp with log(S) inside the exponent        |   1.11 |

| C++ kernel with the fast generator, cost per path    |     ns |
| ---                                                  |   ---: |
| xoshiro256++ draw, converted to a uniform            |   0.67 |
| ziggurat (one table lookup; exp or log for 1.5%)     |   0.78 |
| exp for the terminal price                           |   3.69 |
| payoff and Welford update                            |   1.37 |
| whole kernel, one path                               |   6.51 |
| whole kernel, one antithetic pair                    |   9.11 |
| not used: exp with log(S) inside the exponent        |   1.00 |
