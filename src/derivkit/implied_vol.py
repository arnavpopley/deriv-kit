from __future__ import annotations

import math
from dataclasses import dataclass, replace
from typing import Callable

from derivkit.black_scholes import BlackSpec, greeks, intrinsic_discounted, price, upper_bound
from derivkit.types import VanillaSpec, validate


@dataclass
class ImpliedVolConfig:
    abs_tol: float = 1e-12
    rel_tol: float = 1e-12
    max_newton: int = 40
    max_bisect: int = 80
    lo: float = 1e-8
    hi: float = 5.0


@dataclass
class ImpliedVolResult:
    vol: float = 0.0
    residual: float = 0.0
    iterations: int = 0
    converged: bool = False
    method: str = ""


def _invert_vol(
    market_price: float,
    warm_start: float,
    lower: float,
    upper: float,
    cfg: ImpliedVolConfig,
    priced: Callable[[float], float],
    vega_of: Callable[[float], float],
) -> ImpliedVolResult:
    out = ImpliedVolResult()
    scale = max(1.0, abs(market_price), abs(lower))
    tol = max(cfg.abs_tol, cfg.rel_tol * scale)

    if market_price < lower - 10.0 * tol:
        out.method = "below-intrinsic"
        out.residual = market_price - lower
        return out
    if market_price > upper + 10.0 * tol:
        out.method = "above-upper-bound"
        out.residual = market_price - upper
        return out

    if abs(market_price - lower) <= tol:
        out.vol = 0.0
        out.residual = priced(0.0) - market_price
        out.converged = True
        out.method = "zero-vol"
        return out

    lo = cfg.lo
    hi = cfg.hi
    while priced(hi) < market_price and hi < 1.0e2:
        hi *= 2.0

    sigma = warm_start if warm_start > 0.0 else 0.2
    sigma = min(max(sigma, lo), hi)

    it = 0
    while it < cfg.max_newton:
        px = priced(sigma)
        diff = px - market_price
        out.residual = diff
        out.vol = sigma
        out.iterations = it + 1
        if abs(diff) <= tol:
            out.converged = True
            out.method = "newton"
            return out
        v = vega_of(sigma)
        if not (v > 1.0e-14):
            break
        sigma -= diff / v
        if not (sigma > lo and sigma < hi):
            break
        it += 1

    f_lo = priced(lo) - market_price
    f_hi = priced(hi) - market_price
    if f_lo * f_hi > 0.0:
        k = 0
        while k < 20 and f_lo * f_hi > 0.0:
            lo *= 0.5
            hi *= 1.5
            f_lo = priced(lo) - market_price
            f_hi = priced(hi) - market_price
            k += 1
    if f_lo * f_hi > 0.0:
        out.method = "no-bracket"
        out.iterations = it
        return out

    for _ in range(cfg.max_bisect):
        mid = 0.5 * (lo + hi)
        f_mid = priced(mid) - market_price
        it += 1
        out.iterations = it
        out.vol = mid
        out.residual = f_mid
        if abs(f_mid) <= tol or 0.5 * (hi - lo) <= 1.0e-14 * mid:
            out.converged = True
            out.method = "bisection"
            return out
        if f_lo * f_mid <= 0.0:
            hi = mid
            f_hi = f_mid
        else:
            lo = mid
            f_lo = f_mid

    out.method = "max-iterations"
    return out


def implied_vol(
    spec: VanillaSpec | BlackSpec,
    market_price: float,
    cfg: ImpliedVolConfig | None = None,
) -> ImpliedVolResult:
    if cfg is None:
        cfg = ImpliedVolConfig()
    if not math.isfinite(market_price):
        raise ValueError("market_price must be finite")
    if isinstance(spec, BlackSpec):
        from derivkit.black_scholes import validate_black

        validate_black(spec)
        return _invert_vol(
            market_price,
            spec.vol,
            intrinsic_discounted(spec),
            upper_bound(spec),
            cfg,
            lambda sigma: price(replace(spec, vol=sigma)),
            lambda sigma: greeks(replace(spec, vol=sigma)).vega,
        )
    validate(spec)
    return _invert_vol(
        market_price,
        spec.vol,
        intrinsic_discounted(spec),
        upper_bound(spec),
        cfg,
        lambda sigma: price(replace(spec, vol=sigma)),
        lambda sigma: greeks(replace(spec, vol=sigma)).vega,
    )
