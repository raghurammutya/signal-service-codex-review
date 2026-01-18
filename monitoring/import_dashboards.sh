#!/bin/bash
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
curl -X POST \
  -H "Authorization: Bearer $GRAFANA_API_KEY" \
  -H "Content-Type: application/json" \
  -d @$MONITORING_DIR/config_service_dashboard.json \
  $GRAFANA_URL/api/dashboards/db

# Import Database & Redis Pools Dashboard  
echo "🗄️ Importing Database & Redis Pools Dashboard..."
curl -X POST \
  -H "Authorization: Bearer $GRAFANA_API_KEY" \
  -H "Content-Type: application/json" \
  -d @$MONITORING_DIR/database_redis_pools_dashboard.json \
  $GRAFANA_URL/api/dashboards/db

# Import Circuit Breaker Dashboard
echo "🔌 Importing Circuit Breaker Dashboard..."
curl -X POST \
  -H "Authorization: Bearer $GRAFANA_API_KEY" \
  -H "Content-Type: application/json" \
  -d @$MONITORING_DIR/circuit_breaker_dashboard.json \
  $GRAFANA_URL/api/dashboards/db

# Import SLO & Performance Dashboard
echo "⚡ Importing SLO & Performance Dashboard..."
curl -X POST \
  -H "Authorization: Bearer $GRAFANA_API_KEY" \
  -H "Content-Type: application/json" \
  -d @$MONITORING_DIR/slo_performance_dashboard.json \
  $GRAFANA_URL/api/dashboards/db

echo "✅ All dashboards imported successfully!"
echo "🌐 Access dashboards at: $GRAFANA_URL"
