from __future__ import annotations

import math
from dataclasses import dataclass

from derivkit.black_scholes import d1_d2, price_result
from derivkit.result import PricingResult
from derivkit.types import (
    ExerciseStyle,
    TreeModel,
    VanillaSpec,
    payoff,
    discount_factor,
    validate,
)


def _odd_steps(n: int) -> int:
    if n < 1:
        raise ValueError("tree steps must be positive")
    return n + 1 if n % 2 == 0 else n


def _peizer_pratt(z: float, n: int) -> float:
    x = z / (float(n) + 1.0 / 3.0 + 0.1 / (n + 1.0))
    inner = 1.0 - math.exp(-x * x * (n + 1.0 / 6.0))
    mag = 0.5 * math.sqrt(max(inner, 0.0))
    return 0.5 + (mag if z >= 0.0 else -mag)


def _binomial(
    spec: VanillaSpec, steps: int, u: float, d: float, p: float, american: bool, method: str
) -> PricingResult:
    if not (p > 0.0 and p < 1.0) or not (u > 0.0) or not (d > 0.0):
        raise RuntimeError(f"{method}: invalid tree probabilities; increase the step count")

    dt = spec.time / float(steps)
    disc = discount_factor(spec.rate, dt)
    u_over_d = u / d
    v = [0.0] * (steps + 1)
    s = spec.spot * (d**steps)
    for j in range(steps + 1):
        v[j] = payoff(s, spec.strike, spec.type)
        s *= u_over_d

    for i in range(steps - 1, -1, -1):
        s_down = spec.spot * (d**i)
        for j in range(i + 1):
            cont = disc * (p * v[j + 1] + (1.0 - p) * v[j])
            if american:
                v[j] = max(payoff(s_down, spec.strike, spec.type), cont)
            else:
                v[j] = cont
            s_down *= u_over_d

    return PricingResult(
        value=v[0],
        work=steps,
        method=method,
        converged=True,
        notes="american" if american else "european",
    )


def _crr(spec: VanillaSpec, steps: int, american: bool) -> PricingResult:
    validate(spec)
    if steps < 1:
        raise ValueError("steps must be positive")
    if spec.time == 0.0 or spec.vol == 0.0:
        r = price_result(spec)
        r.method = "crr"
        r.work = steps
        return r
    dt = spec.time / float(steps)
    u = math.exp(spec.vol * math.sqrt(dt))
    d = 1.0 / u
    a = math.exp((spec.rate - spec.dividend) * dt)
    p = (a - d) / (u - d)
    return _binomial(spec, steps, u, d, p, american, "crr")


def _jr(spec: VanillaSpec, steps: int, american: bool) -> PricingResult:
    validate(spec)
    if steps < 1:
        raise ValueError("steps must be positive")
    if spec.time == 0.0 or spec.vol == 0.0:
        r = price_result(spec)
        r.method = "jarrow-rudd"
        r.work = steps
        return r
    dt = spec.time / float(steps)
    drift = (spec.rate - spec.dividend - 0.5 * spec.vol * spec.vol) * dt
    jump = spec.vol * math.sqrt(dt)
    u = math.exp(drift + jump)
    d = math.exp(drift - jump)
    return _binomial(spec, steps, u, d, 0.5, american, "jarrow-rudd")


def _lr(spec: VanillaSpec, steps: int, american: bool) -> PricingResult:
    validate(spec)
    steps = _odd_steps(steps)
    if spec.time == 0.0 or spec.vol == 0.0:
        r = price_result(spec)
        r.method = "leisen-reimer"
        r.work = steps
        return r
    d1, d2 = d1_d2(spec)
    dt = spec.time / float(steps)
    p = _peizer_pratt(d2, steps)
    p_star = _peizer_pratt(d1, steps)
    growth = math.exp((spec.rate - spec.dividend) * dt)
    if p <= 0.0 or p >= 1.0 or p_star <= 0.0 or p_star >= 1.0:
        raise RuntimeError("leisen-reimer: inversion left the unit interval")
    u = growth * p_star / p
    d = (growth - p * u) / (1.0 - p)
    return _binomial(spec, steps, u, d, p, american, "leisen-reimer")


def _trinomial(spec: VanillaSpec, steps: int, american: bool) -> PricingResult:
    validate(spec)
    if steps < 1:
        raise ValueError("steps must be positive")
    if spec.time == 0.0 or spec.vol == 0.0:
        r = price_result(spec)
        r.method = "kamrad-ritchken"
        r.work = steps
        return r

    dt = spec.time / float(steps)
    lam = math.sqrt(3.0)
    nu = spec.rate - spec.dividend - 0.5 * spec.vol * spec.vol
    pu = 1.0 / (2.0 * lam * lam) + 0.5 * nu * math.sqrt(dt) / (lam * spec.vol)
    pd = 1.0 / (2.0 * lam * lam) - 0.5 * nu * math.sqrt(dt) / (lam * spec.vol)
    pm = 1.0 - 1.0 / (lam * lam)
    if pu < 0.0 or pd < 0.0 or pm < 0.0:
        raise RuntimeError("kamrad-ritchken: negative probability; increase the step count")

    disc = discount_factor(spec.rate, dt)
    dx = lam * spec.vol * math.sqrt(dt)
    v = [0.0] * (2 * steps + 1)
    nxt = [0.0] * (2 * steps + 1)
    for j in range(2 * steps + 1):
        net = j - steps
        s = spec.spot * math.exp(float(net) * dx)
        v[j] = payoff(s, spec.strike, spec.type)

    for i in range(steps - 1, -1, -1):
        for j in range(2 * i + 1):
            cont = disc * (pd * v[j] + pm * v[j + 1] + pu * v[j + 2])
            if american:
                net = j - i
                s = spec.spot * math.exp(float(net) * dx)
                nxt[j] = max(payoff(s, spec.strike, spec.type), cont)
            else:
                nxt[j] = cont
        v, nxt = nxt, v

    return PricingResult(
        value=v[0],
        work=steps,
        method="kamrad-ritchken",
        converged=True,
        notes="american" if american else "european",
    )


def _dispatch(spec: VanillaSpec, steps: int, model: TreeModel, american: bool) -> PricingResult:
    if model is TreeModel.COX_ROSS_RUBINSTEIN:
        return _crr(spec, steps, american)
    if model is TreeModel.JARROW_RUDD:
        return _jr(spec, steps, american)
    if model is TreeModel.LEISEN_REIMER:
        return _lr(spec, steps, american)
    if model is TreeModel.KAMRAD_RITCHKEN:
        return _trinomial(spec, steps, american)
    raise ValueError("unknown tree model")


@dataclass
class TreeConfig:
    steps: int = 401
    model: TreeModel = TreeModel.COX_ROSS_RUBINSTEIN
    style: ExerciseStyle = ExerciseStyle.EUROPEAN
    richardson: bool = False


@dataclass
class AdaptiveTreeConfig:
    model: TreeModel = TreeModel.LEISEN_REIMER
    style: ExerciseStyle = ExerciseStyle.EUROPEAN
    abs_tol: float = 1e-6
    min_steps: int = 51
    max_steps: int = 5001


def cox_ross_rubinstein(
    spec: VanillaSpec, steps: int, style: ExerciseStyle = ExerciseStyle.EUROPEAN
) -> PricingResult:
    return _crr(spec, steps, style is ExerciseStyle.AMERICAN)


def jarrow_rudd(
    spec: VanillaSpec, steps: int, style: ExerciseStyle = ExerciseStyle.EUROPEAN
) -> PricingResult:
    return _jr(spec, steps, style is ExerciseStyle.AMERICAN)


def leisen_reimer(
    spec: VanillaSpec, steps: int, style: ExerciseStyle = ExerciseStyle.EUROPEAN
) -> PricingResult:
    return _lr(spec, steps, style is ExerciseStyle.AMERICAN)


def kamrad_ritchken(
    spec: VanillaSpec, steps: int, style: ExerciseStyle = ExerciseStyle.EUROPEAN
) -> PricingResult:
    return _trinomial(spec, steps, style is ExerciseStyle.AMERICAN)


def price(spec: VanillaSpec, cfg: TreeConfig) -> PricingResult:
    american = cfg.style is ExerciseStyle.AMERICAN
    if not cfg.richardson:
        r = _dispatch(spec, cfg.steps, cfg.model, american)
        if cfg.steps >= 4:
            half = _dispatch(spec, max(1, cfg.steps // 2), cfg.model, american)
            r.error_estimate = abs(r.value - half.value)
        return r

    coarse = _dispatch(spec, cfg.steps, cfg.model, american)
    fine_steps = _odd_steps(2 * cfg.steps) if cfg.model is TreeModel.LEISEN_REIMER else 2 * cfg.steps
    fine = _dispatch(spec, fine_steps, cfg.model, american)
    return PricingResult(
        value=2.0 * fine.value - coarse.value,
        error_estimate=abs(fine.value - coarse.value),
        work=coarse.work + fine.work,
        method=coarse.method,
        converged=True,
        notes=("american" if american else "european") + ", richardson",
    )


def adaptive(spec: VanillaSpec, cfg: AdaptiveTreeConfig | None = None) -> PricingResult:
    if cfg is None:
        cfg = AdaptiveTreeConfig()
    if cfg.abs_tol <= 0.0:
        raise ValueError("adaptive abs_tol must be positive")
    n = cfg.min_steps
    if cfg.model is TreeModel.LEISEN_REIMER:
        n = _odd_steps(n)

    prev: PricingResult | None = None
    last = PricingResult()
    while n <= cfg.max_steps:
        last = _dispatch(spec, n, cfg.model, cfg.style is ExerciseStyle.AMERICAN)
        if prev is not None:
            last.error_estimate = abs(last.value - prev.value)
            last.notes += "adaptive" if last.notes == "" else ", adaptive"
            if last.error_estimate <= cfg.abs_tol:
                last.converged = True
                return last
        prev = last
        n = _odd_steps(2 * n) if cfg.model is TreeModel.LEISEN_REIMER else 2 * n

    last.converged = False
    last.notes = "hit max_steps"
    return last
