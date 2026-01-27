#!/usr/bin/env python3
"""
Kite Broker Client - Phase 1 Migration

CLIENT_002: Kite integration with instrument_key-first interface
- Internal token resolution via registry
- Unified broker interface implementation
"""

import asyncio
import logging
from typing import Dict, Any, Optional
import aiohttp
from datetime import datetime
from app.brokers.base_broker_client import BaseBrokerClient, BrokerConfig, BrokerType

logger = logging.getLogger(__name__)

class KiteBrokerClient(BaseBrokerClient):
    """
    Kite broker client with instrument_key-first interface
    
    CLIENT_002: Implements unified broker interface with internal
    token resolution for Kite API operations.
    """
    
    def __init__(self, config: BrokerConfig):
        if config.broker_type != BrokerType.KITE:
            raise ValueError("KiteBrokerClient requires BrokerType.KITE")
        
        super().__init__(config)
        self.base_url = config.base_url or "https://api.kite.trade"
        self.headers = {
            "Authorization": f"token {config.api_key}:{config.access_token}",
            "Content-Type": "application/json",
            "X-Kite-Version": "3"
        }
    
    # =============================================================================
    # KITE-SPECIFIC IMPLEMENTATIONS (INTERNAL TOKEN-BASED)
    # =============================================================================
    
    async def _place_order_impl(self, 
                               broker_token: str,
                               side: str,
                               quantity: int, 
                               order_type: str,
                               price: Optional[float] = None,
                               **kwargs) -> Dict[str, Any]:
        """
        Internal Kite order placement using resolved broker token
        
        Args:
            broker_token: Kite instrument token (resolved from instrument_key)
            side: BUY/SELL
            quantity: Order quantity
            order_type: MARKET/LIMIT/SL/SL-M
            price: Limit price
            **kwargs: Additional Kite parameters
            
        Returns:
            Dict: Kite API response
        """
        logger.debug(f"Placing Kite order: token={broker_token[:8]}*** {side} {quantity}")
        
        # Map generic order types to Kite-specific types
        kite_order_type_map = {
            "MARKET": "MARKET",
            "LIMIT": "LIMIT", 
            "STOP": "SL",
            "STOP_LIMIT": "SL-M"
        }
        
        order_data = {
            "tradingsymbol": broker_token,  # Using resolved token
            "exchange": kwargs.get("exchange", "NSE"),
            "transaction_type": side,
            "order_type": kite_order_type_map.get(order_type, "MARKET"),
            "quantity": quantity,
            "product": kwargs.get("product", "CNC"),
            "validity": kwargs.get("validity", "DAY"),
        }
        
        # Add price for limit orders
        if order_type in ["LIMIT", "STOP_LIMIT"] and price:
            order_data["price"] = price
        
        # Add trigger price for stop orders  
        if order_type in ["STOP", "STOP_LIMIT"] and kwargs.get("trigger_price"):
            order_data["trigger_price"] = kwargs["trigger_price"]
        
        try:
            session = await self._get_session()
            async with session.post(
                f"{self.base_url}/orders/regular", 
                json=order_data,
                headers=self.headers
            ) as response:
                
                if response.status != 200:
                    error_text = await response.text()
                    raise Exception(f"Kite order failed: {error_text}")
                
                result = await response.json()
                
                # Return unified response format
                return {
                    "order_id": result.get("data", {}).get("order_id"),
                    "status": "PENDING",
                    "message": result.get("status", "success")
                }
                
        except Exception as e:
            logger.error(f"Kite order placement error: {e}")
            raise
    
    async def _get_quote_impl(self, broker_token: str) -> Dict[str, Any]:
        """
        Internal Kite quote retrieval using resolved broker token
        
        Args:
            broker_token: Kite instrument token
            
        Returns:
            Dict: Quote data in unified format
        """
        try:
            session = await self._get_session()
            
            # Kite quote API expects exchange:token format
            instruments = f"NSE:{broker_token}"
            
            async with session.get(
                f"{self.base_url}/quote",
                params={"i": instruments},
                headers=self.headers
            ) as response:
                
                if response.status != 200:
                    error_text = await response.text()
                    raise Exception(f"Kite quote failed: {error_text}")
                
                result = await response.json()
                quote_data = result.get("data", {}).get(f"NSE:{broker_token}", {})
                
                return {
                    "ltp": quote_data.get("last_price", 0.0),
                    "bid": quote_data.get("depth", {}).get("buy", [{}])[0].get("price"),
                    "ask": quote_data.get("depth", {}).get("sell", [{}])[0].get("price"), 
                    "volume": quote_data.get("volume", 0),
                    "timestamp": datetime.now().isoformat()
                }
                
        except Exception as e:
            logger.error(f"Kite quote error for token {broker_token[:8]}***: {e}")
            raise
    
    async def _get_order_status_impl(self, broker_order_id: str) -> Dict[str, Any]:
        """Get order status from Kite"""
        try:
            session = await self._get_session()
            async with session.get(
                f"{self.base_url}/orders/{broker_order_id}",
                headers=self.headers
            ) as response:
                
                if response.status != 200:
                    raise Exception(f"Kite order status failed: {response.status}")
                
                result = await response.json()
                order_data = result.get("data", [{}])[0]
                
                # Map Kite status to unified status
                kite_status_map = {
                    "OPEN": "OPEN",
                    "COMPLETE": "FILLED", 
                    "CANCELLED": "CANCELED",
                    "REJECTED": "REJECTED"
                }
                
                return {
                    "order_id": broker_order_id,
                    "status": kite_status_map.get(order_data.get("status"), "UNKNOWN"),
                    "quantity": order_data.get("quantity", 0),
                    "price": order_data.get("price"),
                    "side": order_data.get("transaction_type", ""),
                    "order_type": order_data.get("order_type", "")
                }
                
        except Exception as e:
            logger.error(f"Kite order status error: {e}")
            raise
    
    async def _cancel_order_impl(self, broker_order_id: str) -> bool:
        """Cancel order on Kite"""
        try:
            session = await self._get_session()
            async with session.delete(
                f"{self.base_url}/orders/regular/{broker_order_id}",
                headers=self.headers
            ) as response:
                
                return response.status == 200
                
        except Exception as e:
            logger.error(f"Kite order cancellation error: {e}")
            return False
    
    # =============================================================================
    # CONNECTION MANAGEMENT
    # =============================================================================
    
    async def _connect_impl(self):
        """Establish Kite session"""
        # Validate access token by making a profile request
        session = await self._get_session()
        async with session.get(
            f"{self.base_url}/user/profile",
            headers=self.headers
        ) as response:
            if response.status != 200:
                raise Exception(f"Kite authentication failed: {response.status}")
            
            profile = await response.json()
            logger.info(f"Kite connection established for user: {profile.get('data', {}).get('user_id')}")
    
    async def _disconnect_impl(self):
        """Close Kite session"""
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None
    
    async def _health_check_impl(self) -> Dict[str, Any]:
        """Kite-specific health check"""
        try:
            session = await self._get_session()
            async with session.get(
                f"{self.base_url}/user/margins",
                headers=self.headers
            ) as response:
                
                if response.status == 200:
                    margins = await response.json()
                    return {
                        "api_status": "connected",
                        "available_cash": margins.get("data", {}).get("equity", {}).get("available", {}).get("cash", 0),
                        "last_check": datetime.now().isoformat()
                    }
                else:
                    raise Exception(f"Health check failed: {response.status}")
                    
        except Exception as e:
            raise Exception(f"Kite health check failed: {e}")
    
    # =============================================================================
    # SESSION MANAGEMENT
    # =============================================================================
    
    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create HTTP session for Kite API"""
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=self.config.timeout)
            self._session = aiohttp.ClientSession(timeout=timeout)
        return self._session

# Factory function
def create_kite_client(api_key: str, 
                      access_token: str, 
                      api_secret: Optional[str] = None) -> KiteBrokerClient:
    """
    Create Kite broker client
    
    Args:
        api_key: Kite API key
        access_token: Kite access token
        api_secret: Kite API secret (optional)
        
    Returns:
        KiteBrokerClient: Ready-to-use Kite client
    """
    config = BrokerConfig(
        broker_type=BrokerType.KITE,
        api_key=api_key,
        api_secret=api_secret or "",
        access_token=access_token,
        rate_limit_per_second=3  # Kite rate limit
    )
    
    return KiteBrokerClient(config)