#pragma once

#include "derivkit/result.hpp"
#include "derivkit/types.hpp"

namespace derivkit::tree {

struct TreeConfig {
    int steps = 401;
    TreeModel model = TreeModel::CoxRossRubinstein;
    ExerciseStyle style = ExerciseStyle::European;
    /// One Richardson step: 2 P(2N) − P(N). Helps CRR's O(1/N) term.
    bool richardson = false;
};

struct AdaptiveTreeConfig {
    TreeModel model = TreeModel::LeisenReimer;
    ExerciseStyle style = ExerciseStyle::European;
    double abs_tol = 1e-6;
    int min_steps = 51;
    int max_steps = 5001;
};

[[nodiscard]] PricingResult price(const VanillaSpec& spec, const TreeConfig& cfg);

[[nodiscard]] PricingResult cox_ross_rubinstein(const VanillaSpec& spec, int steps,
                                                ExerciseStyle style = ExerciseStyle::European);

[[nodiscard]] PricingResult jarrow_rudd(const VanillaSpec& spec, int steps,
                                        ExerciseStyle style = ExerciseStyle::European);

[[nodiscard]] PricingResult leisen_reimer(const VanillaSpec& spec, int steps,
                                          ExerciseStyle style = ExerciseStyle::European);

[[nodiscard]] PricingResult kamrad_ritchken(const VanillaSpec& spec, int steps,
                                            ExerciseStyle style = ExerciseStyle::European);

/// Double the step count until successive prices differ by less than `abs_tol`.
/// The reported error is the last successive difference (like an RK step-size
/// controller using |y_{h} − y_{h/2}|).
[[nodiscard]] PricingResult adaptive(const VanillaSpec& spec,
                                     const AdaptiveTreeConfig& cfg = {});

}  // namespace derivkit::tree
