#!/usr/bin/env python3
"""
Strategy Execution Service - Phase 1 Migration

STRATEGY_001: Update Strategy Host APIs  
- All strategy APIs require instrument_key parameters
- Strategy execution uses registry-derived tokens internally
- Position tracking by instrument_key with metadata enrichment
- Historical performance data aggregated by instrument characteristics
"""

import asyncio
import logging
from typing import Dict, Any, List, Optional, Union
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from app.sdk import InstrumentClient, OrderClient, create_instrument_client, create_order_client
from app.sdk import OrderType, OrderSide

logger = logging.getLogger(__name__)

class StrategyStatus(Enum):
    INACTIVE = "inactive"
    ACTIVE = "active"
    PAUSED = "paused"
    ERROR = "error"
    COMPLETED = "completed"

class PositionType(Enum):
    LONG = "long"
    SHORT = "short"
    NEUTRAL = "neutral"

@dataclass
class StrategyPosition:
    """Strategy position with instrument_key as primary identifier"""
    instrument_key: str          # Primary identifier - NO tokens
    symbol: str                  # Enriched from registry
    exchange: str               # Enriched from registry
    sector: str                 # Enriched from registry
    position_type: PositionType
    quantity: int
    entry_price: float
    current_price: float
    unrealized_pnl: float
    realized_pnl: float = 0.0
    entry_timestamp: datetime = field(default_factory=datetime.now)
    last_update: datetime = field(default_factory=datetime.now)
    # Internal fields - not exposed
    _broker_orders: List[str] = field(default_factory=list)

@dataclass 
class StrategyPerformance:
    """Strategy performance metrics with metadata enrichment"""
    strategy_id: str
    total_pnl: float
    win_rate: float
    max_drawdown: float
    sharpe_ratio: float
    total_trades: int
    winning_trades: int
    losing_trades: int
    avg_trade_duration: timedelta
    # Metadata-enriched analytics
    performance_by_sector: Dict[str, Dict[str, float]] = field(default_factory=dict)
    performance_by_exchange: Dict[str, Dict[str, float]] = field(default_factory=dict)
    top_performing_instruments: List[Dict[str, Any]] = field(default_factory=list)

@dataclass
class StrategyConfig:
    """Strategy configuration with instrument_key-based rules"""
    strategy_id: str
    name: str
    description: str
    target_instruments: List[str]  # List of instrument_keys
    max_position_size: int
    max_positions: int
    risk_percentage: float
    sector_limits: Optional[Dict[str, float]] = None  # Sector-based position limits
    exchange_preferences: Optional[List[str]] = None  # Preferred exchanges
    rebalance_frequency: str = "daily"

class StrategyExecutionService:
    """
    Strategy Execution Service - Phase 1 Migration
    
    STRATEGY_001: All strategy operations use instrument_key as primary identifier
    with automatic registry metadata enrichment and internal token resolution.
    """
    
    def __init__(self, 
                 instrument_client: Optional[InstrumentClient] = None,
                 order_client: Optional[OrderClient] = None):
        """
        Initialize strategy service with Phase 1 SDK integration
        
        Args:
            instrument_client: Client for metadata and token resolution
            order_client: Client for order management
        """
        self.instrument_client = instrument_client or create_instrument_client()
        self.order_client = order_client or create_order_client()
        
        # Strategy state management
        self._active_strategies: Dict[str, StrategyConfig] = {}
        self._strategy_positions: Dict[str, List[StrategyPosition]] = {}
        self._strategy_performance: Dict[str, StrategyPerformance] = {}
        self._strategy_status: Dict[str, StrategyStatus] = {}
    
    # =============================================================================
    # STRATEGY LIFECYCLE MANAGEMENT
    # =============================================================================
    
    async def create_strategy(self, config: StrategyConfig) -> Dict[str, Any]:
        """
        Create new strategy with instrument_key-based configuration
        
        Args:
            config: Strategy configuration with instrument_keys
            
        Returns:
            Dict: Strategy creation result with enriched metadata
        """
        strategy_id = config.strategy_id
        
        # Validate all target instruments exist and get metadata
        enriched_instruments = []
        for instrument_key in config.target_instruments:
            try:
                metadata = await self.instrument_client.get_instrument_metadata(instrument_key)
                enriched_instruments.append({
                    "instrument_key": instrument_key,
                    "symbol": metadata.symbol,
                    "exchange": metadata.exchange,
                    "sector": metadata.sector,
                    "instrument_type": metadata.instrument_type,
                    "lot_size": metadata.lot_size
                })
            except Exception as e:
                logger.error(f"Invalid instrument in strategy config: {instrument_key} - {e}")
                raise ValueError(f"Invalid instrument: {instrument_key}")
        
        # Initialize strategy state
        self._active_strategies[strategy_id] = config
        self._strategy_positions[strategy_id] = []
        self._strategy_status[strategy_id] = StrategyStatus.INACTIVE
        
        # Initialize performance tracking
        self._strategy_performance[strategy_id] = StrategyPerformance(
            strategy_id=strategy_id,
            total_pnl=0.0,
            win_rate=0.0,
            max_drawdown=0.0,
            sharpe_ratio=0.0,
            total_trades=0,
            winning_trades=0,
            losing_trades=0,
            avg_trade_duration=timedelta(hours=1)
        )
        
        logger.info(f"Strategy created: {strategy_id} with {len(enriched_instruments)} instruments")
        
        return {
            "strategy_id": strategy_id,
            "status": "created",
            "target_instruments": enriched_instruments,  # Includes enriched metadata
            "configuration": {
                "max_positions": config.max_positions,
                "max_position_size": config.max_position_size,
                "risk_percentage": config.risk_percentage
            },
            "created_at": datetime.now().isoformat()
        }
    
    async def start_strategy(self, strategy_id: str) -> Dict[str, Any]:
        """Start strategy execution"""
        if strategy_id not in self._active_strategies:
            raise ValueError(f"Strategy not found: {strategy_id}")
        
        self._strategy_status[strategy_id] = StrategyStatus.ACTIVE
        
        logger.info(f"Strategy started: {strategy_id}")
        
        return {
            "strategy_id": strategy_id,
            "status": "active",
            "started_at": datetime.now().isoformat()
        }
    
    async def stop_strategy(self, strategy_id: str) -> Dict[str, Any]:
        """Stop strategy execution and close all positions"""
        if strategy_id not in self._active_strategies:
            raise ValueError(f"Strategy not found: {strategy_id}")
        
        # Close all open positions
        positions = self._strategy_positions.get(strategy_id, [])
        for position in positions:
            if position.quantity != 0:
                await self._close_position(strategy_id, position.instrument_key)
        
        self._strategy_status[strategy_id] = StrategyStatus.INACTIVE
        
        logger.info(f"Strategy stopped: {strategy_id}")
        
        return {
            "strategy_id": strategy_id,
            "status": "inactive",
            "stopped_at": datetime.now().isoformat(),
            "positions_closed": len(positions)
        }
    
    # =============================================================================
    # POSITION MANAGEMENT (instrument_key-based)
    # =============================================================================
    
    async def open_position(self,
                           strategy_id: str,
                           instrument_key: str,
                           position_type: PositionType,
                           quantity: int,
                           entry_price: Optional[float] = None) -> Dict[str, Any]:
        """
        Open strategy position using instrument_key
        
        Args:
            strategy_id: Strategy identifier
            instrument_key: Primary identifier (e.g., "AAPL_NASDAQ_EQUITY")
            position_type: LONG/SHORT/NEUTRAL
            quantity: Position size
            entry_price: Entry price (market price if None)
            
        Returns:
            Dict: Position result with enriched metadata
        """
        if strategy_id not in self._active_strategies:
            raise ValueError(f"Strategy not found: {strategy_id}")
        
        if self._strategy_status[strategy_id] != StrategyStatus.ACTIVE:
            raise ValueError(f"Strategy not active: {strategy_id}")
        
        # Get instrument metadata for enrichment
        metadata = await self.instrument_client.get_instrument_metadata(instrument_key)
        
        # Validate position within strategy limits
        config = self._active_strategies[strategy_id]
        current_positions = self._strategy_positions.get(strategy_id, [])
        
        if len(current_positions) >= config.max_positions:
            raise ValueError(f"Maximum positions ({config.max_positions}) reached")
        
        if quantity > config.max_position_size:
            raise ValueError(f"Position size exceeds limit: {config.max_position_size}")
        
        # Check sector limits if configured
        if config.sector_limits and metadata.sector:
            sector_exposure = sum(
                pos.quantity for pos in current_positions 
                if pos.sector == metadata.sector
            )
            sector_limit = config.sector_limits.get(metadata.sector, float('inf'))
            
            if sector_exposure + quantity > sector_limit:
                raise ValueError(f"Sector limit exceeded for {metadata.sector}")
        
        # Place order using Phase 1 SDK (internal token resolution)
        order_side = OrderSide.BUY if position_type == PositionType.LONG else OrderSide.SELL
        order_type = OrderType.MARKET if entry_price is None else OrderType.LIMIT
        
        try:
            order = await self.order_client.create_order(
                instrument_key=instrument_key,
                side=order_side,
                quantity=quantity,
                order_type=order_type,
                price=entry_price
            )
            
            # Create position record
            position = StrategyPosition(
                instrument_key=instrument_key,
                symbol=metadata.symbol,
                exchange=metadata.exchange,
                sector=metadata.sector or "Unknown",
                position_type=position_type,
                quantity=quantity,
                entry_price=entry_price or order.price or 0.0,
                current_price=entry_price or order.price or 0.0,
                unrealized_pnl=0.0,
                _broker_orders=[order.order_id]
            )
            
            # Add to strategy positions
            self._strategy_positions[strategy_id].append(position)
            
            logger.info(f"Position opened: {strategy_id} - {instrument_key} ({metadata.symbol}) {position_type.value} {quantity}")
            
            return {
                "strategy_id": strategy_id,
                "position_id": f"{strategy_id}_{instrument_key}",
                "instrument_key": instrument_key,
                "instrument_metadata": {
                    "symbol": metadata.symbol,
                    "exchange": metadata.exchange,
                    "sector": metadata.sector,
                    "instrument_type": metadata.instrument_type
                },
                "position_type": position_type.value,
                "quantity": quantity,
                "entry_price": position.entry_price,
                "order_id": order.order_id,
                "timestamp": datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Position opening failed: {strategy_id} - {instrument_key} - {e}")
            raise RuntimeError(f"Position opening failed: {e}")
    
    async def close_position(self, strategy_id: str, instrument_key: str) -> Dict[str, Any]:
        """
        Close strategy position by instrument_key
        
        Args:
            strategy_id: Strategy identifier
            instrument_key: Position to close
            
        Returns:
            Dict: Position closure result
        """
        return await self._close_position(strategy_id, instrument_key)
    
    async def _close_position(self, strategy_id: str, instrument_key: str) -> Dict[str, Any]:
        """Internal position closure implementation"""
        positions = self._strategy_positions.get(strategy_id, [])
        position = next((p for p in positions if p.instrument_key == instrument_key), None)
        
        if not position:
            raise ValueError(f"Position not found: {strategy_id} - {instrument_key}")
        
        # Place closing order
        closing_side = OrderSide.SELL if position.position_type == PositionType.LONG else OrderSide.BUY
        
        try:
            closing_order = await self.order_client.create_order(
                instrument_key=instrument_key,
                side=closing_side,
                quantity=abs(position.quantity),
                order_type=OrderType.MARKET
            )
            
            # Calculate realized PnL
            exit_price = closing_order.price or position.current_price
            if position.position_type == PositionType.LONG:
                pnl = (exit_price - position.entry_price) * position.quantity
            else:
                pnl = (position.entry_price - exit_price) * position.quantity
            
            position.realized_pnl = pnl
            position.quantity = 0  # Position closed
            position.last_update = datetime.now()
            
            # Update strategy performance
            await self._update_strategy_performance(strategy_id, pnl, position)
            
            logger.info(f"Position closed: {strategy_id} - {instrument_key} ({position.symbol}) PnL: {pnl:.2f}")
            
            return {
                "strategy_id": strategy_id,
                "instrument_key": instrument_key,
                "symbol": position.symbol,
                "exchange": position.exchange,
                "realized_pnl": pnl,
                "exit_price": exit_price,
                "closing_order_id": closing_order.order_id,
                "closed_at": datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Position closing failed: {strategy_id} - {instrument_key} - {e}")
            raise RuntimeError(f"Position closing failed: {e}")
    
    # =============================================================================
    # PERFORMANCE ANALYTICS (metadata-enriched)
    # =============================================================================
    
    async def get_strategy_performance(self, strategy_id: str) -> Dict[str, Any]:
        """
        Get strategy performance with metadata-enriched analytics
        
        Args:
            strategy_id: Strategy identifier
            
        Returns:
            Dict: Performance metrics with sector/exchange breakdowns
        """
        if strategy_id not in self._strategy_performance:
            raise ValueError(f"Strategy not found: {strategy_id}")
        
        performance = self._strategy_performance[strategy_id]
        positions = self._strategy_positions.get(strategy_id, [])
        
        # Update unrealized PnL for open positions
        for position in positions:
            if position.quantity != 0:
                # In real implementation, get current market price
                # For now, simulate some price movement
                import random
                current_price = position.entry_price * (1 + random.uniform(-0.05, 0.05))
                position.current_price = current_price
                
                if position.position_type == PositionType.LONG:
                    position.unrealized_pnl = (current_price - position.entry_price) * position.quantity
                else:
                    position.unrealized_pnl = (position.entry_price - current_price) * position.quantity
        
        return {
            "strategy_id": strategy_id,
            "overall_performance": {
                "total_pnl": performance.total_pnl + sum(p.unrealized_pnl for p in positions),
                "realized_pnl": performance.total_pnl,
                "unrealized_pnl": sum(p.unrealized_pnl for p in positions),
                "win_rate": performance.win_rate,
                "max_drawdown": performance.max_drawdown,
                "sharpe_ratio": performance.sharpe_ratio,
                "total_trades": performance.total_trades
            },
            "metadata_analytics": {
                "performance_by_sector": performance.performance_by_sector,
                "performance_by_exchange": performance.performance_by_exchange,
                "top_performing_instruments": performance.top_performing_instruments
            },
            "current_positions": [
                {
                    "instrument_key": pos.instrument_key,
                    "symbol": pos.symbol,
                    "exchange": pos.exchange,
                    "sector": pos.sector,
                    "position_type": pos.position_type.value,
                    "quantity": pos.quantity,
                    "unrealized_pnl": pos.unrealized_pnl,
                    "entry_price": pos.entry_price,
                    "current_price": pos.current_price
                }
                for pos in positions if pos.quantity != 0
            ],
            "timestamp": datetime.now().isoformat()
        }
    
    async def _update_strategy_performance(self, 
                                         strategy_id: str, 
                                         trade_pnl: float, 
                                         position: StrategyPosition):
        """Update strategy performance metrics with metadata analytics"""
        performance = self._strategy_performance[strategy_id]
        
        # Update overall metrics
        performance.total_pnl += trade_pnl
        performance.total_trades += 1
        
        if trade_pnl > 0:
            performance.winning_trades += 1
        else:
            performance.losing_trades += 1
        
        performance.win_rate = performance.winning_trades / performance.total_trades
        
        # Update sector-based analytics
        sector = position.sector
        if sector not in performance.performance_by_sector:
            performance.performance_by_sector[sector] = {
                "total_pnl": 0.0, "trades": 0, "win_rate": 0.0
            }
        
        sector_perf = performance.performance_by_sector[sector]
        sector_perf["total_pnl"] += trade_pnl
        sector_perf["trades"] += 1
        if trade_pnl > 0:
            sector_perf["win_rate"] = (sector_perf.get("wins", 0) + 1) / sector_perf["trades"]
            sector_perf["wins"] = sector_perf.get("wins", 0) + 1
        
        # Update exchange-based analytics
        exchange = position.exchange
        if exchange not in performance.performance_by_exchange:
            performance.performance_by_exchange[exchange] = {
                "total_pnl": 0.0, "trades": 0, "win_rate": 0.0
            }
        
        exchange_perf = performance.performance_by_exchange[exchange]
        exchange_perf["total_pnl"] += trade_pnl
        exchange_perf["trades"] += 1
    
    # =============================================================================
    # STRATEGY STATUS AND MONITORING
    # =============================================================================
    
    async def get_active_strategies(self) -> Dict[str, Any]:
        """Get all active strategies with enriched information"""
        active_strategies = []
        
        for strategy_id, config in self._active_strategies.items():
            status = self._strategy_status.get(strategy_id, StrategyStatus.INACTIVE)
            positions = self._strategy_positions.get(strategy_id, [])
            performance = self._strategy_performance.get(strategy_id)
            
            # Get enriched instrument information for target instruments
            enriched_instruments = []
            for instrument_key in config.target_instruments[:5]:  # Limit for performance
                try:
                    metadata = await self.instrument_client.get_instrument_metadata(instrument_key)
                    enriched_instruments.append({
                        "instrument_key": instrument_key,
                        "symbol": metadata.symbol,
                        "exchange": metadata.exchange,
                        "sector": metadata.sector
                    })
                except:
                    enriched_instruments.append({
                        "instrument_key": instrument_key,
                        "symbol": "Unknown",
                        "exchange": "Unknown",
                        "sector": "Unknown"
                    })
            
            active_strategies.append({
                "strategy_id": strategy_id,
                "name": config.name,
                "status": status.value,
                "target_instruments": enriched_instruments,
                "active_positions": len([p for p in positions if p.quantity != 0]),
                "total_pnl": performance.total_pnl if performance else 0.0,
                "win_rate": performance.win_rate if performance else 0.0
            })
        
        return {
            "active_strategies": active_strategies,
            "total_strategies": len(active_strategies),
            "timestamp": datetime.now().isoformat()
        }