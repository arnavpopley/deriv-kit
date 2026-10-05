"""C++ Monte Carlo kernel: a thin adapter over the compiled extension `_mc_cpp_ext`.

Importing this module fails with ImportError when the extension has not been built;
`derivkit.backends` turns that into a BackendUnavailableError with build instructions.

The extension takes plain numbers and returns plain tuples. This adapter unpacks the
`VanillaSpec` on the way in and wraps the moments in a `WelfordPair` on the way out, so
the C++ kernel looks exactly like the other two to `monte_carlo`.

This is the one kernel with a choice of generator (`rng`):

    "reproducible"  mt19937_64 + Box-Muller: the same stream as the python back end
    "fast"          xoshiro256++ + ziggurat: its own stream, fixed by the seed
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

if not hasattr(_ext, "FastEuropeanSampler"):
    # An extension built before the fast generator existed. Failing the import makes
    # `backends` report the back end as present but broken, with this message.
    raise ImportError(
        "the compiled extension is out of date; rebuild it (cmake --build build)"
    )

RNGS: tuple[str, ...] = ("reproducible", "fast")
_EUROPEAN = {"reproducible": _ext.EuropeanSampler, "fast": _ext.FastEuropeanSampler}
_ASIAN = {"reproducible": _ext.AsianSampler, "fast": _ext.FastAsianSampler}


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

    def __init__(
        self, spec: VanillaSpec, seed: int, antithetic: bool, rng: str = "reproducible"
    ) -> None:
        self._impl = _EUROPEAN[rng](*_scalars(spec), seed & _MASK64, antithetic)

    def advance(self, paths: int) -> None:
        _advance(self._impl, paths)

    def moments(self) -> WelfordPair:
        return WelfordPair(*self._impl.moments())


def asian_moments(
    spec: VanillaSpec,
    steps: int,
    paths: int,
    seed: int,
    antithetic: bool,
    rng: str = "reproducible",
) -> WelfordPair:
    """Arithmetic-average payoff (y) paired with the geometric-average payoff (x)."""
    sampler = _ASIAN[rng](*_scalars(spec), steps, seed & _MASK64, antithetic)
    _advance(sampler, paths, draws_per_path=steps)
    return WelfordPair(*sampler.moments())


def normal_draws(rng: str, seed: int, count: int) -> list[float]:
    """The first `count` N(0, 1) draws of generator `rng` for `seed`. Used by the tests."""
    return _ext.normal_draws(rng, seed & _MASK64, count)
