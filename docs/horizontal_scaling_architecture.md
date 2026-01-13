# Signal Service Horizontal Scaling Architecture

## Table of Contents
1. [Overview](#overview)
2. [Sharding Strategy](#sharding-strategy)
3. [Load Distribution](#load-distribution)
4. [Backpressure Management](#backpressure-management)
5. [Auto-scaling Implementation](#auto-scaling-implementation)
6. [Coordination & State Management](#coordination-state-management)
7. [Performance Optimization](#performance-optimization)
8. [Monitoring & Observability](#monitoring-observability)

---

## 1. Overview

The Signal Service must handle millions of computations per second across thousands of instruments. This document outlines the horizontal scaling architecture that enables the service to scale elastically based on load while maintaining low latency and high throughput.

### Key Challenges
- **Instrument Distribution**: 10,000+ unique instrument keys
- **Computation Intensity**: Greeks calculations are CPU-intensive
- **Data Locality**: Minimize cross-pod communication
- **Backpressure**: Handle varying load per instrument
- **State Management**: Maintain computation state during scaling

### Design Principles
1. **Stateless Computation**: Each pod can process any instrument
2. **Consistent Hashing**: Predictable instrument-to-pod mapping
3. **Dynamic Rebalancing**: Adjust distribution based on load
4. **Graceful Scaling**: No computation loss during scale events

---

## 2. Sharding Strategy

### 2.1 Consistent Hashing Ring
```python
import hashlib
from bisect import bisect_right
from typing import List, Dict, Optional

class ConsistentHashRing:
    """
    Consistent hashing for instrument distribution
    with virtual nodes for better balance
    """
    
    def __init__(self, nodes: List[str], virtual_nodes: int = 150):
        self.virtual_nodes = virtual_nodes
        self.ring: Dict[int, str] = {}
        self.sorted_keys: List[int] = []
        self.nodes = set()
        
        for node in nodes:
            self.add_node(node)
    
    def _hash(self, key: str) -> int:
        """Generate hash for a key"""
        return int(hashlib.md5(key.encode()).hexdigest(), 16)
    
    def add_node(self, node: str):
        """Add a node to the ring with virtual nodes"""
        self.nodes.add(node)
        
        for i in range(self.virtual_nodes):
            virtual_key = f"{node}:{i}"
            hash_value = self._hash(virtual_key)
            self.ring[hash_value] = node
            self.sorted_keys.append(hash_value)
        
        self.sorted_keys.sort()
    
    def remove_node(self, node: str):
        """Remove a node from the ring"""
        self.nodes.discard(node)
        
        for i in range(self.virtual_nodes):
            virtual_key = f"{node}:{i}"
            hash_value = self._hash(virtual_key)
            if hash_value in self.ring:
                del self.ring[hash_value]
                self.sorted_keys.remove(hash_value)
    
    def get_node(self, instrument_key: str) -> Optional[str]:
        """Get the node responsible for an instrument"""
        if not self.ring:
            return None
        
        hash_value = self._hash(instrument_key)
        index = bisect_right(self.sorted_keys, hash_value)
        
        if index == len(self.sorted_keys):
            index = 0
        
        return self.ring[self.sorted_keys[index]]
    
    def get_nodes(self, instrument_key: str, count: int = 3) -> List[str]:
        """Get multiple nodes for replication/fallback"""
        if not self.ring:
            return []
        
        nodes = []
        hash_value = self._hash(instrument_key)
        index = bisect_right(self.sorted_keys, hash_value)
        
        for _ in range(min(count, len(self.nodes))):
            if index >= len(self.sorted_keys):
                index = 0
            
            node = self.ring[self.sorted_keys[index]]
            if node not in nodes:
                nodes.append(node)
            
            index += 1
        
        return nodes
```

### 2.2 Instrument Partitioning Strategy
```python
class InstrumentPartitioner:
    """
    Partition instruments based on characteristics
    for better load distribution
    """
    
    def __init__(self):
        self.high_frequency_instruments = set()
        self.load_factors = {}
        self.partition_strategy = self._determine_strategy()
    
    def _determine_strategy(self) -> str:
        """Determine partitioning strategy based on workload"""
        # Strategies: hash, weighted, hierarchical, dynamic
        return "weighted"
    
    def get_partition_key(self, instrument_key: str) -> str:
        """
        Generate partition key based on instrument characteristics
        """
        # Parse instrument key
        parts = instrument_key.split('@')
        exchange = parts[0]
        symbol = parts[1]
        asset_type = parts[2] if len(parts) > 2 else "EQUITY"
        
        if self.partition_strategy == "hierarchical":
            # Partition by exchange first, then symbol
            return f"{exchange}:{symbol[:2]}"
        
        elif self.partition_strategy == "weighted":
            # Consider load factor
            load_factor = self.load_factors.get(instrument_key, 1.0)
            if load_factor > 2.0:
                # High-load instruments get dedicated partitions
                return f"high_load:{instrument_key}"
            else:
                # Normal hash-based partitioning
                return instrument_key
        
        else:
            # Default: simple hash
            return instrument_key
    
    def update_load_factor(self, instrument_key: str, load: float):
        """Update load factor for dynamic rebalancing"""
        self.load_factors[instrument_key] = load
        
        # Mark as high-frequency if consistently high load
        if load > 2.0:
            self.high_frequency_instruments.add(instrument_key)
```

---

## 3. Load Distribution

### 3.1 Pod Assignment Manager
```python
import asyncio
from dataclasses import dataclass
from typing import Set, Dict, List
import aioredis

@dataclass
class PodInfo:
    pod_id: str
    capacity: int  # Max instruments per pod
    current_load: int
    assigned_instruments: Set[str]
    cpu_usage: float
    memory_usage: float
    computation_rate: float  # computations/second

class PodAssignmentManager:
    """
    Manages instrument assignment to pods
    with dynamic load balancing
    """
    
    def __init__(self, redis_client: aioredis.Redis):
        self.redis = redis_client
        self.hash_ring = ConsistentHashRing([])
        self.pods: Dict[str, PodInfo] = {}
        self.instrument_assignments: Dict[str, str] = {}
        self.rebalance_threshold = 0.3  # 30% load difference triggers rebalance
    
    async def register_pod(self, pod_id: str, capacity: int = 1000):
        """Register a new pod in the cluster"""
        pod_info = PodInfo(
            pod_id=pod_id,
            capacity=capacity,
            current_load=0,
            assigned_instruments=set(),
            cpu_usage=0.0,
            memory_usage=0.0,
            computation_rate=0.0
        )
        
        self.pods[pod_id] = pod_info
        self.hash_ring.add_node(pod_id)
        
        # Store in Redis for cluster-wide visibility
        await self.redis.hset(
            "signal:pods",
            pod_id,
            pod_info.to_json()
        )
        
        # Trigger rebalancing if needed
        await self.rebalance_if_needed()
    
    async def unregister_pod(self, pod_id: str):
        """Remove a pod and reassign its instruments"""
        if pod_id not in self.pods:
            return
        
        pod_info = self.pods[pod_id]
        orphaned_instruments = pod_info.assigned_instruments.copy()
        
        # Remove from hash ring
        self.hash_ring.remove_node(pod_id)
        del self.pods[pod_id]
        
        # Reassign orphaned instruments
        for instrument in orphaned_instruments:
            new_pod = await self.assign_instrument(instrument)
            print(f"Reassigned {instrument} from {pod_id} to {new_pod}")
        
        # Remove from Redis
        await self.redis.hdel("signal:pods", pod_id)
    
    async def assign_instrument(self, instrument_key: str) -> str:
        """
        Assign an instrument to a pod using consistent hashing
        with load awareness
        """
        # Get primary and backup nodes from hash ring
        candidate_pods = self.hash_ring.get_nodes(instrument_key, count=3)
        
        # Find the least loaded pod among candidates
        selected_pod = None
        min_load_ratio = float('inf')
        
        for pod_id in candidate_pods:
            if pod_id in self.pods:
                pod_info = self.pods[pod_id]
                load_ratio = pod_info.current_load / pod_info.capacity
                
                if load_ratio < min_load_ratio and load_ratio < 0.9:
                    min_load_ratio = load_ratio
                    selected_pod = pod_id
        
        if not selected_pod:
            # All candidates are overloaded, find any available pod
            for pod_id, pod_info in self.pods.items():
                if pod_info.current_load < pod_info.capacity * 0.9:
                    selected_pod = pod_id
                    break
        
        if selected_pod:
            # Update assignment
            self.instrument_assignments[instrument_key] = selected_pod
            self.pods[selected_pod].assigned_instruments.add(instrument_key)
            self.pods[selected_pod].current_load += 1
            
            # Store in Redis
            await self.redis.hset(
                "signal:assignments",
                instrument_key,
                selected_pod
            )
            
            return selected_pod
        
        raise Exception("No available pods for assignment")
    
    async def rebalance_if_needed(self):
        """Check load distribution and rebalance if needed"""
        if len(self.pods) < 2:
            return
        
        # Calculate load statistics
        loads = [p.current_load / p.capacity for p in self.pods.values()]
        avg_load = sum(loads) / len(loads)
        max_load = max(loads)
        min_load = min(loads)
        
        # Check if rebalancing is needed
        if (max_load - min_load) > self.rebalance_threshold:
            await self.rebalance_load()
    
    async def rebalance_load(self):
        """Rebalance instruments across pods"""
        print("Starting load rebalancing...")
        
        # Sort pods by load
        sorted_pods = sorted(
            self.pods.items(),
            key=lambda x: x[1].current_load / x[1].capacity,
            reverse=True
        )
        
        # Move instruments from overloaded to underloaded pods
        for i in range(len(sorted_pods) // 2):
            overloaded_pod_id, overloaded_pod = sorted_pods[i]
            underloaded_pod_id, underloaded_pod = sorted_pods[-(i+1)]
            
            # Calculate how many instruments to move
            target_load = (overloaded_pod.current_load + underloaded_pod.current_load) // 2
            instruments_to_move = overloaded_pod.current_load - target_load
            
            # Move instruments
            moved = 0
            for instrument in list(overloaded_pod.assigned_instruments):
                if moved >= instruments_to_move:
                    break
                
                # Reassign instrument
                overloaded_pod.assigned_instruments.remove(instrument)
                overloaded_pod.current_load -= 1
                
                underloaded_pod.assigned_instruments.add(instrument)
                underloaded_pod.current_load += 1
                
                self.instrument_assignments[instrument] = underloaded_pod_id
                
                # Update Redis
                await self.redis.hset(
                    "signal:assignments",
                    instrument,
                    underloaded_pod_id
                )
                
                moved += 1
            
            print(f"Moved {moved} instruments from {overloaded_pod_id} to {underloaded_pod_id}")
```

### 3.2 Work Stealing Queue
```python
import asyncio
from collections import deque
from dataclasses import dataclass
from typing import Optional, Deque

@dataclass
class ComputationTask:
    instrument_key: str
    computation_type: str  # "greeks", "indicators", etc.
    priority: int
    timestamp: float
    retry_count: int = 0

class WorkStealingQueue:
    """
    Work stealing queue for dynamic load balancing
    between computation threads/processes
    """
    
    def __init__(self, worker_id: str, total_workers: int):
        self.worker_id = worker_id
        self.total_workers = total_workers
        self.local_queue: Deque[ComputationTask] = deque()
        self.stealing_enabled = True
        self.max_steal_attempts = 3
        
        # Shared memory for inter-worker communication
        self.shared_queues: Dict[str, Deque[ComputationTask]] = {}
    
    async def push(self, task: ComputationTask):
        """Add task to local queue"""
        self.local_queue.append(task)
    
    async def pop(self) -> Optional[ComputationTask]:
        """
        Get task from local queue or steal from others
        """
        # Try local queue first
        if self.local_queue:
            return self.local_queue.popleft()
        
        # If empty and stealing enabled, try to steal
        if self.stealing_enabled:
            return await self.steal_work()
        
        return None
    
    async def steal_work(self) -> Optional[ComputationTask]:
        """Attempt to steal work from other workers"""
        steal_attempts = 0
        
        while steal_attempts < self.max_steal_attempts:
            # Random victim selection
            victim_id = self._select_victim()
            
            if victim_id in self.shared_queues:
                victim_queue = self.shared_queues[victim_id]
                
                # Steal from the back of victim's queue
                if len(victim_queue) > 1:  # Leave at least one task
                    try:
                        stolen_task = victim_queue.pop()
                        print(f"Worker {self.worker_id} stole task from {victim_id}")
                        return stolen_task
                    except IndexError:
                        pass  # Race condition, queue became empty
            
            steal_attempts += 1
            await asyncio.sleep(0.001)  # Small delay between attempts
        
        return None
    
    def _select_victim(self) -> str:
        """Select a victim worker for work stealing"""
        import random
        victim_id = random.randint(0, self.total_workers - 1)
        while f"worker_{victim_id}" == self.worker_id:
            victim_id = random.randint(0, self.total_workers - 1)
        return f"worker_{victim_id}"
```

---

## 4. Backpressure Management

### 4.1 Backpressure Monitor
```python
import time
from enum import Enum
from typing import Dict, List, Tuple

class BackpressureLevel(Enum):
    LOW = "low"          # < 50% capacity
    MEDIUM = "medium"    # 50-70% capacity
    HIGH = "high"        # 70-85% capacity
    CRITICAL = "critical" # > 85% capacity

class BackpressureMonitor:
    """
    Monitors computation backpressure and triggers scaling actions
    """
    
    def __init__(self):
        self.metrics: Dict[str, Dict] = {}
        self.thresholds = {
            BackpressureLevel.LOW: 0.5,
            BackpressureLevel.MEDIUM: 0.7,
            BackpressureLevel.HIGH: 0.85,
            BackpressureLevel.CRITICAL: 0.95
        }
        self.scaling_decisions: List[Tuple[float, str]] = []
    
    def update_metrics(self, pod_id: str, metrics: Dict):
        """Update metrics for a pod"""
        self.metrics[pod_id] = {
            **metrics,
            'timestamp': time.time(),
            'backpressure_level': self._calculate_backpressure_level(metrics)
        }
    
    def _calculate_backpressure_level(self, metrics: Dict) -> BackpressureLevel:
        """Calculate backpressure level from metrics"""
        # Composite score based on multiple factors
        queue_depth_ratio = metrics.get('queue_depth', 0) / metrics.get('queue_capacity', 1)
        cpu_usage = metrics.get('cpu_usage', 0)
        memory_usage = metrics.get('memory_usage', 0)
        latency_ratio = metrics.get('p99_latency', 0) / metrics.get('target_latency', 100)
        
        # Weighted composite score
        composite_score = (
            queue_depth_ratio * 0.4 +
            cpu_usage * 0.3 +
            memory_usage * 0.2 +
            min(latency_ratio, 1.0) * 0.1
        )
        
        # Determine level
        if composite_score >= self.thresholds[BackpressureLevel.CRITICAL]:
            return BackpressureLevel.CRITICAL
        elif composite_score >= self.thresholds[BackpressureLevel.HIGH]:
            return BackpressureLevel.HIGH
        elif composite_score >= self.thresholds[BackpressureLevel.MEDIUM]:
            return BackpressureLevel.MEDIUM
        else:
            return BackpressureLevel.LOW
    
    def get_scaling_recommendation(self) -> Dict:
        """Get scaling recommendation based on cluster-wide backpressure"""
        if not self.metrics:
            return {'action': 'none', 'reason': 'no metrics'}
        
        # Count pods at each backpressure level
        level_counts = {level: 0 for level in BackpressureLevel}
        for pod_metrics in self.metrics.values():
            level = pod_metrics.get('backpressure_level', BackpressureLevel.LOW)
            level_counts[level] += 1
        
        total_pods = len(self.metrics)
        critical_ratio = level_counts[BackpressureLevel.CRITICAL] / total_pods
        high_ratio = level_counts[BackpressureLevel.HIGH] / total_pods
        
        # Scaling decision logic
        if critical_ratio > 0.3:
            return {
                'action': 'scale_up',
                'urgency': 'immediate',
                'recommended_pods': max(2, int(total_pods * 0.5)),
                'reason': f'{critical_ratio:.1%} pods at critical backpressure'
            }
        
        elif high_ratio > 0.5:
            return {
                'action': 'scale_up',
                'urgency': 'normal',
                'recommended_pods': max(1, int(total_pods * 0.3)),
                'reason': f'{high_ratio:.1%} pods at high backpressure'
            }
        
        elif critical_ratio == 0 and high_ratio < 0.1:
            # Check if we can scale down
            low_ratio = level_counts[BackpressureLevel.LOW] / total_pods
            if low_ratio > 0.8 and total_pods > 3:  # Keep minimum 3 pods
                return {
                    'action': 'scale_down',
                    'urgency': 'normal',
                    'recommended_pods': 1,
                    'reason': f'{low_ratio:.1%} pods at low backpressure'
                }
        
        return {'action': 'none', 'reason': 'backpressure within normal range'}
```

### 4.2 Adaptive Load Shedding
```python
class AdaptiveLoadShedder:
    """
    Implements adaptive load shedding to prevent system overload
    """
    
    def __init__(self):
        self.shedding_active = False
        self.shedding_percentage = 0.0
        self.priority_thresholds = {
            'critical': 1.0,   # Never shed
            'high': 0.9,       # Shed when > 90% load
            'medium': 0.7,     # Shed when > 70% load
            'low': 0.5         # Shed when > 50% load
        }
    
    def should_accept_request(
        self,
        request_priority: str,
        current_load: float,
        instrument_key: str
    ) -> Tuple[bool, str]:
        """Determine if request should be accepted or shed"""
        
        # Critical requests always accepted
        if request_priority == 'critical':
            return True, "critical priority"
        
        # Check if instrument is high-frequency
        if self._is_high_frequency_instrument(instrument_key):
            # More lenient for important instruments
            threshold = min(self.priority_thresholds[request_priority] + 0.1, 1.0)
        else:
            threshold = self.priority_thresholds[request_priority]
        
        if current_load < threshold:
            return True, "within threshold"
        
        # Probabilistic shedding
        import random
        shed_probability = (current_load - threshold) / (1.0 - threshold)
        
        if random.random() > shed_probability:
            return True, "probabilistic accept"
        else:
            return False, f"load shedding at {current_load:.1%} load"
    
    def _is_high_frequency_instrument(self, instrument_key: str) -> bool:
        """Check if instrument is high-frequency/important"""
        # Implementation would check against a maintained list
        high_freq_symbols = {'NIFTY', 'BANKNIFTY', 'RELIANCE', 'TCS'}
        symbol = instrument_key.split('@')[1]
        return symbol in high_freq_symbols
```

---

## 5. Auto-scaling Implementation

### 5.1 Kubernetes HPA Configuration
```yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: signal-service-hpa
  namespace: trading-platform
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: signal-service
  
  minReplicas: 3
  maxReplicas: 50
  
  metrics:
  # CPU-based scaling
  - type: Resource
    resource:
      name: cpu
      target:
        type: Utilization
        averageUtilization: 70
  
  # Memory-based scaling
  - type: Resource
    resource:
      name: memory
      target:
        type: Utilization
        averageUtilization: 80
  
  # Custom metrics from Prometheus
  - type: Pods
    pods:
      metric:
        name: signal_service_queue_depth
      target:
        type: AverageValue
        averageValue: "1000"
  
  - type: Pods
    pods:
      metric:
        name: signal_service_computation_latency_p99
      target:
        type: AverageValue
        averageValue: "100"  # 100ms
  
  - type: Pods
    pods:
      metric:
        name: signal_service_backpressure_level
      target:
        type: AverageValue
        averageValue: "2"  # Scale when average > MEDIUM
  
  # Scale up/down policies
  behavior:
    scaleUp:
      stabilizationWindowSeconds: 60
      policies:
      - type: Percent
        value: 100  # Double pods
        periodSeconds: 60
      - type: Pods
        value: 5    # Add max 5 pods
        periodSeconds: 60
      selectPolicy: Max  # Use the policy that scales up most
    
    scaleDown:
      stabilizationWindowSeconds: 300  # 5 minutes
      policies:
      - type: Percent
        value: 10   # Remove 10% of pods
        periodSeconds: 120
      - type: Pods
        value: 2    # Remove max 2 pods
        periodSeconds: 120
      selectPolicy: Min  # Use the policy that scales down least
```

### 5.2 Custom Metrics Provider
```python
from prometheus_client import Gauge, Histogram, Counter
import asyncio

class SignalServiceMetrics:
    """
    Custom metrics for auto-scaling decisions
    """
    
    def __init__(self):
        # Backpressure metrics
        self.queue_depth = Gauge(
            'signal_service_queue_depth',
            'Current queue depth for computations',
            ['pod_id', 'computation_type']
        )
        
        self.backpressure_level = Gauge(
            'signal_service_backpressure_level',
            'Backpressure level (1=low, 2=medium, 3=high, 4=critical)',
            ['pod_id']
        )
        
        # Performance metrics
        self.computation_latency = Histogram(
            'signal_service_computation_latency',
            'Computation latency in milliseconds',
            ['computation_type', 'instrument_type'],
            buckets=[10, 25, 50, 100, 250, 500, 1000, 2500, 5000]
        )
        
        self.computations_per_second = Gauge(
            'signal_service_computations_per_second',
            'Rate of computations',
            ['pod_id', 'computation_type']
        )
        
        # Load distribution metrics
        self.instruments_per_pod = Gauge(
            'signal_service_instruments_per_pod',
            'Number of instruments assigned to pod',
            ['pod_id']
        )
        
        self.load_imbalance_ratio = Gauge(
            'signal_service_load_imbalance_ratio',
            'Ratio of max to min load across pods'
        )
        
        # Scaling metrics
        self.scaling_events = Counter(
            'signal_service_scaling_events',
            'Number of scaling events',
            ['direction', 'trigger']
        )
    
    async def update_metrics_loop(self, pod_manager: PodAssignmentManager):
        """Continuously update metrics for Prometheus"""
        while True:
            try:
                # Update pod-level metrics
                for pod_id, pod_info in pod_manager.pods.items():
                    self.instruments_per_pod.labels(pod_id=pod_id).set(
                        len(pod_info.assigned_instruments)
                    )
                    
                    # Calculate backpressure level
                    load_ratio = pod_info.current_load / pod_info.capacity
                    if load_ratio < 0.5:
                        level = 1  # LOW
                    elif load_ratio < 0.7:
                        level = 2  # MEDIUM
                    elif load_ratio < 0.85:
                        level = 3  # HIGH
                    else:
                        level = 4  # CRITICAL
                    
                    self.backpressure_level.labels(pod_id=pod_id).set(level)
                
                # Calculate load imbalance
                if pod_manager.pods:
                    loads = [len(p.assigned_instruments) for p in pod_manager.pods.values()]
                    if min(loads) > 0:
                        imbalance = max(loads) / min(loads)
                        self.load_imbalance_ratio.set(imbalance)
                
                await asyncio.sleep(10)  # Update every 10 seconds
                
            except Exception as e:
                print(f"Error updating metrics: {e}")
                await asyncio.sleep(30)
```

---

## 6. Coordination & State Management

### 6.1 Distributed Coordinator
```python
import asyncio
from typing import Dict, Set, Optional
import etcd3
import json

class DistributedCoordinator:
    """
    Coordinates signal service pods using etcd for leader election
    and distributed state management
    """
    
    def __init__(self, pod_id: str, etcd_host: str = 'etcd-cluster'):
        self.pod_id = pod_id
        self.etcd = etcd3.client(host=etcd_host)
        self.is_leader = False
        self.leader_key = '/signal-service/leader'
        self.assignments_prefix = '/signal-service/assignments/'
        self.pods_prefix = '/signal-service/pods/'
        self.lease = None
    
    async def start(self):
        """Start coordination tasks"""
        # Try to become leader
        await self.acquire_leadership()
        
        # Start watchers
        asyncio.create_task(self.watch_assignments())
        asyncio.create_task(self.watch_pods())
        
        # If leader, start management tasks
        if self.is_leader:
            asyncio.create_task(self.manage_cluster())
    
    async def acquire_leadership(self):
        """Try to become the leader using etcd lease"""
        try:
            # Create a lease that expires in 10 seconds
            self.lease = self.etcd.lease(10)
            
            # Try to create the leader key with our pod_id
            success = self.etcd.put_if_not_exists(
                self.leader_key,
                self.pod_id.encode(),
                lease=self.lease
            )
            
            if success:
                self.is_leader = True
                print(f"Pod {self.pod_id} became leader")
                
                # Keep lease alive
                asyncio.create_task(self.maintain_leadership())
            else:
                # Watch for leader changes
                asyncio.create_task(self.watch_leadership())
                
        except Exception as e:
            print(f"Failed to acquire leadership: {e}")
    
    async def maintain_leadership(self):
        """Keep the leadership lease alive"""
        while self.is_leader:
            try:
                # Refresh lease
                self.lease.refresh()
                await asyncio.sleep(5)
            except Exception as e:
                print(f"Lost leadership: {e}")
                self.is_leader = False
                # Try to reacquire
                await self.acquire_leadership()
    
    async def watch_leadership(self):
        """Watch for leader changes"""
        events_iterator, cancel = self.etcd.watch(self.leader_key)
        
        try:
            for event in events_iterator:
                if isinstance(event, etcd3.events.DeleteEvent):
                    # Leader key deleted, try to become leader
                    await asyncio.sleep(0.1)  # Small delay to prevent thundering herd
                    await self.acquire_leadership()
        finally:
            cancel()
    
    async def manage_cluster(self):
        """Leader responsibilities"""
        manager = PodAssignmentManager(self.etcd)
        monitor = BackpressureMonitor()
        
        while self.is_leader:
            try:
                # Collect metrics from all pods
                pod_metrics = await self.collect_pod_metrics()
                
                # Update backpressure monitor
                for pod_id, metrics in pod_metrics.items():
                    monitor.update_metrics(pod_id, metrics)
                
                # Get scaling recommendation
                recommendation = monitor.get_scaling_recommendation()
                
                if recommendation['action'] != 'none':
                    await self.execute_scaling_action(recommendation)
                
                # Check for rebalancing needs
                await manager.rebalance_if_needed()
                
                await asyncio.sleep(30)  # Check every 30 seconds
                
            except Exception as e:
                print(f"Error in cluster management: {e}")
                await asyncio.sleep(60)
    
    async def register_pod(self, capacity: int = 1000):
        """Register this pod in the cluster"""
        pod_info = {
            'pod_id': self.pod_id,
            'capacity': capacity,
            'status': 'ready',
            'timestamp': time.time()
        }
        
        # Store in etcd with TTL
        lease = self.etcd.lease(60)  # 60 second TTL
        self.etcd.put(
            f"{self.pods_prefix}{self.pod_id}",
            json.dumps(pod_info).encode(),
            lease=lease
        )
        
        # Keep registration alive
        asyncio.create_task(self.maintain_registration(lease))
    
    async def maintain_registration(self, lease):
        """Keep pod registration alive"""
        while True:
            try:
                lease.refresh()
                await asyncio.sleep(30)
            except Exception as e:
                print(f"Failed to maintain registration: {e}")
                break
```

### 6.2 State Synchronization
```python
class StateSynchronizer:
    """
    Synchronizes computation state across pods
    for failover and load balancing
    """
    
    def __init__(self, redis_client: aioredis.Redis):
        self.redis = redis_client
        self.sync_interval = 5  # seconds
        self.state_prefix = "signal:state:"
    
    async def save_computation_state(
        self,
        instrument_key: str,
        computation_type: str,
        state: Dict
    ):
        """Save computation state to Redis"""
        key = f"{self.state_prefix}{instrument_key}:{computation_type}"
        
        # Add metadata
        state['last_updated'] = time.time()
        state['pod_id'] = os.environ.get('POD_NAME', 'unknown')
        
        # Save with TTL
        await self.redis.setex(
            key,
            300,  # 5 minute TTL
            json.dumps(state)
        )
    
    async def restore_computation_state(
        self,
        instrument_key: str,
        computation_type: str
    ) -> Optional[Dict]:
        """Restore computation state from Redis"""
        key = f"{self.state_prefix}{instrument_key}:{computation_type}"
        
        state_json = await self.redis.get(key)
        if state_json:
            return json.loads(state_json)
        
        return None
    
    async def migrate_state(
        self,
        instrument_key: str,
        from_pod: str,
        to_pod: str
    ):
        """Migrate state during rebalancing"""
        print(f"Migrating state for {instrument_key} from {from_pod} to {to_pod}")
        
        # Get all computation states for the instrument
        pattern = f"{self.state_prefix}{instrument_key}:*"
        
        async for key in self.redis.scan_iter(match=pattern):
            # Get state
            state_json = await self.redis.get(key)
            if state_json:
                state = json.loads(state_json)
                
                # Update pod assignment
                state['pod_id'] = to_pod
                state['migrated_from'] = from_pod
                state['migration_time'] = time.time()
                
                # Save updated state
                await self.redis.setex(key, 300, json.dumps(state))
```

---

## 7. Performance Optimization

### 7.1 Computation Batching
```python
class ComputationBatcher:
    """
    Batches computations for better CPU utilization
    """
    
    def __init__(self, batch_size: int = 100, max_wait_ms: int = 50):
        self.batch_size = batch_size
        self.max_wait_ms = max_wait_ms
        self.pending_computations: Dict[str, List] = {
            'greeks': [],
            'indicators': [],
            'moneyness': []
        }
        self.batch_lock = asyncio.Lock()
    
    async def add_computation(
        self,
        computation_type: str,
        instrument_key: str,
        params: Dict
    ) -> asyncio.Future:
        """Add computation to batch and return future"""
        future = asyncio.Future()
        
        async with self.batch_lock:
            self.pending_computations[computation_type].append({
                'instrument_key': instrument_key,
                'params': params,
                'future': future
            })
            
            # Check if we should process batch
            if len(self.pending_computations[computation_type]) >= self.batch_size:
                asyncio.create_task(self.process_batch(computation_type))
        
        # Start timer for max wait
        asyncio.create_task(self.process_batch_after_timeout(computation_type))
        
        return future
    
    async def process_batch(self, computation_type: str):
        """Process a batch of computations"""
        async with self.batch_lock:
            batch = self.pending_computations[computation_type]
            self.pending_computations[computation_type] = []
        
        if not batch:
            return
        
        # Group by similar parameters for optimization
        grouped = self.group_by_params(batch)
        
        # Process each group
        for params_key, items in grouped.items():
            try:
                # Batch computation
                results = await self.compute_batch(
                    computation_type,
                    [item['instrument_key'] for item in items],
                    items[0]['params']  # Same params for group
                )
                
                # Resolve futures
                for item, result in zip(items, results):
                    item['future'].set_result(result)
                    
            except Exception as e:
                # Reject futures on error
                for item in items:
                    item['future'].set_exception(e)
```

### 7.2 CPU Affinity Optimization
```python
import os
import psutil

class CPUAffinityOptimizer:
    """
    Optimizes CPU affinity for computation threads
    """
    
    def __init__(self):
        self.cpu_count = psutil.cpu_count()
        self.numa_nodes = self._detect_numa_nodes()
    
    def optimize_worker_affinity(self, worker_id: int, worker_type: str):
        """Set CPU affinity for worker based on type"""
        process = psutil.Process()
        
        if worker_type == "greeks":
            # Greeks computation is CPU-intensive
            # Assign to performance cores if available
            if self.numa_nodes:
                # Prefer local NUMA node
                cpus = self.numa_nodes[worker_id % len(self.numa_nodes)]
            else:
                # Distribute across all cores
                cpus = list(range(worker_id % self.cpu_count, self.cpu_count, 4))
        
        elif worker_type == "io":
            # I/O workers can share cores
            cpus = list(range(self.cpu_count))
        
        else:
            # Default: distribute evenly
            cores_per_worker = max(1, self.cpu_count // 8)
            start = (worker_id * cores_per_worker) % self.cpu_count
            cpus = list(range(start, min(start + cores_per_worker, self.cpu_count)))
        
        try:
            process.cpu_affinity(cpus)
            print(f"Worker {worker_id} ({worker_type}) bound to CPUs: {cpus}")
        except Exception as e:
            print(f"Failed to set CPU affinity: {e}")
    
    def _detect_numa_nodes(self) -> Dict[int, List[int]]:
        """Detect NUMA topology"""
        numa_nodes = {}
        
        try:
            # Linux-specific NUMA detection
            numa_path = "/sys/devices/system/node"
            if os.path.exists(numa_path):
                for node_dir in os.listdir(numa_path):
                    if node_dir.startswith("node"):
                        node_id = int(node_dir[4:])
                        cpu_list_path = os.path.join(numa_path, node_dir, "cpulist")
                        
                        if os.path.exists(cpu_list_path):
                            with open(cpu_list_path, 'r') as f:
                                cpu_range = f.read().strip()
                                # Parse CPU range (e.g., "0-7,16-23")
                                cpus = []
                                for part in cpu_range.split(','):
                                    if '-' in part:
                                        start, end = map(int, part.split('-'))
                                        cpus.extend(range(start, end + 1))
                                    else:
                                        cpus.append(int(part))
                                
                                numa_nodes[node_id] = cpus
        except Exception as e:
            print(f"NUMA detection failed: {e}")
        
        return numa_nodes
```

---

## 8. Monitoring & Observability

### 8.1 Distributed Tracing
```python
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

class DistributedTracer:
    """
    Implements distributed tracing for signal computations
    """
    
    def __init__(self):
        # Set up tracer
        trace.set_tracer_provider(TracerProvider())
        tracer_provider = trace.get_tracer_provider()
        
        # Configure OTLP exporter
        otlp_exporter = OTLPSpanExporter(
            endpoint="otel-collector:4317",
            insecure=True
        )
        
        # Add batch processor
        span_processor = BatchSpanProcessor(otlp_exporter)
        tracer_provider.add_span_processor(span_processor)
        
        self.tracer = trace.get_tracer(__name__)
    
    def trace_computation(self, computation_type: str, instrument_key: str):
        """Decorator for tracing computations"""
        def decorator(func):
            async def wrapper(*args, **kwargs):
                with self.tracer.start_as_current_span(
                    f"signal.{computation_type}",
                    attributes={
                        "instrument.key": instrument_key,
                        "computation.type": computation_type,
                        "pod.id": os.environ.get('POD_NAME', 'unknown'),
                        "node.name": os.environ.get('NODE_NAME', 'unknown')
                    }
                ) as span:
                    try:
                        result = await func(*args, **kwargs)
                        span.set_status(trace.Status(trace.StatusCode.OK))
                        return result
                    except Exception as e:
                        span.set_status(
                            trace.Status(trace.StatusCode.ERROR, str(e))
                        )
                        span.record_exception(e)
                        raise
            
            return wrapper
        return decorator
    
    def trace_batch_computation(self, computation_type: str, batch_size: int):
        """Trace batch computations"""
        span = self.tracer.start_span(
            f"signal.batch.{computation_type}",
            attributes={
                "batch.size": batch_size,
                "computation.type": computation_type
            }
        )
        return span
```

### 8.2 Performance Monitoring Dashboard
```python
# Grafana Dashboard JSON Configuration
SIGNAL_SERVICE_DASHBOARD = {
    "dashboard": {
        "title": "Signal Service - Horizontal Scaling",
        "panels": [
            {
                "title": "Pod Distribution",
                "targets": [{
                    "expr": "count by (pod_id) (signal_service_instruments_per_pod)"
                }],
                "type": "graph"
            },
            {
                "title": "Backpressure Levels",
                "targets": [{
                    "expr": "signal_service_backpressure_level"
                }],
                "type": "heatmap"
            },
            {
                "title": "Computation Latency (p99)",
                "targets": [{
                    "expr": "histogram_quantile(0.99, signal_service_computation_latency_bucket)"
                }],
                "type": "graph"
            },
            {
                "title": "Load Imbalance Ratio",
                "targets": [{
                    "expr": "signal_service_load_imbalance_ratio"
                }],
                "type": "gauge"
            },
            {
                "title": "Scaling Events",
                "targets": [{
                    "expr": "rate(signal_service_scaling_events[5m])"
                }],
                "type": "graph"
            },
            {
                "title": "Work Stealing Activity",
                "targets": [{
                    "expr": "rate(signal_service_work_stolen_total[1m])"
                }],
                "type": "graph"
            }
        ]
    }
}
```

---

## Implementation Example

### Complete Scaling-Aware Signal Processor
```python
class ScalableSignalProcessor:
    """
    Main signal processor with horizontal scaling capabilities
    """
    
    def __init__(self, pod_id: str):
        self.pod_id = pod_id
        self.coordinator = DistributedCoordinator(pod_id)
        self.assignment_manager = PodAssignmentManager(get_redis_client())
        self.work_queue = WorkStealingQueue(pod_id, total_workers=8)
        self.computation_batcher = ComputationBatcher()
        self.metrics = SignalServiceMetrics()
        self.backpressure_monitor = BackpressureMonitor()
        self.load_shedder = AdaptiveLoadShedder()
        
        # Register pod
        asyncio.create_task(self.register_pod())
    
    async def register_pod(self):
        """Register this pod in the cluster"""
        await self.coordinator.register_pod(capacity=1000)
        await self.assignment_manager.register_pod(self.pod_id, capacity=1000)
    
    async def process_tick(self, tick_data: Dict):
        """Process incoming tick with scaling awareness"""
        instrument_key = tick_data['instrument_key']
        
        # Check if this pod should handle the instrument
        assigned_pod = await self.assignment_manager.get_assigned_pod(instrument_key)
        if assigned_pod != self.pod_id:
            # Forward to correct pod or skip
            return
        
        # Check backpressure
        current_load = await self.get_current_load()
        accept, reason = self.load_shedder.should_accept_request(
            request_priority='medium',
            current_load=current_load,
            instrument_key=instrument_key
        )
        
        if not accept:
            self.metrics.requests_shed.labels(reason=reason).inc()
            return
        
        # Create computation task
        task = ComputationTask(
            instrument_key=instrument_key,
            computation_type='all',
            priority=2,
            timestamp=time.time()
        )
        
        # Add to work queue
        await self.work_queue.push(task)
    
    async def computation_worker(self, worker_id: int):
        """Worker that processes computations"""
        # Set CPU affinity
        cpu_optimizer = CPUAffinityOptimizer()
        cpu_optimizer.optimize_worker_affinity(worker_id, 'greeks')
        
        while True:
            # Get task (with work stealing)
            task = await self.work_queue.pop()
            
            if task:
                try:
                    # Process computation
                    result = await self.process_computation(task)
                    
                    # Update metrics
                    self.metrics.computations_completed.labels(
                        computation_type=task.computation_type
                    ).inc()
                    
                except Exception as e:
                    print(f"Computation failed: {e}")
                    self.metrics.computation_errors.labels(
                        computation_type=task.computation_type,
                        error_type=type(e).__name__
                    ).inc()
            else:
                # No work available, sleep briefly
                await asyncio.sleep(0.01)
    
    async def start(self):
        """Start the scalable signal processor"""
        # Start coordinator
        await self.coordinator.start()
        
        # Start workers
        workers = []
        for i in range(8):  # 8 workers per pod
            worker = asyncio.create_task(self.computation_worker(i))
            workers.append(worker)
        
        # Start metrics updater
        asyncio.create_task(
            self.metrics.update_metrics_loop(self.assignment_manager)
        )
        
        # Start monitoring
        asyncio.create_task(self.monitor_and_scale())
        
        # Wait for workers
        await asyncio.gather(*workers)
    
    async def monitor_and_scale(self):
        """Monitor load and trigger scaling if needed"""
        while True:
            try:
                # Collect metrics
                metrics = await self.collect_metrics()
                
                # Update backpressure monitor
                self.backpressure_monitor.update_metrics(self.pod_id, metrics)
                
                # If we're the leader, make scaling decisions
                if self.coordinator.is_leader:
                    recommendation = self.backpressure_monitor.get_scaling_recommendation()
                    
                    if recommendation['action'] == 'scale_up':
                        print(f"Recommending scale up: {recommendation}")
                        # This would trigger K8s HPA through custom metrics
                        
                await asyncio.sleep(30)
                
            except Exception as e:
                print(f"Monitoring error: {e}")
                await asyncio.sleep(60)
```

---

## Best Practices

### 1. Instrument Assignment
- Use consistent hashing with virtual nodes (150+ per pod)
- Consider instrument characteristics (volume, complexity)
- Implement graceful reassignment during scaling

### 2. Backpressure Handling
- Monitor multiple metrics (queue depth, CPU, latency)
- Implement adaptive load shedding
- Use work stealing for local load balancing

### 3. State Management
- Keep computations stateless where possible
- Use Redis for shared state with TTL
- Implement state migration for rebalancing

### 4. Performance
- Batch similar computations
- Use CPU affinity for compute-intensive tasks
- Implement intelligent caching

### 5. Monitoring
- Track pod-level and cluster-level metrics
- Implement distributed tracing
- Set up alerting for imbalance and backpressure

---

## Conclusion

This horizontal scaling architecture enables the Signal Service to:
- Scale from 3 to 50+ pods based on load
- Distribute instruments intelligently across pods
- Handle backpressure gracefully
- Maintain low latency during scaling events
- Provide comprehensive monitoring and observability

The architecture is designed to handle the demands of a high-frequency trading platform while maintaining the performance requirements needed for real-time signal computation.