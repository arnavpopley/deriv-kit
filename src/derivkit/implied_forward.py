from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass
class CallPutQuote:
    strike: float = 0.0
    call: float = 0.0
    put: float = 0.0
    weight: float = 1.0


@dataclass
class ForwardFit:
    forward: float = 0.0
    discount: float = 1.0
    rate: float = 0.0
    dividend: float = 0.0
    pairs: int = 0
    ok: bool = False
    method: str = ""


def imply_forward(spot: float, time_rate: float, quotes: list[CallPutQuote]) -> ForwardFit:
    out = ForwardFit()
    if not (spot > 0.0) or not (time_rate > 0.0):
        raise ValueError("imply_forward needs positive spot and time_rate")

    sw = swk = swk2 = swy = swky = 0.0
    n = 0
    for q in quotes:
        if not (q.call > 0.0 and q.put > 0.0 and q.strike > 0.0 and q.weight > 0.0):
            continue
        y = q.call - q.put
        w = q.weight
        k = q.strike
        sw += w
        swk += w * k
        swk2 += w * k * k
        swy += w * y
        swky += w * k * y
        n += 1
    out.pairs = n
    if n < 2 or sw <= 0.0:
        out.method = "too-few-pairs"
        return out

    det = sw * swk2 - swk * swk
    if not (abs(det) > 1e-12 * sw * swk2):
        out.method = "degenerate"
        return out
    a = (swy * swk2 - swk * swky) / det
    b = (sw * swky - swk * swy) / det
    if not (b < 0.0) or not (a > 0.0):
        out.method = "non-physical"
        return out
    out.discount = -b
    out.forward = a / out.discount
    if not (out.forward > 0.0) or not (out.discount > 0.0 and out.discount < 2.0):
        out.method = "non-physical"
        out.ok = False
        return out
    out.rate = -math.log(out.discount) / time_rate
    out.dividend = out.rate - math.log(out.forward / spot) / time_rate
    out.ok = True
    out.method = "pcp-ols"
    return out
