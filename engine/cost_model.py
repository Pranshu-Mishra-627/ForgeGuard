"""Cost model for maintenance alert optimization.

Defines operational cost parameters, validation rules, and cost evaluation formulas.
Costs represent relative operational penalty units (e.g., relative severity between
missed failures and false alarm dispatches), not real currency or factory loss figures.

Default Illustrative Relative Costs:
- Missed failure cost (False Negative): 20.0
- False alarm cost (False Positive): 1.0
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Mapping

import numpy as np

DEFAULT_FALSE_NEGATIVE_COST: float = 20.0
DEFAULT_FALSE_POSITIVE_COST: float = 1.0


@dataclass(frozen=True)
class CostConfig:
    """Configuration for decision engine cost parameters.

    Attributes:
        false_negative_cost: Relative cost of a missed equipment failure (False Negative).
            Default is 20.0. Must be a finite, non-negative number.
        false_positive_cost: Relative cost of a false alarm dispatch (False Positive).
            Default is 1.0. Must be a finite, non-negative number.
    """

    false_negative_cost: float = DEFAULT_FALSE_NEGATIVE_COST
    false_positive_cost: float = DEFAULT_FALSE_POSITIVE_COST

    def __post_init__(self) -> None:
        """Validate cost parameters upon initialization."""
        self._validate_cost_param("false_negative_cost", self.false_negative_cost)
        self._validate_cost_param("false_positive_cost", self.false_positive_cost)

    @staticmethod
    def _validate_cost_param(name: str, value: Any) -> None:
        if isinstance(value, bool) or not isinstance(value, (int, float, np.number)):
            raise TypeError(f"'{name}' must be a numeric value, got {type(value).__name__}.")
        if not math.isfinite(value):
            raise ValueError(f"'{name}' must be finite, got {value}.")
        if value < 0:
            raise ValueError(f"'{name}' must be non-negative (>= 0), got {value}.")


@dataclass(frozen=True)
class CostBreakdown:
    """Structured breakdown of calculated operational costs.

    Attributes:
        total_cost: Total operational cost (FN cost + FP cost).
        fn_cost: Subtotal cost attributed to false negatives.
        fp_cost: Subtotal cost attributed to false positives.
        false_negatives: Count of false negatives evaluated.
        false_positives: Count of false positives evaluated.
        false_negative_cost: Unit cost applied for false negatives.
        false_positive_cost: Unit cost applied for false positives.
    """

    total_cost: float
    fn_cost: float
    fp_cost: float
    false_negatives: int
    false_positives: int
    false_negative_cost: float
    false_positive_cost: float

    def to_dict(self) -> dict[str, Any]:
        """Convert cost breakdown to dictionary format."""
        return {
            "total_cost": self.total_cost,
            "fn_cost": self.fn_cost,
            "fp_cost": self.fp_cost,
            "false_negatives": self.false_negatives,
            "false_positives": self.false_positives,
            "false_negative_cost": self.false_negative_cost,
            "false_positive_cost": self.false_positive_cost,
        }

    def __getitem__(self, key: str) -> Any:
        if hasattr(self, key):
            return getattr(self, key)
        raise KeyError(key)


def validate_cost_config(costs: CostConfig | Mapping[str, Any] | None = None) -> CostConfig:
    """Validates and normalizes cost configuration.

    Args:
        costs: A CostConfig instance, a dictionary mapping cost parameter names,
            or None to use the default cost configuration.

    Returns:
        A validated CostConfig instance.

    Raises:
        TypeError: If costs is not a CostConfig, Mapping, or None.
        ValueError: If cost parameters fail validation or unknown keys are passed.
    """
    if costs is None:
        return CostConfig()
    if isinstance(costs, CostConfig):
        return costs
    if isinstance(costs, Mapping):
        allowed_keys = {"false_negative_cost", "false_positive_cost"}
        unknown_keys = set(costs.keys()) - allowed_keys
        if unknown_keys:
            raise ValueError(f"Unknown cost configuration key(s): {sorted(unknown_keys)}.")
        fn_cost = costs.get("false_negative_cost", DEFAULT_FALSE_NEGATIVE_COST)
        fp_cost = costs.get("false_positive_cost", DEFAULT_FALSE_POSITIVE_COST)
        return CostConfig(false_negative_cost=fn_cost, false_positive_cost=fp_cost)
    raise TypeError(
        f"Invalid cost configuration type: {type(costs).__name__}. "
        "Expected CostConfig, dict/Mapping, or None."
    )


def calculate_cost(
    false_negatives: int,
    false_positives: int,
    costs: CostConfig | Mapping[str, Any] | None = None,
) -> CostBreakdown:
    """Calculates total relative cost for given false negative and false positive counts.

    Cost Formula:
        total_cost = false_negative_cost * FN + false_positive_cost * FP

    Args:
        false_negatives: Number of missed failure events (FN). Must be an integer >= 0.
        false_positives: Number of false alarm dispatches (FP). Must be an integer >= 0.
        costs: Cost configuration or mapping. Defaults to standard costs (FN=20, FP=1).

    Returns:
        A CostBreakdown detailing total cost, subtotal components, and unit costs.

    Raises:
        TypeError: If counts are not integers or costs is invalid.
        ValueError: If counts are negative.
    """
    if isinstance(false_negatives, bool) or not isinstance(false_negatives, (int, np.integer)):
        raise TypeError(f"'false_negatives' must be an integer, got {type(false_negatives).__name__}.")
    if isinstance(false_positives, bool) or not isinstance(false_positives, (int, np.integer)):
        raise TypeError(f"'false_positives' must be an integer, got {type(false_positives).__name__}.")

    if false_negatives < 0:
        raise ValueError(f"'false_negatives' cannot be negative, got {false_negatives}.")
    if false_positives < 0:
        raise ValueError(f"'false_positives' cannot be negative, got {false_positives}.")

    config = validate_cost_config(costs)

    fn = int(false_negatives)
    fp = int(false_positives)
    fn_cost = float(config.false_negative_cost * fn)
    fp_cost = float(config.false_positive_cost * fp)
    total_cost = fn_cost + fp_cost

    return CostBreakdown(
        total_cost=total_cost,
        fn_cost=fn_cost,
        fp_cost=fp_cost,
        false_negatives=fn,
        false_positives=fp,
        false_negative_cost=float(config.false_negative_cost),
        false_positive_cost=float(config.false_positive_cost),
    )
