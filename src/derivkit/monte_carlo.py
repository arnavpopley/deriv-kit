from __future__ import annotations

import math
from dataclasses import dataclass

from derivkit.black_scholes import geometric_asian, price_result
from derivkit.result import PricingResult
from derivkit.rng import NormalRng
from derivkit.types import (
    VanillaSpec,
    VarianceReduction,
    discount_factor,
    has_flag,
    payoff,
    validate,
)


class _WelfordPair:
    def __init__(self) -> None:
        self.n = 0
        self.mean_x = 0.0
        self.mean_y = 0.0
        self.m2_x = 0.0
        self.m2_y = 0.0
        self.c_xy = 0.0

    def add(self, x: float, y: float) -> None:
        self.n += 1
        nn = float(self.n)
        dx = x - self.mean_x
        self.mean_x += dx / nn
        dy = y - self.mean_y
        self.mean_y += dy / nn
        self.m2_x += dx * (x - self.mean_x)
        self.m2_y += dy * (y - self.mean_y)
        self.c_xy += dx * (y - self.mean_y)

    def var_x(self) -> float:
        return self.m2_x / float(self.n - 1) if self.n > 1 else 0.0

    def var_y(self) -> float:
        return self.m2_y / float(self.n - 1) if self.n > 1 else 0.0

    def cov_xy(self) -> float:
        return self.c_xy / float(self.n - 1) if self.n > 1 else 0.0


@dataclass
class McConfig:
    paths: int = 100000
    seed: int = 1
    vr: VarianceReduction = VarianceReduction.NONE


@dataclass
class AdaptiveMcConfig:
    base: McConfig | None = None
    stderr_tol: float = 1e-3
    batch: int = 20000
    max_paths: int = 2000000

    def __post_init__(self) -> None:
        if self.base is None:
            self.base = McConfig()


@dataclass
class AsianConfig:
    mc: McConfig | None = None
    steps: int = 50

    def __post_init__(self) -> None:
        if self.mc is None:
            self.mc = McConfig()


def _known_mean_st(spec: VanillaSpec) -> float:
    return spec.spot * discount_factor(spec.dividend, spec.time)


def _european_pair(spec: VanillaSpec, z: float, antithetic: bool) -> tuple[float, float]:
    drift = (spec.rate - spec.dividend - 0.5 * spec.vol * spec.vol) * spec.time
    vol_t = spec.vol * math.sqrt(spec.time)
    df = discount_factor(spec.rate, spec.time)

    def one(zz: float) -> tuple[float, float]:
        st = spec.spot * math.exp(drift + vol_t * zz)
        return df * st, df * payoff(st, spec.strike, spec.type)

    if not antithetic:
        return one(z)
    ax, ay = one(z)
    bx, by = one(-z)
    return 0.5 * (ax + bx), 0.5 * (ay + by)


def _finish_cv(acc: _WelfordPair, ex: float, method: str, used_cv: bool) -> PricingResult:
    r = PricingResult(work=acc.n, method=method, converged=acc.n > 1)
    if not used_cv or acc.var_x() <= 0.0:
        r.value = acc.mean_y
        r.error_estimate = math.sqrt(acc.var_y() / float(acc.n)) if acc.n > 1 else 0.0
        return r
    beta = acc.cov_xy() / acc.var_x()
    r.value = acc.mean_y - beta * (acc.mean_x - ex)
    var = acc.var_y() + beta * beta * acc.var_x() - 2.0 * beta * acc.cov_xy()
    r.error_estimate = math.sqrt(max(var, 0.0) / float(acc.n)) if acc.n > 1 else 0.0
    r.notes = f"beta={beta}"
    return r


def _european_method_name(vr: VarianceReduction) -> str:
    a = has_flag(vr, VarianceReduction.ANTITHETIC)
    c = has_flag(vr, VarianceReduction.CONTROL_VARIATE)
    if a and c:
        return "mc-european-antithetic-cv"
    if a:
        return "mc-european-antithetic"
    if c:
        return "mc-european-cv"
    return "mc-european"


def european(spec: VanillaSpec, cfg: McConfig | None = None) -> PricingResult:
    if cfg is None:
        cfg = McConfig()
    validate(spec)
    if cfg.paths < 2:
        raise ValueError("monte carlo requires at least 2 paths")
    if spec.time == 0.0 or spec.vol == 0.0:
        r = price_result(spec)
        r.method = _european_method_name(cfg.vr)
        r.work = cfg.paths
        return r

    anti = has_flag(cfg.vr, VarianceReduction.ANTITHETIC)
    cv = has_flag(cfg.vr, VarianceReduction.CONTROL_VARIATE)
    ex = _known_mean_st(spec)
    rng = NormalRng(cfg.seed)
    acc = _WelfordPair()
    for _ in range(cfg.paths):
        x, y = _european_pair(spec, rng.normal(), anti)
        acc.add(x, y)
    return _finish_cv(acc, ex, _european_method_name(cfg.vr), cv)


def european_adaptive(spec: VanillaSpec, cfg: AdaptiveMcConfig | None = None) -> PricingResult:
    if cfg is None:
        cfg = AdaptiveMcConfig()
    validate(spec)
    if cfg.stderr_tol <= 0.0:
        raise ValueError("stderr_tol must be positive")
    if cfg.batch < 2 or cfg.max_paths < cfg.batch:
        raise ValueError("invalid adaptive path budget")

    anti = has_flag(cfg.base.vr, VarianceReduction.ANTITHETIC)
    cv = has_flag(cfg.base.vr, VarianceReduction.CONTROL_VARIATE)
    ex = _known_mean_st(spec)
    rng = NormalRng(cfg.base.seed)
    acc = _WelfordPair()
    last = PricingResult()
    while acc.n < cfg.max_paths:
        remaining = cfg.max_paths - acc.n
        take = min(cfg.batch, remaining)
        for _ in range(take):
            x, y = _european_pair(spec, rng.normal(), anti)
            acc.add(x, y)
        last = _finish_cv(acc, ex, _european_method_name(cfg.base.vr), cv)
        last.notes = "adaptive" if last.notes == "" else last.notes + ", adaptive"
        if last.error_estimate <= cfg.stderr_tol and acc.n >= cfg.batch:
            last.converged = True
            return last
    last.converged = last.error_estimate <= cfg.stderr_tol
    if not last.converged:
        last.notes = "hit max_paths" if last.notes == "" else last.notes + ", hit max_paths"
    return last


def arithmetic_asian(spec: VanillaSpec, cfg: AsianConfig | None = None) -> PricingResult:
    if cfg is None:
        cfg = AsianConfig()
    validate(spec)
    if cfg.mc.paths < 2:
        raise ValueError("monte carlo requires at least 2 paths")
    if cfg.steps == 0:
        raise ValueError("asian steps must be positive")

    anti = has_flag(cfg.mc.vr, VarianceReduction.ANTITHETIC)
    cv = has_flag(cfg.mc.vr, VarianceReduction.CONTROL_VARIATE)
    ex = geometric_asian(spec, cfg.steps)
    dt = spec.time / float(cfg.steps)
    drift = (spec.rate - spec.dividend - 0.5 * spec.vol * spec.vol) * dt
    vol_dt = spec.vol * math.sqrt(dt)
    df = discount_factor(spec.rate, spec.time)
    nfix = float(cfg.steps)
    rng = NormalRng(cfg.mc.seed)
    acc = _WelfordPair()

    for _ in range(cfg.mc.paths):
        if not anti:
            s = spec.spot
            total = 0.0
            logsum = 0.0
            for _k in range(cfg.steps):
                z = rng.normal()
                s *= math.exp(drift + vol_dt * z)
                total += s
                logsum += math.log(s)
            y = df * payoff(total / nfix, spec.strike, spec.type)
            x = df * payoff(math.exp(logsum / nfix), spec.strike, spec.type)
            acc.add(x, y)
        else:
            zs = [rng.normal() for _k in range(cfg.steps)]

            def replay(sign: float) -> tuple[float, float]:
                s = spec.spot
                total = 0.0
                logsum = 0.0
                for z in zs:
                    s *= math.exp(drift + vol_dt * sign * z)
                    total += s
                    logsum += math.log(s)
                return (
                    df * payoff(math.exp(logsum / nfix), spec.strike, spec.type),
                    df * payoff(total / nfix, spec.strike, spec.type),
                )

            ax, ay = replay(1.0)
            bx, by = replay(-1.0)
            acc.add(0.5 * (ax + bx), 0.5 * (ay + by))

    if anti and cv:
        name = "mc-asian-antithetic-cv"
    elif anti:
        name = "mc-asian-antithetic"
    elif cv:
        name = "mc-asian-cv"
    else:
        name = "mc-asian"
    r = _finish_cv(acc, ex, name, cv)
    if cv:
        r.notes = "geo-asian control" if r.notes == "" else r.notes + ", geo-asian control"
    return r
