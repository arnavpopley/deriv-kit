#include "derivkit/implied_forward.hpp"
#include "derivkit/types.hpp"
#include "harness.hpp"

#include <algorithm>
#include <cmath>
#include <vector>

int main() {
    using derivkit::CallPutQuote;
    using derivkit::imply_forward;

    const double spot = 25000.0;
    const double time_rate = 17.0 / 365.0;
    const double rate = 0.065;
    const double dividend = 0.012;
    const double df = derivkit::discount_factor(rate, time_rate);
    const double fwd = derivkit::forward_price(spot, rate, dividend, time_rate);

    std::vector<CallPutQuote> quotes;
    for (double k : {24400.0, 24700.0, 25000.0, 25300.0, 25600.0}) {
        const double parity = df * (fwd - k);
        CallPutQuote q;
        q.strike = k;
        q.call = std::max(parity, 0.0) + 80.0;
        q.put = std::max(-parity, 0.0) + 80.0;
        q.weight = 1.0;
        quotes.push_back(q);
    }

    const auto fit = imply_forward(spot, time_rate, quotes);
    CHECK(fit.ok);
    CHECK(fit.pairs == 5);
    CHECK_NEAR(fit.forward, fwd, 1e-8);
    CHECK_NEAR(fit.discount, df, 1e-10);
    CHECK_NEAR(fit.rate, rate, 1e-10);
    CHECK_NEAR(fit.dividend, dividend, 1e-10);

    const auto empty = imply_forward(spot, time_rate, {});
    CHECK(!empty.ok);

    return derivkit::test::summarize("test_implied_forward");
}
