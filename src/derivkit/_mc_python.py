"""Pure-Python Monte Carlo kernel: the reference the other kernels must match.

A kernel only simulates paths and accumulates paired moments (x = discounted control,
y = discounted payoff). Validation, the control-variate finish and result formatting
live in `monte_carlo` and are shared by every back end.
"""

from __future__ import annotations

import math

from derivkit._moments import WelfordPair
from derivkit.rng import NormalRng
from derivkit.types import VanillaSpec, discount_factor, payoff


class EuropeanSampler:
    """Exact GBM terminal sampling. `advance` may be called repeatedly; the stream continues."""

    def __init__(self, spec: VanillaSpec, seed: int, antithetic: bool) -> None:
        self._spot = spec.spot
        self._strike = spec.strike
        self._type = spec.type
        self._drift = (spec.rate - spec.dividend - 0.5 * spec.vol * spec.vol) * spec.time
        self._vol_t = spec.vol * math.sqrt(spec.time)
        self._df = discount_factor(spec.rate, spec.time)
        self._antithetic = antithetic
        self._rng = NormalRng(seed)
        self._acc = WelfordPair()

    def advance(self, paths: int) -> None:
        spot, strike, kind = self._spot, self._strike, self._type
        drift, vol_t, df = self._drift, self._vol_t, self._df
        rng, acc = self._rng, self._acc
        if not self._antithetic:
            for _ in range(paths):
                st = spot * math.exp(drift + vol_t * rng.normal())
                acc.add(df * st, df * payoff(st, strike, kind))
        else:
            for _ in range(paths):
                z = rng.normal()
                up = spot * math.exp(drift + vol_t * z)
                down = spot * math.exp(drift + vol_t * -z)
                acc.add(
                    0.5 * (df * up + df * down),
                    0.5 * (df * payoff(up, strike, kind) + df * payoff(down, strike, kind)),
                )

    def moments(self) -> WelfordPair:
        return self._acc


def asian_moments(
    spec: VanillaSpec, steps: int, paths: int, seed: int, antithetic: bool
) -> WelfordPair:
    """Arithmetic-average payoff (y) paired with the geometric-average payoff (x)."""
    spot, strike, kind = spec.spot, spec.strike, spec.type
    dt = spec.time / float(steps)
    drift = (spec.rate - spec.dividend - 0.5 * spec.vol * spec.vol) * dt
    vol_dt = spec.vol * math.sqrt(dt)
    df = discount_factor(spec.rate, spec.time)
    nfix = float(steps)
    rng = NormalRng(seed)
    acc = WelfordPair()

    def replay(zs: list[float], sign: float) -> tuple[float, float]:
        s = spot
        total = 0.0
        logsum = 0.0
        for z in zs:
            s *= math.exp(drift + vol_dt * sign * z)
            total += s
            logsum += math.log(s)
        return (
            df * payoff(math.exp(logsum / nfix), strike, kind),
            df * payoff(total / nfix, strike, kind),
        )

    for _ in range(paths):
        if not antithetic:
            s = spot
            total = 0.0
            logsum = 0.0
            for _k in range(steps):
                z = rng.normal()
                s *= math.exp(drift + vol_dt * z)
                total += s
                logsum += math.log(s)
            y = df * payoff(total / nfix, strike, kind)
            x = df * payoff(math.exp(logsum / nfix), strike, kind)
            acc.add(x, y)
        else:
            zs = [rng.normal() for _k in range(steps)]
            ax, ay = replay(zs, 1.0)
            bx, by = replay(zs, -1.0)
            acc.add(0.5 * (ax + bx), 0.5 * (ay + by))
    return acc
