"""
Production Consistent Hash Manager for Signal Service
Manages instrument assignments across multiple pods using consistent hashing
"""
import asyncio
import hashlib
import json
import logging
import time
from bisect import bisect_right

logger = logging.getLogger(__name__)


class ConsistentHashManager:
    """
    Production consistent hash ring implementation for distributing instruments across pods.

    Features:
    - Virtual nodes for better distribution
    - Node load tracking and rebalancing
    - Redis persistence for cluster coordination
    """

    def __init__(self, virtual_nodes: int = 150, redis_client=None):
        self.virtual_nodes = virtual_nodes
        self.redis_client = redis_client

        # Hash ring: hash_value -> node_id
        self.ring: dict[int, str] = {}
        self.sorted_keys: list[int] = []

        # Node tracking
        self.nodes: set[str] = set()
        self.node_loads: dict[str, float] = {}  # node_id -> load (0.0-1.0)

        # Redis keys for persistence
        self.redis_keys = {
            'ring': 'signal_service:hash_ring',
            'nodes': 'signal_service:nodes',
            'loads': 'signal_service:node_loads'
        }

        self._last_sync = 0
        self._sync_interval = 30  # seconds

        logger.info(f"ConsistentHashManager initialized with {virtual_nodes} virtual nodes")

    async def initialize(self):
        """Initialize the hash manager and sync with Redis"""
        if not self.redis_client:
            raise RuntimeError("Redis client required for production ConsistentHashManager")

        # Load existing state from Redis
        await self._load_from_redis()

        # Start background sync task
        asyncio.create_task(self._sync_with_redis())

        logger.info("ConsistentHashManager initialized successfully")

    async def _load_from_redis(self):
        """Load hash ring state from Redis"""
        try:
            # Load ring structure
            ring_data = await self.redis_client.get(self.redis_keys['ring'])
            if ring_data:
                ring_dict = json.loads(ring_data)
                self.ring = {int(k): v for k, v in ring_dict.items()}
                self.sorted_keys = sorted(self.ring.keys())

            # Load nodes
            nodes_data = await self.redis_client.get(self.redis_keys['nodes'])
            if nodes_data:
                self.nodes = set(json.loads(nodes_data))

            # Load node loads
            loads_data = await self.redis_client.get(self.redis_keys['loads'])
            if loads_data:
                self.node_loads = json.loads(loads_data)

            logger.info(f"Loaded hash ring state: {len(self.nodes)} nodes, {len(self.ring)} virtual nodes")

        except Exception as e:
            logger.error(f"Failed to load hash ring from Redis: {e}")
            # Continue with empty state

    async def _save_to_redis(self):
        """Save current hash ring state to Redis"""
        try:
            # Save ring structure
            ring_dict = {str(k): v for k, v in self.ring.items()}
            await self.redis_client.setex(
                self.redis_keys['ring'],
                300,  # 5 minutes
                json.dumps(ring_dict)
            )

            # Save nodes
            await self.redis_client.setex(
                self.redis_keys['nodes'],
                300,
                json.dumps(list(self.nodes))
            )

            # Save node loads
            await self.redis_client.setex(
                self.redis_keys['loads'],
                300,
                json.dumps(self.node_loads)
            )

        except Exception as e:
            logger.error(f"Failed to save hash ring to Redis: {e}")

    async def _sync_with_redis(self):
        """Background task to sync with Redis periodically"""
        while True:
            try:
                current_time = time.time()
                if current_time - self._last_sync > self._sync_interval:
                    await self._load_from_redis()
                    self._last_sync = current_time

                await asyncio.sleep(10)

            except Exception as e:
                logger.error(f"Hash ring sync error: {e}")
                await asyncio.sleep(30)

    def _hash(self, key: str) -> int:
        """Generate hash for a key"""
        return int(hashlib.md5(key.encode('utf-8')).hexdigest(), 16)

    def add_node(self, node_id: str):
        """Add a node to the hash ring"""
        if node_id in self.nodes:
            logger.warning(f"Node {node_id} already exists in ring")
            return

        self.nodes.add(node_id)
        self.node_loads[node_id] = 0.0

        # Add virtual nodes
        for i in range(self.virtual_nodes):
            virtual_key = f"{node_id}:{i}"
            hash_value = self._hash(virtual_key)
            self.ring[hash_value] = node_id

        # Rebuild sorted keys
        self.sorted_keys = sorted(self.ring.keys())

        logger.info(f"Added node {node_id} to hash ring ({len(self.nodes)} total nodes)")

        # Save to Redis asynchronously
        asyncio.create_task(self._save_to_redis())

    def remove_node(self, node_id: str):
        """Remove a node from the hash ring"""
        if node_id not in self.nodes:
            logger.warning(f"Node {node_id} not found in ring")
            return

        self.nodes.remove(node_id)
        self.node_loads.pop(node_id, None)

        # Remove virtual nodes
        keys_to_remove = [k for k, v in self.ring.items() if v == node_id]
        for key in keys_to_remove:
            del self.ring[key]

        # Rebuild sorted keys
        self.sorted_keys = sorted(self.ring.keys())

        logger.info(f"Removed node {node_id} from hash ring ({len(self.nodes)} total nodes)")

        # Save to Redis asynchronously
        asyncio.create_task(self._save_to_redis())

    def get_node(self, key: str, exclude_nodes: list[str] | None = None) -> str | None:
        """Get the primary node for a key"""
        if not self.ring:
            return None

        exclude_set = set(exclude_nodes) if exclude_nodes else set()
        hash_value = self._hash(key)

        # Find the first node clockwise from the hash value
        idx = bisect_right(self.sorted_keys, hash_value)

        # Try nodes starting from the calculated position
        for i in range(len(self.sorted_keys)):
            actual_idx = (idx + i) % len(self.sorted_keys)
            ring_key = self.sorted_keys[actual_idx]
            node_id = self.ring[ring_key]

            if node_id not in exclude_set:
                return node_id

        # If all nodes are excluded, return None
        return None

    def get_nodes(self, key: str, count: int = 1, exclude_nodes: list[str] | None = None) -> list[str]:
        """Get multiple nodes for a key (for replication)"""
        if not self.ring or count <= 0:
            return []

        exclude_set = set(exclude_nodes) if exclude_nodes else set()
        hash_value = self._hash(key)

        # Find the first node clockwise from the hash value
        idx = bisect_right(self.sorted_keys, hash_value)

        selected_nodes = []
        seen_nodes = set()

        # Iterate through ring to find unique nodes
        for i in range(len(self.sorted_keys)):
            if len(selected_nodes) >= count:
                break

            actual_idx = (idx + i) % len(self.sorted_keys)
            ring_key = self.sorted_keys[actual_idx]
            node_id = self.ring[ring_key]

            # Skip if already seen or excluded
            if node_id in seen_nodes or node_id in exclude_set:
                continue

            selected_nodes.append(node_id)
            seen_nodes.add(node_id)

        return selected_nodes

    async def update_node_load(self, node_id: str, load: float):
        """Update the load for a node"""
        if node_id not in self.nodes:
            logger.warning(f"Cannot update load for unknown node: {node_id}")
            return

        # Clamp load between 0.0 and 1.0
        load = max(0.0, min(1.0, load))
        self.node_loads[node_id] = load

        logger.debug(f"Updated load for node {node_id}: {load:.2f}")

        # Save to Redis asynchronously (debounced)
        asyncio.create_task(self._debounced_save())

    async def _debounced_save(self):
        """Debounced save to Redis to avoid too frequent updates"""
        await asyncio.sleep(5)  # Wait 5 seconds before saving
        await self._save_to_redis()

    def get_node_loads(self) -> dict[str, float]:
        """Get current load for all nodes"""
        return dict(self.node_loads)

    def get_least_loaded_node(self, exclude_nodes: list[str] | None = None) -> str | None:
        """Get the node with the lowest load"""
        exclude_set = set(exclude_nodes) if exclude_nodes else set()

        available_nodes = {
            node_id: load for node_id, load in self.node_loads.items()
            if node_id not in exclude_set and node_id in self.nodes
        }

        if not available_nodes:
            return None

        return min(available_nodes.items(), key=lambda x: x[1])[0]

    def get_load_distribution(self) -> dict[str, any]:
        """Get load distribution statistics"""
        if not self.node_loads:
            return {}

        loads = list(self.node_loads.values())
        return {
            'nodes': len(self.nodes),
            'virtual_nodes': len(self.ring),
            'avg_load': sum(loads) / len(loads),
            'max_load': max(loads),
            'min_load': min(loads),
            'load_variance': sum((x - sum(loads) / len(loads)) ** 2 for x in loads) / len(loads),
            'per_node_loads': dict(self.node_loads)
        }

    def rebalance_needed(self, threshold: float = 0.3) -> bool:
        """Check if rebalancing is needed based on load variance"""
        if len(self.nodes) < 2:
            return False

        loads = list(self.node_loads.values())
        if not loads:
            return False

        max_load = max(loads)
        min_load = min(loads)
        load_diff = max_load - min_load

        return load_diff > threshold

    def get_rebalance_suggestions(self) -> list[tuple[str, str]]:
        """Get suggestions for rebalancing (source_node, target_node)"""
        if not self.rebalance_needed():
            return []

        # Sort nodes by load
        sorted_nodes = sorted(self.node_loads.items(), key=lambda x: x[1])

        suggestions = []

        # Suggest moving load from highest to lowest loaded nodes
        for i in range(min(3, len(sorted_nodes) // 2)):  # Limit suggestions
            high_load_node = sorted_nodes[-(i+1)][0]  # Most loaded
            low_load_node = sorted_nodes[i][0]  # Least loaded

            suggestions.append((high_load_node, low_load_node))

        return suggestions
