"""
Dynamic Computation Registry
Manages registration and discovery of computation capabilities
"""
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.utils.logging_utils import log_error, log_info


@dataclass
class ComputationMetadata:
    """Metadata for a registered computation"""
    name: str
    description: str
    asset_types: set[str]
    parameters: dict[str, Any]
    returns: dict[str, Any]
    examples: list[dict[str, Any]]
    tags: list[str]
    version: str
    created_at: datetime
    last_updated: datetime


class ComputationRegistry:
    """
    Central registry for all available computations
    Enables dynamic discovery and validation of computation capabilities
    """

    def __init__(self):
        self._computations: dict[str, ComputationMetadata] = {}
        self._handlers: dict[str, Callable] = {}
        self._asset_computations: dict[str, set[str]] = {}
        self._tag_index: dict[str, set[str]] = {}
        self._initialize_builtin_computations()

    def register(
        self,
        name: str,
        handler: Callable,
        description: str,
        asset_types: list[str],
        parameters: dict[str, Any],
        returns: dict[str, Any],
        examples: list[dict[str, Any]] | None = None,
        tags: list[str] | None = None,
        version: str = "1.0.0"
    ):
        """
        Register a new computation

        Args:
            name: Unique computation name
            handler: Function to handle the computation
            description: Human-readable description
            asset_types: list of supported asset types
            parameters: Parameter schema
            returns: Return value schema
            examples: Usage examples
            tags: Searchable tags
            version: Computation version
        """
        if name in self._computations:
            log_error(f"Computation '{name}' already registered")
            raise ValueError(f"Computation '{name}' already registered")

        # Create metadata
        metadata = ComputationMetadata(
            name=name,
            description=description,
            asset_types=set(asset_types),
            parameters=parameters,
            returns=returns,
            examples=examples or [],
            tags=tags or [],
            version=version,
            created_at=datetime.utcnow(),
            last_updated=datetime.utcnow()
        )

        # Store computation
        self._computations[name] = metadata
        self._handlers[name] = handler

        # Update indices
        for asset_type in asset_types:
            if asset_type not in self._asset_computations:
                self._asset_computations[asset_type] = set()
            self._asset_computations[asset_type].add(name)

        for tag in (tags or []):
            if tag not in self._tag_index:
                self._tag_index[tag] = set()
            self._tag_index[tag].add(name)

        log_info(f"Registered computation: {name} for assets: {asset_types}")

    def get_computation(self, name: str) -> ComputationMetadata | None:
        """Get computation metadata by name"""
        return self._computations.get(name)

    def get_handler(self, name: str) -> Callable | None:
        """Get computation handler by name"""
        return self._handlers.get(name)

    def list_computations(
        self,
        asset_type: str | None = None,
        tags: list[str] | None = None
    ) -> list[ComputationMetadata]:
        """
        list available computations with optional filtering

        Args:
            asset_type: Filter by asset type
            tags: Filter by tags

        Returns:
            list of computation metadata
        """
        computations = set(self._computations.keys())

        # Filter by asset type
        if asset_type:
            asset_computations = self._asset_computations.get(asset_type, set())
            computations &= asset_computations

        # Filter by tags
        if tags:
            tag_computations = set()
            for tag in tags:
                tag_computations |= self._tag_index.get(tag, set())
            computations &= tag_computations

        return [self._computations[name] for name in computations]

    def validate_parameters(
        self,
        computation_name: str,
        parameters: dict[str, Any]
    ) -> dict[str, Any]:
        """
        Validate parameters for a computation

        Args:
            computation_name: Name of computation
            parameters: Parameters to validate

        Returns:
            Validated parameters with defaults applied
        """
        metadata = self.get_computation(computation_name)
        if not metadata:
            raise ValueError(f"Unknown computation: {computation_name}")

        validated = {}
        param_schema = metadata.parameters

        for param_name, param_def in param_schema.items():
            if param_def.get("required", False) and param_name not in parameters:
                raise ValueError(f"Required parameter '{param_name}' missing for {computation_name}")

            if param_name in parameters:
                # Validate type
                expected_type = param_def.get("type")
                value = parameters[param_name]

                if expected_type and not self._check_type(value, expected_type):
                    raise TypeError(
                        f"Parameter '{param_name}' expected type {expected_type}, "
                        f"got {type(value).__name__}"
                    )

                # Validate constraints
                if "min" in param_def and value < param_def["min"]:
                    raise ValueError(
                        f"Parameter '{param_name}' value {value} below minimum {param_def['min']}"
                    )

                if "max" in param_def and value > param_def["max"]:
                    raise ValueError(
                        f"Parameter '{param_name}' value {value} above maximum {param_def['max']}"
                    )

                if "enum" in param_def and value not in param_def["enum"]:
                    raise ValueError(
                        f"Parameter '{param_name}' value {value} not in allowed values: {param_def['enum']}"
                    )

                validated[param_name] = value

            elif "default" in param_def:
                validated[param_name] = param_def["default"]

        return validated

    def _check_type(self, value: Any, expected_type: str) -> bool:
        """Check if value matches expected type"""
        type_map = {
            "int": int,
            "float": (int, float),
            "str": str,
            "bool": bool,
            "list": list,
            "dict": dict
        }

        expected = type_map.get(expected_type)
        if expected:
            return isinstance(value, expected)

        return True  # Unknown type, allow

    def _initialize_builtin_computations(self):
        """Initialize built-in computations"""
        # Technical Indicators
        self.register(
            name="sma",
            handler=None,  # Handler will be set by calculator
            description="Simple Moving Average",
            asset_types=["equity", "futures", "options", "index", "commodity", "currency", "crypto"],
            parameters={
                "period": {
                    "type": "int",
                    "required": False,
                    "default": 20,
                    "min": 1,
                    "max": 500,
                    "description": "Number of periods for moving average"
                }
            },
            returns={
                "value": {"type": "float", "description": "SMA value"},
                "timestamp": {"type": "datetime", "description": "Calculation timestamp"}
            },
            examples=[
                {
                    "params": {"period": 20},
                    "description": "20-period simple moving average"
                }
            ],
            tags=["indicator", "trend", "overlay"]
        )

        self.register(
            name="rsi",
            handler=None,
            description="Relative Strength Index",
            asset_types=["equity", "futures", "options", "index", "commodity", "currency", "crypto"],
            parameters={
                "period": {
                    "type": "int",
                    "required": False,
                    "default": 14,
                    "min": 2,
                    "max": 100,
                    "description": "RSI calculation period"
                }
            },
            returns={
                "value": {"type": "float", "description": "RSI value (0-100)"},
                "timestamp": {"type": "datetime", "description": "Calculation timestamp"}
            },
            tags=["indicator", "momentum", "oscillator"]
        )

        # Options Greeks
        self.register(
            name="greeks",
            handler=None,
            description="Option Greeks (Delta, Gamma, Theta, Vega, Rho)",
            asset_types=["options"],
            parameters={
                "model": {
                    "type": "str",
                    "required": False,
                    "default": "black-scholes",
                    "enum": ["black-scholes", "binomial", "monte-carlo"],
                    "description": "Pricing model to use"
                },
                "risk_free_rate": {
                    "type": "float",
                    "required": False,
                    "default": 0.05,
                    "min": 0,
                    "max": 1,
                    "description": "Risk-free interest rate"
                }
            },
            returns={
                "delta": {"type": "float", "description": "Rate of change of option price with underlying"},
                "gamma": {"type": "float", "description": "Rate of change of delta"},
                "theta": {"type": "float", "description": "Time decay"},
                "vega": {"type": "float", "description": "Volatility sensitivity"},
                "rho": {"type": "float", "description": "Interest rate sensitivity"}
            },
            tags=["greeks", "options", "risk"]
        )

        # Moneyness
        self.register(
            name="moneyness",
            handler=None,
            description="Asset moneyness calculation",
            asset_types=["options", "futures"],
            parameters={
                "reference": {
                    "type": "str",
                    "required": False,
                    "default": "spot",
                    "enum": ["spot", "forward", "strike"],
                    "description": "Reference price for moneyness"
                }
            },
            returns={
                "level": {"type": "str", "description": "Moneyness level (ITM, ATM, OTM, etc.)"},
                "ratio": {"type": "float", "description": "Moneyness ratio"},
                "metadata": {"type": "dict", "description": "Additional moneyness details"}
            },
            tags=["moneyness", "options", "futures"]
        )

        # Volatility
        self.register(
            name="volatility",
            handler=None,
            description="Volatility calculations",
            asset_types=["equity", "futures", "options", "index", "commodity", "currency", "crypto"],
            parameters={
                "type": {
                    "type": "str",
                    "required": False,
                    "default": "historical",
                    "enum": ["historical", "implied", "parkinson", "garman_klass", "yang_zhang"],
                    "description": "Type of volatility calculation"
                },
                "period": {
                    "type": "int",
                    "required": False,
                    "default": 20,
                    "min": 2,
                    "max": 252,
                    "description": "Calculation period"
                },
                "annualize": {
                    "type": "bool",
                    "required": False,
                    "default": True,
                    "description": "Whether to annualize the volatility"
                }
            },
            returns={
                "value": {"type": "float", "description": "Volatility value (as percentage)"},
                "type": {"type": "str", "description": "Type of volatility calculated"},
                "annualized": {"type": "bool", "description": "Whether value is annualized"}
            },
            tags=["volatility", "risk", "statistics"]
        )

        # Risk Metrics
        self.register(
            name="risk_metrics",
            handler=None,
            description="Comprehensive risk metrics",
            asset_types=["equity", "futures", "options", "commodity", "currency", "crypto"],
            parameters={
                "metrics": {
                    "type": "list",
                    "required": False,
                    "default": ["var", "sharpe", "max_drawdown"],
                    "description": "list of risk metrics to calculate"
                },
                "period": {
                    "type": "int",
                    "required": False,
                    "default": 252,
                    "description": "Lookback period for calculations"
                },
                "confidence_level": {
                    "type": "float",
                    "required": False,
                    "default": 0.95,
                    "min": 0.9,
                    "max": 0.99,
                    "description": "Confidence level for VaR/CVaR"
                }
            },
            returns={
                "metrics": {"type": "dict", "description": "Calculated risk metrics"},
                "period": {"type": "int", "description": "Period used"},
                "timestamp": {"type": "datetime", "description": "Calculation timestamp"}
            },
            tags=["risk", "portfolio", "statistics"]
        )

        # Custom Formula
        self.register(
            name="custom",
            handler=None,
            description="Custom formula computation",
            asset_types=["equity", "futures", "options", "index", "commodity", "currency", "crypto"],
            parameters={
                "formula": {
                    "type": "str",
                    "required": True,
                    "description": "Mathematical formula to evaluate"
                },
                "context": {
                    "type": "dict",
                    "required": False,
                    "default": {},
                    "description": "Additional context variables for formula"
                }
            },
            returns={
                "value": {"type": "any", "description": "Formula result"},
                "formula": {"type": "str", "description": "Evaluated formula"}
            },
            examples=[
                {
                    "params": {
                        "formula": "(close - sma20) / sma20 * 100",
                        "context": {"sma20": {"type": "sma", "period": 20}}
                    },
                    "description": "Percentage distance from 20-period SMA"
                }
            ],
            tags=["custom", "formula", "flexible"]
        )

        log_info(f"Initialized {len(self._computations)} built-in computations")

    def get_computation_info(self) -> dict[str, Any]:
        """Get comprehensive information about all registered computations"""
        return {
            "total_computations": len(self._computations),
            "asset_coverage": {
                asset: len(comps)
                for asset, comps in self._asset_computations.items()
            },
            "tags": list(self._tag_index.keys()),
            "computations": {
                name: {
                    "description": meta.description,
                    "asset_types": list(meta.asset_types),
                    "parameters": meta.parameters,
                    "tags": meta.tags,
                    "version": meta.version
                }
                for name, meta in self._computations.items()
            }
        }


# Global registry instance
computation_registry = ComputationRegistry()
