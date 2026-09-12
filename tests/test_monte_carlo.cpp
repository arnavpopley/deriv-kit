#include "derivkit/black_scholes.hpp"
#include "derivkit/monte_carlo.hpp"
#include "harness.hpp"

#include <algorithm>
#include <cmath>

int main() {
    using derivkit::OptionType;
    using derivkit::VarianceReduction;
    using derivkit::VanillaSpec;
    using derivkit::bs::geometric_asian;
    using derivkit::bs::price;
    using derivkit::mc::arithmetic_asian;
    using derivkit::mc::european;
    using derivkit::mc::european_adaptive;

    const VanillaSpec eu{
        .spot = 100.0,
        .strike = 100.0,
        .rate = 0.05,
        .dividend = 0.0,
        .vol = 0.2,
        .time = 1.0,
        .type = OptionType::Call,
    };
    const double bs = price(eu);

    derivkit::mc::McConfig cfg;
    cfg.paths = 20000;
    cfg.seed = 7;

    const auto crude = european(eu, cfg);
    CHECK(std::abs(crude.value - bs) < 6.0 * crude.error_estimate);

    cfg.vr = VarianceReduction::Antithetic;
    const auto anti = european(eu, cfg);
    CHECK(std::abs(anti.value - bs) < 6.0 * anti.error_estimate);
    CHECK(anti.error_estimate < crude.error_estimate);

    cfg.vr = VarianceReduction::ControlVariate;
    const auto cv = european(eu, cfg);
    CHECK(std::abs(cv.value - bs) < 6.0 * cv.error_estimate);
    CHECK(cv.error_estimate < crude.error_estimate);

    cfg.vr = VarianceReduction::Antithetic | VarianceReduction::ControlVariate;
    const auto both = european(eu, cfg);
    CHECK(std::abs(both.value - bs) < 6.0 * both.error_estimate);
    CHECK(both.error_estimate < anti.error_estimate);

    derivkit::mc::AdaptiveMcConfig acfg;
    acfg.base.paths = 0;
    acfg.base.seed = 11;
    acfg.base.vr = VarianceReduction::Antithetic | VarianceReduction::ControlVariate;
    acfg.stderr_tol = 5e-3;
    acfg.batch = 5000;
    acfg.max_paths = 200000;
    const auto ad = european_adaptive(eu, acfg);
    CHECK(ad.converged);
    CHECK(ad.error_estimate <= 5e-3 * 1.01);
    CHECK(std::abs(ad.value - bs) < 6.0 * std::max(ad.error_estimate, 1e-8));

    // Geometric Asian control: the control itself must recover the closed form
    // when the arithmetic average is replaced by the geometric one - checked by
    // pricing the geometric option through BS and ensuring the CV Asian is at
    // least as tight as crude Asian.
    derivkit::mc::AsianConfig asian;
    asian.mc.paths = 8000;
    asian.mc.seed = 3;
    asian.steps = 50;
    const auto asian_crude = arithmetic_asian(eu, asian);
    asian.mc.vr = VarianceReduction::ControlVariate;
    const auto asian_cv = arithmetic_asian(eu, asian);
    CHECK(asian_cv.error_estimate < asian_crude.error_estimate);
    CHECK(asian_cv.value > geometric_asian(eu, 50));  // arithmetic >= geometric in convexity
    CHECK(asian_cv.value > 0.0);

    return derivkit::test::summarize("test_monte_carlo");
}
