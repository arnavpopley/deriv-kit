#pragma once

#include "derivkit/result.hpp"
#include "derivkit/types.hpp"

#include <cstdint>

namespace derivkit::mc {

struct McConfig {
    std::uint64_t paths = 100000;
    std::uint64_t seed = 1;
    VarianceReduction vr = VarianceReduction::None;
};

struct AdaptiveMcConfig {
    McConfig base{};  ///< `seed` and `vr` are used; `paths` is ignored.
    double stderr_tol = 1e-3;
    std::uint64_t batch = 20000;
    std::uint64_t max_paths = 2000000;
};

struct AsianConfig {
    McConfig mc{};
    std::uint32_t steps = 50;  ///< Number of fixings; path uses exact GBM increments.
};

/// Terminal GBM is sampled *exactly* (no Euler bias). Control variate is S_T,
/// whose mean S₀ e^{(r−q)T} is known in closed form.
[[nodiscard]] PricingResult european(const VanillaSpec& spec, const McConfig& cfg = {});

/// Keep drawing independent batches until the standard error is below
/// `stderr_tol` or `max_paths` is hit - the Monte Carlo analogue of an
/// adaptive integrator.
[[nodiscard]] PricingResult european_adaptive(const VanillaSpec& spec,
                                              const AdaptiveMcConfig& cfg = {});

/// Arithmetic-average Asian. Control variate is the geometric-average Asian,
/// priced with the Kemna-Vorst formula (see `bs::geometric_asian`).
[[nodiscard]] PricingResult arithmetic_asian(const VanillaSpec& spec,
                                             const AsianConfig& cfg = {});

}  // namespace derivkit::mc
