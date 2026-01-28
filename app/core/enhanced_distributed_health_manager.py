"""
Enhanced Distributed Health Manager with Real Metrics

Replaces runtime error-throwing distributed health manager with real metrics collection
for requests/queue processing and actual distributed coordination metrics.
"""
import asyncio
import json
import logging
import time
from collections import defaultdict, deque
from datetime import datetime
from typing import Any

import psutil

from app.core.config import settings
from app.services.metrics_service import get_metrics_collector
from app.utils.redis import get_redis_client

logger = logging.getLogger(__name__)


class EnhancedDistributedHealthManager:
    """
    Enhanced distributed health manager with real metrics collection.

    Provides actual metrics for requests/queue processing and distributed
    coordination instead of runtime errors.
    """

    def __init__(self):
        self.redis_client = None
        self.metrics_collector = get_metrics_collector()
        self.instance_id = f"{settings.CONSUMER_NAME}_{int(time.time())}"
        self.start_time = time.time()

        # Real metrics tracking
        self.request_queue = deque(maxlen=1000)
        self.processing_queue = deque(maxlen=1000)
        self.distributed_events = deque(maxlen=500)

        # Redis keys for distributed coordination
        self.redis_keys = {
            'instances': 'signal_service:instances',
            'health': f'signal_service:health:{self.instance_id}',
            'metrics': f'signal_service:metrics:{self.instance_id}',
            'coordination': 'signal_service:coordination',
            'assignments': 'signal_service:assignments'
        }

    async def initialize(self):
        """Initialize distributed health manager."""
        try:
            self.redis_client = await get_redis_client()
            await self.metrics_collector.initialize()

            # Register this instance
            await self._register_instance()

            # Start background tasks
            asyncio.create_task(self._health_reporting_loop())
            asyncio.create_task(self._metrics_collection_loop())

        except Exception as e:
            logger.error(f"Failed to initialize distributed health manager: {e}")

    async def _register_instance(self):
        """Register this instance in the distributed cluster."""
        try:
            instance_data = {
                'instance_id': self.instance_id,
                'start_time': self.start_time,
                'hostname': psutil.Process().name(),
                'pid': psutil.Process().pid,
                'status': 'starting',
                'last_seen': time.time()
            }

            await self.redis_client.hset(
                self.redis_keys['instances'],
                self.instance_id,
                json.dumps(instance_data)
            )

            # set expiration for cleanup
            await self.redis_client.expire(self.redis_keys['instances'], 3600)

        except Exception as e:
            logger.error(f"Failed to register instance: {e}")

    async def get_request_rate(self) -> float:
        """Get real request rate (requests per minute) instead of runtime error."""
        try:
            # Count requests in the last minute
            cutoff_time = time.time() - 60
            recent_requests = [r for r in self.request_queue if r['timestamp'] >= cutoff_time]
            return len(recent_requests)

        except Exception as e:
            logger.error(f"Failed to get request rate: {e}")
            return 0.0

    async def get_queue_size(self) -> int:
        """Get real processing queue size instead of runtime error."""
        try:
            # Get actual queue sizes from Redis
            queue_keys = [
                'signal_service:processing_queue',
                'signal_service:greeks_queue',
                'signal_service:indicators_queue'
            ]

            total_queue_size = 0
            for key in queue_keys:
                try:
                    size = await self.redis_client.llen(key)
                    total_queue_size += size
                except Exception:
                    # Queue doesn't exist, continue
                    continue

            return total_queue_size

        except Exception as e:
            logger.error(f"Failed to get queue size: {e}")
            return 0

    async def get_processing_rate(self) -> float:
        """Get real signal processing rate instead of runtime error."""
        try:
            # Count processing completions in the last minute
            cutoff_time = time.time() - 60
            recent_processing = [p for p in self.processing_queue if p['timestamp'] >= cutoff_time]
            return len(recent_processing)

        except Exception as e:
            logger.error(f"Failed to get processing rate: {e}")
            return 0.0

    async def get_assigned_instruments(self) -> list[str]:
        """Get real list of instruments assigned to this instance."""
        try:
            # Get instrument assignments from Redis
            assignments_key = f"{self.redis_keys['assignments']}:{self.instance_id}"
            assignments = await self.redis_client.smembers(assignments_key)

            if assignments:
                return list(assignments)

            # Fallback: get from processing history
            recent_instruments = set()
            for event in self.processing_queue:
                if 'instrument_key' in event:
                    recent_instruments.add(event['instrument_key'])

            return list(recent_instruments)

        except Exception as e:
            logger.error(f"Failed to get assigned instruments: {e}")
            return []

    def record_request_processing(self, request_data: dict[str, Any]):
        """Record request processing for rate calculation."""
        self.request_queue.append({
            'timestamp': time.time(),
            'endpoint': request_data.get('endpoint', 'unknown'),
            'processing_time_ms': request_data.get('duration_ms', 0),
            'status': request_data.get('status', 'completed')
        })

    def record_signal_processing(self, signal_data: dict[str, Any]):
        """Record signal processing for rate calculation."""
        self.processing_queue.append({
            'timestamp': time.time(),
            'signal_type': signal_data.get('signal_type', 'unknown'),
            'instrument_key': signal_data.get('instrument_key', 'unknown'),
            'processing_time_ms': signal_data.get('duration_ms', 0),
            'success': signal_data.get('success', True)
        })

    def record_distributed_event(self, event_type: str, event_data: dict[str, Any]):
        """Record distributed coordination events."""
        self.distributed_events.append({
            'timestamp': time.time(),
            'event_type': event_type,  # 'assignment_change', 'failover', 'scale_up', 'scale_down'
            'event_data': event_data
        })

    async def get_load_metrics(self) -> dict[str, Any]:
        """Get real load metrics for this instance."""
        try:
            process = psutil.Process()

            # Real system metrics
            memory_info = process.memory_info()
            cpu_percent = process.cpu_percent(interval=0.1)

            # Real processing metrics
            request_rate = await self.get_request_rate()
            processing_rate = await self.get_processing_rate()
            queue_size = await self.get_queue_size()

            # Calculate load score
            load_score = self._calculate_load_score(cpu_percent, memory_info.rss, request_rate)

            return {
                'instance_id': self.instance_id,
                'cpu_percent': round(cpu_percent, 2),
                'memory_mb': round(memory_info.rss / (1024 * 1024), 2),
                'memory_percent': round(process.memory_percent(), 2),
                'connection_count': len(process.connections()),
                'thread_count': process.num_threads(),
                'requests_per_minute': request_rate,
                'queue_size': queue_size,
                'processing_rate': processing_rate,
                'load_score': load_score,
                'uptime_seconds': round(time.time() - self.start_time, 2),
                'timestamp': datetime.utcnow().isoformat()
            }

        except Exception as e:
            logger.error(f"Failed to collect load metrics: {e}")
            return {
                'instance_id': self.instance_id,
                'error': str(e),
                'timestamp': datetime.utcnow().isoformat()
            }

    def _calculate_load_score(self, cpu_percent: float, memory_bytes: int, request_rate: float) -> float:
        """Calculate overall load score for this instance."""
        score = 100.0

        # Penalize high CPU usage
        if cpu_percent > 80:
            score -= 30
        elif cpu_percent > 60:
            score -= 15
        elif cpu_percent > 40:
            score -= 5

        # Penalize high memory usage
        memory_mb = memory_bytes / (1024 * 1024)
        if memory_mb > 1024:  # > 1GB
            score -= 20
        elif memory_mb > 512:  # > 512MB
            score -= 10

        # Penalize very high request rates (overload)
        if request_rate > 200:  # > 200 requests/minute
            score -= 15
        elif request_rate > 100:  # > 100 requests/minute
            score -= 5

        return max(0.0, min(100.0, score))

    async def report_instance_health(self):
        """Report this instance's health to the distributed cluster."""
        try:
            # Get current metrics
            load_metrics = await self.get_load_metrics()
            health_metrics = self.metrics_collector.get_health_score()
            assigned_instruments = await self.get_assigned_instruments()

            # Determine instance status
            overall_score = health_metrics.get('overall_score', 0)
            if overall_score >= 80:
                instance_status = 'healthy'
            elif overall_score >= 60:
                instance_status = 'degraded'
            else:
                instance_status = 'unhealthy'

            health_data = {
                'instance_id': self.instance_id,
                'status': instance_status,
                'health_score': overall_score,
                'load_metrics': load_metrics,
                'assigned_instruments': assigned_instruments,
                'metrics': {
                    'request_rate': await self.get_request_rate(),
                    'processing_rate': await self.get_processing_rate(),
                    'queue_size': await self.get_queue_size(),
                    'error_rate': self.metrics_collector.get_error_rate()
                },
                'timestamp': datetime.utcnow().isoformat(),
                'last_seen': time.time()
            }

            # Store in Redis
            await self.redis_client.hset(
                self.redis_keys['instances'],
                self.instance_id,
                json.dumps(health_data)
            )

            # Update individual health key
            await self.redis_client.setex(
                self.redis_keys['health'],
                300,  # 5 minute expiry
                json.dumps(health_data)
            )

            # Update aggregate health
            await self._update_aggregate_health()

        except Exception as e:
            logger.error(f"Failed to report instance health: {e}")

    async def _update_aggregate_health(self):
        """Update aggregate health status across all instances."""
        try:
            # Get all active instances
            instances_data = await self.redis_client.hgetall(self.redis_keys['instances'])

            if not instances_data:
                return

            healthy_instances = 0
            total_instances = len(instances_data)
            total_request_rate = 0
            total_processing_rate = 0
            total_queue_size = 0

            instance_details = {}

            for instance_id, data_json in instances_data.items():
                try:
                    instance_data = json.loads(data_json)

                    # Check if instance is recent (last 5 minutes)
                    last_seen = instance_data.get('last_seen', 0)
                    if time.time() - last_seen > 300:  # 5 minutes
                        # Instance is stale, remove it
                        await self.redis_client.hdel(self.redis_keys['instances'], instance_id)
                        continue

                    instance_details[instance_id] = instance_data

                    if instance_data.get('status') == 'healthy':
                        healthy_instances += 1

                    # Aggregate metrics
                    metrics = instance_data.get('metrics', {})
                    total_request_rate += metrics.get('request_rate', 0)
                    total_processing_rate += metrics.get('processing_rate', 0)
                    total_queue_size += metrics.get('queue_size', 0)

                except Exception as e:
                    logger.warning(f"Failed to parse instance data for {instance_id}: {e}")
                    continue

            # Calculate aggregate health
            if total_instances > 0:
                health_percentage = healthy_instances / total_instances

                if health_percentage >= 0.8:  # 80% healthy
                    cluster_status = 'healthy'
                elif health_percentage >= 0.5:  # 50% healthy
                    cluster_status = 'degraded'
                else:
                    cluster_status = 'unhealthy'
            else:
                cluster_status = 'unknown'
                health_percentage = 0.0

            # Store aggregate health
            aggregate_health = {
                'cluster_status': cluster_status,
                'health_percentage': round(health_percentage * 100, 1),
                'total_instances': total_instances,
                'healthy_instances': healthy_instances,
                'aggregate_metrics': {
                    'total_request_rate': total_request_rate,
                    'total_processing_rate': total_processing_rate,
                    'total_queue_size': total_queue_size,
                    'average_request_rate': total_request_rate / max(total_instances, 1),
                    'average_processing_rate': total_processing_rate / max(total_instances, 1)
                },
                'instances': instance_details,
                'timestamp': datetime.utcnow().isoformat()
            }

            await self.redis_client.setex(
                'signal_service:cluster_health',
                300,  # 5 minute expiry
                json.dumps(aggregate_health)
            )

        except Exception as e:
            logger.error(f"Failed to update aggregate health: {e}")

    async def get_distributed_coordination_metrics(self) -> dict[str, Any]:
        """Get distributed coordination metrics."""
        try:
            # Get cluster health
            cluster_health_data = await self.redis_client.get('signal_service:cluster_health')
            if cluster_health_data:
                cluster_health = json.loads(cluster_health_data)
            else:
                cluster_health = {'cluster_status': 'unknown'}

            # Calculate coordination metrics
            coordination_events = list(self.distributed_events)
            recent_events = [e for e in coordination_events if time.time() - e['timestamp'] < 3600]  # Last hour

            event_summary = defaultdict(int)
            for event in recent_events:
                event_summary[event['event_type']] += 1

            return {
                'cluster_health': cluster_health,
                'coordination_events_last_hour': len(recent_events),
                'event_breakdown': dict(event_summary),
                'instance_coordination': {
                    'instance_id': self.instance_id,
                    'assigned_instruments': await self.get_assigned_instruments(),
                    'coordination_score': self._calculate_coordination_score(cluster_health)
                },
                'distributed_metrics': {
                    'total_instances': cluster_health.get('total_instances', 0),
                    'healthy_instances': cluster_health.get('healthy_instances', 0),
                    'cluster_load_balance_score': self._calculate_load_balance_score(cluster_health)
                },
                'timestamp': datetime.utcnow().isoformat()
            }

        except Exception as e:
            logger.error(f"Failed to get coordination metrics: {e}")
            return {
                'error': str(e),
                'timestamp': datetime.utcnow().isoformat()
            }

    def _calculate_coordination_score(self, cluster_health: dict[str, Any]) -> float:
        """Calculate coordination score for this instance."""
        score = 100.0

        cluster_status = cluster_health.get('cluster_status', 'unknown')
        if cluster_status == 'unhealthy':
            score -= 40
        elif cluster_status == 'degraded':
            score -= 20

        # Check if this instance is contributing properly
        health_percentage = cluster_health.get('health_percentage', 0)
        if health_percentage < 50:
            score -= 30

        return max(0.0, min(100.0, score))

    def _calculate_load_balance_score(self, cluster_health: dict[str, Any]) -> float:
        """Calculate how well load is balanced across instances."""
        try:
            instances = cluster_health.get('instances', {})
            if len(instances) < 2:
                return 100.0  # Perfect balance with single instance

            # Get request rates
            request_rates = []
            for instance_data in instances.values():
                metrics = instance_data.get('metrics', {})
                request_rates.append(metrics.get('request_rate', 0))

            if not request_rates:
                return 100.0

            # Calculate coefficient of variation
            import statistics
            if len(request_rates) > 1:
                mean_rate = statistics.mean(request_rates)
                if mean_rate > 0:
                    std_dev = statistics.stdev(request_rates)
                    cv = std_dev / mean_rate

                    # Convert to balance score (lower CV = better balance)
                    return max(0, 100 - (cv * 100))

            return 100.0

        except Exception as e:
            logger.error(f"Failed to calculate load balance score: {e}")
            return 50.0  # Default score on error

    async def _health_reporting_loop(self):
        """Background task for periodic health reporting."""
        while True:
            try:
                await self.report_instance_health()
                await asyncio.sleep(30)  # Report every 30 seconds
            except Exception as e:
                logger.error(f"Health reporting loop error: {e}")
                await asyncio.sleep(60)  # Back off on error

    async def _metrics_collection_loop(self):
        """Background task for metrics collection."""
        while True:
            try:
                # Export metrics to Redis for monitoring
                await self.metrics_collector.export_metrics_to_redis()
                await asyncio.sleep(60)  # Export every minute
            except Exception as e:
                logger.error(f"Metrics collection loop error: {e}")
                await asyncio.sleep(120)  # Back off on error

    async def cleanup(self):
        """Clean up instance registration."""
        try:
            # Remove from instances registry
            await self.redis_client.hdel(self.redis_keys['instances'], self.instance_id)

            # Clean up health keys
            await self.redis_client.delete(self.redis_keys['health'])
            await self.redis_client.delete(self.redis_keys['metrics'])

        except Exception as e:
            logger.error(f"Failed to cleanup instance registration: {e}")


# Global enhanced distributed health manager instance
_enhanced_distributed_health_manager: EnhancedDistributedHealthManager | None = None


async def get_enhanced_distributed_health_manager() -> EnhancedDistributedHealthManager:
    """Get or create enhanced distributed health manager instance."""
    global _enhanced_distributed_health_manager
    if _enhanced_distributed_health_manager is None:
        _enhanced_distributed_health_manager = EnhancedDistributedHealthManager()
        await _enhanced_distributed_health_manager.initialize()
    return _enhanced_distributed_health_manager
