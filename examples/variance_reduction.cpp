#include "derivkit/derivkit.hpp"

#include <cmath>
#include <iomanip>
#include <iostream>

namespace {

void row(const char* name, const derivkit::PricingResult& r, double ref_err) {
    const double ratio = ref_err > 0.0 ? (ref_err * ref_err) / (r.error_estimate * r.error_estimate)
                                       : 0.0;
    std::cout << std::left << std::setw(28) << name << std::right << std::fixed
              << std::setprecision(6) << std::setw(12) << r.value << std::scientific
              << std::setprecision(3) << std::setw(12) << r.error_estimate << std::fixed
              << std::setprecision(2) << std::setw(12) << ratio << "\n";
}

}  // namespace

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
    mc::McConfig cfg{.paths = 50000, .seed = 42};

    std::cout << "European call, 50,000 paths, seed=42.  Black-Scholes = " << std::fixed
              << std::setprecision(6) << bs << "\n";
    std::cout << "Variance ratio = Var(crude) / Var(method)  (higher is better).\n\n";
    std::cout << std::left << std::setw(28) << "method" << std::right << std::setw(12) << "price"
              << std::setw(12) << "stderr" << std::setw(12) << "var ratio"
              << "\n";

    cfg.vr = VarianceReduction::None;
    const auto crude = mc::european(spec, cfg);
    row("crude", crude, crude.error_estimate);

    cfg.vr = VarianceReduction::Antithetic;
    row("antithetic", mc::european(spec, cfg), crude.error_estimate);

    cfg.vr = VarianceReduction::ControlVariate;
    row("control (S_T)", mc::european(spec, cfg), crude.error_estimate);

    cfg.vr = VarianceReduction::Antithetic | VarianceReduction::ControlVariate;
    row("antithetic + control", mc::european(spec, cfg), crude.error_estimate);

    std::cout << "\nArithmetic Asian call, 50 fixings, 20,000 paths.\n";
    std::cout << "Geometric Asian (Kemna-Vorst) = " << std::fixed << std::setprecision(6)
              << bs::geometric_asian(spec, 50) << "\n\n";

    mc::AsianConfig asian;
    asian.mc.paths = 20000;
    asian.mc.seed = 42;
    asian.steps = 50;

    asian.mc.vr = VarianceReduction::None;
    const auto a_crude = mc::arithmetic_asian(spec, asian);
    row("asian crude", a_crude, a_crude.error_estimate);

    asian.mc.vr = VarianceReduction::Antithetic;
    row("asian antithetic", mc::arithmetic_asian(spec, asian), a_crude.error_estimate);

    asian.mc.vr = VarianceReduction::ControlVariate;
    row("asian geo-control", mc::arithmetic_asian(spec, asian), a_crude.error_estimate);

    asian.mc.vr = VarianceReduction::Antithetic | VarianceReduction::ControlVariate;
    row("asian anti+geo-cv", mc::arithmetic_asian(spec, asian), a_crude.error_estimate);

    return 0;
}
