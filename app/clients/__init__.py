"""
Service Client Integration Layer for signal_service

API Delegation Era - Architecture v3.0 compliance
Provides unified access to all external service APIs with circuit breakers.
"""

from .alert_service_client import get_alert_service_client, AlertServiceClient, AlertPriority, AlertChannel
from .comms_service_client import get_comms_service_client, CommsServiceClient

__all__ = [
    'get_alert_service_client',
    'get_comms_service_client', 
    'AlertServiceClient',
    'CommsServiceClient',
    'AlertPriority',
    'AlertChannel'
]