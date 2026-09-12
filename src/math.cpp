#include "derivkit/math.hpp"

#include <cmath>
#include <stdexcept>

namespace derivkit::math {
namespace {

constexpr double kInvSqrt2Pi = 0.39894228040143267793994605993438;
constexpr double kSqrt2 = 1.4142135623730950488016887242097;

double acklam_inv(double p) {
    // Peter J. Acklam, "An algorithm for computing the inverse normal CDF".
    constexpr double a1 = -3.969683028665376e+01;
    constexpr double a2 = 2.209460984245205e+02;
    constexpr double a3 = -2.759285104469687e+02;
    constexpr double a4 = 1.383577509590705e+02;
    constexpr double a5 = -3.066479806614716e+01;
    constexpr double a6 = 2.506628277459239e+00;

    constexpr double b1 = -5.447609879822406e+01;
    constexpr double b2 = 1.615858368580409e+02;
    constexpr double b3 = -1.556989798598866e+02;
    constexpr double b4 = 6.680131188771972e+01;
    constexpr double b5 = -1.328068071618818e+01;

    constexpr double c1 = -7.784894002430293e-03;
    constexpr double c2 = -3.223964580411365e-01;
    constexpr double c3 = -2.400758277161838e+00;
    constexpr double c4 = -2.549732539343734e+00;
    constexpr double c5 = 4.374664141464968e+00;
    constexpr double c6 = 2.938163982698783e+00;

    constexpr double d1 = 7.784695709041462e-03;
    constexpr double d2 = 3.224671290700398e-01;
    constexpr double d3 = 2.445134137142996e+00;
    constexpr double d4 = 3.754408661907416e+00;

    constexpr double plow = 0.02425;
    constexpr double phigh = 1.0 - plow;

    if (p < plow) {
        const double q = std::sqrt(-2.0 * std::log(p));
        return (((((c1 * q + c2) * q + c3) * q + c4) * q + c5) * q + c6) /
               ((((d1 * q + d2) * q + d3) * q + d4) * q + 1.0);
    }
    if (p > phigh) {
        const double q = std::sqrt(-2.0 * std::log(1.0 - p));
        return -(((((c1 * q + c2) * q + c3) * q + c4) * q + c5) * q + c6) /
               ((((d1 * q + d2) * q + d3) * q + d4) * q + 1.0);
    }
    const double q = p - 0.5;
    const double r = q * q;
    return (((((a1 * r + a2) * r + a3) * r + a4) * r + a5) * r + a6) * q /
           (((((b1 * r + b2) * r + b3) * r + b4) * r + b5) * r + 1.0);
}

}  // namespace

double norm_pdf(double x) { return kInvSqrt2Pi * std::exp(-0.5 * x * x); }

double norm_cdf(double x) { return 0.5 * std::erfc(-x / kSqrt2); }

double norm_sf(double x) { return 0.5 * std::erfc(x / kSqrt2); }

double norm_inv(double p) {
    if (!(p > 0.0 && p < 1.0)) {
        throw std::invalid_argument("norm_inv: p must lie in (0, 1)");
    }

    double x = acklam_inv(p);
    // Two Halley corrections: f = Φ(x) − p, f' = φ, f'' = −x φ.
    for (int i = 0; i < 2; ++i) {
        const double pdf = norm_pdf(x);
        if (pdf == 0.0) {
            break;
        }
        const double f = norm_cdf(x) - p;
        x -= f / (pdf + 0.5 * x * f);
    }
    return x;
}

}  // namespace derivkit::math
