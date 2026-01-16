"""Integration with Calendar, Alert, and Messaging services for Signal Service"""

import asyncio
import httpx
from datetime import datetime
from typing import Dict, Optional, List
import logging

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
        """Send signal threshold breach alert"""
        message = f"Signal {signal_type} for {symbol}: {value:.4f} (threshold: {threshold:.4f})"
        
        alert_data = {
            "user_id": user_id,
            "alert_type": "SIGNAL_ALERT",
            "message": message,
            "priority": "medium",
            "channels": ["ui"]
        }
        
        result = await self._make_request(
            "POST",
            f"{self.alert_base_url}/api/v1/alerts/send",
            alert_data
        )
        
        if result:
            logger.debug(f"Signal alert sent: {signal_type} for {symbol} to user {user_id}")
            return True
        else:
            logger.debug(f"Failed to send signal alert: {signal_type} for {symbol}")
            return False
    
    async def send_bulk_signal_alerts(self, alerts: List[Dict]) -> int:
        """Send multiple signal alerts efficiently"""
        tasks = []
        for alert in alerts:
            task = self.send_signal_alert(
                alert["user_id"],
                alert["symbol"],
                alert["signal_type"],
                alert["value"],
                alert["threshold"]
            )
            tasks.append(task)
        
        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            success_count = sum(1 for r in results if r is True)
            logger.info(f"Bulk signal alerts: {success_count}/{len(alerts)} sent successfully")
            return success_count
        return 0
    
    async def notify_signal_computation_complete(self, user_id: str, symbol: str, indicators: List[str]) -> bool:
        """Notify user when signal computation is complete"""
        message = f"Signal computation complete for {symbol}: {', '.join(indicators)}"
        
        message_data = {
            "recipient": user_id,
            "message": message,
            "message_type": "SIGNAL_UPDATE",
            "delivery_method": "async"
        }
        
        result = await self._make_request(
            "POST",
            f"{self.messaging_base_url}/api/v1/messages/send",
            message_data
        )
        
        return result is not None
    
    async def send_system_signal_alert(self, message: str, priority: str = "medium") -> bool:
        """Send system-wide signal processing alert"""
        alert_data = {
            "user_id": "system",
            "alert_type": "SIGNAL_SYSTEM",
            "message": message,
            "priority": priority,
            "channels": ["ui"]
        }
        
        result = await self._make_request(
            "POST",
            f"{self.alert_base_url}/api/v1/alerts/send",
            alert_data
        )
        
        return result is not None
    
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
        """Send specific threshold breach alert"""
        message = f"THRESHOLD BREACH: {indicator} for {symbol} is {current_value:.4f} ({direction} threshold {threshold:.4f})"
        
        alert_data = {
            "user_id": user_id,
            "alert_type": "THRESHOLD_BREACH",
            "message": message,
            "priority": "high",
            "channels": ["ui", "email"]
        }
        
        result = await self._make_request(
            "POST",
            f"{self.alert_base_url}/api/v1/alerts/send",
            alert_data
        )
        
        return result is not None


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