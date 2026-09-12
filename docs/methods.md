# Numerical methods

This note records the formulas implemented in `derivkit` and the error
diagnostics each engine reports. The design is deliberately close to an
adaptive ODE toolkit: a method is not finished until it can tell you how
wrong it might be.

## Black–Scholes–Merton

Under geometric Brownian motion

\[
dS_t = (r-q)\,S_t\,dt + \sigma S_t\,dW_t
\]

the European vanilla values are

\[
\begin{aligned}
C &= S_0 e^{-qT}\Phi(d_1) - K e^{-rT}\Phi(d_2),\\
P &= K e^{-rT}\Phi(-d_2) - S_0 e^{-qT}\Phi(-d_1),
\end{aligned}
\]

with

\[
d_{1,2} = \frac{\ln(S_0/K) + (r-q\pm\tfrac12\sigma^2)T}{\sigma\sqrt{T}}.
\]

\(\Phi\) is evaluated with `erfc`. Degenerate limits \(T=0\) and \(\sigma=0\)
are handled as discounted forwards, not as `0/0` in \(d_1\).

Reported error: a few units in the last place of the computed price.

## Implied volatility

Newton’s method on \(\sigma \mapsto V_{\mathrm{BS}}(\sigma) - V_{\mathrm{mkt}}\)
uses analytic vega. The iteration stops on an *absolute residual*

\[
|V_{\mathrm{BS}}(\sigma)-V_{\mathrm{mkt}}| \le \max(\varepsilon_{\mathrm{abs}},
\varepsilon_{\mathrm{rel}} \max(1, |V_{\mathrm{mkt}}|)).
\]

If vega collapses or a step leaves the bracket, a bisection fallback runs
on \([\sigma_{\min},\sigma_{\max}]\), expanded until the residual changes
sign. Prices below discounted intrinsic or above the model-free upper bound
are rejected rather than inverted.

## Binomial trees

**Cox–Ross–Rubinstein.** \(u = e^{\sigma\sqrt{\Delta t}}\), \(d = 1/u\),
risk-neutral \(p = (e^{(r-q)\Delta t}-d)/(u-d)\). Truncation is \(O(N^{-1})\)
and oscillatory in \(N\).

**Jarrow–Rudd.** Equal probability \(p = 1/2\), drift absorbed into \(u,d\).

**Leisen–Reimer.** Odd \(N\), Peizer–Pratt inversion of \(d_1,d_2\) so the
tree matches the Black–Scholes probabilities. Smooth \(O(N^{-2})\)
convergence for Europeans.

American exercise replaces continuation with \(\max(\text{exercise},
\text{continuation})\) at every node.

Error diagnostic: \(|P(N)-P(\lfloor N/2\rfloor)|\). Adaptive pricing doubles
\(N\) until that gap is below a user tolerance (the analogue of an RK
step-size controller). Richardson \(2P(2N)-P(N)\) is optional for CRR.

## Trinomial tree (Kamrad–Ritchken)

Stretch \(\lambda = \sqrt{3}\),

\[
\begin{aligned}
p_u &= \tfrac{1}{2\lambda^2} + \tfrac12 \frac{\nu\sqrt{\Delta t}}{\lambda\sigma},\\
p_d &= \tfrac{1}{2\lambda^2} - \tfrac12 \frac{\nu\sqrt{\Delta t}}{\lambda\sigma},\\
p_m &= 1 - \tfrac{1}{\lambda^2},
\end{aligned}
\]

with \(\nu = r-q-\sigma^2/2\). Negative probabilities are rejected; increase
\(N\).

## Monte Carlo

The terminal spot of GBM is sampled *exactly*:

\[
S_T = S_0 \exp\bigl((r-q-\tfrac12\sigma^2)T + \sigma\sqrt{T}\,Z\bigr),\quad Z\sim N(0,1).
\]

There is no Euler discretisation bias for European payoffs. The reported
error is the sample standard error of the discounted payoff, using Welford’s
numerically stable one-pass moments.

### Antithetic variates

Each \(Z\) is paired with \(-Z\). The averaged pair is one independent
observation, which typically cuts variance on monotone European payoffs.

### Control variates

For Europeans the control is the discounted terminal spot, whose mean
\(S_0 e^{-qT}\) is known. The optimal coefficient
\(\beta = \mathrm{Cov}(Y,X)/\mathrm{Var}(X)\) is estimated from the same
sample.

For arithmetic Asians the control is the geometric-average Asian, which is
lognormal. The Kemna–Vorst formula implemented here uses \(n\) fixings at
\(\Delta t, 2\Delta t, \ldots, T\):

\[
\begin{aligned}
\mu_G &= \ln S_0 + (r-q-\tfrac12\sigma^2)\frac{(n+1)\Delta t}{2},\\
\sigma_G^2 &= \sigma^2\Delta t\frac{(n+1)(2n+1)}{6n}.
\end{aligned}
\]

The geometric option is then Black–Scholes on a lognormal with that mean and
variance, discounted at \(r\).

### Adaptive paths

`european_adaptive` accumulates independent batches until the standard error
falls below a tolerance or a path cap is hit — the Monte Carlo counterpart
of adapting an integrator’s step size to a local error estimate.

## References

- F. Black, M. Scholes, *The pricing of options and corporate liabilities*, JPE 1973.
- J. C. Cox, S. A. Ross, M. Rubinstein, *Option pricing: a simplified approach*, JFE 1979.
- D. Leisen, M. Reimer, *Binomial models for option valuation*, OR Spektrum 1996.
- B. Kamrad, P. Ritchken, *Multinomial approximating models*, Management Science 1991.
- P. Glasserman, *Monte Carlo Methods in Financial Engineering*, Springer 2003.
- A. G. Z. Kemna, A. C. F. Vorst, *A pricing method for options based on average asset values*, JBF 1990.
- E. G. Haug, *The Complete Guide to Option Pricing Formulas*, McGraw-Hill.
