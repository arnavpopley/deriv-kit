from __future__ import annotations

import math

_INV_SQRT_2PI = 0.39894228040143267793994605993438
_SQRT2 = 1.4142135623730950488016887242097


def _acklam_inv(p: float) -> float:
    # Peter J. Acklam, "An algorithm for computing the inverse normal CDF".
    a1 = -3.969683028665376e01
    a2 = 2.209460984245205e02
    a3 = -2.759285104469687e02
    a4 = 1.383577509590705e02
    a5 = -3.066479806614716e01
    a6 = 2.506628277459239e00
    b1 = -5.447609879822406e01
    b2 = 1.615858368580409e02
    b3 = -1.556989798598866e02
    b4 = 6.680131188771972e01
    b5 = -1.328068071618818e01
    c1 = -7.784894002430293e-03
    c2 = -3.223964580411365e-01
    c3 = -2.400758277161838e00
    c4 = -2.549732539343734e00
    c5 = 4.374664141464968e00
    c6 = 2.938163982698783e00
    d1 = 7.784695709041462e-03
    d2 = 3.224671290700398e-01
    d3 = 2.445134137142996e00
    d4 = 3.754408661907416e00
    plow = 0.02425
    phigh = 1.0 - plow

    if p < plow:
        q = math.sqrt(-2.0 * math.log(p))
        return (((((c1 * q + c2) * q + c3) * q + c4) * q + c5) * q + c6) / (
            ((((d1 * q + d2) * q + d3) * q + d4) * q + 1.0)
        )
    if p > phigh:
        q = math.sqrt(-2.0 * math.log(1.0 - p))
        return -(((((c1 * q + c2) * q + c3) * q + c4) * q + c5) * q + c6) / (
            ((((d1 * q + d2) * q + d3) * q + d4) * q + 1.0)
        )
    q = p - 0.5
    r = q * q
    return (((((a1 * r + a2) * r + a3) * r + a4) * r + a5) * r + a6) * q / (
        (((((b1 * r + b2) * r + b3) * r + b4) * r + b5) * r + 1.0)
    )


def norm_pdf(x: float) -> float:
    return _INV_SQRT_2PI * math.exp(-0.5 * x * x)


def norm_cdf(x: float) -> float:
    return 0.5 * math.erfc(-x / _SQRT2)


def norm_sf(x: float) -> float:
    return 0.5 * math.erfc(x / _SQRT2)


def norm_inv(p: float) -> float:
    if not (p > 0.0 and p < 1.0):
        raise ValueError("norm_inv: p must lie in (0, 1)")
    x = _acklam_inv(p)
    for _ in range(2):
        pdf = norm_pdf(x)
        if pdf == 0.0:
            break
        f = norm_cdf(x) - p
        x -= f / (pdf + 0.5 * x * f)
    return x
