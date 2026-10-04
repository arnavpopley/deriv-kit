"""derivkit: European and American pricing with explicit numerical error control."""

from derivkit.backends import BACKENDS, BackendUnavailableError, available_backends
from derivkit.black_scholes import (
    BlackSpec,
    Greeks,
    d1_d2,
    geometric_asian,
    greeks,
    intrinsic_discounted,
    price,
    price_result,
    to_black,
    upper_bound,
    validate_black,
)
from derivkit.implied_forward import CallPutQuote, ForwardFit, imply_forward
from derivkit.implied_vol import ImpliedVolConfig, ImpliedVolResult, implied_vol
from derivkit.monte_carlo import AdaptiveMcConfig, AsianConfig, McConfig
from derivkit.monte_carlo import arithmetic_asian, european, european_adaptive
from derivkit.result import PricingResult
from derivkit.rng import NormalRng
from derivkit.trees import AdaptiveTreeConfig, TreeConfig
from derivkit.trees import (
    adaptive,
    cox_ross_rubinstein,
    jarrow_rudd,
    kamrad_ritchken,
    leisen_reimer,
)
from derivkit.trees import price as tree_price
from derivkit.types import (
    ExerciseStyle,
    OptionType,
    TreeModel,
    VanillaSpec,
    VarianceReduction,
    discount_factor,
    forward_price,
    has_flag,
    payoff,
    validate,
)

__version__ = "2.0.0"


def __getattr__(name: str):
    # compare and accuracy_per_second live in derivkit.comparison, which pulls in
    # subprocess, statistics and platform. Loading it on first use keeps `import derivkit`
    # as light as it was before the benchmarking harness existed.
    if name in ("compare", "accuracy_per_second"):
        from derivkit import comparison

        return getattr(comparison, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "AdaptiveMcConfig",
    "AdaptiveTreeConfig",
    "AsianConfig",
    "BACKENDS",
    "BackendUnavailableError",
    "BlackSpec",
    "CallPutQuote",
    "ExerciseStyle",
    "ForwardFit",
    "Greeks",
    "ImpliedVolConfig",
    "ImpliedVolResult",
    "McConfig",
    "NormalRng",
    "OptionType",
    "PricingResult",
    "TreeConfig",
    "TreeModel",
    "VanillaSpec",
    "VarianceReduction",
    "adaptive",
    "arithmetic_asian",
    "available_backends",
    "cox_ross_rubinstein",
    "d1_d2",
    "discount_factor",
    "european",
    "european_adaptive",
    "forward_price",
    "geometric_asian",
    "greeks",
    "has_flag",
    "imply_forward",
    "implied_vol",
    "intrinsic_discounted",
    "jarrow_rudd",
    "kamrad_ritchken",
    "leisen_reimer",
    "payoff",
    "price",
    "price_result",
    "to_black",
    "tree_price",
    "upper_bound",
    "validate",
    "validate_black",
    "accuracy_per_second",
    "compare",
    "__version__",
]
