from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum, IntFlag, auto


class OptionType(Enum):
    CALL = auto()
    PUT = auto()


class ExerciseStyle(Enum):
    EUROPEAN = auto()
    AMERICAN = auto()


class TreeModel(Enum):
    COX_ROSS_RUBINSTEIN = auto()
    JARROW_RUDD = auto()
    LEISEN_REIMER = auto()
    KAMRAD_RITCHKEN = auto()


class VarianceReduction(IntFlag):
    NONE = 0
    ANTITHETIC = 1 << 0
    CONTROL_VARIATE = 1 << 1


def has_flag(flags: VarianceReduction, bit: VarianceReduction) -> bool:
    return bool(flags & bit)


@dataclass
class VanillaSpec:
    spot: float = 0.0
    strike: float = 0.0
    rate: float = 0.0
    dividend: float = 0.0
    vol: float = 0.0
    time: float = 0.0
    type: OptionType = OptionType.CALL


def validate(spec: VanillaSpec) -> None:
    for name, x in (
        ("spot", spec.spot),
        ("strike", spec.strike),
        ("rate", spec.rate),
        ("dividend", spec.dividend),
        ("vol", spec.vol),
        ("time", spec.time),
    ):
        if not math.isfinite(x):
            raise ValueError(f"{name} must be finite")
    if spec.spot <= 0.0:
        raise ValueError("spot must be positive")
    if spec.strike < 0.0:
        raise ValueError("strike must be non-negative")
    if spec.vol < 0.0:
        raise ValueError("vol must be non-negative")
    if spec.time < 0.0:
        raise ValueError("time must be non-negative")


def payoff(spot: float, strike: float, option_type: OptionType) -> float:
    if option_type is OptionType.CALL:
        return max(spot - strike, 0.0)
    return max(strike - spot, 0.0)


def discount_factor(rate: float, time: float) -> float:
    return math.exp(-rate * time)


def forward_price(spot: float, rate: float, dividend: float, time: float) -> float:
    return spot * math.exp((rate - dividend) * time)


def option_type_str(option_type: OptionType) -> str:
    return "call" if option_type is OptionType.CALL else "put"


def exercise_style_str(style: ExerciseStyle) -> str:
    return "european" if style is ExerciseStyle.EUROPEAN else "american"


def tree_model_str(model: TreeModel) -> str:
    return {
        TreeModel.COX_ROSS_RUBINSTEIN: "crr",
        TreeModel.JARROW_RUDD: "jarrow-rudd",
        TreeModel.LEISEN_REIMER: "leisen-reimer",
        TreeModel.KAMRAD_RITCHKEN: "kamrad-ritchken",
    }.get(model, "unknown")
