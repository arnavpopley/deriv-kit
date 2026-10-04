"""C++ Monte Carlo kernel: a thin adapter over the compiled extension `_mc_cpp_ext`.

Importing this module fails with ImportError when the extension has not been built;
`derivkit.backends` turns that into a BackendUnavailableError with build instructions.

The extension takes plain numbers and returns plain tuples. This adapter unpacks the
`VanillaSpec` on the way in and wraps the moments in a `WelfordPair` on the way out, so
the C++ kernel looks exactly like the other two to `monte_carlo`.
"""

from __future__ import annotations

from derivkit import _mc_cpp_ext as _ext
from derivkit._moments import WelfordPair
from derivkit.types import OptionType, VanillaSpec

_MASK64 = 0xFFFFFFFFFFFFFFFF  # the Python generator reduces seeds mod 2^64; do the same here

build_info = _ext.build_info


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
        self._impl.advance(paths)

    def moments(self) -> WelfordPair:
        return WelfordPair(*self._impl.moments())


def asian_moments(
    spec: VanillaSpec, steps: int, paths: int, seed: int, antithetic: bool
) -> WelfordPair:
    """Arithmetic-average payoff (y) paired with the geometric-average payoff (x)."""
    return WelfordPair(
        *_ext.asian_moments(*_scalars(spec), steps, paths, seed & _MASK64, antithetic)
    )
