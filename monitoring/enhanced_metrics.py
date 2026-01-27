"""
Enhanced Production Metrics for Signal Service

Extends existing metrics infrastructure with critical production KPIs
for operations management and performance tuning.
"""
from prometheus_client import Counter, Enum, Gauge, Histogram

from app.utils.logging_config import get_logger

logger = get_logger(__name__)


class ProductionMetricsCollector:
    """
    Enhanced metrics collector for production operations management.

    Focuses on metrics that directly impact:
    - Performance tuning
    - Capacity planning
    - Error detection
    - Business KPIs
    - Resource optimization
    """

    def __init__(self):
        self._init_api_metrics()
        self._init_business_metrics()
        self._init_operational_metrics()
        self._init_dependency_metrics()

        logger.info("Enhanced production metrics collector initialized")

    def _init_api_metrics(self):
        """API performance and usage metrics"""

        # API Request Duration - Critical for performance tuning
        self.api_request_duration = Histogram(
            'signal_service_api_request_duration_seconds',
            'Duration of API requests',
            ['endpoint', 'method', 'status_code', 'user_tier', 'operation_type'],
            buckets=[0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 25.0, 50.0, 100.0]
        )

        # API Request Rate - For capacity planning
        self.api_request_rate = Counter(
            'signal_service_api_requests_total',
            'Total API requests',
            ['endpoint', 'method', 'status_code', 'user_tier']
        )

        # Concurrent Request Gauge - For load monitoring
        self.concurrent_requests = Gauge(
            'signal_service_concurrent_requests',
            'Current concurrent requests',
            ['endpoint_group']
        )

        # Rate Limit Metrics - For quota management
        self.rate_limit_hits = Counter(
            'signal_service_rate_limit_hits_total',
            'Rate limit violations',
            ['user_id', 'endpoint', 'limit_type']
        )

    def _init_business_metrics(self):
        """Business KPIs for operational insights"""

        # Signal Generation Performance - Core business metric
        self.signal_generation_latency = Histogram(
            'signal_service_signal_generation_seconds',
            'Time to generate signals',
            ['signal_type', 'complexity', 'data_source'],
            buckets=[0.01, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0]
        )

        # Greeks Calculation Efficiency - Key differentiator
        self.greeks_calculation_duration = Histogram(
            'signal_service_greeks_calculation_seconds',
            'Greeks calculation performance',
            ['calculation_type', 'vectorized', 'model_type', 'batch_size'],
            buckets=[0.001, 0.01, 0.1, 0.5, 1.0, 2.0, 5.0]
        )

        # Active Subscriptions - Revenue metric
        self.active_subscriptions = Gauge(
            'signal_service_active_subscriptions',
            'Current active signal subscriptions',
            ['user_tier', 'signal_type', 'delivery_method']
        )

        # Signal Accuracy Tracking - Quality metric
        self.signal_accuracy = Gauge(
            'signal_service_signal_accuracy_ratio',
            'Signal prediction accuracy',
            ['signal_type', 'time_horizon', 'asset_class']
        )

        # Revenue Impact Metrics
        self.calculation_cost = Counter(
            'signal_service_calculation_cost_total',
            'Computational cost of operations',
            ['operation_type', 'user_tier', 'complexity']
        )

    def _init_operational_metrics(self):
        """Operational excellence metrics"""

        # Cache Performance - Critical for cost optimization
        self.cache_operations = Counter(
            'signal_service_cache_operations_total',
            'Cache operations',
            ['cache_type', 'operation', 'result']
        )

        self.cache_hit_ratio = Gauge(
            'signal_service_cache_hit_ratio',
            'Cache hit ratio',
            ['cache_type', 'time_window']
        )

        # Queue Metrics - For capacity planning
        self.queue_size = Gauge(
            'signal_service_queue_size',
            'Current queue size',
            ['queue_type', 'priority', 'instance_id']
        )

        self.queue_processing_rate = Gauge(
            'signal_service_queue_processing_rate_per_second',
            'Queue processing rate',
            ['queue_type', 'priority']
        )

        # Memory Usage by Operation Type
        self.memory_usage_by_operation = Gauge(
            'signal_service_memory_usage_bytes',
            'Memory usage by operation type',
            ['operation_type', 'instance_id']
        )

        # Database Query Performance
        self.db_query_duration = Histogram(
            'signal_service_database_query_seconds',
            'Database query performance',
            ['query_type', 'table', 'operation'],
            buckets=[0.001, 0.01, 0.1, 0.5, 1.0, 2.0, 5.0]
        )

        # Background Task Performance
        self.background_task_duration = Histogram(
            'signal_service_background_task_seconds',
            'Background task execution time',
            ['task_type', 'scheduled', 'priority']
        )

    def _init_dependency_metrics(self):
        """External service dependency monitoring"""

        # External Service Health - Critical for reliability
        self.external_service_health = Gauge(
            'signal_service_external_service_health',
            'External service health status (1=healthy, 0=unhealthy)',
            ['service_name', 'endpoint', 'check_type']
        )

        # External Service Response Time
        self.external_service_duration = Histogram(
            'signal_service_external_service_duration_seconds',
            'External service response time',
            ['service_name', 'endpoint', 'operation'],
            buckets=[0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0]
        )

        # Circuit Breaker State
        self.circuit_breaker_state = Enum(
            'signal_service_circuit_breaker_state',
            'Circuit breaker current state',
            ['service_name', 'operation'],
            states=['closed', 'open', 'half_open']
        )

        # Service Dependency Errors
        self.dependency_errors = Counter(
            'signal_service_dependency_errors_total',
            'External service dependency errors',
            ['service_name', 'error_type', 'impact_level']
        )

        # API Key Usage - For service-to-service auth tracking
        self.internal_api_usage = Counter(
            'signal_service_internal_api_usage_total',
            'Internal API key usage',
            ['target_service', 'operation', 'result']
        )

    def record_api_request(
        self,
        endpoint: str,
        method: str,
        status_code: int,
        duration_seconds: float,
        user_tier: str = "unknown",
        operation_type: str = "general"
    ):
        """Record API request metrics"""
        self.api_request_duration.labels(
            endpoint=endpoint,
            method=method,
            status_code=str(status_code),
            user_tier=user_tier,
            operation_type=operation_type
        ).observe(duration_seconds)

        self.api_request_rate.labels(
            endpoint=endpoint,
            method=method,
            status_code=str(status_code),
            user_tier=user_tier
        ).inc()

    def record_signal_generation(
        self,
        signal_type: str,
        duration_seconds: float,
        complexity: str = "standard",
        data_source: str = "live"
    ):
        """Record signal generation performance"""
        self.signal_generation_latency.labels(
            signal_type=signal_type,
            complexity=complexity,
            data_source=data_source
        ).observe(duration_seconds)

    def record_greeks_calculation(
        self,
        calculation_type: str,
        duration_seconds: float,
        vectorized: bool = False,
        model_type: str = "black_scholes",
        batch_size: int = 1
    ):
        """Record Greeks calculation performance"""
        batch_category = self._categorize_batch_size(batch_size)

        self.greeks_calculation_duration.labels(
            calculation_type=calculation_type,
            vectorized=str(vectorized).lower(),
            model_type=model_type,
            batch_size=batch_category
        ).observe(duration_seconds)

    def record_cache_operation(
        self,
        cache_type: str,
        operation: str,
        result: str
    ):
        """Record cache operation"""
        self.cache_operations.labels(
            cache_type=cache_type,
            operation=operation,
            result=result
        ).inc()

    def update_cache_hit_ratio(
        self,
        cache_type: str,
        hit_ratio: float,
        time_window: str = "1m"
    ):
        """Update cache hit ratio"""
        self.cache_hit_ratio.labels(
            cache_type=cache_type,
            time_window=time_window
        ).set(hit_ratio)

    def record_external_service_call(
        self,
        service_name: str,
        endpoint: str,
        duration_seconds: float,
        success: bool,
        operation: str = "api_call"
    ):
        """Record external service interaction"""
        self.external_service_duration.labels(
            service_name=service_name,
            endpoint=endpoint,
            operation=operation
        ).observe(duration_seconds)

        if not success:
            self.dependency_errors.labels(
                service_name=service_name,
                error_type="timeout_or_error",
                impact_level="medium"
            ).inc()

    def update_external_service_health(
        self,
        service_name: str,
        endpoint: str,
        is_healthy: bool,
        check_type: str = "http_check"
    ):
        """Update external service health status"""
        self.external_service_health.labels(
            service_name=service_name,
            endpoint=endpoint,
            check_type=check_type
        ).set(1.0 if is_healthy else 0.0)

    def update_circuit_breaker_state(
        self,
        service_name: str,
        operation: str,
        state: str
    ):
        """Update circuit breaker state"""
        self.circuit_breaker_state.labels(
            service_name=service_name,
            operation=operation
        ).state(state)

    def update_active_subscriptions(
        self,
        count: int,
        user_tier: str,
        signal_type: str,
        delivery_method: str = "api"
    ):
        """Update active subscription count"""
        self.active_subscriptions.labels(
            user_tier=user_tier,
            signal_type=signal_type,
            delivery_method=delivery_method
        ).set(count)

    def update_queue_metrics(
        self,
        queue_type: str,
        size: int,
        processing_rate: float,
        priority: str = "normal",
        instance_id: str = "default"
    ):
        """Update queue metrics"""
        self.queue_size.labels(
            queue_type=queue_type,
            priority=priority,
            instance_id=instance_id
        ).set(size)

        self.queue_processing_rate.labels(
            queue_type=queue_type,
            priority=priority
        ).set(processing_rate)

    def record_db_query(
        self,
        query_type: str,
        table: str,
        operation: str,
        duration_seconds: float
    ):
        """Record database query performance"""
        self.db_query_duration.labels(
            query_type=query_type,
            table=table,
            operation=operation
        ).observe(duration_seconds)

    def _categorize_batch_size(self, batch_size: int) -> str:
        """Categorize batch size for metrics"""
        if batch_size == 1:
            return "single"
        if batch_size <= 10:
            return "small"
        if batch_size <= 100:
            return "medium"
        if batch_size <= 1000:
            return "large"
        return "xlarge"


# Singleton instance
_enhanced_metrics_collector = None

def get_enhanced_metrics_collector() -> ProductionMetricsCollector:
    """Get singleton enhanced metrics collector"""
    global _enhanced_metrics_collector
    if _enhanced_metrics_collector is None:
        _enhanced_metrics_collector = ProductionMetricsCollector()
    return _enhanced_metrics_collector
