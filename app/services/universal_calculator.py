"""
Universal Calculator for all asset types
A stateless computation engine that handles calculations for any financial instrument
"""
from datetime import datetime
from enum import Enum
from typing import Any

import numpy as np
import pandas as pd

from app.errors import CalculationError
from app.services.custom_indicators import CustomIndicators
from app.services.moneyness_calculator_local import LocalMoneynessCalculator
from app.utils.logging_utils import log_error, log_exception


class AssetType(Enum):
    """Supported asset types"""
    EQUITY = "equity"
    FUTURES = "futures"
    OPTIONS = "options"
    INDEX = "index"
    COMMODITY = "commodity"
    CURRENCY = "currency"
    CRYPTO = "crypto"


class ComputationType(Enum):
    """Types of computations available"""
    INDICATOR = "indicator"
    GREEKS = "greeks"
    MONEYNESS = "moneyness"
    VOLATILITY = "volatility"
    CORRELATION = "correlation"
    CUSTOM = "custom"
    RISK_METRICS = "risk_metrics"
    PRICE_ANALYTICS = "price_analytics"


class UniversalCalculator:
    """
    Universal computation engine for all asset types
    Provides a unified interface for calculating any metric on any asset
    """

    def __init__(self):
        self._calculators = {}
        self._computation_registry = {}
        self._initialize_calculators()
        self._register_computations()

    def _initialize_calculators(self):
        """Initialize asset-specific calculators"""
        # These will be initialized as needed
        self._pandas_ta_executor = None
        self._greeks_calculator = None
        self._moneyness_calculator = LocalMoneynessCalculator()
        self._custom_indicators = CustomIndicators()

    def _register_computations(self):
        """Register available computations for each asset type"""
        # Universal computations (available for all assets)
        universal_computations = {
            ComputationType.INDICATOR: self._compute_indicator,
            ComputationType.VOLATILITY: self._compute_volatility,
            ComputationType.CUSTOM: self._compute_custom,
            ComputationType.PRICE_ANALYTICS: self._compute_price_analytics,
        }

        # Asset-specific computations
        self._computation_registry = {
            AssetType.EQUITY: {
                **universal_computations,
                ComputationType.CORRELATION: self._compute_correlation,
                ComputationType.RISK_METRICS: self._compute_equity_risk_metrics,
            },
            AssetType.FUTURES: {
                **universal_computations,
                ComputationType.MONEYNESS: self._compute_futures_moneyness,
                ComputationType.RISK_METRICS: self._compute_futures_risk_metrics,
            },
            AssetType.OPTIONS: {
                **universal_computations,
                ComputationType.GREEKS: self._compute_greeks,
                ComputationType.MONEYNESS: self._compute_options_moneyness,
                ComputationType.RISK_METRICS: self._compute_options_risk_metrics,
            },
            AssetType.INDEX: {
                **universal_computations,
                ComputationType.CORRELATION: self._compute_correlation,
            },
            AssetType.COMMODITY: {
                **universal_computations,
                ComputationType.RISK_METRICS: self._compute_commodity_risk_metrics,
            },
            AssetType.CURRENCY: {
                **universal_computations,
                ComputationType.CORRELATION: self._compute_correlation,
            },
            AssetType.CRYPTO: {
                **universal_computations,
                ComputationType.RISK_METRICS: self._compute_crypto_risk_metrics,
            }
        }

    async def compute(
        self,
        asset_type: str | AssetType,
        instrument_key: str,
        computations: list[dict[str, Any]],
        data: pd.DataFrame | None = None,
        context: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """
        Main computation method - processes all requested computations

        Args:
            asset_type: Type of asset
            instrument_key: Unique instrument identifier
            computations: list of computation requests
            data: Optional pre-fetched data
            context: Additional context (spot price, risk-free rate, etc.)

        Returns:
            Dictionary with computation results
        """
        try:
            # Convert string to enum if needed
            if isinstance(asset_type, str):
                asset_type = AssetType(asset_type.lower())

            # Initialize context
            if context is None:
                context = {}

            # Get available computations for asset type
            available_computations = self._computation_registry.get(asset_type, {})

            results = {
                "instrument_key": instrument_key,
                "asset_type": asset_type.value,
                "timestamp": datetime.utcnow(),
                "computations": {},
                "metadata": {
                    "requested_computations": len(computations),
                    "successful_computations": 0,
                    "failed_computations": 0
                }
            }

            # Process each computation request
            for computation in computations:
                comp_type = computation.get("type")
                comp_name = computation.get("name", comp_type)
                comp_params = computation.get("params", {})

                try:
                    # Convert string to enum
                    comp_type_enum = ComputationType(comp_type)

                    # Check if computation is available for asset type
                    if comp_type_enum not in available_computations:
                        results["computations"][comp_name] = {
                            "error": f"Computation type '{comp_type}' not available for asset type '{asset_type.value}'"
                        }
                        results["metadata"]["failed_computations"] += 1
                        continue

                    # Get computation function
                    compute_func = available_computations[comp_type_enum]

                    # Execute computation
                    result = await compute_func(
                        instrument_key=instrument_key,
                        asset_type=asset_type,
                        params=comp_params,
                        data=data,
                        context=context
                    )

                    results["computations"][comp_name] = result
                    results["metadata"]["successful_computations"] += 1

                except Exception as e:
                    log_error(f"Error computing {comp_name}: {str(e)}")
                    results["computations"][comp_name] = {
                        "error": str(e)
                    }
                    results["metadata"]["failed_computations"] += 1

            # Add execution time
            results["metadata"]["execution_time_ms"] = (
                datetime.utcnow() - results["timestamp"]
            ).total_seconds() * 1000

            return results

        except Exception as e:
            log_exception(f"Error in universal computation: {str(e)}")
            raise CalculationError(f"Universal computation failed: {str(e)}") from e

    async def _compute_indicator(
        self,
        instrument_key: str,
        asset_type: AssetType,
        params: dict[str, Any],
        data: pd.DataFrame | None,
        context: dict[str, Any]
    ) -> dict[str, Any]:
        """Compute technical indicators"""
        indicator_name = params.get("indicator", params.get("name", "sma"))
        indicator_params = params.get("params", {})

        # Use pandas_ta for standard indicators
        if hasattr(pd.DataFrame.ta, indicator_name):
            if data is None:
                # Fetch data if not provided
                data = await self._fetch_data(instrument_key, context)

            # Calculate indicator
            result = getattr(data.ta, indicator_name)(**indicator_params)

            # Get latest value
            if isinstance(result, pd.Series):
                value = result.iloc[-1] if not result.empty else None
            elif isinstance(result, pd.DataFrame):
                value = {col: result[col].iloc[-1] for col in result.columns}
            else:
                value = result

            return {
                "value": value,
                "indicator": indicator_name,
                "params": indicator_params,
                "timestamp": data.index[-1] if not data.empty else datetime.utcnow()
            }

        # Custom indicators
        if hasattr(self._custom_indicators, indicator_name):
            indicator_func = getattr(self._custom_indicators, indicator_name)
            result = indicator_func(data, **indicator_params)

            return {
                "value": result.iloc[-1] if isinstance(result, pd.Series) else result,
                "indicator": indicator_name,
                "params": indicator_params,
                "custom": True
            }

        raise ValueError(f"Unknown indicator: {indicator_name}")

    async def _compute_greeks(
        self,
        instrument_key: str,
        asset_type: AssetType,
        params: dict[str, Any],
        data: pd.DataFrame | None,
        context: dict[str, Any]
    ) -> dict[str, Any]:
        """Compute option Greeks"""
        if asset_type != AssetType.OPTIONS:
            raise ValueError("Greeks calculation only available for options")

        # Extract option parameters from instrument key or context
        option_params = self._extract_option_params(instrument_key, context)

        # Calculate Greeks
        from app.services.greeks_calculation_engine import GreeksCalculationEngine
        engine = GreeksCalculationEngine()

        greeks = engine.calculate_greeks(
            spot_price=option_params["spot_price"],
            strike_price=option_params["strike_price"],
            time_to_expiry=option_params["time_to_expiry"],
            volatility=option_params.get("volatility", 0.2),
            risk_free_rate=params.get("risk_free_rate", 0.05),
            option_type=option_params["option_type"],
            option_price=option_params.get("option_price")
        )

        return {
            "delta": greeks.delta,
            "gamma": greeks.gamma,
            "theta": greeks.theta,
            "vega": greeks.vega,
            "rho": greeks.rho,
            "implied_volatility": greeks.implied_volatility,
            "model": params.get("model", "black-scholes")
        }

    async def _compute_options_moneyness(
        self,
        instrument_key: str,
        asset_type: AssetType,
        params: dict[str, Any],
        data: pd.DataFrame | None,
        context: dict[str, Any]
    ) -> dict[str, Any]:
        """Compute options moneyness"""
        option_params = self._extract_option_params(instrument_key, context)

        moneyness_level = self._moneyness_calculator.classify_moneyness(
            strike=option_params["strike_price"],
            spot_price=option_params["spot_price"],
            option_type=option_params["option_type"]
        )

        moneyness_ratio = self._moneyness_calculator.calculate_moneyness_ratio(
            strike=option_params["strike_price"],
            spot_price=option_params["spot_price"],
            option_type=option_params["option_type"]
        )

        return {
            "level": moneyness_level.value,
            "ratio": round(moneyness_ratio, 4),
            "strike": option_params["strike_price"],
            "spot": option_params["spot_price"],
            "type": option_params["option_type"]
        }

    async def _compute_futures_moneyness(
        self,
        instrument_key: str,
        asset_type: AssetType,
        params: dict[str, Any],
        data: pd.DataFrame | None,
        context: dict[str, Any]
    ) -> dict[str, Any]:
        """Compute futures moneyness based on time to expiry and basis"""
        futures_params = self._extract_futures_params(instrument_key, context)

        # Calculate basis
        basis = futures_params["futures_price"] - futures_params["spot_price"]
        basis_percentage = (basis / futures_params["spot_price"]) * 100

        # Calculate annualized basis
        days_to_expiry = futures_params["days_to_expiry"]
        annualized_basis = (basis_percentage / days_to_expiry) * 365

        # Classify moneyness
        if days_to_expiry <= 7:
            moneyness = "near_expiry"
        elif days_to_expiry <= 30:
            moneyness = "current_month"
        elif days_to_expiry <= 60:
            moneyness = "next_month"
        else:
            moneyness = "far_month"

        return {
            "level": moneyness,
            "basis": round(basis, 2),
            "basis_percentage": round(basis_percentage, 4),
            "annualized_basis": round(annualized_basis, 4),
            "days_to_expiry": days_to_expiry,
            "futures_price": futures_params["futures_price"],
            "spot_price": futures_params["spot_price"]
        }

    async def _compute_volatility(
        self,
        instrument_key: str,
        asset_type: AssetType,
        params: dict[str, Any],
        data: pd.DataFrame | None,
        context: dict[str, Any]
    ) -> dict[str, Any]:
        """Compute various volatility measures"""
        if data is None:
            data = await self._fetch_data(instrument_key, context)

        period = params.get("period", 20)
        vol_type = params.get("type", "historical")

        returns = data["close"].pct_change().dropna()

        if vol_type == "historical":
            # Historical volatility
            volatility = returns.rolling(window=period).std() * np.sqrt(252)
            current_vol = volatility.iloc[-1]

        elif vol_type == "parkinson":
            # Parkinson volatility (using high-low)
            hl_ratio = np.log(data["high"] / data["low"])
            volatility = np.sqrt(1 / (4 * np.log(2)) * (hl_ratio ** 2).rolling(window=period).mean()) * np.sqrt(252)
            current_vol = volatility.iloc[-1]

        elif vol_type == "garman_klass":
            # Garman-Klass volatility
            hl_ratio = np.log(data["high"] / data["low"])
            co_ratio = np.log(data["close"] / data["open"])
            gk_vol = np.sqrt(
                0.5 * (hl_ratio ** 2).rolling(window=period).mean() -
                (2 * np.log(2) - 1) * (co_ratio ** 2).rolling(window=period).mean()
            ) * np.sqrt(252)
            current_vol = gk_vol.iloc[-1]

        else:
            raise ValueError(f"Unknown volatility type: {vol_type}")

        return {
            "value": round(current_vol * 100, 2),  # As percentage
            "type": vol_type,
            "period": period,
            "annualized": True
        }

    async def _compute_correlation(
        self,
        instrument_key: str,
        asset_type: AssetType,
        params: dict[str, Any],
        data: pd.DataFrame | None,
        context: dict[str, Any]
    ) -> dict[str, Any]:
        """Compute correlation with other instruments"""
        other_instrument = params.get("other_instrument")
        period = params.get("period", 20)

        if not other_instrument:
            raise ValueError("other_instrument parameter required for correlation")

        # Fetch data for both instruments
        if data is None:
            data = await self._fetch_data(instrument_key, context)

        other_data = await self._fetch_data(other_instrument, context)

        # Calculate returns
        returns1 = data["close"].pct_change().dropna()
        returns2 = other_data["close"].pct_change().dropna()

        # Align data
        aligned_returns1 = returns1.reindex(returns2.index)
        aligned_returns2 = returns2.reindex(returns1.index)

        # Calculate rolling correlation
        correlation = aligned_returns1.rolling(window=period).corr(aligned_returns2)
        current_corr = correlation.iloc[-1]

        return {
            "value": round(current_corr, 4),
            "instrument1": instrument_key,
            "instrument2": other_instrument,
            "period": period
        }

    async def _compute_custom(
        self,
        instrument_key: str,
        asset_type: AssetType,
        params: dict[str, Any],
        data: pd.DataFrame | None,
        context: dict[str, Any]
    ) -> dict[str, Any]:
        """Compute custom formula"""
        formula = params.get("formula")
        if not formula:
            raise ValueError("formula parameter required for custom computation")

        if data is None:
            data = await self._fetch_data(instrument_key, context)

        # Create evaluation context
        eval_context = {
            "open": data["open"],
            "high": data["high"],
            "low": data["low"],
            "close": data["close"],
            "volume": data["volume"],
            "returns": data["close"].pct_change(),
            "log_returns": np.log(data["close"] / data["close"].shift(1)),
            "np": np,
            "pd": pd,
            "ta": pd.DataFrame.ta
        }

        # Add any pre-computed indicators to context
        for key, value in params.get("context", {}).items():
            if isinstance(value, dict) and "type" in value:
                # Compute dependent indicator
                dep_result = await self._compute_indicator(
                    instrument_key, asset_type, value, data, context
                )
                eval_context[key] = dep_result["value"]
            else:
                eval_context[key] = value

        # Evaluate formula
        try:
            result = eval(formula, {"__builtins__": {}}, eval_context)

            # Get latest value if series
            value = result.iloc[-1] if isinstance(result, pd.Series) else result

            return {
                "value": value,
                "formula": formula,
                "timestamp": data.index[-1] if not data.empty else datetime.utcnow()
            }

        except Exception as e:
            raise ValueError(f"Error evaluating formula: {str(e)}") from e

    async def _compute_price_analytics(
        self,
        instrument_key: str,
        asset_type: AssetType,
        params: dict[str, Any],
        data: pd.DataFrame | None,
        context: dict[str, Any]
    ) -> dict[str, Any]:
        """Compute price analytics (support/resistance, patterns, etc.)"""
        if data is None:
            data = await self._fetch_data(instrument_key, context)

        analytics_type = params.get("type", "pivot_points")

        if analytics_type == "pivot_points":
            # Calculate pivot points
            high = data["high"].iloc[-1]
            low = data["low"].iloc[-1]
            close = data["close"].iloc[-1]

            pivot = (high + low + close) / 3
            r1 = 2 * pivot - low
            r2 = pivot + (high - low)
            r3 = high + 2 * (pivot - low)
            s1 = 2 * pivot - high
            s2 = pivot - (high - low)
            s3 = low - 2 * (high - pivot)

            return {
                "pivot": round(pivot, 2),
                "resistance": {
                    "r1": round(r1, 2),
                    "r2": round(r2, 2),
                    "r3": round(r3, 2)
                },
                "support": {
                    "s1": round(s1, 2),
                    "s2": round(s2, 2),
                    "s3": round(s3, 2)
                }
            }

        if analytics_type == "price_levels":
            # Key price levels
            period = params.get("period", 20)

            return {
                "current": round(data["close"].iloc[-1], 2),
                "day_high": round(data["high"].iloc[-1], 2),
                "day_low": round(data["low"].iloc[-1], 2),
                "period_high": round(data["high"].rolling(period).max().iloc[-1], 2),
                "period_low": round(data["low"].rolling(period).min().iloc[-1], 2),
                "vwap": round((data["close"] * data["volume"]).sum() / data["volume"].sum(), 2)
            }

        raise ValueError(f"Unknown analytics type: {analytics_type}")

    async def _compute_equity_risk_metrics(
        self,
        instrument_key: str,
        asset_type: AssetType,
        params: dict[str, Any],
        data: pd.DataFrame | None,
        context: dict[str, Any]
    ) -> dict[str, Any]:
        """Compute equity-specific risk metrics"""
        if data is None:
            data = await self._fetch_data(instrument_key, context)

        returns = data["close"].pct_change().dropna()

        # Calculate various risk metrics
        period = params.get("period", 252)
        confidence_level = params.get("confidence_level", 0.95)

        # Value at Risk (VaR)
        var = np.percentile(returns.tail(period), (1 - confidence_level) * 100)

        # Conditional Value at Risk (CVaR)
        cvar = returns[returns <= var].mean()

        # Maximum Drawdown
        cumulative = (1 + returns).cumprod()
        running_max = cumulative.expanding().max()
        drawdown = (cumulative - running_max) / running_max
        max_drawdown = drawdown.min()

        # Sharpe Ratio (assuming risk-free rate from context)
        risk_free_rate = context.get("risk_free_rate", 0.02) / 252
        excess_returns = returns - risk_free_rate
        sharpe_ratio = np.sqrt(252) * excess_returns.mean() / returns.std()

        return {
            "var": round(var * 100, 2),
            "cvar": round(cvar * 100, 2),
            "max_drawdown": round(max_drawdown * 100, 2),
            "sharpe_ratio": round(sharpe_ratio, 2),
            "volatility": round(returns.std() * np.sqrt(252) * 100, 2),
            "period": period,
            "confidence_level": confidence_level
        }

    async def _compute_futures_risk_metrics(
        self,
        instrument_key: str,
        asset_type: AssetType,
        params: dict[str, Any],
        data: pd.DataFrame | None,
        context: dict[str, Any]
    ) -> dict[str, Any]:
        """Compute futures-specific risk metrics"""
        futures_params = self._extract_futures_params(instrument_key, context)

        # DV01 (Dollar Value of 01)
        notional = params.get("notional", 1000000)
        dv01 = notional * 0.0001  # 1 basis point move

        # Roll risk
        days_to_expiry = futures_params["days_to_expiry"]
        if days_to_expiry <= 5:
            roll_risk = "high"
        elif days_to_expiry <= 15:
            roll_risk = "medium"
        else:
            roll_risk = "low"

        # Basis risk
        basis = futures_params["futures_price"] - futures_params["spot_price"]
        basis_volatility = params.get("basis_volatility", 0.02)  # 2% default
        basis_var = basis * basis_volatility * 1.96  # 95% confidence

        return {
            "dv01": round(dv01, 2),
            "roll_risk": roll_risk,
            "days_to_expiry": days_to_expiry,
            "basis": round(basis, 2),
            "basis_var": round(basis_var, 2),
            "notional": notional
        }

    async def _compute_options_risk_metrics(
        self,
        instrument_key: str,
        asset_type: AssetType,
        params: dict[str, Any],
        data: pd.DataFrame | None,
        context: dict[str, Any]
    ) -> dict[str, Any]:
        """Compute options-specific risk metrics"""
        # Get Greeks first
        greeks = await self._compute_greeks(instrument_key, asset_type, params, data, context)

        # Additional risk metrics
        option_params = self._extract_option_params(instrument_key, context)

        # Pin risk (gamma risk near expiry)
        days_to_expiry = option_params["days_to_expiry"]
        if days_to_expiry <= 1:
            pin_risk = "extreme"
        elif days_to_expiry <= 3:
            pin_risk = "high"
        elif days_to_expiry <= 7:
            pin_risk = "medium"
        else:
            pin_risk = "low"

        # Speed (rate of change of gamma)
        # Approximation: speed = -gamma * (2 * moneyness - 1) / (spot * time_to_expiry)
        moneyness = option_params["strike_price"] / option_params["spot_price"]
        time_to_expiry_years = days_to_expiry / 365
        speed = -greeks["gamma"] * (2 * moneyness - 1) / (
            option_params["spot_price"] * max(time_to_expiry_years, 0.01)
        )

        return {
            **greeks,
            "pin_risk": pin_risk,
            "speed": round(speed, 6),
            "days_to_expiry": days_to_expiry,
            "moneyness": round(moneyness, 4)
        }

    async def _compute_commodity_risk_metrics(
        self,
        instrument_key: str,
        asset_type: AssetType,
        params: dict[str, Any],
        data: pd.DataFrame | None,
        context: dict[str, Any]
    ) -> dict[str, Any]:
        """Compute commodity-specific risk metrics"""
        if data is None:
            data = await self._fetch_data(instrument_key, context)

        # Seasonality analysis
        data["month"] = pd.to_datetime(data.index).month
        monthly_returns = data.groupby("month")["close"].pct_change().mean()

        # Storage cost considerations
        storage_cost = params.get("storage_cost_pct", 0.02)  # 2% annual default

        # Convenience yield approximation
        # Using futures-spot relationship if available
        if "futures_price" in context and "spot_price" in context:
            time_to_maturity = params.get("time_to_maturity", 0.25)  # 3 months default
            risk_free_rate = context.get("risk_free_rate", 0.02)

            futures_price = context["futures_price"]
            spot_price = context["spot_price"]

            convenience_yield = (
                (1 / time_to_maturity) *
                np.log(spot_price / futures_price) +
                risk_free_rate +
                storage_cost
            )
        else:
            convenience_yield = None

        return {
            "seasonality": {
                str(month): round(ret * 100, 2)
                for month, ret in monthly_returns.items()
            },
            "storage_cost_annual": round(storage_cost * 100, 2),
            "convenience_yield": round(convenience_yield * 100, 2) if convenience_yield else None,
            "volatility": round(data["close"].pct_change().std() * np.sqrt(252) * 100, 2)
        }

    async def _compute_crypto_risk_metrics(
        self,
        instrument_key: str,
        asset_type: AssetType,
        params: dict[str, Any],
        data: pd.DataFrame | None,
        context: dict[str, Any]
    ) -> dict[str, Any]:
        """Compute crypto-specific risk metrics"""
        if data is None:
            data = await self._fetch_data(instrument_key, context)

        returns = data["close"].pct_change().dropna()

        # 24-hour metrics (crypto trades 24/7)
        hourly_volatility = returns.tail(24).std() * np.sqrt(24)

        # Extreme move probability
        extreme_threshold = params.get("extreme_threshold", 0.1)  # 10% move
        extreme_moves = (returns.abs() > extreme_threshold).sum()
        extreme_probability = extreme_moves / len(returns)

        # Liquidity risk (using volume)
        avg_volume = data["volume"].rolling(window=24).mean().iloc[-1]
        current_volume = data["volume"].iloc[-1]
        volume_ratio = current_volume / avg_volume if avg_volume > 0 else 0

        if volume_ratio < 0.5:
            liquidity_risk = "high"
        elif volume_ratio < 0.8:
            liquidity_risk = "medium"
        else:
            liquidity_risk = "low"

        return {
            "24h_volatility": round(hourly_volatility * 100, 2),
            "extreme_move_probability": round(extreme_probability * 100, 2),
            "extreme_threshold": round(extreme_threshold * 100, 2),
            "liquidity_risk": liquidity_risk,
            "volume_ratio": round(volume_ratio, 2),
            "current_volume": current_volume
        }

    def _extract_option_params(
        self,
        instrument_key: str,
        context: dict[str, Any]
    ) -> dict[str, Any]:
        """Extract option parameters from instrument key and context"""
        # Parse instrument key (format: EXCHANGE@SYMBOL@STRIKE@EXPIRY@TYPE)
        parts = instrument_key.split("@")

        # Get from context or parse from key
        return {
            "spot_price": context.get("spot_price", 100),
            "strike_price": context.get("strike_price", float(parts[2]) if len(parts) > 2 else 100),
            "time_to_expiry": context.get("time_to_expiry", 0.25),  # Years
            "days_to_expiry": context.get("days_to_expiry", 90),
            "option_type": context.get("option_type", parts[4] if len(parts) > 4 else "call"),
            "option_price": context.get("option_price"),
            "volatility": context.get("volatility", 0.2)
        }

    def _extract_futures_params(
        self,
        instrument_key: str,
        context: dict[str, Any]
    ) -> dict[str, Any]:
        """Extract futures parameters from instrument key and context"""
        return {
            "futures_price": context.get("futures_price", 100),
            "spot_price": context.get("spot_price", 99),
            "days_to_expiry": context.get("days_to_expiry", 30),
            "contract_size": context.get("contract_size", 1),
            "tick_size": context.get("tick_size", 0.01)
        }

    async def _fetch_data(
        self,
        instrument_key: str,
        context: dict[str, Any]
    ) -> pd.DataFrame:
        """Fetch historical data for instrument"""
