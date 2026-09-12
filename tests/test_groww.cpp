#include "groww_api.hpp"
#include "derivkit/black_scholes.hpp"
#include "derivkit/implied_vol.hpp"
#include "harness.hpp"

#include <cmath>

#ifndef DERIVKIT_FIXTURE
#define DERIVKIT_FIXTURE "examples/data/nifty_chain.json"
#endif

int main() {
    using derivkit::OptionType;
    using derivkit::VanillaSpec;
    using derivkit::bs::implied_vol;
    using derivkit::bs::price;
    using derivkit::groww::load_fixture;
    using derivkit::groww::nearest_expiry;

    const auto chain = load_fixture(DERIVKIT_FIXTURE);
    CHECK(chain.underlying == "NIFTY");
    CHECK(chain.expiry_date == "2026-09-29");
    CHECK_NEAR(chain.spot, 25012.4, 1e-9);
    CHECK(chain.contracts.size() >= 20);

    CHECK(chain.year_fraction > 0.0);
    const double T = chain.year_fraction;

    // ATM call: BS using Groww IV should sit close to LTP (fixture has ~0.4% noise).
    const derivkit::groww::Contract* atm = nullptr;
    double best = 1e300;
    for (const auto& c : chain.contracts) {
        if (c.type != OptionType::Call) {
            continue;
        }
        const double d = std::abs(c.strike - chain.spot);
        if (d < best) {
            best = d;
            atm = &c;
        }
    }
    CHECK(atm != nullptr);
    VanillaSpec spec{
        .spot = chain.spot,
        .strike = atm->strike,
        .rate = chain.rate,
        .dividend = chain.dividend,
        .vol = atm->groww_iv,
        .time = T,
        .type = OptionType::Call,
    };
    const double bs_px = price(spec);
    CHECK(std::abs(bs_px - atm->ltp) / atm->ltp < 0.02);

    spec.vol = 0.2;
    const auto iv = implied_vol(spec, atm->ltp);
    CHECK(iv.converged);
    CHECK(std::abs(iv.vol - atm->groww_iv) < 0.015);

    const auto near = nearest_expiry({"2026-09-15", "2026-09-22", "2026-09-29"}, "2026-09-12");
    CHECK(near == "2026-09-15");

    return derivkit::test::summarize("test_groww");
}
