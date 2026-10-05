#pragma once

#include <array>
#include <bit>
#include <cmath>
#include <concepts>
#include <cstddef>
#include <cstdint>
#include <cstdlib>
#include <numbers>
#include <random>
#include <span>

// Two N(0, 1) generators with the same interface, so a path loop can use either one.
//
//   NormalRng       "reproducible": mt19937_64 + Box-Muller, the same stream as Python.
//   FastNormalRng   "fast": xoshiro256++ + ziggurat, its own stream, several times cheaper.
//
// The first exists so the C++ and pure-Python back ends can be compared number for number.
// The second exists to show how fast the C++ kernel is when it does not have to match
// Python. Neither replaces the other.
namespace derivkit {

/// What a path loop needs from a generator.
///
/// A `concept` (C++20) is a named list of requirements on a type. A template constrained
/// by it accepts only types that meet them, and a type that does not is rejected with a
/// short error where it is used, instead of a long one from deep inside the template.
template <class G>
concept NormalGenerator =
    std::copyable<G> && std::constructible_from<G, std::uint64_t> &&
    requires(G g, std::span<double> out) {
        { g.uniform() } -> std::same_as<double>;  // U(0, 1), zero excluded
        { g.normal() } -> std::same_as<double>;   // one N(0, 1) draw
        { g.fill(out) } -> std::same_as<void>;    // out.size() draws, same as calling normal()
    };

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

namespace detail {

/// The lookup tables of the ziggurat method (Marsaglia and Tsang, 2000).
///
/// The area under exp(-x^2 / 2) for x >= 0 is covered by 256 horizontal layers of equal
/// area, stacked like a stepped pyramid. Layer i is the rectangle from x = 0 to x = x_i,
/// between the heights f(x_i) and f(x_(i+1)); the edges shrink as the layers go up:
/// x_1 = R > x_2 > ... > x_256 = 0. Layer 0 is the base: the rectangle below f(R) out to
/// R, plus the whole tail beyond R.
///
/// To draw: pick a layer at random and a point x uniformly across its width. If x is left
/// of the next edge x_(i+1), the point is certainly under the curve and x is returned
/// straight away, with one multiplication and one comparison. That happens for 98.5% of
/// draws. Only the rest need `exp` (a point in the sliver next to the curve) or `log` (the
/// tail).
struct Ziggurat {
    static constexpr std::size_t kLayers = 256;
    // Right-hand edge of the base rectangle for 256 layers (Doornik, 2005).
    static constexpr double kR = 3.6541528853610088;

    struct Layer {
        std::int64_t accept;  // |j| below this means x < x_(i+1): return x at once
        double scale;         // x = j * scale, for a signed 54-bit integer j
    };
    // The two numbers the common case reads sit side by side, so they share a cache line.
    std::array<Layer, kLayers> layer;
    std::array<double, kLayers + 1> f;  // f[i] = exp(-x_i^2 / 2); f[256] = 1 at x = 0

    Ziggurat() {
        const auto pdf = [](double x) { return std::exp(-0.5 * x * x); };
        // The area of every layer: the base rectangle plus the tail beyond R.
        const double area = kR * pdf(kR) + std::sqrt(std::numbers::pi / 2.0) *
                                               std::erfc(kR / std::numbers::sqrt2);
        std::array<double, kLayers + 1> x{};
        x[0] = area / pdf(kR);  // the base layer drawn as a rectangle of the same area
        x[1] = kR;
        for (std::size_t i = 1; i + 1 < kLayers; ++i) {
            // Equal areas: x_i * (f(x_(i+1)) - f(x_i)) = area, solved for x_(i+1).
            x[i + 1] = std::sqrt(-2.0 * std::log(area / x[i] + pdf(x[i])));
        }
        x[kLayers] = 0.0;
        for (std::size_t i = 0; i < kLayers; ++i) {
            layer[i].accept = static_cast<std::int64_t>(x[i + 1] / x[i] * 0x1p53);
            layer[i].scale = x[i] * 0x1p-53;
            f[i] = pdf(x[i]);
        }
        f[kLayers] = 1.0;
    }
};

// `inline` on a variable (C++17): every file that includes this header shares one copy.
// It is built once, when the library is loaded, before any generator can use it.
inline const Ziggurat kZiggurat;

}  // namespace detail

/// Fast N(0, 1) generator: the ziggurat method on top of xoshiro256++.
///
/// xoshiro256++ (Blackman and Vigna, public domain) keeps 32 bytes of state against the
/// Mersenne Twister's 2.5 KB and produces a 64-bit number with a few shifts, adds and
/// exclusive-ors. One such number makes one normal draw in the common case.
///
/// The stream is fixed by the seed, so a run can be repeated exactly. It is a different
/// stream from `NormalRng`, from Python and from NumPy: results agree within the standard
/// error, not digit for digit.
class FastNormalRng {
public:
    /// The four state words come from SplitMix64, as the xoshiro authors recommend, so any
    /// seed (including 0) gives a well-mixed state that is never all zeros.
    explicit FastNormalRng(std::uint64_t seed) {
        for (std::uint64_t& word : s_) {
            seed += 0x9e3779b97f4a7c15;
            std::uint64_t z = seed;
            z = (z ^ (z >> 30)) * 0xbf58476d1ce4e5b9;
            z = (z ^ (z >> 27)) * 0x94d049bb133111eb;
            word = z ^ (z >> 31);
        }
    }

    /// U(0, 1) with both ends excluded, so `log(u)` below stays finite: the top 52 bits
    /// plus one half, scaled by 2^-52. Every value is exact.
    [[nodiscard]] double uniform() {
        return (static_cast<double>(next(s_) >> 12) + 0.5) * 0x1p-52;
    }

    /// One N(0, 1) draw.
    [[nodiscard]] double normal() {
        double z = 0.0;
        fill(std::span<double>(&z, 1));
        return z;
    }

    /// Fill `out` with draws: the same values, in the same order, as calling `normal()`
    /// `out.size()` times.
    void fill(std::span<double> out) {
        const detail::Ziggurat& zig = detail::kZiggurat;
        // The loop runs on a local copy of the state. The uncommon cases below are handled
        // by a member function, and once the compiler sees `this` passed to a function it
        // keeps the members in memory. A local that is never passed anywhere stays in CPU
        // registers, which more than doubled the speed of this loop when it was measured.
        State s = s_;
        for (double& z : out) {
            const std::uint64_t u = next(s);
            const std::size_t i = layer_of(u);
            const std::int64_t j = offset_of(u);
            const double x = static_cast<double>(j) * zig.layer[i].scale;
            if (std::abs(j) < zig.layer[i].accept) [[likely]] {
                z = x;  // 98.5% of draws end here
            } else {
                s_ = s;  // hand the state to the member function, then take it back
                z = uncommon(i, j, x);
                s = s_;
            }
        }
        s_ = s;
    }

private:
    using State = std::array<std::uint64_t, 4>;

    /// xoshiro256++ 1.0: the next 64 random bits. `std::rotl` (C++20) rotates the bits of
    /// a word, which compiles to a single instruction.
    [[nodiscard]] static std::uint64_t next(State& s) {
        const std::uint64_t result = std::rotl(s[0] + s[3], 23) + s[0];
        const std::uint64_t t = s[1] << 17;
        s[2] ^= s[0];
        s[3] ^= s[1];
        s[1] ^= s[2];
        s[0] ^= s[3];
        s[2] ^= t;
        s[3] = std::rotl(s[3], 45);
        return result;
    }

    // One 64-bit draw is split in two: the top 8 bits pick the layer, and the next 54 are
    // a signed integer that places the point across it. Separate bits, so the two choices
    // are independent.
    [[nodiscard]] static std::size_t layer_of(std::uint64_t u) {
        return static_cast<std::size_t>(u >> 56);
    }
    [[nodiscard]] static std::int64_t offset_of(std::uint64_t u) {
        return static_cast<std::int64_t>(u << 8) >> 10;
    }

    /// The 1.5% of draws that are not settled by one comparison: the point (layer `i`,
    /// offset `j`, position `x`) lies in the tail or in the sliver next to the curve.
    [[nodiscard]] double uncommon(std::size_t i, std::int64_t j, double x) {
        const detail::Ziggurat& zig = detail::kZiggurat;
        for (;;) {
            if (i == 0) {
                return tail(j < 0);
            }
            // In the sliver between the two edges: keep x if a uniform height in this
            // layer falls under the curve.
            const double y = zig.f[i] + uniform() * (zig.f[i + 1] - zig.f[i]);
            if (y < std::exp(-0.5 * x * x)) {
                return x;
            }
            // Rejected: draw a new point and test it from the start.
            const std::uint64_t u = next(s_);
            i = layer_of(u);
            j = offset_of(u);
            x = static_cast<double>(j) * zig.layer[i].scale;
            if (std::abs(j) < zig.layer[i].accept) {
                return x;
            }
        }
    }

    /// A draw from the tail beyond R (Marsaglia, 1964). `uniform()` never returns zero,
    /// so the logarithms are finite.
    [[nodiscard]] double tail(bool negative) {
        constexpr double r = detail::Ziggurat::kR;
        for (;;) {
            const double a = -std::log(uniform()) / r;
            const double b = -std::log(uniform());
            if (b + b > a * a) {
                return negative ? -(r + a) : r + a;
            }
        }
    }

    State s_{};  // the whole state: 32 bytes
};

// Checked when this header is compiled: both classes offer what the path loops use.
static_assert(NormalGenerator<NormalRng>);
static_assert(NormalGenerator<FastNormalRng>);

}  // namespace derivkit
