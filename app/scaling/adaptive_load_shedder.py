"""
Adaptive Load Shedding for Signal Service
Implements intelligent request dropping to prevent system overload
"""
import random
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from enum import Enum

from prometheus_client import Counter, Gauge, Histogram

from app.utils.logging_utils import log_debug, log_info


class RequestPriority(Enum):
    """Request priority levels"""
    CRITICAL = "critical"     # Never shed - stop losses, market orders
    HIGH = "high"           # Rarely shed - user-initiated requests
    MEDIUM = "medium"       # Normal shedding - regular computations
    LOW = "low"            # Aggressive shedding - background tasks


@dataclass
class LoadSheddingPolicy:
    """Policy for load shedding at different levels"""
    priority: RequestPriority
    start_shedding_at: float  # Load threshold to start shedding
    max_shed_ratio: float     # Maximum percentage to shed

    def get_shed_probability(self, current_load: float) -> float:
        """Calculate probability of shedding based on load"""
        if current_load < self.start_shedding_at:
            return 0.0

        # Linear increase from 0 to max_shed_ratio
        load_range = 1.0 - self.start_shedding_at
        load_above_threshold = current_load - self.start_shedding_at

        return min(self.max_shed_ratio * (load_above_threshold / load_range), self.max_shed_ratio)


class AdaptiveLoadShedder:
    """
    Implements adaptive load shedding to prevent system overload
    Uses multiple signals to make shedding decisions
    """

    def __init__(self):
        # Shedding policies by priority
        self.policies = {
            RequestPriority.CRITICAL: LoadSheddingPolicy(
                priority=RequestPriority.CRITICAL,
                start_shedding_at=1.0,  # Never shed
                max_shed_ratio=0.0
            ),
            RequestPriority.HIGH: LoadSheddingPolicy(
                priority=RequestPriority.HIGH,
                start_shedding_at=0.9,  # Start at 90% load
                max_shed_ratio=0.2      # Max 20% shed
            ),
            RequestPriority.MEDIUM: LoadSheddingPolicy(
                priority=RequestPriority.MEDIUM,
                start_shedding_at=0.7,  # Start at 70% load
                max_shed_ratio=0.5      # Max 50% shed
            ),
            RequestPriority.LOW: LoadSheddingPolicy(
                priority=RequestPriority.LOW,
                start_shedding_at=0.5,  # Start at 50% load
                max_shed_ratio=0.8      # Max 80% shed
            )
        }

        # High-value instruments (never shed critical requests)
        self.high_value_instruments = {
            'NSE@NIFTY@INDEX',
            'NSE@BANKNIFTY@INDEX',
            'NSE@RELIANCE@EQUITY',
            'NSE@TCS@EQUITY',
            'NSE@HDFC@EQUITY',
            'NSE@INFY@EQUITY'
        }

        # Metrics tracking
        self.shed_counts = defaultdict(int)
        self.accept_counts = defaultdict(int)
        self.recent_decisions = deque(maxlen=1000)

        # Adaptive parameters
        self.load_history = deque(maxlen=60)  # 1 minute of history
        self.adaptive_threshold = 0.0  # Learned threshold
        self.learning_rate = 0.1

        # State
        self.is_shedding_active = False
        self.last_shed_time = 0
        self.consecutive_overloads = 0

        # Prometheus metrics
        self._init_metrics()

    def _init_metrics(self):
        """Initialize Prometheus metrics"""
        self.requests_total = Counter(
            'signal_service_requests_total',
            'Total requests received',
            ['priority', 'instrument_type', 'decision']
        )

        self.shed_ratio_gauge = Gauge(
            'signal_service_shed_ratio',
            'Current shedding ratio',
            ['priority']
        )

        self.load_gauge = Gauge(
            'signal_service_load_shedder_load',
            'Current system load as seen by load shedder'
        )

        self.shed_latency = Histogram(
            'signal_service_shed_decision_latency',
            'Time to make shedding decision',
            buckets=[0.0001, 0.0005, 0.001, 0.005, 0.01]
        )

    def should_accept_request(
        self,
        request_priority: RequestPriority,
        current_load: float,
        instrument_key: str,
        request_metadata: dict | None = None
    ) -> tuple[bool, str]:
        """
        Determine if request should be accepted or shed

        Returns:
            (accepted, reason)
        """
        start_time = time.time()

        try:
            # Update load history
            self.load_history.append(current_load)
            self.load_gauge.set(current_load)

            # Critical requests for high-value instruments always accepted
            if (request_priority == RequestPriority.CRITICAL and
                instrument_key in self.high_value_instruments):
                self._record_decision(True, request_priority, instrument_key, "high_value_critical")
                return True, "high_value_critical"

            # Get shedding policy
            policy = self.policies[request_priority]

            # Calculate shed probability
            shed_probability = policy.get_shed_probability(current_load)

            # Apply adaptive adjustments
            shed_probability = self._apply_adaptive_adjustments(
                shed_probability,
                current_load,
                request_priority
            )

            # Consider additional factors
            if request_metadata:
                shed_probability = self._adjust_for_metadata(
                    shed_probability,
                    request_metadata
                )

            # Make probabilistic decision
            accept = random.random() > shed_probability

            # Determine reason
            if accept:
                reason = "below_threshold" if shed_probability == 0 else "probabilistic_accept"
            else:
                reason = f"load_shedding_{current_load:.1%}"

            # Record decision
            self._record_decision(accept, request_priority, instrument_key, reason)

            # Update shedding state
            self._update_shedding_state(current_load, not accept)

            return accept, reason

        finally:
            # Record decision latency
            self.shed_latency.observe(time.time() - start_time)

    def _apply_adaptive_adjustments(
        self,
        base_probability: float,
        current_load: float,
        priority: RequestPriority
    ) -> float:
        """Apply adaptive adjustments based on system behavior"""

        # Check if load is increasing rapidly
        if len(self.load_history) >= 10:
            recent_loads = list(self.load_history)[-10:]
            load_trend = (recent_loads[-1] - recent_loads[0]) / len(recent_loads)

            if load_trend > 0.05:  # Load increasing > 5% per second
                # Be more aggressive with shedding
                base_probability = min(1.0, base_probability * 1.5)
                log_debug(f"Load trending up rapidly ({load_trend:.2f}/s), increased shed probability")

        # Check consecutive overloads
        if self.consecutive_overloads > 5:
            # System struggling, be more aggressive
            adjustment = min(0.2, self.consecutive_overloads * 0.02)
            base_probability = min(1.0, base_probability + adjustment)

        # Apply learned threshold
        if current_load > self.adaptive_threshold:
            # Above learned danger zone
            base_probability = min(1.0, base_probability * 1.2)

        return base_probability

    def _adjust_for_metadata(
        self,
        shed_probability: float,
        metadata: dict
    ) -> float:
        """Adjust shedding probability based on request metadata"""

        # User tier adjustment
        user_tier = metadata.get('user_tier', 'standard')
        if user_tier == 'premium':
            shed_probability *= 0.5  # 50% less likely to shed
        elif user_tier == 'vip':
            shed_probability *= 0.2  # 80% less likely to shed

        # Request age (older requests less likely to be shed)
        request_age = metadata.get('request_age_ms', 0)
        if request_age > 1000:  # Over 1 second old
            shed_probability *= 0.7

        # Retry count (avoid shedding retries)
        retry_count = metadata.get('retry_count', 0)
        if retry_count > 0:
            shed_probability *= max(0.1, 1.0 - (retry_count * 0.3))

        return shed_probability

    def _record_decision(
        self,
        accepted: bool,
        priority: RequestPriority,
        instrument_key: str,
        reason: str
    ):
        """Record shedding decision for metrics"""
        decision = "accept" if accepted else "shed"

        # Update counters
        if accepted:
            self.accept_counts[priority] += 1
        else:
            self.shed_counts[priority] += 1

        # Prometheus metrics
        instrument_type = self._get_instrument_type(instrument_key)
        self.requests_total.labels(
            priority=priority.value,
            instrument_type=instrument_type,
            decision=decision
        ).inc()

        # Update shed ratio
        total = self.accept_counts[priority] + self.shed_counts[priority]
        if total > 0:
            shed_ratio = self.shed_counts[priority] / total
            self.shed_ratio_gauge.labels(priority=priority.value).set(shed_ratio)

        # Record for adaptive learning
        self.recent_decisions.append({
            'timestamp': time.time(),
            'accepted': accepted,
            'priority': priority,
            'reason': reason,
            'load': self.load_history[-1] if self.load_history else 0
        })

    def _update_shedding_state(self, current_load: float, shed_occurred: bool):
        """Update internal shedding state"""
        # Track consecutive overloads
        if current_load > 0.8:
            self.consecutive_overloads += 1
        else:
            self.consecutive_overloads = 0

        # Update shedding active state
        if shed_occurred:
            self.is_shedding_active = True
            self.last_shed_time = time.time()
        elif time.time() - self.last_shed_time > 30:  # No shedding for 30s
            self.is_shedding_active = False

        # Adaptive learning
        if len(self.recent_decisions) >= 100:
            self._update_adaptive_threshold()

    def _update_adaptive_threshold(self):
        """Update adaptive threshold based on recent decisions"""
        # Find load level where system starts struggling
        struggling_loads = []

        for i in range(len(self.recent_decisions) - 10, len(self.recent_decisions)):
            if i >= 0:
                decision = self.recent_decisions[i]
                if not decision['accepted'] and decision['priority'] != RequestPriority.LOW:
                    struggling_loads.append(decision['load'])

        if struggling_loads:
            # Update threshold using exponential moving average
            new_threshold = sum(struggling_loads) / len(struggling_loads)
            self.adaptive_threshold = (
                self.adaptive_threshold * (1 - self.learning_rate) +
                new_threshold * self.learning_rate
            )
            log_debug(f"Updated adaptive threshold to {self.adaptive_threshold:.2f}")

    def _get_instrument_type(self, instrument_key: str) -> str:
        """Extract instrument type from key"""
        parts = instrument_key.split('@')
        if len(parts) >= 3:
            return parts[2]  # EQUITY, OPTION, FUTURE, etc.
        return "unknown"

    def get_shedding_stats(self) -> dict:
        """Get current shedding statistics"""
        stats = {
            'is_shedding_active': self.is_shedding_active,
            'current_load': self.load_history[-1] if self.load_history else 0,
            'adaptive_threshold': self.adaptive_threshold,
            'consecutive_overloads': self.consecutive_overloads,
            'shed_counts': dict(self.shed_counts),
            'accept_counts': dict(self.accept_counts),
            'shed_ratios': {}
        }

        # Calculate shed ratios
        for priority in RequestPriority:
            total = self.accept_counts[priority] + self.shed_counts[priority]
            if total > 0:
                stats['shed_ratios'][priority.value] = self.shed_counts[priority] / total
            else:
                stats['shed_ratios'][priority.value] = 0.0

        return stats

    def reset_stats(self):
        """Reset statistics (for testing or maintenance)"""
        self.shed_counts.clear()
        self.accept_counts.clear()
        self.recent_decisions.clear()
        log_info("Load shedder statistics reset")


class PriorityBasedLoadShedder:
    """
    Alternative implementation using strict priority-based shedding
    """

    def __init__(self):
        self.priority_queues = {
            priority: deque() for priority in RequestPriority
        }
        self.max_queue_sizes = {
            RequestPriority.CRITICAL: 1000,
            RequestPriority.HIGH: 500,
            RequestPriority.MEDIUM: 200,
            RequestPriority.LOW: 100
        }

    def should_accept_request(
        self,
        request_priority: RequestPriority,
        current_load: float,
        instrument_key: str
    ) -> tuple[bool, str]:
        """Priority-based acceptance decision"""

        # Check queue size
        queue = self.priority_queues[request_priority]
        max_size = self.max_queue_sizes[request_priority]

        if len(queue) >= max_size:
            # Queue full, check if we can evict lower priority
            if self._evict_lower_priority(request_priority):
                return True, "evicted_lower_priority"
            return False, "queue_full"

        return True, "queue_available"

    def _evict_lower_priority(self, incoming_priority: RequestPriority) -> bool:
        """Try to evict a lower priority request"""
        # Check lower priority queues
        for priority in reversed(list(RequestPriority)):
            if priority.value < incoming_priority.value:
                queue = self.priority_queues[priority]
                if queue:
                    queue.pop()  # Remove oldest low priority
                    return True
        return False
