// How fast is each normal generator on its own?
//
// The loop here does nothing but draw: no exp, no payoff, no statistics. That isolates the
// cost of the generator, so a change in the kernel's speed can be attributed to the
// generator alone. Normals are drawn in blocks of 256 into a buffer, exactly as the kernel
// draws them.
//
//   cmake --build build --target rng_speed && ./build/rng_speed
//
// The target is built with the same flags as the extension.
#include "rng.hpp"

#include <algorithm>
#include <array>
#include <chrono>
#include <cstddef>
#include <cstdint>
#include <cstdio>
#include <span>

namespace {

constexpr std::uint64_t kDraws = 20'000'000;  // per measurement
constexpr int kRepeats = 7;                   // measurements; the median is reported
constexpr std::size_t kBlock = 256;           // same block size as the kernel

// Tells the compiler that the memory behind `p` may be read here, so it cannot delete the
// work that filled it. It emits no instructions. Summing the draws instead would add a
// chain of floating-point additions to the very thing being timed.
inline void keep(const void* p) { __asm__ __volatile__("" : : "g"(p) : "memory"); }

double seconds_now() {
    using clock = std::chrono::steady_clock;
    return std::chrono::duration<double>(clock::now().time_since_epoch()).count();
}

// Median nanoseconds per draw over kRepeats runs of `run(kDraws)`, after a warm-up.
template <class Run>
double measure(Run run) {
    std::array<double, kRepeats> ns{};
    run(kDraws);
    for (double& slot : ns) {
        const double start = seconds_now();
        run(kDraws);
        slot = (seconds_now() - start) / static_cast<double>(kDraws) * 1e9;
    }
    std::sort(ns.begin(), ns.end());
    return ns[kRepeats / 2];
}

// One 64-bit draw converted to a uniform, per iteration.
template <derivkit::NormalGenerator Rng>
double uniform_ns() {
    return measure([](std::uint64_t draws) {
        Rng rng(1);
        std::array<double, kBlock> u;
        for (std::uint64_t done = 0; done < draws; done += kBlock) {
            for (double& slot : u) {
                slot = rng.uniform();
            }
            keep(u.data());
        }
    });
}

// One normal per iteration, in blocks.
template <derivkit::NormalGenerator Rng>
double normal_ns() {
    return measure([](std::uint64_t draws) {
        Rng rng(1);
        std::array<double, kBlock> z;
        for (std::uint64_t done = 0; done < draws; done += kBlock) {
            rng.fill(z);
            keep(z.data());
        }
    });
}

void row(const char* generator, const char* draw, double ns) {
    std::printf("| %-38s | %-7s | %5.2f | %7.1f M |\n", generator, draw, ns, 1e3 / ns);
}

}  // namespace

int main() {
    using derivkit::FastNormalRng;
    using derivkit::NormalRng;

    const double slow_uniform = uniform_ns<NormalRng>();
    const double slow_normal = normal_ns<NormalRng>();
    const double fast_uniform = uniform_ns<FastNormalRng>();
    const double fast_normal = normal_ns<FastNormalRng>();

    std::printf("| %-38s | %-7s | %5s | %9s |\n", "Generator", "Draw", "ns", "Draws / s");
    std::printf("| %-38s | %-7s | %5s | %9s |\n", "---", "---", "---:", "---:");
    row("reproducible: mt19937_64 + Box-Muller", "uniform", slow_uniform);
    row("reproducible: mt19937_64 + Box-Muller", "normal", slow_normal);
    row("fast: xoshiro256++ + ziggurat", "uniform", fast_uniform);
    row("fast: xoshiro256++ + ziggurat", "normal", fast_normal);
    std::printf("\nNormal draws: fast is %.2f times the speed of reproducible.\n",
                slow_normal / fast_normal);
    return 0;
}
