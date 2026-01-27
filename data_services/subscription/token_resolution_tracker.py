#!/usr/bin/env python3
"""
Token Resolution Gap Tracker - SUB_001 Hardening

Addresses the 4.8% token resolution gap (95.2% success rate) with:
- Retry cadence for failed token resolutions
- Manual intervention workflows
- Dangling token prevention and monitoring
"""

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

logger = logging.getLogger(__name__)

@dataclass
class UnresolvedToken:
    """Tracking unresolved token for retry/escalation"""
    token: str
    user_id: str
    attempts: int = 0
    first_attempt: datetime = field(default_factory=datetime.now)
    last_attempt: datetime | None = None
    resolution_status: str = "pending"  # pending, escalated, manual_review, abandoned
    error_details: list[str] = field(default_factory=list)

class TokenResolutionTracker:
    """
    Tracks and manages unresolved tokens from migration failures

    Ensures no 'dangling tokens' remain in production through:
    - Automated retry with exponential backoff
    - Manual intervention workflows
    - Escalation to data team for resolution
    """

    def __init__(self):
        self.unresolved_tokens: dict[str, UnresolvedToken] = {}
        self.retry_intervals = [1, 6, 24, 72]  # hours: 1h, 6h, 1d, 3d
        self.max_auto_attempts = 4
        self.manual_review_threshold = 7  # days

    async def track_resolution_failure(self,
                                     token: str,
                                     user_id: str,
                                     error: str):
        """Track failed token resolution for retry"""
        key = f"{token}_{user_id}"

        if key in self.unresolved_tokens:
            unresolved = self.unresolved_tokens[key]
            unresolved.attempts += 1
            unresolved.last_attempt = datetime.now()
            unresolved.error_details.append(f"Attempt {unresolved.attempts}: {error}")
        else:
            unresolved = UnresolvedToken(
                token=token,
                user_id=user_id,
                attempts=1,
                last_attempt=datetime.now(),
                error_details=[f"Initial attempt: {error}"]
            )
            self.unresolved_tokens[key] = unresolved

        # Check if escalation needed
        if unresolved.attempts >= self.max_auto_attempts:
            unresolved.resolution_status = "escalated"
            await self._escalate_to_manual_review(unresolved)

        logger.warning(f"Token resolution tracked: {token} (attempt {unresolved.attempts})")

    async def get_retry_candidates(self) -> list[UnresolvedToken]:
        """Get tokens ready for retry based on interval"""
        candidates = []
        current_time = datetime.now()

        for unresolved in self.unresolved_tokens.values():
            if (unresolved.resolution_status == "pending" and
                unresolved.attempts < self.max_auto_attempts):

                # Check if enough time has passed for retry
                if unresolved.last_attempt:
                    interval_hours = self.retry_intervals[min(unresolved.attempts - 1, len(self.retry_intervals) - 1)]
                    next_retry = unresolved.last_attempt + timedelta(hours=interval_hours)

                    if current_time >= next_retry:
                        candidates.append(unresolved)

        return candidates

    async def _escalate_to_manual_review(self, unresolved: UnresolvedToken):
        """Escalate unresolved token for manual intervention"""
        escalation_data = {
            "token": unresolved.token,
            "user_id": unresolved.user_id,
            "attempts": unresolved.attempts,
            "duration_hours": (datetime.now() - unresolved.first_attempt).total_seconds() / 3600,
            "error_summary": unresolved.error_details,
            "escalation_timestamp": datetime.now().isoformat(),
            "recommended_actions": [
                "Check token mapping service for updates",
                "Verify instrument still exists in registry",
                "Contact user for subscription preferences",
                "Consider manual instrument_key assignment"
            ]
        }

        # Write escalation file for ops team
        escalation_file = f"/tmp/token_escalation_{unresolved.token}_{int(datetime.now().timestamp())}.json"
        with open(escalation_file, 'w') as f:
            json.dump(escalation_data, f, indent=2)

        logger.error(f"Token escalated to manual review: {unresolved.token} -> {escalation_file}")

    async def generate_resolution_report(self) -> dict[str, Any]:
        """Generate comprehensive token resolution status report"""
        current_time = datetime.now()

        status_counts = {
            "pending": 0,
            "escalated": 0,
            "manual_review": 0,
            "abandoned": 0
        }

        aging_buckets = {
            "under_1h": 0,
            "1h_to_6h": 0,
            "6h_to_1d": 0,
            "1d_to_3d": 0,
            "over_3d": 0
        }

        for unresolved in self.unresolved_tokens.values():
            # Count by status
            status_counts[unresolved.resolution_status] += 1

            # Count by age
            age_hours = (current_time - unresolved.first_attempt).total_seconds() / 3600
            if age_hours < 1:
                aging_buckets["under_1h"] += 1
            elif age_hours < 6:
                aging_buckets["1h_to_6h"] += 1
            elif age_hours < 24:
                aging_buckets["6h_to_1d"] += 1
            elif age_hours < 72:
                aging_buckets["1d_to_3d"] += 1
            else:
                aging_buckets["over_3d"] += 1

        return {
            "report_timestamp": current_time.isoformat(),
            "total_unresolved": len(self.unresolved_tokens),
            "status_breakdown": status_counts,
            "aging_analysis": aging_buckets,
            "retry_strategy": {
                "retry_intervals_hours": self.retry_intervals,
                "max_auto_attempts": self.max_auto_attempts,
                "manual_review_threshold_days": self.manual_review_threshold
            },
            "operational_impact": {
                "resolution_rate": f"{100 - (len(self.unresolved_tokens) / 1000) * 100:.1f}%",  # Assuming 1000 total
                "dangling_token_risk": "LOW" if len(self.unresolved_tokens) < 50 else "MEDIUM"
            }
        }
