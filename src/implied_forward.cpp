#include "derivkit/implied_forward.hpp"

#include <cmath>
#include <stdexcept>

namespace derivkit {

ForwardFit imply_forward(double spot, double time_rate, const std::vector<CallPutQuote>& quotes) {
    ForwardFit out;
    if (!(spot > 0.0) || !(time_rate > 0.0)) {
        throw std::invalid_argument("imply_forward needs positive spot and time_rate");
    }

    double sw = 0.0;
    double swk = 0.0;
    double swk2 = 0.0;
    double swy = 0.0;
    double swky = 0.0;
    int n = 0;
    for (const auto& q : quotes) {
        if (!(q.call > 0.0 && q.put > 0.0 && q.strike > 0.0 && q.weight > 0.0)) {
            continue;
        }
        const double y = q.call - q.put;
        const double w = q.weight;
        const double k = q.strike;
        sw += w;
        swk += w * k;
        swk2 += w * k * k;
        swy += w * y;
        swky += w * k * y;
        ++n;
    }
    out.pairs = n;
    if (n < 2 || sw <= 0.0) {
        out.method = "too-few-pairs";
        return out;
    }

    const double det = sw * swk2 - swk * swk;
    if (!(std::abs(det) > 1e-12 * sw * swk2)) {
        out.method = "degenerate";
        return out;
    }
    // y = a + b K,  C-P = DF F - DF K  => a = DF F, b = -DF
    const double a = (swy * swk2 - swk * swky) / det;
    const double b = (sw * swky - swk * swy) / det;
    if (!(b < 0.0) || !(a > 0.0)) {
        out.method = "non-physical";
        return out;
    }
    out.discount = -b;
    out.forward = a / out.discount;
    if (!(out.forward > 0.0) || !(out.discount > 0.0 && out.discount < 2.0)) {
        out.method = "non-physical";
        out.ok = false;
        return out;
    }
    out.rate = -std::log(out.discount) / time_rate;
    out.dividend = out.rate - std::log(out.forward / spot) / time_rate;
    out.ok = true;
    out.method = "pcp-ols";
    return out;
}

}  // namespace derivkit
