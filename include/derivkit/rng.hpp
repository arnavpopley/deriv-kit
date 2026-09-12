#pragma once

#include <cstdint>
#include <random>

namespace derivkit {

/// Reproducible normal generator used by every Monte Carlo path.
///
/// Box-Muller on top of `std::mt19937_64`. One engine per pricer call; the
/// library never shares mutable RNG state across threads.
class NormalRng {
public:
    explicit NormalRng(std::uint64_t seed);

    /// i.i.d. N(0, 1).
    [[nodiscard]] double normal();

    /// U(0, 1) with the endpoints excluded so logarithms stay finite.
    [[nodiscard]] double uniform();

    void discard_spare() noexcept { has_spare_ = false; }

private:
    std::mt19937_64 gen_;
    bool has_spare_ = false;
    double spare_ = 0.0;
};

}  // namespace derivkit
