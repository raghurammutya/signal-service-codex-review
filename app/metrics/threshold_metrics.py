# Prometheus Metrics for Threshold Monitoring System
import time
from typing import Any

from prometheus_client import Counter, Gauge, Histogram, Info

# Create threshold monitoring metrics
threshold_metrics = {
    # Threshold Configuration Metrics
    'thresholds_total': Counter(
        'signal_service_thresholds_total',
        'Total number of thresholds configured',
        ['user_id', 'indicator', 'priority', 'channel']
    ),

    'thresholds_active': Gauge(
        'signal_service_thresholds_active',
        'Number of currently active thresholds',
        ['tier', 'priority']
    ),

    # Threshold Breach Metrics
    'threshold_breaches_total': Counter(
        'signal_service_threshold_breaches_total',
        'Total number of threshold breaches',
        ['user_id', 'indicator', 'symbol', 'priority']
    ),

    'threshold_checks_total': Counter(
        'signal_service_threshold_checks_total',
        'Total number of threshold checks performed',
        ['indicator', 'tier', 'symbol']
    ),

    'threshold_check_duration_seconds': Histogram(
        'signal_service_threshold_check_duration_seconds',
        'Time spent checking thresholds',
        ['indicator', 'tier'],
        buckets=[0.001, 0.005, 0.01, 0.05, 0.1, 0.5, 1.0, 2.0, 5.0]
    ),

    # Alert Delivery Metrics
    'alerts_sent_total': Counter(
        'signal_service_alerts_sent_total',
        'Total number of alerts sent',
        ['channel', 'priority', 'status']
    ),

    'alert_delivery_duration_seconds': Histogram(
        'signal_service_alert_delivery_duration_seconds',
        'Time spent delivering alerts',
        ['channel', 'priority'],
        buckets=[0.01, 0.05, 0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0]
    ),

    'alert_queue_size': Gauge(
        'signal_service_alert_queue_size',
        'Current size of alert queues',
        ['priority']
    ),

    # Bulk Computation Metrics
    'option_chains_processed_total': Counter(
        'signal_service_option_chains_processed_total',
        'Total number of option chains processed',
        ['underlying', 'computation_type']
    ),

    'options_computed_total': Counter(
        'signal_service_options_computed_total',
        'Total number of individual options computed',
        ['underlying', 'option_type', 'computation_type']
    ),

    'bulk_computation_duration_seconds': Histogram(
        'signal_service_bulk_computation_duration_seconds',
        'Time spent in bulk computation',
        ['underlying', 'computation_type'],
        buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0]
    ),

    # Dynamic Classification Metrics
    'indicators_classified_total': Counter(
        'signal_service_indicators_classified_total',
        'Total number of indicators classified',
        ['indicator_type', 'assigned_tier', 'complexity']
    ),

    'classification_reclassifications_total': Counter(
        'signal_service_classification_reclassifications_total',
        'Total number of indicator reclassifications',
        ['indicator', 'old_tier', 'new_tier', 'reason']
    ),

    'user_action_learning_total': Counter(
        'signal_service_user_action_learning_total',
        'Total number of user actions learned from',
        ['user_id', 'action_type', 'outcome']
    ),

    # Resource Utilization Metrics
    'resource_utilization_ratio': Gauge(
        'signal_service_resource_utilization_ratio',
        'Current resource utilization ratio',
        ['resource_type', 'instance_id']
    ),

    'monitoring_tier_efficiency': Gauge(
        'signal_service_monitoring_tier_efficiency',
        'Efficiency ratio for each monitoring tier',
        ['tier', 'metric']
    ),

    # Performance Metrics
    'indicators_per_second': Gauge(
        'signal_service_indicators_per_second',
        'Number of indicators processed per second',
        ['tier']
    ),

    'threshold_accuracy_ratio': Gauge(
        'signal_service_threshold_accuracy_ratio',
        'Ratio of actionable threshold breaches',
        ['indicator', 'user_id']
    ),

    # Error Metrics
    'threshold_errors_total': Counter(
        'signal_service_threshold_errors_total',
        'Total number of threshold processing errors',
        ['error_type', 'component', 'indicator']
    ),

    'alert_delivery_failures_total': Counter(
        'signal_service_alert_delivery_failures_total',
        'Total number of alert delivery failures',
        ['channel', 'error_type']
    ),

    # System Health Metrics
    'service_info': Info(
        'signal_service_info',
        'Information about the signal service',
    ),

    'uptime_seconds': Gauge(
        'signal_service_uptime_seconds',
        'Service uptime in seconds'
    ),

    'memory_usage_bytes': Gauge(
        'signal_service_memory_usage_bytes',
        'Current memory usage in bytes',
        ['component']
    )
}

class ThresholdMetricsCollector:
    """Prometheus metrics collector for threshold monitoring system"""

    def __init__(self):
        self.start_time = time.time()
        self.metrics = threshold_metrics

        # Set service info
        self.metrics['service_info'].info({
            'version': '1.0.0',
            'service': 'signal_service',
            'component': 'threshold_monitoring'
        })

    def record_threshold_added(self, user_id: str, indicator: str, priority: str, channels: list):
        """Record when a threshold is added"""
        for channel in channels:
            self.metrics['thresholds_total'].labels(
                user_id=user_id,
                indicator=indicator,
                priority=priority,
                channel=channel
            ).inc()

    def update_active_thresholds(self, tier: str, priority: str, count: int):
        """Update active threshold count"""
        self.metrics['thresholds_active'].labels(
            tier=tier,
            priority=priority
        ).set(count)

    def record_threshold_breach(self, user_id: str, indicator: str, symbol: str, priority: str):
        """Record a threshold breach"""
        self.metrics['threshold_breaches_total'].labels(
            user_id=user_id,
            indicator=indicator,
            symbol=symbol,
            priority=priority
        ).inc()

    def record_threshold_check(self, indicator: str, tier: str, symbol: str, duration_ms: float):
        """Record a threshold check"""
        self.metrics['threshold_checks_total'].labels(
            indicator=indicator,
            tier=tier,
            symbol=symbol
        ).inc()

        self.metrics['threshold_check_duration_seconds'].labels(
            indicator=indicator,
            tier=tier
        ).observe(duration_ms / 1000.0)

    def record_alert_sent(self, channel: str, priority: str, status: str, duration_ms: float = 0):
        """Record an alert being sent"""
        self.metrics['alerts_sent_total'].labels(
            channel=channel,
            priority=priority,
            status=status
        ).inc()

        if duration_ms > 0:
            self.metrics['alert_delivery_duration_seconds'].labels(
                channel=channel,
                priority=priority
            ).observe(duration_ms / 1000.0)

    def update_alert_queue_size(self, priority: str, size: int):
        """Update alert queue size"""
        self.metrics['alert_queue_size'].labels(priority=priority).set(size)

    def record_option_chain_processed(self, underlying: str, computation_type: str,
                                    options_count: int, duration_ms: float):
        """Record option chain processing"""
        self.metrics['option_chains_processed_total'].labels(
            underlying=underlying,
            computation_type=computation_type
        ).inc()

        self.metrics['bulk_computation_duration_seconds'].labels(
            underlying=underlying,
            computation_type=computation_type
        ).observe(duration_ms / 1000.0)

    def record_option_computed(self, underlying: str, option_type: str, computation_type: str):
        """Record individual option computation"""
        self.metrics['options_computed_total'].labels(
            underlying=underlying,
            option_type=option_type,
            computation_type=computation_type
        ).inc()

    def record_indicator_classified(self, indicator_type: str, assigned_tier: str, complexity: str):
        """Record indicator classification"""
        self.metrics['indicators_classified_total'].labels(
            indicator_type=indicator_type,
            assigned_tier=assigned_tier,
            complexity=complexity
        ).inc()

    def record_reclassification(self, indicator: str, old_tier: str, new_tier: str, reason: str):
        """Record indicator reclassification"""
        self.metrics['classification_reclassifications_total'].labels(
            indicator=indicator,
            old_tier=old_tier,
            new_tier=new_tier,
            reason=reason
        ).inc()

    def record_user_action_learning(self, user_id: str, action_type: str, outcome: str):
        """Record user action for learning"""
        self.metrics['user_action_learning_total'].labels(
            user_id=user_id,
            action_type=action_type,
            outcome=outcome
        ).inc()

    def update_resource_utilization(self, resource_type: str, instance_id: str, ratio: float):
        """Update resource utilization ratio"""
        self.metrics['resource_utilization_ratio'].labels(
            resource_type=resource_type,
            instance_id=instance_id
        ).set(ratio)

    def update_monitoring_tier_efficiency(self, tier: str, metric: str, value: float):
        """Update monitoring tier efficiency metrics"""
        self.metrics['monitoring_tier_efficiency'].labels(
            tier=tier,
            metric=metric
        ).set(value)

    def update_indicators_per_second(self, tier: str, rate: float):
        """Update indicator processing rate"""
        self.metrics['indicators_per_second'].labels(tier=tier).set(rate)

    def update_threshold_accuracy(self, indicator: str, user_id: str, accuracy: float):
        """Update threshold accuracy ratio"""
        self.metrics['threshold_accuracy_ratio'].labels(
            indicator=indicator,
            user_id=user_id
        ).set(accuracy)

    def record_error(self, error_type: str, component: str, indicator: str = "unknown"):
        """Record threshold processing error"""
        self.metrics['threshold_errors_total'].labels(
            error_type=error_type,
            component=component,
            indicator=indicator
        ).inc()

    def record_alert_delivery_failure(self, channel: str, error_type: str):
        """Record alert delivery failure"""
        self.metrics['alert_delivery_failures_total'].labels(
            channel=channel,
            error_type=error_type
        ).inc()

    def update_uptime(self):
        """Update service uptime"""
        uptime = time.time() - self.start_time
        self.metrics['uptime_seconds'].set(uptime)

    def update_memory_usage(self, component: str, bytes_used: int):
        """Update memory usage for a component"""
        self.metrics['memory_usage_bytes'].labels(component=component).set(bytes_used)

    def get_all_metrics(self) -> dict[str, Any]:
        """Get all current metric values for debugging"""
        self.update_uptime()

        # This would collect all current metric values
        # In a real implementation, you'd iterate through all metrics
        return {
            'uptime_seconds': time.time() - self.start_time,
            'metrics_registered': len(self.metrics),
            'timestamp': time.time()
        }

# Global metrics collector instance
metrics_collector = ThresholdMetricsCollector()


def get_metrics_collector() -> ThresholdMetricsCollector:
    """Get the global metrics collector instance"""
    return metrics_collector


# Convenience functions for easy metric recording
def record_threshold_added(user_id: str, indicator: str, priority: str, channels: list):
    """Convenience function to record threshold addition"""
    metrics_collector.record_threshold_added(user_id, indicator, priority, channels)


def record_threshold_breach(user_id: str, indicator: str, symbol: str, priority: str):
    """Convenience function to record threshold breach"""
    metrics_collector.record_threshold_breach(user_id, indicator, symbol, priority)


def record_alert_sent(channel: str, priority: str, status: str, duration_ms: float = 0):
    """Convenience function to record alert sent"""
    metrics_collector.record_alert_sent(channel, priority, status, duration_ms)


def record_option_chain_processed(underlying: str, computation_type: str,
                                 options_count: int, duration_ms: float):
    """Convenience function to record option chain processing"""
    metrics_collector.record_option_chain_processed(underlying, computation_type, options_count, duration_ms)


def record_error(error_type: str, component: str, indicator: str = "unknown"):
    """Convenience function to record errors"""
    metrics_collector.record_error(error_type, component, indicator)
