"""
Scalable Signal Processor - Main Implementation
Integrates all scaling components for horizontal scalability
"""
import os
import asyncio
import time
from typing import Dict, List, Optional, Any, Set
from datetime import datetime
from enum import Enum
import json

from app.utils.logging_utils import log_info, log_warning, log_exception, log_debug
from app.utils.redis import get_redis_client

# Import production scaling components
from .consistent_hash_manager import ConsistentHashManager
from .pod_assignment_manager import PodAssignmentManager
from .backpressure_monitor import BackpressureMonitor, BackpressureLevel
from .work_stealing_queue import WorkStealingQueue, WorkerPool, ComputationTask, TaskPriority, ComputationWorker
from .adaptive_load_shedder import AdaptiveLoadShedder, RequestPriority

# Import existing signal service components
from app.services.signal_processor import SignalProcessor
from app.services.config_handler import ConfigHandler
from app.services.greeks_calculator import GreeksCalculator
from app.services.realtime_greeks_calculator import RealTimeGreeksCalculator
from app.services.pandas_ta_executor import PandasTAExecutor


class ScalableSignalProcessor:
    """
    Main signal processor with horizontal scaling capabilities
    Manages work distribution, load balancing, and auto-scaling
    """
    
    def __init__(self):
        # Pod identity from environment (required for scaling)
        self.pod_id = os.environ.get('POD_NAME')
        self.node_name = os.environ.get('NODE_NAME')
        
        if not self.pod_id:
            raise RuntimeError("POD_NAME environment variable required for scaling. No fallbacks allowed per architecture.")
        if not self.node_name:
            raise RuntimeError("NODE_NAME environment variable required for scaling. No fallbacks allowed per architecture.")
        
        # Core components
        self.redis_client = None
        self.hash_manager = None  # Will be initialized with Redis client
        self.assignment_manager = None  # Will be initialized with Redis client
        self.backpressure_monitor = None  # Will be initialized with Redis client
        self.load_shedder = AdaptiveLoadShedder()
        
        # Work distribution
        self.worker_pool = WorkerPool(num_workers=8)
        self.computation_workers = []
        
        # Signal processing components (existing)
        self.config_handler = None
        self.greeks_calculator = None
        self.realtime_greeks_calculator = None
        self.pandas_ta_executor = None
        
        # State
        self.is_running = False
        self.assigned_instruments: Set[str] = set()
        self.start_time = time.time()
        
        # Metrics
        self.metrics = {
            'ticks_processed': 0,
            'computations_completed': 0,
            'errors': 0,
            'requests_shed': 0
        }
        
        # Queue depth history for growth rate calculation
        self.queue_depth_history = []  # List of (timestamp, queue_depth) tuples
        self.max_history_size = 10  # Keep last 10 measurements for trend
        
        # Configuration from environment
        pod_capacity_env = os.environ.get('POD_CAPACITY')
        if not pod_capacity_env:
            raise RuntimeError("POD_CAPACITY environment variable required for scaling. No fallbacks allowed per architecture.")
        
        try:
            self.pod_capacity = int(pod_capacity_env)
        except ValueError:
            raise RuntimeError(f"Invalid POD_CAPACITY value: {pod_capacity_env}. Must be an integer.")
        
        self.heartbeat_interval = 30  # seconds - this is operational, not configuration
        
        log_info(f"Initializing ScalableSignalProcessor for pod {self.pod_id}")
    
    async def initialize(self):
        """Initialize all components"""
        try:
            # Initialize Redis
            self.redis_client = await get_redis_client()
            
            # Initialize scaling components with Redis client
            self.hash_manager = ConsistentHashManager(redis_client=self.redis_client)
            self.assignment_manager = PodAssignmentManager(redis_client=self.redis_client)
            self.backpressure_monitor = BackpressureMonitor(redis_client=self.redis_client)
            
            await self.hash_manager.initialize()
            await self.assignment_manager.initialize()
            await self.backpressure_monitor.initialize()
            
            # Register this pod
            await self.assignment_manager.register_pod(self.pod_id, self.pod_capacity)
            
            # Initialize signal processing components
            await self._initialize_signal_components()
            
            # Start background tasks
            asyncio.create_task(self._heartbeat_loop())
            asyncio.create_task(self._metrics_reporter())
            asyncio.create_task(self._monitor_assignments())
            
            log_info(f"ScalableSignalProcessor initialized for pod {self.pod_id}")
            
        except Exception as e:
            log_exception(f"Failed to initialize ScalableSignalProcessor: {e}")
            raise
    
    async def _initialize_signal_components(self):
        """Initialize existing signal service components"""
        # Config handler
        self.config_handler = ConfigHandler(self.redis_client)
        await self.config_handler.initialize()
        
        # Greeks calculators
        from common.storage.database import get_timescaledb_session
        self.greeks_calculator = GreeksCalculator(get_timescaledb_session)
        self.realtime_greeks_calculator = RealTimeGreeksCalculator(self.redis_client)
        
        # Technical indicators
        self.pandas_ta_executor = PandasTAExecutor(self.redis_client)
        
        log_info("Signal processing components initialized")
    
    async def start(self):
        """Start the scalable processor"""
        self.is_running = True
        
        try:
            # Start computation workers
            for i in range(8):
                worker = ComputationWorker(
                    worker_id=f"{self.pod_id}_worker_{i}",
                    queue=self.worker_pool.workers[f"worker_{i}"],
                    processor=self
                )
                self.computation_workers.append(worker)
                asyncio.create_task(worker.start())
            
            # Start tick consumption
            await self._start_tick_consumption()
            
            log_info(f"ScalableSignalProcessor started on pod {self.pod_id}")
            
        except Exception as e:
            log_exception(f"Failed to start processor: {e}")
            self.is_running = False
            raise
    
    async def _start_tick_consumption(self):
        """Start consuming ticks from Redis streams"""
        # Monitor sharded streams
        NUM_SHARDS = 10
        stream_keys = [f"stream:shard:{i}" for i in range(NUM_SHARDS)]
        
        # Create consumer group
        for stream_key in stream_keys:
            try:
                await self.redis_client.xgroup_create(
                    stream_key, 
                    f"signal_service_{self.pod_id}",
                    id='0',
                    mkstream=True
                )
            except:
                pass  # Group exists
        
        # Start consuming
        while self.is_running:
            try:
                # Read from streams
                messages = await self.redis_client.xreadgroup(
                    f"signal_service_{self.pod_id}",
                    self.pod_id,
                    {stream: '>' for stream in stream_keys},
                    count=100,
                    block=1000
                )
                
                # Process messages
                for stream, msgs in messages:
                    for msg_id, fields in msgs:
                        await self._process_tick_message(stream, msg_id, fields)
                        
            except Exception as e:
                log_exception(f"Error in tick consumption: {e}")
                await asyncio.sleep(5)
    
    async def _process_tick_message(self, stream: str, msg_id: str, fields: Dict):
        """Process a tick message"""
        try:
            # Decode fields
            tick_data = {}
            for key, value in fields.items():
                if isinstance(key, bytes):
                    key = key.decode()
                if isinstance(value, bytes):
                    value = value.decode()
                tick_data[key] = value
            
            instrument_key = tick_data.get('instrument_key')
            if not instrument_key:
                return
            
            # Check if we should process this instrument
            assigned_pod = await self.assignment_manager.get_instrument_pod(instrument_key)
            if assigned_pod != self.pod_id:
                # Not our responsibility
                return
            
            # Check load and potentially shed
            current_load = await self._calculate_current_load()
            
            # Determine priority
            priority = self._determine_request_priority(tick_data)
            
            # Load shedding decision
            accept, reason = self.load_shedder.should_accept_request(
                request_priority=priority,
                current_load=current_load,
                instrument_key=instrument_key,
                request_metadata={
                    'tick_age_ms': self._calculate_tick_age(tick_data),
                    'user_tier': tick_data.get('user_tier', 'standard')
                }
            )
            
            if not accept:
                self.metrics['requests_shed'] += 1
                log_debug(f"Shed tick for {instrument_key}: {reason}")
                # Still ACK to prevent redelivery
                await self.redis_client.xack(stream, f"signal_service_{self.pod_id}", msg_id)
                return
            
            # Create computation task
            task = ComputationTask(
                task_id=msg_id,
                instrument_key=instrument_key,
                computation_type='all',  # Compute all signals
                params={
                    'tick_data': tick_data,
                    'timestamp': tick_data.get('timestamp', time.time())
                },
                priority=self._map_to_task_priority(priority),
                timestamp=time.time()
            )
            
            # Submit to worker pool
            submitted = await self.worker_pool.submit_task(task)
            
            if submitted:
                self.metrics['ticks_processed'] += 1
            else:
                log_warning(f"Failed to submit task for {instrument_key}")
                
            # ACK message
            await self.redis_client.xack(stream, f"signal_service_{self.pod_id}", msg_id)
            
        except Exception as e:
            log_exception(f"Failed to process tick message: {e}")
            self.metrics['errors'] += 1
    
    def _determine_request_priority(self, tick_data: Dict) -> RequestPriority:
        """Determine request priority from tick data"""
        # Check for special flags
        if tick_data.get('is_market_order'):
            return RequestPriority.CRITICAL
        
        if tick_data.get('user_initiated'):
            return RequestPriority.HIGH
            
        # Check instrument type
        instrument_key = tick_data.get('instrument_key', '')
        if any(symbol in instrument_key for symbol in ['NIFTY', 'BANKNIFTY']):
            return RequestPriority.HIGH
            
        return RequestPriority.MEDIUM
    
    def _map_to_task_priority(self, request_priority: RequestPriority) -> TaskPriority:
        """Map request priority to task priority"""
        mapping = {
            RequestPriority.CRITICAL: TaskPriority.CRITICAL,
            RequestPriority.HIGH: TaskPriority.HIGH,
            RequestPriority.MEDIUM: TaskPriority.NORMAL,
            RequestPriority.LOW: TaskPriority.LOW
        }
        return mapping[request_priority]
    
    def _calculate_tick_age(self, tick_data: Dict) -> float:
        """Calculate age of tick in milliseconds"""
        tick_timestamp = float(tick_data.get('timestamp', time.time()))
        return (time.time() - tick_timestamp) * 1000
    
    async def _calculate_current_load(self) -> float:
        """Calculate current system load (0-1)"""
        # Get worker pool metrics
        pool_metrics = self.worker_pool.get_pool_metrics()
        
        # Calculate queue saturation
        total_queued = pool_metrics['total_tasks_queued']
        max_queue_capacity = self.worker_pool.num_workers * 1000  # 1000 per worker
        queue_saturation = min(1.0, total_queued / max_queue_capacity)
        
        # Get resource metrics
        cpu_usage = await self._get_cpu_usage()
        memory_usage = await self._get_memory_usage()
        
        # Composite load score
        load = (
            queue_saturation * 0.5 +  # Queue depth most important
            cpu_usage * 0.3 +         # CPU next
            memory_usage * 0.2        # Memory last
        )
        
        return min(1.0, load)
    
    async def _get_cpu_usage(self) -> float:
        """Get current CPU usage (0-1)"""
        try:
            import psutil
            return psutil.cpu_percent(interval=0.1) / 100.0
        except ImportError:
            raise RuntimeError("psutil package required for CPU monitoring. Install with: pip install psutil")
        except Exception as e:
            raise RuntimeError(f"Failed to get CPU usage: {e}. No default values allowed in production.")
    
    async def _get_memory_usage(self) -> float:
        """Get current memory usage (0-1)"""
        try:
            import psutil
            return psutil.virtual_memory().percent / 100.0
        except ImportError:
            raise RuntimeError("psutil package required for memory monitoring. Install with: pip install psutil")
        except Exception as e:
            raise RuntimeError(f"Failed to get memory usage: {e}. No default values allowed in production.")
    
    async def _heartbeat_loop(self):
        """Send regular heartbeats and metrics"""
        while self.is_running:
            try:
                # Collect metrics
                metrics = await self._collect_pod_metrics()
                
                # Update assignment manager
                await self.assignment_manager.update_pod_metrics(self.pod_id, metrics)
                
                # Update backpressure monitor
                self.backpressure_monitor.update_metrics(self.pod_id, metrics)
                
                # Get scaling recommendation
                recommendation = self.backpressure_monitor.get_scaling_recommendation()
                if recommendation.action != 'none':
                    log_info(f"Scaling recommendation: {recommendation.to_dict()}")
                
                await asyncio.sleep(self.heartbeat_interval)
                
            except Exception as e:
                log_exception(f"Heartbeat error: {e}")
                await asyncio.sleep(60)
    
    async def _collect_pod_metrics(self) -> Dict:
        """Collect comprehensive pod metrics"""
        pool_metrics = self.worker_pool.get_pool_metrics()
        
        # Calculate latencies
        computation_times = []
        for worker in self.computation_workers:
            if hasattr(worker, 'computation_times') and worker.computation_times:
                computation_times.extend(worker.computation_times)
        
        p50_latency = 0
        p99_latency = 0
        if computation_times:
            computation_times.sort()
            p50_latency = computation_times[int(len(computation_times) * 0.5)] * 1000
            p99_latency = computation_times[int(len(computation_times) * 0.99)] * 1000
        
        # Calculate queue growth rate
        current_time = time.time()
        current_queue_depth = pool_metrics['total_tasks_queued']
        queue_growth_rate = self._calculate_queue_growth_rate(current_time, current_queue_depth)
        
        return {
            'queue_depth': current_queue_depth,
            'queue_capacity': self.worker_pool.num_workers * 1000,
            'queue_growth_rate': queue_growth_rate,
            'p50_latency': p50_latency,
            'p99_latency': p99_latency,
            'computations_per_second': self.metrics['computations_completed'] / max(1, time.time() - self.start_time),
            'error_rate': self.metrics['errors'] / max(1, self.metrics['ticks_processed']),
            'cpu_usage': await self._get_cpu_usage(),
            'memory_usage': await self._get_memory_usage()
        }
    
    async def _monitor_assignments(self):
        """Monitor instrument assignments and handle changes"""
        while self.is_running:
            try:
                # Get current assignments for this pod
                new_assignments = set(
                    await self.assignment_manager.get_pod_assignments(self.pod_id)
                )
                
                # Check for changes
                added = new_assignments - self.assigned_instruments
                removed = self.assigned_instruments - new_assignments
                
                if added:
                    log_info(f"New instruments assigned: {len(added)}")
                    for instrument in added:
                        await self._handle_new_assignment(instrument)
                
                if removed:
                    log_info(f"Instruments removed: {len(removed)}")
                    for instrument in removed:
                        await self._handle_removed_assignment(instrument)
                
                self.assigned_instruments = new_assignments
                
                await asyncio.sleep(30)  # Check every 30 seconds
                
            except Exception as e:
                log_exception(f"Assignment monitoring error: {e}")
                await asyncio.sleep(60)
    
    async def _handle_new_assignment(self, instrument_key: str):
        """Handle newly assigned instrument"""
        # Load configuration for instrument
        configs = await self.config_handler.get_configs_for_instrument(instrument_key)
        log_info(f"Loaded {len(configs)} configs for {instrument_key}")
    
    async def _handle_removed_assignment(self, instrument_key: str):
        """Handle removed instrument assignment"""
        # Clean up any cached data
        pass
    
    async def _metrics_reporter(self):
        """Report metrics to monitoring system"""
        while self.is_running:
            try:
                metrics = {
                    'pod_id': self.pod_id,
                    'node_name': self.node_name,
                    'assigned_instruments': list(self.assigned_instruments),  # Keep as list, not count
                    'assigned_instruments_count': len(self.assigned_instruments),  # Add count separately  
                    'ticks_processed': self.metrics['ticks_processed'],
                    'computations_completed': self.metrics['computations_completed'],
                    'errors': self.metrics['errors'],
                    'requests_shed': self.metrics['requests_shed'],
                    'worker_pool': self.worker_pool.get_pool_metrics(),
                    'load_shedder': self.load_shedder.get_shedding_stats()
                }
                
                # Publish to Redis using consistent key format
                metrics_key = f"signal:pod:metrics:{self.pod_id}"
                await self.redis_client.setex(
                    metrics_key,
                    60,
                    json.dumps(metrics)
                )
                
                # Also publish for health manager compatibility
                await self.redis_client.setex(
                    f"signal:instance:metrics:{self.pod_id}",
                    60,
                    json.dumps(metrics)
                )
                
                await asyncio.sleep(10)  # Report every 10 seconds
                
            except Exception as e:
                log_exception(f"Metrics reporting error: {e}")
                await asyncio.sleep(30)
    
    # Signal computation methods (called by workers)
    
    async def compute_greeks_for_instrument(self, instrument_key: str, params: Dict):
        """Compute Greeks for an instrument"""
        try:
            # Implementation would call actual Greeks calculator
            result = await self.greeks_calculator.calculate_greeks(
                instrument_key,
                params.get('tick_data', {})
            )
            
            # Publish result
            await self._publish_computation_result(
                instrument_key,
                'greeks',
                result
            )
            
            self.metrics['computations_completed'] += 1
            
        except Exception as e:
            log_exception(f"Greeks computation failed for {instrument_key}: {e}")
            self.metrics['errors'] += 1
    
    async def compute_indicators_for_instrument(self, instrument_key: str, params: Dict):
        """Compute technical indicators"""
        try:
            # Implementation would call indicator calculator
            result = await self.pandas_ta_executor.calculate_indicators(
                instrument_key,
                params.get('indicators', [])
            )
            
            await self._publish_computation_result(
                instrument_key,
                'indicators',
                result
            )
            
            self.metrics['computations_completed'] += 1
            
        except Exception as e:
            log_exception(f"Indicator computation failed for {instrument_key}: {e}")
            self.metrics['errors'] += 1
    
    async def compute_moneyness_greeks(self, underlying: str, moneyness_level: str, timeframe: str):
        """Compute moneyness-based Greeks using real moneyness calculator"""
        try:
            # PRODUCTION: Use real moneyness Greeks calculator instead of synthetic data
            from app.services.moneyness_greeks_calculator import MoneynessAwareGreeksCalculator
            from app.adapters.ticker_adapter import EnhancedTickerAdapter
            
            # Get real spot price
            ticker_adapter = EnhancedTickerAdapter()
            try:
                spot_price = await ticker_adapter.get_latest_price(underlying)
            finally:
                await ticker_adapter.close()
            
            if not spot_price or spot_price <= 0:
                raise ValueError(f"No valid spot price available for {underlying} from ticker_service")
            
            # Calculate real moneyness Greeks
            calculator = MoneynessAwareGreeksCalculator()
            # PRODUCTION: Get expiry date from instrument service instead of hardcoding
            try:
                from app.services.instrument_service_client import InstrumentServiceClient
                instrument_client = InstrumentServiceClient()
                
                # Get current active expiries for the underlying
                expiries = await instrument_client.get_active_expiries(underlying)
                if not expiries:
                    raise ValueError(f"No active expiries found for {underlying}")
                
                # Use the nearest expiry (first in sorted list)
                expiry_date = sorted(expiries)[0]
                
            except Exception as e:
                raise ValueError(f"Failed to get expiry dates for {underlying} from instrument_service: {e}. No hardcoded expiry fallbacks allowed in production.")
            
            result = await calculator.calculate_moneyness_greeks(
                underlying_symbol=underlying,
                spot_price=spot_price,
                moneyness_level=moneyness_level,
                expiry_date=expiry_date
            )
            
            if not result or not result.get('aggregated_greeks'):
                raise ValueError(f"No valid moneyness Greeks computed for {underlying} {moneyness_level}")
            
            await self._publish_computation_result(
                f"{underlying}_{moneyness_level}",
                'moneyness_greeks',
                result
            )
            
            self.metrics['computations_completed'] += 1
            
        except Exception as e:
            log_exception(f"Moneyness Greeks failed for {underlying}: {e}")
            self.metrics['errors'] += 1
            # PRODUCTION: Fail fast instead of returning synthetic data
            raise ValueError(f"Failed to compute moneyness Greeks for {underlying} {moneyness_level}: {e}. No synthetic data allowed in production.")
    
    async def _publish_computation_result(self, instrument_key: str, computation_type: str, result: Dict):
        """Publish computation result"""
        output_data = {
            'instrument_key': instrument_key,
            'computation_type': computation_type,
            'timestamp': datetime.now().isoformat(),
            'pod_id': self.pod_id,
            'result': result
        }
        
        # Publish to Redis stream
        stream_key = f"signal:output:{instrument_key}"
        await self.redis_client.xadd(stream_key, output_data, maxlen=1000)
        
        # Also publish to list for compatibility
        list_key = f"signal:computed:{instrument_key}"
        await self.redis_client.lpush(list_key, json.dumps(output_data))
        await self.redis_client.ltrim(list_key, 0, 999)
    
    async def shutdown(self):
        """Graceful shutdown"""
        log_info(f"Shutting down ScalableSignalProcessor on pod {self.pod_id}")
        
        self.is_running = False
        
        # Stop workers
        for worker in self.computation_workers:
            worker.stop()
        
        # Unregister pod
        await self.assignment_manager.unregister_pod(self.pod_id)
        
        log_info(f"ScalableSignalProcessor shutdown complete")
    
    def _calculate_queue_growth_rate(self, current_time: float, current_queue_depth: int) -> float:
        """Calculate queue depth growth rate (items per second)"""
        try:
            # Add current measurement to history
            self.queue_depth_history.append((current_time, current_queue_depth))
            
            # Keep only recent history
            if len(self.queue_depth_history) > self.max_history_size:
                self.queue_depth_history.pop(0)
            
            # Need at least 2 points to calculate rate
            if len(self.queue_depth_history) < 2:
                return 0.0
            
            # Calculate linear regression slope (items per second)
            # Simple approach: use first and last points
            first_time, first_depth = self.queue_depth_history[0]
            last_time, last_depth = self.queue_depth_history[-1]
            
            time_diff = last_time - first_time
            if time_diff <= 0:
                return 0.0
            
            depth_diff = last_depth - first_depth
            growth_rate = depth_diff / time_diff
            
            return round(growth_rate, 2)
            
        except Exception as e:
            log_exception(f"Failed to calculate queue growth rate: {e}")
            return 0.0