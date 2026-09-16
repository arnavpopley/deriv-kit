from __future__ import annotations

from dataclasses import dataclass


@dataclass
class PricingResult:
    """Uniform report from every numerical engine.

    `error_estimate` is a computable bound or statistical error:
      - Black-Scholes: a few units in the last place (analytic)
      - Trees: |P(N) - P(floor(N/2))|
      - Monte Carlo: sample standard error of the discounted payoff
    """

    value: float = 0.0
    error_estimate: float = 0.0
    work: int = 0
    method: str = ""
    converged: bool = True
    notes: str = ""

    def __str__(self) -> str:
        s = f"{self.method}  value={self.value}  err={self.error_estimate}  work={self.work}"
        if not self.converged:
            s += "  NOT_CONVERGED"
        if self.notes:
            s += f"  ({self.notes})"
        return s
