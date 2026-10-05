"""The back ends must agree with each other and with the Black-Scholes closed form.

Tolerances, and why each one is what it is:

SAME_STREAM_REL = 1 x 10^-9 (python vs cpp)
    These two share a generator (mt19937_64 + Box-Muller) and do the same arithmetic in
    the same order, so one seed gives one answer. On the development machine the match is
    exact with both Apple clang and GCC. The slack only allows for a compiler replacing
    separate sin and cos calls with a combined one that rounds the last digit differently.

SIGMAS = 4 (any back end vs Black-Scholes, and numpy vs python/cpp)
    A Monte Carlo price is approximately normal around the true price with standard
    deviation equal to its standard error, so a correct engine misses by more than 4
    standard errors with probability 6.3 x 10^-5. Two independent estimates differ by a
    normal with variance se_a^2 + se_b^2, hence the combined bound. The seeds are fixed,
    so the test is deterministic; 4 sigma means a correct engine passes for practically
    any seed or NumPy stream, while with both variance reductions on (standard error about
    0.006 at 10^5 paths) a pricing bias of 0.25% already fails.

STDERR_REL = 5% (standard errors across back ends)
    Each back end estimates the same variance from 10^5 paths. Between independent
    streams the standard errors in these cases differ by at most 1.3%, so 5% is loose for
    a correct engine and far below the 41% or 100% shift that a mis-weighted antithetic
    pair or control produces.
"""

import itertools
import math
import os
import subprocess
import sys
from pathlib import Path

import pytest
from conftest import require_backend, usable_backends

from derivkit import backends as registry
from derivkit.black_scholes import price
from derivkit.monte_carlo import (
    AdaptiveMcConfig,
    AsianConfig,
    McConfig,
    arithmetic_asian,
    european,
    european_adaptive,
)
from derivkit.types import OptionType, VanillaSpec, VarianceReduction

SAME_STREAM_REL = 1e-9
SIGMAS = 4.0
STDERR_REL = 0.05
PATHS = 100_000
SEED = 2024

SAME_STREAM = {"python", "cpp"}

SPECS = {
    "call": VanillaSpec(
        spot=100.0, strike=100.0, rate=0.05, dividend=0.0, vol=0.2, time=1.0, type=OptionType.CALL
    ),
    "put": VanillaSpec(
        spot=95.0, strike=100.0, rate=0.03, dividend=0.01, vol=0.3, time=0.5, type=OptionType.PUT
    ),
}

VR = {
    "none": VarianceReduction.NONE,
    "antithetic": VarianceReduction.ANTITHETIC,
    "cv": VarianceReduction.CONTROL_VARIATE,
    "both": VarianceReduction.ANTITHETIC | VarianceReduction.CONTROL_VARIATE,
}

CASES = list(itertools.product(SPECS, VR))


def assert_pair_agrees(name_a, a, name_b, b):
    if {name_a, name_b} == SAME_STREAM:
        assert a.value == pytest.approx(b.value, rel=SAME_STREAM_REL)
        assert a.error_estimate == pytest.approx(b.error_estimate, rel=SAME_STREAM_REL)
    else:
        combined = math.hypot(a.error_estimate, b.error_estimate)
        assert abs(a.value - b.value) <= SIGMAS * combined, (name_a, name_b)
        assert a.error_estimate == pytest.approx(b.error_estimate, rel=STDERR_REL)
    assert (a.work, a.method) == (b.work, b.method)


@pytest.mark.parametrize(("spec_name", "vr_name"), CASES)
def test_european_agrees_with_black_scholes_and_across_backends(spec_name, vr_name):
    spec = SPECS[spec_name]
    reference = price(spec)
    cfg = McConfig(paths=PATHS, seed=SEED, vr=VR[vr_name])
    results = {b: european(spec, cfg, backend=b) for b in usable_backends()}

    for name, r in results.items():
        assert abs(r.value - reference) <= SIGMAS * r.error_estimate, name
    for (name_a, a), (name_b, b) in itertools.combinations(results.items(), 2):
        assert_pair_agrees(name_a, a, name_b, b)


@pytest.mark.parametrize("vr_name", list(VR))
def test_asian_agrees_across_backends(vr_name):
    cfg = AsianConfig(mc=McConfig(paths=6000, seed=SEED, vr=VR[vr_name]), steps=20)
    results = {b: arithmetic_asian(SPECS["call"], cfg, backend=b) for b in usable_backends()}
    for (name_a, a), (name_b, b) in itertools.combinations(results.items(), 2):
        if {name_a, name_b} == SAME_STREAM:
            assert_pair_agrees(name_a, a, name_b, b)
        else:
            # 6000 paths: the standard-error estimates are themselves noisier, so only
            # the prices are compared here.
            combined = math.hypot(a.error_estimate, b.error_estimate)
            assert abs(a.value - b.value) <= SIGMAS * combined, (name_a, name_b)
        assert a.notes.endswith("geo-asian control") == b.notes.endswith("geo-asian control")


def test_adaptive_stops_on_the_same_rule_in_every_backend(backend):
    spec = SPECS["call"]
    cfg = AdaptiveMcConfig(
        base=McConfig(seed=SEED, vr=VR["both"]),
        stderr_tol=4e-3,
        batch=7001,  # odd on purpose: a Box-Muller spare is carried across batches
        max_paths=400_000,
    )
    r = european_adaptive(spec, cfg, backend=backend)
    assert r.converged
    assert r.error_estimate <= cfg.stderr_tol
    assert r.work % cfg.batch == 0
    assert abs(r.value - price(spec)) <= SIGMAS * r.error_estimate
    assert r.notes.endswith("adaptive")


@pytest.mark.parametrize("antithetic", [False, True])
def test_batches_continue_the_stream(backend, antithetic):
    """Advancing in uneven batches must equal one call of the same total length."""
    kernel = registry.kernel(backend)
    whole = kernel.EuropeanSampler(SPECS["put"], SEED, antithetic)
    whole.advance(771)
    pieces = kernel.EuropeanSampler(SPECS["put"], SEED, antithetic)
    for n in (7, 1, 250, 513):
        pieces.advance(n)
    a, b = whole.moments(), pieces.moments()
    fields = ("n", "mean_x", "mean_y", "m2_x", "m2_y", "c_xy")
    if backend in SAME_STREAM:
        assert [getattr(a, f) for f in fields] == [getattr(b, f) for f in fields]
    else:
        # Same draws, but chunk moments are merged in a different order: equal to rounding.
        assert a.n == b.n
        for f in fields[1:]:
            assert getattr(a, f) == pytest.approx(getattr(b, f), rel=1e-11)


def test_constant_payoffs_have_zero_error_and_no_beta(backend):
    """Zero volatility: every path is the same, so the error is exactly zero and there is
    no control-variate slope to estimate. 70,000-path batches span two NumPy chunks."""
    flat = VanillaSpec(spot=100.0, strike=90.0, rate=0.05, vol=0.0, time=1.0)
    cfg = AdaptiveMcConfig(base=McConfig(vr=VR["cv"]), batch=70_000, max_paths=200_000)
    r = european_adaptive(flat, cfg, backend=backend)
    assert r.error_estimate == 0.0
    assert "beta" not in r.notes
    assert r.value == pytest.approx(price(flat), rel=1e-12)


def test_a_fully_discounted_option_is_worth_zero_in_every_backend(backend):
    # exp(-r T) underflows to zero here; the price is 0, not an error.
    spec = VanillaSpec(spot=100.0, strike=100.0, rate=8.0, dividend=8.0, vol=0.2, time=100.0)
    r = european(spec, McConfig(paths=1000), backend=backend)
    assert (r.value, r.error_estimate) == (0.0, 0.0)


@pytest.mark.parametrize("name", ["numpy", "cpp"])
def test_overflow_raises_instead_of_returning_nan(name):
    """The compiled kernels cannot raise in mid-loop, so their result is checked afterwards."""
    require_backend(name)
    spec = VanillaSpec(spot=100.0, strike=100.0, rate=8.0, vol=0.2, time=100.0)
    with pytest.raises(OverflowError, match="overflowed"):
        arithmetic_asian(spec, AsianConfig(mc=McConfig(paths=200), steps=4), backend=name)


def test_cpp_runs_in_slices_without_changing_the_result(cpp_backend, monkeypatch):
    """Long C++ runs are cut into slices so Ctrl-C can get through. The cut must not show."""
    from derivkit import _mc_cpp

    spec = SPECS["put"]
    euro = McConfig(paths=5001, seed=SEED, vr=VR["antithetic"])
    asian = AsianConfig(mc=McConfig(paths=301, seed=SEED, vr=VR["both"]), steps=12)
    monkeypatch.setattr(_mc_cpp, "_SLICE", 37)
    assert european(spec, euro, backend="cpp") == european(spec, euro)
    assert arithmetic_asian(spec, asian, backend="cpp") == arithmetic_asian(spec, asian)


@pytest.mark.skipif(sys.platform == "win32", reason="sends SIGINT to itself")
@pytest.mark.parametrize("engine", ["european", "asian"])
def test_ctrl_c_stops_a_long_cpp_run(cpp_backend, engine):
    """The child starts a simulation that would run for a minute or more, interrupts itself
    after 0.3 s, and must stop promptly with KeyboardInterrupt."""
    call = {
        "european": "european(spec, McConfig(paths=5_000_000_000), backend='cpp')",
        "asian": "arithmetic_asian(spec, AsianConfig(mc=McConfig(paths=200_000_000), steps=50), "
        "backend='cpp')",
    }[engine]
    script = f"""
import os, signal, threading, time
from derivkit.monte_carlo import AsianConfig, McConfig, arithmetic_asian, european
from derivkit.types import VanillaSpec
spec = VanillaSpec(spot=100.0, strike=100.0, rate=0.05, vol=0.2, time=1.0)
threading.Timer(0.3, lambda: os.kill(os.getpid(), signal.SIGINT)).start()
start = time.perf_counter()
try:
    {call}
except KeyboardInterrupt:
    print("interrupted", time.perf_counter() - start)
"""
    src = Path(__file__).resolve().parents[1] / "src"
    done = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONPATH": str(src)},
        timeout=30,
        check=False,
    )
    assert done.stdout.startswith("interrupted"), done.stderr
    assert float(done.stdout.split()[1]) < 5.0


def test_a_finite_price_is_not_lost_to_overflow_on_the_way(backend):
    """A tiny spot with a huge upward drift: S_k / S_0 overflows a double at the second
    fixing, but S_k itself is an ordinary number, so every back end must price it."""
    spec = VanillaSpec(spot=1e-300, strike=100.0, rate=0.0, dividend=-400.0, vol=0.1, time=2.0)
    cfg = AsianConfig(mc=McConfig(paths=4000, seed=SEED), steps=2)
    r = arithmetic_asian(spec, cfg, backend=backend)
    reference = arithmetic_asian(spec, cfg)  # the pure-Python engine
    assert math.isfinite(r.value) and r.value > 0.0
    combined = math.hypot(r.error_estimate, reference.error_estimate)
    assert abs(r.value - reference.value) <= SIGMAS * combined
