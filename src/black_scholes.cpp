#include "derivkit/black_scholes.hpp"

#include "derivkit/math.hpp"

#include <algorithm>
#include <cmath>
#include <limits>
#include <stdexcept>

namespace derivkit::bs {
namespace {

double deterministic_price(const VanillaSpec& spec) {
    const double fwd = forward_price(spec.spot, spec.rate, spec.dividend, spec.time);
    const double df = discount_factor(spec.rate, spec.time);
    return df * payoff(fwd, spec.strike, spec.type);
}

}  // namespace

void d1_d2(const VanillaSpec& spec, double& d1, double& d2) {
    const double vol_sqrt_t = spec.vol * std::sqrt(spec.time);
    if (vol_sqrt_t <= 0.0) {
        throw std::invalid_argument("d1_d2 requires positive vol * sqrt(time)");
    }
    const double log_moneyness = std::log(spec.spot / spec.strike);
    d1 = (log_moneyness + (spec.rate - spec.dividend + 0.5 * spec.vol * spec.vol) * spec.time) /
         vol_sqrt_t;
    d2 = d1 - vol_sqrt_t;
}

double intrinsic_discounted(const VanillaSpec& spec) {
    validate(spec);
    const double df_r = discount_factor(spec.rate, spec.time);
    const double df_q = discount_factor(spec.dividend, spec.time);
    if (spec.type == OptionType::Call) {
        return std::max(spec.spot * df_q - spec.strike * df_r, 0.0);
    }
    return std::max(spec.strike * df_r - spec.spot * df_q, 0.0);
}

double upper_bound(const VanillaSpec& spec) {
    validate(spec);
    if (spec.type == OptionType::Call) {
        return spec.spot * discount_factor(spec.dividend, spec.time);
    }
    return spec.strike * discount_factor(spec.rate, spec.time);
}

double price(const VanillaSpec& spec) {
    validate(spec);
    if (spec.time == 0.0 || spec.vol == 0.0) {
        return deterministic_price(spec);
    }
    if (spec.strike == 0.0) {
        // Call on a zero strike is the prepaid forward; put is worthless.
        if (spec.type == OptionType::Call) {
            return spec.spot * discount_factor(spec.dividend, spec.time);
        }
        return 0.0;
    }

    double d1 = 0.0;
    double d2 = 0.0;
    d1_d2(spec, d1, d2);
    const double df_q = discount_factor(spec.dividend, spec.time);
    const double df_r = discount_factor(spec.rate, spec.time);
    if (spec.type == OptionType::Call) {
        return spec.spot * df_q * math::norm_cdf(d1) - spec.strike * df_r * math::norm_cdf(d2);
    }
    return spec.strike * df_r * math::norm_cdf(-d2) - spec.spot * df_q * math::norm_cdf(-d1);
}

PricingResult price_result(const VanillaSpec& spec) {
    PricingResult r;
    r.value = price(spec);
    r.method = "black-scholes";
    r.work = 1;
    r.converged = true;
    const double scale = std::max(1.0, std::abs(r.value));
    r.error_estimate = 8.0 * scale * std::numeric_limits<double>::epsilon();
    r.notes = "analytic; error is a few ulps";
    return r;
}

Greeks greeks(const VanillaSpec& spec) {
    validate(spec);
    Greeks g;
    if (spec.time == 0.0 || spec.vol == 0.0 || spec.strike == 0.0) {
        const double df_q = discount_factor(spec.dividend, spec.time);
        if (spec.time == 0.0) {
            if (spec.type == OptionType::Call) {
                g.delta = spec.spot > spec.strike ? 1.0 : (spec.spot < spec.strike ? 0.0 : 0.5);
            } else {
                g.delta = spec.spot < spec.strike ? -1.0 : (spec.spot > spec.strike ? 0.0 : -0.5);
            }
        } else if (spec.vol == 0.0) {
            const double fwd = forward_price(spec.spot, spec.rate, spec.dividend, spec.time);
            const bool itm = spec.type == OptionType::Call ? fwd > spec.strike : fwd < spec.strike;
            g.delta = itm ? (spec.type == OptionType::Call ? df_q : -df_q) : 0.0;
            const double df_r = discount_factor(spec.rate, spec.time);
            if (itm) {
                g.rho = (spec.type == OptionType::Call ? 1.0 : -1.0) * spec.strike * spec.time *
                        df_r;
            }
            const double value = price(spec);
            const double carry =
                spec.type == OptionType::Call ? spec.spot * df_q : -spec.spot * df_q;
            g.theta = spec.rate * (value - carry);
        }
        return g;
    }

    double d1 = 0.0;
    double d2 = 0.0;
    d1_d2(spec, d1, d2);
    g.d1 = d1;
    g.d2 = d2;

    const double sqrt_t = std::sqrt(spec.time);
    const double df_q = discount_factor(spec.dividend, spec.time);
    const double df_r = discount_factor(spec.rate, spec.time);
    const double phi = math::norm_pdf(d1);
    const double nd1 = math::norm_cdf(d1);
    const double nd2 = math::norm_cdf(d2);

    g.gamma = df_q * phi / (spec.spot * spec.vol * sqrt_t);
    g.vega = spec.spot * df_q * phi * sqrt_t;
    g.vanna = -df_q * phi * d2 / spec.vol;
    g.volga = g.vega * d1 * d2 / spec.vol;

    if (spec.type == OptionType::Call) {
        g.delta = df_q * nd1;
        g.theta = -spec.spot * df_q * phi * spec.vol / (2.0 * sqrt_t) -
                  spec.rate * spec.strike * df_r * nd2 + spec.dividend * spec.spot * df_q * nd1;
        g.rho = spec.strike * spec.time * df_r * nd2;
    } else {
        const double nmd1 = math::norm_cdf(-d1);
        const double nmd2 = math::norm_cdf(-d2);
        g.delta = df_q * (nd1 - 1.0);
        g.theta = -spec.spot * df_q * phi * spec.vol / (2.0 * sqrt_t) +
                  spec.rate * spec.strike * df_r * nmd2 - spec.dividend * spec.spot * df_q * nmd1;
        g.rho = -spec.strike * spec.time * df_r * nmd2;
    }
    return g;
}

double geometric_asian(const VanillaSpec& spec, std::uint32_t fixings) {
    validate(spec);
    if (fixings == 0) {
        throw std::invalid_argument("geometric_asian requires at least one fixing");
    }
    if (spec.time == 0.0) {
        return payoff(spec.spot, spec.strike, spec.type);
    }
    if (spec.vol == 0.0) {
        // Average of a deterministic path.
        const double dt = spec.time / static_cast<double>(fixings);
        const double mu = spec.rate - spec.dividend;
        double sum_log = 0.0;
        for (std::uint32_t i = 1; i <= fixings; ++i) {
            const double Si = spec.spot * std::exp(mu * dt * static_cast<double>(i));
            sum_log += std::log(Si);
        }
        const double G = std::exp(sum_log / static_cast<double>(fixings));
        return discount_factor(spec.rate, spec.time) * payoff(G, spec.strike, spec.type);
    }

    const double n = static_cast<double>(fixings);
    const double dt = spec.time / n;
    const double drift = spec.rate - spec.dividend - 0.5 * spec.vol * spec.vol;
    const double mu_g = std::log(spec.spot) + drift * (n + 1.0) * dt / 2.0;
    const double var_g = spec.vol * spec.vol * dt * (n + 1.0) * (2.0 * n + 1.0) / (6.0 * n);
    const double fwd_g = std::exp(mu_g + 0.5 * var_g);
    const double sig_g = std::sqrt(var_g);
    const double d1 = (std::log(fwd_g / spec.strike) + 0.5 * var_g) / sig_g;
    const double d2 = d1 - sig_g;
    const double df = discount_factor(spec.rate, spec.time);
    if (spec.type == OptionType::Call) {
        return df * (fwd_g * math::norm_cdf(d1) - spec.strike * math::norm_cdf(d2));
    }
    return df * (spec.strike * math::norm_cdf(-d2) - fwd_g * math::norm_cdf(-d1));
}

}  // namespace derivkit::bs
