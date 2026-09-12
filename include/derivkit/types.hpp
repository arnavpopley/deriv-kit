#pragma once

#include <algorithm>
#include <cmath>
#include <stdexcept>
#include <string>

namespace derivkit {

/// Call or put payoff direction.
enum class OptionType { Call, Put };

/// Exercise rights. European is analytical in Black-Scholes; American needs a tree.
enum class ExerciseStyle { European, American };

/// Lattice construction used by the tree engines.
enum class TreeModel {
    CoxRossRubinstein,  ///< Recombining CRR binomial (u = 1/d).
    JarrowRudd,         ///< Equal-probability (risk-neutral drift in the moves).
    LeisenReimer,       ///< Smooth, second-order binomial (odd step counts).
    KamradRitchken      ///< Stretched trinomial (λ = √3).
};

/// Variance-reduction switches for Monte Carlo. Values can be combined.
enum class VarianceReduction : unsigned {
    None = 0,
    Antithetic = 1u << 0,
    ControlVariate = 1u << 1,
};

[[nodiscard]] constexpr VarianceReduction operator|(VarianceReduction a,
                                                    VarianceReduction b) noexcept {
    return static_cast<VarianceReduction>(static_cast<unsigned>(a) |
                                          static_cast<unsigned>(b));
}

[[nodiscard]] constexpr bool has(VarianceReduction flags,
                                 VarianceReduction bit) noexcept {
    return (static_cast<unsigned>(flags) & static_cast<unsigned>(bit)) != 0;
}

/// Market and contract inputs for a vanilla (or Asian) option on a GBM spot.
struct VanillaSpec {
    double spot = 0.0;       ///< S₀ > 0
    double strike = 0.0;     ///< K ≥ 0
    double rate = 0.0;       ///< Continuous risk-free rate r
    double dividend = 0.0;   ///< Continuous dividend yield q
    double vol = 0.0;        ///< Black-Scholes volatility σ ≥ 0
    double time = 0.0;       ///< Year-fraction to expiry T ≥ 0
    OptionType type = OptionType::Call;
};

/// Throw `std::invalid_argument` if the spec cannot be priced.
void validate(const VanillaSpec& spec);

[[nodiscard]] inline double payoff(double spot, double strike, OptionType type) {
    if (type == OptionType::Call) {
        return std::max(spot - strike, 0.0);
    }
    return std::max(strike - spot, 0.0);
}

[[nodiscard]] inline double discount_factor(double rate, double time) {
    return std::exp(-rate * time);
}

[[nodiscard]] inline double forward_price(double spot, double rate, double dividend,
                                          double time) {
    return spot * std::exp((rate - dividend) * time);
}

[[nodiscard]] inline const char* to_string(OptionType type) noexcept {
    return type == OptionType::Call ? "call" : "put";
}

[[nodiscard]] inline const char* to_string(ExerciseStyle style) noexcept {
    return style == ExerciseStyle::European ? "european" : "american";
}

[[nodiscard]] inline const char* to_string(TreeModel model) noexcept {
    switch (model) {
        case TreeModel::CoxRossRubinstein:
            return "crr";
        case TreeModel::JarrowRudd:
            return "jarrow-rudd";
        case TreeModel::LeisenReimer:
            return "leisen-reimer";
        case TreeModel::KamradRitchken:
            return "kamrad-ritchken";
    }
    return "unknown";
}

}  // namespace derivkit
