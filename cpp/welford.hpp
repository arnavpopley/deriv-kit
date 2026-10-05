#pragma once

#include <cstdint>

namespace derivkit {

/// Running means, variances and covariance of paired samples (x = control, y = payoff).
///
/// Welford's update keeps six numbers no matter how many samples go in, so the path loop
/// never stores the samples themselves. It is the same update, in the same order, as
/// `derivkit._moments.WelfordPair` in Python.
struct WelfordPair {
    std::uint64_t n = 0;
    double mean_x = 0.0;
    double mean_y = 0.0;
    double m2_x = 0.0;  // sum of (x - mean_x)^2
    double m2_y = 0.0;  // sum of (y - mean_y)^2
    double c_xy = 0.0;  // sum of (x - mean_x) * (y - mean_y)

    void add(double x, double y) {
        ++n;
        const double nn = static_cast<double>(n);
        const double dx = x - mean_x;  // distance from the old mean
        mean_x += dx / nn;
        const double dy = y - mean_y;
        mean_y += dy / nn;
        // (old distance) * (new distance): Welford's identity for the centred sums.
        m2_x += dx * (x - mean_x);
        m2_y += dy * (y - mean_y);
        c_xy += dx * (y - mean_y);
    }
};

}  // namespace derivkit
