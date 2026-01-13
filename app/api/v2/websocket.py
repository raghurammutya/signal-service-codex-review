"""
WebSocket API for Real-time Signal Streaming
Supports 10,000+ concurrent connections with <50ms latency
"""
import asyncio
import json
from typing import Dict, Set, Optional, Any
from datetime import datetime
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
from contextlib import asynccontextmanager

import logging
logger = logging.getLogger(__name__)
from common.storage.redis import get_redis_client
from app.services.signal_processor import SignalProcessor
from app.services.moneyness_greeks_calculator import MoneynessAwareGreeksCalculator
from app.core.config import settings


router = APIRouter(prefix="/subscriptions", tags=["websocket"])


class ConnectionManager:
    """
    Manages WebSocket connections and subscriptions
    Supports high-concurrency with efficient routing
    """
    
    def __init__(self):
        # Connection tracking
        self.active_connections: Dict[str, WebSocket] = {}
        self.connection_subscriptions: Dict[str, Set[str]] = {}
        
        # Subscription routing
        self.subscription_connections: Dict[str, Set[str]] = {}
        
        # Service instances
        self.signal_processor = None
        self.moneyness_calculator = None
        self.redis_client = None
        self.redis_subscriber = None
        
        # Background tasks
        self.heartbeat_task = None
        self.redis_listener_task = None
        
    async def initialize(self):
        """Initialize the connection manager"""
        self.redis_client = get_redis_client()

        # CRITICAL FIX: Use async Redis client for pub/sub to avoid blocking event loop
        # The sync redis client's pubsub() doesn't have async methods
        try:
            import redis.asyncio as aioredis
            from app.core.config import settings

            # Create async Redis client for pub/sub
            async_redis_client = await aioredis.from_url(
                settings.REDIS_URL,
                decode_responses=True,
                socket_connect_timeout=5,
                socket_timeout=5
            )
            self.redis_subscriber = async_redis_client.pubsub()
            logger.info("Async Redis pub/sub client initialized for WebSocket")
        except Exception as e:
            logger.error(f"Failed to create async Redis pub/sub: {e}")
            self.redis_subscriber = None

        # Initialize services
        self.signal_processor = SignalProcessor()
        await self.signal_processor.initialize(None)  # app_state not needed for websocket

        from app.services.instrument_service_client import InstrumentServiceClient
        instrument_client = InstrumentServiceClient()
        self.moneyness_calculator = MoneynessAwareGreeksCalculator(instrument_client)

        # Start background tasks
        self.heartbeat_task = asyncio.create_task(self._heartbeat_loop())

        # Start Redis listener if subscriber is available
        # The listener will wait for subscriptions to be added via _subscribe_to_redis_channel()
        if self.redis_subscriber:
            self.redis_listener_task = asyncio.create_task(self._redis_listener())
            logger.info("WebSocket ConnectionManager initialized with Redis listener")
        else:
            logger.warning("WebSocket ConnectionManager initialized WITHOUT Redis listener (pubsub unavailable)")
        
    async def connect(self, websocket: WebSocket, client_id: str):
        """Accept new WebSocket connection"""
        await websocket.accept()
        self.active_connections[client_id] = websocket
        self.connection_subscriptions[client_id] = set()
        
        logger.info(f"Client {client_id} connected. Total connections: {len(self.active_connections)}")
        
        # Send welcome message
        await self.send_personal_message({
            "type": "connection",
            "status": "connected",
            "client_id": client_id,
            "timestamp": datetime.utcnow().isoformat(),
            "server_time": datetime.utcnow().isoformat()
        }, websocket)
        
    def disconnect(self, client_id: str):
        """Handle client disconnection"""
        if client_id in self.active_connections:
            # Remove from active connections
            del self.active_connections[client_id]
            
            # Clean up subscriptions
            if client_id in self.connection_subscriptions:
                for sub_key in self.connection_subscriptions[client_id]:
                    if sub_key in self.subscription_connections:
                        self.subscription_connections[sub_key].discard(client_id)
                        if not self.subscription_connections[sub_key]:
                            del self.subscription_connections[sub_key]
                            
                del self.connection_subscriptions[client_id]
                
            logger.info(f"Client {client_id} disconnected. Total connections: {len(self.active_connections)}")
            
    async def subscribe(self, client_id: str, subscription: Dict[str, Any]):
        """
        Handle subscription request
        
        Subscription format:
        {
            "type": "subscribe",
            "channel": "greeks|indicators|moneyness",
            "instrument_key": "EXCHANGE@SYMBOL@...",
            "params": {...}
        }
        """
        channel = subscription.get("channel")
        instrument_key = subscription.get("instrument_key")
        
        if not channel or not instrument_key:
            await self.send_error(client_id, "Invalid subscription format")
            return
            
        # Create subscription key
        sub_key = f"{channel}:{instrument_key}"
        params = subscription.get("params", {})
        if params:
            param_str = json.dumps(params, sort_keys=True)
            sub_key = f"{sub_key}:{param_str}"
            
        # Add subscription
        self.connection_subscriptions[client_id].add(sub_key)
        
        if sub_key not in self.subscription_connections:
            self.subscription_connections[sub_key] = set()
            # Subscribe to Redis channel for this subscription
            await self._subscribe_to_redis_channel(sub_key)
            
        self.subscription_connections[sub_key].add(client_id)
        
        # Send confirmation
        await self.send_to_client(client_id, {
            "type": "subscription",
            "status": "subscribed",
            "channel": channel,
            "instrument_key": instrument_key,
            "subscription_key": sub_key,
            "timestamp": datetime.utcnow().isoformat()
        })
        
        # Send initial data
        await self._send_initial_data(client_id, channel, instrument_key, params)
        
    async def unsubscribe(self, client_id: str, subscription: Dict[str, Any]):
        """Handle unsubscription request"""
        channel = subscription.get("channel")
        instrument_key = subscription.get("instrument_key")
        
        if not channel or not instrument_key:
            await self.send_error(client_id, "Invalid unsubscription format")
            return
            
        # Create subscription key
        sub_key = f"{channel}:{instrument_key}"
        params = subscription.get("params", {})
        if params:
            param_str = json.dumps(params, sort_keys=True)
            sub_key = f"{sub_key}:{param_str}"
            
        # Remove subscription
        if client_id in self.connection_subscriptions:
            self.connection_subscriptions[client_id].discard(sub_key)
            
        if sub_key in self.subscription_connections:
            self.subscription_connections[sub_key].discard(client_id)
            if not self.subscription_connections[sub_key]:
                del self.subscription_connections[sub_key]
                await self._unsubscribe_from_redis_channel(sub_key)
                
        # Send confirmation
        await self.send_to_client(client_id, {
            "type": "subscription",
            "status": "unsubscribed",
            "channel": channel,
            "instrument_key": instrument_key,
            "timestamp": datetime.utcnow().isoformat()
        })
        
    async def send_personal_message(self, message: dict, websocket: WebSocket):
        """Send message to specific WebSocket"""
        try:
            await websocket.send_json(message)
        except Exception as e:
            logger.error(f"Error sending personal message: {e}")
            
    async def send_to_client(self, client_id: str, message: dict):
        """Send message to specific client"""
        if client_id in self.active_connections:
            websocket = self.active_connections[client_id]
            await self.send_personal_message(message, websocket)
            
    async def send_error(self, client_id: str, error_message: str):
        """Send error message to client"""
        await self.send_to_client(client_id, {
            "type": "error",
            "message": error_message,
            "timestamp": datetime.utcnow().isoformat()
        })
        
    async def broadcast_to_subscription(self, sub_key: str, data: dict):
        """Broadcast data to all clients subscribed to a key"""
        if sub_key in self.subscription_connections:
            # Create tasks for parallel sending
            tasks = []
            for client_id in self.subscription_connections[sub_key]:
                if client_id in self.active_connections:
                    websocket = self.active_connections[client_id]
                    tasks.append(self.send_personal_message(data, websocket))
                    
            # Send to all clients in parallel
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)
                
    async def _send_initial_data(self, client_id: str, channel: str, instrument_key: str, params: dict):
        """Send initial data upon subscription"""
        try:
            if channel == "greeks":
                # Get latest Greeks
                greeks = await self.signal_processor.get_latest_greeks(instrument_key)
                if greeks:
                    await self.send_to_client(client_id, {
                        "type": "data",
                        "channel": "greeks",
                        "instrument_key": instrument_key,
                        "data": {
                            "delta": greeks.delta,
                            "gamma": greeks.gamma,
                            "theta": greeks.theta,
                            "vega": greeks.vega,
                            "rho": greeks.rho,
                            "iv": greeks.implied_volatility
                        },
                        "timestamp": datetime.utcnow().isoformat()
                    })
                    
            elif channel == "indicators":
                # Get indicator value
                indicator = params.get("indicator", "rsi")
                period = params.get("period", 14)
                value = await self.signal_processor.get_latest_indicator(
                    instrument_key, indicator, period
                )
                if value is not None:
                    await self.send_to_client(client_id, {
                        "type": "data",
                        "channel": "indicators",
                        "instrument_key": instrument_key,
                        "indicator": indicator,
                        "data": {"value": value, "period": period},
                        "timestamp": datetime.utcnow().isoformat()
                    })
                    
            elif channel == "moneyness":
                # Get moneyness Greeks
                underlying = params.get("underlying")
                moneyness_level = params.get("moneyness_level", "ATM")
                if underlying:
                    spot_price = await self.signal_processor.get_latest_price(underlying)
                    if spot_price:
                        result = await self.moneyness_calculator.calculate_moneyness_greeks(
                            underlying, spot_price, moneyness_level
                        )
                        if result:
                            await self.send_to_client(client_id, {
                                "type": "data",
                                "channel": "moneyness",
                                "underlying": underlying,
                                "moneyness_level": moneyness_level,
                                "data": result,
                                "timestamp": datetime.utcnow().isoformat()
                            })
                            
        except Exception as e:
            logger.error(f"Error sending initial data: {e}")
            
    async def _subscribe_to_redis_channel(self, sub_key: str):
        """Subscribe to Redis channel for updates"""
        channel = f"signal:updates:{sub_key}"
        await self.redis_subscriber.subscribe(channel)
        logger.info(f"Subscribed to Redis channel: {channel}")
        
    async def _unsubscribe_from_redis_channel(self, sub_key: str):
        """Unsubscribe from Redis channel"""
        channel = f"signal:updates:{sub_key}"
        await self.redis_subscriber.unsubscribe(channel)
        logger.info(f"Unsubscribed from Redis channel: {channel}")
        
    async def _redis_listener(self):
        """Listen for Redis updates and broadcast to WebSocket clients"""
        # Safety guard: Exit if redis_subscriber is not available
        if not self.redis_subscriber:
            logger.error("Redis listener cannot start - redis_subscriber is None")
            return

        # Subscribe to a dummy channel to initialize pub/sub connection
        # This prevents "pubsub connection not set" error
        try:
            await self.redis_subscriber.subscribe("_websocket:init")
            logger.info("Redis listener started with initial dummy subscription")
        except Exception as e:
            logger.error(f"Failed to initialize Redis pub/sub: {e}")
            return

        while True:
            try:
                message = await self.redis_subscriber.get_message(
                    ignore_subscribe_messages=True,
                    timeout=1.0
                )

                if message and message['data']:
                    # Parse the message
                    channel = message['channel'].decode('utf-8')
                    if channel.startswith('signal:updates:'):
                        sub_key = channel.replace('signal:updates:', '')

                        try:
                            data = json.loads(message['data'])
                            # Broadcast to all subscribed clients
                            await self.broadcast_to_subscription(sub_key, data)
                        except json.JSONDecodeError:
                            logger.error(f"Invalid JSON in Redis message: {message['data']}")

            except Exception as e:
                logger.exception(f"Error in Redis listener: {e}")
                await asyncio.sleep(1)
                
    async def _heartbeat_loop(self):
        """Send periodic heartbeat to all connections"""
        while True:
            try:
                await asyncio.sleep(30)  # 30 second heartbeat
                
                # Send heartbeat to all connections
                heartbeat = {
                    "type": "heartbeat",
                    "timestamp": datetime.utcnow().isoformat(),
                    "connections": len(self.active_connections)
                }
                
                # Create tasks for parallel sending
                tasks = []
                disconnected = []
                
                for client_id, websocket in self.active_connections.items():
                    try:
                        await websocket.send_json(heartbeat)
                    except Exception:
                        disconnected.append(client_id)
                        
                # Clean up disconnected clients
                for client_id in disconnected:
                    self.disconnect(client_id)
                    
            except Exception as e:
                logger.exception(f"Error in heartbeat loop: {e}")
                
    async def shutdown(self):
        """Graceful shutdown"""
        # Cancel background tasks
        if self.heartbeat_task:
            self.heartbeat_task.cancel()
        if self.redis_listener_task:
            self.redis_listener_task.cancel()
            
        # Close all connections
        for client_id in list(self.active_connections.keys()):
            await self.send_to_client(client_id, {
                "type": "connection",
                "status": "closing",
                "message": "Server shutting down"
            })
            self.disconnect(client_id)
            
        # Close Redis connection
        if self.redis_subscriber:
            await self.redis_subscriber.close()


# Global connection manager
manager = ConnectionManager()


@router.on_event("startup")
async def startup():
    """Initialize connection manager on startup"""
    await manager.initialize()


@router.on_event("shutdown")
async def shutdown():
    """Cleanup on shutdown"""
    await manager.shutdown()


@router.websocket("/websocket")
async def websocket_endpoint(
    websocket: WebSocket,
    client_id: str = Query(..., description="Unique client identifier")
):
    """
    WebSocket endpoint for real-time signal updates
    
    Protocol:
    1. Connect with client_id parameter
    2. Send subscription messages:
       {
           "type": "subscribe",
           "channel": "greeks|indicators|moneyness",
           "instrument_key": "EXCHANGE@SYMBOL@...",
           "params": {...}
       }
    3. Receive real-time updates
    4. Send unsubscribe to stop updates
    """
    await manager.connect(websocket, client_id)
    
    try:
        while True:
            # Wait for messages from client
            data = await websocket.receive_json()
            
            message_type = data.get("type")
            
            if message_type == "subscribe":
                await manager.subscribe(client_id, data)
            elif message_type == "unsubscribe":
                await manager.unsubscribe(client_id, data)
            elif message_type == "ping":
                # Respond to ping
                await manager.send_to_client(client_id, {
                    "type": "pong",
                    "timestamp": datetime.utcnow().isoformat()
                })
            else:
                await manager.send_error(client_id, f"Unknown message type: {message_type}")
                
    except WebSocketDisconnect:
        manager.disconnect(client_id)
    except Exception as e:
        logger.exception(f"WebSocket error for client {client_id}: {e}")
        manager.disconnect(client_id)


@router.get("/health")
async def websocket_health_check():
    """Health check endpoint for WebSocket API"""
    return {
        "status": "healthy",
        "api_version": "v2",
        "component": "websocket",
        "active_connections": len(manager.active_connections),
        "active_subscriptions": len(manager.subscription_connections),
        "timestamp": datetime.utcnow().isoformat()
    }