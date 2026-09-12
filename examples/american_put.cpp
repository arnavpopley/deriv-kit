#include "derivkit/derivkit.hpp"

#include <iomanip>
#include <iostream>

int main() {
    using namespace derivkit;

    // Classic American put (Haug / literature): early exercise is material.
    const VanillaSpec spec{
        .spot = 36.0,
        .strike = 40.0,
        .rate = 0.06,
        .dividend = 0.0,
        .vol = 0.20,
        .time = 1.0,
        .type = OptionType::Put,
    };

    const double european = bs::price(spec);
    const auto crr_e = tree::cox_ross_rubinstein(spec, 801, ExerciseStyle::European);
    const auto crr_a = tree::cox_ross_rubinstein(spec, 801, ExerciseStyle::American);
    const auto tri_a = tree::kamrad_ritchken(spec, 801, ExerciseStyle::American);
    const auto lr_a = tree::leisen_reimer(spec, 801, ExerciseStyle::American);

    tree::AdaptiveTreeConfig acfg;
    acfg.model = TreeModel::KamradRitchken;
    acfg.style = ExerciseStyle::American;
    acfg.abs_tol = 5e-4;
    acfg.min_steps = 101;
    acfg.max_steps = 3201;
    const auto adapt = tree::adaptive(spec, acfg);

    std::cout << std::fixed << std::setprecision(6);
    std::cout << "American put  S=36 K=40 r=6% σ=20% T=1\n\n";
    std::cout << "European BS (no early exercise)     " << european << "\n";
    std::cout << "CRR European  N=801                 " << crr_e.value << "\n";
    std::cout << "CRR American  N=801                 " << crr_a.value
              << "   premium=" << (crr_a.value - european) << "\n";
    std::cout << "Trinomial American N=801            " << tri_a.value << "\n";
    std::cout << "Leisen-Reimer American N=801        " << lr_a.value << "\n";
    std::cout << "Adaptive trinomial                  " << adapt.value
              << "   err=" << adapt.error_estimate << "  N=" << adapt.work
              << (adapt.converged ? "  converged\n" : "  NOT CONVERGED\n");
    return 0;
}
