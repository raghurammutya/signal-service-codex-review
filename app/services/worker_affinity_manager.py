"""
Worker Affinity Manager for Horizontal Scaling
Ensures same worker handles same stock for performance optimization
"""

import asyncio
import hashlib
import os
import socket
import time
from dataclasses import dataclass, field
from datetime import datetime

from app.services.signal_redis_manager import signal_redis_manager
from app.services.ticker_stream_consumer import TickerChannelSubscriber, TickerStreamConsumer
from app.utils.logging_utils import log_error, log_info, log_warning


@dataclass
class WorkerInfo:
    """Information about a worker instance"""
    worker_id: str
    hostname: str
    process_id: int
    started_at: datetime
    last_heartbeat: datetime
    assigned_symbols: set[str] = field(default_factory=set)
    active_computations: int = 0
    capacity: int = 100  # Max computations per worker

    @property
    def is_healthy(self) -> bool:
        """Check if worker is healthy based on heartbeat"""
        return (datetime.utcnow() - self.last_heartbeat).seconds < 30

    @property
    def load_factor(self) -> float:
        """Calculate current load factor (0.0 to 1.0)"""
        return self.active_computations / self.capacity


class WorkerAffinityManager:
    """
    Manages worker affinity for symbols to ensure consistent routing
    and optimal cache utilization in horizontally scaled deployments
    """

    def __init__(self, worker_id: str | None = None):
        self.redis_manager = signal_redis_manager
        self.worker_id = worker_id or self._generate_worker_id()
        self.hostname = socket.gethostname()
        self.process_id = os.getpid()

        # Local state
        self.assigned_symbols: set[str] = set()
        self.symbol_locks: dict[str, asyncio.Lock] = {}
        self.last_heartbeat = datetime.utcnow()

        # Ticker consumers
        self.stream_consumer: TickerStreamConsumer | None = None
        self.channel_subscriber: TickerChannelSubscriber | None = None

        # Configuration
        self.rebalance_interval = 60  # seconds
        self.heartbeat_interval = 10  # seconds
        self.assignment_ttl = 300  # 5 minutes
        self.enable_stream_consumer = True  # Use stream-based consumption
        self.enable_channel_subscriber = False  # Optional real-time channel subscription

        log_info(f"WorkerAffinityManager initialized: {self.worker_id}")

    async def initialize(self):
        """Initialize Redis connection and register worker"""
        try:
            await self.redis_manager.initialize()
            await self._register_worker()

            # Initialize ticker consumers
            if self.enable_stream_consumer:
                self.stream_consumer = TickerStreamConsumer(
                    self.worker_id,
                    self.assigned_symbols
                )
                asyncio.create_task(self.stream_consumer.start_consuming())
                log_info(f"Started ticker stream consumer for worker {self.worker_id}")

            if self.enable_channel_subscriber:
                self.channel_subscriber = TickerChannelSubscriber(
                    self.worker_id,
                    self.assigned_symbols
                )
                await self.channel_subscriber.start_subscribing()
                log_info(f"Started ticker channel subscriber for worker {self.worker_id}")

            # Start background tasks
            asyncio.create_task(self._heartbeat_loop())
            asyncio.create_task(self._rebalance_loop())

            log_info(f"Worker {self.worker_id} registered and initialized with ticker consumers")
        except Exception as e:
            log_error(f"Failed to initialize WorkerAffinityManager: {e}")
            raise

    def _generate_worker_id(self) -> str:
        """Generate unique worker ID"""
        timestamp = int(time.time() * 1000)
        random_part = hashlib.md5(os.urandom(16)).hexdigest()[:8]
        return f"worker_{timestamp}_{random_part}"

    async def _register_worker(self):
        """Register this worker in Redis"""
        worker_info = {
            "worker_id": self.worker_id,
            "hostname": self.hostname,
            "process_id": self.process_id,
            "started_at": datetime.utcnow().isoformat(),
            "capacity": 100,
            "version": "1.0.0"
        }

        # Register worker using cluster-aware manager
        await self.redis_manager.register_worker(self.worker_id, worker_info)

        # Set initial heartbeat
        await self._update_heartbeat()

    async def _update_heartbeat(self):
        """Update worker heartbeat in Redis"""
        heartbeat_data = {
            "timestamp": datetime.utcnow().isoformat(),
            "active_computations": len(self.assigned_symbols),
            "load_factor": len(self.assigned_symbols) / 100
        }

        await self.redis_manager.update_worker_heartbeat(self.worker_id, heartbeat_data)

        self.last_heartbeat = datetime.utcnow()

    async def _heartbeat_loop(self):
        """Background task to maintain worker heartbeat"""
        while True:
            try:
                await self._update_heartbeat()
                await asyncio.sleep(self.heartbeat_interval)
            except Exception as e:
                log_error(f"Heartbeat error: {e}")
                await asyncio.sleep(5)

    async def get_worker_for_symbol(self, symbol: str) -> str:
        """
        Get worker assignment for a symbol, creating new assignment if needed
        Returns worker_id that should handle this symbol
        """
        try:
            # Check existing assignment using cluster-aware manager
            assigned_worker = await self.redis_manager.get_worker_assignment(symbol)

            if assigned_worker:
                # Verify worker is still healthy
                if await self._is_worker_healthy(assigned_worker):
                    return assigned_worker
                log_warning(f"Assigned worker {assigned_worker} for {symbol} is unhealthy")

            # Need new assignment
            return await self._assign_symbol_to_worker(symbol)

        except Exception as e:
            log_error(f"Error getting worker for symbol {symbol}: {e}")
            # Fallback to self
            return self.worker_id

    async def _is_worker_healthy(self, worker_id: str) -> bool:
        """Check if a worker is healthy"""
        # Check if worker has recent heartbeat
        workers = await self.redis_manager.get_healthy_workers()
        return any(w['worker_id'] == worker_id for w in workers)

    async def _assign_symbol_to_worker(self, symbol: str) -> str:
        """Assign symbol to least loaded healthy worker"""
        try:
            # Get all healthy workers
            workers_data = await self.redis_manager.get_healthy_workers()

            if not workers_data:
                # No healthy workers, assign to self
                await self._claim_symbol(symbol)
                return self.worker_id

            # Convert to WorkerInfo objects and find least loaded
            workers = []
            for w in workers_data:
                worker = WorkerInfo(
                    worker_id=w['worker_id'],
                    hostname=w['hostname'],
                    process_id=w['process_id'],
                    started_at=datetime.fromisoformat(w['started_at']),
                    last_heartbeat=datetime.utcnow(),
                    active_computations=w['heartbeat'].get('active_computations', 0),
                    capacity=w.get('capacity', 100)
                )
                workers.append(worker)

            # Find least loaded worker
            best_worker = min(workers, key=lambda w: w.load_factor)

            # Assign symbol using cluster-aware manager
            await self.redis_manager.set_worker_assignment(
                symbol,
                best_worker.worker_id,
                ttl=self.assignment_ttl
            )

            log_info(f"Assigned {symbol} to worker {best_worker.worker_id}")

            # If assigned to self, update local state
            if best_worker.worker_id == self.worker_id:
                await self._claim_symbol(symbol)

            return best_worker.worker_id

        except Exception as e:
            log_error(f"Error assigning symbol {symbol}: {e}")
            return self.worker_id


    async def _claim_symbol(self, symbol: str):
        """Claim a symbol for this worker"""
        self.assigned_symbols.add(symbol)

        # Add to worker's symbol set in Redis
        await self.redis_manager.add_symbol_to_worker(self.worker_id, symbol)

        # Update ticker consumers
        if self.stream_consumer:
            await self.stream_consumer.update_assigned_symbols(self.assigned_symbols)
        if self.channel_subscriber:
            await self.channel_subscriber.update_subscriptions(self.assigned_symbols)

        # Create lock for symbol if needed
        if symbol not in self.symbol_locks:
            self.symbol_locks[symbol] = asyncio.Lock()

        log_info(f"Worker {self.worker_id} claimed symbol {symbol}")

    async def _release_symbol(self, symbol: str):
        """Release a symbol from this worker"""
        self.assigned_symbols.discard(symbol)

        # Remove from worker's symbol set
        await self.redis_manager.remove_symbol_from_worker(self.worker_id, symbol)

        # Update ticker consumers
        if self.stream_consumer:
            await self.stream_consumer.update_assigned_symbols(self.assigned_symbols)
        if self.channel_subscriber:
            await self.channel_subscriber.update_subscriptions(self.assigned_symbols)

        log_info(f"Worker {self.worker_id} released symbol {symbol}")

    async def _rebalance_loop(self):
        """Background task to rebalance symbol assignments"""
        await asyncio.sleep(30)  # Initial delay

        while True:
            try:
                await self._rebalance_assignments()
                await asyncio.sleep(self.rebalance_interval)
            except Exception as e:
                log_error(f"Rebalance error: {e}")
                await asyncio.sleep(30)

    async def _rebalance_assignments(self):
        """Rebalance symbol assignments across workers"""
        try:
            workers_data = await self.redis_manager.get_healthy_workers()

            if len(workers_data) <= 1:
                return  # No rebalancing needed

            # Convert to WorkerInfo objects
            workers = []
            for w in workers_data:
                worker = WorkerInfo(
                    worker_id=w['worker_id'],
                    hostname=w['hostname'],
                    process_id=w['process_id'],
                    started_at=datetime.fromisoformat(w['started_at']),
                    last_heartbeat=datetime.utcnow(),
                    active_computations=w['heartbeat'].get('active_computations', 0),
                    capacity=w.get('capacity', 100)
                )
                workers.append(worker)

            # Calculate average load
            total_symbols = sum(w.active_computations for w in workers)
            avg_load = total_symbols / len(workers)

            # Find overloaded and underloaded workers
            overloaded = [w for w in workers if w.active_computations > avg_load * 1.2]
            underloaded = [w for w in workers if w.active_computations < avg_load * 0.8]

            if not overloaded or not underloaded:
                return  # System is balanced

            log_info(f"Rebalancing: {len(overloaded)} overloaded, {len(underloaded)} underloaded workers")

            # Move symbols from overloaded to underloaded workers
            # (Implementation simplified for brevity)

        except Exception as e:
            log_error(f"Rebalance failed: {e}")

    async def should_handle_computation(self, symbol: str) -> bool:
        """
        Check if this worker should handle computation for given symbol
        Used by signal service to filter incoming requests
        """
        assigned_worker = await self.get_worker_for_symbol(symbol)
        return assigned_worker == self.worker_id

    async def acquire_symbol_lock(self, symbol: str) -> asyncio.Lock:
        """
        Get lock for symbol to ensure thread-safe operations
        """
        if symbol not in self.symbol_locks:
            self.symbol_locks[symbol] = asyncio.Lock()
        return self.symbol_locks[symbol]

    async def get_affinity_stats(self) -> dict[str, any]:
        """Get statistics about worker affinity"""
        workers_data = await self.redis_manager.get_healthy_workers()

        # Convert to WorkerInfo objects
        workers = []
        for w in workers_data:
            worker = WorkerInfo(
                worker_id=w['worker_id'],
                hostname=w['hostname'],
                process_id=w['process_id'],
                started_at=datetime.fromisoformat(w['started_at']),
                last_heartbeat=datetime.utcnow(),
                active_computations=w['heartbeat'].get('active_computations', 0),
                capacity=w.get('capacity', 100)
            )
            workers.append(worker)

        stats = {
            "worker_id": self.worker_id,
            "total_workers": len(workers),
            "assigned_symbols": len(self.assigned_symbols),
            "worker_distribution": {
                w.worker_id: {
                    "hostname": w.hostname,
                    "load_factor": w.load_factor,
                    "active_computations": w.active_computations
                }
                for w in workers
            },
            "rebalance_needed": self._is_rebalance_needed(workers)
        }

        # Add ticker consumer metrics if available
        if self.stream_consumer:
            stats["stream_consumer"] = self.stream_consumer.get_metrics()

        return stats

    def _is_rebalance_needed(self, workers: list[WorkerInfo]) -> bool:
        """Check if rebalancing is needed"""
        if len(workers) <= 1:
            return False

        loads = [w.load_factor for w in workers]
        max_load = max(loads)
        min_load = min(loads)

        # Rebalance if load difference > 30%
        return (max_load - min_load) > 0.3

    async def cleanup(self):
        """Cleanup worker registration on shutdown"""
        try:
            # Stop ticker consumers
            if self.stream_consumer:
                await self.stream_consumer.stop_consuming()
            if self.channel_subscriber:
                await self.channel_subscriber.stop_subscribing()

            # Use Redis manager to cleanup
            await self.redis_manager.cleanup_worker(self.worker_id)

            # Clear local state
            self.assigned_symbols.clear()

            log_info(f"Worker {self.worker_id} cleaned up")

        except Exception as e:
            log_error(f"Cleanup error: {e}")


# Global instance (initialized per worker)
worker_affinity_manager = None


async def get_worker_affinity_manager() -> WorkerAffinityManager:
    """Get or create worker affinity manager instance"""
    global worker_affinity_manager

    if worker_affinity_manager is None:
        worker_affinity_manager = WorkerAffinityManager()
        await worker_affinity_manager.initialize()

    return worker_affinity_manager
