#include "derivkit/derivkit.hpp"

#include <iomanip>
#include <iostream>

int main() {
    using namespace derivkit;

    const VanillaSpec spec{
        .spot = 100.0,
        .strike = 100.0,
        .rate = 0.05,
        .dividend = 0.0,
        .vol = 0.20,
        .time = 1.0,
        .type = OptionType::Call,
    };

    const auto analytic = bs::price_result(spec);
    const auto g = bs::greeks(spec);

    tree::TreeConfig crr{.steps = 401, .model = TreeModel::CoxRossRubinstein};
    tree::TreeConfig lr{.steps = 101, .model = TreeModel::LeisenReimer};
    tree::TreeConfig tri{.steps = 401, .model = TreeModel::KamradRitchken};

    mc::McConfig crude{.paths = 100000, .seed = 1, .vr = VarianceReduction::None};
    mc::McConfig vr{.paths = 100000,
                    .seed = 1,
                    .vr = VarianceReduction::Antithetic | VarianceReduction::ControlVariate};

    std::cout << std::fixed << std::setprecision(8);
    std::cout << "European call  S=100 K=100 r=5% q=0 σ=20% T=1\n\n";
    std::cout << analytic << "\n";
    std::cout << tree::price(spec, crr) << "\n";
    std::cout << tree::price(spec, lr) << "\n";
    std::cout << tree::price(spec, tri) << "\n";
    std::cout << mc::european(spec, crude) << "\n";
    std::cout << mc::european(spec, vr) << "\n";

    std::cout << "\nGreeks (per 1.0 of the bump, not 1% / 1bp):\n";
    std::cout << "  delta  " << g.delta << "\n";
    std::cout << "  gamma  " << g.gamma << "\n";
    std::cout << "  vega   " << g.vega << "\n";
    std::cout << "  theta  " << g.theta << "\n";
    std::cout << "  rho    " << g.rho << "\n";
    std::cout << "  vanna  " << g.vanna << "\n";
    std::cout << "  volga  " << g.volga << "\n";

    VanillaSpec put = spec;
    put.type = OptionType::Put;
    const double parity = bs::price(spec) - bs::price(put) -
                          (spec.spot - spec.strike * discount_factor(spec.rate, spec.time));
    std::cout << "\nPut-call parity residual: " << std::scientific << parity << "\n";
    return 0;
}
