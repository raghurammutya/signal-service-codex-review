#!/usr/bin/env python3
"""
Enhanced Strategy API Endpoints with Metadata Enrichment - Phase 1

Demonstrates integration of META_001 metadata enrichment middleware
with strategy services for automatic response enrichment.
"""

import asyncio
import logging
from typing import Dict, Any, List, Optional
from fastapi import FastAPI, HTTPException, Query, Path, Depends
from datetime import datetime
from app.middleware.metadata_enrichment import MetadataEnrichmentMiddleware, EnrichmentConfig
from app.services.strategy_execution_service import StrategyExecutionService, StrategyConfig, PositionType
from app.services.risk_engine_service import RiskEngineService, AlertPriority
from app.services.trailing_stop_service import TrailingStopService, TrailingStopType
from app.services.alert_service import AlertService, AlertType, AlertCondition, NotificationChannel

logger = logging.getLogger(__name__)

# Initialize services and middleware
enrichment_config = EnrichmentConfig(
    enable_caching=True,
    cache_ttl_seconds=300,
    performance_threshold_ms=50.0,
    include_fields=['symbol', 'exchange', 'sector', 'instrument_type', 'lot_size']
)

metadata_middleware = MetadataEnrichmentMiddleware(config=enrichment_config)
strategy_service = StrategyExecutionService()
risk_service = RiskEngineService()
trailing_service = TrailingStopService()
alert_service = AlertService()

class StrategyAPIEnriched:
    """Enhanced Strategy API with automatic metadata enrichment"""
    
    # =============================================================================
    # STRATEGY EXECUTION ENDPOINTS (with enrichment)
    # =============================================================================
    
    @metadata_middleware.enrich_response()
    async def create_strategy(self, strategy_config: Dict[str, Any]) -> Dict[str, Any]:
        """Create strategy with enriched instrument metadata"""
        
        # Convert to StrategyConfig object
        config = StrategyConfig(
            strategy_id=strategy_config["strategy_id"],
            name=strategy_config["name"], 
            description=strategy_config["description"],
            target_instruments=strategy_config["target_instruments"],
            max_position_size=strategy_config.get("max_position_size", 1000),
            max_positions=strategy_config.get("max_positions", 10),
            risk_percentage=strategy_config.get("risk_percentage", 0.02)
        )
        
        # Create strategy (response will be auto-enriched)
        result = await strategy_service.create_strategy(config)
        
        return result
    
    @metadata_middleware.enrich_response()
    async def open_position(self,
                          strategy_id: str,
                          position_request: Dict[str, Any]) -> Dict[str, Any]:
        """Open strategy position with enriched metadata"""
        
        result = await strategy_service.open_position(
            strategy_id=strategy_id,
            instrument_key=position_request["instrument_key"],
            position_type=PositionType(position_request["position_type"]),
            quantity=position_request["quantity"],
            entry_price=position_request.get("entry_price")
        )
        
        return result
    
    @metadata_middleware.enrich_response()
    async def get_strategy_performance(self, strategy_id: str) -> Dict[str, Any]:
        """Get strategy performance with enriched metadata analytics"""
        
        performance = await strategy_service.get_strategy_performance(strategy_id)
        
        # Add enrichment metadata for better analytics
        performance["enrichment_info"] = {
            "metadata_source": "Phase_3_Registry",
            "enriched_at": datetime.now().isoformat(),
            "performance_enhanced": True
        }
        
        return performance
    
    @metadata_middleware.enrich_response()
    async def get_active_strategies(self) -> Dict[str, Any]:
        """Get all active strategies with enriched instrument info"""
        
        strategies = await strategy_service.get_active_strategies()
        
        return strategies
    
    # =============================================================================
    # RISK MANAGEMENT ENDPOINTS (with enrichment)
    # =============================================================================
    
    @metadata_middleware.enrich_response()
    async def calculate_portfolio_risk(self,
                                     portfolio_id: str,
                                     positions: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Calculate portfolio risk with metadata-based analytics"""
        
        risk_metrics = await risk_service.calculate_portfolio_risk(portfolio_id, positions)
        
        # Convert to dict format for enrichment
        result = {
            "portfolio_id": risk_metrics.portfolio_id,
            "total_exposure": risk_metrics.total_exposure,
            "value_at_risk": risk_metrics.value_at_risk,
            "volatility": risk_metrics.volatility,
            "sharpe_ratio": risk_metrics.sharpe_ratio,
            "sector_exposures": risk_metrics.sector_exposures,
            "exchange_exposures": risk_metrics.exchange_exposures,
            "concentration_analysis": risk_metrics.concentration_by_instrument,
            "timestamp": risk_metrics.timestamp.isoformat(),
            # Include position details for enrichment
            "positions": positions
        }
        
        return result
    
    @metadata_middleware.enrich_response()
    async def validate_position(self,
                              portfolio_id: str,
                              position_request: Dict[str, Any],
                              current_positions: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Validate position with enriched risk analysis"""
        
        validation = await risk_service.validate_position(
            portfolio_id=portfolio_id,
            instrument_key=position_request["instrument_key"],
            quantity=position_request["quantity"],
            price=position_request["price"],
            current_positions=current_positions
        )
        
        return validation
    
    @metadata_middleware.enrich_response()
    async def get_portfolio_risk_summary(self, portfolio_id: str) -> Dict[str, Any]:
        """Get portfolio risk summary with enriched metadata"""
        
        summary = await risk_service.get_portfolio_risk_summary(portfolio_id)
        
        return summary
    
    # =============================================================================
    # TRAILING STOP ENDPOINTS (with enrichment)
    # =============================================================================
    
    @metadata_middleware.enrich_response()
    async def create_trailing_stop(self, stop_request: Dict[str, Any]) -> Dict[str, Any]:
        """Create trailing stop with enriched instrument metadata"""
        
        result = await trailing_service.create_trailing_stop(
            instrument_key=stop_request["instrument_key"],
            side=stop_request["side"],
            quantity=stop_request["quantity"],
            trail_type=TrailingStopType(stop_request["trail_type"]),
            trail_value=stop_request["trail_value"],
            initial_stop_price=stop_request.get("initial_stop_price"),
            expires_in_hours=stop_request.get("expires_in_hours", 24)
        )
        
        return result
    
    @metadata_middleware.enrich_response()
    async def get_trailing_stop_status(self, stop_id: str) -> Dict[str, Any]:
        """Get trailing stop status with enriched metadata"""
        
        status = await trailing_service.get_trailing_stop_status(stop_id)
        
        return status
    
    @metadata_middleware.enrich_response()
    async def get_active_trailing_stops(self, instrument_key: Optional[str] = None) -> Dict[str, Any]:
        """Get active trailing stops with enriched metadata"""
        
        stops = await trailing_service.get_active_trailing_stops(instrument_key)
        
        return stops
    
    # =============================================================================
    # ALERT ENDPOINTS (with enrichment)
    # =============================================================================
    
    @metadata_middleware.enrich_response()
    async def create_price_alert(self, alert_request: Dict[str, Any]) -> Dict[str, Any]:
        """Create price alert with enriched metadata"""
        
        condition = AlertCondition(
            condition_type=AlertType(alert_request["condition"]["type"]),
            value=alert_request["condition"]["value"],
            comparison=alert_request["condition"]["comparison"]
        )
        
        channels = [
            NotificationChannel(ch) for ch in alert_request.get("channels", ["in_app"])
        ]
        
        result = await alert_service.create_price_alert(
            user_id=alert_request["user_id"],
            instrument_key=alert_request["instrument_key"],
            condition=condition,
            priority=AlertPriority(alert_request.get("priority", "medium")),
            channels=channels,
            custom_message=alert_request.get("message"),
            expires_in_hours=alert_request.get("expires_in_hours", 24)
        )
        
        return result
    
    @metadata_middleware.enrich_response()
    async def get_user_alerts(self, user_id: str, include_history: bool = True) -> Dict[str, Any]:
        """Get user alerts with enriched metadata"""
        
        alerts = await alert_service.get_user_alerts(user_id, include_history)
        
        return alerts
    
    @metadata_middleware.enrich_response()
    async def get_instrument_alerts(self, instrument_key: str) -> Dict[str, Any]:
        """Get alerts for specific instrument with enriched metadata"""
        
        alerts = await alert_service.get_instrument_alerts(instrument_key)
        
        return alerts
    
    # =============================================================================
    # MARKET DATA ENDPOINTS (with enrichment) 
    # =============================================================================
    
    @metadata_middleware.enrich_response()
    async def get_enriched_quote(self, instrument_key: str) -> Dict[str, Any]:
        """Get market quote enriched with instrument metadata"""
        
        # Mock market data - in real implementation would fetch from data service
        quote_data = {
            "instrument_key": instrument_key,
            "ltp": 150.25,
            "open": 149.80,
            "high": 151.00,
            "low": 149.50,
            "close": 150.10,
            "volume": 1250000,
            "timestamp": datetime.now().isoformat(),
            "market_status": "open"
        }
        
        # Enrich with metadata
        enriched_quote = await metadata_middleware.enrich_market_data(quote_data)
        
        return enriched_quote
    
    @metadata_middleware.enrich_response()
    async def get_enriched_historical_data(self,
                                         instrument_key: str,
                                         timeframe: str = "5m",
                                         periods: int = 100) -> Dict[str, Any]:
        """Get historical data enriched with metadata"""
        
        # Mock historical data
        historical_data = {
            "instrument_key": instrument_key,
            "timeframe": timeframe,
            "periods": periods,
            "data": [
                {
                    "timestamp": datetime.now().isoformat(),
                    "open": 150.0,
                    "high": 151.0, 
                    "low": 149.5,
                    "close": 150.5,
                    "volume": 100000
                }
            ],
            "total_records": periods,
            "data_source": "Phase_1_SDK"
        }
        
        return historical_data
    
    # =============================================================================
    # ENRICHMENT MONITORING ENDPOINTS
    # =============================================================================
    
    async def get_enrichment_metrics(self) -> Dict[str, Any]:
        """Get metadata enrichment performance metrics"""
        
        metrics = metadata_middleware.get_performance_metrics()
        
        return {
            "metadata_enrichment": metrics,
            "service_status": {
                "strategy_service": "active",
                "risk_service": "active", 
                "trailing_service": "active",
                "alert_service": "active"
            },
            "timestamp": datetime.now().isoformat()
        }
    
    async def enrichment_health_check(self) -> Dict[str, Any]:
        """Health check for metadata enrichment"""
        
        health = await metadata_middleware.health_check()
        
        return {
            "enrichment_health": health,
            "phase_1_migration_status": "active",
            "registry_integration": "Phase_3_Compatible",
            "performance_compliance": health.get("performance_within_threshold", False),
            "timestamp": datetime.now().isoformat()
        }

# =============================================================================
# FASTAPI INTEGRATION EXAMPLE
# =============================================================================

def create_enriched_strategy_api() -> FastAPI:
    """Create FastAPI app with enriched strategy endpoints"""
    
    app = FastAPI(
        title="Strategy API - Phase 1 Migration",
        description="Enhanced strategy APIs with automatic metadata enrichment",
        version="1.0.0"
    )
    
    api = StrategyAPIEnriched()
    
    # Strategy endpoints
    @app.post("/api/v1/strategies", response_model=dict)
    async def create_strategy_endpoint(strategy_config: dict):
        return await api.create_strategy(strategy_config)
    
    @app.post("/api/v1/strategies/{strategy_id}/positions", response_model=dict)
    async def open_position_endpoint(strategy_id: str, position_request: dict):
        return await api.open_position(strategy_id, position_request)
    
    @app.get("/api/v1/strategies/{strategy_id}/performance", response_model=dict)
    async def get_performance_endpoint(strategy_id: str):
        return await api.get_strategy_performance(strategy_id)
    
    @app.get("/api/v1/strategies", response_model=dict)
    async def get_strategies_endpoint():
        return await api.get_active_strategies()
    
    # Risk endpoints
    @app.post("/api/v1/risk/portfolio/{portfolio_id}/calculate", response_model=dict)
    async def calculate_risk_endpoint(portfolio_id: str, positions: List[dict]):
        return await api.calculate_portfolio_risk(portfolio_id, positions)
    
    @app.post("/api/v1/risk/portfolio/{portfolio_id}/validate", response_model=dict)
    async def validate_position_endpoint(
        portfolio_id: str, 
        position: dict, 
        current_positions: List[dict]
    ):
        return await api.validate_position(portfolio_id, position, current_positions)
    
    # Trailing stop endpoints
    @app.post("/api/v1/trailing-stops", response_model=dict)
    async def create_trailing_stop_endpoint(stop_request: dict):
        return await api.create_trailing_stop(stop_request)
    
    @app.get("/api/v1/trailing-stops/{stop_id}", response_model=dict)
    async def get_trailing_stop_endpoint(stop_id: str):
        return await api.get_trailing_stop_status(stop_id)
    
    # Alert endpoints
    @app.post("/api/v1/alerts", response_model=dict)
    async def create_alert_endpoint(alert_request: dict):
        return await api.create_price_alert(alert_request)
    
    @app.get("/api/v1/alerts/user/{user_id}", response_model=dict)
    async def get_user_alerts_endpoint(user_id: str, include_history: bool = True):
        return await api.get_user_alerts(user_id, include_history)
    
    # Market data endpoints 
    @app.get("/api/v1/market-data/{instrument_key}/quote", response_model=dict)
    async def get_quote_endpoint(instrument_key: str):
        return await api.get_enriched_quote(instrument_key)
    
    @app.get("/api/v1/market-data/{instrument_key}/historical", response_model=dict)
    async def get_historical_endpoint(
        instrument_key: str, 
        timeframe: str = "5m", 
        periods: int = 100
    ):
        return await api.get_enriched_historical_data(instrument_key, timeframe, periods)
    
    # Monitoring endpoints
    @app.get("/api/v1/enrichment/metrics", response_model=dict)
    async def enrichment_metrics_endpoint():
        return await api.get_enrichment_metrics()
    
    @app.get("/api/v1/enrichment/health", response_model=dict)
    async def enrichment_health_endpoint():
        return await api.enrichment_health_check()
    
    return app

# Example usage
if __name__ == "__main__":
    app = create_enriched_strategy_api()
    print("Strategy API with metadata enrichment ready")
    
    # Example enriched API calls would show:
    # {
    #   "strategy_id": "momentum_strategy_1",
    #   "instrument_key": "AAPL_NASDAQ_EQUITY",
    #   "symbol": "AAPL",           # <- Enriched from registry
    #   "exchange": "NASDAQ",       # <- Enriched from registry  
    #   "sector": "Technology",     # <- Enriched from registry
    #   "instrument_metadata": {    # <- Complete metadata object
    #     "symbol": "AAPL",
    #     "exchange": "NASDAQ", 
    #     "sector": "Technology",
    #     "instrument_type": "EQUITY",
    #     "lot_size": 1,
    #     "tick_size": 0.01,
    #     "enriched_at": "2026-01-27T..."
    #   },
    #   "enriched_at": "2026-01-27T...",
    #   ... rest of response
    # }