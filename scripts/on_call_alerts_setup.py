#!/usr/bin/env python3
"""
On-Call Alerts Setup

Wires critical alerts to on-call for config-service reachability, pool exhaustion,
breaker open count, backpressure activation, and 5xx/latency SLO breaches.
"""
import json
import os
from datetime import datetime
from typing import Any


class OnCallAlertsSetup:
    """On-call alerting configuration for critical production events."""

    def __init__(self):
        self.timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        self.alerts_dir = "alerting"
        os.makedirs(self.alerts_dir, exist_ok=True)

        self.alert_rules = {}
        self.notification_channels = {}

    def create_alertmanager_config(self) -> dict[str, Any]:
        """Create AlertManager configuration for routing alerts to on-call."""
        print("🚨 Creating AlertManager Configuration...")

        alertmanager_config = {
            "global": {
                "smtp_smarthost": "${SMTP_HOST}:587",
                "smtp_from": "alerts@signal-service.com"
            },
            "route": {
                "group_by": ["alertname"],
                "group_wait": "10s",
                "group_interval": "10s",
                "repeat_interval": "1h",
                "receiver": "web.hook",
                "routes": [
                    {
                        "match": {
                            "severity": "critical"
                        },
                        "receiver": "critical-alerts",
                        "group_wait": "5s",
                        "repeat_interval": "5m"
                    },
                    {
                        "match": {
                            "severity": "warning"
                        },
                        "receiver": "warning-alerts",
                        "group_wait": "30s",
                        "repeat_interval": "30m"
                    }
                ]
            },
            "receivers": [
                {
                    "name": "web.hook",
                    "webhook_configs": [
                        {
                            "url": "http://webhook:5000/alerts"
                        }
                    ]
                },
                {
                    "name": "critical-alerts",
                    "pagerduty_configs": [
                        {
                            "service_key": "${PAGERDUTY_SERVICE_KEY}",
                            "description": "Signal Service Critical Alert: {{ range .Alerts }}{{ .Annotations.summary }}{{ end }}",
                            "severity": "critical"
                        }
                    ],
                    "slack_configs": [
                        {
                            "api_url": "${SLACK_WEBHOOK_URL}",
                            "channel": "#signal-service-alerts",
                            "title": "🚨 CRITICAL: Signal Service Alert",
                            "text": "{{ range .Alerts }}{{ .Annotations.summary }}\\n{{ .Annotations.description }}{{ end }}",
                            "color": "danger"
                        }
                    ]
                },
                {
                    "name": "warning-alerts",
                    "slack_configs": [
                        {
                            "api_url": "${SLACK_WEBHOOK_URL}",
                            "channel": "#signal-service-monitoring",
                            "title": "⚠️ WARNING: Signal Service Alert",
                            "text": "{{ range .Alerts }}{{ .Annotations.summary }}\\n{{ .Annotations.description }}{{ end }}",
                            "color": "warning"
                        }
                    ],
                    "email_configs": [
                        {
                            "to": "${ON_CALL_EMAIL}",
                            "subject": "Signal Service Warning Alert",
                            "body": "{{ range .Alerts }}{{ .Annotations.summary }}\\n{{ .Annotations.description }}{{ end }}"
                        }
                    ]
                }
            ]
        }

        config_file = os.path.join(self.alerts_dir, "alertmanager.yml")
        with open(config_file, 'w') as f:
            json.dump(alertmanager_config, f, indent=2)

        print(f"    ✅ AlertManager config: {config_file}")
        print("    🔔 Critical alerts → PagerDuty + Slack")
        print("    ⚠️ Warning alerts → Slack + Email")

        return alertmanager_config

    def create_config_service_alerts(self) -> dict[str, Any]:
        """Create config service reachability alerts."""
        print("⚙️ Creating Config Service Alerts...")

        alerts = {
            "groups": [
                {
                    "name": "config-service",
                    "rules": [
                        {
                            "alert": "ConfigServiceDown",
                            "expr": "up{job=\"config-service\"} == 0",
                            "for": "1m",
                            "labels": {
                                "severity": "critical",
                                "service": "config-service",
                                "component": "infrastructure"
                            },
                            "annotations": {
                                "summary": "Config Service is down",
                                "description": "Config service has been down for more than 1 minute. Signal service cannot start or update configuration.",
                                "runbook_url": "https://docs.signal-service.com/runbooks/config-service-down"
                            }
                        },
                        {
                            "alert": "ConfigServiceHighLatency",
                            "expr": "histogram_quantile(0.95, rate(config_service_fetch_duration_seconds_bucket[5m])) > 0.5",
                            "for": "2m",
                            "labels": {
                                "severity": "warning",
                                "service": "config-service",
                                "component": "performance"
                            },
                            "annotations": {
                                "summary": "Config Service high latency detected",
                                "description": "Config service P95 latency is {{ $value }}s, above 500ms threshold for 2 minutes.",
                                "runbook_url": "https://docs.signal-service.com/runbooks/config-service-latency"
                            }
                        },
                        {
                            "alert": "ConfigServiceLowCacheHitRate",
                            "expr": "rate(config_service_cache_hits_total[5m]) / rate(config_service_cache_requests_total[5m]) * 100 < 80",
                            "for": "5m",
                            "labels": {
                                "severity": "warning",
                                "service": "config-service",
                                "component": "caching"
                            },
                            "annotations": {
                                "summary": "Config Service cache hit rate is low",
                                "description": "Config service cache hit rate is {{ $value }}%, below 80% threshold.",
                                "runbook_url": "https://docs.signal-service.com/runbooks/config-service-cache"
                            }
                        },
                        {
                            "alert": "ConfigServiceHighErrorRate",
                            "expr": "rate(config_service_requests_total{status=~\"4..|5..\"}[5m]) / rate(config_service_requests_total[5m]) * 100 > 5",
                            "for": "2m",
                            "labels": {
                                "severity": "critical",
                                "service": "config-service",
                                "component": "reliability"
                            },
                            "annotations": {
                                "summary": "Config Service high error rate",
                                "description": "Config service error rate is {{ $value }}%, above 5% threshold for 2 minutes.",
                                "runbook_url": "https://docs.signal-service.com/runbooks/config-service-errors"
                            }
                        },
                        {
                            "alert": "ServiceBootstrapFailure",
                            "expr": "increase(service_bootstrap_failures_total[5m]) > 0",
                            "for": "0m",
                            "labels": {
                                "severity": "critical",
                                "service": "signal-service",
                                "component": "bootstrap"
                            },
                            "annotations": {
                                "summary": "Signal Service bootstrap failure detected",
                                "description": "Signal service failed to bootstrap {{ $value }} times in the last 5 minutes. Check config service connectivity.",
                                "runbook_url": "https://docs.signal-service.com/runbooks/bootstrap-failure"
                            }
                        }
                    ]
                }
            ]
        }

        alerts_file = os.path.join(self.alerts_dir, "config_service_alerts.yml")
        with open(alerts_file, 'w') as f:
            json.dump(alerts, f, indent=2)

        print(f"    ✅ Config service alerts: {alerts_file}")
        print(f"    🚨 {len(alerts['groups'][0]['rules'])} alert rules created")

        return alerts

    def create_pool_exhaustion_alerts(self) -> dict[str, Any]:
        """Create database and Redis pool exhaustion alerts."""
        print("🔋 Creating Pool Exhaustion Alerts...")

        alerts = {
            "groups": [
                {
                    "name": "pool-exhaustion",
                    "rules": [
                        {
                            "alert": "DatabaseConnectionPoolExhaustion",
                            "expr": "db_connection_pool_active / db_connection_pool_max * 100 > 90",
                            "for": "1m",
                            "labels": {
                                "severity": "critical",
                                "service": "signal-service",
                                "component": "database"
                            },
                            "annotations": {
                                "summary": "Database connection pool near exhaustion",
                                "description": "Database connection pool usage is {{ $value }}%, above 90% threshold for 1 minute.",
                                "runbook_url": "https://docs.signal-service.com/runbooks/db-pool-exhaustion"
                            }
                        },
                        {
                            "alert": "RedisConnectionPoolExhaustion",
                            "expr": "redis_connection_pool_active / redis_connection_pool_max * 100 > 85",
                            "for": "1m",
                            "labels": {
                                "severity": "critical",
                                "service": "signal-service",
                                "component": "redis"
                            },
                            "annotations": {
                                "summary": "Redis connection pool near exhaustion",
                                "description": "Redis connection pool usage is {{ $value }}%, above 85% threshold for 1 minute.",
                                "runbook_url": "https://docs.signal-service.com/runbooks/redis-pool-exhaustion"
                            }
                        },
                        {
                            "alert": "DatabaseConnectionLeaks",
                            "expr": "db_connection_pool_leaks > 5",
                            "for": "2m",
                            "labels": {
                                "severity": "warning",
                                "service": "signal-service",
                                "component": "database"
                            },
                            "annotations": {
                                "summary": "Database connection leaks detected",
                                "description": "{{ $value }} database connection leaks detected. This may lead to pool exhaustion.",
                                "runbook_url": "https://docs.signal-service.com/runbooks/db-connection-leaks"
                            }
                        },
                        {
                            "alert": "DatabaseHighLatency",
                            "expr": "histogram_quantile(0.95, rate(db_query_duration_seconds_bucket[5m])) > 0.1",
                            "for": "3m",
                            "labels": {
                                "severity": "warning",
                                "service": "signal-service",
                                "component": "database"
                            },
                            "annotations": {
                                "summary": "Database query latency high",
                                "description": "Database P95 query latency is {{ $value }}s, above 100ms threshold for 3 minutes.",
                                "runbook_url": "https://docs.signal-service.com/runbooks/db-high-latency"
                            }
                        },
                        {
                            "alert": "RedisHighLatency",
                            "expr": "histogram_quantile(0.95, rate(redis_operation_duration_seconds_bucket[5m])) > 0.05",
                            "for": "3m",
                            "labels": {
                                "severity": "warning",
                                "service": "signal-service",
                                "component": "redis"
                            },
                            "annotations": {
                                "summary": "Redis operation latency high",
                                "description": "Redis P95 operation latency is {{ $value }}s, above 50ms threshold for 3 minutes.",
                                "runbook_url": "https://docs.signal-service.com/runbooks/redis-high-latency"
                            }
                        }
                    ]
                }
            ]
        }

        alerts_file = os.path.join(self.alerts_dir, "pool_exhaustion_alerts.yml")
        with open(alerts_file, 'w') as f:
            json.dump(alerts, f, indent=2)

        print(f"    ✅ Pool exhaustion alerts: {alerts_file}")
        print(f"    🚨 {len(alerts['groups'][0]['rules'])} alert rules created")

        return alerts

    def create_circuit_breaker_alerts(self) -> dict[str, Any]:
        """Create circuit breaker open count alerts."""
        print("🔌 Creating Circuit Breaker Alerts...")

        alerts = {
            "groups": [
                {
                    "name": "circuit-breakers",
                    "rules": [
                        {
                            "alert": "CircuitBreakerOpen",
                            "expr": "circuit_breaker_state == 2",
                            "for": "0m",
                            "labels": {
                                "severity": "critical",
                                "service": "signal-service",
                                "component": "circuit-breaker"
                            },
                            "annotations": {
                                "summary": "Circuit breaker is open for {{ $labels.service }}",
                                "description": "Circuit breaker for {{ $labels.service }} is open. External service calls are being blocked.",
                                "runbook_url": "https://docs.signal-service.com/runbooks/circuit-breaker-open"
                            }
                        },
                        {
                            "alert": "CircuitBreakerHighFailureRate",
                            "expr": "rate(circuit_breaker_failures_total[5m]) / rate(circuit_breaker_requests_total[5m]) * 100 > 20",
                            "for": "2m",
                            "labels": {
                                "severity": "warning",
                                "service": "signal-service",
                                "component": "circuit-breaker"
                            },
                            "annotations": {
                                "summary": "Circuit breaker high failure rate for {{ $labels.service }}",
                                "description": "Circuit breaker failure rate for {{ $labels.service }} is {{ $value }}%, above 20% threshold. May trigger circuit breaker open.",
                                "runbook_url": "https://docs.signal-service.com/runbooks/circuit-breaker-failures"
                            }
                        },
                        {
                            "alert": "CircuitBreakerLongHalfOpen",
                            "expr": "circuit_breaker_half_open_duration_seconds > 60",
                            "for": "1m",
                            "labels": {
                                "severity": "warning",
                                "service": "signal-service",
                                "component": "circuit-breaker"
                            },
                            "annotations": {
                                "summary": "Circuit breaker stuck in half-open state for {{ $labels.service }}",
                                "description": "Circuit breaker for {{ $labels.service }} has been in half-open state for {{ $value }}s, longer than 60s threshold.",
                                "runbook_url": "https://docs.signal-service.com/runbooks/circuit-breaker-half-open"
                            }
                        },
                        {
                            "alert": "CircuitBreakerRecoveryFailures",
                            "expr": "increase(circuit_breaker_recovery_failures_total[10m]) > 3",
                            "for": "0m",
                            "labels": {
                                "severity": "warning",
                                "service": "signal-service",
                                "component": "circuit-breaker"
                            },
                            "annotations": {
                                "summary": "Circuit breaker recovery failures for {{ $labels.service }}",
                                "description": "Circuit breaker for {{ $labels.service }} has failed recovery {{ $value }} times in 10 minutes. May need manual intervention.",
                                "runbook_url": "https://docs.signal-service.com/runbooks/circuit-breaker-recovery"
                            }
                        }
                    ]
                }
            ]
        }

        alerts_file = os.path.join(self.alerts_dir, "circuit_breaker_alerts.yml")
        with open(alerts_file, 'w') as f:
            json.dump(alerts, f, indent=2)

        print(f"    ✅ Circuit breaker alerts: {alerts_file}")
        print(f"    🚨 {len(alerts['groups'][0]['rules'])} alert rules created")

        return alerts

    def create_backpressure_alerts(self) -> dict[str, Any]:
        """Create backpressure activation alerts."""
        print("⏸️ Creating Backpressure Alerts...")

        alerts = {
            "groups": [
                {
                    "name": "backpressure",
                    "rules": [
                        {
                            "alert": "BudgetGuardActivation",
                            "expr": "rate(budget_guard_rejections_total[5m]) * 60 > 5",
                            "for": "1m",
                            "labels": {
                                "severity": "warning",
                                "service": "signal-service",
                                "component": "backpressure"
                            },
                            "annotations": {
                                "summary": "Budget guard rejecting requests",
                                "description": "Budget guard is rejecting {{ $value }} requests per minute, above 5/min threshold. System is under pressure.",
                                "runbook_url": "https://docs.signal-service.com/runbooks/budget-guard-activation"
                            }
                        },
                        {
                            "alert": "HighMemoryPressure",
                            "expr": "process_memory_usage_percent > 85",
                            "for": "2m",
                            "labels": {
                                "severity": "critical",
                                "service": "signal-service",
                                "component": "memory"
                            },
                            "annotations": {
                                "summary": "High memory pressure detected",
                                "description": "Memory usage is {{ $value }}%, above 85% threshold for 2 minutes. May trigger backpressure.",
                                "runbook_url": "https://docs.signal-service.com/runbooks/high-memory-pressure"
                            }
                        },
                        {
                            "alert": "HighCPUPressure",
                            "expr": "process_cpu_usage_percent > 90",
                            "for": "2m",
                            "labels": {
                                "severity": "critical",
                                "service": "signal-service",
                                "component": "cpu"
                            },
                            "annotations": {
                                "summary": "High CPU pressure detected",
                                "description": "CPU usage is {{ $value }}%, above 90% threshold for 2 minutes. May trigger backpressure.",
                                "runbook_url": "https://docs.signal-service.com/runbooks/high-cpu-pressure"
                            }
                        },
                        {
                            "alert": "RequestQueueBacklog",
                            "expr": "request_queue_depth > 100",
                            "for": "30s",
                            "labels": {
                                "severity": "warning",
                                "service": "signal-service",
                                "component": "queue"
                            },
                            "annotations": {
                                "summary": "Request queue backlog detected",
                                "description": "Request queue depth is {{ $value }}, above 100 threshold. Processing may be lagging.",
                                "runbook_url": "https://docs.signal-service.com/runbooks/request-queue-backlog"
                            }
                        },
                        {
                            "alert": "BackpressureCascadeEvent",
                            "expr": "increase(backpressure_cascade_events_total[5m]) > 0",
                            "for": "0m",
                            "labels": {
                                "severity": "critical",
                                "service": "signal-service",
                                "component": "backpressure"
                            },
                            "annotations": {
                                "summary": "Backpressure cascade event detected",
                                "description": "Backpressure cascade event occurred {{ $value }} times in 5 minutes. System-wide pressure detected.",
                                "runbook_url": "https://docs.signal-service.com/runbooks/backpressure-cascade"
                            }
                        },
                        {
                            "alert": "GracefulDegradationActive",
                            "expr": "graceful_degradation_mode_active == 1",
                            "for": "0m",
                            "labels": {
                                "severity": "warning",
                                "service": "signal-service",
                                "component": "degradation"
                            },
                            "annotations": {
                                "summary": "Service operating in graceful degradation mode",
                                "description": "Signal service is operating in graceful degradation mode due to high load or resource pressure.",
                                "runbook_url": "https://docs.signal-service.com/runbooks/graceful-degradation"
                            }
                        }
                    ]
                }
            ]
        }

        alerts_file = os.path.join(self.alerts_dir, "backpressure_alerts.yml")
        with open(alerts_file, 'w') as f:
            json.dump(alerts, f, indent=2)

        print(f"    ✅ Backpressure alerts: {alerts_file}")
        print(f"    🚨 {len(alerts['groups'][0]['rules'])} alert rules created")

        return alerts

    def create_slo_breach_alerts(self) -> dict[str, Any]:
        """Create 5xx/latency SLO breach alerts."""
        print("📊 Creating SLO Breach Alerts...")

        alerts = {
            "groups": [
                {
                    "name": "slo-breaches",
                    "rules": [
                        {
                            "alert": "LatencySLOBreach",
                            "expr": "histogram_quantile(0.95, rate(http_request_duration_seconds_bucket[5m])) > 0.2",
                            "for": "2m",
                            "labels": {
                                "severity": "critical",
                                "service": "signal-service",
                                "component": "latency"
                            },
                            "annotations": {
                                "summary": "Latency SLO breach detected",
                                "description": "P95 request latency is {{ $value }}s, above 200ms SLO threshold for 2 minutes.",
                                "runbook_url": "https://docs.signal-service.com/runbooks/latency-slo-breach"
                            }
                        },
                        {
                            "alert": "ErrorRateSLOBreach",
                            "expr": "rate(http_requests_total{status=~\"4..|5..\"}[5m]) / rate(http_requests_total[5m]) * 100 > 0.1",
                            "for": "2m",
                            "labels": {
                                "severity": "critical",
                                "service": "signal-service",
                                "component": "errors"
                            },
                            "annotations": {
                                "summary": "Error rate SLO breach detected",
                                "description": "Error rate is {{ $value }}%, above 0.1% SLO threshold for 2 minutes.",
                                "runbook_url": "https://docs.signal-service.com/runbooks/error-rate-slo-breach"
                            }
                        },
                        {
                            "alert": "High5xxErrorRate",
                            "expr": "rate(http_requests_total{status=~\"5..\"}[5m]) / rate(http_requests_total[5m]) * 100 > 1",
                            "for": "1m",
                            "labels": {
                                "severity": "critical",
                                "service": "signal-service",
                                "component": "server-errors"
                            },
                            "annotations": {
                                "summary": "High 5xx error rate detected",
                                "description": "5xx error rate is {{ $value }}%, above 1% threshold for 1 minute.",
                                "runbook_url": "https://docs.signal-service.com/runbooks/high-5xx-errors"
                            }
                        },
                        {
                            "alert": "P99LatencyDegraded",
                            "expr": "histogram_quantile(0.99, rate(http_request_duration_seconds_bucket[5m])) > 0.5",
                            "for": "5m",
                            "labels": {
                                "severity": "warning",
                                "service": "signal-service",
                                "component": "latency"
                            },
                            "annotations": {
                                "summary": "P99 latency degraded",
                                "description": "P99 request latency is {{ $value }}s, above 500ms threshold for 5 minutes.",
                                "runbook_url": "https://docs.signal-service.com/runbooks/p99-latency-degraded"
                            }
                        },
                        {
                            "alert": "LowThroughput",
                            "expr": "rate(http_requests_total[5m]) < 10",
                            "for": "5m",
                            "labels": {
                                "severity": "warning",
                                "service": "signal-service",
                                "component": "throughput"
                            },
                            "annotations": {
                                "summary": "Low throughput detected",
                                "description": "Request throughput is {{ $value }} RPS, below 10 RPS threshold for 5 minutes.",
                                "runbook_url": "https://docs.signal-service.com/runbooks/low-throughput"
                            }
                        }
                    ]
                }
            ]
        }

        alerts_file = os.path.join(self.alerts_dir, "slo_breach_alerts.yml")
        with open(alerts_file, 'w') as f:
            json.dump(alerts, f, indent=2)

        print(f"    ✅ SLO breach alerts: {alerts_file}")
        print(f"    🚨 {len(alerts['groups'][0]['rules'])} alert rules created")

        return alerts

    def create_prometheus_alerts_config(self) -> str:
        """Create Prometheus alerts configuration file."""
        print("📊 Creating Prometheus Alerts Configuration...")

        prometheus_config = '''# Prometheus Alert Rules Configuration
global:
  scrape_interval: 15s
  evaluation_interval: 15s

rule_files:
  - "alerting/config_service_alerts.yml"
  - "alerting/pool_exhaustion_alerts.yml"
  - "alerting/circuit_breaker_alerts.yml"
  - "alerting/backpressure_alerts.yml"
  - "alerting/slo_breach_alerts.yml"

alerting:
  alertmanagers:
    - static_configs:
        - targets:
          - alertmanager:9093

scrape_configs:
  - job_name: 'signal-service'
    static_configs:
      - targets: ['signal-service:8080']
    metrics_path: '/api/v1/metrics'
    scrape_interval: 15s

  - job_name: 'config-service'
    static_configs:
      - targets: ['config-service:8100']
    metrics_path: '/metrics'
    scrape_interval: 30s
'''

        config_file = os.path.join(self.alerts_dir, "prometheus.yml")
        with open(config_file, 'w') as f:
            f.write(prometheus_config)

        print(f"    ✅ Prometheus config: {config_file}")

        return config_file

    def create_deployment_script(self) -> str:
        """Create script to deploy alerts to production."""
        print("🚀 Creating Alerts Deployment Script...")

        deployment_script = '''#!/bin/bash
"""
Production Alerts Deployment Script

Deploys all alert rules and configuration to production monitoring stack.
"""

PROMETHEUS_CONFIG_PATH="${PROMETHEUS_CONFIG_PATH:-/etc/prometheus}"
ALERTMANAGER_CONFIG_PATH="${ALERTMANAGER_CONFIG_PATH:-/etc/alertmanager}"
ALERTS_DIR="alerting"

echo "🚨 Deploying Signal Service Alerts to Production..."

# Validate alert rule files
echo "✅ Validating alert rules..."
promtool check rules $ALERTS_DIR/*.yml
if [ $? -ne 0 ]; then
    echo "❌ Alert rules validation failed!"
    exit 1
fi

# Validate AlertManager config
echo "✅ Validating AlertManager configuration..."
amtool check-config $ALERTS_DIR/alertmanager.yml
if [ $? -ne 0 ]; then
    echo "❌ AlertManager config validation failed!"
    exit 1
fi

# Deploy alert rules
echo "📋 Deploying alert rules..."
cp $ALERTS_DIR/*.yml $PROMETHEUS_CONFIG_PATH/rules/
cp $ALERTS_DIR/prometheus.yml $PROMETHEUS_CONFIG_PATH/

# Deploy AlertManager config
echo "🔔 Deploying AlertManager configuration..."
cp $ALERTS_DIR/alertmanager.yml $ALERTMANAGER_CONFIG_PATH/

# Reload Prometheus
echo "🔄 Reloading Prometheus configuration..."
curl -X POST http://prometheus:9090/-/reload

# Reload AlertManager
echo "🔄 Reloading AlertManager configuration..."
curl -X POST http://alertmanager:9093/-/reload

echo "✅ All alerts deployed successfully!"
echo "🌐 View alerts at: http://prometheus:9090/alerts"
echo "🔔 View AlertManager at: http://alertmanager:9093"

# Test alert rules
echo "🧪 Testing alert rules..."
curl -s http://prometheus:9090/api/v1/rules | jq '.data.groups[].rules[] | select(.type=="alerting") | {name: .name, state: .state}'

echo "🎉 Production alerts deployment complete!"
'''

        script_path = os.path.join(self.alerts_dir, "deploy_alerts.sh")
        with open(script_path, 'w') as f:
            f.write(deployment_script)

        os.chmod(script_path, 0o755)

        print(f"    🚀 Deployment script: {script_path}")

        return script_path

    def run_on_call_alerts_setup(self) -> dict[str, Any]:
        """Execute complete on-call alerts setup."""
        print("🚨 On-Call Alerts Setup")
        print("=" * 60)

        # Create AlertManager configuration
        self.create_alertmanager_config()
        print()

        # Create all alert rule groups
        self.alert_rules["config_service"] = self.create_config_service_alerts()
        print()

        self.alert_rules["pool_exhaustion"] = self.create_pool_exhaustion_alerts()
        print()

        self.alert_rules["circuit_breaker"] = self.create_circuit_breaker_alerts()
        print()

        self.alert_rules["backpressure"] = self.create_backpressure_alerts()
        print()

        self.alert_rules["slo_breach"] = self.create_slo_breach_alerts()
        print()

        # Create Prometheus configuration
        prometheus_config = self.create_prometheus_alerts_config()
        print()

        # Create deployment script
        deployment_script = self.create_deployment_script()
        print()

        # Create setup summary
        total_alerts = sum(len(group['groups'][0]['rules']) for group in self.alert_rules.values())

        summary = {
            "setup_timestamp": datetime.now().isoformat(),
            "alert_groups": len(self.alert_rules),
            "total_alert_rules": total_alerts,
            "alerting_directory": self.alerts_dir,
            "prometheus_config": prometheus_config,
            "alertmanager_config": "alerting/alertmanager.yml",
            "deployment_script": deployment_script,
            "notification_channels": {
                "pagerduty": "Critical alerts",
                "slack_critical": "#signal-service-alerts",
                "slack_warning": "#signal-service-monitoring",
                "email": "Warning alerts to on-call"
            },
            "alert_coverage": {
                "config_service": "Reachability, latency, cache, errors, bootstrap",
                "pool_exhaustion": "DB/Redis connection pools, leaks, latency",
                "circuit_breaker": "Open states, failure rates, recovery",
                "backpressure": "Budget guard, memory/CPU pressure, queue depth",
                "slo_breach": "Latency SLO, error rate SLO, 5xx errors"
            }
        }

        summary_file = os.path.join(self.alerts_dir, f"on_call_alerts_summary_{self.timestamp}.json")
        with open(summary_file, 'w') as f:
            json.dump(summary, f, indent=2)

        print("=" * 60)
        print("🎯 On-Call Alerts Setup Complete")
        print(f"🚨 Alert groups: {len(self.alert_rules)}")
        print(f"📋 Total rules: {total_alerts}")
        print(f"📁 Directory: {self.alerts_dir}")
        print(f"🚀 Deploy: {deployment_script}")
        print(f"📄 Summary: {summary_file}")

        return summary


def main():
    """Execute on-call alerts setup."""
    try:
        setup = OnCallAlertsSetup()
        results = setup.run_on_call_alerts_setup()

        print("\\n🎉 ON-CALL ALERTS SETUP COMPLETE")
        print(f"🚨 {results['total_alert_rules']} alert rules created")
        print(f"📁 All files in: {results['alerting_directory']}")
        print("\\n🚀 Next steps:")
        print("   1. set environment variables:")
        print("      - PAGERDUTY_SERVICE_KEY")
        print("      - SLACK_WEBHOOK_URL")
        print("      - ON_CALL_EMAIL")
        print(f"   2. Run: ./{results['deployment_script']}")
        print("   3. Verify alerts at: http://prometheus:9090/alerts")

        return 0

    except Exception as e:
        print(f"💥 On-call alerts setup failed: {e}")
        return 1


if __name__ == "__main__":
    exit_code = main()
    exit(exit_code)
