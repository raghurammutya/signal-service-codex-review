#!/bin/bash
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
