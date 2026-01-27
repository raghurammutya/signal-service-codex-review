"""
Real Metrics Service Implementation

Provides actual metrics collection and reporting for health checks and monitoring.
Provides real measurements for production readiness.
"""
import asyncio
import json
import logging
import threading
import time
from collections import defaultdict, deque
from datetime import datetime
from typing import Any

import psutil

# Import logging utilities
from app.utils.logging_utils import log_info


def log_error(message, *args, **kwargs):
    """Log error messages."""
    logging.error(message, *args, **kwargs)

from app.utils.redis import get_redis_client

logger = logging.getLogger(__name__)


class MetricsCollector:
    """
    Real-time metrics collector for signal service performance.
    Tracks request rates, processing times, and system resources.
    """

    def __init__(self):
        self.redis_client = None
        self.metrics_cache = {}
        self.request_times = deque(maxlen=1000)  # Last 1000 requests
        self.processing_times = deque(maxlen=1000)  # Last 1000 processing times
        self.error_counts = defaultdict(int)
        self.request_counts = defaultdict(int)
        self._lock = threading.Lock()
        self._start_time = time.time()

        # Performance tracking
        self.greeks_calculation_times = deque(maxlen=500)
        self.circuit_breaker_metrics = {}
        self.cache_hit_rates = {}

        # Config-driven budget guards and backpressure
        self.budget_guards = None  # Will be loaded from config service
        self.backpressure_state = {
            'active': False,
            'level': 'none',  # none, light, moderate, heavy
            'start_time': None,
            'current_restrictions': {}
        }
        self.concurrent_operations = 0
        self._budget_manager = None

    async def initialize(self):
        """Initialize metrics collector with Redis connection and config-driven budget."""
        self.redis_client = await get_redis_client()

        # Initialize config-driven budget manager
        from app.config.budget_config import get_budget_manager
        self._budget_manager = get_budget_manager()

        # Load initial budget configuration
        await self._refresh_budget_config()

    async def _refresh_budget_config(self):
        """Refresh budget configuration from config service."""
        try:
            if self._budget_manager:
                budget_config = await self._budget_manager.get_metrics_budget()

                # Convert config to dictionary format expected by existing code
                self.budget_guards = {
                    'max_concurrent_operations': budget_config.max_concurrent_operations,
                    'max_memory_mb': budget_config.max_memory_mb,
                    'max_cpu_percent': budget_config.max_cpu_percent,
                    'max_request_rate_per_minute': budget_config.max_request_rate_per_minute,
                    'max_processing_time_ms': budget_config.max_processing_time_ms,
                    # Add backpressure thresholds
                    'light_pressure_threshold': budget_config.light_pressure_threshold,
                    'moderate_pressure_threshold': budget_config.moderate_pressure_threshold,
                    'heavy_pressure_threshold': budget_config.heavy_pressure_threshold
                }

                log_info(f"Budget configuration refreshed: {self.budget_guards}")
            else:
                # Fallback to default values
                self.budget_guards = {
                    'max_concurrent_operations': 50,
                    'max_memory_mb': 512,
                    'max_cpu_percent': 85,
                    'max_request_rate_per_minute': 300,
                    'max_processing_time_ms': 5000,
                    'light_pressure_threshold': 0.7,
                    'moderate_pressure_threshold': 0.85,
                    'heavy_pressure_threshold': 0.95
                }
                log_info("Using default budget configuration")

        except Exception as e:
            log_error(f"Failed to refresh budget config: {e}")
            # Use safe defaults if config fetch fails
            self.budget_guards = {
                'max_concurrent_operations': 50,
                'max_memory_mb': 512,
                'max_cpu_percent': 85,
                'max_request_rate_per_minute': 300,
                'max_processing_time_ms': 5000,
                'light_pressure_threshold': 0.7,
                'moderate_pressure_threshold': 0.85,
                'heavy_pressure_threshold': 0.95
            }

    async def refresh_budget_config(self):
        """Public method to refresh budget configuration."""
        await self._refresh_budget_config()

    def record_request(self, endpoint: str, duration_ms: float, status_code: int):
        """Record API request metrics with budget guard validation."""
        # Apply budget throttling - drop non-essential metrics under pressure
        if self.backpressure_state['active'] and self.backpressure_state['level'] == 'heavy':
            # Only record essential endpoints during heavy backpressure
            if not any(essential in endpoint for essential in ['/health', '/metrics']):
                return

        with self._lock:
            timestamp = time.time()

            # Check backpressure thresholds
            self._evaluate_backpressure()

            # Record request timing
            self.request_times.append({
                'endpoint': endpoint,
                'duration_ms': duration_ms,
                'status_code': status_code,
                'timestamp': timestamp
            })

            # Update counters
            self.request_counts[endpoint] += 1
            if status_code >= 400:
                self.error_counts[endpoint] += 1

            # Budget guard: Check if processing time exceeds limit
            if duration_ms > self.budget_guards['max_processing_time_ms']:
                logger.warning(f"Request {endpoint} exceeded processing time budget: {duration_ms}ms")
                self._trigger_backpressure('processing_time_exceeded')

    def record_processing_time(self, operation: str, duration_ms: float, success: bool):
        """Record signal processing metrics."""
        with self._lock:
            self.processing_times.append({
                'operation': operation,
                'duration_ms': duration_ms,
                'success': success,
                'timestamp': time.time()
            })

            # Specific tracking for Greeks calculations
            if operation.startswith('greeks_'):
                self.greeks_calculation_times.append({
                    'type': operation,
                    'duration_ms': duration_ms,
                    'success': success,
                    'timestamp': time.time()
                })

    def record_circuit_breaker_event(self, breaker_type: str, event: str, metrics: dict[str, Any]):
        """Record circuit breaker state changes and metrics."""
        if breaker_type not in self.circuit_breaker_metrics:
            self.circuit_breaker_metrics[breaker_type] = deque(maxlen=100)

        self.circuit_breaker_metrics[breaker_type].append({
            'event': event,  # 'open', 'close', 'half_open', 'call_success', 'call_failure'
            'metrics': metrics.copy(),
            'timestamp': time.time()
        })

    def record_cache_operation(self, cache_type: str, hit: bool):
        """Record cache hit/miss metrics."""
        if cache_type not in self.cache_hit_rates:
            self.cache_hit_rates[cache_type] = {'hits': 0, 'misses': 0}

        if hit:
            self.cache_hit_rates[cache_type]['hits'] += 1
        else:
            self.cache_hit_rates[cache_type]['misses'] += 1

    def get_request_rate(self, window_minutes: int = 5) -> float:
        """Get request rate over specified time window."""
        cutoff_time = time.time() - (window_minutes * 60)

        with self._lock:
            recent_requests = [r for r in self.request_times if r['timestamp'] >= cutoff_time]

        if not recent_requests:
            return 0.0

        return len(recent_requests) / window_minutes

    def get_processing_rate(self, window_minutes: int = 5) -> float:
        """Get signal processing rate over specified time window."""
        cutoff_time = time.time() - (window_minutes * 60)

        with self._lock:
            recent_processing = [p for p in self.processing_times if p['timestamp'] >= cutoff_time]

        if not recent_processing:
            return 0.0

        return len(recent_processing) / window_minutes

    def get_error_rate(self, window_minutes: int = 5) -> float:
        """Get error rate over specified time window."""
        cutoff_time = time.time() - (window_minutes * 60)

        with self._lock:
            recent_requests = [r for r in self.request_times if r['timestamp'] >= cutoff_time]

        if not recent_requests:
            return 0.0

        error_count = len([r for r in recent_requests if r['status_code'] >= 400])
        return error_count / len(recent_requests)

    def get_average_response_time(self, window_minutes: int = 5) -> float:
        """Get average response time over specified time window."""
        cutoff_time = time.time() - (window_minutes * 60)

        with self._lock:
            recent_requests = [r for r in self.request_times if r['timestamp'] >= cutoff_time]

        if not recent_requests:
            return 0.0

        total_time = sum(r['duration_ms'] for r in recent_requests)
        return total_time / len(recent_requests)

    def get_greeks_performance_metrics(self) -> dict[str, Any]:
        """Get comprehensive Greeks calculation performance metrics."""
        with self._lock:
            recent_greeks = list(self.greeks_calculation_times)

        if not recent_greeks:
            return {
                'total_calculations': 0,
                'success_rate': 0.0,
                'average_duration_ms': 0.0,
                'p95_duration_ms': 0.0,
                'calculations_per_minute': 0.0
            }

        # Calculate metrics
        total_calculations = len(recent_greeks)
        successful_calculations = len([g for g in recent_greeks if g['success']])
        success_rate = successful_calculations / total_calculations if total_calculations > 0 else 0.0

        durations = [g['duration_ms'] for g in recent_greeks]
        average_duration = sum(durations) / len(durations) if durations else 0.0

        # P95 calculation
        sorted_durations = sorted(durations)
        p95_index = int(0.95 * len(sorted_durations))
        p95_duration = sorted_durations[p95_index] if sorted_durations else 0.0

        # Rate calculation (last 5 minutes)
        cutoff_time = time.time() - 300
        recent_count = len([g for g in recent_greeks if g['timestamp'] >= cutoff_time])
        calculations_per_minute = recent_count / 5.0

        return {
            'total_calculations': total_calculations,
            'success_rate': success_rate,
            'average_duration_ms': average_duration,
            'p95_duration_ms': p95_duration,
            'calculations_per_minute': calculations_per_minute,
            'breakdown_by_type': self._get_greeks_breakdown(),
            'timestamp': datetime.utcnow().isoformat()
        }

    def _get_greeks_breakdown(self) -> dict[str, dict[str, Any]]:
        """Get breakdown of Greeks calculations by type."""
        breakdown = defaultdict(lambda: {'count': 0, 'total_time': 0.0, 'errors': 0})

        with self._lock:
            for calc in self.greeks_calculation_times:
                calc_type = calc['type']
                breakdown[calc_type]['count'] += 1
                breakdown[calc_type]['total_time'] += calc['duration_ms']
                if not calc['success']:
                    breakdown[calc_type]['errors'] += 1

        # Calculate averages
        for calc_type, metrics in breakdown.items():
            if metrics['count'] > 0:
                metrics['average_duration_ms'] = metrics['total_time'] / metrics['count']
                metrics['error_rate'] = metrics['errors'] / metrics['count']
            else:
                metrics['average_duration_ms'] = 0.0
                metrics['error_rate'] = 0.0

        return dict(breakdown)

    def get_cache_performance_metrics(self) -> dict[str, Any]:
        """Get cache performance metrics."""
        metrics = {}

        for cache_type, counts in self.cache_hit_rates.items():
            total_operations = counts['hits'] + counts['misses']
            hit_rate = counts['hits'] / total_operations if total_operations > 0 else 0.0

            metrics[cache_type] = {
                'hit_rate': hit_rate,
                'total_hits': counts['hits'],
                'total_misses': counts['misses'],
                'total_operations': total_operations
            }

        return metrics

    def get_system_metrics(self) -> dict[str, Any]:
        """Get real system resource metrics."""
        try:
            process = psutil.Process()

            # Process metrics
            memory_info = process.memory_info()
            memory_mb = memory_info.rss / (1024 * 1024)
            memory_percent = process.memory_percent()

            # Get CPU percentage over 1 second interval for accuracy
            cpu_percent = process.cpu_percent(interval=1.0)

            # System-wide metrics
            system_memory = psutil.virtual_memory()
            system_cpu = psutil.cpu_percent(interval=1.0)

            # Disk usage for log directory
            disk_usage = psutil.disk_usage('/')

            # Network connections
            connections = len(process.connections())

            return {
                'process': {
                    'memory_mb': round(memory_mb, 2),
                    'memory_percent': round(memory_percent, 2),
                    'cpu_percent': round(cpu_percent, 2),
                    'threads': process.num_threads(),
                    'connections': connections,
                    'uptime_seconds': round(time.time() - self._start_time, 2)
                },
                'system': {
                    'memory_total_gb': round(system_memory.total / (1024**3), 2),
                    'memory_available_gb': round(system_memory.available / (1024**3), 2),
                    'memory_percent': round(system_memory.percent, 2),
                    'cpu_percent': round(system_cpu, 2),
                    'disk_total_gb': round(disk_usage.total / (1024**3), 2),
                    'disk_free_gb': round(disk_usage.free / (1024**3), 2),
                    'disk_percent': round((disk_usage.used / disk_usage.total) * 100, 2)
                },
                'timestamp': datetime.utcnow().isoformat()
            }

        except Exception as e:
            logger.error(f"Failed to collect system metrics: {e}")
            return {
                'error': str(e),
                'timestamp': datetime.utcnow().isoformat()
            }

    def get_health_score(self) -> dict[str, Any]:
        """Calculate overall health score based on metrics."""
        try:
            # Get current metrics
            error_rate = self.get_error_rate()
            avg_response_time = self.get_average_response_time()
            greeks_metrics = self.get_greeks_performance_metrics()
            system_metrics = self.get_system_metrics()

            # Calculate component scores (0-100)
            scores = {}

            # Error rate score (lower is better)
            if error_rate <= 0.01:  # <= 1% error rate
                scores['error_rate'] = 100
            elif error_rate <= 0.05:  # <= 5% error rate
                scores['error_rate'] = 80
            elif error_rate <= 0.10:  # <= 10% error rate
                scores['error_rate'] = 60
            else:
                scores['error_rate'] = 40

            # Response time score (lower is better)
            if avg_response_time <= 100:  # <= 100ms
                scores['response_time'] = 100
            elif avg_response_time <= 200:  # <= 200ms
                scores['response_time'] = 80
            elif avg_response_time <= 500:  # <= 500ms
                scores['response_time'] = 60
            else:
                scores['response_time'] = 40

            # Greeks calculation score
            greeks_success_rate = greeks_metrics.get('success_rate', 0.0)
            if greeks_success_rate >= 0.99:  # >= 99% success rate
                scores['greeks_calculations'] = 100
            elif greeks_success_rate >= 0.95:  # >= 95% success rate
                scores['greeks_calculations'] = 80
            elif greeks_success_rate >= 0.90:  # >= 90% success rate
                scores['greeks_calculations'] = 60
            else:
                scores['greeks_calculations'] = 40

            # System resource score
            if 'process' in system_metrics:
                cpu_percent = system_metrics['process']['cpu_percent']
                memory_percent = system_metrics['process']['memory_percent']

                # CPU score
                if cpu_percent <= 50:
                    cpu_score = 100
                elif cpu_percent <= 70:
                    cpu_score = 80
                elif cpu_percent <= 85:
                    cpu_score = 60
                else:
                    cpu_score = 40

                # Memory score
                if memory_percent <= 60:
                    memory_score = 100
                elif memory_percent <= 75:
                    memory_score = 80
                elif memory_percent <= 90:
                    memory_score = 60
                else:
                    memory_score = 40

                scores['system_resources'] = (cpu_score + memory_score) / 2
            else:
                scores['system_resources'] = 50  # Default score on error

            # Calculate overall health score
            overall_score = sum(scores.values()) / len(scores)

            # Determine health status
            if overall_score >= 90:
                health_status = 'excellent'
            elif overall_score >= 80:
                health_status = 'good'
            elif overall_score >= 70:
                health_status = 'fair'
            elif overall_score >= 60:
                health_status = 'poor'
            else:
                health_status = 'critical'

            return {
                'overall_score': round(overall_score, 1),
                'health_status': health_status,
                'component_scores': scores,
                'metrics_summary': {
                    'error_rate': error_rate,
                    'avg_response_time_ms': avg_response_time,
                    'greeks_success_rate': greeks_success_rate,
                    'request_rate_per_minute': self.get_request_rate(),
                    'processing_rate_per_minute': self.get_processing_rate()
                },
                'timestamp': datetime.utcnow().isoformat()
            }

        except Exception as e:
            logger.error(f"Failed to calculate health score: {e}")
            return {
                'overall_score': 0,
                'health_status': 'unknown',
                'error': str(e),
                'timestamp': datetime.utcnow().isoformat()
            }

    async def export_metrics_to_redis(self, ttl_seconds: int = 300):
        """Export current metrics to Redis for monitoring systems."""
        if not self.redis_client:
            return

        # Apply budget throttling - drop metrics export under pressure
        if not self.should_allow_operation('metrics_export', 'normal'):
            self.record_processing_time('metrics_export_dropped', 0, False)
            return

        try:
            metrics_data = {
                'request_rate': self.get_request_rate(),
                'processing_rate': self.get_processing_rate(),
                'error_rate': self.get_error_rate(),
                'response_time': self.get_average_response_time(),
                'greeks_performance': self.get_greeks_performance_metrics(),
                'cache_performance': self.get_cache_performance_metrics(),
                'system_metrics': self.get_system_metrics(),
                'health_score': self.get_health_score(),
                'last_updated': datetime.utcnow().isoformat()
            }

            # Store in Redis with TTL
            import json
            await self.redis_client.setex(
                'signal_service:metrics:current',
                ttl_seconds,
                json.dumps(metrics_data)
            )

        except Exception as e:
            logger.error(f"Failed to export metrics to Redis: {e}")
            # Implement circuit breaker for Redis export reliability
            self.record_circuit_breaker_event('redis_export', 'call_failure', {'error': str(e)})

            # Retry logic for critical metrics export
            retry_count = 0
            max_retries = 3
            while retry_count < max_retries:
                try:
                    await asyncio.sleep(2 ** retry_count)  # Exponential backoff

                    # Simplified metrics for retry
                    fallback_metrics = {
                        'error_rate': self.get_error_rate(),
                        'request_rate': self.get_request_rate(),
                        'health_score': self.get_health_score()['overall'],
                        'last_updated': datetime.utcnow().isoformat(),
                        'export_status': 'fallback_retry'
                    }

                    await self.redis_client.setex(
                        'signal_service:metrics:fallback',
                        ttl_seconds // 2,  # Shorter TTL for fallback
                        json.dumps(fallback_metrics)
                    )

                    self.record_circuit_breaker_event('redis_export', 'call_success', {'retry_count': retry_count})
                    logger.info(f"Metrics export succeeded on retry {retry_count + 1}")
                    break

                except Exception as retry_e:
                    retry_count += 1
                    logger.warning(f"Metrics export retry {retry_count} failed: {retry_e}")

            if retry_count >= max_retries:
                self.record_circuit_breaker_event('redis_export', 'open', {'consecutive_failures': retry_count})

    def _evaluate_backpressure(self):
        """Evaluate current system state and adjust backpressure if needed."""
        try:
            # Check current metrics against budget guards
            current_request_rate = self.get_request_rate()
            system_metrics = self.get_system_metrics()

            pressure_indicators = []

            # Request rate pressure
            if current_request_rate > self.budget_guards['max_request_rate_per_minute']:
                pressure_indicators.append('high_request_rate')

            # Memory pressure
            if 'process' in system_metrics:
                memory_mb = system_metrics['process']['memory_mb']
                cpu_percent = system_metrics['process']['cpu_percent']

                if memory_mb > self.budget_guards['max_memory_mb']:
                    pressure_indicators.append('high_memory')

                if cpu_percent > self.budget_guards['max_cpu_percent']:
                    pressure_indicators.append('high_cpu')

            # Concurrent operations pressure
            if self.concurrent_operations > self.budget_guards['max_concurrent_operations']:
                pressure_indicators.append('high_concurrency')

            # Determine backpressure level
            if len(pressure_indicators) >= 3:
                new_level = 'heavy'
            elif len(pressure_indicators) >= 2:
                new_level = 'moderate'
            elif len(pressure_indicators) >= 1:
                new_level = 'light'
            else:
                new_level = 'none'

            # Update backpressure state
            current_level = self.backpressure_state['level']
            if new_level != current_level:
                logger.info(f"Backpressure level changed: {current_level} -> {new_level}")
                self.backpressure_state['level'] = new_level
                self.backpressure_state['active'] = new_level != 'none'

                if new_level != 'none' and not self.backpressure_state['start_time']:
                    self.backpressure_state['start_time'] = time.time()
                elif new_level == 'none':
                    self.backpressure_state['start_time'] = None

                self._apply_backpressure_restrictions(new_level, pressure_indicators)

        except Exception as e:
            logger.error(f"Error evaluating backpressure: {e}")

    def _trigger_backpressure(self, reason: str):
        """Manually trigger backpressure due to specific condition."""
        logger.warning(f"Backpressure triggered due to: {reason}")
        self.backpressure_state['active'] = True
        self.backpressure_state['level'] = 'moderate'
        self.backpressure_state['start_time'] = time.time()
        self._apply_backpressure_restrictions('moderate', [reason])

    def _apply_backpressure_restrictions(self, level: str, indicators: list[str]):
        """Apply appropriate restrictions based on backpressure level."""
        restrictions = {}

        if level == 'light':
            # Light restrictions: reduce cache sizes, increase timeouts
            restrictions = {
                'reduce_cache_sizes': True,
                'increased_timeouts': True,
                'priority_requests_only': False,
                'reject_non_essential': False
            }
        elif level == 'moderate':
            # Moderate restrictions: priority requests only, reduce concurrency
            restrictions = {
                'reduce_cache_sizes': True,
                'increased_timeouts': True,
                'priority_requests_only': True,
                'reject_non_essential': True,
                'max_concurrent_operations': min(25, self.budget_guards['max_concurrent_operations'] // 2)
            }
        elif level == 'heavy':
            # Heavy restrictions: minimal operations only
            restrictions = {
                'reduce_cache_sizes': True,
                'increased_timeouts': True,
                'priority_requests_only': True,
                'reject_non_essential': True,
                'max_concurrent_operations': min(10, self.budget_guards['max_concurrent_operations'] // 4),
                'emergency_mode': True
            }

        self.backpressure_state['current_restrictions'] = restrictions
        logger.info(f"Applied {level} backpressure restrictions: {restrictions}")

    def should_allow_operation(self, operation_type: str = 'default', priority: str = 'normal') -> bool:
        """Check if an operation should be allowed based on current backpressure state."""
        if not self.backpressure_state['active']:
            return True

        restrictions = self.backpressure_state['current_restrictions']

        # Always allow health checks and essential operations
        if operation_type in ['health_check', 'essential']:
            return True

        # Check priority restrictions
        if restrictions.get('priority_requests_only') and priority != 'high':
            return False

        # Check non-essential rejection
        if restrictions.get('reject_non_essential') and operation_type in ['analytics', 'reporting', 'batch']:
            return False

        # Check concurrent operation limits
        max_concurrent = restrictions.get('max_concurrent_operations')
        if max_concurrent and self.concurrent_operations >= max_concurrent:
            return False

        # Emergency mode - only critical operations
        if restrictions.get('emergency_mode') and operation_type not in ['critical', 'essential']:
            return False

        return True

    async def acquire_operation_permit(self, operation_type: str = 'default', priority: str = 'normal') -> bool:
        """Acquire a permit to perform an operation (with backpressure check)."""
        if not self.should_allow_operation(operation_type, priority):
            return False

        with self._lock:
            self.concurrent_operations += 1

        return True

    async def release_operation_permit(self):
        """Release an operation permit."""
        with self._lock:
            self.concurrent_operations = max(0, self.concurrent_operations - 1)

    def get_backpressure_status(self) -> dict[str, Any]:
        """Get current backpressure status and metrics."""
        return {
            'active': self.backpressure_state['active'],
            'level': self.backpressure_state['level'],
            'start_time': self.backpressure_state['start_time'],
            'duration_seconds': time.time() - self.backpressure_state['start_time'] if self.backpressure_state['start_time'] else 0,
            'restrictions': self.backpressure_state['current_restrictions'],
            'concurrent_operations': self.concurrent_operations,
            'budget_guards': self.budget_guards,
            'current_metrics': {
                'request_rate': self.get_request_rate(),
                'error_rate': self.get_error_rate(),
                'avg_response_time': self.get_average_response_time()
            }
        }

    def update_budget_guards(self, new_guards: dict[str, Any]):
        """Update budget guard thresholds (for dynamic adjustment)."""
        for key, value in new_guards.items():
            if key in self.budget_guards:
                old_value = self.budget_guards[key]
                self.budget_guards[key] = value
                logger.info(f"Updated budget guard {key}: {old_value} -> {value}")

        # Re-evaluate backpressure with new thresholds
        self._evaluate_backpressure()


# Global metrics collector instance
_metrics_collector: MetricsCollector | None = None


def get_metrics_collector() -> MetricsCollector:
    """Get or create metrics collector instance."""
    global _metrics_collector
    if _metrics_collector is None:
        _metrics_collector = MetricsCollector()
    return _metrics_collector


async def initialize_metrics_service():
    """Initialize the metrics service."""
    collector = get_metrics_collector()
    await collector.initialize()
    return collector


class MetricsMiddleware:
    """FastAPI middleware for automatic metrics collection."""

    def __init__(self, app):
        self.app = app
        self.metrics_collector = get_metrics_collector()

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        endpoint = scope.get("path", "unknown")

        # Check backpressure before processing request
        operation_type = self._classify_operation_type(endpoint)
        priority = self._determine_request_priority(scope)

        # Acquire operation permit with backpressure check
        permit_acquired = await self.metrics_collector.acquire_operation_permit(operation_type, priority)

        if not permit_acquired:
            # Return 503 Service Unavailable due to backpressure
            backpressure_status = self.metrics_collector.get_backpressure_status()

            response = {
                "type": "http.response.start",
                "status": 503,
                "headers": [
                    [b"content-type", b"application/json"],
                    [b"retry-after", b"30"],  # Suggest retry in 30 seconds
                ],
            }
            await send(response)

            body = {
                "error": "Service temporarily unavailable due to high load",
                "backpressure_level": backpressure_status["level"],
                "retry_after_seconds": 30
            }

            await send({
                "type": "http.response.body",
                "body": json.dumps(body).encode(),
            })

            # Record rejected request
            self.metrics_collector.record_request(endpoint, 0, 503)
            return

        start_time = time.time()
        status_code = 200

        async def send_wrapper(message):
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            duration_ms = (time.time() - start_time) * 1000
            self.metrics_collector.record_request(endpoint, duration_ms, status_code)

            # Release operation permit
            await self.metrics_collector.release_operation_permit()

    def _classify_operation_type(self, endpoint: str) -> str:
        """Classify operation type for backpressure decisions."""
        if any(path in endpoint for path in ['/health', '/metrics', '/ping']):
            return 'health_check'
        if any(path in endpoint for path in ['/api/v2/signals', '/websocket']):
            return 'critical'
        if any(path in endpoint for path in ['/admin', '/monitoring']):
            return 'essential'
        if any(path in endpoint for path in ['/analytics', '/reporting']):
            return 'analytics'
        if any(path in endpoint for path in ['/batch']):
            return 'batch'
        return 'default'

    def _determine_request_priority(self, scope) -> str:
        """Determine request priority based on headers or endpoint."""
        headers = dict(scope.get("headers", []))

        # Check for priority header
        priority_header = headers.get(b"x-priority", b"").decode().lower()
        if priority_header in ['high', 'critical']:
            return 'high'
        if priority_header == 'low':
            return 'low'

        # Endpoint-based priority
        endpoint = scope.get("path", "")
        if any(path in endpoint for path in ['/health', '/metrics']) or '/admin' in endpoint:
            return 'high'
        if '/batch' in endpoint:
            return 'low'

        return 'normal'
