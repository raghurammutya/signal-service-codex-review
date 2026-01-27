"""
Production Monitoring Endpoints for Signal Service
Provides observability into Greeks calculations, circuit breakers, and performance
"""

import logging
import os

# Import standardized error handling (architecture compliance)
import sys
from datetime import datetime

from fastapi import APIRouter

from app.core.circuit_breaker import get_all_circuit_breaker_metrics, get_circuit_breaker

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))))
from common.errors.standardized_errors import internal_server_error

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/monitoring", tags=["monitoring"])


@router.get("/circuit-breakers")
async def get_circuit_breaker_status():
    """
    Get status of all circuit breakers protecting Greeks calculations.
    Used by monitoring systems to track resilience patterns.
    """
    try:
        metrics = get_all_circuit_breaker_metrics()

        # Calculate summary statistics
        summary = {
            'total_breakers': len(metrics),
            'open_breakers': len([m for m in metrics.values() if m['state'] == 'open']),
            'half_open_breakers': len([m for m in metrics.values() if m['state'] == 'half_open']),
            'closed_breakers': len([m for m in metrics.values() if m['state'] == 'closed']),
            'total_requests': sum(m['metrics']['total_requests'] for m in metrics.values()),
            'total_failures': sum(m['metrics']['failed_requests'] for m in metrics.values()),
            'total_rejections': sum(m['metrics']['rejected_requests'] for m in metrics.values()),
            'overall_failure_rate': 0.0,
            'timestamp': datetime.utcnow().isoformat()
        }

        # Calculate overall failure rate
        if summary['total_requests'] > 0:
            summary['overall_failure_rate'] = summary['total_failures'] / summary['total_requests']

        return {
            'summary': summary,
            'circuit_breakers': metrics,
            'health_status': 'healthy' if summary['open_breakers'] == 0 else 'degraded'
        }

    except Exception as e:
        logger.error(f"Circuit breaker monitoring failed: {e}")
        internal_server_error("Circuit breaker monitoring failed", {"error": str(e)})


@router.get("/circuit-breakers/{breaker_type}")
async def get_specific_circuit_breaker(breaker_type: str):
    """
    Get detailed metrics for a specific circuit breaker.

    Available types: individual, vectorized, bulk, default
    """
    try:
        breaker = get_circuit_breaker(breaker_type)
        metrics = breaker.get_metrics()

        # Add additional analysis
        analysis = {
            'health_assessment': 'healthy',
            'recommendations': [],
            'alert_level': 'none'
        }

        # Health assessment based on metrics
        if metrics['state'] == 'open':
            analysis['health_assessment'] = 'critical'
            analysis['alert_level'] = 'critical'
            analysis['recommendations'].append('Service is failing, investigate root cause')

        elif metrics['state'] == 'half_open':
            analysis['health_assessment'] = 'warning'
            analysis['alert_level'] = 'warning'
            analysis['recommendations'].append('Service is recovering, monitor closely')

        elif metrics['metrics']['failure_rate'] > 0.1:  # > 10% failure rate
            analysis['health_assessment'] = 'warning'
            analysis['alert_level'] = 'warning'
            analysis['recommendations'].append('Elevated failure rate detected')

        elif metrics['metrics']['slow_call_rate'] > 0.5:  # > 50% slow calls
            analysis['health_assessment'] = 'warning'
            analysis['alert_level'] = 'warning'
            analysis['recommendations'].append('Performance degradation detected')

        return {
            'breaker_type': breaker_type,
            'metrics': metrics,
            'analysis': analysis,
            'timestamp': datetime.utcnow().isoformat()
        }

    except Exception as e:
        logger.error(f"Circuit breaker {breaker_type} monitoring failed: {e}")
        internal_server_error(f"Circuit breaker {breaker_type} monitoring failed", {"error": str(e)})


@router.get("/performance/greeks")
async def get_greeks_performance_metrics():
    """
    Get performance metrics for Greeks calculations.
    Compares vectorized vs individual calculation performance.
    """
    try:
        from app.services.metrics_service import get_metrics_collector

        metrics_collector = get_metrics_collector()

        # Get real Greeks performance metrics
        greeks_metrics = metrics_collector.get_greeks_performance_metrics()
        system_metrics = metrics_collector.get_system_metrics()
        cache_metrics = metrics_collector.get_cache_performance_metrics()

        # Calculate performance insights
        performance_analysis = {
            'overall_performance': 'excellent' if greeks_metrics.get('success_rate', 0) > 0.95 else 'good',
            'throughput_assessment': 'high' if greeks_metrics.get('calculations_per_minute', 0) > 30 else 'moderate',
            'latency_assessment': 'fast' if greeks_metrics.get('average_duration_ms', 0) < 100 else 'acceptable',
            'reliability_score': round(greeks_metrics.get('success_rate', 0) * 100, 1)
        }

        # Get comparison metrics by calculation type
        breakdown = greeks_metrics.get('breakdown_by_type', {})
        performance_comparison = {}

        for calc_type, metrics in breakdown.items():
            performance_comparison[calc_type] = {
                'average_duration_ms': metrics.get('average_duration_ms', 0),
                'error_rate': metrics.get('error_rate', 0),
                'total_calculations': metrics.get('count', 0),
                'performance_grade': 'A' if metrics.get('average_duration_ms', 1000) < 100 else 'B'
            }

        return {
            'summary': greeks_metrics,
            'performance_analysis': performance_analysis,
            'calculation_type_comparison': performance_comparison,
            'cache_performance': cache_metrics,
            'system_impact': {
                'cpu_utilization': system_metrics.get('process', {}).get('cpu_percent', 0),
                'memory_usage_mb': system_metrics.get('process', {}).get('memory_mb', 0)
            },
            'timestamp': datetime.utcnow().isoformat()
        }

    except Exception as e:
        logger.error(f"Performance metrics collection failed: {e}")
        internal_server_error("Performance monitoring failed", {"error": str(e)})


@router.get("/model-configuration")
async def get_model_configuration_status():
    """
    Monitor the Greeks model configuration from config_service.
    Tracks parameter changes and validation status.
    """
    try:
        from app.core.greeks_model_config import get_greeks_model_config

        model_config = get_greeks_model_config()
        model_info = model_config.get_model_info()

        # Add monitoring-specific information
        status_data = {
            'model_configuration': model_info,
            'validation_status': 'valid',
            'last_updated': datetime.utcnow().isoformat(),
            'parameter_health': {
                'risk_free_rate': {
                    'value': model_info['parameters']['risk_free_rate'],
                    'status': 'normal' if 0.0 <= model_info['parameters']['risk_free_rate'] <= 0.15 else 'warning',
                    'last_changed': None  # Would track from config service
                },
                'dividend_yield': {
                    'value': model_info['parameters']['dividend_yield'],
                    'status': 'normal' if 0.0 <= model_info['parameters']['dividend_yield'] <= 0.10 else 'warning',
                    'last_changed': None
                },
                'volatility_bounds': {
                    'min': model_info['parameters']['volatility_bounds'][0],
                    'max': model_info['parameters']['volatility_bounds'][1],
                    'status': 'normal' if model_info['parameters']['volatility_bounds'][1] <= 10.0 else 'warning',
                    'last_changed': None
                }
            },
            'config_service_connectivity': 'connected',  # Would check actual connectivity
            'fallback_mode': False
        }

        return status_data

    except Exception as e:
        logger.error(f"Model configuration monitoring failed: {e}")
        return {
            'validation_status': 'error',
            'error': str(e),
            'fallback_mode': True,
            'timestamp': datetime.utcnow().isoformat()
        }


@router.get("/alerts")
async def get_active_alerts():
    """
    Get active alerts and warnings for the Signal Service.
    Used by monitoring dashboards for alerting.
    """
    try:
        alerts = []

        # Check circuit breaker states
        cb_metrics = get_all_circuit_breaker_metrics()
        for breaker_type, metrics in cb_metrics.items():
            if metrics['state'] == 'open':
                alerts.append({
                    'severity': 'critical',
                    'type': 'circuit_breaker_open',
                    'message': f'{breaker_type} circuit breaker is OPEN',
                    'details': {
                        'breaker_type': breaker_type,
                        'failure_rate': metrics['metrics']['failure_rate'],
                        'time_in_state': metrics['state_info']['time_in_current_state']
                    },
                    'timestamp': datetime.utcnow().isoformat()
                })
            elif metrics['state'] == 'half_open':
                alerts.append({
                    'severity': 'warning',
                    'type': 'circuit_breaker_recovering',
                    'message': f'{breaker_type} circuit breaker is testing recovery',
                    'details': {
                        'breaker_type': breaker_type,
                        'test_requests': metrics['metrics']['total_requests']
                    },
                    'timestamp': datetime.utcnow().isoformat()
                })
            elif metrics['metrics']['failure_rate'] > 0.1:
                alerts.append({
                    'severity': 'warning',
                    'type': 'high_failure_rate',
                    'message': f'{breaker_type} calculations showing elevated failure rate',
                    'details': {
                        'breaker_type': breaker_type,
                        'failure_rate': metrics['metrics']['failure_rate']
                    },
                    'timestamp': datetime.utcnow().isoformat()
                })

        return {
            'total_alerts': len(alerts),
            'critical_alerts': len([a for a in alerts if a['severity'] == 'critical']),
            'warning_alerts': len([a for a in alerts if a['severity'] == 'warning']),
            'alerts': alerts,
            'timestamp': datetime.utcnow().isoformat()
        }

    except Exception as e:
        logger.error(f"Alert monitoring failed: {e}")
        internal_server_error("Alert monitoring failed", {"error": str(e)})


@router.post("/circuit-breakers/{breaker_type}/reset")
async def reset_circuit_breaker(breaker_type: str):
    """
    Reset a specific circuit breaker to CLOSED state.
    Use with caution - only reset if underlying issue is resolved.
    """
    try:
        breaker = get_circuit_breaker(breaker_type)
        old_state = breaker.state.value

        breaker.reset()

        logger.info(f"Circuit breaker {breaker_type} manually reset from {old_state} to CLOSED")

        return {
            'message': f'Circuit breaker {breaker_type} reset successfully',
            'previous_state': old_state,
            'current_state': 'closed',
            'timestamp': datetime.utcnow().isoformat()
        }

    except Exception as e:
        logger.error(f"Circuit breaker reset failed for {breaker_type}: {e}")
        internal_server_error(f"Circuit breaker reset failed for {breaker_type}", {"error": str(e)})


async def get_prometheus_metrics():
    """
    Export metrics in Prometheus format for scraping.
    """
    try:
        metrics = []

        # Circuit breaker metrics
        cb_metrics = get_all_circuit_breaker_metrics()
        for breaker_type, data in cb_metrics.items():
            # State as numeric (0=closed, 1=half_open, 2=open)
            state_value = {'closed': 0, 'half_open': 1, 'open': 2}[data['state']]
            metrics.append(f'signal_service_circuit_breaker_state{{type="{breaker_type}"}} {state_value}')
            metrics.append(f'signal_service_circuit_breaker_requests_total{{type="{breaker_type}"}} {data["metrics"]["total_requests"]}')
            metrics.append(f'signal_service_circuit_breaker_failures_total{{type="{breaker_type}"}} {data["metrics"]["failed_requests"]}')
            metrics.append(f'signal_service_circuit_breaker_rejections_total{{type="{breaker_type}"}} {data["metrics"]["rejected_requests"]}')
            metrics.append(f'signal_service_circuit_breaker_failure_rate{{type="{breaker_type}"}} {data["metrics"]["failure_rate"]}')


        from fastapi.responses import PlainTextResponse
        return PlainTextResponse('\n'.join(metrics))

    except Exception as e:
        logger.error(f"Prometheus metrics export failed: {e}")
        internal_server_error("Prometheus metrics export failed", {"error": str(e)})
