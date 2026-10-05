"""Pin the pure-Python Monte Carlo engine to the numbers it produced before back ends existed.

The values below were captured from the engine at commit bf2b639. Any refactor of the
pure-Python path must reproduce them. The tolerance is 1 x 10^-9 relative: on one machine
the match is exact, but exp/log/sin/cos may differ by an ulp between C libraries, and the
control-variate error estimate amplifies that by a few thousand through cancellation. A
real behaviour change (different stream, different formula) moves these numbers by
1 x 10^-4 or more, so 1 x 10^-9 cannot hide one.
"""

import pytest
from conftest import SAME_STREAM_RNGS

from derivkit.monte_carlo import (
    AdaptiveMcConfig,
    AsianConfig,
    McConfig,
    arithmetic_asian,
    european,
    european_adaptive,
)
from derivkit.types import OptionType, VanillaSpec, VarianceReduction

REL = 1e-9

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

# (engine, spec, vr): (value, error_estimate, work, method, converged, notes)
GOLDEN = {
    ("european", "call", "none"): (10.679391454680246, 0.23801005606742054, 4000, "mc-european", True, ""),
    ("european", "call", "antithetic"): (10.432573674733137, 0.11566856491454633, 4000, "mc-european-antithetic", True, ""),
    ("european", "call", "cv"): (10.409836581551936, 0.08812498910463422, 4000, "mc-european-cv", True, "beta=0.6875501372766103"),
    ("european", "call", "both"): (10.450538615010784, 0.02940300768327638, 4000, "mc-european-antithetic-cv", True, "beta=2.55070617174477"),
    ("european", "put", "none"): (10.135101415503538, 0.18230158608619682, 4000, "mc-european", True, ""),
    ("european", "put", "antithetic"): (10.288318165346423, 0.06843514267869741, 4000, "mc-european-antithetic", True, ""),
    ("european", "put", "cv"): (10.323038137489524, 0.0971552657658167, 4000, "mc-european-cv", True, "beta=-0.4776335658815932"),
    ("european", "put", "both"): (10.29865897875057, 0.024402482456566236, 4000, "mc-european-antithetic-cv", True, "beta=1.3711421313935201"),
    ("adaptive", "call", "none"): (10.360987369186025, 0.15324078867220933, 9000, "mc-european", False, "adaptive, hit max_paths"),
    ("adaptive", "call", "antithetic"): (10.404498776921978, 0.07725969154981621, 9000, "mc-european-antithetic", False, "adaptive, hit max_paths"),
    ("adaptive", "call", "cv"): (10.408697192496918, 0.05887326932048208, 9000, "mc-european-cv", False, "beta=0.6699324740690793, adaptive, hit max_paths"),
    ("adaptive", "call", "both"): (10.458490879775685, 0.04800565982975047, 1500, "mc-european-antithetic-cv", True, "beta=2.5592596466242212, adaptive"),
    ("asian", "call", "none"): (6.508151074816013, 0.4318591433407105, 400, "mc-asian", True, ""),
    ("asian", "call", "antithetic"): (6.319607991463855, 0.21233760571068971, 400, "mc-asian-antithetic", True, ""),
    ("asian", "call", "cv"): (6.17385142633389, 0.012200417780354167, 400, "mc-asian-cv", True, "beta=1.0321723328957144, geo-asian control"),
    ("asian", "call", "both"): (6.167107393181954, 0.009014191163053992, 400, "mc-asian-antithetic-cv", True, "beta=1.0277458031429256, geo-asian control"),
    ("asian", "put", "none"): (7.389955334602273, 0.4121495762719506, 400, "mc-asian", True, ""),
    ("asian", "put", "antithetic"): (7.621634680211252, 0.13623267044250995, 400, "mc-asian-antithetic", True, ""),
    ("asian", "put", "cv"): (7.524778919457291, 0.00985318415819402, 400, "mc-asian-cv", True, "beta=0.9810375532126936, geo-asian control"),
    ("asian", "put", "both"): (7.519359434969697, 0.008287410277839545, 400, "mc-asian-antithetic-cv", True, "beta=0.9901298856693516, geo-asian control"),
}


def run_case(engine: str, spec_name: str, vr_name: str, **kwargs):
    """Price one golden case; extra keyword arguments go to the engine (e.g. backend=...)."""
    spec = SPECS[spec_name]
    vr = VR[vr_name]
    if engine == "european":
        return european(spec, McConfig(paths=4000, seed=7, vr=vr), **kwargs)
    if engine == "adaptive":
        cfg = AdaptiveMcConfig(
            base=McConfig(paths=0, seed=11, vr=vr), stderr_tol=0.05, batch=1500, max_paths=9000
        )
        return european_adaptive(spec, cfg, **kwargs)
    return arithmetic_asian(spec, AsianConfig(mc=McConfig(paths=400, seed=3, vr=vr), steps=12), **kwargs)


def split_beta(notes: str) -> tuple[float | None, str]:
    """Separate the beta=<float> part of the notes from the rest of the text."""
    if not notes.startswith("beta="):
        return None, notes
    head, _, tail = notes.partition(", ")
    return float(head.removeprefix("beta=")), tail


def assert_matches(result, expected, rel: float) -> None:
    value, error, work, method, converged, notes = expected
    assert result.value == pytest.approx(value, rel=rel)
    assert result.error_estimate == pytest.approx(error, rel=rel)
    assert result.work == work
    assert result.method == method
    assert result.converged is converged
    beta, text = split_beta(result.notes)
    want_beta, want_text = split_beta(notes)
    assert text == want_text
    assert beta == pytest.approx(want_beta, rel=rel)


@pytest.mark.parametrize("case", list(GOLDEN), ids=lambda c: "-".join(c))
def test_pure_python_matches_golden(case):
    assert_matches(run_case(*case), GOLDEN[case], REL)


@pytest.mark.parametrize("rng", SAME_STREAM_RNGS)  # rng="fast" is exempt: see conftest.py
@pytest.mark.parametrize("case", list(GOLDEN), ids=lambda c: "-".join(c))
def test_cpp_reproduces_the_pure_python_numbers(case, rng, cpp_backend):
    """The C++ kernel uses the same generator and the same arithmetic in the same order,
    so it must land on the pure-Python numbers, not merely near them."""
    assert_matches(run_case(*case, backend=cpp_backend, rng=rng), GOLDEN[case], REL)
