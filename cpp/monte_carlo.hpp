#pragma once

#include "rng.hpp"
#include "welford.hpp"

#include <cstdint>
#include <vector>

// The C++ Monte Carlo kernel. It does one job: simulate paths and accumulate moments.
// Input validation, the closed-form control mean and the control-variate finish stay in
// Python (derivkit.monte_carlo), where all three back ends share them.
namespace derivkit::mc {

enum class OptionType { Call, Put };

/// Market and contract inputs for an option on a geometric Brownian motion spot.
struct VanillaSpec {
    double spot = 0.0;
    double strike = 0.0;
    double rate = 0.0;      // continuous risk-free rate r
    double dividend = 0.0;  // continuous dividend yield q
    double vol = 0.0;
    double time = 0.0;      // years to expiry T
    OptionType type = OptionType::Call;
};

/// European vanilla by exact terminal sampling: S_T = S_0 exp((r - q - vol^2/2) T + vol sqrt(T) Z).
///
/// The sampler keeps its generator and its moments between calls, so `advance` can be
/// called batch after batch (that is how the adaptive pricer uses it) and the result is
/// the same as one big call.
///
/// Not thread-safe: one sampler belongs to one pricing call.
class EuropeanSampler {
public:
    EuropeanSampler(const VanillaSpec& spec, std::uint64_t seed, bool antithetic);

    /// Simulate `paths` more paths. With antithetic on, each path is a +Z / -Z pair.
    void advance(std::uint64_t paths);

    // [[nodiscard]]: the compiler warns if a caller ignores the result.
    // noexcept: this cannot throw, which the compiler and the reader can both rely on.
    [[nodiscard]] const WelfordPair& moments() const noexcept { return acc_; }

private:
    // Everything that is the same for every path is computed once, in the constructor.
    double spot_;
    double strike_;
    double drift_;   // (r - q - vol^2/2) T
    double vol_t_;   // vol sqrt(T)
    double df_;      // exp(-r T)
    bool is_call_;
    bool antithetic_;
    NormalRng rng_;
    WelfordPair acc_;
};

/// Arithmetic-average Asian with `steps` fixings. x is the discounted geometric-average
/// payoff (the control), y the discounted arithmetic-average payoff.
///
/// Like EuropeanSampler it keeps its generator and moments between calls, so `advance`
/// can be called in slices and the result is the same as one big call. Not thread-safe.
class AsianSampler {
public:
    /// Throws std::invalid_argument if `steps` is zero.
    AsianSampler(const VanillaSpec& spec, std::uint32_t steps, std::uint64_t seed,
                 bool antithetic);

    /// Simulate `paths` more paths. With antithetic on, each path is a +Z / -Z pair.
    void advance(std::uint64_t paths);

    [[nodiscard]] const WelfordPair& moments() const noexcept { return acc_; }

private:
    double spot_;
    double strike_;
    double drift_;    // (r - q - vol^2/2) dt
    double vol_dt_;   // vol sqrt(dt)
    double df_;       // exp(-r T)
    double nfix_;     // number of fixings, as a double
    bool is_call_;
    bool antithetic_;
    // One path's draws. The number of fixings is only known at run time, so this cannot
    // be a std::array. It is the one heap allocation of the sampler: made once, in the
    // constructor, and reused by every path.
    std::vector<double> z_;
    NormalRng rng_;
    WelfordPair acc_;
};

}  // namespace derivkit::mc
