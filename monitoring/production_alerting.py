"""
Production Alerting Rules for Signal Service

Critical alerts for production operations management based on enhanced metrics.
Focuses on business impact and operational excellence.
"""
import json
from typing import Dict, List, Any
from dataclasses import dataclass, asdict


@dataclass
class AlertRule:
    """Alert rule definition"""
    alert: str
    expr: str
    for_duration: str
    labels: Dict[str, str]
    annotations: Dict[str, str]


class ProductionAlertingRules:
    """
    Production-ready alerting rules for signal_service.
    
    Categorized by:
    - Critical Business Impact (immediate response)
    - Performance Degradation (tuning required)
    - Capacity Planning (scaling needed)
    - External Dependencies (service health)
    """
    
    def __init__(self):
        self.critical_alerts = self._define_critical_alerts()
        self.performance_alerts = self._define_performance_alerts()
        self.capacity_alerts = self._define_capacity_alerts()
        self.dependency_alerts = self._define_dependency_alerts()
    
    def _define_critical_alerts(self) -> List[AlertRule]:
        """Critical business impact alerts - immediate response required"""
        return [
            # Signal Generation Failure
            AlertRule(
                alert="SignalServiceDown",
                expr='up{job="signal-service"} == 0',
                for_duration="30s",
                labels={
                    "severity": "critical",
                    "team": "trading",
                    "impact": "business_critical"
                },
                annotations={
                    "summary": "Signal Service is down",
                    "description": "Signal service has been down for more than 30 seconds. All signal generation stopped.",
                    "runbook": "Check service logs and restart if necessary",
                    "impact": "Complete signal generation outage"
                }
            ),
            
            # High Error Rate
            AlertRule(
                alert="SignalServiceHighErrorRate",
                expr='(rate(signal_service_api_requests_total{status_code!~"2.."}[5m]) / rate(signal_service_api_requests_total[5m])) > 0.1',
                for_duration="2m",
                labels={
                    "severity": "critical", 
                    "team": "trading",
                    "impact": "user_experience"
                },
                annotations={
                    "summary": "High error rate in Signal Service",
                    "description": "Error rate is above 10% for more than 2 minutes",
                    "runbook": "Check application logs and external service health",
                    "impact": "Users experiencing frequent failures"
                }
            ),
            
            # Greeks Calculation Failure
            AlertRule(
                alert="GreeksCalculationSystemFailure", 
                expr='rate(signal_service_greeks_calculation_seconds_count[5m]) == 0 and rate(signal_service_api_requests_total{endpoint=~".*greeks.*"}[5m]) > 0',
                for_duration="1m",
                labels={
                    "severity": "critical",
                    "team": "quant",
                    "impact": "business_critical"
                },
                annotations={
                    "summary": "Greeks calculation system failure",
                    "description": "Greeks calculations are not completing despite API requests",
                    "runbook": "Check vectorized engine and circuit breaker status",
                    "impact": "Options trading signals unavailable"
                }
            ),
            
            # Circuit Breaker Open Critical Services
            AlertRule(
                alert="CriticalServiceCircuitBreakerOpen",
                expr='signal_service_circuit_breaker_state{service_name=~"ticker_service|marketplace_service"} == 1',
                for_duration="30s",
                labels={
                    "severity": "critical",
                    "team": "platform",
                    "impact": "business_critical"
                },
                annotations={
                    "summary": "Critical service circuit breaker is open",
                    "description": "Circuit breaker for {{ $labels.service_name }} is open, blocking {{ $labels.operation }}",
                    "runbook": "Check external service health and network connectivity", 
                    "impact": "Reduced signal generation capabilities"
                }
            )
        ]
    
    def _define_performance_alerts(self) -> List[AlertRule]:
        """Performance degradation alerts - tuning required"""
        return [
            # High API Latency
            AlertRule(
                alert="SignalServiceHighLatency",
                expr='histogram_quantile(0.95, rate(signal_service_api_request_duration_seconds_bucket[5m])) > 5.0',
                for_duration="3m",
                labels={
                    "severity": "warning",
                    "team": "platform",
                    "impact": "performance"
                },
                annotations={
                    "summary": "High API latency in Signal Service",
                    "description": "95th percentile API latency is above 5 seconds",
                    "runbook": "Check resource utilization and database performance",
                    "impact": "Degraded user experience"
                }
            ),
            
            # Slow Greeks Calculations
            AlertRule(
                alert="SlowGreeksCalculations",
                expr='histogram_quantile(0.90, rate(signal_service_greeks_calculation_seconds_bucket{vectorized="true"}[5m])) > 1.0',
                for_duration="5m",
                labels={
                    "severity": "warning",
                    "team": "quant",
                    "impact": "performance"
                },
                annotations={
                    "summary": "Greeks calculations are running slowly",
                    "description": "90th percentile vectorized Greeks calculation time > 1 second",
                    "runbook": "Check CPU utilization and consider batch size optimization",
                    "impact": "Delayed signal generation"
                }
            ),
            
            # Low Cache Hit Rate
            AlertRule(
                alert="LowCacheHitRate",
                expr='signal_service_cache_hit_ratio{cache_type="greeks"} < 0.7',
                for_duration="10m",
                labels={
                    "severity": "warning",
                    "team": "platform", 
                    "impact": "efficiency"
                },
                annotations={
                    "summary": "Low cache hit rate for Greeks calculations",
                    "description": "Greeks cache hit rate is below 70%",
                    "runbook": "Check cache configuration and TTL settings",
                    "impact": "Increased computational cost and latency"
                }
            ),
            
            # High Queue Backlog
            AlertRule(
                alert="HighQueueBacklog",
                expr='signal_service_queue_size{priority="critical"} > 100',
                for_duration="1m",
                labels={
                    "severity": "warning",
                    "team": "platform",
                    "impact": "performance"
                },
                annotations={
                    "summary": "High queue backlog detected",
                    "description": "Critical priority queue has more than 100 items",
                    "runbook": "Check processing capacity and consider scaling",
                    "impact": "Delayed processing of critical signals"
                }
            )
        ]
    
    def _define_capacity_alerts(self) -> List[AlertRule]:
        """Capacity planning alerts - scaling decisions needed"""
        return [
            # High CPU Usage
            AlertRule(
                alert="SignalServiceHighCPUUsage",
                expr='rate(process_cpu_seconds_total{job="signal-service"}[5m]) > 0.8',
                for_duration="10m",
                labels={
                    "severity": "warning",
                    "team": "platform",
                    "impact": "capacity"
                },
                annotations={
                    "summary": "High CPU usage in Signal Service",
                    "description": "CPU usage is above 80% for more than 10 minutes",
                    "runbook": "Consider scaling up or optimizing algorithms",
                    "impact": "Performance degradation risk"
                }
            ),
            
            # High Memory Usage
            AlertRule(
                alert="SignalServiceHighMemoryUsage",
                expr='process_resident_memory_bytes{job="signal-service"} / 1024/1024/1024 > 4',
                for_duration="5m", 
                labels={
                    "severity": "warning",
                    "team": "platform",
                    "impact": "capacity"
                },
                annotations={
                    "summary": "High memory usage in Signal Service",
                    "description": "Memory usage is above 4GB",
                    "runbook": "Check for memory leaks and consider scaling",
                    "impact": "Risk of OOM and service restart"
                }
            ),
            
            # High Request Rate
            AlertRule(
                alert="SignalServiceHighRequestRate", 
                expr='rate(signal_service_api_requests_total[5m]) > 1000',
                for_duration="10m",
                labels={
                    "severity": "info",
                    "team": "platform",
                    "impact": "capacity"
                },
                annotations={
                    "summary": "High request rate to Signal Service",
                    "description": "Request rate is above 1000 RPS",
                    "runbook": "Monitor performance and consider horizontal scaling",
                    "impact": "Approaching capacity limits"
                }
            ),
            
            # Growing Subscription Count
            AlertRule(
                alert="HighActiveSubscriptions",
                expr='signal_service_active_subscriptions > 10000',
                for_duration="0s",
                labels={
                    "severity": "info",
                    "team": "product",
                    "impact": "capacity"
                },
                annotations={
                    "summary": "High number of active subscriptions",
                    "description": "Active subscriptions exceed 10,000",
                    "runbook": "Plan for increased computational capacity",
                    "impact": "Resource planning required"
                }
            )
        ]
    
    def _define_dependency_alerts(self) -> List[AlertRule]:
        """External service dependency alerts"""
        return [
            # External Service Down
            AlertRule(
                alert="ExternalServiceDown",
                expr='signal_service_external_service_health == 0',
                for_duration="1m",
                labels={
                    "severity": "warning",
                    "team": "platform",
                    "impact": "dependency"
                },
                annotations={
                    "summary": "External service is down",
                    "description": "{{ $labels.service_name }} service is unhealthy",
                    "runbook": "Check external service status and network connectivity",
                    "impact": "Reduced signal service capabilities"
                }
            ),
            
            # High External Service Latency
            AlertRule(
                alert="ExternalServiceHighLatency",
                expr='histogram_quantile(0.95, rate(signal_service_external_service_duration_seconds_bucket[5m])) > 10.0',
                for_duration="5m",
                labels={
                    "severity": "warning",
                    "team": "platform", 
                    "impact": "dependency"
                },
                annotations={
                    "summary": "High latency to external service",
                    "description": "95th percentile latency to {{ $labels.service_name }} > 10s",
                    "runbook": "Check network and external service performance",
                    "impact": "Degraded signal generation performance"
                }
            ),
            
            # Dependency Error Rate
            AlertRule(
                alert="HighDependencyErrorRate",
                expr='rate(signal_service_dependency_errors_total[5m]) > 10',
                for_duration="3m",
                labels={
                    "severity": "warning",
                    "team": "platform",
                    "impact": "dependency"
                },
                annotations={
                    "summary": "High error rate for external dependencies",
                    "description": "Dependency errors above 10 per minute",
                    "runbook": "Check external service health and API limits",
                    "impact": "Increased failure rate in signal generation"
                }
            ),
            
            # Config Service Unavailable (Critical)
            AlertRule(
                alert="ConfigServiceUnavailable",
                expr='signal_service_external_service_health{service_name="config_service"} == 0',
                for_duration="10s",
                labels={
                    "severity": "critical",
                    "team": "platform",
                    "impact": "business_critical"
                },
                annotations={
                    "summary": "Config Service is unavailable",
                    "description": "Config Service is required for signal service operation",
                    "runbook": "Check config service immediately - service may fail to start",
                    "impact": "Service startup failures and configuration issues"
                }
            )
        ]
    
    def generate_prometheus_rules(self) -> Dict[str, Any]:
        """Generate Prometheus alerting rules configuration"""
        
        all_alerts = (
            self.critical_alerts + 
            self.performance_alerts + 
            self.capacity_alerts + 
            self.dependency_alerts
        )
        
        return {
            "groups": [
                {
                    "name": "signal-service.critical",
                    "rules": [asdict(alert) for alert in self.critical_alerts]
                },
                {
                    "name": "signal-service.performance", 
                    "rules": [asdict(alert) for alert in self.performance_alerts]
                },
                {
                    "name": "signal-service.capacity",
                    "rules": [asdict(alert) for alert in self.capacity_alerts]
                },
                {
                    "name": "signal-service.dependencies",
                    "rules": [asdict(alert) for alert in self.dependency_alerts]
                }
            ]
        }
    
    def generate_grafana_alerts(self) -> List[Dict[str, Any]]:
        """Generate Grafana alert definitions"""
        
        grafana_alerts = []
        
        for alert in self.critical_alerts + self.performance_alerts:
            grafana_alerts.append({
                "uid": f"signal-service-{alert.alert.lower()}",
                "title": alert.alert,
                "condition": "A",
                "data": [{
                    "refId": "A",
                    "queryType": "",
                    "model": {
                        "expr": alert.expr,
                        "interval": "",
                        "legendFormat": "",
                        "refId": "A"
                    }
                }],
                "noDataState": "NoData",
                "execErrState": "Alerting",
                "for": alert.for_duration,
                "annotations": alert.annotations,
                "labels": alert.labels,
                "frequency": "10s"
            })
        
        return grafana_alerts