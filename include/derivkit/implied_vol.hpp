#pragma once

#include "derivkit/black_scholes.hpp"
#include "derivkit/types.hpp"

namespace derivkit::bs {

struct ImpliedVolConfig {
    double abs_tol = 1e-12;   ///< |BS(σ) − price| stopping residual
    double rel_tol = 1e-12;   ///< relative residual vs. max(|price|, 1)
    int max_newton = 40;
    int max_bisect = 80;
    double lo = 1e-8;
    double hi = 5.0;
};

struct ImpliedVolResult {
    double vol = 0.0;
    double residual = 0.0;  ///< BS(σ) − market price
    int iterations = 0;
    bool converged = false;
    const char* method = "";  ///< "newton", "bisection", or a failure tag
};

/// Invert Black-Scholes for σ. Newton on vega, bisection fallback.
/// The input spec's `vol` is ignored (used only as a warm start if > 0).
[[nodiscard]] ImpliedVolResult implied_vol(const VanillaSpec& spec, double market_price,
                                           const ImpliedVolConfig& cfg = {});

/// Invert Black-76 for σ. Same solver; residual is Black-76(σ) − market.
[[nodiscard]] ImpliedVolResult implied_vol(const BlackSpec& spec, double market_price,
                                           const ImpliedVolConfig& cfg = {});

}  // namespace derivkit::bs
