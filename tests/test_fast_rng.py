"""The cpp back end's fast generator: `backend="cpp", rng="fast"`.

It is xoshiro256++ with a ziggurat sampler, in place of mt19937_64 with Box-Muller. What
is promised, and tested here:

- It prices correctly: within SIGMAS standard errors of Black-Scholes, like every back end.
- It is repeatable: one seed gives one answer, in one call or in batches.
- Its draws are standard normal (moments, a chi-square test over 64 bins, and the tail).

What is not promised: that it matches python, numpy or the reproducible cpp generator
digit for digit. It is a different stream by design, so the golden and same-stream tests
leave it out by name (SAME_STREAM_RNGS in conftest.py), and a test below shows that it
really does land on different numbers.

Tolerances:

SIGMAS = 4
    As in test_backend_agreement.py: a correct engine misses by more than 4 standard
    errors with probability 6.3 x 10^-5. Seeds are fixed, so each test is deterministic.

STDERR_REL = 5%
    The fast and reproducible generators estimate the same variance from 10^5 paths, so
    their standard errors agree to about 1%. A sampler with the wrong variance or a
    missing tail would move the standard error, not only the price.

DRAW_REL = 1 x 10^-13 (reproducible C++ draws against the Python generator)
    The same arithmetic on the same integers. On one machine most draws are identical,
    but a compiler may merge a sin and a cos call into one that rounds the last digit
    differently, so a single unit in the last place (2 x 10^-16) is allowed for.
"""

import bisect
import math
import statistics
import sys
import types

import pytest
from conftest import OWN_STREAM_RNGS, SAME_STREAM_RNGS, require_backend
from test_monte_carlo_golden import GOLDEN, run_case

import derivkit
from derivkit import backends as registry
from derivkit.__main__ import main
from derivkit.black_scholes import price
from derivkit.comparison import FAST_CPP
from derivkit.monte_carlo import (
    AdaptiveMcConfig,
    AsianConfig,
    McConfig,
    arithmetic_asian,
    european,
    european_adaptive,
)
from derivkit.rng import NormalRng
from derivkit.types import OptionType, VanillaSpec, VarianceReduction

SIGMAS = 4.0
STDERR_REL = 0.05
DRAW_REL = 1e-13
PATHS = 100_000
SEED = 2024

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

FAST = {"backend": "cpp", "rng": "fast"}


@pytest.fixture
def fast(cpp_backend) -> dict[str, str]:
    """Keyword arguments that select the fast generator; skips when cpp is not built."""
    return FAST


# --------------------------------------------------------------------------------------
# Choosing a generator
# --------------------------------------------------------------------------------------


def test_every_generator_is_either_same_stream_or_exempt_by_name():
    """A new generator must be put in one group or the other before the tests pass, so it
    cannot slip past the golden comparison without anyone deciding that it should."""
    assert registry.RNGS == derivkit.RNGS == ("reproducible", "fast")
    assert sorted(SAME_STREAM_RNGS + OWN_STREAM_RNGS) == sorted(registry.RNGS)
    assert not set(SAME_STREAM_RNGS) & set(OWN_STREAM_RNGS)
    assert registry.DEFAULT_RNG in SAME_STREAM_RNGS


def test_reproducible_is_the_default_generator_in_every_backend(backend):
    cfg = McConfig(paths=2000, seed=5)
    assert european(SPECS["call"], cfg, backend=backend, rng="reproducible") == european(
        SPECS["call"], cfg, backend=backend
    )


@pytest.mark.parametrize("engine", [european, european_adaptive, arithmetic_asian])
def test_fast_needs_the_cpp_backend(engine):
    with pytest.raises(ValueError, match="rng='fast' needs backend='cpp'"):
        engine(SPECS["call"], rng="fast")  # the default back end is python
    with pytest.raises(ValueError, match="unknown rng 'quick'"):
        engine(SPECS["call"], rng="quick")


def test_numpy_has_no_fast_generator():
    require_backend("numpy")
    with pytest.raises(ValueError, match="backend 'numpy' has one generator"):
        european(SPECS["call"], McConfig(paths=10), backend="numpy", rng="fast")


def test_an_extension_built_before_the_fast_generator_is_reported_as_out_of_date(monkeypatch):
    """A stale build must not look like a working back end, or like one that was never
    built: it is present but broken, and the message says to rebuild."""
    stale = types.ModuleType("derivkit._mc_cpp_ext")
    stale.build_info = dict
    stale.EuropeanSampler = stale.AsianSampler = object
    monkeypatch.setitem(sys.modules, "derivkit._mc_cpp_ext", stale)
    monkeypatch.delitem(sys.modules, "derivkit._mc_cpp", raising=False)
    monkeypatch.delattr(derivkit, "_mc_cpp", raising=False)
    monkeypatch.delattr(derivkit, "_mc_cpp_ext", raising=False)
    with pytest.raises(derivkit.BackendUnavailableError, match="out of date; rebuild") as excinfo:
        european(SPECS["call"], McConfig(paths=10), backend="cpp")
    assert not excinfo.value.missing


# --------------------------------------------------------------------------------------
# Pricing
# --------------------------------------------------------------------------------------


@pytest.mark.parametrize("vr_name", list(VR))
@pytest.mark.parametrize("spec_name", list(SPECS))
def test_fast_european_is_within_four_standard_errors_of_black_scholes(spec_name, vr_name, fast):
    spec = SPECS[spec_name]
    cfg = McConfig(paths=PATHS, seed=SEED, vr=VR[vr_name])
    r = european(spec, cfg, **fast)
    assert abs(r.value - price(spec)) <= SIGMAS * r.error_estimate

    reference = european(spec, cfg, backend="cpp")  # the reproducible generator
    assert r.error_estimate == pytest.approx(reference.error_estimate, rel=STDERR_REL)
    assert (r.work, r.method) == (reference.work, reference.method)


@pytest.mark.parametrize("vr_name", list(VR))
def test_fast_asian_agrees_with_the_reproducible_generator(vr_name, fast):
    cfg = AsianConfig(mc=McConfig(paths=6000, seed=SEED, vr=VR[vr_name]), steps=20)
    r = arithmetic_asian(SPECS["call"], cfg, **fast)
    reference = arithmetic_asian(SPECS["call"], cfg, backend="cpp")
    combined = math.hypot(r.error_estimate, reference.error_estimate)
    assert abs(r.value - reference.value) <= SIGMAS * combined
    assert (r.work, r.method) == (reference.work, reference.method)
    assert r.notes.endswith("geo-asian control") == reference.notes.endswith("geo-asian control")


def test_fast_adaptive_stops_on_the_same_rule(fast):
    spec = SPECS["call"]
    cfg = AdaptiveMcConfig(
        base=McConfig(seed=SEED, vr=VR["both"]), stderr_tol=4e-3, batch=7001, max_paths=400_000
    )
    r = european_adaptive(spec, cfg, **fast)
    assert r.converged
    assert r.error_estimate <= cfg.stderr_tol
    assert r.work % cfg.batch == 0
    assert abs(r.value - price(spec)) <= SIGMAS * r.error_estimate
    assert r.notes.endswith("adaptive")


def test_fast_overflow_raises_instead_of_returning_nan(fast):
    spec = VanillaSpec(spot=100.0, strike=100.0, rate=8.0, vol=0.2, time=100.0)
    with pytest.raises(OverflowError, match="overflowed"):
        arithmetic_asian(spec, AsianConfig(mc=McConfig(paths=200), steps=4), **fast)


# --------------------------------------------------------------------------------------
# Repeatable, and a stream of its own
# --------------------------------------------------------------------------------------


def test_fast_is_deterministic_for_a_fixed_seed(fast):
    spec = SPECS["put"]
    euro = McConfig(paths=20_001, seed=SEED, vr=VR["antithetic"])
    asian = AsianConfig(mc=McConfig(paths=501, seed=SEED, vr=VR["both"]), steps=12)
    adaptive = AdaptiveMcConfig(base=McConfig(seed=SEED), stderr_tol=0.05, batch=1500)

    assert european(spec, euro, **fast) == european(spec, euro, **fast)
    assert arithmetic_asian(spec, asian, **fast) == arithmetic_asian(spec, asian, **fast)
    assert european_adaptive(spec, adaptive, **fast) == european_adaptive(spec, adaptive, **fast)

    other_seed = McConfig(paths=20_001, seed=SEED + 1, vr=VR["antithetic"])
    assert european(spec, other_seed, **fast).value != european(spec, euro, **fast).value


def test_fast_seeds_are_reduced_mod_two_to_the_64_like_the_other_generators(fast):
    spec = SPECS["call"]
    for seed in (0, 5):
        low = european(spec, McConfig(paths=3000, seed=seed), **fast)
        assert low == european(spec, McConfig(paths=3000, seed=seed + 2**64), **fast)
        assert low.value > 0.0


@pytest.mark.parametrize("antithetic", [False, True])
def test_fast_batches_continue_the_stream(cpp_backend, antithetic):
    """Advancing in uneven batches must equal one call of the same total length, exactly:
    the generator's state is carried from call to call and nothing is drawn twice."""
    from derivkit import _mc_cpp

    whole = _mc_cpp.EuropeanSampler(SPECS["put"], SEED, antithetic, rng="fast")
    whole.advance(771)
    pieces = _mc_cpp.EuropeanSampler(SPECS["put"], SEED, antithetic, rng="fast")
    for n in (7, 1, 250, 513):
        pieces.advance(n)
    a, b = whole.moments(), pieces.moments()
    fields = ("n", "mean_x", "mean_y", "m2_x", "m2_y", "c_xy")
    assert [getattr(a, f) for f in fields] == [getattr(b, f) for f in fields]


def test_fast_runs_in_slices_without_changing_the_result(fast, monkeypatch):
    from derivkit import _mc_cpp

    spec = SPECS["put"]
    euro = McConfig(paths=5001, seed=SEED, vr=VR["antithetic"])
    asian = AsianConfig(mc=McConfig(paths=301, seed=SEED, vr=VR["both"]), steps=12)
    in_one_piece = european(spec, euro, **fast), arithmetic_asian(spec, asian, **fast)
    monkeypatch.setattr(_mc_cpp, "_SLICE", 37)
    assert (european(spec, euro, **fast), arithmetic_asian(spec, asian, **fast)) == in_one_piece


def test_the_two_generators_produce_different_streams(cpp_backend):
    from derivkit import _mc_cpp

    n = 1000
    reproducible = _mc_cpp.normal_draws("reproducible", SEED, n)
    fast_draws = _mc_cpp.normal_draws("fast", SEED, n)
    assert len(reproducible) == len(fast_draws) == n
    assert not set(reproducible) & set(fast_draws)  # not one draw in common
    assert fast_draws == _mc_cpp.normal_draws("fast", SEED, n)  # and each is repeatable
    assert fast_draws[:10] != _mc_cpp.normal_draws("fast", SEED + 1, 10)

    cfg = McConfig(paths=PATHS, seed=SEED)
    assert european(SPECS["call"], cfg, **FAST).value != european(SPECS["call"], cfg).value
    with pytest.raises(ValueError, match="unknown rng"):
        _mc_cpp.normal_draws("quick", SEED, 1)


@pytest.mark.parametrize("case", list(GOLDEN), ids=lambda c: "-".join(c))
def test_fast_is_exempt_from_the_golden_numbers_because_it_does_not_reproduce_them(case, fast):
    """The other half of the exemption in test_monte_carlo_golden.py: the fast generator
    gives a valid result of the same kind, and a different number."""
    value, _, _, method, _, _ = GOLDEN[case]
    r = run_case(*case, **fast)
    assert r.method == method
    assert math.isfinite(r.value) and r.value > 0.0
    assert r.value != pytest.approx(value, rel=1e-9)


def test_reproducible_cpp_draws_are_the_python_generators_draws(cpp_backend):
    from derivkit import _mc_cpp

    n = 2001  # odd, so the last draw is half of a Box-Muller pair
    python = NormalRng(SEED)
    assert _mc_cpp.normal_draws("reproducible", SEED, n) == pytest.approx(
        [python.normal() for _ in range(n)], rel=DRAW_REL, abs=0.0
    )


# --------------------------------------------------------------------------------------
# The sampler itself
# --------------------------------------------------------------------------------------

DRAWS = 1_000_000
ZIGGURAT_R = 3.6541528853610088  # the edge beyond which the tail sampler takes over


@pytest.fixture(scope="module")
def fast_draws() -> list[float]:
    require_backend("cpp")
    from derivkit import _mc_cpp

    return _mc_cpp.normal_draws("fast", SEED, DRAWS)


def test_fast_draws_have_standard_normal_moments(fast_draws):
    """For n draws of N(0, 1) the sample means of z, z^2, z^3 and z^4 are approximately
    normal around 0, 1, 0 and 3 with variances 1/n, 2/n, 15/n and 96/n."""
    n = len(fast_draws)
    expected = {1: (0.0, 1.0), 2: (1.0, 2.0), 3: (0.0, 15.0), 4: (3.0, 96.0)}
    for power, (mean, variance) in expected.items():
        sample = statistics.fmean(z**power for z in fast_draws)
        assert abs(sample - mean) <= SIGMAS * math.sqrt(variance / n), power


def test_fast_draws_pass_a_chi_square_test_on_64_equal_bins(fast_draws):
    """Sort the draws into 64 bins that each hold 1/64 of a standard normal. A sampler with
    a wrong layer table would over-fill some bins and starve others."""
    bins = 64
    edges = [statistics.NormalDist().inv_cdf(k / bins) for k in range(1, bins)]
    ordered = sorted(fast_draws)
    cuts = [0, *(bisect.bisect_left(ordered, e) for e in edges), len(ordered)]
    expected = len(ordered) / bins
    chi2 = sum((b - a - expected) ** 2 / expected for a, b in zip(cuts, cuts[1:]))
    # Upper bound for chi-square with k = 63 degrees of freedom at SIGMAS standard
    # deviations, from the Wilson-Hilferty approximation: k (1 - 2/(9k) + z sqrt(2/(9k)))^3.
    k = bins - 1
    bound = k * (1.0 - 2.0 / (9.0 * k) + SIGMAS * math.sqrt(2.0 / (9.0 * k))) ** 3
    assert chi2 <= bound


def test_fast_draws_have_the_right_tail_and_are_symmetric(fast_draws):
    """Beyond R the draws come from a separate tail sampler, on either side."""
    n = len(fast_draws)
    p_tail = math.erfc(ZIGGURAT_R / math.sqrt(2.0))  # P(|Z| > R), about 2.6 x 10^-4
    right = sum(1 for z in fast_draws if z > ZIGGURAT_R)
    left = sum(1 for z in fast_draws if z < -ZIGGURAT_R)
    for count in (left, right):
        mean = n * p_tail / 2.0
        assert abs(count - mean) <= SIGMAS * math.sqrt(mean)
    negatives = sum(1 for z in fast_draws if z < 0.0)
    assert abs(negatives - n / 2.0) <= SIGMAS * math.sqrt(n / 4.0)
    assert all(math.isfinite(z) for z in fast_draws)
    assert max(abs(z) for z in fast_draws) < 8.0  # P(|Z| > 8) is 1.2 x 10^-15


# --------------------------------------------------------------------------------------
# The comparison harness
# --------------------------------------------------------------------------------------


def test_compare_measures_the_fast_generator_only_when_it_is_named(fast):
    cfg = McConfig(paths=3000, seed=4, vr=VarianceReduction.ANTITHETIC)
    assert FAST_CPP not in [r.backend for r in derivkit.compare(SPECS["call"], cfg, repeats=1).rows]

    report = derivkit.compare(SPECS["call"], cfg, backends=["cpp", FAST_CPP], repeats=1)
    assert [r.backend for r in report.rows] == ["cpp", FAST_CPP]
    row = report.rows[1]
    direct = european(SPECS["call"], cfg, **fast)
    assert (row.value, row.stderr) == (direct.value, direct.error_estimate)
    assert [(s.faster, s.baseline) for s in report.speed_ratios()] == [(FAST_CPP, "cpp")]
    assert "cpp/fast vs cpp" in report.table()

    budget = derivkit.accuracy_per_second(
        SPECS["call"], budgets=(0.005,), vr_methods=[VR["none"]], backends=[FAST_CPP],
        repeats=1, calibration_seconds=0.005,
    )  # fmt: skip
    assert [r.backend for r in budget.rows] == [FAST_CPP]


def test_compare_rejects_a_fast_generator_on_a_backend_that_has_none():
    with pytest.raises(ValueError, match="rng='fast' needs backend='cpp'"):
        derivkit.compare(SPECS["call"], backends=["python/fast"])


def test_command_line_takes_cpp_fast_and_the_report_says_what_it_is(fast, tmp_path, capsys):
    report = tmp_path / "RESULTS.md"
    argv = ["compare", "--paths", "2e3", "--repeats", "1", "--backends", "cpp", "cpp/fast"]
    assert main([*argv, "--report", str(report)]) == 0
    assert "| cpp/fast | 2,000 |" in capsys.readouterr().out
    text = report.read_text()
    assert "cpp/fast is the cpp back end with `rng=\"fast\"` (xoshiro256++" in text
