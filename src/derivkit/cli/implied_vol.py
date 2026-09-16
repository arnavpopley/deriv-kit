from __future__ import annotations

from derivkit.black_scholes import price
from derivkit.implied_vol import implied_vol
from derivkit.trees import cox_ross_rubinstein
from derivkit.types import OptionType, VanillaSpec


def main() -> int:
    spec = VanillaSpec(
        spot=100.0,
        strike=100.0,
        rate=0.05,
        dividend=0.0,
        vol=0.20,
        time=1.0,
        type=OptionType.CALL,
    )
    true_vol = spec.vol
    px = price(spec)
    probe = VanillaSpec(**{**spec.__dict__, "vol": 0.50})
    iv = implied_vol(probe, px)
    print(f"Market price (true σ = {true_vol}): {px}")
    status = "converged" if iv.converged else "FAILED"
    print(
        f"Implied vol:  {iv.vol}   residual={iv.residual}   "
        f"iters={iv.iterations}   via {iv.method}  {status}"
    )
    print("\nSmile reconstruction from CRR prices (N=401):")
    print(f"{'K':>8}{'tree px':>14}{'iv':>14}{'|iv-σ|':>14}")
    for k in (80.0, 90.0, 100.0, 110.0, 120.0):
        s = VanillaSpec(**{**spec.__dict__, "strike": k})
        tree_px = cox_ross_rubinstein(s, 401).value
        s.vol = 0.3
        recovered = implied_vol(s, tree_px)
        print(f"{k:8.2f}{tree_px:14.8f}{recovered.vol:14.8f}{abs(recovered.vol - true_vol):14.3e}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
