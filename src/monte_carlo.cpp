#include "derivkit/monte_carlo.hpp"

#include "derivkit/black_scholes.hpp"
#include "derivkit/rng.hpp"
#include "detail/welford.hpp"

#include <algorithm>
#include <cmath>
#include <stdexcept>
#include <string>
#include <vector>

namespace derivkit::mc {
namespace {

struct Sample {
    double y = 0.0;  // discounted payoff
    double x = 0.0;  // discounted control
};

double known_mean_st(const VanillaSpec& spec) {
    // E[e^{-rT} S_T] = S₀ e^{-qT}
    return spec.spot * discount_factor(spec.dividend, spec.time);
}

Sample european_pair(const VanillaSpec& spec, double z, bool antithetic) {
    const double drift = (spec.rate - spec.dividend - 0.5 * spec.vol * spec.vol) * spec.time;
    const double vol_t = spec.vol * std::sqrt(spec.time);
    const double df = discount_factor(spec.rate, spec.time);

    auto one = [&](double zz) {
        const double st = spec.spot * std::exp(drift + vol_t * zz);
        Sample s;
        s.y = df * payoff(st, spec.strike, spec.type);
        s.x = df * st;
        return s;
    };

    if (!antithetic) {
        return one(z);
    }
    const Sample a = one(z);
    const Sample b = one(-z);
    return Sample{0.5 * (a.y + b.y), 0.5 * (a.x + b.x)};
}

PricingResult finish_cv(const detail::WelfordPair& acc, double ex, const char* method,
                        bool used_cv) {
    PricingResult r;
    r.work = acc.n;
    r.method = method;
    r.converged = acc.n > 1;

    if (!used_cv || acc.var_x() <= 0.0) {
        r.value = acc.mean_y;
        r.error_estimate = acc.n > 1 ? std::sqrt(acc.var_y() / static_cast<double>(acc.n)) : 0.0;
        return r;
    }

    const double beta = acc.cov_xy() / acc.var_x();
    r.value = acc.mean_y - beta * (acc.mean_x - ex);
    const double var = acc.var_y() + beta * beta * acc.var_x() - 2.0 * beta * acc.cov_xy();
    r.error_estimate = acc.n > 1 ? std::sqrt(std::max(var, 0.0) / static_cast<double>(acc.n)) : 0.0;
    r.notes = "beta=" + std::to_string(beta);
    return r;
}

const char* european_method_name(VarianceReduction vr) {
    const bool a = has(vr, VarianceReduction::Antithetic);
    const bool c = has(vr, VarianceReduction::ControlVariate);
    if (a && c) {
        return "mc-european-antithetic-cv";
    }
    if (a) {
        return "mc-european-antithetic";
    }
    if (c) {
        return "mc-european-cv";
    }
    return "mc-european";
}

}  // namespace

PricingResult european(const VanillaSpec& spec, const McConfig& cfg) {
    validate(spec);
    if (cfg.paths < 2) {
        throw std::invalid_argument("monte carlo requires at least 2 paths");
    }
    if (spec.time == 0.0 || spec.vol == 0.0) {
        PricingResult r = bs::price_result(spec);
        r.method = european_method_name(cfg.vr);
        r.work = cfg.paths;
        return r;
    }

    const bool anti = has(cfg.vr, VarianceReduction::Antithetic);
    const bool cv = has(cfg.vr, VarianceReduction::ControlVariate);
    const double ex = known_mean_st(spec);

    NormalRng rng(cfg.seed);
    detail::WelfordPair acc;
    for (std::uint64_t i = 0; i < cfg.paths; ++i) {
        const Sample s = european_pair(spec, rng.normal(), anti);
        acc.add(s.x, s.y);
    }
    return finish_cv(acc, ex, european_method_name(cfg.vr), cv);
}

PricingResult european_adaptive(const VanillaSpec& spec, const AdaptiveMcConfig& cfg) {
    validate(spec);
    if (cfg.stderr_tol <= 0.0) {
        throw std::invalid_argument("stderr_tol must be positive");
    }
    if (cfg.batch < 2 || cfg.max_paths < cfg.batch) {
        throw std::invalid_argument("invalid adaptive path budget");
    }

    const bool anti = has(cfg.base.vr, VarianceReduction::Antithetic);
    const bool cv = has(cfg.base.vr, VarianceReduction::ControlVariate);
    const double ex = known_mean_st(spec);

    NormalRng rng(cfg.base.seed);
    detail::WelfordPair acc;
    PricingResult last{};

    while (acc.n < cfg.max_paths) {
        const std::uint64_t remaining = cfg.max_paths - acc.n;
        const std::uint64_t take = std::min(cfg.batch, remaining);
        for (std::uint64_t i = 0; i < take; ++i) {
            const Sample s = european_pair(spec, rng.normal(), anti);
            acc.add(s.x, s.y);
        }
        last = finish_cv(acc, ex, european_method_name(cfg.base.vr), cv);
        last.notes = last.notes.empty() ? "adaptive" : last.notes + ", adaptive";
        if (last.error_estimate <= cfg.stderr_tol && acc.n >= cfg.batch) {
            last.converged = true;
            return last;
        }
    }
    last.converged = last.error_estimate <= cfg.stderr_tol;
    if (!last.converged) {
        last.notes = last.notes.empty() ? "hit max_paths" : last.notes + ", hit max_paths";
    }
    return last;
}

PricingResult arithmetic_asian(const VanillaSpec& spec, const AsianConfig& cfg) {
    validate(spec);
    if (cfg.mc.paths < 2) {
        throw std::invalid_argument("monte carlo requires at least 2 paths");
    }
    if (cfg.steps == 0) {
        throw std::invalid_argument("asian steps must be positive");
    }

    const bool anti = has(cfg.mc.vr, VarianceReduction::Antithetic);
    const bool cv = has(cfg.mc.vr, VarianceReduction::ControlVariate);
    const double ex = bs::geometric_asian(spec, cfg.steps);  // already discounted
    const double dt = spec.time / static_cast<double>(cfg.steps);
    const double drift = (spec.rate - spec.dividend - 0.5 * spec.vol * spec.vol) * dt;
    const double vol_dt = spec.vol * std::sqrt(dt);
    const double df = discount_factor(spec.rate, spec.time);
    const double nfix = static_cast<double>(cfg.steps);

    auto one_path = [&](NormalRng& rng, bool flip) {
        double s = spec.spot;
        double sum = 0.0;
        double logsum = 0.0;
        for (std::uint32_t k = 0; k < cfg.steps; ++k) {
            double z = rng.normal();
            if (flip) {
                z = -z;
            }
            s *= std::exp(drift + vol_dt * z);
            sum += s;
            logsum += std::log(s);
        }
        const double arith = sum / nfix;
        const double geo = std::exp(logsum / nfix);
        Sample out;
        out.y = df * payoff(arith, spec.strike, spec.type);
        out.x = df * payoff(geo, spec.strike, spec.type);
        return out;
    };

    NormalRng rng(cfg.mc.seed);
    detail::WelfordPair acc;
    for (std::uint64_t i = 0; i < cfg.mc.paths; ++i) {
        if (!anti) {
            const Sample s = one_path(rng, false);
            acc.add(s.x, s.y);
        } else {
            // Pair the path with its sign-flipped twin; consume 2 * steps normals
            // by drawing one path then replaying with a fresh engine? Easier: draw
            // the Z's once. We implement that by running the + path and storing Z.
            // To keep the RNG interface simple we draw a dedicated engine copy:
            // generate Zs into a tiny loop with stored normals.
            std::vector<double> z(cfg.steps);
            for (std::uint32_t k = 0; k < cfg.steps; ++k) {
                z[k] = rng.normal();
            }
            auto replay = [&](double sign) {
                double s = spec.spot;
                double sum = 0.0;
                double logsum = 0.0;
                for (std::uint32_t k = 0; k < cfg.steps; ++k) {
                    s *= std::exp(drift + vol_dt * sign * z[k]);
                    sum += s;
                    logsum += std::log(s);
                }
                Sample out;
                out.y = df * payoff(sum / nfix, spec.strike, spec.type);
                out.x = df * payoff(std::exp(logsum / nfix), spec.strike, spec.type);
                return out;
            };
            const Sample a = replay(1.0);
            const Sample b = replay(-1.0);
            acc.add(0.5 * (a.x + b.x), 0.5 * (a.y + b.y));
        }
    }

    const bool a = anti;
    const bool c = cv;
    const char* name = (a && c)   ? "mc-asian-antithetic-cv"
                       : a        ? "mc-asian-antithetic"
                       : c        ? "mc-asian-cv"
                                  : "mc-asian";
    PricingResult r = finish_cv(acc, ex, name, cv);
    if (cv) {
        r.notes += r.notes.empty() ? "geo-asian control" : ", geo-asian control";
    }
    return r;
}

}  // namespace derivkit::mc
