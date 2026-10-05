// Where the time goes in the C++ kernel.
//
// The path loop is rebuilt one step at a time: first only the random 64-bit draws, then
// the Box-Muller transform on top, then exp, then the full kernel. The cost of a step is
// the time it adds. Timing steps this way, on fresh random numbers, matters: exp, log, sin
// and cos branch on their argument, so a loop over a small buffer of repeated inputs lets
// the CPU's branch predictor learn the answers and reports times that are too low.
//
//   cmake --build build --target where_time_goes && ./build/where_time_goes
//
// The target is built with the same flags as the extension.
#include "monte_carlo.hpp"

#include <algorithm>
#include <array>
#include <chrono>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <cstdio>
#include <span>

namespace {

constexpr std::uint64_t kPaths = 2'000'000;  // per measurement
constexpr int kRepeats = 7;                  // measurements; the median is reported
constexpr std::size_t kBlock = 256;          // same block size as the kernel

// Writing results here stops the compiler from deleting work whose result is unused.
volatile double g_sink = 0.0;

double seconds_now() {
    using clock = std::chrono::steady_clock;
    return std::chrono::duration<double>(clock::now().time_since_epoch()).count();
}

// Median nanoseconds per path over kRepeats runs of `run(kPaths)`.
template <class Run>
double measure(Run run) {
    std::array<double, kRepeats> ns{};
    run(kPaths);  // warm-up
    for (double& slot : ns) {
        const double start = seconds_now();
        g_sink = g_sink + run(kPaths);
        slot = (seconds_now() - start) / static_cast<double>(kPaths) * 1e9;
    }
    std::sort(ns.begin(), ns.end());
    return ns[kRepeats / 2];
}

void row(const char* name, double ns) { std::printf("| %-52s | %6.2f |\n", name, ns); }

}  // namespace

int main() {
    using derivkit::NormalRng;
    namespace mc = derivkit::mc;

    // The option every benchmark in this repo uses: S = K = 100, r = 5%, q = 0, vol = 20%, T = 1.
    const mc::VanillaSpec spec{100.0, 100.0, 0.05, 0.0, 0.2, 1.0, mc::OptionType::Call};
    const double spot = spec.spot;
    const double drift = (spec.rate - spec.dividend - 0.5 * spec.vol * spec.vol) * spec.time;
    const double vol_t = spec.vol * std::sqrt(spec.time);

    // Step 1: one uniform per path. Box-Muller turns two uniforms into two normals, so
    // this is exactly the generator work behind one normal draw.
    const double uniforms = measure([&](std::uint64_t paths) {
        NormalRng rng(1);
        double sum = 0.0;
        for (std::uint64_t i = 0; i < paths; ++i) {
            sum += rng.uniform();
        }
        return sum;
    });

    // Step 2: one normal per path, drawn in blocks exactly as the kernel does.
    const double normals = measure([&](std::uint64_t paths) {
        NormalRng rng(1);
        std::array<double, kBlock> z;
        double sum = 0.0;
        for (std::uint64_t done = 0; done < paths; done += kBlock) {
            rng.fill(z);
            for (const double zi : z) {
                sum += zi;
            }
        }
        return sum;
    });

    // Step 3: the same, plus the terminal price S_T = S exp(drift + vol_t z).
    const double with_exp = measure([&](std::uint64_t paths) {
        NormalRng rng(1);
        std::array<double, kBlock> z;
        double sum = 0.0;
        for (std::uint64_t done = 0; done < paths; done += kBlock) {
            rng.fill(z);
            for (const double zi : z) {
                sum += spot * std::exp(drift + vol_t * zi);
            }
        }
        return sum;
    });

    // Not what the kernel does: the same price with log(S) moved inside the exponent. The
    // argument of exp then stays well above zero instead of changing sign from path to
    // path, and this machine's exp is much faster for it. The kernel cannot use this form
    // because it would round differently from the pure-Python engine (see the walkthrough).
    const double log_spot = std::log(spot);
    const double with_folded_exp = measure([&](std::uint64_t paths) {
        NormalRng rng(1);
        std::array<double, kBlock> z;
        double sum = 0.0;
        for (std::uint64_t done = 0; done < paths; done += kBlock) {
            rng.fill(z);
            for (const double zi : z) {
                sum += std::exp(log_spot + drift + vol_t * zi);
            }
        }
        return sum;
    });

    // Step 4: the real kernel, which adds the payoff and the Welford update.
    const double kernel = measure([&](std::uint64_t paths) {
        mc::EuropeanSampler sampler(spec, 1, false);
        sampler.advance(paths);
        return sampler.moments().mean_y;
    });

    const double antithetic = measure([&](std::uint64_t paths) {
        mc::EuropeanSampler sampler(spec, 1, true);
        sampler.advance(paths);
        return sampler.moments().mean_y;
    });

    std::printf("| %-52s | %6s |\n", "C++ kernel, cost per path", "ns");
    std::printf("| %-52s | %6s |\n", "---", "---:");
    row("mt19937_64 draw, converted to a uniform", uniforms);
    row("Box-Muller transform (log, sqrt, sin, cos)", normals - uniforms);
    row("exp for the terminal price", with_exp - normals);
    row("payoff and Welford update", kernel - with_exp);
    row("whole kernel, one path", kernel);
    row("whole kernel, one antithetic pair", antithetic);
    std::printf("\n");
    row("not used: exp with log(S) inside the exponent", with_folded_exp - normals);
    return 0;
}
