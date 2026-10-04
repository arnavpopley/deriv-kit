#include "monte_carlo.hpp"

#include <algorithm>
#include <array>
#include <cmath>
#include <cstddef>
#include <span>
#include <stdexcept>

namespace derivkit::mc {
namespace {  // unnamed namespace: these helpers are visible in this file only

// Normals are drawn in blocks of this many, into a buffer on the stack.
// 256 doubles = 2 KB: small enough to stay in the L1 cache with everything else.
constexpr std::size_t kBlock = 256;

// `inline` + defined before use: the compiler pastes this into the loop, so there is no
// function call per path. `is_call` never changes inside a loop, so the branch costs nothing.
inline double payoff(double price, double strike, bool is_call) {
    return is_call ? std::max(price - strike, 0.0) : std::max(strike - price, 0.0);
}

}  // namespace

EuropeanSampler::EuropeanSampler(const VanillaSpec& spec, std::uint64_t seed, bool antithetic)
    // Member initialiser list: members are constructed directly with these values, in the
    // order they are declared in the class.
    : spot_(spec.spot),
      strike_(spec.strike),
      drift_((spec.rate - spec.dividend - 0.5 * spec.vol * spec.vol) * spec.time),
      vol_t_(spec.vol * std::sqrt(spec.time)),
      df_(std::exp(-spec.rate * spec.time)),
      is_call_(spec.type == OptionType::Call),
      antithetic_(antithetic),
      rng_(seed) {}

void EuropeanSampler::advance(std::uint64_t paths) {
    // Copy the state into local variables for the duration of the loop. The compiler
    // cannot see inside exp/log/sin/cos, so it must assume those calls might change
    // anything reachable through `this`, and would reload and store the members around
    // every call. It knows nothing else can touch a local, so locals stay in registers.
    const double spot = spot_;
    const double strike = strike_;
    const double drift = drift_;
    const double vol_t = vol_t_;
    const double df = df_;
    const bool is_call = is_call_;
    const bool antithetic = antithetic_;
    NormalRng rng = rng_;
    WelfordPair acc = acc_;

    // std::array is a fixed-size array that lives on the stack: creating it moves the
    // stack pointer and nothing else. No heap allocation happens anywhere in this function.
    std::array<double, kBlock> z;

    std::uint64_t remaining = paths;
    while (remaining > 0) {
        const std::size_t m = static_cast<std::size_t>(std::min<std::uint64_t>(remaining, kBlock));

        // Two tight loops instead of one mixed loop: first all the random numbers for the
        // block, then all the payoffs. Each loop then does one kind of work, which the
        // CPU pipelines better. The draws are consumed in the same order either way, so
        // the result is identical to drawing one normal per path.
        rng.fill(std::span<double>(z.data(), m));

        for (std::size_t i = 0; i < m; ++i) {
            const double up = spot * std::exp(drift + vol_t * z[i]);
            double x = df * up;                           // discounted S_T (the control)
            double y = df * payoff(up, strike, is_call);  // discounted payoff
            if (antithetic) {
                // Reuse the same draw with its sign flipped and average the two results.
                const double down = spot * std::exp(drift + vol_t * -z[i]);
                x = 0.5 * (x + df * down);
                y = 0.5 * (y + df * payoff(down, strike, is_call));
            }
            acc.add(x, y);
        }
        remaining -= m;
    }

    // Write the advanced state back so the next call continues the same stream.
    rng_ = rng;
    acc_ = acc;
}

AsianSampler::AsianSampler(const VanillaSpec& spec, std::uint32_t steps, std::uint64_t seed,
                           bool antithetic)
    : spot_(spec.spot),
      strike_(spec.strike),
      drift_(0.0),
      vol_dt_(0.0),
      df_(std::exp(-spec.rate * spec.time)),
      nfix_(static_cast<double>(steps)),
      is_call_(spec.type == OptionType::Call),
      antithetic_(antithetic),
      z_(steps),  // the one heap allocation: `steps` doubles, reused by every path
      rng_(seed) {
    if (steps == 0) {
        // pybind11 turns this C++ exception into a Python ValueError.
        throw std::invalid_argument("asian steps must be positive");
    }
    const double dt = spec.time / nfix_;
    drift_ = (spec.rate - spec.dividend - 0.5 * spec.vol * spec.vol) * dt;
    vol_dt_ = spec.vol * std::sqrt(dt);
}

void AsianSampler::advance(std::uint64_t paths) {
    // Locals for the same reason as in EuropeanSampler::advance: the compiler can keep
    // them in registers across the exp and log calls.
    const double spot = spot_;
    const double strike = strike_;
    const double drift = drift_;
    const double vol_dt = vol_dt_;
    const double df = df_;
    const double nfix = nfix_;
    const bool is_call = is_call_;
    const bool antithetic = antithetic_;
    NormalRng rng = rng_;
    WelfordPair acc = acc_;

    // A span is a pointer and a length: a view of the member buffer, not a copy of it.
    // Nothing inside the path loop allocates.
    const std::span<double> z(z_);

    struct Sample {
        double x;  // discounted geometric-average payoff
        double y;  // discounted arithmetic-average payoff
    };

    // A lambda is a function defined in place. [&] lets it use the variables above by
    // reference, so nothing is copied. `sign` is +1 for the path and -1 for its mirror.
    auto walk = [&](double sign) -> Sample {
        const double step_vol = vol_dt * sign;
        double s = spot;
        double sum = 0.0;
        double logsum = 0.0;
        for (const double zk : z) {  // range-for: visits each element, no index needed
            s *= std::exp(drift + step_vol * zk);
            sum += s;
            logsum += std::log(s);
        }
        return {df * payoff(std::exp(logsum / nfix), strike, is_call),
                df * payoff(sum / nfix, strike, is_call)};
    };

    for (std::uint64_t p = 0; p < paths; ++p) {
        rng.fill(z);
        const Sample a = walk(1.0);
        if (!antithetic) {
            acc.add(a.x, a.y);
        } else {
            const Sample b = walk(-1.0);  // same draws, signs flipped
            acc.add(0.5 * (a.x + b.x), 0.5 * (a.y + b.y));
        }
    }

    rng_ = rng;
    acc_ = acc;
}

}  // namespace derivkit::mc
