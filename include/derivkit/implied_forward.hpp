#pragma once

#include <vector>

namespace derivkit {

/// One strike with both call and put last prices.
struct CallPutQuote {
    double strike = 0.0;
    double call = 0.0;
    double put = 0.0;
    double weight = 1.0;
};

/// Put-call parity fit: C - P = DF * (F - K).
struct ForwardFit {
    double forward = 0.0;
    double discount = 1.0;
    double rate = 0.0;      ///< -ln(DF) / time_rate
    double dividend = 0.0;  ///< r - ln(F/S) / time_rate
    int pairs = 0;
    bool ok = false;
    const char* method = "";
};

/// Weighted linear regression of (C-P) on K. Requires time_rate > 0 and spot > 0.
[[nodiscard]] ForwardFit imply_forward(double spot, double time_rate,
                                       const std::vector<CallPutQuote>& quotes);

}  // namespace derivkit
