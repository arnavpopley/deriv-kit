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

import pytest
from conftest import usable_backends

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
        base=McConfig(seed=SEED, vr=VarianceReduction.ANTITHETIC | VarianceReduction.CONTROL_VARIATE),
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
