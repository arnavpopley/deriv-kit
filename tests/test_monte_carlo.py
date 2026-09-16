from derivkit.black_scholes import geometric_asian, price
from derivkit.monte_carlo import (
    AdaptiveMcConfig,
    AsianConfig,
    McConfig,
    arithmetic_asian,
    european,
    european_adaptive,
)
from derivkit.types import OptionType, VanillaSpec, VarianceReduction


def test_monte_carlo():
    eu = VanillaSpec(
        spot=100.0, strike=100.0, rate=0.05, dividend=0.0, vol=0.2, time=1.0, type=OptionType.CALL
    )
    bs = price(eu)
    cfg = McConfig(paths=20000, seed=7)

    crude = european(eu, cfg)
    assert abs(crude.value - bs) < 6.0 * crude.error_estimate

    cfg.vr = VarianceReduction.ANTITHETIC
    anti = european(eu, cfg)
    assert abs(anti.value - bs) < 6.0 * anti.error_estimate
    assert anti.error_estimate < crude.error_estimate

    cfg.vr = VarianceReduction.CONTROL_VARIATE
    cv = european(eu, cfg)
    assert abs(cv.value - bs) < 6.0 * cv.error_estimate
    assert cv.error_estimate < crude.error_estimate

    cfg.vr = VarianceReduction.ANTITHETIC | VarianceReduction.CONTROL_VARIATE
    both = european(eu, cfg)
    assert abs(both.value - bs) < 6.0 * both.error_estimate
    assert both.error_estimate < anti.error_estimate

    acfg = AdaptiveMcConfig(
        base=McConfig(
            paths=0,
            seed=11,
            vr=VarianceReduction.ANTITHETIC | VarianceReduction.CONTROL_VARIATE,
        ),
        stderr_tol=5e-3,
        batch=5000,
        max_paths=200000,
    )
    ad = european_adaptive(eu, acfg)
    assert ad.converged
    assert ad.error_estimate <= 5e-3 * 1.01
    assert abs(ad.value - bs) < 6.0 * max(ad.error_estimate, 1e-8)

    asian = AsianConfig(mc=McConfig(paths=8000, seed=3), steps=50)
    asian_crude = arithmetic_asian(eu, asian)
    asian.mc.vr = VarianceReduction.CONTROL_VARIATE
    asian_cv = arithmetic_asian(eu, asian)
    assert asian_cv.error_estimate < asian_crude.error_estimate
    assert asian_cv.value > geometric_asian(eu, 50)
    assert asian_cv.value > 0.0
