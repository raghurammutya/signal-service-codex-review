"""Stubbed backpressure monitor for tests."""

from dataclasses import dataclass
from enum import Enum
from typing import List, Dict, Any


class BackpressureLevel(Enum):
    LOW = 1
    MEDIUM = 2
    HIGH = 3
    CRITICAL = 4


@dataclass
class ScalingRecommendation:
    action: str
    urgency: str
    recommended_pods: int
    reason: str = ""


class BackpressureMonitor:
    """Minimal monitor that avoids Prometheus side effects."""

    def __init__(self):
        self.current_level = BackpressureLevel.LOW
        self.queue_size = 0
        self.processing_rate = 0.0
        self.memory_usage = 0.0
        self.metrics_history: List[Dict[str, Any]] = []

    def update_queue_size(self, size: int):
        self.queue_size = size
        self._record_metrics(append_new=True)

    def update_processing_rate(self, rate: float):
        self.processing_rate = rate
        self._record_metrics(replace_last=True)

    def update_memory_usage(self, usage: float):
        self.memory_usage = usage
        self._record_metrics(replace_last=True)

    def _record_metrics(self, append_new: bool = False, replace_last: bool = False):
        snapshot = {
            "queue_size": self.queue_size,
            "processing_rate": self.processing_rate,
            "memory_usage": self.memory_usage,
            "timestamp": len(self.metrics_history),
        }
        if append_new or not self.metrics_history:
            self.metrics_history.append(snapshot)
        elif replace_last:
            self.metrics_history[-1] = snapshot

    def _calculate_rate_based_level(self) -> BackpressureLevel:
        if self.processing_rate >= 100:
            return BackpressureLevel.LOW
        if self.processing_rate >= 50:
            return BackpressureLevel.MEDIUM
        if self.processing_rate >= 20:
            return BackpressureLevel.HIGH
        return BackpressureLevel.CRITICAL

    def _calculate_memory_based_level(self) -> BackpressureLevel:
        if self.memory_usage >= 90:
            return BackpressureLevel.CRITICAL
        if self.memory_usage >= 80:
            return BackpressureLevel.HIGH
        if self.memory_usage >= 60:
            return BackpressureLevel.MEDIUM
        return BackpressureLevel.LOW

    def get_backpressure_level(self) -> BackpressureLevel:
        # Combine queue, rate, memory
        queue_level = (
            BackpressureLevel.CRITICAL if self.queue_size >= 2000
            else BackpressureLevel.HIGH if self.queue_size >= 1200
            else BackpressureLevel.MEDIUM if self.queue_size >= 500
            else BackpressureLevel.LOW
        )
        rate_level = self._calculate_rate_based_level() if self.processing_rate else BackpressureLevel.LOW
        mem_level = self._calculate_memory_based_level()
        # Take the highest severity
        self.current_level = max(queue_level, rate_level, mem_level, key=lambda x: x.value)
        return self.current_level

    def get_trend_analysis(self) -> Dict[str, Any]:
        history = self.metrics_history[-5:] if len(self.metrics_history) > 5 else self.metrics_history
        if len(history) < 2:
            return {"direction": "stable", "severity": "low"}
        deltas = [history[i]["queue_size"] - history[i - 1]["queue_size"] for i in range(1, len(history))]
        delta_sum = sum(deltas)
        trend = "increasing" if delta_sum > 0 else "decreasing" if delta_sum < 0 else "stable"
        severity = "high" if abs(delta_sum) > 500 else "medium" if abs(delta_sum) > 100 else "low"
        return {"direction": trend, "severity": severity}

    def get_scaling_recommendations(self) -> Dict[str, Any]:
        level = self.get_backpressure_level()
        if level == BackpressureLevel.CRITICAL:
            return {"action": "scale_up", "urgency": "critical", "target_replicas": 3}
        if level == BackpressureLevel.HIGH:
            return {"action": "scale_up", "urgency": "high", "target_replicas": 2}
        if level == BackpressureLevel.MEDIUM:
            return {"action": "none", "urgency": "medium", "target_replicas": 1}
        return {"action": "none", "urgency": "low", "target_replicas": 1}
