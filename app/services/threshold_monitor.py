# Threshold Monitor Service - Core monitoring engine for signal_service
import asyncio
import json
import time
from typing import Dict, List, Optional, Any, Callable
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict
from enum import Enum

from app.utils.logging_config import get_logger
from app.utils.redis import get_redis_client

# Import metrics
from ..metrics.threshold_metrics import get_metrics_collector

from .dynamic_indicator_classifier import (
    DynamicIndicatorClassifier,
    AdaptiveLearningEngine,
    CustomIndicatorAnalyzer,
    RealTimeAdaptationEngine,
    IndicatorClassificationContext,
    MonitoringStrategy,
    MonitoringTier,
    ThresholdBreach,
    UserAction,
    UserIntent,
    FinancialImpact,
    TimeSensitivity,
    IndicatorType,
    ComputationComplexity
)

logger = get_logger(__name__)


class ThresholdType(Enum):
    """Types of threshold monitoring"""
    GREATER_THAN = "gt"
    LESS_THAN = "lt"
    EQUALS = "eq"
    BETWEEN = "between"
    OUTSIDE = "outside"
    PERCENTAGE_CHANGE = "pct_change"
    MOVING_AVERAGE_CROSS = "ma_cross"
    CUSTOM_FUNCTION = "custom"


class AlertChannel(Enum):
    """Alert delivery channels"""
    UI = "ui"
    TELEGRAM = "telegram"
    EMAIL = "email"
    WEBHOOK = "webhook"
    EXECUTION_ENGINE = "execution_engine"


@dataclass
class ThresholdConfig:
    """Configuration for a threshold to monitor"""
    threshold_id: str
    user_id: str
    strategy_id: str
    
    # Indicator details
    indicator_name: str
    indicator_params: Dict[str, Any]
    symbol: str
    timeframe: str
    
    # Threshold specification
    threshold_type: ThresholdType
    threshold_value: float
    secondary_value: Optional[float] = None  # For BETWEEN/OUTSIDE
    
    # Classification context
    user_priority: UserIntent
    financial_impact: FinancialImpact
    time_sensitivity: TimeSensitivity
    position_size: float = 0.0
    portfolio_percentage: float = 0.0
    
    # Alert configuration
    alert_channels: List[AlertChannel] = None
    alert_message: str = ""
    cooldown_minutes: int = 5
    
    # Monitoring metadata
    created_at: datetime = None
    last_triggered: Optional[datetime] = None
    trigger_count: int = 0
    is_active: bool = True
    
    def __post_init__(self):
        if self.alert_channels is None:
            self.alert_channels = [AlertChannel.UI]
        if self.created_at is None:
            self.created_at = datetime.utcnow()


@dataclass
class MonitoringJob:
    """Monitoring job created from threshold config and strategy"""
    threshold_config: ThresholdConfig
    monitoring_strategy: MonitoringStrategy
    
    # Job control
    is_running: bool = False
    last_check: Optional[datetime] = None
    next_check: Optional[datetime] = None
    check_interval_seconds: int = 60
    
    # Performance tracking
    total_checks: int = 0
    breach_count: int = 0
    computation_time_ms: float = 0.0
    last_value: Optional[float] = None


class ThresholdMonitor:
    """
    Core monitoring engine with real-time and periodic modes.
    Integrates with DynamicIndicatorClassifier for intelligent resource allocation.
    """
    
    def __init__(self):
        self.redis = None
        self.classifier = DynamicIndicatorClassifier()
        self.learning_engine = AdaptiveLearningEngine(self.classifier)
        self.custom_analyzer = CustomIndicatorAnalyzer()
        self.adaptation_engine = RealTimeAdaptationEngine(self.classifier)
        
        # Monitoring state
        self.active_jobs: Dict[str, MonitoringJob] = {}
        self.real_time_jobs: Dict[str, MonitoringJob] = {}
        self.periodic_jobs: Dict[str, MonitoringJob] = {}
        self.on_demand_jobs: Dict[str, MonitoringJob] = {}
        
        # Custom indicators and functions
        self.custom_indicators: Dict[str, Callable] = {}
        self.builtin_indicators: Dict[str, Callable] = {}
        
        # Performance metrics
        self.metrics = {
            'total_thresholds': 0,
            'active_real_time': 0,
            'active_periodic': 0,
            'breaches_today': 0,
            'avg_computation_time': 0.0
        }
        
        # Prometheus metrics collector
        self.metrics_collector = get_metrics_collector()
        
        self.running = False
        
    async def initialize(self):
        """Initialize the threshold monitor"""
        self.redis = await get_redis_client()
        
        # Initialize classification system
        await self.classifier.initialize()
        await self.learning_engine.initialize()
        await self.adaptation_engine.initialize()
        
        # Register builtin indicators
        self._register_builtin_indicators()
        
        logger.info("ThresholdMonitor initialized")
    
    async def start_monitoring(self):
        """Start the threshold monitoring engine"""
        if self.running:
            logger.warning("ThresholdMonitor already running")
            return
        
        self.running = True
        
        # Start background tasks
        asyncio.create_task(self._real_time_monitoring_loop())
        asyncio.create_task(self._periodic_monitoring_loop())
        asyncio.create_task(self._performance_tracking_loop())
        
        # Start adaptation engine
        await self.adaptation_engine.start_monitoring()
        
        logger.info("ThresholdMonitor started")
    
    async def stop_monitoring(self):
        """Stop the threshold monitoring engine"""
        self.running = False
        await self.adaptation_engine.stop_monitoring()
        logger.info("ThresholdMonitor stopped")
    
    async def add_threshold(self, threshold_config: ThresholdConfig) -> str:
        """
        Add a new threshold to monitor.
        Returns the monitoring job ID.
        """
        
        # Create classification context
        context = self._create_classification_context(threshold_config)
        
        # Get monitoring strategy from classifier
        monitoring_strategy = self.classifier.classify_indicator(context)
        
        # Create monitoring job
        job = MonitoringJob(
            threshold_config=threshold_config,
            monitoring_strategy=monitoring_strategy
        )
        
        # Set check interval based on strategy
        job.check_interval_seconds = self._strategy_to_interval(monitoring_strategy)
        
        # Add to appropriate monitoring tier
        job_id = f"{threshold_config.threshold_id}_{int(time.time())}"
        self.active_jobs[job_id] = job
        
        if monitoring_strategy.tier == MonitoringTier.REAL_TIME:
            self.real_time_jobs[job_id] = job
            logger.info(f"Added real-time threshold: {threshold_config.indicator_name} for {threshold_config.symbol}")
        elif monitoring_strategy.tier == MonitoringTier.HIGH_FREQUENCY_PERIODIC:
            self.periodic_jobs[job_id] = job
            logger.info(f"Added high-frequency periodic threshold: {threshold_config.indicator_name}")
        elif monitoring_strategy.tier == MonitoringTier.PERIODIC:
            self.periodic_jobs[job_id] = job
            logger.info(f"Added periodic threshold: {threshold_config.indicator_name}")
        else:  # ON_DEMAND
            self.on_demand_jobs[job_id] = job
            logger.info(f"Added on-demand threshold: {threshold_config.indicator_name}")
        
        # Update metrics
        self.metrics['total_thresholds'] += 1
        if monitoring_strategy.tier == MonitoringTier.REAL_TIME:
            self.metrics['active_real_time'] += 1
        else:
            self.metrics['active_periodic'] += 1
        
        # Record Prometheus metrics
        self.metrics_collector.record_threshold_added(
            threshold_config.user_id,
            threshold_config.indicator_name,
            threshold_config.user_priority.value,
            [ch.value for ch in threshold_config.alert_channels]
        )
        
        self.metrics_collector.update_active_thresholds(
            monitoring_strategy.tier.value,
            threshold_config.user_priority.value,
            len(self.active_jobs)
        )
        
        # Save to Redis for persistence
        await self._save_threshold_config(job_id, threshold_config)
        
        return job_id
    
    async def remove_threshold(self, job_id: str) -> bool:
        """Remove a threshold from monitoring"""
        
        if job_id not in self.active_jobs:
            return False
        
        job = self.active_jobs[job_id]
        
        # Remove from tier-specific collections
        self.real_time_jobs.pop(job_id, None)
        self.periodic_jobs.pop(job_id, None)
        self.on_demand_jobs.pop(job_id, None)
        
        # Remove from active jobs
        del self.active_jobs[job_id]
        
        # Update metrics
        self.metrics['total_thresholds'] -= 1
        if job.monitoring_strategy.tier == MonitoringTier.REAL_TIME:
            self.metrics['active_real_time'] -= 1
        else:
            self.metrics['active_periodic'] -= 1
        
        # Remove from Redis
        await self.redis.delete(f"threshold_config:{job_id}")
        
        logger.info(f"Removed threshold: {job_id}")
        return True
    
    async def check_threshold_on_demand(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Check a specific threshold on-demand"""
        
        if job_id not in self.active_jobs:
            return None
        
        job = self.active_jobs[job_id]
        return await self._check_single_threshold(job_id, job)
    
    async def register_custom_indicator(self, name: str, function: Callable):
        """Register a custom indicator function"""
        
        # Analyze the custom function
        function_code = function.__code__.co_code if hasattr(function, '__code__') else ""
        profile = await self.custom_analyzer.analyze_custom_script(
            str(function_code), 
            {'name': name}
        )
        
        self.custom_indicators[name] = function
        logger.info(f"Registered custom indicator: {name} (complexity: {profile.complexity.value})")
    
    async def _real_time_monitoring_loop(self):
        """Main loop for real-time threshold monitoring"""
        
        while self.running:
            try:
                # Check all real-time thresholds
                tasks = []
                for job_id, job in self.real_time_jobs.items():
                    if job.is_running:
                        continue
                    
                    task = self._check_single_threshold(job_id, job)
                    tasks.append(task)
                
                if tasks:
                    await asyncio.gather(*tasks, return_exceptions=True)
                
                # Short sleep for real-time monitoring
                await asyncio.sleep(0.1)  # 100ms
                
            except Exception as e:
                logger.error(f"Real-time monitoring loop error: {e}")
                await asyncio.sleep(1)
    
    async def _periodic_monitoring_loop(self):
        """Main loop for periodic threshold monitoring"""
        
        while self.running:
            try:
                current_time = datetime.utcnow()
                
                # Check periodic thresholds that are due
                tasks = []
                for job_id, job in self.periodic_jobs.items():
                    if job.is_running:
                        continue
                    
                    # Check if it's time for next check
                    if (job.next_check is None or 
                        current_time >= job.next_check):
                        
                        task = self._check_single_threshold(job_id, job)
                        tasks.append(task)
                
                if tasks:
                    await asyncio.gather(*tasks, return_exceptions=True)
                
                # Sleep for periodic monitoring
                await asyncio.sleep(1)  # 1 second
                
            except Exception as e:
                logger.error(f"Periodic monitoring loop error: {e}")
                await asyncio.sleep(5)
    
    async def _check_single_threshold(self, job_id: str, job: MonitoringJob) -> Optional[Dict[str, Any]]:
        """Check a single threshold and trigger alerts if needed"""
        
        job.is_running = True
        start_time = time.time()
        
        try:
            threshold_config = job.threshold_config
            
            # Get current indicator value
            current_value = await self._compute_indicator_value(
                threshold_config.indicator_name,
                threshold_config.indicator_params,
                threshold_config.symbol,
                threshold_config.timeframe
            )
            
            if current_value is None:
                logger.warning(f"Could not compute indicator {threshold_config.indicator_name} for {threshold_config.symbol}")
                return None
            
            # Check threshold condition
            breach_detected = self._evaluate_threshold_condition(
                current_value,
                threshold_config.threshold_type,
                threshold_config.threshold_value,
                threshold_config.secondary_value
            )
            
            # Update job tracking
            job.last_check = datetime.utcnow()
            job.next_check = job.last_check + timedelta(seconds=job.check_interval_seconds)
            job.total_checks += 1
            job.last_value = current_value
            
            computation_time = (time.time() - start_time) * 1000
            job.computation_time_ms = computation_time
            
            result = {
                'job_id': job_id,
                'threshold_id': threshold_config.threshold_id,
                'symbol': threshold_config.symbol,
                'indicator': threshold_config.indicator_name,
                'current_value': current_value,
                'threshold_value': threshold_config.threshold_value,
                'breach_detected': breach_detected,
                'computation_time_ms': computation_time,
                'timestamp': datetime.utcnow().isoformat()
            }
            
            # Handle breach
            if breach_detected:
                await self._handle_threshold_breach(job_id, job, current_value)
                job.breach_count += 1
                self.metrics['breaches_today'] += 1
                result['breach_handled'] = True
                
                # Record Prometheus metrics for breach
                self.metrics_collector.record_threshold_breach(
                    threshold_config.user_id,
                    threshold_config.indicator_name,
                    threshold_config.symbol,
                    threshold_config.user_priority.value
                )
            
            # Record Prometheus metrics for check
            self.metrics_collector.record_threshold_check(
                threshold_config.indicator_name,
                job.monitoring_strategy.tier.value,
                threshold_config.symbol,
                computation_time
            )
            
            return result
            
        except Exception as e:
            logger.error(f"Error checking threshold {job_id}: {e}")
            return None
        finally:
            job.is_running = False
    
    async def _compute_indicator_value(
        self, 
        indicator_name: str, 
        params: Dict[str, Any], 
        symbol: str, 
        timeframe: str
    ) -> Optional[float]:
        """Compute the current value of an indicator"""
        
        try:
            # Check if it's a builtin indicator
            if indicator_name in self.builtin_indicators:
                indicator_func = self.builtin_indicators[indicator_name]
                return await self._compute_builtin_indicator(indicator_func, params, symbol, timeframe)
            
            # Check if it's a custom indicator
            elif indicator_name in self.custom_indicators:
                indicator_func = self.custom_indicators[indicator_name]
                return await self._compute_custom_indicator(indicator_func, params, symbol, timeframe)
            
            else:
                logger.error(f"Unknown indicator: {indicator_name}")
                return None
                
        except Exception as e:
            logger.error(f"Error computing indicator {indicator_name}: {e}")
            return None
    
    async def _compute_builtin_indicator(
        self, 
        indicator_func: Callable, 
        params: Dict[str, Any], 
        symbol: str, 
        timeframe: str
    ) -> Optional[float]:
        """Compute a builtin indicator value"""
        
        # Get market data
        market_data = await self._get_market_data(symbol, timeframe, params.get('lookback', 20))
        
        if not market_data:
            return None
        
        # Call the indicator function
        try:
            result = indicator_func(market_data, **params)
            return float(result) if result is not None else None
        except Exception as e:
            logger.error(f"Builtin indicator computation error: {e}")
            return None
    
    async def _compute_custom_indicator(
        self, 
        indicator_func: Callable, 
        params: Dict[str, Any], 
        symbol: str, 
        timeframe: str
    ) -> Optional[float]:
        """Compute a custom indicator value"""
        
        # Get market data
        market_data = await self._get_market_data(symbol, timeframe, params.get('lookback', 20))
        
        if not market_data:
            return None
        
        # Call the custom function
        try:
            result = await asyncio.to_thread(indicator_func, market_data, **params)
            return float(result) if result is not None else None
        except Exception as e:
            logger.error(f"Custom indicator computation error: {e}")
            return None
    
    async def _get_market_data(self, symbol: str, timeframe: str, lookback: int) -> Optional[Dict[str, Any]]:
        """Get market data for indicator computation"""
        
        try:
            # Check if data is available in Redis (real-time)
            tick_data = await self.redis.get(f"tick:{symbol}")
            if tick_data:
                data = json.loads(tick_data)
                return {
                    'symbol': symbol,
                    'ltp': data.get('ltp', 0),
                    'volume': data.get('volume', 0),
                    'timestamp': data.get('timestamp'),
                    'timeframe': timeframe
                }
            
            # Fallback to historical data or option chain API
            # This would integrate with ticker_service option chain API
            logger.debug(f"No real-time data for {symbol}, would use option chain API")
            return None
            
        except Exception as e:
            logger.error(f"Error getting market data for {symbol}: {e}")
            return None
    
    def _evaluate_threshold_condition(
        self, 
        current_value: float, 
        threshold_type: ThresholdType, 
        threshold_value: float, 
        secondary_value: Optional[float]
    ) -> bool:
        """Evaluate if threshold condition is met"""
        
        if threshold_type == ThresholdType.GREATER_THAN:
            return current_value > threshold_value
        elif threshold_type == ThresholdType.LESS_THAN:
            return current_value < threshold_value
        elif threshold_type == ThresholdType.EQUALS:
            # Use small epsilon for floating point comparison
            epsilon = abs(threshold_value) * 0.001  # 0.1% tolerance
            return abs(current_value - threshold_value) <= epsilon
        elif threshold_type == ThresholdType.BETWEEN:
            if secondary_value is None:
                return False
            return min(threshold_value, secondary_value) <= current_value <= max(threshold_value, secondary_value)
        elif threshold_type == ThresholdType.OUTSIDE:
            if secondary_value is None:
                return False
            return current_value < min(threshold_value, secondary_value) or current_value > max(threshold_value, secondary_value)
        else:
            # For complex conditions, would need custom evaluation
            return False
    
    async def _handle_threshold_breach(self, job_id: str, job: MonitoringJob, current_value: float):
        """Handle a threshold breach by sending alerts"""
        
        threshold_config = job.threshold_config
        
        # Check cooldown period
        if (threshold_config.last_triggered and 
            datetime.utcnow() - threshold_config.last_triggered < timedelta(minutes=threshold_config.cooldown_minutes)):
            logger.debug(f"Threshold {job_id} in cooldown period")
            return
        
        # Create breach event
        breach = ThresholdBreach(
            user_id=threshold_config.user_id,
            indicator=threshold_config.indicator_name,
            threshold_value=threshold_config.threshold_value,
            actual_value=current_value,
            market_context={
                'symbol': threshold_config.symbol,
                'timeframe': threshold_config.timeframe,
                'strategy_id': threshold_config.strategy_id
            },
            timestamp=datetime.utcnow()
        )
        
        # Send alerts through configured channels
        for channel in threshold_config.alert_channels:
            await self._send_alert(channel, breach, threshold_config)
        
        # Update threshold config
        threshold_config.last_triggered = datetime.utcnow()
        threshold_config.trigger_count += 1
        
        # Save updated config
        await self._save_threshold_config(job_id, threshold_config)
        
        # Log breach for learning
        await self._log_breach_for_learning(breach)
        
        logger.info(f"Threshold breach handled: {threshold_config.indicator_name} = {current_value} (threshold: {threshold_config.threshold_value})")
    
    async def _send_alert(self, channel: AlertChannel, breach: ThresholdBreach, config: ThresholdConfig):
        """Send alert through specified channel"""
        
        alert_data = {
            'breach': asdict(breach),
            'config': {
                'threshold_id': config.threshold_id,
                'symbol': config.symbol,
                'indicator': config.indicator_name,
                'threshold_value': config.threshold_value,
                'message': config.alert_message
            },
            'timestamp': datetime.utcnow().isoformat()
        }
        
        try:
            # CONSOLIDATED: Route all alerts through SignalDeliveryService
            from app.services.signal_delivery_service import get_signal_delivery_service
            
            delivery_service = get_signal_delivery_service()
            
            # Transform threshold alert to signal delivery format
            signal_data = {
                "signal_type": "threshold_alert",
                "alert_type": channel.value,
                "threshold_id": alert_data['threshold_id'],
                "user_id": alert_data['user_id'],
                "strategy_id": alert_data.get('strategy_id'),
                "breach": alert_data['breach'],
                "timestamp": alert_data['timestamp']
            }
            
            # Map channel-specific delivery config
            delivery_config = {
                "channels": [channel.value],
                "message": config.alert_message or f"Threshold breach: {config.indicator_name}",
                "priority": self._get_alert_priority(config),
                "metadata": {
                    "threshold_type": config.threshold_type.value,
                    "symbol": config.symbol,
                    "indicator": config.indicator_name
                }
            }
            
            # Route through unified delivery service with entitlement checking
            result = await delivery_service.deliver_signal(
                user_id=config.user_id,
                signal_data=signal_data,
                delivery_config=delivery_config
            )
            
            if not result.get("success"):
                logger.error(f"SignalDeliveryService failed for {channel.value}: {result.get('error')}")
                # Fallback to direct Redis for critical system alerts
                if channel in [AlertChannel.UI, AlertChannel.EXECUTION_ENGINE]:
                    await self._fallback_redis_alert(channel, alert_data)
            
        except Exception as e:
            logger.error(f"Failed to send alert via SignalDeliveryService for {channel.value}: {e}")
            # Fallback to direct Redis for critical channels
            if channel in [AlertChannel.UI, AlertChannel.EXECUTION_ENGINE]:
                await self._fallback_redis_alert(channel, alert_data)
    
    def _get_alert_priority(self, config: ThresholdConfig) -> str:
        """Get alert priority based on threshold configuration"""
        if config.financial_impact == FinancialImpact.HIGH and config.time_sensitivity == TimeSensitivity.HIGH:
            return "critical"
        elif config.financial_impact == FinancialImpact.MEDIUM or config.time_sensitivity == TimeSensitivity.HIGH:
            return "high"
        elif config.financial_impact == FinancialImpact.LOW and config.time_sensitivity == TimeSensitivity.MEDIUM:
            return "medium"
        else:
            return "low"
    
    async def _fallback_redis_alert(self, channel: AlertChannel, alert_data: Dict[str, Any]):
        """Fallback to direct Redis for critical system alerts when SignalDeliveryService fails"""
        try:
            if channel == AlertChannel.UI:
                await self.redis.xadd("ui_alerts", alert_data)
            elif channel == AlertChannel.EXECUTION_ENGINE:
                await self.redis.xadd("execution_alerts", alert_data)
            
            logger.warning(f"Used Redis fallback for critical {channel.value} alert")
            
        except Exception as e:
            logger.error(f"Redis fallback also failed for {channel.value}: {e}")
    
    async def _log_breach_for_learning(self, breach: ThresholdBreach):
        """Log breach event for machine learning"""
        
        learning_data = {
            'breach': asdict(breach),
            'logged_at': datetime.utcnow().isoformat()
        }
        
        try:
            await self.redis.xadd("threshold_breach_events", learning_data)
        except Exception as e:
            logger.error(f"Failed to log breach for learning: {e}")
    
    def _create_classification_context(self, threshold_config: ThresholdConfig) -> IndicatorClassificationContext:
        """Create classification context from threshold config"""
        
        # Determine indicator type
        indicator_type = IndicatorType.BUILTIN
        if threshold_config.indicator_name in self.custom_indicators:
            indicator_type = IndicatorType.CUSTOM_SCRIPT
        elif threshold_config.indicator_name not in self.builtin_indicators:
            indicator_type = IndicatorType.UNKNOWN
        
        # Estimate complexity (simplified)
        complexity = ComputationComplexity.MODERATE
        if threshold_config.indicator_name in ['rsi', 'sma', 'ema']:
            complexity = ComputationComplexity.SIMPLE
        elif threshold_config.indicator_name in ['macd', 'bollinger_bands']:
            complexity = ComputationComplexity.MODERATE
        
        return IndicatorClassificationContext(
            user_priority=threshold_config.user_priority,
            financial_impact=threshold_config.financial_impact,
            time_sensitivity=threshold_config.time_sensitivity,
            indicator_type=indicator_type,
            computation_complexity=complexity,
            data_dependencies=['ohlc'],  # Simplified
            required_frequency='1m',  # Default
            lookback_period=20,  # Default
            computation_time_ms=100.0,  # Default
            strategy_type='unknown',  # Would be derived from strategy_id
            position_size=threshold_config.position_size,
            portfolio_percentage=threshold_config.portfolio_percentage,
            underlying_type='stock',  # Simplified
            volatility_regime='normal',  # Would be computed
            market_hours=True,  # Simplified
            historical_breach_frequency=1.0,  # Default
            historical_action_rate=0.5,  # Default
            avg_response_time_required=5000.0  # 5 seconds default
        )
    
    def _strategy_to_interval(self, strategy: MonitoringStrategy) -> int:
        """Convert monitoring strategy to check interval in seconds"""
        
        if strategy.tier == MonitoringTier.REAL_TIME:
            return 1  # 1 second for real-time
        elif strategy.tier == MonitoringTier.HIGH_FREQUENCY_PERIODIC:
            # Parse frequency string
            if strategy.frequency:
                if strategy.frequency.endswith('s'):
                    return int(strategy.frequency[:-1])
                elif strategy.frequency.endswith('m'):
                    return int(strategy.frequency[:-1]) * 60
            return 30  # Default 30 seconds
        elif strategy.tier == MonitoringTier.PERIODIC:
            return 120  # 2 minutes
        else:  # ON_DEMAND
            return 3600  # 1 hour (not really used)
    
    async def _save_threshold_config(self, job_id: str, config: ThresholdConfig):
        """Save threshold configuration to Redis"""
        try:
            config_data = {
                'threshold_id': config.threshold_id,
                'user_id': config.user_id,
                'strategy_id': config.strategy_id,
                'indicator_name': config.indicator_name,
                'indicator_params': config.indicator_params,
                'symbol': config.symbol,
                'timeframe': config.timeframe,
                'threshold_type': config.threshold_type.value,
                'threshold_value': config.threshold_value,
                'secondary_value': config.secondary_value,
                'user_priority': config.user_priority.value,
                'financial_impact': config.financial_impact.value,
                'time_sensitivity': config.time_sensitivity.value,
                'position_size': config.position_size,
                'portfolio_percentage': config.portfolio_percentage,
                'alert_channels': [ch.value for ch in config.alert_channels],
                'alert_message': config.alert_message,
                'cooldown_minutes': config.cooldown_minutes,
                'created_at': config.created_at.isoformat(),
                'last_triggered': config.last_triggered.isoformat() if config.last_triggered else None,
                'trigger_count': config.trigger_count,
                'is_active': config.is_active
            }
            
            await self.redis.setex(
                f"threshold_config:{job_id}",
                86400,  # 24 hours TTL
                json.dumps(config_data)
            )
        except Exception as e:
            logger.error(f"Failed to save threshold config {job_id}: {e}")
    
    def _register_builtin_indicators(self):
        """Register builtin technical indicators"""
        
        # Simple Moving Average
        def sma(data: Dict[str, Any], period: int = 20) -> float:
            # Simplified implementation
            ltp = data.get('ltp', 0)
            return ltp  # Would use actual historical data
        
        # RSI
        def rsi(data: Dict[str, Any], period: int = 14) -> float:
            # Simplified implementation
            return 50.0  # Would compute actual RSI
        
        # MACD
        def macd(data: Dict[str, Any], fast: int = 12, slow: int = 26, signal: int = 9) -> float:
            # Simplified implementation
            return 0.0  # Would compute actual MACD
        
        self.builtin_indicators = {
            'sma': sma,
            'rsi': rsi,
            'macd': macd
        }
    
    async def _performance_tracking_loop(self):
        """Background task for performance tracking"""
        
        while self.running:
            try:
                # Update performance metrics
                total_computation_time = sum(job.computation_time_ms for job in self.active_jobs.values())
                total_checks = sum(job.total_checks for job in self.active_jobs.values())
                
                if total_checks > 0:
                    self.metrics['avg_computation_time'] = total_computation_time / total_checks
                
                # Save metrics to Redis
                await self.redis.setex(
                    "threshold_monitor_metrics",
                    300,  # 5 minutes TTL
                    json.dumps(self.metrics)
                )
                
                await asyncio.sleep(60)  # Update every minute
                
            except Exception as e:
                logger.error(f"Performance tracking error: {e}")
                await asyncio.sleep(60)
    
    async def get_monitoring_status(self) -> Dict[str, Any]:
        """Get current monitoring status and metrics"""
        
        return {
            'running': self.running,
            'metrics': self.metrics,
            'active_jobs': {
                'total': len(self.active_jobs),
                'real_time': len(self.real_time_jobs),
                'periodic': len(self.periodic_jobs),
                'on_demand': len(self.on_demand_jobs)
            },
            'timestamp': datetime.utcnow().isoformat()
        }