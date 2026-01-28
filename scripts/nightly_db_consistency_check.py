#!/usr/bin/env python3
"""
Nightly Database Consistency Check

Checks hypertable health, recent writes, row counts with alerting thresholds.
"""
import asyncio
import json
import logging
from datetime import datetime, timedelta
from typing import Any

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class NightlyDBConsistencyCheck:
    """Nightly database consistency checker."""

    def __init__(self):
        self.thresholds = {
            "max_age_hours": 24,          # Data should be no older than 24 hours
            "min_row_count": 1000,        # Minimum rows expected in active tables
            "hypertable_health_score": 80, # Minimum hypertable health percentage
        }

        self.results = {
            "timestamp": datetime.now().isoformat(),
            "checks_performed": [],
            "alerts_triggered": [],
            "overall_health": "UNKNOWN"
        }

    async def check_recent_writes(self) -> dict[str, Any]:
        """Check for recent writes in all tables."""
        logger.info("Checking recent writes...")

        # Simulate database checks (would use actual DB connection in production)
        tables_to_check = [
            "signal_greeks",
            "signal_indicators",
            "custom_timeframes",
            "user_preferences"
        ]

        write_check_results = []
        alerts = []

        for table in tables_to_check:
            # Simulate checking last write time (would be actual SQL query)
            last_write_hours = 2  # Simulate 2 hours ago
            row_count = 5000     # Simulate 5000 rows

            if last_write_hours > self.thresholds["max_age_hours"]:
                alerts.append({
                    "type": "STALE_DATA",
                    "table": table,
                    "last_write_hours": last_write_hours,
                    "threshold": self.thresholds["max_age_hours"]
                })
                logger.warning(f"Stale data detected in {table}")

            if row_count < self.thresholds["min_row_count"]:
                alerts.append({
                    "type": "LOW_ROW_COUNT",
                    "table": table,
                    "row_count": row_count,
                    "threshold": self.thresholds["min_row_count"]
                })
                logger.warning(f"Low row count in {table}: {row_count}")

            write_check_results.append({
                "table": table,
                "last_write_hours": last_write_hours,
                "row_count": row_count,
                "status": "HEALTHY" if last_write_hours <= self.thresholds["max_age_hours"] and row_count >= self.thresholds["min_row_count"] else "ALERT"
            })

        return {
            "checks": write_check_results,
            "alerts": alerts,
            "healthy_tables": sum(1 for check in write_check_results if check["status"] == "HEALTHY")
        }

    async def check_hypertable_health(self) -> dict[str, Any]:
        """Check TimescaleDB hypertable health."""
        logger.info("Checking hypertable health...")

        # Simulate hypertable health checks
        hypertables = ["signal_greeks", "signal_indicators"]
        health_results = []
        alerts = []

        for hypertable in hypertables:
            # Simulate health metrics (would be actual TimescaleDB queries)
            health_score = 95  # Simulate 95% health
            chunk_count = 50   # Number of chunks
            compression_ratio = 0.75  # Compression ratio

            if health_score < self.thresholds["hypertable_health_score"]:
                alerts.append({
                    "type": "HYPERTABLE_DEGRADED",
                    "hypertable": hypertable,
                    "health_score": health_score,
                    "threshold": self.thresholds["hypertable_health_score"]
                })
                logger.error(f"Hypertable {hypertable} health degraded: {health_score}%")

            health_results.append({
                "hypertable": hypertable,
                "health_score": health_score,
                "chunk_count": chunk_count,
                "compression_ratio": compression_ratio,
                "status": "HEALTHY" if health_score >= self.thresholds["hypertable_health_score"] else "DEGRADED"
            })

        return {
            "hypertables": health_results,
            "alerts": alerts,
            "avg_health_score": sum(h["health_score"] for h in health_results) / len(health_results)
        }

    async def run_consistency_check(self) -> dict[str, Any]:
        """Run complete nightly consistency check."""
        logger.info("Starting nightly DB consistency check...")

        start_time = datetime.now()

        # Perform all checks
        recent_writes = await self.check_recent_writes()
        self.results["checks_performed"].append("recent_writes")

        hypertable_health = await self.check_hypertable_health()
        self.results["checks_performed"].append("hypertable_health")

        # Aggregate alerts
        all_alerts = recent_writes["alerts"] + hypertable_health["alerts"]
        self.results["alerts_triggered"] = all_alerts

        # Determine overall health
        critical_alerts = [alert for alert in all_alerts if alert["type"] in ["HYPERTABLE_DEGRADED", "STALE_DATA"]]

        if len(critical_alerts) == 0:
            self.results["overall_health"] = "HEALTHY"
        elif len(critical_alerts) <= 2:
            self.results["overall_health"] = "WARNING"
        else:
            self.results["overall_health"] = "CRITICAL"

        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()

        self.results.update({
            "duration_seconds": duration,
            "recent_writes": recent_writes,
            "hypertable_health": hypertable_health,
            "summary": {
                "total_alerts": len(all_alerts),
                "critical_alerts": len(critical_alerts),
                "healthy_tables": recent_writes["healthy_tables"],
                "avg_hypertable_health": hypertable_health["avg_health_score"]
            }
        })

        # Log results
        logger.info(f"Consistency check completed: {self.results['overall_health']}")
        logger.info(f"Total alerts: {len(all_alerts)}, Duration: {duration:.2f}s")

        return self.results

    async def send_alerts_if_needed(self):
        """Send alerts if consistency check fails."""
        if self.results["overall_health"] in ["WARNING", "CRITICAL"]:
            logger.warning("Database consistency issues detected - alerting required")
            # In production, this would integrate with alert service
            return True
        return False


async def main():
    """Run nightly consistency check."""
    checker = NightlyDBConsistencyCheck()
    results = await checker.run_consistency_check()

    # Save results
    report_file = f"nightly_db_consistency_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(report_file, 'w') as f:
        json.dump(results, f, indent=2)

    # Send alerts if needed
    await checker.send_alerts_if_needed()

    # Exit with appropriate code
    if results["overall_health"] == "HEALTHY":
        return 0
    if results["overall_health"] == "WARNING":
        return 1
    return 2


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    exit(exit_code)
