"""
Rate Limiting Middleware for Signal Service
Implements per-user and global rate limiting
"""
import time
import asyncio
from typing import Dict, Optional, Tuple
from fastapi import Request, Response, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp
import json

from app.utils.redis import get_redis_client
import logging
log_info = logging.getLogger(__name__).info
log_warning = logging.getLogger(__name__).warning
log_error = logging.getLogger(__name__).error
from app.core.config import settings


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Rate limiting middleware with Redis backend
    Supports per-user and global rate limits
    """
    
    def __init__(self, app: ASGIApp):
        super().__init__(app)
        self.redis_client = None
        self.global_limit = settings.API_V2_RATE_LIMIT  # requests per minute
        self.user_limit = 100  # requests per minute per user
        self.window_seconds = 60  # 1 minute window
        
        # Endpoint-specific limits (requests per minute)
        self.endpoint_limits = {
            "/api/v2/signals/realtime/greeks": 200,
            "/api/v2/signals/realtime/indicators": 200,
            "/api/v2/signals/realtime/moneyness": 100,
            "/api/v2/signals/historical": 50,
            "/api/v2/signals/subscriptions/websocket": 10
        }
        
        # Excluded paths
        self.excluded_paths = {
            "/health", "/ready", "/metrics", "/docs", "/openapi.json", "/"
        }
        
    async def dispatch(self, request: Request, call_next):
        """Process request with rate limiting"""
        # Initialize Redis client if needed
        if not self.redis_client:
            self.redis_client = await get_redis_client()
            
        # Skip rate limiting for excluded paths
        if request.url.path in self.excluded_paths:
            return await call_next(request)
            
        # Get rate limit key and limits
        user_id = self._get_user_id(request)
        endpoint_key = self._get_endpoint_key(request.url.path)
        
        # Check rate limits
        try:
            # Check user-specific limit
            if user_id:
                user_allowed, user_remaining = await self._check_rate_limit(
                    f"ratelimit:user:{user_id}",
                    self.user_limit
                )
                if not user_allowed:
                    return self._rate_limit_exceeded_response(user_remaining)
                    
            # Check endpoint-specific limit
            endpoint_limit = self.endpoint_limits.get(endpoint_key, self.global_limit)
            endpoint_allowed, endpoint_remaining = await self._check_rate_limit(
                f"ratelimit:endpoint:{endpoint_key}",
                endpoint_limit
            )
            if not endpoint_allowed:
                return self._rate_limit_exceeded_response(endpoint_remaining)
                
            # Check global limit
            global_allowed, global_remaining = await self._check_rate_limit(
                "ratelimit:global",
                self.global_limit
            )
            if not global_allowed:
                return self._rate_limit_exceeded_response(global_remaining)
                
            # Process request
            response = await call_next(request)
            
            # Add rate limit headers
            response.headers["X-RateLimit-Limit"] = str(min(
                self.user_limit if user_id else float('inf'),
                endpoint_limit,
                self.global_limit
            ))
            response.headers["X-RateLimit-Remaining"] = str(min(
                user_remaining if user_id else float('inf'),
                endpoint_remaining,
                global_remaining
            ))
            response.headers["X-RateLimit-Reset"] = str(int(time.time()) + self.window_seconds)
            
            return response
            
        except Exception as e:
            log_error(f"Rate limiting error: {e}")
            # On error, allow request to proceed
            return await call_next(request)
            
    async def _check_rate_limit(self, key: str, limit: int) -> Tuple[bool, int]:
        """
        Check rate limit for a key
        
        Returns:
            Tuple of (allowed, remaining_requests)
        """
        try:
            # Use Redis pipeline for atomic operations
            pipe = self.redis_client.pipeline()
            
            # Increment counter
            pipe.incr(key)
            # Set expiry if new key
            pipe.expire(key, self.window_seconds)
            # Get current value
            pipe.get(key)
            
            results = await pipe.execute()
            current_count = int(results[2] or 1)
            
            # Check if limit exceeded
            if current_count > limit:
                return False, limit - current_count
                
            return True, limit - current_count
            
        except Exception as e:
            log_error(f"Redis rate limit check error: {e}")
            # On error, allow request
            return True, limit
            
    def _get_user_id(self, request: Request) -> Optional[str]:
        """Extract user ID from request (Architecture Principle #7: JWT validation at gateway only)"""
        # ARCHITECTURE COMPLIANCE: Services MUST trust api-gateway for JWT validation
        # Services MUST NOT independently validate JWT tokens per Architecture Principle #7
        # ARCHITECTURE COMPLIANCE: Single route per functionality - NO alternate identity paths
        
        # Get user ID from gateway-validated header (ONLY source of user identity)
        # API Gateway is the SOLE source of user identity - no exceptions
        user_id = request.headers.get("X-User-ID")
        if user_id:
            return user_id
            
        # No user identity available - unauthenticated request
        # Internal services MUST go through api-gateway like all other requests
        return None
        
    def _get_endpoint_key(self, path: str) -> str:
        """Get endpoint key for rate limiting"""
        # Match path patterns
        for pattern in self.endpoint_limits.keys():
            if path.startswith(pattern):
                return pattern
                
        # Generic v2 API
        if path.startswith("/api/v2/"):
            return "/api/v2/*"
            
        return path
        
    def _rate_limit_exceeded_response(self, remaining: int) -> Response:
        """Create rate limit exceeded response"""
        return Response(
            content=json.dumps({
                "error": "Rate limit exceeded",
                "message": "Too many requests. Please try again later.",
                "retry_after_seconds": self.window_seconds
            }),
            status_code=429,
            headers={
                "Retry-After": str(self.window_seconds),
                "X-RateLimit-Limit": "0",
                "X-RateLimit-Remaining": str(max(0, remaining)),
                "X-RateLimit-Reset": str(int(time.time()) + self.window_seconds)
            },
            media_type="application/json"
        )


class AdaptiveRateLimiter:
    """
    Advanced rate limiter with adaptive limits based on system load
    """
    
    def __init__(self):
        self.redis_client = None
        self.base_limits = {
            "low_load": 1.5,    # 150% of base limit
            "normal_load": 1.0,  # 100% of base limit
            "high_load": 0.5,    # 50% of base limit
            "critical_load": 0.2 # 20% of base limit
        }
        
    async def get_adaptive_limit(self, base_limit: int) -> int:
        """
        Get adaptive rate limit based on system load
        
        Args:
            base_limit: Base rate limit
            
        Returns:
            Adjusted rate limit
        """
        try:
            # Get system load metrics
            load_level = await self._get_system_load()
            
            # Apply multiplier
            multiplier = self.base_limits.get(load_level, 1.0)
            adaptive_limit = int(base_limit * multiplier)
            
            log_info(f"Adaptive rate limit: {adaptive_limit} (load: {load_level})")
            
            return adaptive_limit
            
        except Exception as e:
            log_error(f"Error calculating adaptive limit: {e}")
            return base_limit
            
    async def _get_system_load(self) -> str:
        """Get current system load level"""
        if not self.redis_client:
            self.redis_client = await get_redis_client()
            
        try:
            # Get load metrics from Redis
            metrics = await self.redis_client.hgetall("signal:system:metrics")
            
            if not metrics:
                return "normal_load"
                
            # Calculate load score
            cpu_usage = float(metrics.get(b"cpu_usage", 0))
            memory_usage = float(metrics.get(b"memory_usage", 0))
            queue_depth = int(metrics.get(b"queue_depth", 0))
            
            # Determine load level
            if cpu_usage > 90 or memory_usage > 90 or queue_depth > 1000:
                return "critical_load"
            elif cpu_usage > 70 or memory_usage > 70 or queue_depth > 500:
                return "high_load"
            elif cpu_usage < 30 and memory_usage < 30 and queue_depth < 100:
                return "low_load"
            else:
                return "normal_load"
                
        except Exception as e:
            log_error(f"Error getting system load: {e}")
            return "normal_load"
