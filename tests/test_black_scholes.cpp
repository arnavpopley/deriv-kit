#include "derivkit/black_scholes.hpp"
#include "harness.hpp"

#include <cmath>
#include <stdexcept>

int main() {
    using derivkit::OptionType;
    using derivkit::VanillaSpec;
    using derivkit::bs::geometric_asian;
    using derivkit::bs::greeks;
    using derivkit::bs::price;

    const VanillaSpec atm{
        .spot = 100.0,
        .strike = 100.0,
        .rate = 0.05,
        .dividend = 0.0,
        .vol = 0.2,
        .time = 1.0,
        .type = OptionType::Call,
    };

    CHECK_NEAR(price(atm), 10.450583572185565, 1e-12);
    VanillaSpec atm_put = atm;
    atm_put.type = OptionType::Put;
    CHECK_NEAR(price(atm_put), 5.573526022256971, 1e-12);

    const double parity = price(atm) - price(atm_put);
    const double fwd_gap = atm.spot - atm.strike * std::exp(-atm.rate * atm.time);
    CHECK_NEAR(parity, fwd_gap, 1e-12);

    const auto g = greeks(atm);
    CHECK_NEAR(g.d1, 0.35, 1e-12);
    CHECK_NEAR(g.d2, 0.15, 1e-12);
    CHECK_NEAR(g.delta, 0.6368306511756191, 1e-12);
    CHECK_NEAR(g.gamma, 0.018762017345846895, 1e-12);
    CHECK_NEAR(g.vega, 37.52403469169379, 1e-10);
    CHECK_NEAR(g.theta, -6.414027546438197, 1e-12);
    CHECK_NEAR(g.rho, 53.232481545376345, 1e-10);
    CHECK_NEAR(g.vanna, -0.28143026018770345, 1e-12);
    CHECK_NEAR(g.volga, 9.850059106569622, 1e-10);

    const auto gp = greeks(atm_put);
    CHECK_NEAR(gp.delta, -0.3631693488243809, 1e-12);
    CHECK_NEAR(gp.gamma, g.gamma, 1e-15);  // gamma is shared
    CHECK_NEAR(gp.vega, g.vega, 1e-15);

    const VanillaSpec otm{
        .spot = 100.0,
        .strike = 110.0,
        .rate = 0.05,
        .dividend = 0.02,
        .vol = 0.25,
        .time = 0.75,
        .type = OptionType::Call,
    };
    CHECK_NEAR(price(otm), 5.584270225140479, 1e-12);
    VanillaSpec otm_put = otm;
    otm_put.type = OptionType::Put;
    CHECK_NEAR(price(otm_put), 13.024462214124618, 1e-12);

    const VanillaSpec short_dated{
        .spot = 50.0,
        .strike = 50.0,
        .rate = 0.10,
        .dividend = 0.0,
        .vol = 0.40,
        .time = 0.25,
        .type = OptionType::Call,
    };
    CHECK_NEAR(price(short_dated), 4.5814555505432395, 1e-12);

    const VanillaSpec hull{
        .spot = 36.0,
        .strike = 40.0,
        .rate = 0.06,
        .dividend = 0.0,
        .vol = 0.20,
        .time = 1.0,
        .type = OptionType::Put,
    };
    CHECK_NEAR(price(hull), 3.84430779159684, 1e-12);

    CHECK_NEAR(geometric_asian(atm, 50), 5.641058127824213, 1e-12);

    // Black-76 coincides with Black-Scholes when F = S e^{(r-q)T}, DF = e^{-rT}.
    using derivkit::bs::to_black;
    CHECK_NEAR(price(to_black(atm)), price(atm), 1e-12);
    CHECK_NEAR(price(to_black(atm_put)), price(atm_put), 1e-12);
    CHECK_NEAR(price(to_black(otm)), price(otm), 1e-12);
    CHECK_NEAR(price(to_black(otm_put)), price(otm_put), 1e-12);
    CHECK_NEAR(greeks(to_black(atm)).vega, greeks(atm).vega, 1e-10);

    // Expiry: option collapses to the intrinsic.
    VanillaSpec expired = atm;
    expired.time = 0.0;
    CHECK_NEAR(price(expired), 0.0, 1e-15);
    expired.spot = 120.0;
    CHECK_NEAR(price(expired), 20.0, 1e-15);

    // Zero vol: discounted intrinsic of the forward.
    VanillaSpec det = atm;
    det.vol = 0.0;
    const double det_call = std::exp(-0.05) * (100.0 * std::exp(0.05) - 100.0);
    CHECK_NEAR(price(det), det_call, 1e-12);

    bool threw = false;
    try {
        VanillaSpec bad = atm;
        bad.spot = -1.0;
        (void)price(bad);
    } catch (const std::invalid_argument&) {
        threw = true;
    }
    CHECK(threw);

    return derivkit::test::summarize("test_black_scholes");
}
