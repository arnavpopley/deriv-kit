#pragma once

#include <cmath>
#include <cstddef>
#include <cstdint>
#include <numbers>
#include <random>
#include <span>

namespace derivkit {

/// Reproducible N(0, 1) generator: Box-Muller on top of `std::mt19937_64`.
///
/// It is written to produce the same stream as `derivkit.rng.NormalRng` in Python:
/// same engine, same seeding, same arithmetic in the same order. That is what lets the
/// tests compare the C++ and pure-Python back ends number for number.
///
/// Everything is defined in the header so the compiler can inline it into the path loop;
/// a call into another .cpp file per random number would not be inlined without LTO.
class NormalRng {
public:
    // `explicit` stops an integer from silently converting into a generator.
    explicit NormalRng(std::uint64_t seed) : gen_(seed) {}

    /// U(0, 1) with zero excluded, so `log(u)` below stays finite.
    [[nodiscard]] double uniform() {
        std::uint64_t u = gen_();
        if (u == 0) {
            u = 1;
        }
        // 0x1p-64 is 2^-64 written as a hexadecimal float. Multiplying by a power of two
        // only changes the exponent, so this is exact and equals Python's ldexp(u, -64).
        return static_cast<double>(u) * 0x1p-64;
    }

    /// One N(0, 1) draw. Box-Muller makes two at a time; the second is kept for the next call.
    [[nodiscard]] double normal() {
        if (has_spare_) {
            has_spare_ = false;
            return spare_;
        }
        const Pair p = next_pair();
        spare_ = p.second;
        has_spare_ = true;
        return p.first;
    }

    /// Fill `out` with draws: the same values, in the same order, as calling `normal()`
    /// `out.size()` times. Working in pairs removes the has-spare branch from the loop.
    ///
    /// `std::span` (C++20) is a pointer plus a length. It does not own or copy the data,
    /// so passing one costs the same as passing a raw pointer and a size.
    void fill(std::span<double> out) {
        std::size_t i = 0;
        const std::size_t n = out.size();
        if (has_spare_ && n > 0) {  // a draw left over from an earlier call goes first
            out[i++] = spare_;
            has_spare_ = false;
        }
        for (; i + 1 < n; i += 2) {
            const Pair p = next_pair();
            out[i] = p.first;
            out[i + 1] = p.second;
        }
        if (i < n) {  // odd count: normal() makes a pair and keeps the second as the spare
            out[i] = normal();
        }
    }

private:
    struct Pair {
        double first;
        double second;
    };

    /// Box-Muller: two independent uniforms become two independent normals.
    [[nodiscard]] Pair next_pair() {
        const double u1 = uniform();
        const double u2 = uniform();
        const double r = std::sqrt(-2.0 * std::log(u1));
        const double theta = 2.0 * std::numbers::pi * u2;
        return {r * std::cos(theta), r * std::sin(theta)};
    }

    std::mt19937_64 gen_;     // 312 64-bit words of state (about 2.5 KB), stored inline
    bool has_spare_ = false;
    double spare_ = 0.0;
};

}  // namespace derivkit
