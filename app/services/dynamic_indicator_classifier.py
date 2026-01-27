# Dynamic Indicator Classification System for Signal Service
import asyncio
import json
import re
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any

from app.utils.logging_config import get_logger
from app.utils.redis import get_redis_client

logger = get_logger(__name__)


class MonitoringTier(Enum):
    """Monitoring tiers based on priority and resource allocation"""
    REAL_TIME = "real_time"           # <100ms latency, critical thresholds
    HIGH_FREQUENCY_PERIODIC = "high_frequency_periodic"  # 30s-2m, high priority
    PERIODIC = "periodic"             # 2-15m, medium priority
    ON_DEMAND = "on_demand"          # Only when requested, low priority


class UserIntent(Enum):
    """User intent categories for threshold classification"""
    STOP_LOSS = "stop_loss"
    PROFIT_TARGET = "profit_target"
    ENTRY_SIGNAL = "entry_signal"
    ANALYSIS = "analysis"
    RESEARCH = "research"


class FinancialImpact(Enum):
    """Financial impact levels"""
    HIGH = "high"      # >5% of portfolio
    MEDIUM = "medium"  # 1-5% of portfolio
    LOW = "low"        # <1% of portfolio


class TimeSensitivity(Enum):
    """Time sensitivity levels"""
    IMMEDIATE = "immediate"    # Real-time required
    NEAR_TERM = "near_term"    # Sub-minute required
    PERIODIC = "periodic"      # Minutes acceptable
    HISTORICAL = "historical"  # Hours/days acceptable


class IndicatorType(Enum):
    """Indicator types for complexity assessment"""
    BUILTIN = "builtin"           # Standard TA indicators
    CUSTOM_SCRIPT = "custom_script"  # User-defined code
    COMPOSITE = "composite"       # Multiple indicators combined
    UNKNOWN = "unknown"          # Cannot be classified


class ComputationComplexity(Enum):
    """Computation complexity levels"""
    SIMPLE = "simple"          # <10ms computation
    MODERATE = "moderate"      # 10-100ms computation
    COMPLEX = "complex"        # 100ms-1s computation
    VERY_COMPLEX = "very_complex"  # >1s computation


@dataclass
class IndicatorClassificationContext:
    """Complete context for indicator classification"""
    # User Intent Context
    user_priority: UserIntent
    financial_impact: FinancialImpact
    time_sensitivity: TimeSensitivity

    # Indicator Characteristics
    indicator_type: IndicatorType
    computation_complexity: ComputationComplexity
    data_dependencies: list[str]

    # Technical Requirements
    required_frequency: str  # 'tick', '1s', '30s', '1m', '5m', etc.
    lookback_period: int     # Days of historical data needed
    computation_time_ms: float  # Estimated computation time

    # Strategy Context
    strategy_type: str       # 'scalping', 'swing', 'options', 'arbitrage'
    position_size: float     # Financial exposure
    portfolio_percentage: float  # % of total portfolio

    # Market Context
    underlying_type: str     # 'index', 'stock', 'commodity', 'currency'
    volatility_regime: str   # 'low', 'normal', 'high', 'extreme'
    market_hours: bool

    # Performance Context (learning from history)
    historical_breach_frequency: float  # Breaches per day
    historical_action_rate: float       # % of breaches leading to action
    avg_response_time_required: float   # Seconds


@dataclass
class MonitoringStrategy:
    """Monitoring strategy determined by classification"""
    tier: MonitoringTier
    data_source: str         # 'real_time_stream', 'option_chain_api', 'batch_computation'
    frequency: str | None = None        # For periodic monitoring
    max_latency_ms: int = 5000
    resource_allocation: str = "medium"    # 'minimal', 'low', 'medium', 'high'
    fallback_strategy: str | None = None
    trigger: str | None = None          # For on-demand monitoring


@dataclass
class IndicatorProfile:
    """Profile of a custom indicator for resource prediction"""
    complexity: ComputationComplexity = ComputationComplexity.MODERATE
    data_dependencies: list[str] = None
    estimated_computation_time: float = 100.0  # milliseconds
    required_data_sources: list[str] = None
    lookback_period: int = 1  # days
    resource_intensity: str = "medium"

    def __post_init__(self):
        if self.data_dependencies is None:
            self.data_dependencies = []
        if self.required_data_sources is None:
            self.required_data_sources = []


@dataclass
class UserAction:
    """User action taken in response to threshold breach"""
    action_type: str        # 'trade', 'ignore', 'adjust_threshold'
    response_time_ms: float
    outcome: str           # 'profitable', 'loss', 'neutral'
    timestamp: datetime


@dataclass
class ThresholdBreach:
    """Threshold breach event"""
    user_id: str
    indicator: str
    threshold_value: float
    actual_value: float
    market_context: dict[str, Any]
    timestamp: datetime


class DynamicIndicatorClassifier:
    """
    Intelligent classifier that learns and adapts to assign monitoring priority
    """

    def __init__(self):
        self.redis = None
        self.performance_history = {}
        self.user_behavior_patterns = {}

    async def initialize(self):
        """Initialize Redis connection and load historical data"""
        self.redis = await get_redis_client()
        await self._load_performance_history()
        await self._load_user_behavior_patterns()
        logger.info("DynamicIndicatorClassifier initialized")

    def classify_indicator(self, context: IndicatorClassificationContext) -> MonitoringStrategy:
        """
        Dynamic classification based on multiple factors
        """

        # Base scoring (0-100)
        priority_score = 0

        # 1. USER INTENT WEIGHTING (40% of score)
        intent_weights = {
            UserIntent.STOP_LOSS: 40,        # Highest priority - financial protection
            UserIntent.PROFIT_TARGET: 35,    # High priority - profit protection
            UserIntent.ENTRY_SIGNAL: 25,     # Medium-high priority - opportunity capture
            UserIntent.ANALYSIS: 15,         # Medium priority - decision support
            UserIntent.RESEARCH: 5           # Low priority - knowledge gathering
        }
        priority_score += intent_weights.get(context.user_priority, 15)

        # 2. FINANCIAL IMPACT WEIGHTING (30% of score)
        if context.financial_impact == FinancialImpact.HIGH:
            priority_score += 30
        elif context.financial_impact == FinancialImpact.MEDIUM:
            priority_score += 20
        else:
            priority_score += 10

        # 3. TIME SENSITIVITY WEIGHTING (20% of score)
        time_weights = {
            TimeSensitivity.IMMEDIATE: 20,        # Real-time required
            TimeSensitivity.NEAR_TERM: 15,        # Sub-minute required
            TimeSensitivity.PERIODIC: 10,         # Minutes acceptable
            TimeSensitivity.HISTORICAL: 5         # Hours/days acceptable
        }
        priority_score += time_weights.get(context.time_sensitivity, 10)

        # 4. COMPLEXITY/COST ADJUSTMENT (10% of score)
        complexity_penalty = {
            ComputationComplexity.SIMPLE: 0,            # No penalty
            ComputationComplexity.MODERATE: -5,         # Small penalty
            ComputationComplexity.COMPLEX: -10,         # Medium penalty
            ComputationComplexity.VERY_COMPLEX: -15     # High penalty
        }
        priority_score += complexity_penalty.get(context.computation_complexity, -5)

        # 5. HISTORICAL PERFORMANCE BONUS (bonus points)
        if context.historical_action_rate > 0.7:  # 70% of breaches lead to action
            priority_score += 10  # Proven important
        elif context.historical_action_rate < 0.1:  # <10% lead to action
            priority_score -= 10  # Proven less important

        # 6. MARKET CONDITIONS ADJUSTMENT
        if context.volatility_regime == 'extreme':
            priority_score += 5  # Everything becomes more important
        elif context.volatility_regime == 'low':
            priority_score -= 3  # Less urgent in calm markets

        # 7. PORTFOLIO PERCENTAGE ADJUSTMENT
        if context.portfolio_percentage > 10:  # >10% of portfolio
            priority_score += 8
        elif context.portfolio_percentage > 5:  # >5% of portfolio
            priority_score += 5
        elif context.portfolio_percentage < 0.5:  # <0.5% of portfolio
            priority_score -= 5

        # Determine monitoring strategy based on final score
        return self._score_to_strategy(priority_score, context)

    def _score_to_strategy(self, score: int, context: IndicatorClassificationContext) -> MonitoringStrategy:
        """Convert priority score to concrete monitoring strategy"""

        if score >= 70:
            # CRITICAL: Real-time monitoring required
            return MonitoringStrategy(
                tier=MonitoringTier.REAL_TIME,
                data_source='real_time_stream',
                max_latency_ms=100,
                resource_allocation='high',
                fallback_strategy='degrade_other_monitoring'
            )

        if score >= 50:
            # HIGH: Fast periodic monitoring
            frequency = self._determine_optimal_frequency(context)
            return MonitoringStrategy(
                tier=MonitoringTier.HIGH_FREQUENCY_PERIODIC,
                data_source='option_chain_api',
                frequency=frequency,
                max_latency_ms=5000,
                resource_allocation='medium'
            )

        if score >= 30:
            # MEDIUM: Regular periodic monitoring
            return MonitoringStrategy(
                tier=MonitoringTier.PERIODIC,
                data_source='option_chain_api',
                frequency='2m',
                max_latency_ms=30000,
                resource_allocation='low'
            )

        # LOW: On-demand or batch processing
        return MonitoringStrategy(
            tier=MonitoringTier.ON_DEMAND,
            data_source='batch_computation',
            trigger='user_request',
            resource_allocation='minimal'
        )

    def _determine_optimal_frequency(self, context: IndicatorClassificationContext) -> str:
        """Dynamically determine monitoring frequency based on multiple factors"""

        # Base frequency from user requirements
        base_freq = context.required_frequency

        # Adjust based on indicator type
        if context.indicator_type == IndicatorType.CUSTOM_SCRIPT and context.computation_time_ms > 1000:  # >1 second
            # Custom scripts might be expensive
            return self._reduce_frequency(base_freq, factor=2)

        # Adjust based on market conditions
        if context.volatility_regime == 'extreme':
            return self._increase_frequency(base_freq, factor=1.5)
        if context.volatility_regime == 'low':
            return self._reduce_frequency(base_freq, factor=1.5)

        # Adjust based on historical patterns
        if context.historical_breach_frequency > 10:  # >10 breaches per day
            return self._increase_frequency(base_freq, factor=2)
        if context.historical_breach_frequency < 1:  # <1 breach per day
            return self._reduce_frequency(base_freq, factor=3)

        return base_freq

    def _increase_frequency(self, frequency: str, factor: float) -> str:
        """Increase monitoring frequency by factor"""
        freq_seconds = self._parse_frequency_to_seconds(frequency)
        new_seconds = max(1, int(freq_seconds / factor))
        return self._seconds_to_frequency(new_seconds)

    def _reduce_frequency(self, frequency: str, factor: float) -> str:
        """Reduce monitoring frequency by factor"""
        freq_seconds = self._parse_frequency_to_seconds(frequency)
        new_seconds = int(freq_seconds * factor)
        return self._seconds_to_frequency(new_seconds)

    def _parse_frequency_to_seconds(self, frequency: str) -> int:
        """Parse frequency string to seconds"""
        if frequency == 'tick':
            return 1
        if frequency.endswith('s'):
            return int(frequency[:-1])
        if frequency.endswith('m'):
            return int(frequency[:-1]) * 60
        if frequency.endswith('h'):
            return int(frequency[:-1]) * 3600
        return 60  # Default to 1 minute

    def _seconds_to_frequency(self, seconds: int) -> str:
        """Convert seconds to frequency string"""
        if seconds < 60:
            return f"{seconds}s"
        if seconds < 3600:
            return f"{seconds // 60}m"
        return f"{seconds // 3600}h"

    async def _load_performance_history(self):
        """Load historical performance data from Redis"""
        try:
            data = await self.redis.get("indicator_performance_history")
            if data:
                self.performance_history = json.loads(data)
            logger.debug(f"Loaded performance history for {len(self.performance_history)} indicators")
        except Exception as e:
            logger.error(f"Failed to load performance history: {e}")
            self.performance_history = {}

    async def _save_performance_history(self):
        """Save performance history to Redis"""
        try:
            await self.redis.setex(
                "indicator_performance_history",
                86400,  # 24 hours TTL
                json.dumps(self.performance_history)
            )
        except Exception as e:
            logger.error(f"Failed to save performance history: {e}")

    async def _load_user_behavior_patterns(self):
        """Load user behavior patterns from Redis"""
        try:
            data = await self.redis.get("user_behavior_patterns")
            if data:
                self.user_behavior_patterns = json.loads(data)
            logger.debug(f"Loaded behavior patterns for {len(self.user_behavior_patterns)} users")
        except Exception as e:
            logger.error(f"Failed to load user behavior patterns: {e}")
            self.user_behavior_patterns = {}


class AdaptiveLearningEngine:
    """
    Learns from user behavior and market conditions to improve classification
    """

    def __init__(self, classifier: DynamicIndicatorClassifier):
        self.classifier = classifier
        self.redis = None

    async def initialize(self):
        """Initialize the learning engine"""
        self.redis = await get_redis_client()
        logger.info("AdaptiveLearningEngine initialized")

    async def learn_from_user_action(self, threshold_breach: ThresholdBreach, user_action: UserAction):
        """
        Learn from what users actually do when thresholds breach
        """

        learning_data = {
            'indicator': threshold_breach.indicator,
            'breach_context': threshold_breach.market_context,
            'user_response_time': user_action.response_time_ms,
            'action_type': user_action.action_type,
            'outcome': user_action.outcome,
            'timestamp': user_action.timestamp.isoformat()
        }

        # Update learning database
        await self._update_indicator_effectiveness(learning_data)
        await self._update_user_behavior_pattern(threshold_breach.user_id, learning_data)

        # Trigger reclassification if pattern changes significantly
        if self._significant_pattern_change(threshold_breach.indicator):
            await self._trigger_reclassification(threshold_breach.indicator)

    async def _update_indicator_effectiveness(self, learning_data: dict):
        """Update indicator effectiveness metrics"""

        indicator = learning_data['indicator']

        if indicator not in self.classifier.performance_history:
            self.classifier.performance_history[indicator] = {
                'total_breaches': 0,
                'actions_taken': 0,
                'profitable_actions': 0,
                'avg_response_time': 0,
                'effectiveness_score': 0.5  # Start neutral
            }

        history = self.classifier.performance_history[indicator]
        history['total_breaches'] += 1

        if learning_data['action_type'] != 'ignore':
            history['actions_taken'] += 1

            if learning_data['outcome'] == 'profitable':
                history['profitable_actions'] += 1

        # Calculate new effectiveness score
        action_rate = history['actions_taken'] / history['total_breaches']
        profitability_rate = history['profitable_actions'] / max(history['actions_taken'], 1)

        # Combined effectiveness (0.0 to 1.0)
        history['effectiveness_score'] = (action_rate * 0.6) + (profitability_rate * 0.4)

        # Save updated history
        await self.classifier._save_performance_history()

    async def _update_user_behavior_pattern(self, user_id: str, learning_data: dict):
        """Update user-specific behavior patterns"""

        if user_id not in self.classifier.user_behavior_patterns:
            self.classifier.user_behavior_patterns[user_id] = {
                'avg_response_time': 5000,  # 5 seconds default
                'preferred_indicators': {},
                'action_tendencies': {
                    'trade': 0.3,
                    'ignore': 0.5,
                    'adjust_threshold': 0.2
                },
                'success_rate': 0.5
            }

        pattern = self.classifier.user_behavior_patterns[user_id]

        # Update response time (exponential moving average)
        current_response = learning_data['user_response_time']
        pattern['avg_response_time'] = (pattern['avg_response_time'] * 0.8) + (current_response * 0.2)

        # Update action tendencies
        action_type = learning_data['action_type']
        total_actions = sum(pattern['action_tendencies'].values()) + 1
        for action, count in pattern['action_tendencies'].items():
            if action == action_type:
                pattern['action_tendencies'][action] = (count + 1) / total_actions
            else:
                pattern['action_tendencies'][action] = count / total_actions

    def _significant_pattern_change(self, indicator: str) -> bool:
        """Check if indicator patterns have changed significantly"""
        if indicator not in self.classifier.performance_history:
            return False

        history = self.classifier.performance_history[indicator]

        # Check if we have enough data points
        if history['total_breaches'] < 10:
            return False

        # Simple check: if effectiveness score changed by >20%
        return abs(history['effectiveness_score'] - 0.5) > 0.2

    async def _trigger_reclassification(self, indicator: str):
        """Trigger reclassification of an indicator"""
        reclassification_event = {
            'indicator': indicator,
            'reason': 'significant_pattern_change',
            'timestamp': datetime.utcnow().isoformat(),
            'action': 'reclassify'
        }

        try:
            await self.redis.xadd("indicator_reclassification_events", reclassification_event)
            logger.info(f"Triggered reclassification for indicator: {indicator}")
        except Exception as e:
            logger.error(f"Failed to trigger reclassification: {e}")


class CustomIndicatorAnalyzer:
    """
    Analyzes custom scripts to determine their resource requirements and characteristics
    """

    def __init__(self):
        self.analyzer_cache = {}

    async def analyze_custom_script(self, script_code: str, metadata: dict) -> IndicatorProfile:
        """
        Analyze custom script to determine monitoring requirements
        """

        profile = IndicatorProfile()

        # 1. STATIC CODE ANALYSIS
        profile.complexity = self._analyze_code_complexity(script_code)
        profile.data_dependencies = self._extract_data_dependencies(script_code)
        profile.estimated_computation_time = self._estimate_computation_time(script_code)

        # 2. DEPENDENCY ANALYSIS
        profile.required_data_sources = self._identify_required_data_sources(script_code)
        profile.lookback_period = self._extract_lookback_requirements(script_code)

        # 3. EXECUTION PROFILE LEARNING
        if metadata.get('execution_history'):
            profile = await self._learn_from_execution_history(profile, metadata['execution_history'])

        # 4. RESOURCE PREDICTION
        profile.resource_intensity = self._predict_resource_usage(profile)

        return profile

    def _analyze_code_complexity(self, script_code: str) -> ComputationComplexity:
        """Analyze code complexity using various metrics"""

        # Count loops, nested structures, function calls
        loop_count = script_code.count('for ') + script_code.count('while ')
        nested_count = script_code.count('    ') // 4  # Approximate nesting
        function_calls = len(re.findall(r'\w+\(', script_code))

        complexity_score = loop_count * 2 + nested_count + function_calls * 0.5

        if complexity_score > 20:
            return ComputationComplexity.VERY_COMPLEX
        if complexity_score > 10:
            return ComputationComplexity.COMPLEX
        if complexity_score > 5:
            return ComputationComplexity.MODERATE
        return ComputationComplexity.SIMPLE

    def _extract_data_dependencies(self, script_code: str) -> list[str]:
        """Extract what data the script needs"""

        dependencies = []

        # Common data access patterns
        patterns = {
            'ohlc': r'\b(open|high|low|close|volume)\b',
            'options': r'\b(strike|expiry|option_type|oi)\b',
            'greeks': r'\b(delta|gamma|theta|vega|rho|iv)\b',
            'technical': r'\b(sma|ema|rsi|macd|bollinger)\b'
        }

        for category, pattern in patterns.items():
            if re.search(pattern, script_code, re.IGNORECASE):
                dependencies.append(category)

        return dependencies

    def _estimate_computation_time(self, script_code: str) -> float:
        """Estimate computation time based on code complexity"""

        # Simple heuristic based on operations
        lines = len(script_code.split('\n'))
        loops = script_code.count('for ') + script_code.count('while ')

        # Base time: 1ms per line
        base_time = lines * 1.0

        # Loop penalty: 10ms per loop
        loop_penalty = loops * 10.0

        # Function call penalty
        function_calls = len(re.findall(r'\w+\(', script_code))
        function_penalty = function_calls * 2.0

        total_time = base_time + loop_penalty + function_penalty

        # Cap at reasonable limits
        return min(max(total_time, 10.0), 5000.0)  # 10ms to 5s

    def _identify_required_data_sources(self, script_code: str) -> list[str]:
        """Identify what data sources the script requires"""

        sources = []

        # Check for real-time data access
        if re.search(r'\b(tick|real_time|live)\b', script_code, re.IGNORECASE):
            sources.append('real_time_stream')

        # Check for historical data access
        if re.search(r'\b(history|historical|past)\b', script_code, re.IGNORECASE):
            sources.append('historical_data')

        # Check for option chain access
        if re.search(r'\b(option_chain|strikes|expiry)\b', script_code, re.IGNORECASE):
            sources.append('option_chain_api')

        return sources if sources else ['real_time_stream']  # Default

    def _extract_lookback_requirements(self, script_code: str) -> int:
        """Extract how much historical data is needed"""

        # Look for numeric patterns that might indicate lookback periods
        lookback_patterns = [
            r'(\d+)\s*days?',
            r'(\d+)\s*periods?',
            r'lookback\s*=\s*(\d+)',
            r'window\s*=\s*(\d+)'
        ]

        max_lookback = 1  # Default 1 day

        for pattern in lookback_patterns:
            matches = re.findall(pattern, script_code, re.IGNORECASE)
            if matches:
                for match in matches:
                    try:
                        value = int(match)
                        max_lookback = max(max_lookback, value)
                    except ValueError:
                        continue

        return min(max_lookback, 365)  # Cap at 1 year

    async def _learn_from_execution_history(self, profile: IndicatorProfile, execution_history: list[dict]) -> IndicatorProfile:
        """Learn from actual execution history"""

        if not execution_history:
            return profile

        # Calculate average execution time
        execution_times = [entry.get('execution_time_ms', 100) for entry in execution_history]
        if execution_times:
            profile.estimated_computation_time = sum(execution_times) / len(execution_times)

        # Adjust complexity based on actual performance
        avg_time = profile.estimated_computation_time
        if avg_time > 1000:
            profile.complexity = ComputationComplexity.VERY_COMPLEX
        elif avg_time > 100:
            profile.complexity = ComputationComplexity.COMPLEX
        elif avg_time > 10:
            profile.complexity = ComputationComplexity.MODERATE
        else:
            profile.complexity = ComputationComplexity.SIMPLE

        return profile

    def _predict_resource_usage(self, profile: IndicatorProfile) -> str:
        """Predict resource usage intensity"""

        score = 0

        # Complexity contribution
        complexity_scores = {
            ComputationComplexity.SIMPLE: 1,
            ComputationComplexity.MODERATE: 2,
            ComputationComplexity.COMPLEX: 3,
            ComputationComplexity.VERY_COMPLEX: 4
        }
        score += complexity_scores.get(profile.complexity, 2)

        # Data dependency contribution
        score += len(profile.data_dependencies)

        # Lookback period contribution
        if profile.lookback_period > 30:
            score += 2
        elif profile.lookback_period > 7:
            score += 1

        # Convert to resource intensity
        if score >= 7:
            return "very_high"
        if score >= 5:
            return "high"
        if score >= 3:
            return "medium"
        return "low"


class RealTimeAdaptationEngine:
    """
    Continuously adapts monitoring strategies based on real-time conditions
    """

    def __init__(self, classifier: DynamicIndicatorClassifier):
        self.classifier = classifier
        self.redis = None
        self.performance_metrics = {}
        self.running = False

    async def initialize(self):
        """Initialize the adaptation engine"""
        self.redis = await get_redis_client()
        logger.info("RealTimeAdaptationEngine initialized")

    async def start_monitoring(self):
        """Start the continuous adaptation monitoring"""
        self.running = True
        asyncio.create_task(self.monitor_and_adapt())
        logger.info("Real-time adaptation monitoring started")

    async def stop_monitoring(self):
        """Stop the continuous adaptation monitoring"""
        self.running = False
        logger.info("Real-time adaptation monitoring stopped")

    async def monitor_and_adapt(self):
        """
        Background task that continuously optimizes monitoring strategies
        """

        while self.running:
            try:
                # 1. Monitor current resource usage
                resource_usage = await self._get_current_resource_usage()

                # 2. Check if any strategies are underperforming
                underperforming = await self._identify_underperforming_strategies()

                # 3. Check if market conditions have changed
                market_change = await self._detect_market_regime_change()

                # 4. Adapt strategies based on findings
                if resource_usage.get('overall_utilization', 0) > 0.8:
                    await self._reduce_low_priority_monitoring()

                if underperforming:
                    await self._adjust_underperforming_strategies(underperforming)

                if market_change:
                    await self._adapt_to_market_conditions(market_change)

                await asyncio.sleep(60)  # Check every minute

            except Exception as e:
                logger.error(f"Adaptation engine error: {e}")
                await asyncio.sleep(300)  # Longer sleep on error

    async def _get_current_resource_usage(self) -> dict[str, Any]:
        """Get current resource usage metrics"""
        try:
            # This would integrate with subscription_service to get actual metrics
            usage_data = await self.redis.get("current_resource_usage")
            if usage_data:
                return json.loads(usage_data)

            # Default fallback
            return {"overall_utilization": 0.3}
        except Exception as e:
            logger.error(f"Failed to get resource usage: {e}")
            return {"overall_utilization": 0.3}

    async def _identify_underperforming_strategies(self) -> list[str]:
        """Identify strategies with low action rates"""
        underperforming = []

        for indicator_id, metrics in self.performance_metrics.items():
            action_rate = metrics.get('action_rate', 0.5)
            priority_score = metrics.get('priority_score', 50)

            if action_rate < 0.1 and priority_score < 40:
                underperforming.append(indicator_id)

        return underperforming

    async def _detect_market_regime_change(self) -> dict[str, Any] | None:
        """Detect significant market condition changes"""
        try:
            # This would integrate with market data to detect volatility changes
            market_data = await self.redis.get("market_conditions")
            if market_data:
                data = json.loads(market_data)
                # Simple volatility change detection
                if data.get('volatility_change_pct', 0) > 50:
                    return {"volatility_increase": data['volatility_change_pct'] / 100}
                if data.get('volatility_change_pct', 0) < -30:
                    return {"volatility_decrease": abs(data['volatility_change_pct']) / 100}

            return None
        except Exception as e:
            logger.error(f"Failed to detect market regime change: {e}")
            return None

    async def _reduce_low_priority_monitoring(self):
        """Reduce monitoring frequency for low-priority indicators"""

        # Find indicators with low action rates
        low_priority_indicators = []
        for indicator_id, metrics in self.performance_metrics.items():
            if metrics.get('action_rate', 0.5) < 0.1 and metrics.get('priority_score', 50) < 40:
                low_priority_indicators.append(indicator_id)

        # Reduce their monitoring frequency temporarily
        for indicator_id in low_priority_indicators:
            await self._temporarily_reduce_frequency(indicator_id, factor=2)

    async def _temporarily_reduce_frequency(self, indicator_id: str, factor: float):
        """Temporarily reduce monitoring frequency for an indicator"""
        try:
            reduction_event = {
                'indicator_id': indicator_id,
                'action': 'reduce_frequency',
                'factor': factor,
                'reason': 'resource_pressure',
                'timestamp': datetime.utcnow().isoformat()
            }

            await self.redis.xadd("monitoring_adjustments", reduction_event)
            logger.info(f"Temporarily reduced monitoring frequency for {indicator_id} by factor {factor}")
        except Exception as e:
            logger.error(f"Failed to reduce frequency for {indicator_id}: {e}")

    async def _adjust_underperforming_strategies(self, underperforming: list[str]):
        """Adjust monitoring for underperforming strategies"""
        for strategy_id in underperforming:
            await self._temporarily_reduce_frequency(strategy_id, factor=1.5)

    async def _adapt_to_market_conditions(self, market_change: dict[str, Any]):
        """Adapt monitoring based on market condition changes"""

        if market_change.get('volatility_increase', 0) > 0.5:  # 50% volatility increase
            # Increase monitoring frequency for all strategies
            await self._globally_increase_monitoring_frequency(factor=1.5)

        elif market_change.get('volatility_decrease', 0) > 0.3:  # 30% volatility decrease
            # Reduce monitoring frequency to save resources
            await self._globally_reduce_monitoring_frequency(factor=1.3)

    async def _globally_increase_monitoring_frequency(self, factor: float):
        """Globally increase monitoring frequency"""
        try:
            adjustment_event = {
                'action': 'global_increase_frequency',
                'factor': factor,
                'reason': 'volatility_increase',
                'timestamp': datetime.utcnow().isoformat()
            }

            await self.redis.xadd("global_monitoring_adjustments", adjustment_event)
            logger.info(f"Globally increased monitoring frequency by factor {factor}")
        except Exception as e:
            logger.error(f"Failed to globally increase frequency: {e}")

    async def _globally_reduce_monitoring_frequency(self, factor: float):
        """Globally reduce monitoring frequency"""
        try:
            adjustment_event = {
                'action': 'global_reduce_frequency',
                'factor': factor,
                'reason': 'volatility_decrease',
                'timestamp': datetime.utcnow().isoformat()
            }

            await self.redis.xadd("global_monitoring_adjustments", adjustment_event)
            logger.info(f"Globally reduced monitoring frequency by factor {factor}")
        except Exception as e:
            logger.error(f"Failed to globally reduce frequency: {e}")
