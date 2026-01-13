"""Stubbed Docker orchestrator for unit tests."""

import logging
import time
from typing import Dict, Any


logger = logging.getLogger(__name__)


class DockerOrchestrator:
    """Lightweight orchestrator that mimics scaling decisions without Docker."""

    def __init__(self):
        self.min_instances = 1
        self.max_instances = 10
        self.scale_cooldown = 30
        self.last_scaling_time = None

    async def _make_scaling_decision(self, current_replicas: int, recommendations: Dict[str, Any]) -> Dict[str, Any]:
        action = recommendations.get("action", "none")
        target = recommendations.get("target_replicas", current_replicas)
        urgency = recommendations.get("urgency", "low")

        target = max(self.min_instances, min(self.max_instances, target))

        # Cooldown handling
        if (
            self.last_scaling_time
            and (time.time() - self.last_scaling_time) < self.scale_cooldown
            and urgency != "critical"
        ):
            return {"scale": False, "reason": "cooldown"}

        if action == "none":
            return {"scale": False, "reason": "no_action"}

        direction = "up" if target > current_replicas else "down"
        return {"scale": True, "target_replicas": target, "direction": direction}

    async def _get_cluster_health(self) -> Dict[str, Any]:
        # Simulate three instances using _check_instance_health
        results = [
            await self._check_instance_health(),
            await self._check_instance_health(),
            await self._check_instance_health(),
        ]
        healthy = [r for r in results if r.get("healthy")]
        unhealthy = len(results) - len(healthy)
        overall = sum(1 if r.get("healthy") else 0 for r in results) / len(results)
        return {
            "overall_health": overall,
            "unhealthy_instances": unhealthy,
        }

    async def _check_instance_health(self):
        return {"healthy": True, "response_time": 50}

    async def _shutdown_instance(self, instance_id: str) -> bool:
        await self._send_shutdown_signal(instance_id)
        graceful = await self._wait_for_graceful_shutdown(instance_id)
        if not graceful:
            await self._force_stop_container(instance_id)
        return True

    async def _handle_scale_up(self, current: int, target: int):
        started_instances = []
        try:
            for _ in range(max(0, target - current)):
                instance_id = await self._start_new_instance()
                started_instances.append(instance_id)
                await self._register_with_load_balancer(instance_id)
            return {"success": True, "started": started_instances}
        except Exception as exc:
            await self._cleanup_failed_scaling(started_instances)
            return {"success": False, "error": str(exc)}

    async def _handle_scale_down(self, current: int, target: int):
        for _ in range(max(0, current - target)):
            await self._deregister_from_load_balancer("old-instance")
        return {"success": True}

    # The following are placeholders that can be patched in tests
    async def _send_shutdown_signal(self, instance_id: str):  # pragma: no cover - patched in tests
        return True

    async def _wait_for_graceful_shutdown(self, instance_id: str):  # pragma: no cover - patched in tests
        return True

    async def _force_stop_container(self, instance_id: str):  # pragma: no cover - patched in tests
        return True

    async def _register_with_load_balancer(self, instance_id: str):  # pragma: no cover - patched in tests
        return True

    async def _deregister_from_load_balancer(self, instance_id: str):  # pragma: no cover - patched in tests
        return True

    async def _start_new_instance(self, *_args, **_kwargs):  # pragma: no cover - patched in tests
        return True

    async def _stop_instance(self, *_args, **_kwargs):  # pragma: no cover - patched in tests
        return True

    async def _emit_scaling_metrics(self, *_args, **_kwargs):
        return True

    async def _cleanup_failed_scaling(self, started_instances):
        for inst in started_instances:
            try:
                await self._deregister_from_load_balancer(inst)
            except Exception:
                continue

    async def _execute_scaling_decision(self, decision: Dict[str, Any]):
        if not decision.get("scale"):
            return {"success": True}
        result = None
        if decision.get("direction") == "up":
            result = await self._handle_scale_up(0, decision.get("target_replicas", 1))
        else:
            result = await self._handle_scale_down(decision.get("target_replicas", 1), 0)
        await self._emit_scaling_metrics({"event_type": "scaling_initiated", **decision})
        return result
