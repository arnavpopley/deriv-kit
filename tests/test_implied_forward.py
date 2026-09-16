import math

from derivkit.implied_forward import CallPutQuote, imply_forward
from derivkit.types import discount_factor, forward_price


def test_imply_forward_recovers_carry():
    spot = 25000.0
    time_rate = 17.0 / 365.0
    rate = 0.065
    dividend = 0.012
    df = discount_factor(rate, time_rate)
    fwd = forward_price(spot, rate, dividend, time_rate)
    quotes = []
    for k in (24400.0, 24700.0, 25000.0, 25300.0, 25600.0):
        parity = df * (fwd - k)
        quotes.append(
            CallPutQuote(
                strike=k,
                call=max(parity, 0.0) + 80.0,
                put=max(-parity, 0.0) + 80.0,
                weight=1.0,
            )
        )
    fit = imply_forward(spot, time_rate, quotes)
    assert fit.ok
    assert fit.pairs == 5
    assert abs(fit.forward - fwd) <= 1e-8
    assert abs(fit.discount - df) <= 1e-10
    assert abs(fit.rate - rate) <= 1e-10
    assert abs(fit.dividend - dividend) <= 1e-10

    empty = imply_forward(spot, time_rate, [])
    assert not empty.ok
