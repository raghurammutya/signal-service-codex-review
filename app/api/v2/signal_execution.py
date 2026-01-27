"""
Signal Execution API

Endpoints for executing signal scripts (marketplace and personal).
"""

from datetime import datetime
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Header, HTTPException

from app.core.auth import get_current_user_from_gateway
from app.core.logging import log_error, log_info
from app.schemas.signal_schemas import (
    PersonalSignalExecutionRequest,
    SignalExecutionRequest,
    SignalExecutionResponse,
)
from app.services.signal_executor import SignalExecutor
from app.services.signal_stream_contract import StreamKeyFormat

router = APIRouter(prefix="/api/v2/signals", tags=["signal-execution"])


@router.post("/execute/marketplace", response_model=SignalExecutionResponse)
async def execute_marketplace_signal(
    request: SignalExecutionRequest,
    background_tasks: BackgroundTasks,
    authorization: str | None = Header(None),
    x_user_id: str | None = Header(None, alias="X-User-ID"),
    x_gateway_secret: str | None = Header(None, alias="X-Gateway-Secret")
) -> SignalExecutionResponse:
    """
    Execute a marketplace signal script.

    Requires valid execution token from marketplace subscription.
    Script is fetched from MinIO and executed in sandbox.
    Results are published to Redis streams.
    """
    try:
        # Get user info
        user_info = await get_current_user_from_gateway(
            x_user_id, x_gateway_secret, authorization
        )
        user_id = str(user_info.get("user_id", user_info.get("id")))

        log_info(
            f"Marketplace signal execution request: user={user_id}, "
            f"product={request.product_id}, instrument={request.instrument}"
        )

        # Generate execution ID and initialize tracking
        execution_id = f"exec_{request.product_id}_{request.instrument}_{int(datetime.now().timestamp())}"

        # Initialize execution status tracking
        await SignalExecutor._init_execution_tracking(execution_id)

        # Execute in background to avoid blocking
        background_tasks.add_task(
            SignalExecutor.execute_marketplace_signal,
            execution_token=request.execution_token,
            product_id=request.product_id,
            instrument=request.instrument,
            params=request.params,
            user_id=user_id,
            subscription_id=request.subscription_id,
            execution_id=execution_id
        )

        return SignalExecutionResponse(
            success=True,
            message="Signal execution initiated",
            execution_id=execution_id,
            stream_keys=[
                StreamKeyFormat.create_marketplace_key(
                    request.product_id,
                    request.instrument,
                    "default",  # Will be replaced with actual signal names
                    request.params
                )
            ]
        )

    except Exception as e:
        log_error(f"Error initiating marketplace signal execution: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/execute/personal", response_model=SignalExecutionResponse)
async def execute_personal_signal(
    request: PersonalSignalExecutionRequest,
    background_tasks: BackgroundTasks,
    authorization: str | None = Header(None),
    x_user_id: str | None = Header(None, alias="X-User-ID"),
    x_gateway_secret: str | None = Header(None, alias="X-Gateway-Secret")
) -> SignalExecutionResponse:
    """
    Execute a personal signal script.

    Only the owner can execute their personal signals.
    Script is fetched from MinIO personal namespace and executed.
    Results are published to Redis streams.
    """
    try:
        # Get user info
        user_info = await get_current_user_from_gateway(
            x_user_id, x_gateway_secret, authorization
        )
        user_id = str(user_info.get("user_id", user_info.get("id")))

        log_info(
            f"Personal signal execution request: user={user_id}, "
            f"script={request.script_id}, instrument={request.instrument}"
        )

        # Generate execution ID and initialize tracking
        execution_id = f"exec_personal_{user_id}_{request.script_id}_{int(datetime.now().timestamp())}"

        # Initialize execution status tracking
        await SignalExecutor._init_execution_tracking(execution_id)

        # Execute in background
        background_tasks.add_task(
            SignalExecutor.execute_personal_signal,
            user_id=user_id,
            script_id=request.script_id,
            instrument=request.instrument,
            params=request.params,
            execution_id=execution_id
        )

        return SignalExecutionResponse(
            success=True,
            message="Personal signal execution initiated",
            execution_id=execution_id,
            stream_keys=[
                StreamKeyFormat.create_personal_key(
                    user_id,
                    request.script_id,
                    request.instrument,
                    request.params
                )
            ]
        )

    except Exception as e:
        log_error(f"Error initiating personal signal execution: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/execution/status/{execution_id}")
async def get_execution_status(
    execution_id: str,
    authorization: str | None = Header(None),
    x_user_id: str | None = Header(None, alias="X-User-ID"),
    x_gateway_secret: str | None = Header(None, alias="X-Gateway-Secret")
) -> dict[str, Any]:
    """
    Get status of a signal execution.

    Tracks execution state in Redis with 1-hour TTL.
    """
    # Validate authentication using gateway trust pattern (let auth errors pass through)
    from app.core.auth.gateway_trust import get_current_user_from_gateway
    await get_current_user_from_gateway(
        x_user_id=x_user_id,
        x_gateway_secret=x_gateway_secret,
        authorization=authorization
    )

    try:
        import json

        from app.core.redis_manager import get_redis_client

        redis_client = await get_redis_client()
        execution_key = f"signal_execution:{execution_id}"

        # Get execution status from Redis
        execution_data = await redis_client.get(execution_key)

        if not execution_data:
            # Execution not found or expired
            return {
                "execution_id": execution_id,
                "status": "not_found",
                "message": "Execution not found or has expired"
            }

        # Parse execution status
        status_info = json.loads(execution_data)

        return {
            "execution_id": execution_id,
            "status": status_info.get("status", "unknown"),
            "message": status_info.get("message", ""),
            "started_at": status_info.get("started_at"),
            "updated_at": status_info.get("updated_at"),
            "error": status_info.get("error")
        }

    except Exception as e:
        # Only catch non-HTTP exceptions (Redis, JSON parsing errors, etc.)
        log_error(f"Error getting execution status for {execution_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


# Import for stream key generation
