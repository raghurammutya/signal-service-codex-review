#!/usr/bin/env python3
"""
Risk Engine Service - Phase 1 Migration

STRATEGY_002: Risk Engine Contract Updates
- Risk calculations based on instrument metadata from registry
- Position limits enforced by instrument_key
- Risk monitoring alerts use instrument symbols, not tokens
- Portfolio analytics aggregated by metadata characteristics
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

import numpy as np

from app.sdk import InstrumentClient, create_instrument_client

logger = logging.getLogger(__name__)

class RiskLevel(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

class RiskMetric(Enum):
    VAR = "value_at_risk"
    CONCENTRATION = "concentration_risk"
    VOLATILITY = "volatility_risk"
    CORRELATION = "correlation_risk"
    SECTOR_EXPOSURE = "sector_exposure"
    LEVERAGE = "leverage_risk"

@dataclass
class RiskLimit:
    """Risk limit configuration with metadata-based rules"""
    limit_type: str                    # position, sector, exchange, volatility
    identifier: str                    # instrument_key, sector name, exchange
    max_value: float                   # Maximum allowed value
    threshold_warning: float           # Warning threshold (% of max)
    threshold_critical: float          # Critical threshold (% of max)
    enabled: bool = True
    # Metadata-based conditions
    applies_to_sectors: list[str] | None = None
    applies_to_exchanges: list[str] | None = None
    applies_to_instrument_types: list[str] | None = None

@dataclass
class RiskAlert:
    """Risk alert with enriched instrument metadata"""
    alert_id: str
    risk_type: RiskMetric
    level: RiskLevel
    instrument_key: str               # Primary identifier
    symbol: str                       # Enriched from registry
    exchange: str                     # Enriched from registry
    sector: str                       # Enriched from registry
    current_value: float
    limit_value: float
    breach_percentage: float
    message: str
    timestamp: datetime = field(default_factory=datetime.now)
    acknowledged: bool = False

@dataclass
class PortfolioRiskMetrics:
    """Portfolio risk metrics with metadata aggregations"""
    portfolio_id: str
    total_exposure: float
    value_at_risk: float             # 1-day VaR at 95% confidence
    max_drawdown: float
    volatility: float
    sharpe_ratio: float
    # Metadata-based risk breakdowns
    sector_exposures: dict[str, float] = field(default_factory=dict)
    exchange_exposures: dict[str, float] = field(default_factory=dict)
    concentration_by_instrument: dict[str, float] = field(default_factory=dict)
    correlation_matrix: dict[str, dict[str, float]] | None = None
    timestamp: datetime = field(default_factory=datetime.now)

class RiskEngineService:
    """
    Risk Engine Service - Phase 1 Migration

    STRATEGY_002: All risk calculations use instrument_key as primary identifier
    with registry metadata for enhanced risk rules and monitoring.
    """

    def __init__(self, instrument_client: InstrumentClient | None = None):
        """
        Initialize risk engine with Phase 1 SDK integration

        Args:
            instrument_client: Client for metadata enrichment
        """
        self.instrument_client = instrument_client or create_instrument_client()

        # Risk configuration
        self._risk_limits: dict[str, RiskLimit] = {}
        self._active_alerts: dict[str, RiskAlert] = {}
        self._portfolio_metrics: dict[str, PortfolioRiskMetrics] = {}

        # Initialize default risk limits
        self._initialize_default_limits()

    def _initialize_default_limits(self):
        """Initialize default metadata-based risk limits"""
        default_limits = [
            # Position-based limits
            RiskLimit(
                limit_type="position",
                identifier="single_instrument",
                max_value=0.1,  # 10% of portfolio max per instrument
                threshold_warning=0.75,
                threshold_critical=0.9
            ),
            # Sector concentration limits
            RiskLimit(
                limit_type="sector",
                identifier="Technology",
                max_value=0.3,  # 30% max in tech sector
                threshold_warning=0.8,
                threshold_critical=0.9,
                applies_to_sectors=["Technology", "Software"]
            ),
            # Exchange concentration limits
            RiskLimit(
                limit_type="exchange",
                identifier="NASDAQ",
                max_value=0.4,  # 40% max on NASDAQ
                threshold_warning=0.8,
                threshold_critical=0.9
            ),
            # Volatility-based limits
            RiskLimit(
                limit_type="volatility",
                identifier="high_vol_instruments",
                max_value=0.15,  # 15% max in high volatility instruments
                threshold_warning=0.8,
                threshold_critical=0.9
            )
        ]

        for limit in default_limits:
            self._risk_limits[f"{limit.limit_type}_{limit.identifier}"] = limit

    # =============================================================================
    # RISK CALCULATION METHODS (metadata-based)
    # =============================================================================

    async def calculate_portfolio_risk(self,
                                     portfolio_id: str,
                                     positions: list[dict[str, Any]]) -> PortfolioRiskMetrics:
        """
        Calculate comprehensive portfolio risk metrics

        Args:
            portfolio_id: Portfolio identifier
            positions: list of positions with instrument_key

        Returns:
            PortfolioRiskMetrics: Risk metrics with metadata breakdowns
        """
        if not positions:
            return PortfolioRiskMetrics(
                portfolio_id=portfolio_id,
                total_exposure=0.0,
                value_at_risk=0.0,
                max_drawdown=0.0,
                volatility=0.0,
                sharpe_ratio=0.0
            )

        # Enrich positions with metadata
        enriched_positions = []
        for position in positions:
            try:
                metadata = await self.instrument_client.get_instrument_metadata(
                    position['instrument_key']
                )
                enriched_positions.append({
                    **position,
                    'symbol': metadata.symbol,
                    'exchange': metadata.exchange,
                    'sector': metadata.sector or 'Unknown',
                    'instrument_type': metadata.instrument_type,
                    'market_cap': getattr(metadata, 'market_cap', None)
                })
            except Exception as e:
                logger.warning(f"Failed to enrich position {position['instrument_key']}: {e}")
                # Use position without metadata
                enriched_positions.append({
                    **position,
                    'symbol': position.get('symbol', 'Unknown'),
                    'exchange': 'Unknown',
                    'sector': 'Unknown'
                })

        # Calculate total exposure
        total_exposure = sum(
            abs(pos.get('market_value', pos.get('quantity', 0) * pos.get('price', 0)))
            for pos in enriched_positions
        )

        # Calculate sector exposures
        sector_exposures = {}
        for position in enriched_positions:
            sector = position['sector']
            market_value = abs(position.get('market_value',
                              position.get('quantity', 0) * position.get('price', 0)))
            sector_exposures[sector] = sector_exposures.get(sector, 0) + market_value

        # Convert to percentages
        if total_exposure > 0:
            sector_exposures = {k: v/total_exposure for k, v in sector_exposures.items()}

        # Calculate exchange exposures
        exchange_exposures = {}
        for position in enriched_positions:
            exchange = position['exchange']
            market_value = abs(position.get('market_value',
                              position.get('quantity', 0) * position.get('price', 0)))
            exchange_exposures[exchange] = exchange_exposures.get(exchange, 0) + market_value

        if total_exposure > 0:
            exchange_exposures = {k: v/total_exposure for k, v in exchange_exposures.items()}

        # Calculate concentration risk by instrument
        concentration_by_instrument = {}
        for position in enriched_positions:
            instrument_key = position['instrument_key']
            market_value = abs(position.get('market_value',
                              position.get('quantity', 0) * position.get('price', 0)))
            if total_exposure > 0:
                concentration_by_instrument[instrument_key] = market_value / total_exposure

        # Calculate VaR (simplified - in real implementation would use historical data)
        position_values = [
            abs(pos.get('market_value', pos.get('quantity', 0) * pos.get('price', 0)))
            for pos in enriched_positions
        ]

        if position_values:
            portfolio_vol = np.std(position_values) / np.mean(position_values) if position_values else 0
            var_95 = total_exposure * portfolio_vol * 1.65  # 95% confidence interval
        else:
            portfolio_vol = 0
            var_95 = 0

        # Create risk metrics
        metrics = PortfolioRiskMetrics(
            portfolio_id=portfolio_id,
            total_exposure=total_exposure,
            value_at_risk=var_95,
            max_drawdown=0.0,  # Would calculate from historical performance
            volatility=portfolio_vol,
            sharpe_ratio=0.0,  # Would calculate from returns
            sector_exposures=sector_exposures,
            exchange_exposures=exchange_exposures,
            concentration_by_instrument=concentration_by_instrument
        )

        # Cache metrics
        self._portfolio_metrics[portfolio_id] = metrics

        logger.info(f"Portfolio risk calculated: {portfolio_id} - Total exposure: {total_exposure:.2f}")
        return metrics

    async def check_risk_limits(self,
                              portfolio_id: str,
                              positions: list[dict[str, Any]]) -> list[RiskAlert]:
        """
        Check positions against configured risk limits

        Args:
            portfolio_id: Portfolio identifier
            positions: Current positions with instrument_key

        Returns:
            list[RiskAlert]: Active risk limit breaches
        """
        # Calculate current portfolio metrics
        metrics = await self.calculate_portfolio_risk(portfolio_id, positions)
        alerts = []

        # Check position concentration limits
        for instrument_key, concentration in metrics.concentration_by_instrument.items():
            position_limit = self._risk_limits.get("position_single_instrument")
            if position_limit and position_limit.enabled:
                if concentration >= position_limit.max_value * position_limit.threshold_critical:
                    level = RiskLevel.CRITICAL
                elif concentration >= position_limit.max_value * position_limit.threshold_warning:
                    level = RiskLevel.HIGH
                else:
                    continue

                # Get instrument metadata for alert
                try:
                    metadata = await self.instrument_client.get_instrument_metadata(instrument_key)
                    alert = RiskAlert(
                        alert_id=f"concentration_{instrument_key}_{datetime.now().timestamp()}",
                        risk_type=RiskMetric.CONCENTRATION,
                        level=level,
                        instrument_key=instrument_key,
                        symbol=metadata.symbol,
                        exchange=metadata.exchange,
                        sector=metadata.sector or "Unknown",
                        current_value=concentration,
                        limit_value=position_limit.max_value,
                        breach_percentage=(concentration - position_limit.max_value) / position_limit.max_value * 100,
                        message=f"Position concentration in {metadata.symbol} exceeds {level.value} threshold"
                    )
                    alerts.append(alert)
                except Exception as e:
                    logger.error(f"Failed to create concentration alert for {instrument_key}: {e}")

        # Check sector concentration limits
        for sector, exposure in metrics.sector_exposures.items():
            sector_limit = self._risk_limits.get(f"sector_{sector}")
            if sector_limit and sector_limit.enabled:
                if exposure >= sector_limit.max_value * sector_limit.threshold_critical:
                    level = RiskLevel.CRITICAL
                elif exposure >= sector_limit.max_value * sector_limit.threshold_warning:
                    level = RiskLevel.HIGH
                else:
                    continue

                alert = RiskAlert(
                    alert_id=f"sector_{sector}_{datetime.now().timestamp()}",
                    risk_type=RiskMetric.SECTOR_EXPOSURE,
                    level=level,
                    instrument_key=f"SECTOR_{sector}",
                    symbol=sector,
                    exchange="Multiple",
                    sector=sector,
                    current_value=exposure,
                    limit_value=sector_limit.max_value,
                    breach_percentage=(exposure - sector_limit.max_value) / sector_limit.max_value * 100,
                    message=f"Sector exposure in {sector} exceeds {level.value} threshold"
                )
                alerts.append(alert)

        # Check exchange concentration limits
        for exchange, exposure in metrics.exchange_exposures.items():
            exchange_limit = self._risk_limits.get(f"exchange_{exchange}")
            if exchange_limit and exchange_limit.enabled:
                if exposure >= exchange_limit.max_value * exchange_limit.threshold_critical:
                    level = RiskLevel.CRITICAL
                elif exposure >= exchange_limit.max_value * exchange_limit.threshold_warning:
                    level = RiskLevel.HIGH
                else:
                    continue

                alert = RiskAlert(
                    alert_id=f"exchange_{exchange}_{datetime.now().timestamp()}",
                    risk_type=RiskMetric.CONCENTRATION,
                    level=level,
                    instrument_key=f"EXCHANGE_{exchange}",
                    symbol=exchange,
                    exchange=exchange,
                    sector="Multiple",
                    current_value=exposure,
                    limit_value=exchange_limit.max_value,
                    breach_percentage=(exposure - exchange_limit.max_value) / exchange_limit.max_value * 100,
                    message=f"Exchange exposure on {exchange} exceeds {level.value} threshold"
                )
                alerts.append(alert)

        # Store active alerts
        for alert in alerts:
            self._active_alerts[alert.alert_id] = alert

        if alerts:
            logger.warning(f"Risk alerts generated for {portfolio_id}: {len(alerts)} breaches")

        return alerts

    # =============================================================================
    # POSITION VALIDATION (instrument_key-based)
    # =============================================================================

    async def validate_position(self,
                              portfolio_id: str,
                              instrument_key: str,
                              quantity: int,
                              price: float,
                              current_positions: list[dict[str, Any]]) -> dict[str, Any]:
        """
        Validate proposed position against risk limits

        Args:
            portfolio_id: Portfolio identifier
            instrument_key: Position instrument
            quantity: Proposed quantity
            price: Position price
            current_positions: Current portfolio positions

        Returns:
            dict: Validation result with risk assessment
        """
        # Get instrument metadata
        try:
            metadata = await self.instrument_client.get_instrument_metadata(instrument_key)
        except Exception as e:
            logger.error(f"Failed to get metadata for {instrument_key}: {e}")
            return {
                "valid": False,
                "reason": f"Invalid instrument: {instrument_key}",
                "risk_level": RiskLevel.CRITICAL.value
            }

        # Calculate position value
        position_value = abs(quantity * price)

        # Calculate current portfolio metrics
        current_metrics = await self.calculate_portfolio_risk(portfolio_id, current_positions)

        # Simulate adding the new position
        simulated_positions = current_positions.copy()
        simulated_positions.append({
            'instrument_key': instrument_key,
            'quantity': quantity,
            'price': price,
            'market_value': position_value
        })

        simulated_metrics = await self.calculate_portfolio_risk(portfolio_id, simulated_positions)

        # Check position concentration
        new_concentration = position_value / simulated_metrics.total_exposure if simulated_metrics.total_exposure > 0 else 0
        position_limit = self._risk_limits.get("position_single_instrument")

        if position_limit and new_concentration > position_limit.max_value:
            return {
                "valid": False,
                "reason": f"Position in {metadata.symbol} would exceed concentration limit",
                "risk_level": RiskLevel.CRITICAL.value,
                "current_concentration": new_concentration,
                "limit": position_limit.max_value,
                "instrument_metadata": {
                    "symbol": metadata.symbol,
                    "exchange": metadata.exchange,
                    "sector": metadata.sector
                }
            }

        # Check sector limits
        sector = metadata.sector or "Unknown"
        new_sector_exposure = simulated_metrics.sector_exposures.get(sector, 0)
        sector_limit = self._risk_limits.get(f"sector_{sector}")

        if sector_limit and new_sector_exposure > sector_limit.max_value:
            return {
                "valid": False,
                "reason": f"Position would exceed {sector} sector limit",
                "risk_level": RiskLevel.HIGH.value,
                "sector_exposure": new_sector_exposure,
                "sector_limit": sector_limit.max_value,
                "instrument_metadata": {
                    "symbol": metadata.symbol,
                    "exchange": metadata.exchange,
                    "sector": metadata.sector
                }
            }

        # Calculate risk level for valid position
        risk_level = RiskLevel.LOW
        if new_concentration > position_limit.max_value * 0.7 if position_limit else False:
            risk_level = RiskLevel.MEDIUM
        if new_sector_exposure > sector_limit.max_value * 0.8 if sector_limit else False:
            risk_level = RiskLevel.MEDIUM

        return {
            "valid": True,
            "risk_level": risk_level.value,
            "position_concentration": new_concentration,
            "sector_exposure": new_sector_exposure,
            "portfolio_impact": {
                "total_exposure_change": simulated_metrics.total_exposure - current_metrics.total_exposure,
                "var_change": simulated_metrics.value_at_risk - current_metrics.value_at_risk
            },
            "instrument_metadata": {
                "symbol": metadata.symbol,
                "exchange": metadata.exchange,
                "sector": metadata.sector,
                "instrument_type": metadata.instrument_type
            }
        }

    # =============================================================================
    # RISK MONITORING AND ALERTS
    # =============================================================================

    async def get_portfolio_risk_summary(self, portfolio_id: str) -> dict[str, Any]:
        """
        Get comprehensive risk summary for portfolio

        Args:
            portfolio_id: Portfolio identifier

        Returns:
            dict: Risk summary with metadata breakdowns
        """
        metrics = self._portfolio_metrics.get(portfolio_id)
        if not metrics:
            return {
                "portfolio_id": portfolio_id,
                "status": "no_data",
                "message": "No risk metrics available"
            }

        # Get active alerts for this portfolio
        portfolio_alerts = [
            alert for alert in self._active_alerts.values()
            if not alert.acknowledged
        ]

        # Categorize alerts by risk level
        alert_counts = {level.value: 0 for level in RiskLevel}
        for alert in portfolio_alerts:
            alert_counts[alert.level.value] += 1

        return {
            "portfolio_id": portfolio_id,
            "risk_summary": {
                "total_exposure": metrics.total_exposure,
                "value_at_risk": metrics.value_at_risk,
                "volatility": metrics.volatility,
                "sharpe_ratio": metrics.sharpe_ratio
            },
            "concentration_analysis": {
                "sector_exposures": metrics.sector_exposures,
                "exchange_exposures": metrics.exchange_exposures,
                "top_positions": dict(sorted(
                    metrics.concentration_by_instrument.items(),
                    key=lambda x: x[1],
                    reverse=True
                )[:5])  # Top 5 positions
            },
            "alert_summary": {
                "total_alerts": len(portfolio_alerts),
                "by_severity": alert_counts,
                "recent_alerts": [
                    {
                        "alert_id": alert.alert_id,
                        "risk_type": alert.risk_type.value,
                        "level": alert.level.value,
                        "symbol": alert.symbol,
                        "message": alert.message,
                        "timestamp": alert.timestamp.isoformat()
                    }
                    for alert in sorted(portfolio_alerts, key=lambda x: x.timestamp, reverse=True)[:5]
                ]
            },
            "timestamp": datetime.now().isoformat()
        }

    # =============================================================================
    # RISK LIMIT MANAGEMENT
    # =============================================================================

    async def update_risk_limit(self, limit_id: str, limit: RiskLimit) -> dict[str, Any]:
        """Update risk limit configuration"""
        self._risk_limits[limit_id] = limit

        return {
            "limit_id": limit_id,
            "status": "updated",
            "limit_type": limit.limit_type,
            "max_value": limit.max_value,
            "enabled": limit.enabled,
            "timestamp": datetime.now().isoformat()
        }

    async def get_risk_limits(self) -> dict[str, Any]:
        """Get all configured risk limits"""
        return {
            "risk_limits": {
                limit_id: {
                    "limit_type": limit.limit_type,
                    "identifier": limit.identifier,
                    "max_value": limit.max_value,
                    "threshold_warning": limit.threshold_warning,
                    "threshold_critical": limit.threshold_critical,
                    "enabled": limit.enabled,
                    "metadata_conditions": {
                        "sectors": limit.applies_to_sectors,
                        "exchanges": limit.applies_to_exchanges,
                        "instrument_types": limit.applies_to_instrument_types
                    }
                }
                for limit_id, limit in self._risk_limits.items()
            },
            "total_limits": len(self._risk_limits),
            "active_limits": sum(1 for limit in self._risk_limits.values() if limit.enabled)
        }
