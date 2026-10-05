"""C++ Monte Carlo kernel: a thin adapter over the compiled extension `_mc_cpp_ext`.

Importing this module fails with ImportError when the extension has not been built;
`derivkit.backends` turns that into a BackendUnavailableError with build instructions.

The extension takes plain numbers and returns plain tuples. This adapter unpacks the
`VanillaSpec` on the way in and wraps the moments in a `WelfordPair` on the way out, so
the C++ kernel looks exactly like the other two to `monte_carlo`.
"""

from __future__ import annotations

import operator

# Imported by its full name so that a missing extension raises ModuleNotFoundError naming
# this module, which is how `backends` tells "not built" from "built but broken".
import derivkit._mc_cpp_ext as _ext
from derivkit._moments import WelfordPair
from derivkit.rng import _MASK64  # the Python generator reduces seeds mod 2^64; so do we
from derivkit.types import OptionType, VanillaSpec

# Normal draws per call into C++. While C++ runs, Python cannot deliver Ctrl-C, so a long
# simulation is run as a series of calls of a few hundredths of a second each. The samplers
# continue their stream from call to call, so slicing does not change the result.
_SLICE = 1 << 22

build_info = _ext.build_info


def _advance(sampler, paths: int, draws_per_path: int = 1) -> None:
    remaining = operator.index(paths)  # same TypeError as range() for a non-integer
    step = max(1, _SLICE // draws_per_path)
    while remaining > 0:
        take = min(step, remaining)
        sampler.advance(take)
        remaining -= take


def _scalars(spec: VanillaSpec) -> tuple[float, float, float, float, float, float, bool]:
    return (
        spec.spot,
        spec.strike,
        spec.rate,
        spec.dividend,
        spec.vol,
        spec.time,
        spec.type is OptionType.CALL,
    )


class EuropeanSampler:
    """Exact GBM terminal sampling. `advance` may be called repeatedly; the stream continues."""

    def __init__(self, spec: VanillaSpec, seed: int, antithetic: bool) -> None:
        self._impl = _ext.EuropeanSampler(*_scalars(spec), seed & _MASK64, antithetic)

    def advance(self, paths: int) -> None:
        _advance(self._impl, paths)

    def moments(self) -> WelfordPair:
        return WelfordPair(*self._impl.moments())


def asian_moments(
    spec: VanillaSpec, steps: int, paths: int, seed: int, antithetic: bool
) -> WelfordPair:
    """Arithmetic-average payoff (y) paired with the geometric-average payoff (x)."""
    sampler = _ext.AsianSampler(*_scalars(spec), steps, seed & _MASK64, antithetic)
    _advance(sampler, paths, draws_per_path=steps)
    return WelfordPair(*sampler.moments())
