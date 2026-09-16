from derivkit.black_scholes import price, to_black
from derivkit.implied_vol import implied_vol
from derivkit.types import OptionType, VanillaSpec


def test_implied_vol_roundtrip():
    spec = VanillaSpec(
        spot=100.0, strike=100.0, rate=0.05, dividend=0.0, vol=0.2, time=1.0, type=OptionType.CALL
    )
    px = price(spec)
    probe = VanillaSpec(**{**spec.__dict__, "vol": 0.0})
    iv = implied_vol(probe, px)
    assert iv.converged
    assert abs(iv.vol - 0.2) <= 1e-10
    assert abs(iv.residual) <= 1e-12

    otm = VanillaSpec(
        spot=100.0, strike=70.0, rate=0.01, dividend=0.0, vol=0.35, time=0.25, type=OptionType.PUT
    )
    otm_px = price(otm)
    otm.vol = 1.5
    iv = implied_vol(otm, otm_px)
    assert iv.converged
    assert abs(iv.vol - 0.35) <= 1e-8

    for k in (80.0, 90.0, 100.0, 110.0, 120.0):
        for sig in (0.1, 0.2, 0.5):
            s = VanillaSpec(**{**spec.__dict__, "strike": k, "vol": sig, "type": OptionType.PUT})
            market = price(s)
            s.vol = 0.25
            iv = implied_vol(s, market)
            assert iv.converged
            assert abs(iv.vol - sig) <= 1e-8

    bad = implied_vol(spec, -1.0)
    assert not bad.converged

    blk_round = VanillaSpec(**{**otm.__dict__, "vol": 0.35})
    iv_blk = implied_vol(to_black(blk_round), otm_px)
    assert iv_blk.converged
    assert abs(iv_blk.vol - 0.35) <= 1e-8
