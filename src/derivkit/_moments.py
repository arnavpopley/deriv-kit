"""Running moments of paired Monte Carlo samples (x = control, y = payoff)."""

from __future__ import annotations


class WelfordPair:
    """Welford's online update for the means, variances and covariance of (x, y).

    Every Monte Carlo back end reports its work as one of these, so the control-variate
    finish in `monte_carlo` is shared rather than reimplemented per back end.
    """

    def __init__(
        self,
        n: int = 0,
        mean_x: float = 0.0,
        mean_y: float = 0.0,
        m2_x: float = 0.0,
        m2_y: float = 0.0,
        c_xy: float = 0.0,
    ) -> None:
        self.n = n
        self.mean_x = mean_x
        self.mean_y = mean_y
        self.m2_x = m2_x
        self.m2_y = m2_y
        self.c_xy = c_xy

    def add(self, x: float, y: float) -> None:
        self.n += 1
        nn = float(self.n)
        dx = x - self.mean_x
        self.mean_x += dx / nn
        dy = y - self.mean_y
        self.mean_y += dy / nn
        self.m2_x += dx * (x - self.mean_x)
        self.m2_y += dy * (y - self.mean_y)
        self.c_xy += dx * (y - self.mean_y)

    def merge(
        self, n: int, mean_x: float, mean_y: float, m2_x: float, m2_y: float, c_xy: float
    ) -> None:
        """Fold in a batch summarised by its own count, means and centred sums.

        The pairwise form of Welford's update (Chan, Golub and LeVeque, 1979): exact in
        real arithmetic and free of the cancellation in sum(x^2) - n * mean^2.
        """
        if n == 0:
            return
        total = self.n + n
        dx = mean_x - self.mean_x
        dy = mean_y - self.mean_y
        weight = float(self.n) * float(n) / float(total)
        self.m2_x += m2_x + dx * dx * weight
        self.m2_y += m2_y + dy * dy * weight
        self.c_xy += c_xy + dx * dy * weight
        self.mean_x += dx * float(n) / float(total)
        self.mean_y += dy * float(n) / float(total)
        self.n = total

    def var_x(self) -> float:
        return self.m2_x / float(self.n - 1) if self.n > 1 else 0.0

    def var_y(self) -> float:
        return self.m2_y / float(self.n - 1) if self.n > 1 else 0.0

    def cov_xy(self) -> float:
        return self.c_xy / float(self.n - 1) if self.n > 1 else 0.0
