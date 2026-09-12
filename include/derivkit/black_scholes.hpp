#pragma once

#include "derivkit/result.hpp"
#include "derivkit/types.hpp"

#include <cstdint>

namespace derivkit::bs {

/// Analytic Greeks of a European vanilla. Units:
///   delta  = ∂V/∂S
///   gamma  = ∂²V/∂S²
///   vega   = ∂V/∂σ          (per 1.0 of volatility, not per 1%)
///   theta  = ∂V/∂t          (per year; t increasing toward expiry is negative)
///   rho    = ∂V/∂r          (per 1.0 of rate, not per basis point)
///   vanna  = ∂²V/∂S∂σ
///   volga  = ∂²V/∂σ²
struct Greeks {
    double delta = 0.0;
    double gamma = 0.0;
    double vega = 0.0;
    double theta = 0.0;
    double rho = 0.0;
    double vanna = 0.0;
    double volga = 0.0;
    double d1 = 0.0;
    double d2 = 0.0;
};

/// Black-Scholes-Merton European vanilla (continuous dividend yield).
[[nodiscard]] double price(const VanillaSpec& spec);

/// Same value packaged as a `PricingResult` (error is a few ulps).
[[nodiscard]] PricingResult price_result(const VanillaSpec& spec);

[[nodiscard]] Greeks greeks(const VanillaSpec& spec);

/// Undiscounted Black-Scholes d₁, d₂. `vol * sqrt(time)` must be positive.
void d1_d2(const VanillaSpec& spec, double& d1, double& d2);

/// Discounted European value of a discrete geometric-average Asian.
/// `fixings` observations at Δt, 2Δt, …, T (S₀ is not in the average).
/// Kemna-Vorst lognormal formula; used as the control in arithmetic-Asian MC.
[[nodiscard]] double geometric_asian(const VanillaSpec& spec, std::uint32_t fixings);

/// Tight model-independent bounds for a European vanilla.
[[nodiscard]] double intrinsic_discounted(const VanillaSpec& spec);
[[nodiscard]] double upper_bound(const VanillaSpec& spec);

/// Black-76 on a forward. Diffusion uses `time_vol`; discounting is a given DF
/// (typically e^{-r T_rate} with a possibly different calendar year-fraction).
/// Identity: `price(to_black(spec)) == price(spec)` when T_vol = T_rate = spec.time.
struct BlackSpec {
    double forward = 0.0;   ///< F > 0
    double strike = 0.0;    ///< K >= 0
    double discount = 1.0;  ///< DF > 0
    double vol = 0.0;       ///< sigma >= 0
    double time_vol = 0.0;  ///< year-fraction for the diffusion >= 0
    OptionType type = OptionType::Call;
};

using derivkit::validate;  // VanillaSpec overload; do not hide it in this namespace
void validate(const BlackSpec& spec);

/// Map a spot Black-Scholes spec to Black-76 with a single year-fraction.
[[nodiscard]] inline BlackSpec to_black(const VanillaSpec& spec) {
    return BlackSpec{
        .forward = forward_price(spec.spot, spec.rate, spec.dividend, spec.time),
        .strike = spec.strike,
        .discount = discount_factor(spec.rate, spec.time),
        .vol = spec.vol,
        .time_vol = spec.time,
        .type = spec.type,
    };
}

[[nodiscard]] double price(const BlackSpec& spec);
[[nodiscard]] Greeks greeks(const BlackSpec& spec);
[[nodiscard]] double intrinsic_discounted(const BlackSpec& spec);
[[nodiscard]] double upper_bound(const BlackSpec& spec);

}  // namespace derivkit::bs
