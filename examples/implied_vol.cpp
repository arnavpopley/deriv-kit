#include "derivkit/derivkit.hpp"

#include <cmath>
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

    const double true_vol = spec.vol;
    const double px = bs::price(spec);

    VanillaSpec probe = spec;
    probe.vol = 0.50;  // deliberately bad Newton start
    const auto iv = bs::implied_vol(probe, px);

    std::cout << std::setprecision(12);
    std::cout << "Market price (true σ = " << true_vol << "): " << px << "\n";
    std::cout << "Implied vol:  " << iv.vol << "   residual=" << iv.residual
              << "   iters=" << iv.iterations << "   via " << iv.method
              << (iv.converged ? "  converged\n" : "  FAILED\n");

    std::cout << "\nSmile reconstruction from CRR prices (N=401):\n";
    std::cout << std::setw(8) << "K" << std::setw(14) << "tree px" << std::setw(14) << "iv"
              << std::setw(14) << "|iv-σ|"
              << "\n";
    for (double k : {80.0, 90.0, 100.0, 110.0, 120.0}) {
        VanillaSpec s = spec;
        s.strike = k;
        const double tree_px = tree::cox_ross_rubinstein(s, 401).value;
        s.vol = 0.3;
        const auto recovered = bs::implied_vol(s, tree_px);
        std::cout << std::fixed << std::setprecision(2) << std::setw(8) << k << std::setprecision(8)
                  << std::setw(14) << tree_px << std::setw(14) << recovered.vol << std::scientific
                  << std::setprecision(3) << std::setw(14) << std::abs(recovered.vol - true_vol)
                  << "\n";
    }
    return 0;
}
