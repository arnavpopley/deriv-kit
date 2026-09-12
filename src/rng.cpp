#include "derivkit/rng.hpp"

#include <cmath>
#include <numbers>

namespace derivkit {

NormalRng::NormalRng(std::uint64_t seed) : gen_(seed) {}

double NormalRng::uniform() {
    // (0, 1) open interval: map integers 1..2^64-1 into (0, 1).
    std::uint64_t u = gen_();
    if (u == 0) {
        u = 1;
    }
    return std::ldexp(static_cast<double>(u), -64);
}

double NormalRng::normal() {
    if (has_spare_) {
        has_spare_ = false;
        return spare_;
    }
    const double u1 = uniform();
    const double u2 = uniform();
    const double r = std::sqrt(-2.0 * std::log(u1));
    const double theta = 2.0 * std::numbers::pi * u2;
    spare_ = r * std::sin(theta);
    has_spare_ = true;
    return r * std::cos(theta);
}

}  // namespace derivkit
