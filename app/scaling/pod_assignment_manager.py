"""
Pod Assignment Manager for Signal Service
Manages instrument assignments across pods with dynamic load balancing
"""
import asyncio
import json
import os
import time
from dataclasses import dataclass, asdict
from typing import Set, Dict, List, Optional, Tuple
from datetime import datetime

import aioredis
from app.utils.logging_utils import log_info, log_warning, log_exception
from app.utils.redis import get_redis_client

from .consistent_hash_manager import ConsistentHashManager


@dataclass
class PodInfo:
    """Information about a signal service pod"""
    pod_id: str
    capacity: int  # Max instruments per pod
    current_load: int
    assigned_instruments: Set[str]
    cpu_usage: float
    memory_usage: float
    computation_rate: float  # computations/second
    last_heartbeat: float
    status: str  # 'ready', 'overloaded', 'draining'
    
    def to_dict(self) -> Dict:
        """Convert to dictionary for serialization"""
        return {
            **asdict(self),
            'assigned_instruments': list(self.assigned_instruments)
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'PodInfo':
        """Create from dictionary"""
        data['assigned_instruments'] = set(data.get('assigned_instruments', []))
        return cls(**data)


class PodAssignmentManager:
    """
    Manages instrument assignment to pods with dynamic load balancing
    and fault tolerance
    """
    
    def __init__(self):
        self.redis_client = None
        self.hash_manager = ConsistentHashManager()
        self.pods: Dict[str, PodInfo] = {}
        self.instrument_assignments: Dict[str, str] = {}
        
        # Configuration
        self.rebalance_threshold = 0.3  # 30% load difference
        self.overload_threshold = 0.9   # 90% capacity
        self.heartbeat_timeout = 60     # seconds
        self.rebalance_cooldown = 300  # 5 minutes
        
        # State
        self.last_rebalance = datetime.now()
        self.is_rebalancing = False
        
        # Metrics
        self.assignment_metrics = {
            'total_assignments': 0,
            'rebalance_count': 0,
            'failed_assignments': 0
        }
        
    async def initialize(self):
        """Initialize the assignment manager"""
        self.redis_client = await get_redis_client()
        await self.hash_manager.initialize()
        
        # Load existing state
        await self.load_state()
        
        # Start background tasks
        asyncio.create_task(self.heartbeat_monitor())
        asyncio.create_task(self.rebalance_monitor())
        
        log_info("PodAssignmentManager initialized")
    
    async def load_state(self):
        """Load pod and assignment state from Redis"""
        try:
            # Load pods
            pods_data = await self.redis_client.hgetall("signal:pods")
            for pod_id, pod_json in pods_data.items():
                pod_id = pod_id.decode() if isinstance(pod_id, bytes) else pod_id
                pod_data = json.loads(pod_json)
                self.pods[pod_id] = PodInfo.from_dict(pod_data)
                self.hash_manager.add_node(pod_id)
            
            # Load assignments
            assignments = await self.redis_client.hgetall("signal:assignments")
            for instrument, pod_id in assignments.items():
                instrument = instrument.decode() if isinstance(instrument, bytes) else instrument
                pod_id = pod_id.decode() if isinstance(pod_id, bytes) else pod_id
                self.instrument_assignments[instrument] = pod_id
            
            log_info(f"Loaded {len(self.pods)} pods and {len(self.instrument_assignments)} assignments")
            
        except Exception as e:
            log_exception(f"Failed to load state: {e}")
    
    async def register_pod(self, pod_id: str, capacity: int = 1000) -> bool:
        """Register a new pod in the cluster"""
        try:
            # Check if pod already exists
            if pod_id in self.pods:
                log_warning(f"Pod {pod_id} already registered")
                return False
            
            # Create pod info
            pod_info = PodInfo(
                pod_id=pod_id,
                capacity=capacity,
                current_load=0,
                assigned_instruments=set(),
                cpu_usage=0.0,
                memory_usage=0.0,
                computation_rate=0.0,
                last_heartbeat=time.time(),
                status='ready'
            )
            
            # Add to local state
            self.pods[pod_id] = pod_info
            self.hash_manager.add_node(pod_id)
            
            # Store in Redis
            await self.redis_client.hset(
                "signal:pods",
                pod_id,
                json.dumps(pod_info.to_dict())
            )
            
            # Publish registration event
            await self.redis_client.publish(
                "signal:pod_events",
                json.dumps({
                    'event': 'pod_registered',
                    'pod_id': pod_id,
                    'capacity': capacity,
                    'timestamp': time.time()
                })
            )
            
            log_info(f"Registered pod {pod_id} with capacity {capacity}")
            
            # Trigger rebalancing if needed
            if len(self.pods) > 1:
                asyncio.create_task(self.rebalance_if_needed())
            
            return True
            
        except Exception as e:
            log_exception(f"Failed to register pod {pod_id}: {e}")
            return False
    
    async def unregister_pod(self, pod_id: str):
        """Remove a pod and reassign its instruments"""
        if pod_id not in self.pods:
            log_warning(f"Pod {pod_id} not found")
            return
        
        try:
            pod_info = self.pods[pod_id]
            orphaned_instruments = pod_info.assigned_instruments.copy()
            
            log_info(f"Unregistering pod {pod_id} with {len(orphaned_instruments)} instruments")
            
            # Mark pod as draining
            pod_info.status = 'draining'
            await self.update_pod_state(pod_id)
            
            # Reassign instruments
            reassignments = {}
            for instrument in orphaned_instruments:
                new_pod = await self.reassign_instrument(instrument, exclude_pod=pod_id)
                if new_pod:
                    reassignments[instrument] = new_pod
                else:
                    log_warning(f"Failed to reassign {instrument}")
            
            # Remove pod
            self.hash_manager.remove_node(pod_id)
            del self.pods[pod_id]
            
            # Remove from Redis
            await self.redis_client.hdel("signal:pods", pod_id)
            
            # Publish event
            await self.redis_client.publish(
                "signal:pod_events",
                json.dumps({
                    'event': 'pod_unregistered',
                    'pod_id': pod_id,
                    'reassignments': reassignments,
                    'timestamp': time.time()
                })
            )
            
            log_info(f"Unregistered pod {pod_id}, reassigned {len(reassignments)} instruments")
            
        except Exception as e:
            log_exception(f"Failed to unregister pod {pod_id}: {e}")
    
    async def assign_instrument(self, instrument_key: str, preferred_pod: str = None) -> Optional[str]:
        """
        Assign an instrument to a pod using consistent hashing with load awareness
        """
        try:
            # Check if already assigned
            if instrument_key in self.instrument_assignments:
                current_pod = self.instrument_assignments[instrument_key]
                if current_pod in self.pods and self.pods[current_pod].status == 'ready':
                    return current_pod
            
            # Get candidate pods from hash ring
            if preferred_pod and preferred_pod in self.pods:
                candidates = [preferred_pod]
            else:
                candidates = self.hash_manager.get_nodes(instrument_key, count=3)
            
            # Find best pod based on load
            selected_pod = None
            min_load_ratio = float('inf')
            
            for pod_id in candidates:
                if pod_id not in self.pods:
                    continue
                    
                pod_info = self.pods[pod_id]
                
                # Skip pods that are not ready
                if pod_info.status != 'ready':
                    continue
                
                # Calculate load ratio
                load_ratio = pod_info.current_load / pod_info.capacity
                
                # Prefer pod with lowest load that's not overloaded
                if load_ratio < self.overload_threshold and load_ratio < min_load_ratio:
                    min_load_ratio = load_ratio
                    selected_pod = pod_id
            
            # If all candidates are overloaded, find any available pod
            if not selected_pod:
                for pod_id, pod_info in self.pods.items():
                    if pod_info.status == 'ready' and pod_info.current_load < pod_info.capacity:
                        selected_pod = pod_id
                        break
            
            if selected_pod:
                # Update assignment
                await self.update_assignment(instrument_key, selected_pod)
                
                self.assignment_metrics['total_assignments'] += 1
                
                log_info(f"Assigned {instrument_key} to pod {selected_pod} (load: {min_load_ratio:.2%})")
                return selected_pod
            else:
                self.assignment_metrics['failed_assignments'] += 1
                log_warning(f"No available pods for {instrument_key}")
                return None
                
        except Exception as e:
            log_exception(f"Failed to assign {instrument_key}: {e}")
            return None
    
    async def update_assignment(self, instrument_key: str, pod_id: str):
        """Update instrument assignment"""
        # Remove from old pod if reassigning
        old_pod = self.instrument_assignments.get(instrument_key)
        if old_pod and old_pod != pod_id:
            if old_pod in self.pods:
                self.pods[old_pod].assigned_instruments.discard(instrument_key)
                self.pods[old_pod].current_load = len(self.pods[old_pod].assigned_instruments)
        
        # Add to new pod
        self.instrument_assignments[instrument_key] = pod_id
        if pod_id in self.pods:
            self.pods[pod_id].assigned_instruments.add(instrument_key)
            self.pods[pod_id].current_load = len(self.pods[pod_id].assigned_instruments)
        
        # Update Redis
        await self.redis_client.hset("signal:assignments", instrument_key, pod_id)
        
        # Update pod states
        if old_pod and old_pod in self.pods:
            await self.update_pod_state(old_pod)
        await self.update_pod_state(pod_id)
    
    async def reassign_instrument(self, instrument_key: str, exclude_pod: str = None) -> Optional[str]:
        """Reassign an instrument, excluding a specific pod"""
        exclude_nodes = {exclude_pod} if exclude_pod else set()
        
        # Get new pod using hash ring
        new_pod = self.hash_manager.get_node(instrument_key, exclude_nodes)
        
        if new_pod and new_pod != exclude_pod:
            await self.update_assignment(instrument_key, new_pod)
            return new_pod
        
        return None
    
    async def update_pod_metrics(self, pod_id: str, metrics: Dict):
        """Update pod metrics"""
        if pod_id not in self.pods:
            log_warning(f"Unknown pod {pod_id}")
            return
        
        pod_info = self.pods[pod_id]
        
        # Update metrics
        pod_info.cpu_usage = metrics.get('cpu_usage', pod_info.cpu_usage)
        pod_info.memory_usage = metrics.get('memory_usage', pod_info.memory_usage)
        pod_info.computation_rate = metrics.get('computation_rate', pod_info.computation_rate)
        pod_info.last_heartbeat = time.time()
        
        # Update load in hash manager
        await self.hash_manager.update_node_load(pod_id, pod_info.current_load)
        
        # Check if pod is overloaded
        if pod_info.cpu_usage > 0.9 or pod_info.memory_usage > 0.9:
            if pod_info.status == 'ready':
                pod_info.status = 'overloaded'
                log_warning(f"Pod {pod_id} is overloaded")
        elif pod_info.status == 'overloaded' and pod_info.cpu_usage < 0.7 and pod_info.memory_usage < 0.7:
            pod_info.status = 'ready'
            log_info(f"Pod {pod_id} recovered from overload")
        
        # Update state
        await self.update_pod_state(pod_id)
    
    async def update_pod_state(self, pod_id: str):
        """Update pod state in Redis"""
        if pod_id in self.pods:
            await self.redis_client.hset(
                "signal:pods",
                pod_id,
                json.dumps(self.pods[pod_id].to_dict())
            )
    
    async def heartbeat_monitor(self):
        """Monitor pod heartbeats and handle failures"""
        while True:
            try:
                current_time = time.time()
                failed_pods = []
                
                for pod_id, pod_info in self.pods.items():
                    # Check heartbeat timeout
                    if current_time - pod_info.last_heartbeat > self.heartbeat_timeout:
                        log_warning(f"Pod {pod_id} heartbeat timeout")
                        failed_pods.append(pod_id)
                
                # Handle failed pods
                for pod_id in failed_pods:
                    await self.handle_pod_failure(pod_id)
                
                await asyncio.sleep(30)  # Check every 30 seconds
                
            except Exception as e:
                log_exception(f"Heartbeat monitor error: {e}")
                await asyncio.sleep(60)
    
    async def handle_pod_failure(self, pod_id: str):
        """Handle pod failure"""
        log_warning(f"Handling failure of pod {pod_id}")
        
        # Unregister pod (which will reassign instruments)
        await self.unregister_pod(pod_id)
        
        # Alert about pod failure
        await self.redis_client.publish(
            "signal:alerts",
            json.dumps({
                'alert': 'pod_failure',
                'pod_id': pod_id,
                'timestamp': time.time()
            })
        )
    
    async def rebalance_monitor(self):
        """Monitor and trigger rebalancing when needed"""
        while True:
            try:
                await asyncio.sleep(60)  # Check every minute
                
                if not self.is_rebalancing:
                    await self.rebalance_if_needed()
                    
            except Exception as e:
                log_exception(f"Rebalance monitor error: {e}")
                await asyncio.sleep(120)
    
    async def rebalance_if_needed(self):
        """Check if rebalancing is needed and execute"""
        # Check cooldown
        if (datetime.now() - self.last_rebalance).seconds < self.rebalance_cooldown:
            return
        
        # Check if rebalancing is needed
        if await self.should_rebalance():
            await self.execute_rebalance()
    
    async def should_rebalance(self) -> bool:
        """Determine if rebalancing is needed"""
        if len(self.pods) < 2:
            return False
        
        # Calculate load statistics
        loads = [pod.current_load for pod in self.pods.values() if pod.status == 'ready']
        if not loads:
            return False
        
        avg_load = sum(loads) / len(loads)
        max_load = max(loads)
        min_load = min(loads)
        
        # Check threshold
        if max_load > 0 and (max_load - min_load) / max_load > self.rebalance_threshold:
            log_info(f"Rebalancing needed: max={max_load}, min={min_load}, avg={avg_load:.1f}")
            return True
        
        return False
    
    async def execute_rebalance(self):
        """Execute load rebalancing"""
        if self.is_rebalancing:
            return
        
        self.is_rebalancing = True
        self.last_rebalance = datetime.now()
        
        try:
            log_info("Starting load rebalancing")
            
            # Get rebalance plan
            plan = await self.create_rebalance_plan()
            
            if not plan:
                log_info("No rebalancing needed")
                return
            
            # Execute moves
            total_moved = 0
            for move in plan:
                instrument = move['instrument']
                from_pod = move['from']
                to_pod = move['to']
                
                # Update assignment
                await self.update_assignment(instrument, to_pod)
                total_moved += 1
                
                # Publish move event
                await self.redis_client.publish(
                    "signal:rebalance_events",
                    json.dumps({
                        'instrument': instrument,
                        'from_pod': from_pod,
                        'to_pod': to_pod,
                        'timestamp': time.time()
                    })
                )
                
                # Small delay to avoid overwhelming the system
                if total_moved % 10 == 0:
                    await asyncio.sleep(0.1)
            
            self.assignment_metrics['rebalance_count'] += 1
            log_info(f"Rebalancing complete: moved {total_moved} instruments")
            
        except Exception as e:
            log_exception(f"Rebalancing failed: {e}")
        finally:
            self.is_rebalancing = False
    
    async def create_rebalance_plan(self) -> List[Dict]:
        """Create a plan for rebalancing instruments"""
        moves = []
        
        # Sort pods by load
        sorted_pods = sorted(
            [(pod_id, pod) for pod_id, pod in self.pods.items() if pod.status == 'ready'],
            key=lambda x: x[1].current_load,
            reverse=True
        )
        
        if len(sorted_pods) < 2:
            return moves
        
        # Calculate target load
        total_load = sum(pod.current_load for _, pod in sorted_pods)
        target_load = total_load / len(sorted_pods)
        
        # Move instruments from overloaded to underloaded pods
        for i in range(len(sorted_pods) // 2):
            over_pod_id, over_pod = sorted_pods[i]
            under_pod_id, under_pod = sorted_pods[-(i+1)]
            
            # Calculate how many to move
            excess = over_pod.current_load - target_load
            capacity = target_load - under_pod.current_load
            
            if excess <= 0 or capacity <= 0:
                continue
            
            move_count = int(min(excess, capacity))
            
            # Select instruments to move (prefer low-weight instruments)
            instruments_to_move = list(over_pod.assigned_instruments)[:move_count]
            
            for instrument in instruments_to_move:
                moves.append({
                    'instrument': instrument,
                    'from': over_pod_id,
                    'to': under_pod_id
                })
            
            if len(moves) >= 50:  # Limit moves per rebalance
                break
        
        return moves
    
    def get_assignment_stats(self) -> Dict:
        """Get assignment statistics"""
        ready_pods = [p for p in self.pods.values() if p.status == 'ready']
        
        if not ready_pods:
            return {
                'total_pods': len(self.pods),
                'ready_pods': 0,
                'total_instruments': 0,
                'avg_load': 0,
                'load_variance': 0
            }
        
        loads = [p.current_load for p in ready_pods]
        avg_load = sum(loads) / len(loads) if loads else 0
        
        # Calculate variance
        variance = 0
        if len(loads) > 1:
            variance = sum((load - avg_load) ** 2 for load in loads) / len(loads)
        
        return {
            'total_pods': len(self.pods),
            'ready_pods': len(ready_pods),
            'total_instruments': len(self.instrument_assignments),
            'avg_load': avg_load,
            'load_variance': variance ** 0.5,
            'max_load': max(loads) if loads else 0,
            'min_load': min(loads) if loads else 0,
            'assignment_metrics': self.assignment_metrics.copy()
        }
    
    async def get_pod_assignments(self, pod_id: str) -> List[str]:
        """Get all instruments assigned to a pod"""
        if pod_id in self.pods:
            return list(self.pods[pod_id].assigned_instruments)
        return []
    
    async def get_instrument_pod(self, instrument_key: str) -> Optional[str]:
        """Get the pod assigned to an instrument"""
        return self.instrument_assignments.get(instrument_key)  -- TODO: Use EXPLAIN ANALYZE to check performance