"""
Distributed health management for Signal Service horizontal scaling
"""
import asyncio
import json
import socket
import time
import uuid
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, asdict
import logging

import redis.asyncio as redis

logger = logging.getLogger(__name__)

@dataclass
class ServiceInstance:
    """Represents a Signal Service instance"""
    instance_id: str
    container_name: str
    host: str
    port: int
    started_at: datetime
    last_heartbeat: datetime
    status: str  # healthy, unhealthy, error
    health_data: Dict[str, Any]
    load_metrics: Dict[str, Any]
    assigned_instruments: List[str]

class DistributedHealthManager:
    """Manages health across multiple Signal Service instances"""
    
    def __init__(self, redis_client, instance_id: str = None):
        self.redis_client = redis_client
        self.instance_id = instance_id or self._generate_instance_id()
        self.container_name = self._get_container_name()
        self.host = self._get_host_ip()
        self.port = 8003  # Signal Service port
        self.started_at = datetime.utcnow()
        self.heartbeat_interval = 30  # seconds
        self.instance_ttl = 90  # seconds before considering instance dead
        
        # Redis keys for distributed coordination
        self.redis_keys = {
            'instances': 'signal_service:instances',
            'health_aggregate': 'signal_service:health:aggregate',
            'scaling_metrics': 'signal_service:scaling:metrics',
            'load_distribution': 'signal_service:load:distribution'
        }
    
    def _generate_instance_id(self) -> str:
        """Generate unique instance ID"""
        return f"signal-service-{uuid.uuid4().hex[:8]}"
    
    def _get_container_name(self) -> str:
        """Get container name from environment or hostname"""
        import os
        return os.environ.get('CONTAINER_NAME', socket.gethostname())
    
    def _get_host_ip(self) -> str:
        """Get host IP address"""
        try:
            # Connect to external address to determine local IP
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except Exception:
            return "127.0.0.1"
    
    async def register_instance(self, health_checker) -> None:
        """Register this instance in the distributed registry"""
        try:
            instance = ServiceInstance(
                instance_id=self.instance_id,
                container_name=self.container_name,
                host=self.host,
                port=self.port,
                started_at=self.started_at,
                last_heartbeat=datetime.utcnow(),
                status="healthy",
                health_data={},
                load_metrics={},
                assigned_instruments=[]
            )
            
            # Store instance data
            await self.redis_client.hset(
                self.redis_keys['instances'],
                self.instance_id,
                json.dumps(asdict(instance), default=str)
            )
            
            # Set TTL for auto-cleanup
            await self.redis_client.expire(
                f"{self.redis_keys['instances']}:{self.instance_id}",
                self.instance_ttl
            )
            
            logger.info(f"Registered instance {self.instance_id} ({self.container_name})")
            
        except Exception as e:
            logger.error(f"Failed to register instance: {e}")
    
    async def start_heartbeat(self, health_checker) -> None:
        """Start periodic heartbeat and health reporting"""
        while True:
            try:
                await self._send_heartbeat(health_checker)
                await asyncio.sleep(self.heartbeat_interval)
            except Exception as e:
                logger.error(f"Heartbeat failed: {e}")
                await asyncio.sleep(5)  # Retry after 5 seconds
    
    async def _send_heartbeat(self, health_checker) -> None:
        """Send heartbeat with current health and load data"""
        try:
            # Get current health status
            health_data = await health_checker.get_comprehensive_health()
            
            # Get current load metrics
            load_metrics = await self._collect_load_metrics()
            
            # Update instance data
            instance_data = {
                'instance_id': self.instance_id,
                'container_name': self.container_name,
                'host': self.host,
                'port': self.port,
                'started_at': self.started_at.isoformat(),
                'last_heartbeat': datetime.utcnow().isoformat(),
                'status': health_data['status'],
                'health_data': health_data,
                'load_metrics': load_metrics,
                'assigned_instruments': await self._get_assigned_instruments()
            }
            
            # Store in Redis
            await self.redis_client.hset(
                self.redis_keys['instances'],
                self.instance_id,
                json.dumps(instance_data)
            )
            
            # Update aggregate health
            await self._update_aggregate_health()
            
            # Update scaling metrics
            await self._update_scaling_metrics(load_metrics)
            
        except Exception as e:
            logger.error(f"Failed to send heartbeat: {e}")
    
    async def _collect_load_metrics(self) -> Dict[str, Any]:
        """Collect current load metrics for this instance"""
        import psutil
        
        try:
            process = psutil.Process()
            
            return {
                'cpu_percent': process.cpu_percent(),
                'memory_percent': process.memory_percent(),
                'memory_mb': process.memory_info().rss / (1024 * 1024),
                'connection_count': len(process.connections()),
                'thread_count': process.num_threads(),
                'requests_per_minute': await self._get_request_rate(),
                'queue_size': await self._get_queue_size(),
                'processing_rate': await self._get_processing_rate(),
                'timestamp': datetime.utcnow().isoformat()
            }
        except Exception as e:
            logger.error(f"Failed to collect load metrics: {e}")
            return {}
    
    async def _get_request_rate(self) -> float:
        """Get current request rate (requests per minute)"""
        # In real implementation, this would track actual request rates
        # For now, return a mock value
        return 450.0
    
    async def _get_queue_size(self) -> int:
        """Get current processing queue size"""
        # In real implementation, this would check actual queue
        return 125
    
    async def _get_processing_rate(self) -> float:
        """Get current signal processing rate"""
        # In real implementation, this would track actual processing rate
        return 85.5
    
    async def _get_assigned_instruments(self) -> List[str]:
        """Get list of instruments assigned to this instance"""
        # In real implementation, this would get from consistent hash manager
        return [
            f"NSE@NIFTY@equity_options@2025-07-10@call@{21000 + i*50}"
            for i in range(20)  # Mock 20 assigned instruments
        ]
    
    async def _update_aggregate_health(self) -> None:
        """Update aggregate health status across all instances"""
        try:
            # Get all active instances
            instances_data = await self.redis_client.hgetall(self.redis_keys['instances'])
            
            if not instances_data:
                return
            
            instances = []
            current_time = datetime.utcnow()
            
            for instance_json in instances_data.values():
                try:
                    instance = json.loads(instance_json)
                    last_heartbeat = datetime.fromisoformat(instance['last_heartbeat'])
                    
                    # Check if instance is still alive
                    if (current_time - last_heartbeat).total_seconds() < self.instance_ttl:
                        instances.append(instance)
                except Exception as e:
                    logger.warning(f"Failed to parse instance data: {e}")
            
            # Calculate aggregate metrics
            aggregate_data = await self._calculate_aggregate_metrics(instances)
            
            # Store aggregate data
            await self.redis_client.set(
                self.redis_keys['health_aggregate'],
                json.dumps(aggregate_data),
                ex=60  # Expire after 1 minute
            )
            
        except Exception as e:
            logger.error(f"Failed to update aggregate health: {e}")
    
    async def _calculate_aggregate_metrics(self, instances: List[Dict]) -> Dict[str, Any]:
        """Calculate aggregate metrics across all instances"""
        if not instances:
            return {
                'status': 'error',
                'message': 'No active instances',
                'timestamp': datetime.utcnow().isoformat()
            }
        
        # Count statuses
        status_counts = {'healthy': 0, 'unhealthy': 0, 'error': 0}
        total_instances = len(instances)
        
        # Aggregate load metrics
        total_cpu = 0
        total_memory = 0
        total_requests = 0
        total_queue_size = 0
        total_instruments = 0
        
        instance_details = []
        
        for instance in instances:
            status = instance.get('status', 'error')
            status_counts[status] = status_counts.get(status, 0) + 1
            
            load_metrics = instance.get('load_metrics', {})
            total_cpu += load_metrics.get('cpu_percent', 0)
            total_memory += load_metrics.get('memory_percent', 0)
            total_requests += load_metrics.get('requests_per_minute', 0)
            total_queue_size += load_metrics.get('queue_size', 0)
            total_instruments += len(instance.get('assigned_instruments', []))
            
            instance_details.append({
                'instance_id': instance['instance_id'],
                'container_name': instance['container_name'],
                'host': instance['host'],
                'status': instance['status'],
                'uptime_seconds': (
                    datetime.utcnow() - datetime.fromisoformat(instance['started_at'])
                ).total_seconds(),
                'load_metrics': load_metrics,
                'assigned_instruments_count': len(instance.get('assigned_instruments', []))
            })
        
        # Determine overall status
        if status_counts['error'] > 0:
            overall_status = 'error'
        elif status_counts['unhealthy'] > total_instances * 0.5:  # More than 50% unhealthy
            overall_status = 'unhealthy'
        elif status_counts['unhealthy'] > 0:
            overall_status = 'unhealthy'
        else:
            overall_status = 'healthy'
        
        # Calculate averages
        avg_cpu = total_cpu / total_instances if total_instances > 0 else 0
        avg_memory = total_memory / total_instances if total_instances > 0 else 0
        
        return {
            'status': overall_status,
            'timestamp': datetime.utcnow().isoformat(),
            'service': 'signal_service',
            'cluster_metrics': {
                'total_instances': total_instances,
                'healthy_instances': status_counts['healthy'],
                'unhealthy_instances': status_counts['unhealthy'],
                'error_instances': status_counts['error'],
                'total_requests_per_minute': total_requests,
                'total_queue_size': total_queue_size,
                'total_assigned_instruments': total_instruments,
                'average_cpu_percent': round(avg_cpu, 1),
                'average_memory_percent': round(avg_memory, 1)
            },
            'instances': instance_details,
            'scaling_recommendation': await self._get_scaling_recommendation(instances),
            'load_distribution': await self._analyze_load_distribution(instances)
        }
    
    async def _get_scaling_recommendation(self, instances: List[Dict]) -> Dict[str, Any]:
        """Analyze if scaling up or down is recommended"""
        if not instances:
            return {'action': 'scale_up', 'reason': 'No instances running', 'target_instances': 1}
        
        total_instances = len(instances)
        
        # Calculate average load metrics
        avg_cpu = sum(inst.get('load_metrics', {}).get('cpu_percent', 0) for inst in instances) / total_instances
        avg_memory = sum(inst.get('load_metrics', {}).get('memory_percent', 0) for inst in instances) / total_instances
        avg_queue_size = sum(inst.get('load_metrics', {}).get('queue_size', 0) for inst in instances) / total_instances
        
        # Count unhealthy instances
        unhealthy_count = sum(1 for inst in instances if inst.get('status') != 'healthy')
        
        # Scaling logic
        if unhealthy_count > total_instances * 0.3:  # More than 30% unhealthy
            return {
                'action': 'scale_up',
                'reason': f'{unhealthy_count}/{total_instances} instances unhealthy',
                'target_instances': min(total_instances + 2, 10),
                'urgency': 'high'
            }
        elif avg_cpu > 85 or avg_memory > 85 or avg_queue_size > 1000:
            return {
                'action': 'scale_up',
                'reason': f'High load: CPU {avg_cpu:.1f}%, Memory {avg_memory:.1f}%, Queue {avg_queue_size}',
                'target_instances': min(total_instances + 1, 10),
                'urgency': 'medium'
            }
        elif total_instances > 1 and avg_cpu < 30 and avg_memory < 50 and avg_queue_size < 100:
            return {
                'action': 'scale_down',
                'reason': f'Low load: CPU {avg_cpu:.1f}%, Memory {avg_memory:.1f}%, Queue {avg_queue_size}',
                'target_instances': max(total_instances - 1, 1),
                'urgency': 'low'
            }
        else:
            return {
                'action': 'maintain',
                'reason': 'Load within acceptable range',
                'target_instances': total_instances,
                'urgency': 'none'
            }
    
    async def _analyze_load_distribution(self, instances: List[Dict]) -> Dict[str, Any]:
        """Analyze load distribution across instances"""
        if not instances:
            return {}
        
        # Calculate load variance
        cpu_values = [inst.get('load_metrics', {}).get('cpu_percent', 0) for inst in instances]
        memory_values = [inst.get('load_metrics', {}).get('memory_percent', 0) for inst in instances]
        
        import statistics
        
        cpu_variance = statistics.variance(cpu_values) if len(cpu_values) > 1 else 0
        memory_variance = statistics.variance(memory_values) if len(memory_values) > 1 else 0
        
        # Find overloaded instances
        overloaded = [
            inst['instance_id'] for inst in instances
            if (inst.get('load_metrics', {}).get('cpu_percent', 0) > 90 or
                inst.get('load_metrics', {}).get('memory_percent', 0) > 90)
        ]
        
        # Find underutilized instances
        underutilized = [
            inst['instance_id'] for inst in instances
            if (inst.get('load_metrics', {}).get('cpu_percent', 0) < 20 and
                inst.get('load_metrics', {}).get('memory_percent', 0) < 30)
        ]
        
        return {
            'cpu_variance': round(cpu_variance, 2),
            'memory_variance': round(memory_variance, 2),
            'load_balance_score': self._calculate_load_balance_score(cpu_variance, memory_variance),
            'overloaded_instances': overloaded,
            'underutilized_instances': underutilized,
            'rebalancing_needed': len(overloaded) > 0 and len(underutilized) > 0
        }
    
    def _calculate_load_balance_score(self, cpu_variance: float, memory_variance: float) -> str:
        """Calculate load balance score (good/fair/poor)"""
        max_variance = max(cpu_variance, memory_variance)
        
        if max_variance < 100:
            return 'good'
        elif max_variance < 400:
            return 'fair'
        else:
            return 'poor'
    
    async def _update_scaling_metrics(self, load_metrics: Dict[str, Any]) -> None:
        """Update scaling metrics for dashboard"""
        try:
            scaling_data = {
                'instance_id': self.instance_id,
                'timestamp': datetime.utcnow().isoformat(),
                'metrics': load_metrics
            }
            
            # Store individual instance metrics
            await self.redis_client.lpush(
                f"{self.redis_keys['scaling_metrics']}:{self.instance_id}",
                json.dumps(scaling_data)
            )
            
            # Keep only last 100 entries per instance
            await self.redis_client.ltrim(
                f"{self.redis_keys['scaling_metrics']}:{self.instance_id}",
                0, 99
            )
            
        except Exception as e:
            logger.error(f"Failed to update scaling metrics: {e}")
    
    async def get_cluster_health_for_dashboard(self) -> Dict[str, Any]:
        """Get cluster health data formatted for the dynamic dashboard"""
        try:
            # Get aggregate health data
            aggregate_data = await self.redis_client.get(self.redis_keys['health_aggregate'])
            
            if not aggregate_data:
                return {
                    'service_name': 'signal_service',
                    'status': 'error',
                    'message': 'No health data available',
                    'instances': [],
                    'cluster_metrics': {}
                }
            
            health_data = json.loads(aggregate_data)
            
            # Format for dashboard
            dashboard_data = {
                'service_name': 'signal_service',
                'status': health_data['status'],
                'timestamp': health_data['timestamp'],
                'cluster_metrics': health_data['cluster_metrics'],
                'scaling_recommendation': health_data['scaling_recommendation'],
                'load_distribution': health_data['load_distribution'],
                'instances': [
                    {
                        'id': inst['instance_id'],
                        'name': inst['container_name'],
                        'host': inst['host'],
                        'status': inst['status'],
                        'uptime_seconds': inst['uptime_seconds'],
                        'cpu_percent': inst['load_metrics'].get('cpu_percent', 0),
                        'memory_percent': inst['load_metrics'].get('memory_percent', 0),
                        'requests_per_minute': inst['load_metrics'].get('requests_per_minute', 0),
                        'queue_size': inst['load_metrics'].get('queue_size', 0),
                        'assigned_instruments': inst['assigned_instruments_count']
                    }
                    for inst in health_data['instances']
                ]
            }
            
            return dashboard_data
            
        except Exception as e:
            logger.error(f"Failed to get cluster health for dashboard: {e}")
            return {
                'service_name': 'signal_service',
                'status': 'error',
                'message': f'Failed to retrieve health data: {e}',
                'instances': [],
                'cluster_metrics': {}
            }
    
    async def cleanup_dead_instances(self) -> None:
        """Remove dead instances from the registry"""
        try:
            instances_data = await self.redis_client.hgetall(self.redis_keys['instances'])
            current_time = datetime.utcnow()
            
            for instance_id, instance_json in instances_data.items():
                try:
                    instance = json.loads(instance_json)
                    last_heartbeat = datetime.fromisoformat(instance['last_heartbeat'])
                    
                    if (current_time - last_heartbeat).total_seconds() > self.instance_ttl:
                        await self.redis_client.hdel(self.redis_keys['instances'], instance_id)
                        logger.info(f"Cleaned up dead instance: {instance_id}")
                        
                except Exception as e:
                    logger.warning(f"Failed to check instance {instance_id}: {e}")
                    # Remove malformed data
                    await self.redis_client.hdel(self.redis_keys['instances'], instance_id)
                    
        except Exception as e:
            logger.error(f"Failed to cleanup dead instances: {e}")
    
    async def shutdown(self) -> None:
        """Gracefully shutdown and unregister this instance"""
        try:
            await self.redis_client.hdel(self.redis_keys['instances'], self.instance_id)
            logger.info(f"Unregistered instance {self.instance_id}")
        except Exception as e:
            logger.error(f"Failed to unregister instance: {e}")