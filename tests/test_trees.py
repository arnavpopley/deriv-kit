from derivkit.black_scholes import price
from derivkit.trees import (
    AdaptiveTreeConfig,
    TreeConfig,
    adaptive,
    cox_ross_rubinstein,
    jarrow_rudd,
    kamrad_ritchken,
    leisen_reimer,
    price as tree_price,
)
from derivkit.types import ExerciseStyle, OptionType, TreeModel, VanillaSpec


def test_trees():
    eu = VanillaSpec(
        spot=100.0, strike=100.0, rate=0.05, dividend=0.0, vol=0.2, time=1.0, type=OptionType.CALL
    )
    bs = price(eu)
    crr_n = cox_ross_rubinstein(eu, 1000)
    assert abs(crr_n.value - bs) <= 5e-3
    assert abs(kamrad_ritchken(eu, 1000).value - bs) <= 5e-3
    assert abs(jarrow_rudd(eu, 1000).value - bs) <= 5e-3
    assert abs(leisen_reimer(eu, 101).value - bs) <= 5e-4

    crr_coarse = cox_ross_rubinstein(eu, 50)
    assert abs(crr_n.value - bs) < abs(crr_coarse.value - bs)

    rich = tree_price(
        eu, TreeConfig(steps=200, model=TreeModel.COX_ROSS_RUBINSTEIN, richardson=True)
    )
    assert abs(rich.value - bs) < abs(crr_coarse.value - bs)

    am = VanillaSpec(
        spot=36.0, strike=40.0, rate=0.06, dividend=0.0, vol=0.20, time=1.0, type=OptionType.PUT
    )
    eu_put = price(am)
    am_crr = cox_ross_rubinstein(am, 401, ExerciseStyle.AMERICAN)
    eu_crr = cox_ross_rubinstein(am, 401, ExerciseStyle.EUROPEAN)
    assert am_crr.value > eu_put
    assert am_crr.value > eu_crr.value
    assert abs(eu_crr.value - eu_put) <= 5e-3
    assert abs(am_crr.value - 4.4866573200158) <= 5e-3
    assert abs(kamrad_ritchken(am, 401, ExerciseStyle.AMERICAN).value - 4.4852773512221455) <= 5e-3

    ad = adaptive(
        eu,
        AdaptiveTreeConfig(
            model=TreeModel.LEISEN_REIMER, abs_tol=1e-5, min_steps=51, max_steps=2001
        ),
    )
    assert ad.converged
    assert abs(ad.value - bs) <= 1e-4
