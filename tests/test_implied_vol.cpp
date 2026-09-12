#include "derivkit/black_scholes.hpp"
#include "derivkit/implied_vol.hpp"
#include "harness.hpp"

int main() {
    using derivkit::OptionType;
    using derivkit::VanillaSpec;
    using derivkit::bs::implied_vol;
    using derivkit::bs::price;

    const VanillaSpec spec{
        .spot = 100.0,
        .strike = 100.0,
        .rate = 0.05,
        .dividend = 0.0,
        .vol = 0.2,
        .time = 1.0,
        .type = OptionType::Call,
    };

    const double px = price(spec);
    VanillaSpec probe = spec;
    probe.vol = 0.0;  // ignored except as a warm start; leave a bad guess
    auto iv = implied_vol(probe, px);
    CHECK(iv.converged);
    CHECK_NEAR(iv.vol, 0.2, 1e-10);
    CHECK_NEAR(iv.residual, 0.0, 1e-12);

    // Deep OTM put, poor Newton start — bisection must still recover σ.
    VanillaSpec otm{
        .spot = 100.0,
        .strike = 70.0,
        .rate = 0.01,
        .dividend = 0.0,
        .vol = 0.35,
        .time = 0.25,
        .type = OptionType::Put,
    };
    const double otm_px = price(otm);
    otm.vol = 1.5;
    iv = implied_vol(otm, otm_px);
    CHECK(iv.converged);
    CHECK_NEAR(iv.vol, 0.35, 1e-8);

    // Grid of round-trips.
    for (double k : {80.0, 90.0, 100.0, 110.0, 120.0}) {
        for (double sig : {0.1, 0.2, 0.5}) {
            VanillaSpec s = spec;
            s.strike = k;
            s.vol = sig;
            s.type = OptionType::Put;
            const double market = price(s);
            s.vol = 0.25;
            iv = implied_vol(s, market);
            CHECK(iv.converged);
            CHECK_NEAR(iv.vol, sig, 1e-8);
        }
    }

    // Price below intrinsic is rejected.
    auto bad = implied_vol(spec, -1.0);
    CHECK(!bad.converged);

    return derivkit::test::summarize("test_implied_vol");
}
