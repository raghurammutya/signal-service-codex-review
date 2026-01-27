"""
User Service Client for ACL and permission management
"""
import asyncio
import logging
from typing import Any

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)


class UserServiceClient:
    """Client for communicating with the User Service for ACL operations"""

    def __init__(self):
        self.base_url = settings.USER_SERVICE_URL
        self.timeout = 10.0
        self.max_retries = 3
        self.retry_delay = 1.0

    async def _make_request_with_retry(self, method: str, url: str, operation: str, **kwargs) -> dict[str, Any] | None:
        """Make HTTP request with retry logic and circuit breaker"""
        last_exception = None

        for attempt in range(self.max_retries + 1):
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    if method.upper() == "GET":
                        response = await client.get(url, **kwargs)
                    elif method.upper() == "POST":
                        response = await client.post(url, **kwargs)
                    else:
                        raise ValueError(f"Unsupported method: {method}")

                    response.raise_for_status()
                    return response.json()

            except (httpx.TimeoutException, httpx.ConnectError, httpx.HTTPStatusError) as e:
                last_exception = e
                if attempt < self.max_retries:
                    wait_time = self.retry_delay * (2 ** attempt)
                    logger.warning(f"Attempt {attempt + 1} failed for {operation}: {e}. Retrying in {wait_time}s...")
                    await asyncio.sleep(wait_time)
                else:
                    logger.error(f"All {self.max_retries + 1} attempts failed for {operation}: {e}")
                    raise
            except Exception as e:
                logger.error(f"Non-retryable error for {operation}: {e}")
                raise

        if last_exception:
            raise last_exception

    async def get_user_permissions(self, user_id: str) -> dict[str, Any] | None:
        """Get user permissions from user service with retry logic"""
        return await self._make_request_with_retry(
            method="GET",
            url=f"{self.base_url}/api/v1/users/{user_id}/permissions",
            operation=f"get user permissions for {user_id}"
        )

    async def get_user_profile(self, user_id: str) -> dict[str, Any] | None:
        """Get user profile including preferences and watchlist"""
        return await self._make_request_with_retry(
            method="GET",
            url=f"{self.base_url}/api/v1/users/{user_id}/profile",
            operation=f"get user profile for {user_id}"
        )

    def get_user_permissions_sync(self, user_id: str) -> dict[str, Any] | None:
        """Synchronous version for non-async contexts"""
        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.get(
                    f"{self.base_url}/api/v1/users/{user_id}/permissions"
                )
                response.raise_for_status()
                return response.json()
        except Exception as e:
            logger.error(f"Failed to get user permissions for {user_id}: {e}")
            raise
