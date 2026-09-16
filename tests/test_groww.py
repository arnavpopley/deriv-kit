from pathlib import Path

from derivkit.black_scholes import price
from derivkit.groww import load_fixture, nearest_expiry
from derivkit.implied_forward import CallPutQuote, imply_forward
from derivkit.implied_vol import implied_vol
from derivkit.types import OptionType, VanillaSpec, forward_price

_FIXTURE = Path(__file__).resolve().parents[1] / "examples" / "data" / "nifty_chain.json"


def test_groww_fixture():
    chain = load_fixture(_FIXTURE)
    assert chain.underlying == "NIFTY"
    assert chain.expiry_date == "2026-09-29"
    assert abs(chain.spot - 25012.4) <= 1e-9
    assert len(chain.contracts) >= 20
    assert chain.year_fraction > 0.0
    t = chain.year_fraction

    by_k: dict[float, dict[str, float]] = {}
    atm = None
    best = 1e300
    for c in chain.contracts:
        side = by_k.setdefault(c.strike, {"call": 0.0, "put": 0.0})
        if c.type is OptionType.CALL:
            side["call"] = c.ltp
            d = abs(c.strike - chain.spot)
            if d < best:
                best = d
                atm = c
        else:
            side["put"] = c.ltp
    assert atm is not None

    quotes = [
        CallPutQuote(k, side["call"], side["put"], 1.0)
        for k, side in by_k.items()
        if side["call"] > 0.0 and side["put"] > 0.0
    ]
    fit = imply_forward(chain.spot, t, quotes)
    assert fit.ok
    f = forward_price(chain.spot, chain.rate, chain.dividend, t)
    assert abs(fit.forward - f) <= 5.0

    spec = VanillaSpec(
        spot=chain.spot,
        strike=atm.strike,
        rate=chain.rate,
        dividend=chain.dividend,
        vol=atm.groww_iv,
        time=t,
        type=OptionType.CALL,
    )
    bs_px = price(spec)
    assert abs(bs_px - atm.ltp) / atm.ltp < 0.02
    spec.vol = 0.2
    iv = implied_vol(spec, atm.ltp)
    assert iv.converged
    assert abs(iv.vol - atm.groww_iv) < 0.015
    assert nearest_expiry(["2026-09-15", "2026-09-22", "2026-09-29"], "2026-09-12") == "2026-09-15"
