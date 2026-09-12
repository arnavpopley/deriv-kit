#pragma once

namespace derivkit::math {

/// Standard normal density φ(x).
[[nodiscard]] double norm_pdf(double x);

/// Standard normal CDF Φ(x), via `erfc`. Typical abs error ≲ 1 x 10^-15.
[[nodiscard]] double norm_cdf(double x);

/// Inverse CDF Φ⁻¹(p) for p ∈ (0, 1).
/// Acklam rational seed + Halley correction; round-trip |Φ(Φ⁻¹(p)) − p| ≲ 1 x 10^-15
/// on (1 x 10^-16, 1 − 1 x 10^-16).
[[nodiscard]] double norm_inv(double p);

/// Complementary CDF Φ(-x) computed directly for a slightly better tail.
[[nodiscard]] double norm_sf(double x);

}  // namespace derivkit::math
