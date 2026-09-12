#include "derivkit/types.hpp"

#include <cmath>
#include <stdexcept>

namespace derivkit {

void validate(const VanillaSpec& spec) {
    auto require_finite = [](double x, const char* name) {
        if (!std::isfinite(x)) {
            throw std::invalid_argument(std::string(name) + " must be finite");
        }
    };
    require_finite(spec.spot, "spot");
    require_finite(spec.strike, "strike");
    require_finite(spec.rate, "rate");
    require_finite(spec.dividend, "dividend");
    require_finite(spec.vol, "vol");
    require_finite(spec.time, "time");

    if (spec.spot <= 0.0) {
        throw std::invalid_argument("spot must be positive");
    }
    if (spec.strike < 0.0) {
        throw std::invalid_argument("strike must be non-negative");
    }
    if (spec.vol < 0.0) {
        throw std::invalid_argument("vol must be non-negative");
    }
    if (spec.time < 0.0) {
        throw std::invalid_argument("time must be non-negative");
    }
}

}  // namespace derivkit
