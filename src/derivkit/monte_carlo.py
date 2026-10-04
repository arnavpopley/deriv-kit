from __future__ import annotations

import math
from dataclasses import dataclass

from derivkit import backends as _backends
from derivkit._moments import WelfordPair as _WelfordPair
from derivkit.black_scholes import geometric_asian, price_result
from derivkit.result import PricingResult
from derivkit.types import (
    VanillaSpec,
    VarianceReduction,
    discount_factor,
    has_flag,
    validate,
)


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


def european(
    spec: VanillaSpec, cfg: McConfig | None = None, *, backend: str = "python"
) -> PricingResult:
    """European vanilla by exact GBM sampling.

    `backend` picks the kernel that runs the path loop: "python" (default, standard
    library only), "numpy" or "cpp". See `derivkit.backends`.
    """
    if cfg is None:
        cfg = McConfig()
    kernel = _backends.kernel(backend)
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
    sampler = kernel.EuropeanSampler(spec, cfg.seed, anti)
    sampler.advance(cfg.paths)
    return _finish_cv(sampler.moments(), ex, _european_method_name(cfg.vr), cv)


def european_adaptive(
    spec: VanillaSpec, cfg: AdaptiveMcConfig | None = None, *, backend: str = "python"
) -> PricingResult:
    """Draw batches until the standard error is below `stderr_tol` or `max_paths` is hit."""
    if cfg is None:
        cfg = AdaptiveMcConfig()
    kernel = _backends.kernel(backend)
    validate(spec)
    if cfg.stderr_tol <= 0.0:
        raise ValueError("stderr_tol must be positive")
    if cfg.batch < 2 or cfg.max_paths < cfg.batch:
        raise ValueError("invalid adaptive path budget")

    anti = has_flag(cfg.base.vr, VarianceReduction.ANTITHETIC)
    cv = has_flag(cfg.base.vr, VarianceReduction.CONTROL_VARIATE)
    ex = _known_mean_st(spec)
    sampler = kernel.EuropeanSampler(spec, cfg.base.seed, anti)
    done = 0
    last = PricingResult()
    while done < cfg.max_paths:
        remaining = cfg.max_paths - done
        take = min(cfg.batch, remaining)
        sampler.advance(take)
        done += take
        last = _finish_cv(sampler.moments(), ex, _european_method_name(cfg.base.vr), cv)
        last.notes = "adaptive" if last.notes == "" else last.notes + ", adaptive"
        if last.error_estimate <= cfg.stderr_tol and done >= cfg.batch:
            last.converged = True
            return last
    last.converged = last.error_estimate <= cfg.stderr_tol
    if not last.converged:
        last.notes = "hit max_paths" if last.notes == "" else last.notes + ", hit max_paths"
    return last


def arithmetic_asian(
    spec: VanillaSpec, cfg: AsianConfig | None = None, *, backend: str = "python"
) -> PricingResult:
    """Arithmetic-average Asian; the control variate is the geometric-average Asian."""
    if cfg is None:
        cfg = AsianConfig()
    kernel = _backends.kernel(backend)
    validate(spec)
    if cfg.mc.paths < 2:
        raise ValueError("monte carlo requires at least 2 paths")
    if cfg.steps == 0:
        raise ValueError("asian steps must be positive")

    anti = has_flag(cfg.mc.vr, VarianceReduction.ANTITHETIC)
    cv = has_flag(cfg.mc.vr, VarianceReduction.CONTROL_VARIATE)
    ex = geometric_asian(spec, cfg.steps)
    acc = kernel.asian_moments(spec, cfg.steps, cfg.mc.paths, cfg.mc.seed, anti)

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
