#!/usr/bin/env python3
"""
Day-0/1 Monitoring Dashboards Setup

Sets up comprehensive monitoring dashboards for config service, DB/Redis pools, 
circuit breakers, backpressure events, error rate/latency SLOs, and metrics scrape health.
"""
import json
import os
from datetime import datetime
from typing import Dict, Any, List


class Day01MonitoringSetup:
    """Day-0/1 monitoring dashboards and alerting setup."""
    
    def __init__(self):
        self.timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        self.monitoring_dir = "monitoring"
        os.makedirs(self.monitoring_dir, exist_ok=True)
        
        self.dashboards = {}
        self.alert_rules = {}
    
    def create_config_service_dashboard(self) -> Dict[str, Any]:
        """Create config service monitoring dashboard."""
        print("⚙️ Creating Config Service Dashboard...")
        
        dashboard = {
            "dashboard": {
                "id": None,
                "title": "Signal Service - Config Service Health",
                "tags": ["signal-service", "config-service", "production"],
                "timezone": "UTC",
                "refresh": "30s",
                "time": {
                    "from": "now-1h",
                    "to": "now"
                },
                "panels": [
                    {
                        "id": 1,
                        "title": "Config Service Health Status",
                        "type": "stat",
                        "targets": [
                            {
                                "expr": "up{job=\"config-service\"}",
                                "legendFormat": "Config Service Up",
                                "refId": "A"
                            }
                        ],
                        "fieldConfig": {
                            "defaults": {
                                "color": {
                                    "mode": "thresholds"
                                },
                                "thresholds": {
                                    "steps": [
                                        {"color": "red", "value": 0},
                                        {"color": "green", "value": 1}
                                    ]
                                },
                                "unit": "short"
                            }
                        },
                        "gridPos": {"h": 6, "w": 6, "x": 0, "y": 0}
                    },
                    {
                        "id": 2,
                        "title": "Config Fetch Latency (P95)",
                        "type": "graph",
                        "targets": [
                            {
                                "expr": "histogram_quantile(0.95, rate(config_service_fetch_duration_seconds_bucket[5m]))",
                                "legendFormat": "P95 Latency",
                                "refId": "A"
                            },
                            {
                                "expr": "histogram_quantile(0.50, rate(config_service_fetch_duration_seconds_bucket[5m]))",
                                "legendFormat": "P50 Latency", 
                                "refId": "B"
                            }
                        ],
                        "yAxes": [
                            {
                                "label": "Latency (seconds)",
                                "min": 0
                            }
                        ],
                        "alert": {
                            "conditions": [
                                {
                                    "query": {"queryType": "", "refId": "A"},
                                    "reducer": {"type": "last", "params": []},
                                    "evaluator": {"params": [0.5], "type": "gt"}
                                }
                            ],
                            "executionErrorState": "alerting",
                            "frequency": "30s",
                            "handler": 1,
                            "name": "Config Service High Latency",
                            "noDataState": "no_data"
                        },
                        "gridPos": {"h": 6, "w": 12, "x": 6, "y": 0}
                    },
                    {
                        "id": 3,
                        "title": "Config Cache Hit Rate",
                        "type": "graph",
                        "targets": [
                            {
                                "expr": "rate(config_service_cache_hits_total[5m]) / rate(config_service_cache_requests_total[5m]) * 100",
                                "legendFormat": "Cache Hit Rate %",
                                "refId": "A"
                            }
                        ],
                        "yAxes": [
                            {
                                "label": "Percentage",
                                "min": 0,
                                "max": 100
                            }
                        ],
                        "thresholds": [
                            {
                                "value": 80,
                                "colorMode": "critical",
                                "op": "lt"
                            }
                        ],
                        "gridPos": {"h": 6, "w": 6, "x": 18, "y": 0}
                    },
                    {
                        "id": 4,
                        "title": "Config Service Error Rate",
                        "type": "graph",
                        "targets": [
                            {
                                "expr": "rate(config_service_requests_total{status=~\"4..|5..\"}[5m]) / rate(config_service_requests_total[5m]) * 100",
                                "legendFormat": "Error Rate %",
                                "refId": "A"
                            }
                        ],
                        "yAxes": [
                            {
                                "label": "Error Rate %",
                                "min": 0
                            }
                        ],
                        "thresholds": [
                            {
                                "value": 5,
                                "colorMode": "critical",
                                "op": "gt"
                            }
                        ],
                        "gridPos": {"h": 6, "w": 12, "x": 0, "y": 6}
                    },
                    {
                        "id": 5,
                        "title": "Bootstrap Failures",
                        "type": "stat",
                        "targets": [
                            {
                                "expr": "increase(service_bootstrap_failures_total[1h])",
                                "legendFormat": "Bootstrap Failures (1h)",
                                "refId": "A"
                            }
                        ],
                        "fieldConfig": {
                            "defaults": {
                                "color": {
                                    "mode": "thresholds"
                                },
                                "thresholds": {
                                    "steps": [
                                        {"color": "green", "value": 0},
                                        {"color": "red", "value": 1}
                                    ]
                                }
                            }
                        },
                        "gridPos": {"h": 6, "w": 12, "x": 12, "y": 6}
                    }
                ]
            }
        }
        
        dashboard_file = os.path.join(self.monitoring_dir, "config_service_dashboard.json")
        with open(dashboard_file, 'w') as f:
            json.dump(dashboard, f, indent=2)
        
        print(f"    ✅ Dashboard created: {dashboard_file}")
        print(f"    📊 Panels: {len(dashboard['dashboard']['panels'])}")
        
        return dashboard
    
    def create_database_pools_dashboard(self) -> Dict[str, Any]:
        """Create database and Redis pools monitoring dashboard."""
        print("🗄️ Creating Database & Redis Pools Dashboard...")
        
        dashboard = {
            "dashboard": {
                "id": None,
                "title": "Signal Service - Database & Redis Pools",
                "tags": ["signal-service", "database", "redis", "pools"],
                "timezone": "UTC",
                "refresh": "30s",
                "time": {
                    "from": "now-1h",
                    "to": "now"
                },
                "panels": [
                    {
                        "id": 1,
                        "title": "Database Connection Pool Usage",
                        "type": "graph",
                        "targets": [
                            {
                                "expr": "db_connection_pool_active / db_connection_pool_max * 100",
                                "legendFormat": "Pool Usage %",
                                "refId": "A"
                            },
                            {
                                "expr": "db_connection_pool_idle",
                                "legendFormat": "Idle Connections",
                                "refId": "B"
                            }
                        ],
                        "yAxes": [
                            {
                                "label": "Percentage / Count",
                                "min": 0
                            }
                        ],
                        "thresholds": [
                            {
                                "value": 90,
                                "colorMode": "critical",
                                "op": "gt"
                            }
                        ],
                        "gridPos": {"h": 6, "w": 12, "x": 0, "y": 0}
                    },
                    {
                        "id": 2,
                        "title": "Database Query Latency",
                        "type": "graph",
                        "targets": [
                            {
                                "expr": "histogram_quantile(0.95, rate(db_query_duration_seconds_bucket[5m]))",
                                "legendFormat": "P95 Query Latency",
                                "refId": "A"
                            },
                            {
                                "expr": "histogram_quantile(0.50, rate(db_query_duration_seconds_bucket[5m]))",
                                "legendFormat": "P50 Query Latency",
                                "refId": "B"
                            }
                        ],
                        "yAxes": [
                            {
                                "label": "Latency (seconds)",
                                "min": 0
                            }
                        ],
                        "thresholds": [
                            {
                                "value": 0.1,
                                "colorMode": "critical",
                                "op": "gt"
                            }
                        ],
                        "gridPos": {"h": 6, "w": 12, "x": 12, "y": 0}
                    },
                    {
                        "id": 3,
                        "title": "Redis Connection Pool Status",
                        "type": "graph",
                        "targets": [
                            {
                                "expr": "redis_connection_pool_active / redis_connection_pool_max * 100",
                                "legendFormat": "Redis Pool Usage %",
                                "refId": "A"
                            },
                            {
                                "expr": "redis_connection_pool_idle",
                                "legendFormat": "Redis Idle Connections",
                                "refId": "B"
                            }
                        ],
                        "yAxes": [
                            {
                                "label": "Percentage / Count",
                                "min": 0
                            }
                        ],
                        "thresholds": [
                            {
                                "value": 85,
                                "colorMode": "critical",
                                "op": "gt"
                            }
                        ],
                        "gridPos": {"h": 6, "w": 12, "x": 0, "y": 6}
                    },
                    {
                        "id": 4,
                        "title": "Redis Cache Performance",
                        "type": "graph",
                        "targets": [
                            {
                                "expr": "rate(redis_cache_hits_total[5m]) / rate(redis_cache_requests_total[5m]) * 100",
                                "legendFormat": "Cache Hit Rate %",
                                "refId": "A"
                            },
                            {
                                "expr": "histogram_quantile(0.95, rate(redis_operation_duration_seconds_bucket[5m])) * 1000",
                                "legendFormat": "P95 Operation Latency (ms)",
                                "refId": "B"
                            }
                        ],
                        "yAxes": [
                            {
                                "label": "Percentage / Milliseconds",
                                "min": 0
                            }
                        ],
                        "gridPos": {"h": 6, "w": 12, "x": 12, "y": 6}
                    },
                    {
                        "id": 5,
                        "title": "TimescaleDB Hypertable Health",
                        "type": "stat",
                        "targets": [
                            {
                                "expr": "timescale_hypertable_health_score",
                                "legendFormat": "Hypertable Health %",
                                "refId": "A"
                            }
                        ],
                        "fieldConfig": {
                            "defaults": {
                                "color": {
                                    "mode": "thresholds"
                                },
                                "thresholds": {
                                    "steps": [
                                        {"color": "red", "value": 0},
                                        {"color": "yellow", "value": 80},
                                        {"color": "green", "value": 90}
                                    ]
                                },
                                "unit": "percent"
                            }
                        },
                        "gridPos": {"h": 6, "w": 8, "x": 0, "y": 12}
                    },
                    {
                        "id": 6,
                        "title": "Connection Pool Leaks",
                        "type": "stat",
                        "targets": [
                            {
                                "expr": "db_connection_pool_leaks",
                                "legendFormat": "Connection Leaks",
                                "refId": "A"
                            }
                        ],
                        "fieldConfig": {
                            "defaults": {
                                "color": {
                                    "mode": "thresholds"
                                },
                                "thresholds": {
                                    "steps": [
                                        {"color": "green", "value": 0},
                                        {"color": "yellow", "value": 3},
                                        {"color": "red", "value": 5}
                                    ]
                                }
                            }
                        },
                        "gridPos": {"h": 6, "w": 8, "x": 8, "y": 12}
                    },
                    {
                        "id": 7,
                        "title": "Transaction Deadlocks",
                        "type": "stat",
                        "targets": [
                            {
                                "expr": "rate(db_transaction_deadlocks_total[5m]) * 60",
                                "legendFormat": "Deadlocks/min",
                                "refId": "A"
                            }
                        ],
                        "fieldConfig": {
                            "defaults": {
                                "color": {
                                    "mode": "thresholds"
                                },
                                "thresholds": {
                                    "steps": [
                                        {"color": "green", "value": 0},
                                        {"color": "yellow", "value": 1},
                                        {"color": "red", "value": 2}
                                    ]
                                }
                            }
                        },
                        "gridPos": {"h": 6, "w": 8, "x": 16, "y": 12}
                    }
                ]
            }
        }
        
        dashboard_file = os.path.join(self.monitoring_dir, "database_redis_pools_dashboard.json")
        with open(dashboard_file, 'w') as f:
            json.dump(dashboard, f, indent=2)
        
        print(f"    ✅ Dashboard created: {dashboard_file}")
        print(f"    📊 Panels: {len(dashboard['dashboard']['panels'])}")
        
        return dashboard
    
    def create_circuit_breaker_dashboard(self) -> Dict[str, Any]:
        """Create circuit breaker monitoring dashboard."""
        print("🔌 Creating Circuit Breaker Dashboard...")
        
        dashboard = {
            "dashboard": {
                "id": None,
                "title": "Signal Service - Circuit Breaker Status",
                "tags": ["signal-service", "circuit-breaker", "resilience"],
                "timezone": "UTC",
                "refresh": "30s",
                "time": {
                    "from": "now-1h",
                    "to": "now"
                },
                "panels": [
                    {
                        "id": 1,
                        "title": "Circuit Breaker States",
                        "type": "stat",
                        "targets": [
                            {
                                "expr": "circuit_breaker_state{service=\"ticker_service\"}",
                                "legendFormat": "Ticker Service",
                                "refId": "A"
                            },
                            {
                                "expr": "circuit_breaker_state{service=\"user_service\"}",
                                "legendFormat": "User Service",
                                "refId": "B"
                            },
                            {
                                "expr": "circuit_breaker_state{service=\"metrics_service\"}",
                                "legendFormat": "Metrics Service",
                                "refId": "C"
                            }
                        ],
                        "fieldConfig": {
                            "defaults": {
                                "color": {
                                    "mode": "thresholds"
                                },
                                "mappings": [
                                    {
                                        "type": "value",
                                        "value": "0",
                                        "text": "CLOSED"
                                    },
                                    {
                                        "type": "value", 
                                        "value": "1",
                                        "text": "HALF-OPEN"
                                    },
                                    {
                                        "type": "value",
                                        "value": "2", 
                                        "text": "OPEN"
                                    }
                                ],
                                "thresholds": {
                                    "steps": [
                                        {"color": "green", "value": 0},
                                        {"color": "yellow", "value": 1},
                                        {"color": "red", "value": 2}
                                    ]
                                }
                            }
                        },
                        "gridPos": {"h": 6, "w": 12, "x": 0, "y": 0}
                    },
                    {
                        "id": 2,
                        "title": "Circuit Breaker Failure Rates",
                        "type": "graph",
                        "targets": [
                            {
                                "expr": "rate(circuit_breaker_failures_total[5m]) / rate(circuit_breaker_requests_total[5m]) * 100",
                                "legendFormat": "{{service}} Failure Rate %",
                                "refId": "A"
                            }
                        ],
                        "yAxes": [
                            {
                                "label": "Failure Rate %",
                                "min": 0,
                                "max": 100
                            }
                        ],
                        "thresholds": [
                            {
                                "value": 20,
                                "colorMode": "critical",
                                "op": "gt"
                            }
                        ],
                        "gridPos": {"h": 6, "w": 12, "x": 12, "y": 0}
                    },
                    {
                        "id": 3,
                        "title": "Circuit Breaker State Changes",
                        "type": "graph",
                        "targets": [
                            {
                                "expr": "increase(circuit_breaker_state_changes_total[5m])",
                                "legendFormat": "{{service}} State Changes",
                                "refId": "A"
                            }
                        ],
                        "yAxes": [
                            {
                                "label": "State Changes (5m)",
                                "min": 0
                            }
                        ],
                        "gridPos": {"h": 6, "w": 12, "x": 0, "y": 6}
                    },
                    {
                        "id": 4,
                        "title": "Half-Open Duration",
                        "type": "graph",
                        "targets": [
                            {
                                "expr": "circuit_breaker_half_open_duration_seconds",
                                "legendFormat": "{{service}} Half-Open Duration",
                                "refId": "A"
                            }
                        ],
                        "yAxes": [
                            {
                                "label": "Duration (seconds)",
                                "min": 0
                            }
                        ],
                        "thresholds": [
                            {
                                "value": 60,
                                "colorMode": "critical",
                                "op": "gt"
                            }
                        ],
                        "gridPos": {"h": 6, "w": 12, "x": 12, "y": 6}
                    },
                    {
                        "id": 5,
                        "title": "Recovery Success Rate",
                        "type": "stat",
                        "targets": [
                            {
                                "expr": "rate(circuit_breaker_recovery_successes_total[5m]) / rate(circuit_breaker_recovery_attempts_total[5m]) * 100",
                                "legendFormat": "Recovery Success %",
                                "refId": "A"
                            }
                        ],
                        "fieldConfig": {
                            "defaults": {
                                "color": {
                                    "mode": "thresholds"
                                },
                                "thresholds": {
                                    "steps": [
                                        {"color": "red", "value": 0},
                                        {"color": "yellow", "value": 70},
                                        {"color": "green", "value": 90}
                                    ]
                                },
                                "unit": "percent"
                            }
                        },
                        "gridPos": {"h": 6, "w": 24, "x": 0, "y": 12}
                    }
                ]
            }
        }
        
        dashboard_file = os.path.join(self.monitoring_dir, "circuit_breaker_dashboard.json")
        with open(dashboard_file, 'w') as f:
            json.dump(dashboard, f, indent=2)
        
        print(f"    ✅ Dashboard created: {dashboard_file}")
        print(f"    📊 Panels: {len(dashboard['dashboard']['panels'])}")
        
        return dashboard
    
    def create_slo_performance_dashboard(self) -> Dict[str, Any]:
        """Create SLO and performance monitoring dashboard."""
        print("⚡ Creating SLO & Performance Dashboard...")
        
        dashboard = {
            "dashboard": {
                "id": None,
                "title": "Signal Service - SLOs & Performance",
                "tags": ["signal-service", "slo", "performance", "latency"],
                "timezone": "UTC",
                "refresh": "30s",
                "time": {
                    "from": "now-1h",
                    "to": "now"
                },
                "panels": [
                    {
                        "id": 1,
                        "title": "Request Latency SLOs",
                        "type": "graph",
                        "targets": [
                            {
                                "expr": "histogram_quantile(0.95, rate(http_request_duration_seconds_bucket[5m]))",
                                "legendFormat": "P95 Latency",
                                "refId": "A"
                            },
                            {
                                "expr": "histogram_quantile(0.99, rate(http_request_duration_seconds_bucket[5m]))",
                                "legendFormat": "P99 Latency",
                                "refId": "B"
                            }
                        ],
                        "yAxes": [
                            {
                                "label": "Latency (seconds)",
                                "min": 0
                            }
                        ],
                        "thresholds": [
                            {
                                "value": 0.2,
                                "colorMode": "critical",
                                "op": "gt",
                                "yAxis": "left"
                            }
                        ],
                        "gridPos": {"h": 6, "w": 12, "x": 0, "y": 0}
                    },
                    {
                        "id": 2,
                        "title": "Error Rate SLO",
                        "type": "graph", 
                        "targets": [
                            {
                                "expr": "rate(http_requests_total{status=~\"4..|5..\"}[5m]) / rate(http_requests_total[5m]) * 100",
                                "legendFormat": "Error Rate %",
                                "refId": "A"
                            }
                        ],
                        "yAxes": [
                            {
                                "label": "Error Rate %",
                                "min": 0,
                                "max": 5
                            }
                        ],
                        "thresholds": [
                            {
                                "value": 0.1,
                                "colorMode": "critical",
                                "op": "gt"
                            }
                        ],
                        "gridPos": {"h": 6, "w": 12, "x": 12, "y": 0}
                    },
                    {
                        "id": 3,
                        "title": "Throughput (RPS)",
                        "type": "graph",
                        "targets": [
                            {
                                "expr": "rate(http_requests_total[5m])",
                                "legendFormat": "Requests/sec",
                                "refId": "A"
                            }
                        ],
                        "yAxes": [
                            {
                                "label": "Requests per second",
                                "min": 0
                            }
                        ],
                        "gridPos": {"h": 6, "w": 8, "x": 0, "y": 6}
                    },
                    {
                        "id": 4,
                        "title": "Backpressure Events",
                        "type": "graph",
                        "targets": [
                            {
                                "expr": "rate(budget_guard_rejections_total[5m]) * 60",
                                "legendFormat": "Budget Guard Rejections/min",
                                "refId": "A"
                            },
                            {
                                "expr": "rate(backpressure_events_total[5m]) * 60",
                                "legendFormat": "Backpressure Events/min",
                                "refId": "B"
                            }
                        ],
                        "yAxes": [
                            {
                                "label": "Events per minute",
                                "min": 0
                            }
                        ],
                        "thresholds": [
                            {
                                "value": 5,
                                "colorMode": "critical",
                                "op": "gt"
                            }
                        ],
                        "gridPos": {"h": 6, "w": 8, "x": 8, "y": 6}
                    },
                    {
                        "id": 5,
                        "title": "Resource Usage",
                        "type": "graph",
                        "targets": [
                            {
                                "expr": "process_memory_usage_percent",
                                "legendFormat": "Memory Usage %",
                                "refId": "A"
                            },
                            {
                                "expr": "process_cpu_usage_percent",
                                "legendFormat": "CPU Usage %",
                                "refId": "B"
                            }
                        ],
                        "yAxes": [
                            {
                                "label": "Usage %",
                                "min": 0,
                                "max": 100
                            }
                        ],
                        "thresholds": [
                            {
                                "value": 85,
                                "colorMode": "critical",
                                "op": "gt"
                            }
                        ],
                        "gridPos": {"h": 6, "w": 8, "x": 16, "y": 6}
                    },
                    {
                        "id": 6,
                        "title": "Metrics Scrape Health",
                        "type": "stat",
                        "targets": [
                            {
                                "expr": "up{job=\"signal-service\"}",
                                "legendFormat": "Metrics Endpoint Up",
                                "refId": "A"
                            },
                            {
                                "expr": "prometheus_target_scrape_duration_seconds{job=\"signal-service\"}",
                                "legendFormat": "Scrape Duration",
                                "refId": "B"
                            }
                        ],
                        "fieldConfig": {
                            "defaults": {
                                "color": {
                                    "mode": "thresholds"
                                },
                                "thresholds": {
                                    "steps": [
                                        {"color": "red", "value": 0},
                                        {"color": "green", "value": 1}
                                    ]
                                }
                            }
                        },
                        "gridPos": {"h": 6, "w": 24, "x": 0, "y": 12}
                    }
                ]
            }
        }
        
        dashboard_file = os.path.join(self.monitoring_dir, "slo_performance_dashboard.json")
        with open(dashboard_file, 'w') as f:
            json.dump(dashboard, f, indent=2)
        
        print(f"    ✅ Dashboard created: {dashboard_file}")
        print(f"    📊 Panels: {len(dashboard['dashboard']['panels'])}")
        
        return dashboard
    
    def create_grafana_import_script(self) -> str:
        """Create script to import all dashboards into Grafana."""
        print("📊 Creating Grafana Import Script...")
        
        import_script = '''#!/bin/bash
"""
Grafana Dashboard Import Script

Imports all Signal Service monitoring dashboards into Grafana.
"""

GRAFANA_URL="${GRAFANA_URL:-http://grafana:3000}"
GRAFANA_API_KEY="${GRAFANA_API_KEY:-admin:admin}"
MONITORING_DIR="monitoring"

echo "🔧 Importing Signal Service Dashboards to Grafana..."
echo "📍 Grafana URL: $GRAFANA_URL"

# Import Config Service Dashboard
echo "⚙️ Importing Config Service Dashboard..."
curl -X POST \\
  -H "Authorization: Bearer $GRAFANA_API_KEY" \\
  -H "Content-Type: application/json" \\
  -d @$MONITORING_DIR/config_service_dashboard.json \\
  $GRAFANA_URL/api/dashboards/db

# Import Database & Redis Pools Dashboard  
echo "🗄️ Importing Database & Redis Pools Dashboard..."
curl -X POST \\
  -H "Authorization: Bearer $GRAFANA_API_KEY" \\
  -H "Content-Type: application/json" \\
  -d @$MONITORING_DIR/database_redis_pools_dashboard.json \\
  $GRAFANA_URL/api/dashboards/db

# Import Circuit Breaker Dashboard
echo "🔌 Importing Circuit Breaker Dashboard..."
curl -X POST \\
  -H "Authorization: Bearer $GRAFANA_API_KEY" \\
  -H "Content-Type: application/json" \\
  -d @$MONITORING_DIR/circuit_breaker_dashboard.json \\
  $GRAFANA_URL/api/dashboards/db

# Import SLO & Performance Dashboard
echo "⚡ Importing SLO & Performance Dashboard..."
curl -X POST \\
  -H "Authorization: Bearer $GRAFANA_API_KEY" \\
  -H "Content-Type: application/json" \\
  -d @$MONITORING_DIR/slo_performance_dashboard.json \\
  $GRAFANA_URL/api/dashboards/db

echo "✅ All dashboards imported successfully!"
echo "🌐 Access dashboards at: $GRAFANA_URL"
'''
        
        script_path = os.path.join(self.monitoring_dir, "import_dashboards.sh")
        with open(script_path, 'w') as f:
            f.write(import_script)
        
        os.chmod(script_path, 0o755)
        
        print(f"    🔧 Import script: {script_path}")
        
        return script_path
    
    def run_day01_monitoring_setup(self) -> Dict[str, Any]:
        """Execute complete day-0/1 monitoring setup."""
        print("📊 Day-0/1 Monitoring Setup")
        print("=" * 60)
        
        # Create all dashboards
        self.dashboards["config_service"] = self.create_config_service_dashboard()
        print()
        
        self.dashboards["database_redis"] = self.create_database_pools_dashboard()
        print()
        
        self.dashboards["circuit_breaker"] = self.create_circuit_breaker_dashboard()
        print()
        
        self.dashboards["slo_performance"] = self.create_slo_performance_dashboard()
        print()
        
        # Create import script
        import_script = self.create_grafana_import_script()
        print()
        
        # Create monitoring summary
        summary = {
            "setup_timestamp": datetime.now().isoformat(),
            "dashboards_created": len(self.dashboards),
            "monitoring_directory": self.monitoring_dir,
            "import_script": import_script,
            "dashboards": {
                "config_service": "Config service health, latency, cache hit rate, errors",
                "database_redis": "DB/Redis pools, connection usage, query latency, hypertable health",
                "circuit_breaker": "Circuit breaker states, failure rates, recovery metrics",
                "slo_performance": "Request latency SLOs, error rates, throughput, backpressure"
            }
        }
        
        summary_file = os.path.join(self.monitoring_dir, f"monitoring_setup_summary_{self.timestamp}.json")
        with open(summary_file, 'w') as f:
            json.dump(summary, f, indent=2)
        
        print("=" * 60)
        print("🎯 Day-0/1 Monitoring Setup Complete")
        print(f"📊 Dashboards: {len(self.dashboards)} created")
        print(f"📁 Directory: {self.monitoring_dir}")
        print(f"🔧 Import script: {import_script}")
        print(f"📄 Summary: {summary_file}")
        
        return summary


def main():
    """Execute day-0/1 monitoring setup."""
    try:
        setup = Day01MonitoringSetup()
        results = setup.run_day01_monitoring_setup()
        
        print(f"\\n🎉 DAY-0/1 MONITORING SETUP COMPLETE")
        print(f"📊 {results['dashboards_created']} dashboards created")
        print(f"📁 All files in: {results['monitoring_directory']}")
        print(f"\\n🚀 Next steps:")
        print(f"   1. Set GRAFANA_URL and GRAFANA_API_KEY environment variables")
        print(f"   2. Run: ./{results['import_script']}")
        print(f"   3. Access dashboards in Grafana")
        
        return 0
        
    except Exception as e:
        print(f"💥 Day-0/1 monitoring setup failed: {e}")
        return 1


if __name__ == "__main__":
    exit_code = main()
    exit(exit_code)