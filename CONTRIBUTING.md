# Contributing

This is a small numerical library. Changes that land should preserve the
error-control contract: every numerical engine reports a diagnostic
(`PricingResult::error_estimate`) that a caller can actually check.

## Build the tests

```bash
cmake -S . -B build -DCMAKE_BUILD_TYPE=Debug -DDERIVKIT_WERROR=ON
cmake --build build --parallel
ctest --test-dir build --output-on-failure
```

With sanitizers:

```bash
cmake -S . -B build -DDERIVKIT_SANITIZE=ON -DDERIVKIT_WERROR=ON
cmake --build build --parallel
ctest --test-dir build --output-on-failure
```

## Style

- C++20, four-space indent, 100-column wrap (see `.clang-format`).
- No `using namespace` in headers.
- `[[nodiscard]]` on pure numeric functions.
- Throw `std::invalid_argument` for contract violations; do not return NaN
  as a silent failure.
- New engines go through `PricingResult` so examples and tests stay uniform.

## Numerical changes

If you touch a formula, add a regression against a published or independently
computed reference (Haug, Hull, or a high-resolution run of an existing
engine). State the tolerance and why it is justified - 1e-12 for analytic
identities, a few standard errors for Monte Carlo, the observed truncation
order for trees.
