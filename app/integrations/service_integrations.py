"""Integration with Calendar, Alert, and Messaging services for Signal Service

Updated for consolidation: All signal notifications now route through SignalDeliveryService
for consistent delivery and entitlement checking.
"""

import asyncio
import httpx
from datetime import datetime
from typing import Dict, Optional, List
import logging

from app.services.signal_delivery_service import get_signal_delivery_service

logger = logging.getLogger(__name__)

class SignalServiceIntegrations:
    """Handles integrations with Calendar, Alert, and Messaging services for Signal Service"""
    
    def __init__(self):
        # Get service URLs from config_service exclusively (Architecture Principle #1: Config service exclusivity)
        try:
            from common.config_service.client import ConfigServiceClient
            from app.core.config import settings
            
            config_client = ConfigServiceClient(
                service_name="signal_service",
                environment=settings.environment,
                timeout=5
            )
            
            self.calendar_base_url = config_client.get_service_url("calendar_service")
            self.alert_base_url = config_client.get_service_url("alert_service") 
            self.messaging_base_url = config_client.get_service_url("messaging_service")
            
        except Exception as e:
            raise RuntimeError(f"Failed to get service URLs from config_service: {e}. No hardcoded fallbacks allowed per architecture.")
            
        self.timeout = 3.0  # Very short timeout for signal processing
        
    async def _make_request(self, method: str, url: str, data: Optional[Dict] = None, params: Optional[Dict] = None) -> Optional[Dict]:
        """Make HTTP request with error handling"""
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                if method.upper() == "GET":
                    response = await client.get(url, params=params)
                elif method.upper() == "POST":
                    response = await client.post(url, json=data)
                else:
                    return None
                
                if response.status_code == 200:
                    return response.json()
                else:
                    logger.debug(f"Service request failed: {response.status_code}")
                    return None
                    
        except Exception as e:
            logger.debug(f"Service integration error: {e}")
            return None
    
    async def is_trading_session_active(self, exchange: str = "NSE") -> bool:
        """Check if trading session is active for signal processing"""
        result = await self._make_request(
            "GET", 
            f"{self.calendar_base_url}/api/v1/market-status",
            params={"exchange": exchange}
        )
        
        if result:
            return result.get("is_open", True)
        
        # Fallback logic for high-frequency signal processing
        current_hour = datetime.now().hour
        return 9 <= current_hour <= 15
    
    async def send_signal_alert(self, user_id: str, symbol: str, signal_type: str, value: float, threshold: float) -> bool:
        """Send signal threshold breach alert via SignalDeliveryService (CONSOLIDATED)"""
        # Prepare signal data for unified delivery service
        signal_data = {
            "signal_id": f"{symbol}_{signal_type}_{int(datetime.now().timestamp())}",
            "symbol": symbol,
            "signal_type": signal_type,
            "value": value,
            "threshold": threshold,
            "message": f"Signal {signal_type} for {symbol}: {value:.4f} (threshold: {threshold:.4f})",
            "alert_type": "SIGNAL_ALERT",
            "timestamp": datetime.now().isoformat()
        }
        
        delivery_config = {
            "channels": ["ui", "telegram"],  # Default channels
            "priority": "medium"
        }
        
        # Use consolidated SignalDeliveryService
        try:
            delivery_service = get_signal_delivery_service()
            result = await delivery_service.deliver_signal(
                user_id=user_id,
                signal_data=signal_data,
                delivery_config=delivery_config
            )
            
            if result.get("overall_success", False):
                logger.debug(f"Signal alert delivered: {signal_type} for {symbol} to user {user_id}")
                return True
            else:
                logger.debug(f"Signal alert delivery failed: {signal_type} for {symbol} - {result.get('error', 'Unknown error')}")
                return False
                
        except Exception as e:
            logger.error(f"Signal alert delivery error: {e}")
            return False
    
    async def send_bulk_signal_alerts(self, alerts: List[Dict]) -> int:
        """Send multiple signal alerts efficiently via SignalDeliveryService (CONSOLIDATED)"""
        if not alerts:
            return 0
        
        try:
            # Transform alerts into signal delivery format
            signal_deliveries = []
            for alert in alerts:
                signal_data = {
                    "signal_id": f"{alert['symbol']}_{alert['signal_type']}_{int(datetime.now().timestamp())}",
                    "symbol": alert["symbol"],
                    "signal_type": alert["signal_type"], 
                    "value": alert["value"],
                    "threshold": alert["threshold"],
                    "message": f"Signal {alert['signal_type']} for {alert['symbol']}: {alert['value']:.4f} (threshold: {alert['threshold']:.4f})",
                    "alert_type": "SIGNAL_ALERT",
                    "timestamp": datetime.now().isoformat()
                }
                
                signal_deliveries.append({
                    "user_id": alert["user_id"],
                    "signal_data": signal_data,
                    "channels": ["ui", "telegram"],
                    "priority": "medium"
                })
            
            # Use consolidated SignalDeliveryService for bulk delivery
            delivery_service = get_signal_delivery_service()
            result = await delivery_service.deliver_bulk_signals(signal_deliveries)
            
            # Extract success count from result
            success_count = 0
            if result.get("bulk_delivery") and result.get("results"):
                # Count successful deliveries across services
                for service_result in result["results"].values():
                    if isinstance(service_result, dict) and service_result.get("success_count"):
                        success_count += service_result["success_count"]
                    elif isinstance(service_result, dict) and service_result.get("successful"):
                        success_count += len(service_result["successful"])
            
            logger.info(f"Bulk signal alerts: {success_count}/{len(alerts)} delivered successfully")
            return success_count
            
        except Exception as e:
            logger.error(f"Bulk signal delivery error: {e}")
            return 0
    
    async def notify_signal_computation_complete(self, user_id: str, symbol: str, indicators: List[str]) -> bool:
        """Notify user when signal computation is complete via SignalDeliveryService (CONSOLIDATED)"""
        # Prepare signal data for unified delivery
        signal_data = {
            "signal_id": f"{symbol}_computation_complete_{int(datetime.now().timestamp())}",
            "symbol": symbol,
            "signal_type": "computation_complete",
            "indicators": indicators,
            "message": f"Signal computation complete for {symbol}: {', '.join(indicators)}",
            "alert_type": "SIGNAL_UPDATE",
            "timestamp": datetime.now().isoformat()
        }
        
        delivery_config = {
            "channels": ["ui"],  # Computation complete notifications are typically UI-only
            "priority": "low"
        }
        
        # Use consolidated SignalDeliveryService
        try:
            delivery_service = get_signal_delivery_service()
            result = await delivery_service.deliver_signal(
                user_id=user_id,
                signal_data=signal_data,
                delivery_config=delivery_config
            )
            
            return result.get("overall_success", False)
            
        except Exception as e:
            logger.error(f"Signal computation notification error: {e}")
            return False
    
    async def send_system_signal_alert(self, message: str, priority: str = "medium") -> bool:
        """CONSOLIDATED: Send system-wide signal processing alert through SignalDeliveryService"""
        try:
            from app.services.signal_delivery_service import get_signal_delivery_service
            
            delivery_service = get_signal_delivery_service()
            
            # Transform to signal delivery format
            signal_data = {
                "signal_type": "system_alert",
                "alert_type": "SIGNAL_SYSTEM", 
                "message": message,
                "priority": priority,
                "timestamp": datetime.utcnow().isoformat(),
                "source": "signal_processing_system"
            }
            
            delivery_config = {
                "channels": ["ui"],
                "message": message,
                "priority": priority,
                "metadata": {
                    "alert_type": "SIGNAL_SYSTEM",
                    "system_wide": True
                }
            }
            
            # Send through unified delivery service
            # Use a special system user ID for system-wide alerts
            result = await delivery_service.deliver_signal(
                user_id="system",  # Special system user for system alerts
                signal_data=signal_data,
                delivery_config=delivery_config
            )
            
            return result.get("success", False)
            
        except Exception as e:
            logger.error(f"System signal alert failed: {e}")
            return False
    
    async def schedule_signal_computation(self, computation_data: Dict) -> bool:
        """Schedule signal computation for next trading session"""
        event_data = {
            "event_type": "SCHEDULED_SIGNAL_COMPUTATION",
            "computation_data": computation_data,
            "schedule_time": "next_market_open"
        }
        
        result = await self._make_request(
            "POST",
            f"{self.calendar_base_url}/api/v1/events",
            event_data
        )
        
        return result is not None
    
    async def send_threshold_breach_alert(self, user_id: str, symbol: str, indicator: str, current_value: float, threshold: float, direction: str) -> bool:
        """Send specific threshold breach alert via SignalDeliveryService (CONSOLIDATED)"""
        # Prepare signal data for unified delivery
        signal_data = {
            "signal_id": f"{symbol}_{indicator}_breach_{int(datetime.now().timestamp())}",
            "symbol": symbol,
            "indicator": indicator,
            "signal_type": "threshold_breach",
            "current_value": current_value,
            "threshold": threshold,
            "direction": direction,
            "message": f"THRESHOLD BREACH: {indicator} for {symbol} is {current_value:.4f} ({direction} threshold {threshold:.4f})",
            "alert_type": "THRESHOLD_BREACH",
            "timestamp": datetime.now().isoformat()
        }
        
        delivery_config = {
            "channels": ["ui", "email", "telegram"],  # High priority - multiple channels
            "priority": "high"
        }
        
        # Use consolidated SignalDeliveryService
        try:
            delivery_service = get_signal_delivery_service()
            result = await delivery_service.deliver_signal(
                user_id=user_id,
                signal_data=signal_data,
                delivery_config=delivery_config
            )
            
            return result.get("overall_success", False)
            
        except Exception as e:
            logger.error(f"Threshold breach alert delivery error: {e}")
            return False


# Global service integration instance
signal_integrations = SignalServiceIntegrations()

# Convenience functions for signal service
async def check_signal_processing_allowed(exchange: str = "NSE") -> bool:
    """Check if signal processing should continue (market hours)"""
    return await signal_integrations.is_trading_session_active(exchange)

async def notify_signal_threshold_breach(user_id: str, symbol: str, indicator: str, value: float, threshold: float, direction: str = "above") -> None:
    """Notify user of signal threshold breach"""
    await signal_integrations.send_threshold_breach_alert(user_id, symbol, indicator, value, threshold, direction)

async def notify_computation_complete(user_id: str, symbol: str, indicators: List[str]) -> None:
    """Notify user when signal computation is complete"""
    await signal_integrations.notify_signal_computation_complete(user_id, symbol, indicators)

async def send_bulk_alerts(alerts: List[Dict]) -> int:
    """Send multiple alerts efficiently"""
    return await signal_integrations.send_bulk_signal_alerts(alerts)

async def alert_system_status(message: str, priority: str = "medium") -> None:
    """Send system status alert"""
    await signal_integrations.send_system_signal_alert(message, priority)


# Decorator for market hours validation in signal processing
def validate_market_hours(func):
    """Decorator to check market hours before signal processing"""
    async def wrapper(*args, **kwargs):
        if await check_signal_processing_allowed():
            return await func(*args, **kwargs)
        else:
            # Market is closed, queue for next session
            computation_data = {
                "function": func.__name__,
                "args": str(args),
                "kwargs": str(kwargs),
                "scheduled_at": datetime.now().isoformat()
            }
            await signal_integrations.schedule_signal_computation(computation_data)
            return {"status": "queued", "message": "Market closed, queued for next session"}
    
    return wrapper


# Signal processing integration utilities
class SignalProcessingIntegration:
    """Utilities for integrating signal processing with services"""
    
    @staticmethod
    async def process_with_notifications(symbol: str, user_id: str, indicators: List[str], thresholds: Dict[str, float]):
        """Process signals with automatic notifications"""
        results = {}
        alerts_to_send = []
        
        for indicator in indicators:
            # Simulate signal computation (replace with actual logic)
            computed_value = 50.0  # Placeholder
            threshold = thresholds.get(indicator, 0.0)
            
            results[indicator] = computed_value
            
            # Check threshold breach
            if computed_value > threshold:
                alerts_to_send.append({
                    "user_id": user_id,
                    "symbol": symbol,
                    "signal_type": indicator,
                    "value": computed_value,
                    "threshold": threshold
                })
        
        # Send alerts if any
        if alerts_to_send:
            await send_bulk_alerts(alerts_to_send)
        
        # Notify completion
        await notify_computation_complete(user_id, symbol, indicators)
        
        return results


# Integration health check
async def check_signal_service_integrations() -> Dict[str, bool]:
    """Check health of all integrated services"""
    integrations = SignalServiceIntegrations()
    
    health_checks = {
        "calendar": integrations._make_request("GET", f"{integrations.calendar_base_url}/health"),
        "alert": integrations._make_request("GET", f"{integrations.alert_base_url}/health"),
        "messaging": integrations._make_request("GET", f"{integrations.messaging_base_url}/health")
    }
    
    results = {}
    for service, check_task in health_checks.items():
        try:
            result = await check_task
            results[service] = result is not None and result.get("status") == "healthy"
        except:
            results[service] = False
    
    return results