"""
Work Stealing Queue Implementation for Signal Service
Enables dynamic load balancing between worker threads
"""
import asyncio
import random
import time
from collections import deque
from dataclasses import dataclass
from enum import Enum
from threading import Lock
from typing import Any

from app.utils.logging_utils import log_debug, log_info, log_warning


class TaskPriority(Enum):
    """Task priority levels"""
    CRITICAL = 4   # Market orders, stop losses
    HIGH = 3       # User-initiated computations
    NORMAL = 2     # Regular tick processing
    LOW = 1        # Background tasks


@dataclass
class ComputationTask:
    """Represents a computation task"""
    task_id: str
    instrument_key: str
    computation_type: str  # "greeks", "indicators", "moneyness"
    params: dict[str, Any]
    priority: TaskPriority
    timestamp: float
    retry_count: int = 0
    max_retries: int = 3

    def __lt__(self, other):
        """For priority queue sorting (higher priority first)"""
        return self.priority.value > other.priority.value


class WorkStealingQueue:
    """
    Work stealing queue for dynamic load balancing
    Each worker has its own deque and can steal from others
    """

    def __init__(self, worker_id: str, worker_pool: 'WorkerPool'):
        self.worker_id = worker_id
        self.worker_pool = worker_pool

        # Local work queue (double-ended for efficient stealing)
        self.local_queue: deque[ComputationTask] = deque()
        self.queue_lock = Lock()

        # Metrics
        self.tasks_processed = 0
        self.tasks_stolen = 0
        self.steal_attempts = 0
        self.failed_steals = 0

        # Configuration
        self.max_steal_attempts = 3
        self.steal_batch_size = 5  # Steal multiple tasks at once
        self.local_queue_limit = 1000

    async def push(self, task: ComputationTask) -> bool:
        """Add task to local queue"""
        with self.queue_lock:
            if len(self.local_queue) >= self.local_queue_limit:
                log_warning(f"Worker {self.worker_id} queue full, rejecting task")
                return False

            # Add high priority tasks to front
            if task.priority in [TaskPriority.CRITICAL, TaskPriority.HIGH]:
                self.local_queue.appendleft(task)
            else:
                self.local_queue.append(task)

            return True

    async def push_batch(self, tasks: list[ComputationTask]):
        """Add multiple tasks efficiently"""
        with self.queue_lock:
            # Sort by priority
            tasks.sort(reverse=True)  # High priority first

            # Add to queue
            for task in tasks:
                if len(self.local_queue) >= self.local_queue_limit:
                    break
                self.local_queue.append(task)

    async def pop(self) -> ComputationTask | None:
        """Get task from local queue or steal from others"""
        # Try local queue first
        task = self._pop_local()
        if task:
            return task

        # If empty, try to steal
        return await self._steal_work()

    def _pop_local(self) -> ComputationTask | None:
        """Pop from local queue"""
        with self.queue_lock:
            if self.local_queue:
                self.tasks_processed += 1
                return self.local_queue.popleft()
        return None

    async def _steal_work(self) -> ComputationTask | None:
        """Attempt to steal work from other workers"""
        self.steal_attempts += 1

        # Get list of potential victims
        victims = self.worker_pool.get_stealable_workers(self.worker_id)
        if not victims:
            return None

        # Randomize victim order to avoid patterns
        random.shuffle(victims)

        # Try to steal from each victim
        for attempt in range(min(self.max_steal_attempts, len(victims))):
            victim_id = victims[attempt % len(victims)]

            # Try to steal from victim
            stolen_tasks = await self.worker_pool.steal_from_worker(
                victim_id,
                self.steal_batch_size
            )

            if stolen_tasks:
                # Add stolen tasks to our queue
                with self.queue_lock:
                    self.local_queue.extend(stolen_tasks[1:])  # Keep rest

                self.tasks_stolen += len(stolen_tasks)
                log_debug(f"Worker {self.worker_id} stole {len(stolen_tasks)} tasks from {victim_id}")

                # Return first task
                return stolen_tasks[0]

            # Small delay between attempts
            await asyncio.sleep(0.001)

        self.failed_steals += 1
        return None

    def get_stealable_tasks(self, count: int) -> list[ComputationTask]:
        """Get tasks that can be stolen (from back of queue)"""
        stolen = []

        with self.queue_lock:
            # Only steal if we have enough tasks
            if len(self.local_queue) > count * 2:
                # Steal from back (low priority tasks)
                for _ in range(min(count, len(self.local_queue) // 2)):
                    if self.local_queue:
                        stolen.append(self.local_queue.pop())

        return stolen

    def size(self) -> int:
        """Get current queue size"""
        with self.queue_lock:
            return len(self.local_queue)

    def get_metrics(self) -> dict:
        """Get queue metrics"""
        with self.queue_lock:
            queue_size = len(self.local_queue)

        return {
            'worker_id': self.worker_id,
            'queue_size': queue_size,
            'tasks_processed': self.tasks_processed,
            'tasks_stolen': self.tasks_stolen,
            'steal_attempts': self.steal_attempts,
            'failed_steals': self.failed_steals,
            'steal_success_rate': (
                (self.steal_attempts - self.failed_steals) / self.steal_attempts
                if self.steal_attempts > 0 else 0
            )
        }


class WorkerPool:
    """
    Manages a pool of workers with work stealing queues
    """

    def __init__(self, num_workers: int):
        self.num_workers = num_workers
        self.workers: dict[str, WorkStealingQueue] = {}
        self.worker_stats: dict[str, dict] = {}

        # Load balancer
        self.next_worker = 0
        self.distribution_strategy = 'least_loaded'  # 'round_robin', 'least_loaded', 'hash'

        # Initialize workers
        for i in range(num_workers):
            worker_id = f"worker_{i}"
            self.workers[worker_id] = WorkStealingQueue(worker_id, self)
            self.worker_stats[worker_id] = {
                'total_assigned': 0,
                'last_assignment': time.time()
            }

    async def submit_task(self, task: ComputationTask) -> bool:
        """Submit a task to the pool"""
        # Select worker based on strategy
        worker_id = self._select_worker(task)

        if worker_id:
            success = await self.workers[worker_id].push(task)
            if success:
                self.worker_stats[worker_id]['total_assigned'] += 1
                self.worker_stats[worker_id]['last_assignment'] = time.time()
            return success

        # If no suitable worker, try any worker
        for worker_id, queue in self.workers.items():
            if await queue.push(task):
                self.worker_stats[worker_id]['total_assigned'] += 1
                return True

        return False

    async def submit_batch(self, tasks: list[ComputationTask]):
        """Submit multiple tasks efficiently"""
        # Group by instrument for better locality
        grouped = {}
        for task in tasks:
            key = hash(task.instrument_key) % self.num_workers
            worker_id = f"worker_{key}"

            if worker_id not in grouped:
                grouped[worker_id] = []
            grouped[worker_id].append(task)

        # Submit to workers
        for worker_id, worker_tasks in grouped.items():
            await self.workers[worker_id].push_batch(worker_tasks)

    def _select_worker(self, task: ComputationTask) -> str | None:
        """Select worker based on distribution strategy"""
        if self.distribution_strategy == 'round_robin':
            worker_id = f"worker_{self.next_worker}"
            self.next_worker = (self.next_worker + 1) % self.num_workers
            return worker_id

        if self.distribution_strategy == 'least_loaded':
            # Find worker with smallest queue
            min_size = float('inf')
            selected = None

            for worker_id, queue in self.workers.items():
                size = queue.size()
                if size < min_size:
                    min_size = size
                    selected = worker_id

            return selected

        if self.distribution_strategy == 'hash':
            # Hash-based distribution for instrument locality
            hash_val = hash(task.instrument_key)
            worker_idx = hash_val % self.num_workers
            return f"worker_{worker_idx}"

        return None

    def get_stealable_workers(self, requester_id: str) -> list[str]:
        """Get list of workers that can be stolen from"""
        stealable = []

        requester_size = self.workers[requester_id].size()

        for worker_id, queue in self.workers.items():
            if worker_id != requester_id and queue.size() > requester_size + 10:  # Threshold
                stealable.append(worker_id)

        return stealable

    async def steal_from_worker(self, victim_id: str, count: int) -> list[ComputationTask]:
        """Steal tasks from a specific worker"""
        if victim_id in self.workers:
            return self.workers[victim_id].get_stealable_tasks(count)
        return []

    def get_pool_metrics(self) -> dict:
        """Get metrics for entire pool"""
        total_tasks = 0
        total_processed = 0
        total_stolen = 0
        queue_sizes = []

        worker_metrics = []
        for _worker_id, queue in self.workers.items():
            metrics = queue.get_metrics()
            worker_metrics.append(metrics)

            total_tasks += metrics['queue_size']
            total_processed += metrics['tasks_processed']
            total_stolen += metrics['tasks_stolen']
            queue_sizes.append(metrics['queue_size'])

        # Calculate load imbalance
        avg_size = sum(queue_sizes) / len(queue_sizes) if queue_sizes else 0
        max_size = max(queue_sizes) if queue_sizes else 0
        min_size = min(queue_sizes) if queue_sizes else 0

        return {
            'num_workers': self.num_workers,
            'total_tasks_queued': total_tasks,
            'total_tasks_processed': total_processed,
            'total_tasks_stolen': total_stolen,
            'average_queue_size': avg_size,
            'max_queue_size': max_size,
            'min_queue_size': min_size,
            'load_imbalance_ratio': max_size / (min_size + 1),
            'worker_metrics': worker_metrics
        }

    def rebalance(self):
        """Force rebalancing of tasks across workers"""
        # Collect all tasks
        all_tasks = []
        for queue in self.workers.values():
            with queue.queue_lock:
                all_tasks.extend(queue.local_queue)
                queue.local_queue.clear()

        # Sort by priority
        all_tasks.sort(reverse=True)

        # Redistribute evenly
        for i, task in enumerate(all_tasks):
            worker_idx = i % self.num_workers
            worker_id = f"worker_{worker_idx}"
            with self.workers[worker_id].queue_lock:
                self.workers[worker_id].local_queue.append(task)


class ComputationWorker:
    """
    Worker that processes tasks from work stealing queue with load balancing
    """

    def __init__(self, worker_id: str, queue: WorkStealingQueue, processor):
        self.worker_id = worker_id
        self.queue = queue
        self.processor = processor  # Signal processor instance
        self.is_running = False

        # Performance tracking
        self.computation_times = deque(maxlen=100)
        self.idle_time = 0
        self.busy_time = 0

    async def start(self):
        """Start processing tasks"""
        self.is_running = True
        log_info(f"Worker {self.worker_id} started")

        while self.is_running:
            start_time = time.time()

            # Get next task
            task = await self.queue.pop()

            if task:
                # Process task
                try:
                    computation_start = time.time()
                    await self._process_task(task)

                    computation_time = time.time() - computation_start
                    self.computation_times.append(computation_time)
                    self.busy_time += computation_time

                except Exception as e:
                    log_warning(f"Worker {self.worker_id} task failed: {e}")

                    # Retry logic
                    if task.retry_count < task.max_retries:
                        task.retry_count += 1
                        await self.queue.push(task)  # Re-queue

            else:
                # No work available
                idle_duration = time.time() - start_time
                self.idle_time += idle_duration

                # Exponential backoff when idle
                await asyncio.sleep(min(0.1 * (2 ** min(5, self.idle_time)), 1.0))

    async def _process_task(self, task: ComputationTask):
        """Process a single computation task"""
        if task.computation_type == "greeks":
            await self.processor.compute_greeks_for_instrument(
                task.instrument_key,
                task.params
            )
        elif task.computation_type == "indicators":
            await self.processor.compute_indicators_for_instrument(
                task.instrument_key,
                task.params
            )
        elif task.computation_type == "moneyness":
            await self.processor.compute_moneyness_greeks(
                task.params['underlying'],
                task.params['moneyness_level'],
                task.params['timeframe']
            )
        else:
            log_warning(f"Unknown computation type: {task.computation_type}")

    def stop(self):
        """Stop the worker"""
        self.is_running = False
        log_info(f"Worker {self.worker_id} stopped")

    def get_performance_stats(self) -> dict:
        """Get worker performance statistics"""
        if not self.computation_times:
            avg_computation_time = 0
        else:
            avg_computation_time = sum(self.computation_times) / len(self.computation_times)

        total_time = self.busy_time + self.idle_time
        utilization = self.busy_time / total_time if total_time > 0 else 0

        return {
            'worker_id': self.worker_id,
            'average_computation_time': avg_computation_time,
            'utilization': utilization,
            'busy_time': self.busy_time,
            'idle_time': self.idle_time,
            'tasks_per_second': len(self.computation_times) / self.busy_time if self.busy_time > 0 else 0
        }
