#pragma once

#include <cstdint>
#include <ostream>
#include <string>

namespace derivkit {

/// Uniform report from every numerical engine.
///
/// `error_estimate` is a *computable* bound or statistical error, not a
/// marketing tolerance:
///   - Black-Scholes: a few units in the last place (analytic).
///   - Trees: |P(N) − P(⌊N/2⌋)|, a practical truncation diagnostic.
///   - Monte Carlo: sample standard error of the discounted payoff.
/// Adaptive drivers keep refining until this quantity falls below a user
/// tolerance - the same contract used by an adaptive ODE integrator.
struct PricingResult {
    double value = 0.0;
    double error_estimate = 0.0;
    std::uint64_t work = 0;  ///< Time steps (trees) or independent paths (MC).
    const char* method = "";
    bool converged = true;
    std::string notes;
};

inline std::ostream& operator<<(std::ostream& os, const PricingResult& r) {
    os << r.method << "  value=" << r.value << "  err=" << r.error_estimate
       << "  work=" << r.work;
    if (!r.converged) {
        os << "  NOT_CONVERGED";
    }
    if (!r.notes.empty()) {
        os << "  (" << r.notes << ")";
    }
    return os;
}

}  // namespace derivkit
