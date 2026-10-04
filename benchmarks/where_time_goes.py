"""Where the time goes in the NumPy and pure-Python kernels.

Each path loop is rebuilt one step at a time (draw the normal, then add exp, then the
payoff, then the moments) and the cost of a step is the time it adds. The companion for
the C++ kernel is where_time_goes.cpp.

    python benchmarks/where_time_goes.py
"""

from __future__ import annotations

import math
import statistics
import time

from derivkit import _mc_python
from derivkit._moments import WelfordPair
from derivkit.comparison import pin_to_one_thread
from derivkit.rng import NormalRng
from derivkit.types import OptionType, VanillaSpec, payoff

SPEC = VanillaSpec(
    spot=100.0, strike=100.0, rate=0.05, dividend=0.0, vol=0.2, time=1.0, type=OptionType.CALL
)
DRIFT = (SPEC.rate - SPEC.dividend - 0.5 * SPEC.vol * SPEC.vol) * SPEC.time
VOL_T = SPEC.vol * math.sqrt(SPEC.time)
DF = math.exp(-SPEC.rate * SPEC.time)
REPEATS = 7


def measure(paths: int, run) -> float:
    """Median nanoseconds per path over REPEATS runs of `run(paths)`, after a warm-up."""
    run(paths)
    samples = []
    for _ in range(REPEATS):
        start = time.perf_counter()
        run(paths)
        samples.append((time.perf_counter() - start) / paths * 1e9)
    return statistics.median(samples)


def table(title: str, rows: list[tuple[str, float]]) -> None:
    print(f"\n| {title:<52} | {'ns':>8} |")
    print(f"| {'---':<52} | {'---:':>8} |")
    for name, ns in rows:
        print(f"| {name:<52} | {ns:8.2f} |")


def numpy_breakdown() -> None:
    import numpy as np

    from derivkit import _mc_numpy

    chunk = 1 << 16  # the kernel's own chunk size
    shift = math.log(DF * SPEC.spot) + DRIFT
    strike = DF * SPEC.strike
    z, x, y = np.empty(chunk), np.empty(chunk), np.empty(chunk)

    def stage(steps: int):
        """The kernel's chunk loop, cut off after the first `steps` steps."""

        def run(paths: int) -> None:
            rng = np.random.Generator(np.random.PCG64(1))
            acc = WelfordPair()
            for _ in range(paths // chunk):
                rng.standard_normal(out=z)
                if steps >= 2:
                    np.multiply(z, VOL_T, out=z)
                    np.add(z, shift, out=x)
                if steps >= 3:
                    np.exp(x, out=x)
                if steps >= 4:
                    np.subtract(x, strike, out=y)
                    np.maximum(y, 0.0, out=y)
                if steps >= 5:
                    _mc_numpy._accumulate(acc, x, y)

        return run

    paths = 64 * chunk
    t = [measure(paths, stage(k)) for k in range(1, 6)]
    kernel = measure(paths, lambda n: _mc_numpy.EuropeanSampler(SPEC, 1, False).advance(n))
    pair = measure(paths, lambda n: _mc_numpy.EuropeanSampler(SPEC, 1, True).advance(n))
    table(
        "NumPy kernel, cost per path",
        [
            ("PCG64 normal draw (standard_normal)", t[0]),
            ("scale and shift (2 array passes)", t[1] - t[0]),
            ("exp of the whole array", t[2] - t[1]),
            ("payoff (2 array passes)", t[3] - t[2]),
            ("chunk moments (2 means, 2 centrings, 3 dots)", t[4] - t[3]),
            ("whole kernel, one path", kernel),
            ("whole kernel, one antithetic pair", pair),
        ],
    )


def python_breakdown() -> None:
    spot, strike, kind = SPEC.spot, SPEC.strike, SPEC.type

    def draw_only(paths: int) -> None:
        rng = NormalRng(1)
        for _ in range(paths):
            rng.normal()

    def draw_exp_payoff(paths: int) -> None:
        rng = NormalRng(1)
        for _ in range(paths):
            st = spot * math.exp(DRIFT + VOL_T * rng.normal())
            DF * st, DF * payoff(st, strike, kind)

    def empty_loop(paths: int) -> None:
        for _ in range(paths):
            pass

    paths = 100_000
    loop = measure(paths, empty_loop)
    draw = measure(paths, draw_only)
    priced = measure(paths, draw_exp_payoff)
    kernel = measure(paths, lambda n: _mc_python.EuropeanSampler(SPEC, 1, False).advance(n))
    pair = measure(paths, lambda n: _mc_python.EuropeanSampler(SPEC, 1, True).advance(n))
    table(
        "Pure-Python kernel, cost per path",
        [
            ("an empty loop iteration, for scale", loop),
            ("mt19937_64 + Box-Muller normal draw", draw),
            ("exp and payoff", priced - draw),
            ("Welford update", kernel - priced),
            ("whole kernel, one path", kernel),
            ("whole kernel, one antithetic pair", pair),
        ],
    )


def main() -> int:
    pin_to_one_thread()
    try:
        numpy_breakdown()
    except ImportError:
        print("NumPy is not installed; skipping the NumPy breakdown.")
    python_breakdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
