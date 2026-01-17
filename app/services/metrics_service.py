"""
Real Metrics Service Implementation

Provides actual metrics collection and reporting for health checks and monitoring.
Replaces mock data with real measurements for production readiness.
"""
import asyncio
import time
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from collections import defaultdict, deque
import psutil
import threading

from app.utils.redis import get_redis_client
from app.core.config import settings

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
        
    async def initialize(self):
        """Initialize metrics collector with Redis connection."""
        self.redis_client = await get_redis_client()
        
    def record_request(self, endpoint: str, duration_ms: float, status_code: int):
        """Record API request metrics."""
        with self._lock:
            timestamp = time.time()
            
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
    
    def record_circuit_breaker_event(self, breaker_type: str, event: str, metrics: Dict[str, Any]):
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
    
    def get_greeks_performance_metrics(self) -> Dict[str, Any]:
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
    
    def _get_greeks_breakdown(self) -> Dict[str, Dict[str, Any]]:
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
    
    def get_cache_performance_metrics(self) -> Dict[str, Any]:
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
    
    def get_system_metrics(self) -> Dict[str, Any]:
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
    
    def get_health_score(self) -> Dict[str, Any]:
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


# Global metrics collector instance
_metrics_collector: Optional[MetricsCollector] = None


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
            endpoint = scope.get("path", "unknown")
            self.metrics_collector.record_request(endpoint, duration_ms, status_code)