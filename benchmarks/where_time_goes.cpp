// Where the time goes in the C++ kernel.
//
// The path loop is rebuilt one step at a time: first only the random 64-bit draws, then
// the transform to normals on top, then exp, then the full kernel. The cost of a step is
// the time it adds. Timing steps this way, on fresh random numbers, matters: exp, log, sin
// and cos branch on their argument, so a loop over a small buffer of repeated inputs lets
// the CPU's branch predictor learn the answers and reports times that are too low.
//
// The breakdown is printed twice: once for the reproducible generator (mt19937_64 +
// Box-Muller) and once for the fast one (xoshiro256++ + ziggurat). The steps after the
// draw are the same code in both, so the tables show what the generator alone changes.
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

struct Breakdown {
    double uniforms;         // one uniform per path
    double normals;          // one normal per path, drawn in blocks
    double with_exp;         // plus the terminal price
    double with_folded_exp;  // the same price with log(S) inside the exponent
    double kernel;           // the real kernel
    double antithetic;       // the real kernel, one antithetic pair per path
};

// The same measurements for either generator: `Rng` draws the numbers and `Sampler` is
// the kernel built on it.
template <class Rng, class Sampler>
Breakdown breakdown(const derivkit::mc::VanillaSpec& spec) {
    const double spot = spec.spot;
    const double drift = (spec.rate - spec.dividend - 0.5 * spec.vol * spec.vol) * spec.time;
    const double vol_t = spec.vol * std::sqrt(spec.time);
    Breakdown b{};

    // Step 1: one uniform per path. Box-Muller turns two uniforms into two normals, and
    // the ziggurat uses one 64-bit draw for a normal in the common case, so either way
    // this is the generator work behind one normal draw.
    b.uniforms = measure([&](std::uint64_t paths) {
        Rng rng(1);
        double sum = 0.0;
        for (std::uint64_t i = 0; i < paths; ++i) {
            sum += rng.uniform();
        }
        return sum;
    });

    // Step 2: one normal per path, drawn in blocks exactly as the kernel does.
    b.normals = measure([&](std::uint64_t paths) {
        Rng rng(1);
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
    b.with_exp = measure([&](std::uint64_t paths) {
        Rng rng(1);
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
    // path, and this machine's exp is much faster for it. The reproducible kernel cannot
    // use this form because it would round differently from the pure-Python engine (see
    // the walkthrough); the fast kernel shares the path loop, so it does not use it either.
    const double log_spot = std::log(spot);
    b.with_folded_exp = measure([&](std::uint64_t paths) {
        Rng rng(1);
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
    b.kernel = measure([&](std::uint64_t paths) {
        Sampler sampler(spec, 1, false);
        sampler.advance(paths);
        return sampler.moments().mean_y;
    });

    b.antithetic = measure([&](std::uint64_t paths) {
        Sampler sampler(spec, 1, true);
        sampler.advance(paths);
        return sampler.moments().mean_y;
    });
    return b;
}

void table(const char* title, const char* draw, const char* transform, const Breakdown& b) {
    std::printf("| %-52s | %6s |\n", title, "ns");
    std::printf("| %-52s | %6s |\n", "---", "---:");
    row(draw, b.uniforms);
    row(transform, b.normals - b.uniforms);
    row("exp for the terminal price", b.with_exp - b.normals);
    row("payoff and Welford update", b.kernel - b.with_exp);
    row("whole kernel, one path", b.kernel);
    row("whole kernel, one antithetic pair", b.antithetic);
    std::printf("\n");
    row("not used: exp with log(S) inside the exponent", b.with_folded_exp - b.normals);
    std::printf("\n");
}

}  // namespace

int main() {
    namespace mc = derivkit::mc;

    // The option every benchmark in this repo uses: S = K = 100, r = 5%, q = 0, vol = 20%, T = 1.
    const mc::VanillaSpec spec{100.0, 100.0, 0.05, 0.0, 0.2, 1.0, mc::OptionType::Call};

    const Breakdown slow = breakdown<derivkit::NormalRng, mc::EuropeanSampler>(spec);
    const Breakdown fast = breakdown<derivkit::FastNormalRng, mc::FastEuropeanSampler>(spec);

    table("C++ kernel, cost per path", "mt19937_64 draw, converted to a uniform",
          "Box-Muller transform (log, sqrt, sin, cos)", slow);
    table("C++ kernel with the fast generator, cost per path",
          "xoshiro256++ draw, converted to a uniform",
          "ziggurat (one table lookup; exp or log for 1.5%)", fast);
    return 0;
}
