"""
Production Monitoring Package for Signal Service

Comprehensive monitoring infrastructure that enhances existing capabilities
with production-critical metrics for operations management.
"""

from .enhanced_metrics import get_enhanced_metrics_collector, ProductionMetricsCollector
from .production_alerting import ProductionAlertingRules

__all__ = [
    'get_enhanced_metrics_collector',
    'ProductionMetricsCollector', 
    'ProductionAlertingRules'
]

__version__ = "1.0.0"