import math

from derivkit.black_scholes import geometric_asian, greeks, price, to_black
from derivkit.types import OptionType, VanillaSpec


def test_black_scholes_references():
    atm = VanillaSpec(
        spot=100.0, strike=100.0, rate=0.05, dividend=0.0, vol=0.2, time=1.0, type=OptionType.CALL
    )
    assert abs(price(atm) - 10.450583572185565) <= 1e-12
    atm_put = VanillaSpec(**{**atm.__dict__, "type": OptionType.PUT})
    assert abs(price(atm_put) - 5.573526022256971) <= 1e-12

    parity = price(atm) - price(atm_put)
    fwd_gap = atm.spot - atm.strike * math.exp(-atm.rate * atm.time)
    assert abs(parity - fwd_gap) <= 1e-12

    g = greeks(atm)
    assert abs(g.d1 - 0.35) <= 1e-12
    assert abs(g.d2 - 0.15) <= 1e-12
    assert abs(g.delta - 0.6368306511756191) <= 1e-12
    assert abs(g.gamma - 0.018762017345846895) <= 1e-12
    assert abs(g.vega - 37.52403469169379) <= 1e-10
    assert abs(g.theta - (-6.414027546438197)) <= 1e-12
    assert abs(g.rho - 53.232481545376345) <= 1e-10
    assert abs(g.vanna - (-0.28143026018770345)) <= 1e-12
    assert abs(g.volga - 9.850059106569622) <= 1e-10

    gp = greeks(atm_put)
    assert abs(gp.delta - (-0.3631693488243809)) <= 1e-12
    assert abs(gp.gamma - g.gamma) <= 1e-15
    assert abs(gp.vega - g.vega) <= 1e-15

    otm = VanillaSpec(
        spot=100.0, strike=110.0, rate=0.05, dividend=0.02, vol=0.25, time=0.75, type=OptionType.CALL
    )
    assert abs(price(otm) - 5.584270225140479) <= 1e-12
    otm_put = VanillaSpec(**{**otm.__dict__, "type": OptionType.PUT})
    assert abs(price(otm_put) - 13.024462214124618) <= 1e-12

    short_dated = VanillaSpec(
        spot=50.0, strike=50.0, rate=0.10, dividend=0.0, vol=0.40, time=0.25, type=OptionType.CALL
    )
    assert abs(price(short_dated) - 4.5814555505432395) <= 1e-12

    hull = VanillaSpec(
        spot=36.0, strike=40.0, rate=0.06, dividend=0.0, vol=0.20, time=1.0, type=OptionType.PUT
    )
    assert abs(price(hull) - 3.84430779159684) <= 1e-12
    assert abs(geometric_asian(atm, 50) - 5.641058127824213) <= 1e-12

    assert abs(price(to_black(atm)) - price(atm)) <= 1e-12
    assert abs(price(to_black(atm_put)) - price(atm_put)) <= 1e-12
    assert abs(price(to_black(otm)) - price(otm)) <= 1e-12
    assert abs(price(to_black(otm_put)) - price(otm_put)) <= 1e-12
    assert abs(greeks(to_black(atm)).vega - greeks(atm).vega) <= 1e-10

    expired = VanillaSpec(**{**atm.__dict__, "time": 0.0})
    assert abs(price(expired) - 0.0) <= 1e-15
    expired.spot = 120.0
    assert abs(price(expired) - 20.0) <= 1e-15

    det = VanillaSpec(**{**atm.__dict__, "vol": 0.0})
    det_call = math.exp(-0.05) * (100.0 * math.exp(0.05) - 100.0)
    assert abs(price(det) - det_call) <= 1e-12

    threw = False
    try:
        price(VanillaSpec(**{**atm.__dict__, "spot": -1.0}))
    except ValueError:
        threw = True
    assert threw
