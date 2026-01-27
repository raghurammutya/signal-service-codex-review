"""
Production Backpressure Monitor for Signal Service
Monitors system load and provides deterministic scaling recommendations
"""
import logging
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class BackpressureLevel(Enum):
    """System backpressure levels"""
    LOW = 1
    MEDIUM = 2
    HIGH = 3
    CRITICAL = 4


@dataclass
class ScalingRecommendation:
    """Scaling recommendation with reasoning"""
    action: str  # 'none', 'scale_up', 'scale_down'
    urgency: str  # 'low', 'medium', 'high', 'critical'
    recommended_pods: int
    reason: str
    confidence: float  # 0.0-1.0

    def to_dict(self) -> dict[str, Any]:
        return {
            'action': self.action,
            'urgency': self.urgency,
            'recommended_pods': self.recommended_pods,
            'reason': self.reason,
            'confidence': self.confidence
        }


class BackpressureMonitor:
    """
    Production backpressure monitor that provides deterministic scaling decisions
    based on real metrics: queue depth, processing rate, latency, error rate
    """

    def __init__(self, redis_client=None):
        self.redis_client = redis_client

        # Configuration
        self.config = {
            'queue_depth_threshold_high': 1000,
            'queue_depth_threshold_critical': 2000,
            'processing_rate_min': 10.0,  # computations per second
            'latency_p99_threshold_ms': 5000,
            'error_rate_threshold': 0.1,  # 10%
            'cpu_threshold_high': 0.8,
            'memory_threshold_high': 0.85,
            'scale_up_threshold': 0.7,  # Combined load score
            'scale_down_threshold': 0.3
        }

        # Metrics history for trend analysis
        self.metrics_history: list[dict[str, Any]] = []
        self.max_history_size = 50  # Keep last 50 measurements

        # State
        self.current_backpressure = BackpressureLevel.LOW
        self.last_recommendation = None
        self.last_recommendation_time = 0
        self.recommendation_cooldown = 300  # 5 minutes

        logger.info("BackpressureMonitor initialized")

    async def initialize(self):
        """Initialize the backpressure monitor"""
        if not self.redis_client:
            raise RuntimeError("Redis client required for production BackpressureMonitor")

        # Load configuration from Redis if available
        await self._load_config()

        logger.info("BackpressureMonitor initialized successfully")

    async def _load_config(self):
        """Load configuration from Redis"""
        try:
            import json
            config_data = await self.redis_client.get('signal_service:backpressure:config')
            if config_data:
                saved_config = json.loads(config_data)
                self.config.update(saved_config)
                logger.info("Loaded backpressure configuration from Redis")
        except Exception as e:
            logger.warning(f"Failed to load backpressure config from Redis: {e}")

    def update_metrics(self, pod_id: str, metrics: dict[str, Any]):
        """Update metrics for a pod and recalculate backpressure"""
        try:
            # Validate required metrics
            required_fields = ['queue_depth', 'p99_latency', 'cpu_usage', 'memory_usage', 'error_rate']
            missing_fields = [field for field in required_fields if field not in metrics]

            if missing_fields:
                logger.error(f"Missing required metrics fields for pod {pod_id}: {missing_fields}")
                raise ValueError(f"Missing required metrics: {missing_fields}. No defaults allowed in production.")

            # Add timestamp and pod info
            timestamped_metrics = {
                'timestamp': time.time(),
                'pod_id': pod_id,
                **metrics
            }

            # Add to history
            self.metrics_history.append(timestamped_metrics)

            # Keep only recent history
            if len(self.metrics_history) > self.max_history_size:
                self.metrics_history.pop(0)

            # Calculate current backpressure level
            self.current_backpressure = self._calculate_backpressure_level(metrics)

            logger.debug(f"Updated metrics for pod {pod_id}, backpressure: {self.current_backpressure}")

        except Exception as e:
            logger.error(f"Failed to update metrics for pod {pod_id}: {e}")
            raise

    def _calculate_backpressure_level(self, metrics: dict[str, Any]) -> BackpressureLevel:
        """Calculate current backpressure level based on metrics"""
        try:
            queue_depth = metrics.get('queue_depth', 0)
            cpu_usage = metrics.get('cpu_usage', 0.0)
            memory_usage = metrics.get('memory_usage', 0.0)
            error_rate = metrics.get('error_rate', 0.0)
            p99_latency = metrics.get('p99_latency', 0.0)

            # Critical conditions
            if (queue_depth > self.config['queue_depth_threshold_critical'] or
                error_rate > self.config['error_rate_threshold'] * 2 or
                cpu_usage > 0.95 or memory_usage > 0.95):
                return BackpressureLevel.CRITICAL

            # High backpressure conditions
            if (queue_depth > self.config['queue_depth_threshold_high'] or
                p99_latency > self.config['latency_p99_threshold_ms'] or
                cpu_usage > self.config['cpu_threshold_high'] or
                memory_usage > self.config['memory_threshold_high'] or
                error_rate > self.config['error_rate_threshold']):
                return BackpressureLevel.HIGH

            # Medium backpressure conditions
            if (queue_depth > self.config['queue_depth_threshold_high'] * 0.5 or
                cpu_usage > 0.6 or memory_usage > 0.7):
                return BackpressureLevel.MEDIUM

            return BackpressureLevel.LOW

        except Exception as e:
            logger.error(f"Failed to calculate backpressure level: {e}")
            # Fail fast instead of defaulting
            raise ValueError(f"Unable to calculate backpressure level: {e}. No default values allowed in production.") from e

    def get_scaling_recommendation(self, current_pods: int = 1) -> ScalingRecommendation:
        """Get scaling recommendation based on current metrics and trends"""
        try:
            # Check cooldown period
            current_time = time.time()
            if (self.last_recommendation and
                current_time - self.last_recommendation_time < self.recommendation_cooldown):
                return self.last_recommendation

            if not self.metrics_history:
                return ScalingRecommendation(
                    action='none',
                    urgency='low',
                    recommended_pods=current_pods,
                    reason='No metrics available yet',
                    confidence=0.0
                )

            # Get latest metrics
            latest_metrics = self.metrics_history[-1]

            # Calculate composite load score
            load_score = self._calculate_load_score(latest_metrics)

            # Analyze trends
            trend_analysis = self._analyze_trends()

            # Determine recommendation
            recommendation = self._determine_scaling_action(
                load_score, trend_analysis, current_pods
            )

            # Cache recommendation
            self.last_recommendation = recommendation
            self.last_recommendation_time = current_time

            logger.info(f"Scaling recommendation: {recommendation.action} ({recommendation.reason})")

            return recommendation

        except Exception as e:
            logger.error(f"Failed to generate scaling recommendation: {e}")
            # Fail fast instead of returning default
            raise ValueError(f"Unable to generate scaling recommendation: {e}. No default recommendations allowed in production.") from e

    def _calculate_load_score(self, metrics: dict[str, Any]) -> float:
        """Calculate composite load score (0.0-1.0)"""
        try:
            queue_depth = metrics.get('queue_depth', 0)
            cpu_usage = metrics.get('cpu_usage', 0.0)
            memory_usage = metrics.get('memory_usage', 0.0)
            error_rate = metrics.get('error_rate', 0.0)

            # Normalize queue depth (0-1 based on thresholds)
            queue_score = min(1.0, queue_depth / self.config['queue_depth_threshold_high'])

            # Error rate score (0-1 based on threshold)
            error_score = min(1.0, error_rate / self.config['error_rate_threshold'])

            # Weighted composite score
            load_score = (
                queue_score * 0.4 +      # Queue depth is most important
                cpu_usage * 0.25 +       # CPU usage
                memory_usage * 0.25 +    # Memory usage
                error_score * 0.1        # Error rate
            )

            return min(1.0, load_score)

        except Exception as e:
            logger.error(f"Failed to calculate load score: {e}")
            raise ValueError(f"Unable to calculate load score: {e}") from e

    def _analyze_trends(self) -> dict[str, Any]:
        """Analyze trends in metrics over time"""
        if len(self.metrics_history) < 5:
            return {'trend': 'insufficient_data', 'confidence': 0.0}

        try:
            # Get recent metrics for trend analysis
            recent_metrics = self.metrics_history[-5:]

            # Calculate trends for key metrics
            queue_depths = [m.get('queue_depth', 0) for m in recent_metrics]
            cpu_usages = [m.get('cpu_usage', 0.0) for m in recent_metrics]
            error_rates = [m.get('error_rate', 0.0) for m in recent_metrics]

            # Simple trend analysis using linear correlation
            def calculate_trend(values):
                if len(set(values)) == 1:  # All values the same
                    return 0.0
                x = list(range(len(values)))
                n = len(values)
                sum_x = sum(x)
                sum_y = sum(values)
                sum_xy = sum(x[i] * values[i] for i in range(n))
                sum_x2 = sum(x[i] ** 2 for i in range(n))

                return (n * sum_xy - sum_x * sum_y) / (n * sum_x2 - sum_x ** 2)

            queue_trend = calculate_trend(queue_depths)
            cpu_trend = calculate_trend(cpu_usages)
            error_trend = calculate_trend(error_rates)

            # Determine overall trend
            if queue_trend > 50 or cpu_trend > 0.1 or error_trend > 0.01:
                trend = 'increasing'
                confidence = 0.8
            elif queue_trend < -50 or (cpu_trend < -0.1 and error_trend <= 0):
                trend = 'decreasing'
                confidence = 0.7
            else:
                trend = 'stable'
                confidence = 0.6

            return {
                'trend': trend,
                'confidence': confidence,
                'queue_trend': queue_trend,
                'cpu_trend': cpu_trend,
                'error_trend': error_trend
            }

        except Exception as e:
            logger.error(f"Failed to analyze trends: {e}")
            return {'trend': 'error', 'confidence': 0.0}

    def _determine_scaling_action(
        self,
        load_score: float,
        trend_analysis: dict[str, Any],
        current_pods: int
    ) -> ScalingRecommendation:
        """Determine scaling action based on load score and trends"""

        # Critical backpressure - immediate scale up
        if self.current_backpressure == BackpressureLevel.CRITICAL:
            return ScalingRecommendation(
                action='scale_up',
                urgency='critical',
                recommended_pods=min(current_pods + 2, 10),
                reason=f'Critical backpressure detected (load: {load_score:.2f})',
                confidence=0.9
            )

        # High load or increasing trend
        if (load_score > self.config['scale_up_threshold'] or
            (load_score > 0.5 and trend_analysis.get('trend') == 'increasing')):

            urgency = 'high' if load_score > 0.8 else 'medium'
            pods_to_add = 2 if load_score > 0.8 else 1

            return ScalingRecommendation(
                action='scale_up',
                urgency=urgency,
                recommended_pods=min(current_pods + pods_to_add, 10),
                reason=f'High load detected (score: {load_score:.2f}, trend: {trend_analysis.get("trend")})',
                confidence=max(0.7, trend_analysis.get('confidence', 0.5))
            )

        # Low load and decreasing trend - scale down
        if (current_pods > 1 and
            load_score < self.config['scale_down_threshold'] and
            trend_analysis.get('trend') == 'decreasing' and
            self.current_backpressure == BackpressureLevel.LOW):

            return ScalingRecommendation(
                action='scale_down',
                urgency='low',
                recommended_pods=max(current_pods - 1, 1),
                reason=f'Low sustained load (score: {load_score:.2f}, trend: decreasing)',
                confidence=trend_analysis.get('confidence', 0.5)
            )

        # Default - no action
        return ScalingRecommendation(
            action='none',
            urgency='none',
            recommended_pods=current_pods,
            reason=f'Load within acceptable range (score: {load_score:.2f})',
            confidence=0.6
        )

    def get_current_status(self) -> dict[str, Any]:
        """Get current backpressure status"""
        latest_metrics = self.metrics_history[-1] if self.metrics_history else {}

        return {
            'backpressure_level': self.current_backpressure.name,
            'metrics_history_size': len(self.metrics_history),
            'latest_metrics': latest_metrics,
            'config': self.config,
            'last_recommendation': self.last_recommendation.to_dict() if self.last_recommendation else None
        }

    async def update_config(self, new_config: dict[str, Any]):
        """Update configuration and save to Redis"""
        try:
            self.config.update(new_config)

            # Save to Redis
            import json
            await self.redis_client.setex(
                'signal_service:backpressure:config',
                3600,  # 1 hour
                json.dumps(self.config)
            )

            logger.info("Updated backpressure configuration")

        except Exception as e:
            logger.error(f"Failed to update backpressure config: {e}")
            raise
