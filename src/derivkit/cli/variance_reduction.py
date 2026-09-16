from __future__ import annotations

from derivkit.black_scholes import geometric_asian, price
from derivkit.monte_carlo import AsianConfig, McConfig, arithmetic_asian, european
from derivkit.result import PricingResult
from derivkit.types import OptionType, VanillaSpec, VarianceReduction


def _row(name: str, r: PricingResult, ref_err: float) -> None:
    ratio = (ref_err * ref_err) / (r.error_estimate * r.error_estimate) if ref_err > 0.0 else 0.0
    print(f"{name:<28}{r.value:12.6f}{r.error_estimate:12.3e}{ratio:12.2f}")


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
    bs = price(spec)
    cfg = McConfig(paths=50000, seed=42)
    print(f"European call, 50,000 paths, seed=42.  Black-Scholes = {bs:.6f}")
    print("Variance ratio = Var(crude) / Var(method)  (higher is better).\n")
    print(f"{'method':<28}{'price':>12}{'stderr':>12}{'var ratio':>12}")

    cfg.vr = VarianceReduction.NONE
    crude = european(spec, cfg)
    _row("crude", crude, crude.error_estimate)
    cfg.vr = VarianceReduction.ANTITHETIC
    _row("antithetic", european(spec, cfg), crude.error_estimate)
    cfg.vr = VarianceReduction.CONTROL_VARIATE
    _row("control (S_T)", european(spec, cfg), crude.error_estimate)
    cfg.vr = VarianceReduction.ANTITHETIC | VarianceReduction.CONTROL_VARIATE
    _row("antithetic + control", european(spec, cfg), crude.error_estimate)

    print("\nArithmetic Asian call, 50 fixings, 20,000 paths.")
    print(f"Geometric Asian (Kemna-Vorst) = {geometric_asian(spec, 50):.6f}\n")

    asian = AsianConfig(mc=McConfig(paths=20000, seed=42), steps=50)
    asian.mc.vr = VarianceReduction.NONE
    a_crude = arithmetic_asian(spec, asian)
    _row("asian crude", a_crude, a_crude.error_estimate)
    asian.mc.vr = VarianceReduction.ANTITHETIC
    _row("asian antithetic", arithmetic_asian(spec, asian), a_crude.error_estimate)
    asian.mc.vr = VarianceReduction.CONTROL_VARIATE
    _row("asian geo-control", arithmetic_asian(spec, asian), a_crude.error_estimate)
    asian.mc.vr = VarianceReduction.ANTITHETIC | VarianceReduction.CONTROL_VARIATE
    _row("asian anti+geo-cv", arithmetic_asian(spec, asian), a_crude.error_estimate)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
