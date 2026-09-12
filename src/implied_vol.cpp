#include "derivkit/implied_vol.hpp"

#include "derivkit/black_scholes.hpp"

#include <algorithm>
#include <cmath>
#include <stdexcept>

namespace derivkit::bs {

ImpliedVolResult implied_vol(const VanillaSpec& spec, double market_price,
                             const ImpliedVolConfig& cfg) {
    validate(spec);
    if (!std::isfinite(market_price)) {
        throw std::invalid_argument("market_price must be finite");
    }

    ImpliedVolResult out;
    const double lower = intrinsic_discounted(spec);
    const double upper = upper_bound(spec);
    const double scale = std::max({1.0, std::abs(market_price), std::abs(lower)});
    const double tol = std::max(cfg.abs_tol, cfg.rel_tol * scale);

    if (market_price < lower - 10.0 * tol) {
        out.method = "below-intrinsic";
        out.residual = market_price - lower;
        return out;
    }
    if (market_price > upper + 10.0 * tol) {
        out.method = "above-upper-bound";
        out.residual = market_price - upper;
        return out;
    }

    // Prices hugging the intrinsic/upper bound map to σ → 0 or σ → ∞.
    if (std::abs(market_price - lower) <= tol) {
        out.vol = 0.0;
        VanillaSpec s = spec;
        s.vol = 0.0;
        out.residual = price(s) - market_price;
        out.converged = true;
        out.method = "zero-vol";
        return out;
    }

    auto priced = [&](double sigma) {
        VanillaSpec s = spec;
        s.vol = sigma;
        return price(s);
    };
    auto vega_of = [&](double sigma) {
        VanillaSpec s = spec;
        s.vol = sigma;
        return greeks(s).vega;
    };

    double lo = cfg.lo;
    double hi = cfg.hi;
    while (priced(hi) < market_price && hi < 1.0e2) {
        hi *= 2.0;
    }

    double sigma = spec.vol > 0.0 ? spec.vol : 0.2;
    sigma = std::clamp(sigma, lo, hi);

    int it = 0;
    for (; it < cfg.max_newton; ++it) {
        const double px = priced(sigma);
        const double diff = px - market_price;
        out.residual = diff;
        out.vol = sigma;
        out.iterations = it + 1;
        if (std::abs(diff) <= tol) {
            out.converged = true;
            out.method = "newton";
            return out;
        }
        const double v = vega_of(sigma);
        if (!(v > 1.0e-14)) {
            break;
        }
        sigma -= diff / v;
        if (!(sigma > lo && sigma < hi)) {
            break;
        }
    }

    // Bisection on a bracket that is known to contain the root.
    double f_lo = priced(lo) - market_price;
    double f_hi = priced(hi) - market_price;
    if (f_lo * f_hi > 0.0) {
        // Expand until we bracket or give up.
        for (int k = 0; k < 20 && f_lo * f_hi > 0.0; ++k) {
            lo *= 0.5;
            hi *= 1.5;
            f_lo = priced(lo) - market_price;
            f_hi = priced(hi) - market_price;
        }
    }
    if (f_lo * f_hi > 0.0) {
        out.method = "no-bracket";
        out.iterations = it;
        return out;
    }

    for (int k = 0; k < cfg.max_bisect; ++k) {
        const double mid = 0.5 * (lo + hi);
        const double f_mid = priced(mid) - market_price;
        ++it;
        out.iterations = it;
        out.vol = mid;
        out.residual = f_mid;
        if (std::abs(f_mid) <= tol || 0.5 * (hi - lo) <= 1.0e-14 * mid) {
            out.converged = true;
            out.method = "bisection";
            return out;
        }
        if (f_lo * f_mid <= 0.0) {
            hi = mid;
            f_hi = f_mid;
        } else {
            lo = mid;
            f_lo = f_mid;
        }
    }

    out.method = "max-iterations";
    return out;
}

}  // namespace derivkit::bs
