#!/usr/bin/env python3
"""
PythonSDK HTTP Client Middleware - Phase 1 Migration

SDK_002: Internal Token Resolution for HTTP Requests
- All API requests use instrument_key in request body/params
- Internal token resolution via middleware
- Broker tokens never exposed in request/response logs
"""

import asyncio
import logging
import json
from typing import Dict, Any, List, Optional, Union, AsyncIterator
from datetime import datetime
import aiohttp
from app.sdk.instrument_client import InstrumentClient, create_instrument_client

logger = logging.getLogger(__name__)

class HTTPClientConfig:
    """Configuration for HTTP client with registry integration"""
    
    def __init__(self, 
                 base_url: str = "http://localhost:8080",
                 default_timeout: int = 30,
                 max_retries: int = 3,
                 enable_token_resolution: bool = True):
        self.base_url = base_url
        self.default_timeout = default_timeout
        self.max_retries = max_retries
        self.enable_token_resolution = enable_token_resolution

class TokenResolutionMiddleware:
    """
    Middleware for internal token resolution in HTTP requests
    
    SDK_002: Automatically resolves instrument_key to broker tokens
    before making HTTP requests to backend services.
    """
    
    def __init__(self, instrument_client: InstrumentClient):
        self.instrument_client = instrument_client
        self._resolution_cache = {}  # Cache for resolved tokens
    
    async def process_request(self, 
                            method: str, 
                            url: str,
                            data: Optional[Dict[str, Any]] = None,
                            params: Optional[Dict[str, Any]] = None,
                            headers: Optional[Dict[str, str]] = None,
                            broker_id: str = "default") -> Dict[str, Any]:
        """
        Process outgoing request to resolve instrument_key to tokens
        
        Args:
            method: HTTP method
            url: Request URL
            data: Request body data
            params: Query parameters
            headers: HTTP headers
            broker_id: Target broker for token resolution
            
        Returns:
            Dict: Processed request parameters with resolved tokens
        """
        processed_data = data.copy() if data else {}
        processed_params = params.copy() if params else {}
        processed_headers = headers.copy() if headers else {}
        
        # Add metadata for request tracking
        processed_headers["X-SDK-Phase"] = "1.0-instrument-key-first"
        processed_headers["X-Token-Resolution"] = "enabled"
        
        # Look for instrument_key in request data and resolve to tokens
        if data and "instrument_key" in data:
            instrument_key = data["instrument_key"]
            try:
                # Resolve to broker token internally
                broker_token = await self.instrument_client.resolve_broker_token(
                    instrument_key, broker_id
                )
                
                # Replace instrument_key with internal token for backend
                processed_data["_internal_token"] = broker_token
                processed_data["_original_instrument_key"] = instrument_key
                
                # Remove instrument_key from request to backend
                # Backend will use _internal_token for broker operations
                del processed_data["instrument_key"]
                
                logger.debug(f"Resolved {instrument_key} -> {broker_token[:8]}*** for {method} {url}")
                
            except Exception as e:
                logger.error(f"Token resolution failed for {instrument_key}: {e}")
                # Keep original request format and let backend handle error
                processed_data["_resolution_error"] = str(e)
        
        # Similar processing for query parameters
        if params and "instrument_key" in params:
            instrument_key = params["instrument_key"]
            try:
                broker_token = await self.instrument_client.resolve_broker_token(
                    instrument_key, broker_id
                )
                processed_params["_internal_token"] = broker_token
                processed_params["_original_instrument_key"] = instrument_key
                del processed_params["instrument_key"]
                
            except Exception as e:
                logger.error(f"Token resolution failed in params for {instrument_key}: {e}")
                processed_params["_resolution_error"] = str(e)
        
        return {
            "data": processed_data,
            "params": processed_params,
            "headers": processed_headers
        }
    
    async def process_response(self, 
                             response_data: Dict[str, Any],
                             original_request: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process incoming response to restore instrument_key and enrich metadata
        
        Args:
            response_data: Response from backend service
            original_request: Original request data for context
            
        Returns:
            Dict: Processed response with instrument_key and metadata
        """
        processed_response = response_data.copy()
        
        # Restore instrument_key from internal tracking
        if "_original_instrument_key" in original_request.get("data", {}):
            original_key = original_request["data"]["_original_instrument_key"]
            
            # Add instrument_key back to response
            if "instrument" in processed_response:
                processed_response["instrument"]["instrument_key"] = original_key
            else:
                processed_response["instrument_key"] = original_key
            
            # Add enriched metadata from registry
            try:
                metadata = await self.instrument_client.get_instrument_metadata(original_key)
                processed_response["metadata"] = {
                    "symbol": metadata.symbol,
                    "exchange": metadata.exchange,
                    "sector": metadata.sector,
                    "instrument_type": metadata.instrument_type,
                    "lot_size": metadata.lot_size,
                    "tick_size": metadata.tick_size
                }
                
            except Exception as e:
                logger.warning(f"Failed to enrich response metadata for {original_key}: {e}")
        
        # Remove internal fields from response
        for internal_field in ["_internal_token", "_broker_data", "_resolution_error"]:
            if internal_field in processed_response:
                del processed_response[internal_field]
        
        return processed_response

class InstrumentHTTPClient:
    """
    HTTP Client with automatic instrument_key resolution
    
    SDK_002: All HTTP requests automatically resolve instrument_key
    to appropriate broker tokens before sending to backend services.
    """
    
    def __init__(self, 
                 config: HTTPClientConfig = None,
                 instrument_client: Optional[InstrumentClient] = None):
        """
        Initialize HTTP client with token resolution capability
        
        Args:
            config: HTTP client configuration
            instrument_client: Client for token resolution
        """
        self.config = config or HTTPClientConfig()
        self.instrument_client = instrument_client or create_instrument_client()
        self.middleware = TokenResolutionMiddleware(self.instrument_client)
        self._session: Optional[aiohttp.ClientSession] = None
    
    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create HTTP session"""
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=self.config.default_timeout)
            self._session = aiohttp.ClientSession(timeout=timeout)
        return self._session
    
    async def close(self):
        """Close HTTP session"""
        if self._session and not self._session.closed:
            await self._session.close()
    
    async def post(self, 
                  endpoint: str,
                  data: Dict[str, Any],
                  broker_id: str = "default",
                  **kwargs) -> Dict[str, Any]:
        """
        POST request with automatic token resolution
        
        Args:
            endpoint: API endpoint (e.g., "/api/v1/orders")
            data: Request data containing instrument_key
            broker_id: Target broker for token resolution
            **kwargs: Additional request parameters
            
        Returns:
            Dict: Response with enriched metadata
        """
        url = f"{self.config.base_url}{endpoint}"
        
        # Process request through middleware
        processed = await self.middleware.process_request(
            method="POST", 
            url=url,
            data=data,
            broker_id=broker_id,
            **kwargs
        )
        
        session = await self._get_session()
        
        try:
            async with session.post(
                url,
                json=processed["data"],
                headers=processed["headers"]
            ) as response:
                
                if response.status >= 400:
                    error_text = await response.text()
                    logger.error(f"HTTP {response.status}: {error_text}")
                    raise aiohttp.ClientError(f"HTTP {response.status}: {error_text}")
                
                response_data = await response.json()
                
                # Process response through middleware
                processed_response = await self.middleware.process_response(
                    response_data, processed
                )
                
                logger.debug(f"POST {endpoint} completed successfully")
                return processed_response
                
        except Exception as e:
            logger.error(f"POST {endpoint} failed: {e}")
            raise
    
    async def get(self,
                 endpoint: str,
                 params: Optional[Dict[str, Any]] = None,
                 broker_id: str = "default",
                 **kwargs) -> Dict[str, Any]:
        """
        GET request with automatic token resolution
        
        Args:
            endpoint: API endpoint
            params: Query parameters containing instrument_key
            broker_id: Target broker for token resolution
            **kwargs: Additional request parameters
            
        Returns:
            Dict: Response with enriched metadata
        """
        url = f"{self.config.base_url}{endpoint}"
        
        # Process request through middleware
        processed = await self.middleware.process_request(
            method="GET",
            url=url,
            params=params,
            broker_id=broker_id,
            **kwargs
        )
        
        session = await self._get_session()
        
        try:
            async with session.get(
                url,
                params=processed["params"],
                headers=processed["headers"]
            ) as response:
                
                if response.status >= 400:
                    error_text = await response.text()
                    raise aiohttp.ClientError(f"HTTP {response.status}: {error_text}")
                
                response_data = await response.json()
                
                # Process response through middleware
                processed_response = await self.middleware.process_response(
                    response_data, processed
                )
                
                logger.debug(f"GET {endpoint} completed successfully")
                return processed_response
                
        except Exception as e:
            logger.error(f"GET {endpoint} failed: {e}")
            raise
    
    async def stream_get(self,
                        endpoint: str,
                        params: Optional[Dict[str, Any]] = None,
                        broker_id: str = "default") -> AsyncIterator[Dict[str, Any]]:
        """
        Streaming GET request with token resolution
        
        Args:
            endpoint: Streaming endpoint
            params: Parameters containing instrument_key
            broker_id: Target broker for token resolution
            
        Yields:
            Dict: Streaming responses with metadata
        """
        url = f"{self.config.base_url}{endpoint}"
        
        processed = await self.middleware.process_request(
            method="GET",
            url=url,
            params=params,
            broker_id=broker_id
        )
        
        session = await self._get_session()
        
        try:
            async with session.get(
                url,
                params=processed["params"],
                headers=processed["headers"]
            ) as response:
                
                if response.status >= 400:
                    error_text = await response.text()
                    raise aiohttp.ClientError(f"HTTP {response.status}: {error_text}")
                
                async for line in response.content:
                    if line:
                        try:
                            data = json.loads(line.decode().strip())
                            
                            # Process each streaming response
                            processed_data = await self.middleware.process_response(
                                data, processed
                            )
                            
                            yield processed_data
                            
                        except json.JSONDecodeError:
                            logger.warning(f"Failed to parse streaming data: {line}")
                            continue
                            
        except Exception as e:
            logger.error(f"Streaming GET {endpoint} failed: {e}")
            raise

# Factory function
def create_http_client(base_url: str = "http://localhost:8080") -> InstrumentHTTPClient:
    """
    Create HTTP client with automatic token resolution
    
    Args:
        base_url: Base URL for API requests
        
    Returns:
        InstrumentHTTPClient: Ready-to-use client
    """
    config = HTTPClientConfig(base_url=base_url)
    return InstrumentHTTPClient(config)