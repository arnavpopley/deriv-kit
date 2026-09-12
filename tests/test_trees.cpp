#include "derivkit/black_scholes.hpp"
#include "derivkit/trees.hpp"
#include "harness.hpp"

#include <cmath>

int main() {
    using derivkit::ExerciseStyle;
    using derivkit::OptionType;
    using derivkit::TreeModel;
    using derivkit::VanillaSpec;
    using derivkit::bs::price;
    using derivkit::tree::adaptive;
    using derivkit::tree::cox_ross_rubinstein;
    using derivkit::tree::jarrow_rudd;
    using derivkit::tree::kamrad_ritchken;
    using derivkit::tree::leisen_reimer;

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

    // CRR / trinomial must approach BS; LR is designed to be close at modest N.
    const auto crr_n = cox_ross_rubinstein(eu, 1000);
    CHECK_NEAR(crr_n.value, bs, 5e-3);
    const auto tri_n = kamrad_ritchken(eu, 1000);
    CHECK_NEAR(tri_n.value, bs, 5e-3);
    const auto jr_n = jarrow_rudd(eu, 1000);
    CHECK_NEAR(jr_n.value, bs, 5e-3);
    const auto lr = leisen_reimer(eu, 101);
    CHECK_NEAR(lr.value, bs, 5e-4);

    // Error diagnostic shrinks as N grows (CRR, same option).
    const auto crr_coarse = cox_ross_rubinstein(eu, 50);
    CHECK(std::abs(crr_n.value - bs) < std::abs(crr_coarse.value - bs));

    // Richardson should beat the coarse tree on this smooth European.
    derivkit::tree::TreeConfig cfg;
    cfg.steps = 200;
    cfg.model = TreeModel::CoxRossRubinstein;
    cfg.richardson = true;
    const auto rich = derivkit::tree::price(eu, cfg);
    CHECK(std::abs(rich.value - bs) < std::abs(crr_coarse.value - bs));

    // American put: early exercise premium is strictly positive.
    const VanillaSpec am{
        .spot = 36.0,
        .strike = 40.0,
        .rate = 0.06,
        .dividend = 0.0,
        .vol = 0.20,
        .time = 1.0,
        .type = OptionType::Put,
    };
    const double eu_put = price(am);
    const auto am_crr = cox_ross_rubinstein(am, 401, ExerciseStyle::American);
    const auto eu_crr = cox_ross_rubinstein(am, 401, ExerciseStyle::European);
    CHECK(am_crr.value > eu_put);
    CHECK(am_crr.value > eu_crr.value);
    CHECK_NEAR(eu_crr.value, eu_put, 5e-3);
    CHECK_NEAR(am_crr.value, 4.4866573200158, 5e-3);

    const auto am_tri = kamrad_ritchken(am, 401, ExerciseStyle::American);
    CHECK_NEAR(am_tri.value, 4.4852773512221455, 5e-3);

    // Adaptive Leisen-Reimer on a European should land inside the tolerance.
    derivkit::tree::AdaptiveTreeConfig acfg;
    acfg.model = TreeModel::LeisenReimer;
    acfg.abs_tol = 1e-5;
    acfg.min_steps = 51;
    acfg.max_steps = 2001;
    const auto ad = adaptive(eu, acfg);
    CHECK(ad.converged);
    CHECK_NEAR(ad.value, bs, 1e-4);

    return derivkit::test::summarize("test_trees");
}
