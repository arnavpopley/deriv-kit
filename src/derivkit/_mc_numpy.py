"""NumPy-vectorised Monte Carlo kernel.

Same model and estimators as `_mc_python`, written the way NumPy code is normally written:
whole arrays at a time, NumPy's own generator (PCG64 with its ziggurat normal sampler) and
work buffers reused in place. The random stream therefore differs from the python and cpp
kernels: results agree statistically, not digit for digit.

Paths are processed in chunks, so memory stays bounded for any path count and the work
arrays stay in cache. The only BLAS routine used is `dot` (three inner products per
chunk). `derivkit.comparison` asks BLAS for one thread before timing and reports CPU time
over wall time, so extra threads would show up in the results.
"""

from __future__ import annotations

import math
import operator
import sys

import numpy as np

from derivkit._moments import WelfordPair
from derivkit.rng import _MASK64
from derivkit.types import OptionType, VanillaSpec, discount_factor

_CHUNK = 1 << 16  # float64 elements per work array: 512 KiB each

# Overflow to inf is reported by the caller (monte_carlo raises OverflowError on non-finite
# moments), so NumPy's own floating-point warnings would only repeat it.
_QUIET = {"over": "ignore", "invalid": "ignore"}


def _generator(seed: int) -> np.random.Generator:
    return np.random.Generator(np.random.PCG64(seed & _MASK64))


def _payoff(price: np.ndarray, strike: float, is_call: bool, out: np.ndarray) -> np.ndarray:
    if is_call:
        np.subtract(price, strike, out=out)
    else:
        np.subtract(strike, price, out=out)
    return np.maximum(out, 0.0, out=out)


def _accumulate(acc: WelfordPair, x: np.ndarray, y: np.ndarray) -> None:
    """Fold one chunk into the running moments. Centres `x` and `y` in place.

    Centring on the chunk's own means before taking inner products avoids the cancellation
    in sum(x^2) - n * mean^2, which matters when the standard deviation is small next to
    the mean (low vol, deep in the money).
    """
    mean_x = float(x.mean())
    mean_y = float(y.mean())
    x -= mean_x
    y -= mean_y
    acc.merge(x.size, mean_x, mean_y, float(np.dot(x, x)), float(np.dot(y, y)), float(np.dot(x, y)))


def _settled(acc: WelfordPair) -> WelfordPair:
    """A copy of the moments with spread at the level of rounding noise set to exactly zero.

    Constant samples (zero volatility) should have zero variance. Chunk means are rounded,
    so merging chunks leaves a variance of order (machine epsilon x mean)^2 instead, which
    is enough to defeat the exact `var_x() <= 0` test that switches the control variate
    off. The python and cpp kernels give exactly zero; this makes numpy agree.
    """
    eps = 8.0 * sys.float_info.epsilon
    out = WelfordPair(acc.n, acc.mean_x, acc.mean_y, acc.m2_x, acc.m2_y, acc.c_xy)
    if out.m2_x <= out.n * (eps * abs(out.mean_x)) ** 2:
        out.m2_x = out.c_xy = 0.0
    if out.m2_y <= out.n * (eps * abs(out.mean_y)) ** 2:
        out.m2_y = out.c_xy = 0.0
    return out


class EuropeanSampler:
    """Exact GBM terminal sampling. `advance` may be called repeatedly; the stream continues."""

    def __init__(self, spec: VanillaSpec, seed: int, antithetic: bool) -> None:
        # With antithetic pairs each leg carries weight 1/2. That weight and the discount
        # factor ride inside the exponent and the strike, which saves two array passes:
        #   x = half * df * S_T = exp(shift + vol_t * z),  y = max(x - half * df * K, 0).
        half = 0.5 if antithetic else 1.0
        drift = (spec.rate - spec.dividend - 0.5 * spec.vol * spec.vol) * spec.time
        self._vol_t = spec.vol * math.sqrt(spec.time)
        # log(half * df * spot), with log(df) = -r T written out: the discount factor
        # itself underflows to zero for very large r T, and log(0) would be an error.
        self._shift = math.log(half * spec.spot) - spec.rate * spec.time + drift
        self._strike = half * discount_factor(spec.rate, spec.time) * spec.strike
        self._is_call = spec.type is OptionType.CALL
        self._antithetic = antithetic
        self._rng = _generator(seed)
        self._acc = WelfordPair()
        # np.empty reserves address space only; pages are touched as chunks use them.
        self._z = np.empty(_CHUNK)
        self._x = np.empty(_CHUNK)
        self._y = np.empty(_CHUNK)

    def advance(self, paths: int) -> None:
        shift, strike, is_call = self._shift, self._strike, self._is_call
        remaining = operator.index(paths)
        with np.errstate(**_QUIET):
            while remaining > 0:
                m = min(remaining, _CHUNK)
                z, x, y = self._z[:m], self._x[:m], self._y[:m]
                self._rng.standard_normal(out=z)
                z *= self._vol_t
                np.add(z, shift, out=x)
                np.exp(x, out=x)
                _payoff(x, strike, is_call, out=y)
                if self._antithetic:
                    # Reuse z for the mirrored leg: exp(shift - vol_t * z).
                    np.subtract(shift, z, out=z)
                    np.exp(z, out=z)
                    x += z
                    y += _payoff(z, strike, is_call, out=z)
                _accumulate(self._acc, x, y)
                remaining -= m

    def moments(self) -> WelfordPair:
        return _settled(self._acc)


def asian_moments(
    spec: VanillaSpec, steps: int, paths: int, seed: int, antithetic: bool
) -> WelfordPair:
    """Arithmetic-average payoff (y) paired with the geometric-average payoff (x)."""
    steps = operator.index(steps)
    remaining = operator.index(paths)
    dt = spec.time / float(steps)
    drift = (spec.rate - spec.dividend - 0.5 * spec.vol * spec.vol) * dt
    vol_dt = spec.vol * math.sqrt(dt)
    scale = (0.5 if antithetic else 1.0) * discount_factor(spec.rate, spec.time)
    strike, is_call = spec.strike, spec.type is OptionType.CALL
    log_spot = math.log(spec.spot)
    rows = max(1, _CHUNK // steps)
    rng = _generator(seed)
    acc = WelfordPair()
    z = np.empty((rows, steps))
    w = np.empty((rows, steps))
    x, y, x2, y2 = (np.empty(rows) for _ in range(4))

    def leg(shocks: np.ndarray, geo: np.ndarray, arith: np.ndarray) -> None:
        """Discounted geometric- and arithmetic-average payoffs for one set of shocks."""
        logs = w[: shocks.shape[0]]
        np.add(shocks, drift, out=logs)
        # Start every path at log(S_0), so the running sum is log(S_k) itself. Working
        # with log(S_k / S_0) and multiplying by S_0 afterwards would overflow whenever
        # that ratio is huge, even when the price S_k is an ordinary finite number.
        logs[:, 0] += log_spot
        np.cumsum(logs, axis=1, out=logs)  # log(S_k) at each fixing
        logs.mean(axis=1, out=geo)
        np.exp(geo, out=geo)  # geometric average of the S_k
        np.exp(logs, out=logs)  # S_k
        logs.mean(axis=1, out=arith)
        _payoff(geo, strike, is_call, out=geo)
        _payoff(arith, strike, is_call, out=arith)
        geo *= scale
        arith *= scale

    with np.errstate(**_QUIET):
        while remaining > 0:
            m = min(remaining, rows)
            shocks = z[:m]
            rng.standard_normal(out=shocks)
            shocks *= vol_dt
            leg(shocks, x[:m], y[:m])
            if antithetic:
                np.negative(shocks, out=shocks)
                leg(shocks, x2[:m], y2[:m])
                x[:m] += x2[:m]
                y[:m] += y2[:m]
            _accumulate(acc, x[:m], y[:m])
            remaining -= m
    return _settled(acc)
