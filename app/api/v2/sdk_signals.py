"""
SDK Signal Subscription API

Sprint 5A: Signal delivery endpoint for SDK integration
- Provides unified signal subscription interface
- Enforces entitlement checking via signal stream contract
- Routes signals from signal_service to SDK clients
"""
import asyncio
import json
from typing import Dict, List, Optional, Any, Set
from datetime import datetime
from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect, Query, Header
from pydantic import BaseModel, Field

from app.utils.logging_utils import log_info, log_error, log_exception
from app.services.signal_stream_contract import (
    SignalStreamContract, 
    StreamKeyFormat,
    SignalEntitlement,
    SignalType
)
from app.api.v2.websocket import ConnectionManager
from app.core.auth.gateway_trust import get_current_user_from_gateway

router = APIRouter(prefix="/sdk", tags=["sdk-signals"])

# Global connection manager instance
sdk_connection_manager: Optional[ConnectionManager] = None


async def _cache_subscription_metadata(connection_token: str, metadata: Dict[str, Any]) -> None:
    """
    Cache subscription metadata for a connection.
    
    Sprint 5A: Stores subscription metadata with 24-hour TTL for watermarking.
    
    Args:
        connection_token: SDK connection token
        metadata: Metadata to cache including user_id, marketplace info
    """
    from app.core.cache import get_cache
    cache = await get_cache()
    await cache.set(
        f"sdk_connection_metadata:{connection_token}",
        metadata,
        expire=86400  # 24 hour TTL
    )


class SignalSubscriptionRequest(BaseModel):
    """Request to subscribe to signals."""
    instrument: str = Field(..., description="Instrument to subscribe (e.g., SYMBOL)")
    signal_types: List[str] = Field(
        default=["common"], 
        description="Signal types to subscribe: public, common, marketplace, personal"
    )
    execution_token: Optional[str] = Field(
        None, 
        description="Marketplace execution token for premium signals"
    )
    indicators: Optional[List[str]] = Field(
        None,
        description="Specific indicators to subscribe (defaults to common set)"
    )
    product_id: Optional[str] = Field(
        None,
        description="Marketplace product ID for premium signals"
    )
    personal_signal_id: Optional[str] = Field(
        None,
        description="Personal signal ID for custom signals"
    )


class SignalSubscriptionResponse(BaseModel):
    """Response for signal subscription."""
    success: bool
    stream_keys: List[str] = Field(default_factory=list)
    allowed_streams: List[str] = Field(default_factory=list)
    denied_streams: List[Dict[str, str]] = Field(default_factory=list)
    websocket_url: str
    connection_token: Optional[str] = None


async def get_sdk_connection_manager() -> ConnectionManager:
    """Get or create SDK connection manager."""
    global sdk_connection_manager
    if not sdk_connection_manager:
        sdk_connection_manager = ConnectionManager()
        await sdk_connection_manager.initialize()
    return sdk_connection_manager


@router.post("/signals/subscribe", response_model=SignalSubscriptionResponse)
async def subscribe_to_signals(
    request: SignalSubscriptionRequest,
    authorization: Optional[str] = Header(None),
    x_user_id: Optional[str] = Header(None, alias="X-User-ID"),
    x_gateway_secret: Optional[str] = Header(None, alias="X-Gateway-Secret")
) -> SignalSubscriptionResponse:
    """
    Sprint 5A: Subscribe to signal streams via SDK.
    
    Creates stream keys based on requested signal types and validates
    entitlements before returning WebSocket connection info.
    
    Supports both JWT (Authorization header) and gateway auth (X-User-ID + X-Gateway-Secret).
    """
    try:
        # Extract user info - support both JWT and gateway auth
        user_info = await get_current_user_from_gateway(x_user_id, x_gateway_secret, authorization)
        user_id = str(user_info.get("user_id", user_info.get("id")))
        
        # Initialize signal stream contract with marketplace client
        from app.services.marketplace_client import create_marketplace_client
        marketplace_client = create_marketplace_client()
        signal_contract = SignalStreamContract(marketplace_client=marketplace_client)
        
        # Generate stream keys based on request
        stream_keys = []
        allowed_streams = []
        denied_streams = []
        
        instruments = [request.instrument]  # Can be extended to multiple
        
        for signal_type in request.signal_types:
            if signal_type == "public":
                # Add public streams
                public_keys = signal_contract.get_public_streams(instruments)
                stream_keys.extend(public_keys)
                allowed_streams.extend(public_keys)  # Public always allowed
                
            elif signal_type == "common":
                # Add common indicator streams
                if request.indicators:
                    # Specific indicators requested
                    for indicator in request.indicators:
                        key = StreamKeyFormat.create_common_key(
                            request.instrument, 
                            indicator.lower()
                        )
                        stream_keys.append(key)
                        
                        # Check if indicator is in common set
                        if indicator.lower() in SignalStreamContract.COMMON_INDICATORS:
                            allowed_streams.append(key)
                        else:
                            denied_streams.append({
                                "stream_key": key,
                                "reason": f"Not a common indicator: {indicator}"
                            })
                else:
                    # Default common streams
                    common_keys = signal_contract.get_common_streams(instruments)
                    stream_keys.extend(common_keys)
                    allowed_streams.extend(common_keys)  # Common always allowed
                    
            elif signal_type == "marketplace" and request.product_id:
                # Get dynamic marketplace signals from product metadata
                subscription_id = None
                try:
                    # First, get user's subscription to find subscription_id
                    user_subs_response = await marketplace_client.get_user_subscriptions(user_id)
                    user_subscriptions = user_subs_response.get("subscriptions", [])
                    
                    # Find subscription for this product
                    for sub in user_subscriptions:
                        if sub.get("product_id") == request.product_id and sub.get("status") == "active":
                            subscription_id = sub.get("subscription_id")
                            break
                    
                    # Then get product signals
                    product_signals_response = await marketplace_client.get_product_signals(
                        request.product_id, user_id, request.execution_token
                    )
                    marketplace_signals = []
                    for signal_group in product_signals_response.get("signals", []):
                        marketplace_signals.extend(signal_group.get("indicators", []))
                    
                    # Fallback: Extract subscription_id from the response if available
                    if not subscription_id:
                        subscription_id = product_signals_response.get("subscription_id")
                    
                    # If product has no signals defined, return empty list
                    if not marketplace_signals:
                        marketplace_signals = []
                        
                except Exception as e:
                    log_error(f"Failed to fetch marketplace signals for product {request.product_id}: {e}")
                    # No fallback - return empty list on error to avoid hardcoded behavior
                    marketplace_signals = []
                
                for signal in marketplace_signals:
                    key = StreamKeyFormat.create_marketplace_key(
                        request.product_id,
                        request.instrument,
                        signal
                    )
                    stream_keys.append(key)
                    
                    # Check entitlement
                    entitlement = await signal_contract.check_entitlement(
                        key, user_id, request.execution_token
                    )
                    
                    if entitlement.is_allowed:
                        allowed_streams.append(key)
                        # Store metadata for watermarking
                        if subscription_id:
                            if not hasattr(request, '_marketplace_metadata'):
                                request._marketplace_metadata = {}
                            request._marketplace_metadata[key] = {
                                "subscription_id": subscription_id,
                                "product_id": request.product_id,
                                "signal_id": signal
                            }
                    else:
                        denied_streams.append({
                            "stream_key": key,
                            "reason": entitlement.reason or "No marketplace access"
                        })
                        
            elif signal_type == "personal" and request.personal_signal_id:
                # Add personal signal stream
                key = StreamKeyFormat.create_personal_key(
                    user_id,
                    request.personal_signal_id,
                    request.instrument
                )
                stream_keys.append(key)
                
                # Personal signals always allowed for owner
                allowed_streams.append(key)
        
        # Generate connection token for WebSocket auth
        connection_token = f"sdk_{user_id}_{int(datetime.utcnow().timestamp())}"
        
        # Store subscription metadata in cache for the WebSocket to retrieve
        # This includes subscription_id and product_id for watermarking
        marketplace_metadata = {}
        if hasattr(request, '_marketplace_metadata'):
            marketplace_metadata = request._marketplace_metadata
        
        # Cache the metadata keyed by connection token
        await _cache_subscription_metadata(
            connection_token,
            {
                "user_id": user_id,
                "marketplace_metadata": marketplace_metadata,  
                "execution_token": request.execution_token
            }
        )
        
        # Prepare WebSocket URL
        websocket_url = f"/api/v2/signals/sdk/ws?token={connection_token}"
        
        log_info(
            f"SDK signal subscription for user {user_id}: "
            f"{len(allowed_streams)} allowed, {len(denied_streams)} denied"
        )
        
        return SignalSubscriptionResponse(
            success=True,
            stream_keys=stream_keys,
            allowed_streams=allowed_streams,
            denied_streams=denied_streams,
            websocket_url=websocket_url,
            connection_token=connection_token
        )
        
    except Exception as e:
        log_error(f"Error in SDK signal subscription: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.websocket("/ws")
async def sdk_websocket_endpoint(
    websocket: WebSocket,
    token: str = Query(..., description="Connection token from subscribe endpoint")
):
    """
    Sprint 5A: WebSocket endpoint for SDK signal streaming.
    
    Streams real-time signals to SDK clients based on their subscriptions
    and entitlements. Bridges stream keys to actual signal data.
    """
    client_id = f"sdk_{token}"
    manager = await get_sdk_connection_manager()
    
    # Store client's allowed streams (populated from subscription response)
    client_allowed_streams = set()
    client_entitlements = {}  # stream_key -> entitlement info
    
    try:
        # Connect client
        await manager.connect(websocket, client_id)
        
        # Parse token to get user_id and validate
        # Token format: sdk_<user_id>_<timestamp>
        parts = token.split("_")
        if len(parts) >= 3 and parts[0] == "sdk":
            user_id = parts[1]
            
            # Retrieve subscription metadata from cache
            from app.core.cache import get_cache
            cache = await get_cache()
            cached_metadata = await cache.get(f"sdk_connection_metadata:{token}")
            
            # Store user metadata for watermarking
            if client_id not in manager.connection_metadata:
                manager.connection_metadata[client_id] = {}
            
            base_metadata = {
                "user_id": user_id,
                "connection_type": "sdk",
                "token": token
            }
            
            # Add marketplace metadata if available
            if cached_metadata:
                base_metadata["marketplace_metadata"] = cached_metadata.get("marketplace_metadata", {})
                base_metadata["execution_token"] = cached_metadata.get("execution_token")
            
            manager.connection_metadata[client_id].update(base_metadata)
        else:
            await websocket.send_json({
                "type": "error",
                "message": "Invalid connection token"
            })
            await websocket.close()
            return
        
        # Optionally, fetch allowed streams from the initial subscription response
        # This would be passed via query params or fetched from cache
        # For now, entitlements are checked on each subscribe request
        
        while True:
            # Receive messages from client
            data = await websocket.receive_text()
            message = json.loads(data)
            
            message_type = message.get("type")
            
            if message_type == "subscribe":
                # Handle SDK stream key subscription
                stream_keys = message.get("stream_keys", [])
                if not stream_keys:
                    await websocket.send_json({
                        "type": "error",
                        "message": "No stream_keys provided"
                    })
                    continue
                
                # Get execution token if provided for marketplace streams
                execution_token = message.get("execution_token")
                # Stream-specific tokens can be provided as a dict
                stream_tokens = message.get("stream_tokens", {})
                
                # Update connection metadata with execution token for watermarking
                if execution_token and client_id in manager.connection_metadata:
                    manager.connection_metadata[client_id]["execution_token"] = execution_token
                
                # Also add stream-specific tokens to metadata
                if stream_tokens and client_id in manager.connection_metadata:
                    if "stream_tokens" not in manager.connection_metadata[client_id]:
                        manager.connection_metadata[client_id]["stream_tokens"] = {}
                    manager.connection_metadata[client_id]["stream_tokens"].update(stream_tokens)
                
                # Bridge stream keys to WebSocket channels with entitlement check
                from app.services.marketplace_client import create_marketplace_client
                marketplace_client = create_marketplace_client()
                signal_contract = SignalStreamContract(marketplace_client=marketplace_client)
                
                for stream_key in stream_keys:
                    # Check if client is entitled to this stream
                    if stream_key not in client_allowed_streams:
                        # Get token for this stream (specific token takes precedence)
                        stream_execution_token = stream_tokens.get(stream_key, execution_token)
                        
                        # Validate entitlement
                        entitlement = await signal_contract.check_entitlement(
                            stream_key, 
                            user_id,
                            execution_token=stream_execution_token
                        )
                        
                        if not entitlement.is_allowed:
                            await websocket.send_json({
                                "type": "subscription_denied",
                                "stream_key": stream_key,
                                "reason": entitlement.reason or "Not authorized for this stream"
                            })
                            continue
                        
                        # Cache entitlement for this session
                        client_allowed_streams.add(stream_key)
                        client_entitlements[stream_key] = {
                            "signal_type": entitlement.signal_type,
                            "execution_token": stream_execution_token
                        }
                    
                    # Parse stream key to determine channel and params
                    parsed = StreamKeyFormat.parse_key(stream_key)
                    if not parsed:
                        continue
                    
                    # Map to WebSocket subscription format based on available channels
                    # The ConnectionManager supports: greeks, indicators, moneyness
                    if parsed["type"] == "public" and parsed["indicator"] == "price":
                        # Price is a special "indicator" that tracks last traded price
                        # Route through indicators channel with price as the indicator
                        sub_message = {
                            "type": "subscribe",
                            "channel": "indicators",
                            "instrument_key": parsed["instrument"],
                            "params": {
                                "indicator": "price",  # Special indicator for LTP
                                **parsed.get("params", {})
                            }
                        }
                    elif parsed["type"] in ["public", "common"]:
                        # Technical indicators - supported by ConnectionManager
                        sub_message = {
                            "type": "subscribe",
                            "channel": "indicators",
                            "instrument_key": parsed["instrument"],
                            "params": {
                                "indicator": parsed["indicator"],
                                **parsed.get("params", {})
                            }
                        }
                    elif parsed["indicator"] in ["delta", "gamma", "theta", "vega", "rho", "iv"]:
                        # Greeks - supported by ConnectionManager
                        sub_message = {
                            "type": "subscribe",
                            "channel": "greeks",
                            "instrument_key": parsed["instrument"],
                            "params": parsed.get("params", {})
                        }
                    elif parsed["type"] == "marketplace":
                        # Premium signals - use marketplace channel to trigger watermarking
                        sub_message = {
                            "type": "subscribe",
                            "channel": "marketplace",
                            "instrument_key": parsed["instrument"],
                            "params": {
                                "signal": parsed["signal"],
                                "product_id": parsed["product_id"],
                                "stream_key": stream_key,  # Preserve original stream key for watermarking
                                **parsed.get("params", {})
                            }
                        }
                    elif parsed["type"] == "personal":
                        # Personal signals - map to indicators channel with special params
                        sub_message = {
                            "type": "subscribe", 
                            "channel": "indicators",
                            "instrument_key": parsed["instrument"],
                            "params": {
                                "indicator": f"personal_{parsed['signal_id']}",
                                "user_id": parsed["user_id"],
                                **parsed.get("params", {})
                            }
                        }
                    else:
                        logger.warning(f"Unsupported stream key type: {parsed['type']}")
                        continue
                    
                    # Forward to actual subscription handler
                    await manager.subscribe(client_id, sub_message)
                    
                    # Already tracked in entitlement check above
                
                # Send confirmation with stream keys
                await websocket.send_json({
                    "type": "subscription",
                    "status": "subscribed", 
                    "stream_keys": list(client_allowed_streams),
                    "timestamp": datetime.utcnow().isoformat()
                })
                
            elif message_type == "unsubscribe":
                stream_keys = message.get("stream_keys", [])
                for stream_key in stream_keys:
                    client_allowed_streams.discard(stream_key)
                    
            elif message_type == "ping":
                # Respond to ping
                await websocket.send_json({
                    "type": "pong",
                    "timestamp": datetime.utcnow().isoformat()
                })
                
            else:
                await websocket.send_json({
                    "type": "error",
                    "message": f"Unknown message type: {message_type}"
                })
                
    except WebSocketDisconnect:
        manager.disconnect(client_id)
        log_info(f"SDK client {client_id} disconnected")
    except Exception as e:
        log_exception(f"Error in SDK WebSocket: {e}")
        manager.disconnect(client_id)


@router.get("/signals/streams")
async def list_available_streams(
    signal_type: Optional[str] = Query(None, description="Filter by signal type"),
    instruments: Optional[List[str]] = Query(None, description="Instruments to get signals for"),
    authorization: Optional[str] = Header(None),
    x_user_id: Optional[str] = Header(None, alias="X-User-ID"),
    x_gateway_secret: Optional[str] = Header(None, alias="X-Gateway-Secret")
) -> Dict[str, Any]:
    """
    List available signal streams for the authenticated user.
    
    Returns categorized lists of streams the user can subscribe to.
    Sprint 5A: Real integration with marketplace and personal signals.
    """
    try:
        # Extract user info
        user_info = await get_current_user_from_gateway(x_user_id, x_gateway_secret, authorization)
        user_id = str(user_info.get("user_id", user_info.get("id")))
        
        signal_contract = SignalStreamContract()
        
        # Use provided instruments or fetch from user watchlist/preferences
        if not instruments:
            # Default instruments - in production, fetch from user preferences/watchlist
            instruments = ["SYMBOL1", "SYMBOL2", "SYMBOL3", "SYMBOL4", "SYMBOL5"]
        
        available_streams = {
            "public": signal_contract.get_public_streams(instruments),
            "common": signal_contract.get_common_streams(instruments),
            "marketplace": [],
            "personal": []
        }
        
        # Fetch marketplace signals
        try:
            from app.services.marketplace_client import create_marketplace_client
            marketplace_client = create_marketplace_client()
            
            # Get user's active subscriptions
            subscriptions_response = await marketplace_client.get_user_subscriptions(user_id)
            user_subscriptions = subscriptions_response.get("subscriptions", [])
            
            # Get available marketplace signals based on subscriptions
            for subscription in user_subscriptions:
                if subscription.get("status") == "active":
                    product_id = subscription.get("product_id")
                    product_signals = subscription.get("signals", [])
                    
                    # Create stream keys for each signal
                    for signal_info in product_signals:
                        signal_name = signal_info.get("name", "default")
                        signal_params = signal_info.get("default_params", {})
                        
                        # Add stream key for each instrument
                        for instrument in instruments:
                            stream_key = StreamKeyFormat.create_marketplace_key(
                                product_id=product_id,
                                instrument=instrument,
                                signal=signal_name,
                                params=signal_params
                            )
                            
                            available_streams["marketplace"].append({
                                "stream_key": stream_key,
                                "product_id": product_id,
                                "product_name": subscription.get("product_name"),
                                "signal_name": signal_name,
                                "instrument": instrument,
                                "subscription_id": subscription.get("subscription_id"),
                                "execution_token": subscription.get("execution_token")
                            })
        except Exception as e:
            log_error(f"Failed to fetch marketplace signals: {e}")
            # Continue without marketplace signals
        
        # Fetch personal signals
        try:
            # Import personal script service
            from algo_engine.app.services.personal_script_service import PersonalScriptService
            
            # List user's personal signal scripts
            personal_scripts = await PersonalScriptService.list_scripts(
                user_id=user_id,
                script_type="signal",
                limit=100
            )
            
            for script_info in personal_scripts:
                script_id = script_info.get("script_id")
                script_name = script_info.get("name", "Unnamed Signal")
                
                # Create stream keys for each instrument
                for instrument in instruments:
                    stream_key = StreamKeyFormat.create_personal_key(
                        user_id=user_id,
                        signal_id=script_id,
                        instrument=instrument,
                        params=None  # Personal signals may have dynamic params
                    )
                    
                    available_streams["personal"].append({
                        "stream_key": stream_key,
                        "script_id": script_id,
                        "script_name": script_name,
                        "instrument": instrument,
                        "owner_id": user_id
                    })
        except Exception as e:
            log_error(f"Failed to fetch personal signals: {e}")
            # Continue without personal signals
        
        # Filter by type if requested
        if signal_type and signal_type in available_streams:
            return {
                "signal_type": signal_type,
                "streams": available_streams[signal_type],
                "count": len(available_streams[signal_type])
            }
        
        # Return all streams with counts
        return {
            "streams": available_streams,
            "counts": {
                k: len(v) for k, v in available_streams.items()
            },
            "total": sum(len(v) for v in available_streams.values())
        }
        
    except Exception as e:
        log_error(f"Error listing streams: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/signals/validate-token")
async def validate_execution_token(
    execution_token: str = Query(..., description="Marketplace execution token"),
    product_id: str = Query(..., description="Marketplace product ID"),
    authorization: Optional[str] = Header(None),
    x_user_id: Optional[str] = Header(None, alias="X-User-ID"),
    x_gateway_secret: Optional[str] = Header(None, alias="X-Gateway-Secret")
) -> Dict[str, Any]:
    """
    Validate a marketplace execution token for signal access.
    
    Used by SDK to check if a token is valid before subscribing.
    Sprint 5A: Real marketplace integration.
    """
    try:
        # Extract user info
        user_info = await get_current_user_from_gateway(x_user_id, x_gateway_secret, authorization)
        user_id = str(user_info.get("user_id", user_info.get("id")))
        
        # Check with marketplace service
        from app.services.marketplace_client import create_marketplace_client
        marketplace_client = create_marketplace_client()
        
        validation_result = await marketplace_client.verify_execution_token(
            token=execution_token,
            product_id=product_id,
            user_id=user_id
        )
        
        return {
            "is_valid": validation_result.get("is_valid", False),
            "user_id": user_id,
            "product_id": product_id,
            "subscription_id": validation_result.get("subscription_id"),
            "expires_at": validation_result.get("expires_at", 
                datetime.utcnow().replace(hour=23, minute=59).isoformat())
        }
        
    except Exception as e:
        log_error(f"Error validating token: {e}")
        raise HTTPException(status_code=500, detail=str(e))