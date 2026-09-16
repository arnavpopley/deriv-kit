from __future__ import annotations

import math
from dataclasses import dataclass
from sys import float_info

import derivkit.math as dmath
from derivkit.result import PricingResult
from derivkit.types import (
    OptionType,
    VanillaSpec,
    discount_factor,
    forward_price,
    payoff,
    validate as validate_vanilla,
)


@dataclass
class Greeks:
    delta: float = 0.0
    gamma: float = 0.0
    vega: float = 0.0
    theta: float = 0.0
    rho: float = 0.0
    vanna: float = 0.0
    volga: float = 0.0
    d1: float = 0.0
    d2: float = 0.0


@dataclass
class BlackSpec:
    forward: float = 0.0
    strike: float = 0.0
    discount: float = 1.0
    vol: float = 0.0
    time_vol: float = 0.0
    type: OptionType = OptionType.CALL


def validate_black(spec: BlackSpec) -> None:
    for name, x in (
        ("forward", spec.forward),
        ("strike", spec.strike),
        ("discount", spec.discount),
        ("vol", spec.vol),
        ("time_vol", spec.time_vol),
    ):
        if not math.isfinite(x):
            raise ValueError(f"{name} must be finite")
    if spec.forward <= 0.0:
        raise ValueError("forward must be positive")
    if spec.strike < 0.0:
        raise ValueError("strike must be non-negative")
    if not (spec.discount > 0.0):
        raise ValueError("discount must be positive")
    if spec.vol < 0.0:
        raise ValueError("vol must be non-negative")
    if spec.time_vol < 0.0:
        raise ValueError("time_vol must be non-negative")


def to_black(spec: VanillaSpec) -> BlackSpec:
    return BlackSpec(
        forward=forward_price(spec.spot, spec.rate, spec.dividend, spec.time),
        strike=spec.strike,
        discount=discount_factor(spec.rate, spec.time),
        vol=spec.vol,
        time_vol=spec.time,
        type=spec.type,
    )


def d1_d2(spec: VanillaSpec) -> tuple[float, float]:
    vol_sqrt_t = spec.vol * math.sqrt(spec.time)
    if vol_sqrt_t <= 0.0:
        raise ValueError("d1_d2 requires positive vol * sqrt(time)")
    log_moneyness = math.log(spec.spot / spec.strike)
    d1 = (log_moneyness + (spec.rate - spec.dividend + 0.5 * spec.vol * spec.vol) * spec.time) / (
        vol_sqrt_t
    )
    return d1, d1 - vol_sqrt_t


def _deterministic_price(spec: VanillaSpec) -> float:
    fwd = forward_price(spec.spot, spec.rate, spec.dividend, spec.time)
    df = discount_factor(spec.rate, spec.time)
    return df * payoff(fwd, spec.strike, spec.type)


def intrinsic_discounted(spec: VanillaSpec | BlackSpec) -> float:
    if isinstance(spec, BlackSpec):
        validate_black(spec)
        return spec.discount * payoff(spec.forward, spec.strike, spec.type)
    validate_vanilla(spec)
    df_r = discount_factor(spec.rate, spec.time)
    df_q = discount_factor(spec.dividend, spec.time)
    if spec.type is OptionType.CALL:
        return max(spec.spot * df_q - spec.strike * df_r, 0.0)
    return max(spec.strike * df_r - spec.spot * df_q, 0.0)


def upper_bound(spec: VanillaSpec | BlackSpec) -> float:
    if isinstance(spec, BlackSpec):
        validate_black(spec)
        if spec.type is OptionType.CALL:
            return spec.discount * spec.forward
        return spec.discount * spec.strike
    validate_vanilla(spec)
    if spec.type is OptionType.CALL:
        return spec.spot * discount_factor(spec.dividend, spec.time)
    return spec.strike * discount_factor(spec.rate, spec.time)


def _undiscounted_black(spec: BlackSpec) -> VanillaSpec:
    return VanillaSpec(
        spot=spec.forward,
        strike=spec.strike,
        rate=0.0,
        dividend=0.0,
        vol=spec.vol,
        time=spec.time_vol,
        type=spec.type,
    )


def price(spec: VanillaSpec | BlackSpec) -> float:
    if isinstance(spec, BlackSpec):
        validate_black(spec)
        return spec.discount * price(_undiscounted_black(spec))

    validate_vanilla(spec)
    if spec.time == 0.0 or spec.vol == 0.0:
        return _deterministic_price(spec)
    if spec.strike == 0.0:
        if spec.type is OptionType.CALL:
            return spec.spot * discount_factor(spec.dividend, spec.time)
        return 0.0

    d1, d2 = d1_d2(spec)
    df_q = discount_factor(spec.dividend, spec.time)
    df_r = discount_factor(spec.rate, spec.time)
    if spec.type is OptionType.CALL:
        return spec.spot * df_q * dmath.norm_cdf(d1) - spec.strike * df_r * dmath.norm_cdf(d2)
    return spec.strike * df_r * dmath.norm_cdf(-d2) - spec.spot * df_q * dmath.norm_cdf(-d1)


def price_result(spec: VanillaSpec) -> PricingResult:
    value = price(spec)
    scale = max(1.0, abs(value))
    return PricingResult(
        value=value,
        method="black-scholes",
        work=1,
        converged=True,
        error_estimate=8.0 * scale * float_info.epsilon,
        notes="analytic; error is a few ulps",
    )


def greeks(spec: VanillaSpec | BlackSpec) -> Greeks:
    if isinstance(spec, BlackSpec):
        validate_black(spec)
        g = greeks(_undiscounted_black(spec))
        g.delta *= spec.discount
        g.gamma *= spec.discount
        g.vega *= spec.discount
        g.theta *= spec.discount
        g.vanna *= spec.discount
        g.volga *= spec.discount
        g.rho = 0.0
        return g

    validate_vanilla(spec)
    g = Greeks()
    if spec.time == 0.0 or spec.vol == 0.0 or spec.strike == 0.0:
        df_q = discount_factor(spec.dividend, spec.time)
        if spec.time == 0.0:
            if spec.type is OptionType.CALL:
                g.delta = 1.0 if spec.spot > spec.strike else (0.0 if spec.spot < spec.strike else 0.5)
            else:
                g.delta = -1.0 if spec.spot < spec.strike else (0.0 if spec.spot > spec.strike else -0.5)
        elif spec.vol == 0.0:
            fwd = forward_price(spec.spot, spec.rate, spec.dividend, spec.time)
            itm = fwd > spec.strike if spec.type is OptionType.CALL else fwd < spec.strike
            g.delta = (df_q if spec.type is OptionType.CALL else -df_q) if itm else 0.0
            df_r = discount_factor(spec.rate, spec.time)
            if itm:
                g.rho = (1.0 if spec.type is OptionType.CALL else -1.0) * spec.strike * spec.time * df_r
            value = price(spec)
            carry = spec.spot * df_q if spec.type is OptionType.CALL else -spec.spot * df_q
            g.theta = spec.rate * (value - carry)
        return g

    d1, d2 = d1_d2(spec)
    g.d1 = d1
    g.d2 = d2
    sqrt_t = math.sqrt(spec.time)
    df_q = discount_factor(spec.dividend, spec.time)
    df_r = discount_factor(spec.rate, spec.time)
    phi = dmath.norm_pdf(d1)
    nd1 = dmath.norm_cdf(d1)
    nd2 = dmath.norm_cdf(d2)
    g.gamma = df_q * phi / (spec.spot * spec.vol * sqrt_t)
    g.vega = spec.spot * df_q * phi * sqrt_t
    g.vanna = -df_q * phi * d2 / spec.vol
    g.volga = g.vega * d1 * d2 / spec.vol
    if spec.type is OptionType.CALL:
        g.delta = df_q * nd1
        g.theta = (
            -spec.spot * df_q * phi * spec.vol / (2.0 * sqrt_t)
            - spec.rate * spec.strike * df_r * nd2
            + spec.dividend * spec.spot * df_q * nd1
        )
        g.rho = spec.strike * spec.time * df_r * nd2
    else:
        nmd1 = dmath.norm_cdf(-d1)
        nmd2 = dmath.norm_cdf(-d2)
        g.delta = df_q * (nd1 - 1.0)
        g.theta = (
            -spec.spot * df_q * phi * spec.vol / (2.0 * sqrt_t)
            + spec.rate * spec.strike * df_r * nmd2
            - spec.dividend * spec.spot * df_q * nmd1
        )
        g.rho = -spec.strike * spec.time * df_r * nmd2
    return g


def geometric_asian(spec: VanillaSpec, fixings: int) -> float:
    validate_vanilla(spec)
    if fixings == 0:
        raise ValueError("geometric_asian requires at least one fixing")
    if spec.time == 0.0:
        return payoff(spec.spot, spec.strike, spec.type)
    if spec.vol == 0.0:
        dt = spec.time / float(fixings)
        mu = spec.rate - spec.dividend
        sum_log = 0.0
        for i in range(1, fixings + 1):
            si = spec.spot * math.exp(mu * dt * float(i))
            sum_log += math.log(si)
        g = math.exp(sum_log / float(fixings))
        return discount_factor(spec.rate, spec.time) * payoff(g, spec.strike, spec.type)

    n = float(fixings)
    dt = spec.time / n
    drift = spec.rate - spec.dividend - 0.5 * spec.vol * spec.vol
    mu_g = math.log(spec.spot) + drift * (n + 1.0) * dt / 2.0
    var_g = spec.vol * spec.vol * dt * (n + 1.0) * (2.0 * n + 1.0) / (6.0 * n)
    fwd_g = math.exp(mu_g + 0.5 * var_g)
    sig_g = math.sqrt(var_g)
    d1 = (math.log(fwd_g / spec.strike) + 0.5 * var_g) / sig_g
    d2 = d1 - sig_g
    df = discount_factor(spec.rate, spec.time)
    if spec.type is OptionType.CALL:
        return df * (fwd_g * dmath.norm_cdf(d1) - spec.strike * dmath.norm_cdf(d2))
    return df * (spec.strike * dmath.norm_cdf(-d2) - fwd_g * dmath.norm_cdf(-d1))
