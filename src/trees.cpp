#include "derivkit/trees.hpp"

#include "derivkit/black_scholes.hpp"

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

namespace derivkit::tree {
namespace {

int odd_steps(int n) {
    if (n < 1) {
        throw std::invalid_argument("tree steps must be positive");
    }
    return n % 2 == 0 ? n + 1 : n;
}

double peizer_pratt(double z, int n) {
    // Improved Peizer-Pratt inversion (Haug / Leisen-Reimer).
    const double x = z / (static_cast<double>(n) + 1.0 / 3.0 + 0.1 / (n + 1.0));
    const double inner = 1.0 - std::exp(-x * x * (n + 1.0 / 6.0));
    const double mag = 0.5 * std::sqrt(std::max(inner, 0.0));
    return 0.5 + (z >= 0.0 ? mag : -mag);
}

PricingResult binomial(const VanillaSpec& spec, int steps, double u, double d, double p,
                       bool american, const char* method) {
    if (!(p > 0.0 && p < 1.0) || !(u > 0.0) || !(d > 0.0)) {
        throw std::runtime_error(std::string(method) +
                                 ": invalid tree probabilities; increase the step count");
    }

    const double dt = spec.time / static_cast<double>(steps);
    const double disc = discount_factor(spec.rate, dt);
    const double u_over_d = u / d;

    std::vector<double> v(static_cast<std::size_t>(steps) + 1);
    double s = spec.spot * std::pow(d, static_cast<double>(steps));
    for (int j = 0; j <= steps; ++j) {
        v[static_cast<std::size_t>(j)] = payoff(s, spec.strike, spec.type);
        s *= u_over_d;
    }

    for (int i = steps - 1; i >= 0; --i) {
        double s_down = spec.spot * std::pow(d, static_cast<double>(i));
        for (int j = 0; j <= i; ++j) {
            const double cont =
                disc * (p * v[static_cast<std::size_t>(j) + 1] + (1.0 - p) * v[static_cast<std::size_t>(j)]);
            if (american) {
                v[static_cast<std::size_t>(j)] =
                    std::max(payoff(s_down, spec.strike, spec.type), cont);
            } else {
                v[static_cast<std::size_t>(j)] = cont;
            }
            s_down *= u_over_d;
        }
    }

    PricingResult r;
    r.value = v[0];
    r.work = static_cast<std::uint64_t>(steps);
    r.method = method;
    r.converged = true;
    r.notes = american ? "american" : "european";
    return r;
}

PricingResult crr_impl(const VanillaSpec& spec, int steps, bool american) {
    validate(spec);
    if (steps < 1) {
        throw std::invalid_argument("steps must be positive");
    }
    if (spec.time == 0.0 || spec.vol == 0.0) {
        PricingResult r = bs::price_result(spec);
        r.method = "crr";
        r.work = static_cast<std::uint64_t>(steps);
        return r;
    }
    const double dt = spec.time / static_cast<double>(steps);
    const double u = std::exp(spec.vol * std::sqrt(dt));
    const double d = 1.0 / u;
    const double a = std::exp((spec.rate - spec.dividend) * dt);
    const double p = (a - d) / (u - d);
    return binomial(spec, steps, u, d, p, american, "crr");
}

PricingResult jr_impl(const VanillaSpec& spec, int steps, bool american) {
    validate(spec);
    if (steps < 1) {
        throw std::invalid_argument("steps must be positive");
    }
    if (spec.time == 0.0 || spec.vol == 0.0) {
        PricingResult r = bs::price_result(spec);
        r.method = "jarrow-rudd";
        r.work = static_cast<std::uint64_t>(steps);
        return r;
    }
    const double dt = spec.time / static_cast<double>(steps);
    const double drift = (spec.rate - spec.dividend - 0.5 * spec.vol * spec.vol) * dt;
    const double jump = spec.vol * std::sqrt(dt);
    const double u = std::exp(drift + jump);
    const double d = std::exp(drift - jump);
    return binomial(spec, steps, u, d, 0.5, american, "jarrow-rudd");
}

PricingResult lr_impl(const VanillaSpec& spec, int steps, bool american) {
    validate(spec);
    steps = odd_steps(steps);
    if (spec.time == 0.0 || spec.vol == 0.0) {
        PricingResult r = bs::price_result(spec);
        r.method = "leisen-reimer";
        r.work = static_cast<std::uint64_t>(steps);
        return r;
    }
    double d1 = 0.0;
    double d2 = 0.0;
    bs::d1_d2(spec, d1, d2);
    const double dt = spec.time / static_cast<double>(steps);
    const double p = peizer_pratt(d2, steps);
    const double p_star = peizer_pratt(d1, steps);
    const double growth = std::exp((spec.rate - spec.dividend) * dt);
    if (p <= 0.0 || p >= 1.0 || p_star <= 0.0 || p_star >= 1.0) {
        throw std::runtime_error("leisen-reimer: inversion left the unit interval");
    }
    const double u = growth * p_star / p;
    const double d = (growth - p * u) / (1.0 - p);
    return binomial(spec, steps, u, d, p, american, "leisen-reimer");
}

PricingResult trinomial_impl(const VanillaSpec& spec, int steps, bool american) {
    validate(spec);
    if (steps < 1) {
        throw std::invalid_argument("steps must be positive");
    }
    if (spec.time == 0.0 || spec.vol == 0.0) {
        PricingResult r = bs::price_result(spec);
        r.method = "kamrad-ritchken";
        r.work = static_cast<std::uint64_t>(steps);
        return r;
    }

    const double dt = spec.time / static_cast<double>(steps);
    const double lambda = std::sqrt(3.0);
    const double nu = spec.rate - spec.dividend - 0.5 * spec.vol * spec.vol;
    const double pu = 1.0 / (2.0 * lambda * lambda) +
                      0.5 * nu * std::sqrt(dt) / (lambda * spec.vol);
    const double pd = 1.0 / (2.0 * lambda * lambda) -
                      0.5 * nu * std::sqrt(dt) / (lambda * spec.vol);
    const double pm = 1.0 - 1.0 / (lambda * lambda);
    if (pu < 0.0 || pd < 0.0 || pm < 0.0) {
        throw std::runtime_error(
            "kamrad-ritchken: negative probability; increase the step count");
    }

    const double disc = discount_factor(spec.rate, dt);
    const double dx = lambda * spec.vol * std::sqrt(dt);

    std::vector<double> v(static_cast<std::size_t>(2 * steps + 1));
    std::vector<double> nxt(static_cast<std::size_t>(2 * steps + 1));
    for (int j = 0; j <= 2 * steps; ++j) {
        const int net = j - steps;
        const double s = spec.spot * std::exp(static_cast<double>(net) * dx);
        v[static_cast<std::size_t>(j)] = payoff(s, spec.strike, spec.type);
    }

    for (int i = steps - 1; i >= 0; --i) {
        for (int j = 0; j <= 2 * i; ++j) {
            const double cont = disc * (pd * v[static_cast<std::size_t>(j)] +
                                        pm * v[static_cast<std::size_t>(j) + 1] +
                                        pu * v[static_cast<std::size_t>(j) + 2]);
            if (american) {
                const int net = j - i;
                const double s = spec.spot * std::exp(static_cast<double>(net) * dx);
                nxt[static_cast<std::size_t>(j)] =
                    std::max(payoff(s, spec.strike, spec.type), cont);
            } else {
                nxt[static_cast<std::size_t>(j)] = cont;
            }
        }
        v.swap(nxt);
    }

    PricingResult r;
    r.value = v[0];
    r.work = static_cast<std::uint64_t>(steps);
    r.method = "kamrad-ritchken";
    r.converged = true;
    r.notes = american ? "american" : "european";
    return r;
}

PricingResult dispatch(const VanillaSpec& spec, int steps, TreeModel model, bool american) {
    switch (model) {
        case TreeModel::CoxRossRubinstein:
            return crr_impl(spec, steps, american);
        case TreeModel::JarrowRudd:
            return jr_impl(spec, steps, american);
        case TreeModel::LeisenReimer:
            return lr_impl(spec, steps, american);
        case TreeModel::KamradRitchken:
            return trinomial_impl(spec, steps, american);
    }
    throw std::invalid_argument("unknown tree model");
}

}  // namespace

PricingResult cox_ross_rubinstein(const VanillaSpec& spec, int steps, ExerciseStyle style) {
    return crr_impl(spec, steps, style == ExerciseStyle::American);
}

PricingResult jarrow_rudd(const VanillaSpec& spec, int steps, ExerciseStyle style) {
    return jr_impl(spec, steps, style == ExerciseStyle::American);
}

PricingResult leisen_reimer(const VanillaSpec& spec, int steps, ExerciseStyle style) {
    return lr_impl(spec, steps, style == ExerciseStyle::American);
}

PricingResult kamrad_ritchken(const VanillaSpec& spec, int steps, ExerciseStyle style) {
    return trinomial_impl(spec, steps, style == ExerciseStyle::American);
}

PricingResult price(const VanillaSpec& spec, const TreeConfig& cfg) {
    const bool american = cfg.style == ExerciseStyle::American;
    if (!cfg.richardson) {
        PricingResult r = dispatch(spec, cfg.steps, cfg.model, american);
        if (cfg.steps >= 4) {
            const PricingResult half =
                dispatch(spec, std::max(1, cfg.steps / 2), cfg.model, american);
            r.error_estimate = std::abs(r.value - half.value);
        }
        return r;
    }

    const PricingResult coarse = dispatch(spec, cfg.steps, cfg.model, american);
    const int fine_steps =
        cfg.model == TreeModel::LeisenReimer ? odd_steps(2 * cfg.steps) : 2 * cfg.steps;
    const PricingResult fine = dispatch(spec, fine_steps, cfg.model, american);
    PricingResult r;
    r.value = 2.0 * fine.value - coarse.value;
    r.error_estimate = std::abs(fine.value - coarse.value);
    r.work = coarse.work + fine.work;
    r.method = coarse.method;
    r.converged = true;
    r.notes = std::string(american ? "american" : "european") + ", richardson";
    return r;
}

PricingResult adaptive(const VanillaSpec& spec, const AdaptiveTreeConfig& cfg) {
    if (cfg.abs_tol <= 0.0) {
        throw std::invalid_argument("adaptive abs_tol must be positive");
    }
    int n = cfg.min_steps;
    if (cfg.model == TreeModel::LeisenReimer) {
        n = odd_steps(n);
    }

    PricingResult prev{};
    bool have_prev = false;
    PricingResult last{};

    while (n <= cfg.max_steps) {
        last = dispatch(spec, n, cfg.model, cfg.style == ExerciseStyle::American);
        if (have_prev) {
            last.error_estimate = std::abs(last.value - prev.value);
            last.notes += last.notes.empty() ? "adaptive" : ", adaptive";
            if (last.error_estimate <= cfg.abs_tol) {
                last.converged = true;
                return last;
            }
        }
        prev = last;
        have_prev = true;
        n = cfg.model == TreeModel::LeisenReimer ? odd_steps(2 * n) : 2 * n;
    }

    last.converged = false;
    last.notes = "hit max_steps";
    return last;
}

}  // namespace derivkit::tree
