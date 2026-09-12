#include "derivkit/math.hpp"
#include "harness.hpp"

#include <cmath>
#include <stdexcept>

int main() {
    using derivkit::math::norm_cdf;
    using derivkit::math::norm_inv;
    using derivkit::math::norm_pdf;
    using derivkit::math::norm_sf;

    CHECK_NEAR(norm_cdf(0.0), 0.5, 1e-15);
    CHECK_NEAR(norm_cdf(1.0), 0.8413447460685429, 1e-14);
    CHECK_NEAR(norm_cdf(-1.0), 0.15865525393145705, 1e-14);
    CHECK_NEAR(norm_pdf(0.0), 0.3989422804014327, 1e-15);
    CHECK_NEAR(norm_sf(1.0), 1.0 - norm_cdf(1.0), 1e-15);

    // Round-trip on a log-spaced grid, including far tails.
    for (int i = 1; i < 40; ++i) {
        const double p = std::ldexp(1.0, -i);  // 2^{-i}
        if (p == 0.0) {
            continue;
        }
        CHECK_NEAR(norm_cdf(norm_inv(p)), p, 1e-14);
        CHECK_NEAR(norm_cdf(norm_inv(1.0 - p)), 1.0 - p, 1e-14);
    }
    for (int i = 1; i < 20; ++i) {
        const double p = 0.05 * i;
        CHECK_NEAR(norm_inv(norm_cdf(norm_inv(p))), norm_inv(p), 1e-12);
    }

    bool threw = false;
    try {
        (void)norm_inv(0.0);
    } catch (const std::invalid_argument&) {
        threw = true;
    }
    CHECK(threw);

    return derivkit::test::summarize("test_math");
}
