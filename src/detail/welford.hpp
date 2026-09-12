#pragma once

#include <cmath>
#include <cstdint>

namespace derivkit::detail {

struct Welford {
    std::uint64_t n = 0;
    double mean = 0.0;
    double m2 = 0.0;

    void add(double x) {
        ++n;
        const double d = x - mean;
        mean += d / static_cast<double>(n);
        m2 += d * (x - mean);
    }

    [[nodiscard]] double variance() const {
        return n > 1 ? m2 / static_cast<double>(n - 1) : 0.0;
    }

    [[nodiscard]] double stderr_of_mean() const {
        return n > 1 ? std::sqrt(variance() / static_cast<double>(n)) : 0.0;
    }
};

struct WelfordPair {
    std::uint64_t n = 0;
    double mean_x = 0.0;
    double mean_y = 0.0;
    double m2_x = 0.0;
    double m2_y = 0.0;
    double c_xy = 0.0;

    void add(double x, double y) {
        ++n;
        const double nn = static_cast<double>(n);
        const double dx = x - mean_x;
        mean_x += dx / nn;
        const double dy = y - mean_y;
        mean_y += dy / nn;
        m2_x += dx * (x - mean_x);
        m2_y += dy * (y - mean_y);
        c_xy += dx * (y - mean_y);
    }

    [[nodiscard]] double var_x() const {
        return n > 1 ? m2_x / static_cast<double>(n - 1) : 0.0;
    }
    [[nodiscard]] double var_y() const {
        return n > 1 ? m2_y / static_cast<double>(n - 1) : 0.0;
    }
    [[nodiscard]] double cov_xy() const {
        return n > 1 ? c_xy / static_cast<double>(n - 1) : 0.0;
    }
};

}  // namespace derivkit::detail
