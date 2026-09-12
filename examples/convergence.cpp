#include "derivkit/derivkit.hpp"

#include <cmath>
#include <iomanip>
#include <iostream>
#include <vector>

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
    const double bs = bs::price(spec);

    std::cout << "European call vs Black-Scholes = " << std::fixed << std::setprecision(10) << bs
              << "\n\n";
    std::cout << std::setw(6) << "N" << std::setw(16) << "CRR err" << std::setw(16) << "JR err"
              << std::setw(16) << "LR err" << std::setw(16) << "TRIN err"
              << "\n";

    for (int n : {25, 51, 101, 201, 401, 801}) {
        const double e_crr = std::abs(tree::cox_ross_rubinstein(spec, n).value - bs);
        const double e_jr = std::abs(tree::jarrow_rudd(spec, n).value - bs);
        const double e_lr = std::abs(tree::leisen_reimer(spec, n).value - bs);
        const double e_tr = std::abs(tree::kamrad_ritchken(spec, n).value - bs);
        std::cout << std::setw(6) << n << std::scientific << std::setprecision(4) << std::setw(16)
                  << e_crr << std::setw(16) << e_jr << std::setw(16) << e_lr << std::setw(16)
                  << e_tr << "\n";
    }

    std::cout << "\nCRR with Richardson 2P(2N)-P(N) (even N; CRR oscillates on odd N):\n";
    std::cout << std::setw(6) << "N" << std::setw(16) << "plain err" << std::setw(16) << "rich err"
              << "\n";
    for (int n : {50, 100, 200, 400}) {
        tree::TreeConfig plain{.steps = n, .richardson = false};
        tree::TreeConfig rich{.steps = n, .richardson = true};
        const double e0 = std::abs(tree::price(spec, plain).value - bs);
        const double e1 = std::abs(tree::price(spec, rich).value - bs);
        std::cout << std::setw(6) << n << std::scientific << std::setprecision(4) << std::setw(16)
                  << e0 << std::setw(16) << e1 << "\n";
    }
    return 0;
}
