from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone

from derivkit.black_scholes import BlackSpec, price
from derivkit.groww import ClientConfig, bundled_fixture, from_env, load_chain
from derivkit.implied_forward import CallPutQuote, imply_forward
from derivkit.implied_vol import implied_vol
from derivkit.monte_carlo import McConfig, european
from derivkit.nse_calendar import clock_to_expiry, expiry_close
from derivkit.types import (
    OptionType,
    VanillaSpec,
    VarianceReduction,
    discount_factor,
    forward_price,
)


def _parse(argv: list[str] | None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="groww_chain",
        description=(
            "Price a Groww option chain with derivkit. Default pricing is Black-76 "
            "with an implied forward from put-call parity, NSE business-day vol time "
            "(trading days / 252), and ACT/365.25 discounting."
        ),
    )
    p.add_argument("underlying", nargs="?", default=None)
    p.add_argument("--expiry", metavar="YYYY-MM-DD")
    p.add_argument("--as-of", dest="as_of", metavar="YYYY-MM-DD")
    p.add_argument("--strikes", type=int, default=5)
    p.add_argument("--rate", type=float)
    p.add_argument("--div", type=float)
    p.add_argument("--fixture", metavar="PATH")
    p.add_argument("--mc", action="store_true")
    p.add_argument("--json", dest="json_out", action="store_true")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse(argv)
    try:
        client: ClientConfig = from_env()
        client.fixture_path = str(bundled_fixture())
        if args.underlying:
            client.underlying = args.underlying
        if args.expiry:
            client.expiry_date = args.expiry
        if args.fixture:
            client.fixture_path = args.fixture
            client.force_fixture = True

        chain = load_chain(client)
        if chain.spot <= 0.0:
            raise RuntimeError("option chain did not include underlying_ltp")
        if not chain.expiry_date:
            raise RuntimeError("missing expiry_date")

        as_of = datetime.now(timezone.utc)
        if args.as_of:
            as_of = expiry_close(args.as_of)
        clk = clock_to_expiry(chain.expiry_date, as_of)

        by_strike: dict[float, dict[str, object]] = {}
        for c in chain.contracts:
            side = by_strike.setdefault(c.strike, {"call": None, "put": None})
            if c.type is OptionType.CALL:
                side["call"] = c
            else:
                side["put"] = c

        override_carry = args.rate is not None or args.div is not None
        fit = None
        if not override_carry:
            quotes: list[CallPutQuote] = []
            for k, side in by_strike.items():
                call = side["call"]
                put = side["put"]
                if call is None or put is None:
                    continue
                if not (call.ltp > 0.0 and put.ltp > 0.0):
                    continue
                w = min(call.volume, put.volume) + min(call.open_interest, put.open_interest)
                quotes.append(
                    CallPutQuote(
                        strike=k,
                        call=call.ltp,
                        put=put.ltp,
                        weight=w if w > 0.0 else 1.0,
                    )
                )
            fit = imply_forward(chain.spot, clk.time_rate, quotes)

        rate = args.rate if args.rate is not None else chain.rate
        dividend = args.div if args.div is not None else chain.dividend
        forward = forward_price(chain.spot, rate, dividend, clk.time_rate)
        df = discount_factor(rate, clk.time_rate)
        carry_src = "overrides"
        if not override_carry and fit is not None and fit.ok:
            forward = fit.forward
            df = fit.discount
            rate = fit.rate
            dividend = fit.dividend
            carry_src = fit.method
        elif not override_carry:
            carry_src = "defaults (pcp failed)"

        strikes = sorted({c.strike for c in chain.contracts}, key=lambda k: abs(k - chain.spot))
        keep = min(len(strikes), 2 * args.strikes + 1)
        strikes = sorted(strikes[:keep])

        snap = " (snapped to last close)" if clk.snapped_to_close else ""
        print(
            f"{chain.underlying}  {chain.exchange}  expiry {clk.expiry_ist}  "
            f"as-of {clk.as_of_ist}{snap}  [{chain.source}]"
        )
        print(
            f"T_rate={clk.time_rate:.4f}  T_vol={clk.time_vol:.4f} "
            f"({clk.trading_days:.2f} trading days)  spot={chain.spot:.2f}  "
            f"F={forward:.2f}  DF={df:.6f}  r={rate:.4f}  q={dividend:.4f}  [{carry_src}]"
        )
        print()
        print(
            f"{'symbol':<22}{'cp':>4}{'K':>8}{'LTP':>10}{'BS':>10}{'Rs':>10}"
            f"{'iv%':>8}{'ivG%':>8}{'volpts':>8}"
        )

        rows = []
        atm = None
        atm_diff = 1e300
        for c in chain.contracts:
            if c.strike not in strikes or c.ltp <= 0.0:
                continue
            spec = BlackSpec(
                forward=forward,
                strike=c.strike,
                discount=df,
                vol=c.groww_iv if c.groww_iv > 0.0 else 0.15,
                time_vol=clk.time_vol,
                type=c.type,
            )
            bs_px = price(spec)
            rupees = bs_px - c.ltp
            iv = implied_vol(BlackSpec(**{**spec.__dict__, "vol": 0.2}), c.ltp)
            iv_pct = iv.vol * 100.0 if iv.converged else 0.0
            groww_iv_pct = c.groww_iv * 100.0
            volpts = 100.0 * (iv.vol - c.groww_iv) if iv.converged else 0.0
            cp = "CE" if c.type is OptionType.CALL else "PE"
            iv_s = f"{iv_pct:8.2f}" if iv.converged else f"{'n/a':>8}"
            vp_s = f"{volpts:8.2f}" if iv.converged else f"{'n/a':>8}"
            print(
                f"{c.trading_symbol:<22}{cp:>4}{int(c.strike):8d}{c.ltp:10.2f}"
                f"{bs_px:10.2f}{rupees:10.2f}{iv_s}{groww_iv_pct:8.2f}{vp_s}"
            )
            row = {
                "symbol": c.trading_symbol,
                "type": cp,
                "strike": c.strike,
                "ltp": c.ltp,
                "bs": bs_px,
                "residual_rs": rupees,
                "iv_groww": c.groww_iv,
                "oi": c.open_interest,
                "volume": c.volume,
            }
            if iv.converged:
                row["iv_from_ltp"] = iv.vol
                row["vol_points"] = volpts
            rows.append(row)
            dist = abs(c.strike - chain.spot)
            if c.type is OptionType.CALL and dist < atm_diff:
                atm_diff = dist
                atm = c

        print()
        print(
            "LTP = Groww last traded price.  BS is Black-76 using Groww IV, the "
            "implied (or override) forward, and T_vol."
        )
        print(
            "Rs = BS - LTP (rupees).  iv% is derivkit implied vol from LTP; ivG% is "
            "Groww's published IV."
        )
        print(
            "volpts = 100 * (iv_from_LTP - Groww_IV).  T_rate is ACT/365.25; T_vol is "
            "NSE trading days / 252."
        )

        if args.mc and atm is not None:
            spec = VanillaSpec(
                spot=forward,
                strike=atm.strike,
                rate=0.0,
                dividend=0.0,
                vol=atm.groww_iv if atm.groww_iv > 0.0 else 0.15,
                time=clk.time_vol,
                type=atm.type,
            )
            cfg = McConfig(
                paths=40000,
                seed=7,
                vr=VarianceReduction.ANTITHETIC | VarianceReduction.CONTROL_VARIATE,
            )
            mc_px = european(spec, cfg)
            blk = BlackSpec(
                forward=forward,
                strike=atm.strike,
                discount=df,
                vol=spec.vol,
                time_vol=clk.time_vol,
                type=atm.type,
            )
            print()
            print(
                f"ATM Monte Carlo ({atm.trading_symbol}): {df * mc_px.value:.4f}  "
                f"stderr={df * mc_px.error_estimate:.4e}  vs Black-76 {price(blk):.4f}"
            )

        if args.json_out:
            out = {
                "underlying": chain.underlying,
                "expiry": chain.expiry_date,
                "spot": chain.spot,
                "forward": forward,
                "discount": df,
                "rate": rate,
                "dividend": dividend,
                "carry_source": carry_src,
                "as_of_ist": clk.as_of_ist,
                "expiry_ist": clk.expiry_ist,
                "time_rate": clk.time_rate,
                "time_vol": clk.time_vol,
                "trading_days": clk.trading_days,
                "source": chain.source,
                "rows": rows,
            }
            print()
            print(json.dumps(out, indent=2))
        return 0
    except Exception as ex:
        print(f"groww_chain: {ex}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
