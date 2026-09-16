from __future__ import annotations

from derivkit.black_scholes import price
from derivkit.trees import AdaptiveTreeConfig, cox_ross_rubinstein, kamrad_ritchken, leisen_reimer, adaptive
from derivkit.types import ExerciseStyle, OptionType, TreeModel, VanillaSpec


def main() -> int:
    spec = VanillaSpec(
        spot=36.0,
        strike=40.0,
        rate=0.06,
        dividend=0.0,
        vol=0.20,
        time=1.0,
        type=OptionType.PUT,
    )
    european = price(spec)
    crr_e = cox_ross_rubinstein(spec, 801, ExerciseStyle.EUROPEAN)
    crr_a = cox_ross_rubinstein(spec, 801, ExerciseStyle.AMERICAN)
    tri_a = kamrad_ritchken(spec, 801, ExerciseStyle.AMERICAN)
    lr_a = leisen_reimer(spec, 801, ExerciseStyle.AMERICAN)
    acfg = AdaptiveTreeConfig(
        model=TreeModel.KAMRAD_RITCHKEN,
        style=ExerciseStyle.AMERICAN,
        abs_tol=5e-4,
        min_steps=101,
        max_steps=3201,
    )
    adapt = adaptive(spec, acfg)
    print("American put  S=36 K=40 r=6% σ=20% T=1\n")
    print(f"European BS (no early exercise)     {european:.6f}")
    print(f"CRR European  N=801                 {crr_e.value:.6f}")
    print(f"CRR American  N=801                 {crr_a.value:.6f}   premium={crr_a.value - european:.6f}")
    print(f"Trinomial American N=801            {tri_a.value:.6f}")
    print(f"Leisen-Reimer American N=801        {lr_a.value:.6f}")
    flag = "converged" if adapt.converged else "NOT CONVERGED"
    print(
        f"Adaptive trinomial                  {adapt.value:.6f}   "
        f"err={adapt.error_estimate:.6f}  N={adapt.work}  {flag}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
