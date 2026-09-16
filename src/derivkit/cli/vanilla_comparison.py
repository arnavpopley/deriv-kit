from __future__ import annotations

from derivkit.black_scholes import greeks, price, price_result
from derivkit.monte_carlo import McConfig, european
from derivkit.trees import TreeConfig, price as tree_price
from derivkit.types import (
    OptionType,
    TreeModel,
    VanillaSpec,
    VarianceReduction,
    discount_factor,
)


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
    analytic = price_result(spec)
    g = greeks(spec)
    crr = TreeConfig(steps=401, model=TreeModel.COX_ROSS_RUBINSTEIN)
    lr = TreeConfig(steps=101, model=TreeModel.LEISEN_REIMER)
    tri = TreeConfig(steps=401, model=TreeModel.KAMRAD_RITCHKEN)
    crude = McConfig(paths=100000, seed=1, vr=VarianceReduction.NONE)
    vr = McConfig(
        paths=100000,
        seed=1,
        vr=VarianceReduction.ANTITHETIC | VarianceReduction.CONTROL_VARIATE,
    )
    print("European call  S=100 K=100 r=5% q=0 σ=20% T=1\n")
    print(analytic)
    print(tree_price(spec, crr))
    print(tree_price(spec, lr))
    print(tree_price(spec, tri))
    print(european(spec, crude))
    print(european(spec, vr))
    print("\nGreeks (per 1.0 of the bump, not 1% / 1bp):")
    print(f"  delta  {g.delta:.8f}")
    print(f"  gamma  {g.gamma:.8f}")
    print(f"  vega   {g.vega:.8f}")
    print(f"  theta  {g.theta:.8f}")
    print(f"  rho    {g.rho:.8f}")
    print(f"  vanna  {g.vanna:.8f}")
    print(f"  volga  {g.volga:.8f}")
    put = VanillaSpec(**{**spec.__dict__, "type": OptionType.PUT})
    parity = price(spec) - price(put) - (spec.spot - spec.strike * discount_factor(spec.rate, spec.time))
    print(f"\nPut-call parity residual: {parity:.6e}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
