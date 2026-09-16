from __future__ import annotations

from derivkit.black_scholes import price
from derivkit.trees import TreeConfig, cox_ross_rubinstein, jarrow_rudd, kamrad_ritchken, leisen_reimer
from derivkit.trees import price as tree_price
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
    bs = price(spec)
    print(f"European call vs Black-Scholes = {bs:.10f}\n")
    print(f"{'N':>6}{'CRR err':>16}{'JR err':>16}{'LR err':>16}{'TRIN err':>16}")
    for n in (25, 51, 101, 201, 401, 801):
        e_crr = abs(cox_ross_rubinstein(spec, n).value - bs)
        e_jr = abs(jarrow_rudd(spec, n).value - bs)
        e_lr = abs(leisen_reimer(spec, n).value - bs)
        e_tr = abs(kamrad_ritchken(spec, n).value - bs)
        print(f"{n:6d}{e_crr:16.4e}{e_jr:16.4e}{e_lr:16.4e}{e_tr:16.4e}")

    print("\nCRR with Richardson 2P(2N)-P(N) (even N; CRR oscillates on odd N):")
    print(f"{'N':>6}{'plain err':>16}{'rich err':>16}")
    for n in (50, 100, 200, 400):
        e0 = abs(tree_price(spec, TreeConfig(steps=n, richardson=False)).value - bs)
        e1 = abs(tree_price(spec, TreeConfig(steps=n, richardson=True)).value - bs)
        print(f"{n:6d}{e0:16.4e}{e1:16.4e}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
