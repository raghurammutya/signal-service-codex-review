"""
Redis Manager for Signal Service
Provides cluster-aware Redis operations with proper key patterns
"""

from typing import Dict, List, Optional, Any, Set
import json
from datetime import datetime, timedelta

import logging
from app.core.config import settings
from app.utils.redis import get_redis_client

logger = logging.getLogger(__name__)


def log_info(message):
    logger.info(message)


def log_error(message):
    logger.error(message)


class RedisClusterManager:
    """Simple Redis cluster manager for Signal Service."""
    
    def __init__(self, redis_client):
        self.redis_client = redis_client
        
    async def store_with_expiry(self, key: str, value: Any, ttl: int) -> bool:
        """Store value with expiry."""
        try:
            await self.redis_client.setex(key, ttl, value)
            return True
        except Exception as e:
            log_error(f"Failed to store with expiry {key}: {e}")
            return False
    
    async def get_value(self, key: str) -> Optional[str]:
        """Get value from Redis."""
        try:
            return await self.redis_client.get(key)
        except Exception as e:
            log_error(f"Failed to get value {key}: {e}")
            return None
    
    async def hash_set(self, key: str, field: str, value: Any) -> bool:
        """Set hash field."""
        try:
            await self.redis_client.hset(key, field, value)
            return True
        except Exception as e:
            log_error(f"Failed to hash set {key}:{field}: {e}")
            return False
    
    async def hash_get_all(self, key: str) -> Dict[str, Any]:
        """Get all hash fields."""
        try:
            return await self.redis_client.hgetall(key)
        except Exception as e:
            log_error(f"Failed to hash get all {key}: {e}")
            return {}
    
    async def hash_delete(self, key: str, field: str) -> bool:
        """Delete hash field."""
        try:
            await self.redis_client.hdel(key, field)
            return True
        except Exception as e:
            log_error(f"Failed to hash delete {key}:{field}: {e}")
            return False
    
    async def get_json(self, key: str) -> Optional[Dict[str, Any]]:
        """Get JSON value."""
        try:
            value = await self.redis_client.get(key)
            if value:
                return json.loads(value)
            return None
        except Exception as e:
            log_error(f"Failed to get JSON {key}: {e}")
            return None
    
    async def store_json_with_expiry(self, key: str, value: Dict[str, Any], ttl: int) -> bool:
        """Store JSON with expiry."""
        try:
            await self.redis_client.setex(key, ttl, json.dumps(value))
            return True
        except Exception as e:
            log_error(f"Failed to store JSON with expiry {key}: {e}")
            return False
    
    async def set_add(self, key: str, value: Any) -> bool:
        """Add to set."""
        try:
            # Use list since fake Redis doesn't have sets
            current = await self.redis_client.get(key)
            if current:
                try:
                    items = json.loads(current)
                    if not isinstance(items, list):
                        items = []
                except:
                    items = []
            else:
                items = []
            
            if value not in items:
                items.append(value)
            
            await self.redis_client.set(key, json.dumps(items))
            return True
        except Exception as e:
            log_error(f"Failed to set add {key}: {e}")
            return False
    
    async def set_remove(self, key: str, value: Any) -> bool:
        """Remove from set."""
        try:
            current = await self.redis_client.get(key)
            if current:
                try:
                    items = json.loads(current)
                    if isinstance(items, list) and value in items:
                        items.remove(value)
                        await self.redis_client.set(key, json.dumps(items))
                except json.JSONDecodeError as e:
                    logger.warning(f"Failed to parse JSON for key {key}: {e}")
                except Exception as e:
                    logger.error(f"Failed to process list operation for key {key}: {e}")
            return True
        except Exception as e:
            log_error(f"Failed to set remove {key}: {e}")
            return False
    
    async def set_members(self, key: str) -> List[str]:
        """Get set members."""
        try:
            current = await self.redis_client.get(key)
            if current:
                try:
                    items = json.loads(current)
                    return items if isinstance(items, list) else []
                except:
                    return []
            return []
        except Exception as e:
            log_error(f"Failed to get set members {key}: {e}")
            return []
    
    async def delete_key(self, key: str) -> bool:
        """Delete key."""
        try:
            await self.redis_client.delete(key)
            return True
        except Exception as e:
            log_error(f"Failed to delete key {key}: {e}")
            return False
    
    async def stream_add(self, stream_key: str, fields: Dict[str, Any], maxlen: Optional[int] = None) -> bool:
        """Add to stream."""
        try:
            await self.redis_client.xadd(stream_key, fields, maxlen=maxlen)
            return True
        except Exception as e:
            log_error(f"Failed to add to stream {stream_key}: {e}")
            return False


class SignalRedisManager:
    """Signal Service specific Redis manager."""

    def __init__(self):
        # Define signal service specific key patterns with hash tags for cluster
        self.key_patterns = {
            # Worker affinity keys - grouped by symbol
            "worker_assignment": "signal:workers:{symbol}:assignment",
            "worker_registry": "signal:workers:registry",
            "worker_heartbeat": "signal:workers:{worker_id}:heartbeat",
            "worker_symbols": "signal:workers:{worker_id}:symbols",

            # Indicator computation keys - grouped by symbol
            "indicator_state": "signal:indicator:{symbol}:{indicator}:state",
            "indicator_result": "signal:indicator:{symbol}:{indicator}:result",
            "indicator_subscription": "signal:indicator:{symbol}:subscriptions",

            # Configuration keys - grouped by user
            "user_config": "signal:config:{user_id}:settings",
            "user_subscriptions": "signal:config:{user_id}:subscriptions",

            # Computation queue - grouped by priority
            "computation_queue": "signal:queue:{priority}:computations",
            "computation_results": "signal:queue:{symbol}:results",

            # Rate limiting - grouped by user
            "rate_limit": "signal:ratelimit:{user_id}:{endpoint}",

            # Cache keys - grouped by data type
            "cache_greeks": "signal:cache:{symbol}:greeks",
            "cache_indicators": "signal:cache:{symbol}:indicators",
            "cache_moneyness": "signal:cache:{symbol}:moneyness",
        }

        # Stream names with hash tags
        self.streams = {
            "tick_data": "signal:stream:{symbol}:ticks",
            "indicator_requests": "signal:stream:{priority}:requests",
            "computation_results": "signal:stream:{symbol}:results",
            "config_updates": "signal:stream:{user_id}:config",
        }

        self.redis_client = None
        self.cluster_manager = None
        logger.info("SignalRedisManager initialized")

    async def initialize(self):
        """Initialize Redis connection and cluster manager"""
        try:
            if not self.redis_client:
                self.redis_client = await get_redis_client()
            
            # Initialize cluster manager
            if not self.cluster_manager:
                self.cluster_manager = RedisClusterManager(self.redis_client)
            
            logger.info("SignalRedisManager connected to Redis with cluster manager")
        except Exception as e:
            logger.error(f"Failed to initialize SignalRedisManager: {e}")
            raise
    
    async def initialize_service_data(self):
        """Initialize signal service specific data in Redis"""
        try:
            # Initialize any default data structures if needed
            log_info("Signal service Redis data initialized")
        except Exception as e:
            logger.error(f"Failed to initialize signal service data: {e}")
    
    async def set_worker_assignment(self, symbol: str, worker_id: str, ttl: int = 300) -> bool:
        """Assign a symbol to a worker with TTL"""
        try:
            key = self.key_patterns["worker_assignment"].format(symbol=symbol)
            return await self.cluster_manager.store_with_expiry(key, worker_id, ttl)
        except Exception as e:
            log_error(f"Failed to set worker assignment for {symbol}: {e}")
            return False
    
    async def get_worker_assignment(self, symbol: str) -> Optional[str]:
        """Get worker assignment for a symbol"""
        try:
            key = self.key_patterns["worker_assignment"].format(symbol=symbol)
            result = await self.cluster_manager.get_value(key)
            return result if result else None
        except Exception as e:
            log_error(f"Failed to get worker assignment for {symbol}: {e}")
            return None
    
    async def register_worker(self, worker_id: str, worker_info: Dict[str, Any]) -> bool:
        """Register a worker in the cluster"""
        try:
            # Use hash for worker registry to keep all workers in same slot
            return await self.cluster_manager.hash_set(
                self.key_patterns["worker_registry"],
                worker_id,
                json.dumps(worker_info)
            )
        except Exception as e:
            log_error(f"Failed to register worker {worker_id}: {e}")
            return False
    
    async def update_worker_heartbeat(self, worker_id: str, heartbeat_data: Dict[str, Any]) -> bool:
        """Update worker heartbeat with cluster-aware key"""
        try:
            key = self.key_patterns["worker_heartbeat"].format(worker_id=worker_id)
            return await self.cluster_manager.store_json_with_expiry(
                key,
                heartbeat_data,
                30  # 30 second TTL
            )
        except Exception as e:
            log_error(f"Failed to update worker heartbeat: {e}")
            return False
    
    async def get_healthy_workers(self) -> List[Dict[str, Any]]:
        """Get all healthy workers from the cluster"""
        try:
            # Get all registered workers
            workers_data = await self.cluster_manager.hash_get_all(self.key_patterns["worker_registry"])
            healthy_workers = []
            
            if workers_data:
                for worker_id, info_json in workers_data.items():
                    # Check heartbeat
                    heartbeat_key = self.key_patterns["worker_heartbeat"].format(worker_id=worker_id)
                    heartbeat_data = await self.cluster_manager.get_json(heartbeat_key)
                    
                    if heartbeat_data:
                        worker_info = json.loads(info_json)
                        worker_info['worker_id'] = worker_id
                        worker_info['heartbeat'] = heartbeat_data
                        healthy_workers.append(worker_info)
            
            return healthy_workers
            
        except Exception as e:
            log_error(f"Failed to get healthy workers: {e}")
            from app.errors import WorkerRegistryError
            raise WorkerRegistryError(f"Failed to retrieve workers: {str(e)}") from e
    
    async def add_symbol_to_worker(self, worker_id: str, symbol: str) -> bool:
        """Add a symbol to worker's assigned symbols set"""
        try:
            key = self.key_patterns["worker_symbols"].format(worker_id=worker_id)
            return await self.cluster_manager.set_add(key, symbol)
        except Exception as e:
            log_error(f"Failed to add symbol to worker: {e}")
            return False
    
    async def remove_symbol_from_worker(self, worker_id: str, symbol: str) -> bool:
        """Remove a symbol from worker's assigned symbols set"""
        try:
            key = self.key_patterns["worker_symbols"].format(worker_id=worker_id)
            return await self.cluster_manager.set_remove(key, symbol)
        except Exception as e:
            log_error(f"Failed to remove symbol from worker: {e}")
            return False
    
    async def get_worker_symbols(self, worker_id: str) -> Set[str]:
        """Get all symbols assigned to a worker"""
        try:
            key = self.key_patterns["worker_symbols"].format(worker_id=worker_id)
            members = await self.cluster_manager.set_members(key)
            return set(members) if members else set()
        except Exception as e:
            log_error(f"Failed to get worker symbols: {e}")
            return set()
    
    async def store_indicator_state(self, symbol: str, indicator: str, state: Dict[str, Any]) -> bool:
        """Store indicator computation state"""
        try:
            key = self.key_patterns["indicator_state"].format(
                symbol=symbol,
                indicator=indicator
            )
            return await self.cluster_manager.store_json_with_expiry(
                key,
                state,
                3600  # 1 hour TTL
            )
        except Exception as e:
            log_error(f"Failed to store indicator state: {e}")
            return False
    
    async def get_indicator_state(self, symbol: str, indicator: str) -> Optional[Dict[str, Any]]:
        """Get indicator computation state"""
        try:
            key = self.key_patterns["indicator_state"].format(
                symbol=symbol,
                indicator=indicator
            )
            return await self.cluster_manager.get_json(key)
        except Exception as e:
            log_error(f"Failed to get indicator state: {e}")
            return None
    
    async def publish_computation_result(self, symbol: str, result: Dict[str, Any]) -> bool:
        """
        Publish computation result to symbol-specific stream.
        
        Note: For user notifications, also use SignalDeliveryService.deliver_signal() 
        to ensure proper entitlement validation and delivery through multiple channels.
        This method only handles internal stream publishing for service coordination.
        """
        try:
            stream_key = self.streams["computation_results"].format(symbol=symbol)
            return await self.cluster_manager.stream_add(
                stream_key,
                {"result": json.dumps(result), "timestamp": datetime.utcnow().isoformat()},
                maxlen=1000  # Keep last 1000 results
            )
        except Exception as e:
            log_error(f"Failed to publish computation result: {e}")
            return False
    
    async def consume_computation_requests(self, priority: str, consumer_group: str, consumer_name: str) -> List[Dict[str, Any]]:
        """Consume computation requests from priority-based stream"""
        try:
            stream_key = self.streams["indicator_requests"].format(priority=priority)
            
            # Create consumer group if needed
            try:
                await self.redis_client.xgroup_create(stream_key, consumer_group, id="0")
            except:
                pass  # Group already exists
            
            # Read messages
            messages = await self.redis_client.xreadgroup(
                consumer_group,
                consumer_name,
                {stream_key: ">"},
                count=10,
                block=1000  # 1 second timeout
            )
            
            results = []
            for stream, stream_messages in messages:
                for msg_id, data in stream_messages:
                    try:
                        results.append({
                            "id": msg_id.decode('utf-8'),
                            "data": json.loads(data[b"request"].decode('utf-8'))
                        })
                    except (json.JSONDecodeError, UnicodeDecodeError, KeyError) as e:
                        logger.warning(f"Failed to parse stream message {msg_id}: {e}")
                    except Exception as e:
                        logger.error(f"Unexpected error processing stream message {msg_id}: {e}")
            
            return results
            
        except Exception as e:
            if "MOVED" not in str(e):  # Don't log MOVED errors
                log_error(f"Failed to consume computation requests: {e}")
                from app.errors import ConsumerError
                raise ConsumerError(f"Failed to consume requests: {str(e)}") from e
            return []
    
    async def cleanup_worker(self, worker_id: str) -> bool:
        """Cleanup all data for a worker"""
        try:
            # Remove from registry
            await self.cluster_manager.hash_delete(self.key_patterns["worker_registry"], worker_id)
            
            # Get and release all assigned symbols
            symbols = await self.get_worker_symbols(worker_id)
            for symbol in symbols:
                assignment_key = self.key_patterns["worker_assignment"].format(symbol=symbol)
                current_worker = await self.cluster_manager.get_value(assignment_key)
                if current_worker and current_worker == worker_id:
                    await self.cluster_manager.delete_key(assignment_key)
            
            # Delete worker-specific keys
            symbols_key = self.key_patterns["worker_symbols"].format(worker_id=worker_id)
            heartbeat_key = self.key_patterns["worker_heartbeat"].format(worker_id=worker_id)
            
            await self.cluster_manager.delete_key(symbols_key)
            await self.cluster_manager.delete_key(heartbeat_key)
            
            return True
            
        except Exception as e:
            log_error(f"Failed to cleanup worker {worker_id}: {e}")
            return False


# Global instance
signal_redis_manager = SignalRedisManager()
