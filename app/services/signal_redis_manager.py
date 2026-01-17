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


class SignalRedisManager:
    """Signal Service specific Redis manager (single Redis instance)."""

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
        logger.info("SignalRedisManager initialized")

    async def initialize(self):
        """Initialize Redis connection"""
        try:
            if not self.redis_client:
                self.redis_client = await get_redis_client()
            logger.info("SignalRedisManager connected to Redis")
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
            await self.redis_client.setex(key, ttl, worker_id)
            return True
        except Exception as e:
            log_error(f"Failed to set worker assignment for {symbol}: {e}")
            return False
    
    async def get_worker_assignment(self, symbol: str) -> Optional[str]:
        """Get worker assignment for a symbol"""
        try:
            key = self.key_patterns["worker_assignment"].format(symbol=symbol)
            result = await self.redis_client.get(key)
            return result if result else None
        except Exception as e:
            log_error(f"Failed to get worker assignment for {symbol}: {e}")
            return None
    
    async def register_worker(self, worker_id: str, worker_info: Dict[str, Any]) -> bool:
        """Register a worker in the cluster"""
        try:
            # Use hash for worker registry
            await self.redis_client.hset(
                self.key_patterns["worker_registry"],
                worker_id,
                json.dumps(worker_info)
            )
            return True
        except Exception as e:
            log_error(f"Failed to register worker {worker_id}: {e}")
            return False
    
    async def update_worker_heartbeat(self, worker_id: str, heartbeat_data: Dict[str, Any]) -> bool:
        """Update worker heartbeat with TTL"""
        try:
            key = self.key_patterns["worker_heartbeat"].format(worker_id=worker_id)
            await self.redis_client.setex(
                key,
                30,  # 30 second TTL
                json.dumps(heartbeat_data)
            )
            return True
        except Exception as e:
            log_error(f"Failed to update worker heartbeat: {e}")
            return False
    
    async def get_healthy_workers(self) -> List[Dict[str, Any]]:
        """Get all healthy workers from Redis"""
        try:
            # Get all registered workers
            workers_data = await self.redis_client.hgetall(self.key_patterns["worker_registry"])
            healthy_workers = []
            
            if workers_data:
                for worker_id, info_json in workers_data.items():
                    # Check heartbeat
                    heartbeat_key = self.key_patterns["worker_heartbeat"].format(worker_id=worker_id)
                    heartbeat_json = await self.redis_client.get(heartbeat_key)
                    
                    if heartbeat_json:
                        try:
                            worker_info = json.loads(info_json)
                            heartbeat_data = json.loads(heartbeat_json)
                            worker_info['worker_id'] = worker_id
                            worker_info['heartbeat'] = heartbeat_data
                            healthy_workers.append(worker_info)
                        except json.JSONDecodeError:
                            log_error(f"Invalid JSON for worker {worker_id}")
            
            return healthy_workers
            
        except Exception as e:
            log_error(f"Failed to get healthy workers: {e}")
            from app.errors import WorkerRegistryError
            raise WorkerRegistryError(f"Failed to retrieve workers: {str(e)}") from e from e
    
    async def add_symbol_to_worker(self, worker_id: str, symbol: str) -> bool:
        """Add a symbol to worker's assigned symbols set using Redis SADD"""
        try:
            key = self.key_patterns["worker_symbols"].format(worker_id=worker_id)
            await self.redis_client.sadd(key, symbol)
            return True
        except Exception as e:
            log_error(f"Failed to add symbol to worker: {e}")
            return False
    
    async def remove_symbol_from_worker(self, worker_id: str, symbol: str) -> bool:
        """Remove a symbol from worker's assigned symbols set using Redis SREM"""
        try:
            key = self.key_patterns["worker_symbols"].format(worker_id=worker_id)
            result = await self.redis_client.srem(key, symbol)
            return result > 0
        except Exception as e:
            log_error(f"Failed to remove symbol from worker: {e}")
            return False
    
    async def get_worker_symbols(self, worker_id: str) -> Set[str]:
        """Get all symbols assigned to a worker using Redis SMEMBERS"""
        try:
            key = self.key_patterns["worker_symbols"].format(worker_id=worker_id)
            members = await self.redis_client.smembers(key)
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
            await self.redis_client.setex(
                key,
                3600,  # 1 hour TTL
                json.dumps(state)
            )
            return True
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
            result = await self.redis_client.get(key)
            if result:
                return json.loads(result)
            return None
        except Exception as e:
            log_error(f"Failed to get indicator state: {e}")
            return None
    
    async def publish_computation_result(self, symbol: str, result: Dict[str, Any]) -> bool:
        """Publish computation result to symbol-specific stream"""
        try:
            stream_key = self.streams["computation_results"].format(symbol=symbol)
            await self.redis_client.xadd(
                stream_key,
                {"result": json.dumps(result), "timestamp": datetime.utcnow().isoformat()},
                maxlen=1000  # Keep last 1000 results
            )
            return True
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
            except Exception as e:
                # Only ignore BUSYGROUP error, log all others
                error_str = str(e).upper()
                if 'BUSYGROUP' not in error_str:
                    log_error(f"Failed to create consumer group for {stream_key}: {e}")
                # BUSYGROUP means group already exists, which is expected
            
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
                    except Exception as e:
                        log_error(f"Failed to parse message {msg_id}: {e}")
                        continue  # Skip malformed messages
            
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
            await self.redis_client.hdel(self.key_patterns["worker_registry"], worker_id)
            
            # Get and release all assigned symbols
            symbols = await self.get_worker_symbols(worker_id)
            for symbol in symbols:
                assignment_key = self.key_patterns["worker_assignment"].format(symbol=symbol)
                current_worker = await self.redis_client.get(assignment_key)
                if current_worker and current_worker == worker_id:
                    await self.redis_client.delete(assignment_key)
            
            # Delete worker-specific keys
            symbols_key = self.key_patterns["worker_symbols"].format(worker_id=worker_id)
            heartbeat_key = self.key_patterns["worker_heartbeat"].format(worker_id=worker_id)
            
            await self.redis_client.delete(symbols_key, heartbeat_key)
            
            return True
            
        except Exception as e:
            log_error(f"Failed to cleanup worker {worker_id}: {e}")
            return False


# Global instance
signal_redis_manager = SignalRedisManager()
