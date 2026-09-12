# derivkit

C++20 toolkit for pricing derivative contracts with **explicit numerical error control**.

The same discipline that makes a CR3BP integrator trustworthy — adaptive refinement, a
computable error estimate, and tests that check orders of accuracy — is applied here to
Black–Scholes analytics, binomial and trinomial trees, and Monte Carlo with antithetic
and control variates.

[![C++](https://img.shields.io/badge/C%2B%2B-20-blue.svg)](CMakeLists.txt)
[![CMake](https://img.shields.io/badge/CMake-3.16%2B-green.svg)](CMakeLists.txt)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

## Features

| Engine | What it prices | Error diagnostic |
| --- | --- | --- |
| Black–Scholes–Merton | European vanilla, geometric Asian, Greeks | a few ulps |
| Implied volatility | Newton + residual-controlled bisection | \|BS(σ) − market\| |
| CRR / Jarrow–Rudd binomial | European and American vanilla | \|P(N) − P(N/2)\| |
| Leisen–Reimer binomial | Smooth second-order European (American too) | successive difference |
| Kamrad–Ritchken trinomial | European and American vanilla | successive difference |
| Monte Carlo (exact GBM) | European, arithmetic Asian | sample standard error |
| Antithetic + control variates | Europeans (control = S_T); Asians (control = geometric) | reduced standard error |
| Adaptive drivers | trees double N; MC grows paths | user `abs_tol` / `stderr_tol` |
| Groww option chain | live NIFTY / BANKNIFTY / stocks → derivkit prices | BS vs LTP, IV vs Groww IV |

The core library has no third-party dependencies. Headers, a static library, CTest,
examples (including a Groww option-chain client), and GitHub Actions CI.

## Quick start

```bash
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build --parallel
ctest --test-dir build --output-on-failure
./build/examples/vanilla_comparison
./build/examples/groww_chain          # bundled NIFTY chain; live with GROWW_ACCESS_TOKEN
```

A C++20 compiler is required (GCC 11+, Clang 14+, or MSVC 2022). If `c++` on your
PATH is a Clang that cannot find `libstdc++`, configure with `CXX=g++`.

```cpp
#include "derivkit/derivkit.hpp"

using namespace derivkit;

VanillaSpec spec{
    .spot = 100, .strike = 100, .rate = 0.05,
    .dividend = 0.0, .vol = 0.20, .time = 1.0,
    .type = OptionType::Call,
};

double analytic = bs::price(spec);
auto greeks    = bs::greeks(spec);
auto tree_px   = tree::leisen_reimer(spec, 101);
auto mc_px     = mc::european(spec, {
    .paths = 100000,
    .seed = 1,
    .vr = VarianceReduction::Antithetic | VarianceReduction::ControlVariate,
});
```

Every numerical call returns a `PricingResult` with `value`, `error_estimate`, and the
amount of work performed (steps or paths). Treat that error the way you would treat an
RK45 local truncation estimate: if it is not small enough, ask the adaptive driver for
more work.

```cpp
auto refined = tree::adaptive(spec, {.abs_tol = 1e-6});
auto mc_ok   = mc::european_adaptive(spec, {.stderr_tol = 1e-3});
```

## Why the error-control contract

A closed-form price without a residual, a tree without a truncation check, and a Monte
Carlo estimate without a standard error are all unfinished numerical methods. `derivkit`
makes the diagnostic part of the return type so it cannot be forgotten:

- **Analytic identities** (put-call parity, round-trip implied vol) are tested to ~1e-12.
- **Trees** expose \|P(N) − P(N/2)\| and can Richardson-extrapolate CRR’s O(1/N) term.
- **Leisen–Reimer** is the high-order lattice: it matches Φ(d₁), Φ(d₂) so a European
  with a few hundred steps sits well inside a basis point of Black–Scholes.
- **Monte Carlo** uses Welford moments, exact GBM sampling (no Euler bias on vanillas),
  and optional antithetic / control variates. Adaptive sampling stops on standard error,
  not on a guessed path count.

The mapping from an orbital toolkit is intentional:

| CR3BP-style integrator | derivkit |
| --- | --- |
| Adaptive Runge–Kutta step | Adaptive tree depth / MC path count |
| Local truncation error | \|P(N)−P(N/2)\| or MC standard error |
| Event / root finding with residual | Implied vol Newton + bisection residual |
| Conserved quantities | Put-call parity, model-free price bounds |

Formulas and references: [docs/methods.md](docs/methods.md).

## Example numbers

European call, S = K = 100, r = 5%, σ = 20%, T = 1. Black–Scholes = **10.45058357**.

Absolute error versus N (`./build/examples/convergence`):

| N | CRR | Jarrow–Rudd | Leisen–Reimer | Trinomial |
| ---: | ---: | ---: | ---: | ---: |
| 51 | 3.4×10⁻² | 2.7×10⁻² | 1.3×10⁻⁴ | 3.9×10⁻² |
| 101 | 1.7×10⁻² | 9.1×10⁻³ | 3.4×10⁻⁵ | 2.0×10⁻² |
| 401 | 4.4×10⁻³ | 4.7×10⁻³ | 2.2×10⁻⁶ | 5.0×10⁻³ |
| 801 | 2.2×10⁻³ | 2.0×10⁻³ | 5.5×10⁻⁷ | 2.5×10⁻³ |

Leisen–Reimer is the high-order lattice: at 101 steps it is already inside 0.04 cents of Black–Scholes. CRR with Richardson on even N drops the 401-step error from ~4×10⁻³ to ~10⁻⁶.

American put, S = 36, K = 40, r = 6%, σ = 20%, T = 1:

| Method | Price |
| --- | ---: |
| European Black–Scholes | 3.844308 |
| CRR American, N = 801 | 4.486399 |
| Kamrad–Ritchken American, N = 801 | 4.486245 |
| Adaptive trinomial (tol 5×10⁻⁴) | 4.486403 |

Early-exercise premium ≈ **0.642**.

Variance reduction, 50,000 European paths, seed 42 (`./build/examples/variance_reduction`):

| Method | Price | Std. err. | Variance ratio |
| --- | ---: | ---: | ---: |
| Crude | 10.544 | 6.6×10⁻² | 1.0 |
| Antithetic | 10.463 | 3.3×10⁻² | 4.1 |
| Control (S_T) | 10.459 | 2.5×10⁻² | 7.0 |
| Antithetic + control | 10.459 | 8.8×10⁻³ | **57** |

Arithmetic Asian, 50 fixings, 20,000 paths. Geometric closed form = 5.641058. The geometric-average control is the classical pairing and is worth three orders of magnitude in variance:

| Method | Std. err. | Variance ratio |
| --- | ---: | ---: |
| Crude | 5.7×10⁻² | 1 |
| Antithetic | 2.8×10⁻² | 4 |
| Geometric control | 1.6×10⁻³ | 1,300 |
| Antithetic + geo-control | 1.2×10⁻³ | **2,300** |

## Project layout

```
include/derivkit/   public headers
src/                library implementation
tests/              CTest binaries, no external test framework
examples/           comparison, American put, VR study, convergence, implied vol,
                    Groww NIFTY chain
examples/data/      bundled Groww-shaped NIFTY fixture
docs/methods.md     formulas and references
```

## Live NIFTY chain via Groww

`examples/groww_chain` pulls an option chain from the [Groww Trading API](https://groww.in/trade-api/docs/curl/live-data)
and prices every nearby strike with Black–Scholes and a Leisen–Reimer tree. It prints
Groww's last traded price next to the model, and implied vol / delta next to Groww's
own Greeks.

```bash
# Offline demo (no account) — bundled NIFTY fixture
./build/examples/groww_chain

# Live NIFTY, nearest expiry (token from Groww → Settings → Trading APIs)
export GROWW_ACCESS_TOKEN=...
./build/examples/groww_chain NIFTY

# Other underlyings, specific expiry
./build/examples/groww_chain BANKNIFTY --expiry 2026-09-29
./build/examples/groww_chain RELIANCE --strikes 4 --mc
```

Copy `.env.example` and fill `GROWW_ACCESS_TOKEN`, or use `GROWW_API_KEY` +
`GROWW_API_SECRET` / `GROWW_TOTP`. Live mode needs `curl` on `PATH`. Without
credentials the example still runs against `examples/data/nifty_chain.json`.

Columns: **LTP** is Groww's market, **BS** is Black–Scholes using Groww's IV,
**LR** is the tree, **iv%** is derivkit's implied vol from LTP, **ivG%** is Groww.

## Install

```bash
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release -DCMAKE_INSTALL_PREFIX=/usr/local
cmake --build build --parallel
cmake --install build
```

Downstream:

```cmake
find_package(derivkit REQUIRED)
target_link_libraries(my_app PRIVATE derivkit::derivkit)
```

## Tests and sanitizers

```bash
cmake -S . -B build -DDERIVKIT_WERROR=ON -DDERIVKIT_SANITIZE=ON
cmake --build build --parallel
ctest --test-dir build --output-on-failure
```

CI builds with both GCC and Clang, treats warnings as errors, and reruns the suite
under ASan/UBSan.

## License

MIT. See [LICENSE](LICENSE).
