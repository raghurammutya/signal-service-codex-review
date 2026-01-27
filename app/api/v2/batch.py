"""
Batch Processing API endpoints for Signal Service
Handles bulk computation requests for improved performance
"""
import asyncio
import logging
import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException

logger = logging.getLogger(__name__)
from app.core.config import settings
from app.dependencies import get_moneyness_calculator
from app.schemas.signal_schemas import BatchGreeksRequest, BatchGreeksResponse
from app.services.bulk_computation_engine import BulkComputationEngine
from app.services.moneyness_greeks_calculator import MoneynessAwareGreeksCalculator

router = APIRouter(prefix="/batch", tags=["batch"])

# Batch job storage (in production, use Redis or database)
batch_jobs = {}


async def get_bulk_engine() -> BulkComputationEngine:
    """Get bulk computation engine instance"""
    from app.main import app
    if hasattr(app.state, 'bulk_computation_engine'):
        return app.state.bulk_computation_engine
    # Initialize if not available
    engine = BulkComputationEngine()
    await engine.initialize()
    return engine


@router.post("/greeks", response_model=BatchGreeksResponse)
async def compute_batch_greeks(
    request: BatchGreeksRequest,
    background_tasks: BackgroundTasks,
    engine: BulkComputationEngine = Depends(get_bulk_engine)
) -> BatchGreeksResponse:
    """
    Compute Greeks for multiple instruments in batch

    Args:
        request: Batch Greeks computation request

    Returns:
        Batch computation results
    """
    try:
        start_time = datetime.utcnow()
        results = {}
        errors = {}

        # Process in parallel batches
        batch_size = 10  # Process 10 instruments at a time
        tasks = []

        for i in range(0, len(request.instrument_keys), batch_size):
            batch = request.instrument_keys[i:i + batch_size]
            task = engine.compute_greeks_batch(batch)
            tasks.append(task)

        # Wait for all batches
        batch_results = await asyncio.gather(*tasks, return_exceptions=True)

        # Aggregate results
        for batch_result in batch_results:
            if isinstance(batch_result, Exception):
                logger.error(f"Batch processing error: {batch_result}")
                continue

            for instrument_key, result in batch_result.items():
                if "error" in result:
                    errors[instrument_key] = result["error"]
                else:
                    results[instrument_key] = result

        # Calculate computation time
        computation_time_ms = (datetime.utcnow() - start_time).total_seconds() * 1000

        return BatchGreeksResponse(
            timestamp=datetime.utcnow(),
            results=results,
            errors=errors if errors else None,
            computation_time_ms=computation_time_ms
        )

    except Exception as e:
        logger.exception(f"Error in batch Greeks computation: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/indicators")
async def compute_batch_indicators(
    instrument_keys: list[str],
    indicators: list[dict[str, Any]],
    timeframe: str = "5m",
    engine: BulkComputationEngine = Depends(get_bulk_engine)
) -> dict[str, Any]:
    """
    Compute multiple indicators for multiple instruments

    Args:
        instrument_keys: List of instruments
        indicators: List of indicator configurations
        timeframe: Time interval

    Returns:
        Batch indicator results
    """
    try:
        if len(instrument_keys) > settings.API_V2_BATCH_SIZE:
            raise HTTPException(
                status_code=400,
                detail=f"Batch size exceeds limit of {settings.API_V2_BATCH_SIZE}"
            )

        start_time = datetime.utcnow()
        results = {}

        # Process each instrument
        for instrument_key in instrument_keys:
            instrument_results = {}

            # Compute each indicator
            for indicator_config in indicators:
                indicator_name = indicator_config.get("name")
                params = indicator_config.get("params", {})

                try:
                    value = await engine.compute_indicator(
                        instrument_key,
                        indicator_name,
                        timeframe,
                        **params
                    )
                    instrument_results[indicator_name] = {
                        "value": value,
                        "params": params
                    }
                except Exception as e:
                    instrument_results[indicator_name] = {
                        "error": str(e)
                    }

            results[instrument_key] = instrument_results

        computation_time_ms = (datetime.utcnow() - start_time).total_seconds() * 1000

        return {
            "timestamp": datetime.utcnow().isoformat(),
            "results": results,
            "computation_time_ms": computation_time_ms,
            "instruments_processed": len(instrument_keys),
            "indicators_computed": len(indicators)
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error in batch indicators computation: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/moneyness/greeks")
async def compute_batch_moneyness_greeks(
    underlyings: list[str],
    moneyness_levels: list[str],
    expiry_dates: list[str] | None = None,
    calculator: MoneynessAwareGreeksCalculator = Depends(get_moneyness_calculator)
) -> dict[str, Any]:
    """
    Compute moneyness Greeks for multiple underlyings and levels

    Args:
        underlyings: List of underlying symbols
        moneyness_levels: List of moneyness levels (ATM, OTM5delta, etc.)
        expiry_dates: Optional list of expiry dates

    Returns:
        Batch moneyness Greeks results
    """
    try:
        start_time = datetime.utcnow()
        results = {}

        # Get spot prices for all underlyings
        from app.services.signal_processor import SignalProcessor
        processor = SignalProcessor()

        # Create all computation tasks
        tasks = []
        task_keys = []

        for underlying in underlyings:
            # Get spot price
            spot_price = await processor.get_latest_price(underlying)
            if not spot_price:
                results[underlying] = {"error": "Spot price not available"}
                continue

            for moneyness_level in moneyness_levels:
                # Use first expiry date if provided, else None
                expiry = expiry_dates[0] if expiry_dates else None

                task = calculator.calculate_moneyness_greeks(
                    underlying,
                    spot_price,
                    moneyness_level,
                    expiry
                )
                tasks.append(task)
                task_keys.append(f"{underlying}_{moneyness_level}")

        # Execute all tasks in parallel
        task_results = await asyncio.gather(*tasks, return_exceptions=True)

        # Map results
        for key, result in zip(task_keys, task_results, strict=False):
            if isinstance(result, Exception):
                results[key] = {"error": str(result)}
            else:
                results[key] = result

        computation_time_ms = (datetime.utcnow() - start_time).total_seconds() * 1000

        return {
            "timestamp": datetime.utcnow().isoformat(),
            "results": results,
            "computation_time_ms": computation_time_ms,
            "underlyings_processed": len(underlyings),
            "moneyness_levels": moneyness_levels
        }

    except Exception as e:
        logger.exception(f"Error in batch moneyness Greeks: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/async/submit")
async def submit_async_batch_job(
    job_type: str,
    parameters: dict[str, Any],
    callback_url: str | None = None,
    background_tasks: BackgroundTasks = BackgroundTasks()
) -> dict[str, Any]:
    """
    Submit an asynchronous batch job

    Args:
        job_type: Type of batch job (greeks, indicators, moneyness)
        parameters: Job parameters
        callback_url: Optional URL to call when job completes

    Returns:
        Job submission details
    """
    try:
        # Generate job ID
        job_id = str(uuid.uuid4())

        # Store job info
        batch_jobs[job_id] = {
            "id": job_id,
            "type": job_type,
            "parameters": parameters,
            "status": "queued",
            "submitted_at": datetime.utcnow().isoformat(),
            "callback_url": callback_url
        }

        # Queue background task
        background_tasks.add_task(
            process_async_batch_job,
            job_id,
            job_type,
            parameters,
            callback_url
        )

        logger.info(f"Batch job {job_id} submitted for {job_type}")

        return {
            "job_id": job_id,
            "status": "queued",
            "message": "Batch job submitted successfully",
            "check_status_url": f"/api/v2/signals/batch/async/status/{job_id}"
        }

    except Exception as e:
        logger.exception(f"Error submitting batch job: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/async/status/{job_id}")
async def get_batch_job_status(job_id: str) -> dict[str, Any]:
    """
    Get status of an asynchronous batch job

    Args:
        job_id: Job identifier

    Returns:
        Job status and results if available
    """
    try:
        if job_id not in batch_jobs:
            raise HTTPException(status_code=404, detail="Job not found")

        job = batch_jobs[job_id]

        response = {
            "job_id": job_id,
            "type": job["type"],
            "status": job["status"],
            "submitted_at": job["submitted_at"],
            "started_at": job.get("started_at"),
            "completed_at": job.get("completed_at")
        }

        if job["status"] == "completed":
            response["results"] = job.get("results", {})
            response["computation_time_ms"] = job.get("computation_time_ms")
        elif job["status"] == "failed":
            response["error"] = job.get("error", "Unknown error")

        return response

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error getting job status: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


async def process_async_batch_job(
    job_id: str,
    job_type: str,
    parameters: dict[str, Any],
    callback_url: str | None
):
    """
    Process asynchronous batch job

    Args:
        job_id: Job identifier
        job_type: Type of job
        parameters: Job parameters
        callback_url: Optional callback URL
    """
    try:
        # Update job status
        batch_jobs[job_id]["status"] = "processing"
        batch_jobs[job_id]["started_at"] = datetime.utcnow().isoformat()

        start_time = datetime.utcnow()

        # Process based on job type
        if job_type == "greeks":
            engine = BulkComputationEngine()
            await engine.initialize()

            results = {}
            for instrument_key in parameters.get("instrument_keys", []):
                try:
                    greeks = await engine.compute_greeks_batch([instrument_key])
                    results[instrument_key] = greeks[instrument_key]
                except Exception as e:
                    results[instrument_key] = {"error": str(e)}

        elif job_type == "indicators":
            # Process indicators batch
            results = {"message": "Indicators batch processing not implemented"}

        elif job_type == "moneyness":
            # Process moneyness batch
            results = {"message": "Moneyness batch processing not implemented"}

        else:
            raise ValueError(f"Unknown job type: {job_type}")

        # Calculate computation time
        computation_time_ms = (datetime.utcnow() - start_time).total_seconds() * 1000

        # Update job with results
        batch_jobs[job_id].update({
            "status": "completed",
            "completed_at": datetime.utcnow().isoformat(),
            "results": results,
            "computation_time_ms": computation_time_ms
        })

        # Call callback if provided
        if callback_url:
            await notify_job_completion(job_id, callback_url, results)

    except Exception as e:
        logger.exception(f"Error processing batch job {job_id}: {e}")
        batch_jobs[job_id].update({
            "status": "failed",
            "completed_at": datetime.utcnow().isoformat(),
            "error": str(e)
        })


async def notify_job_completion(
    job_id: str,
    callback_url: str,
    results: dict[str, Any]
):
    """Notify callback URL of job completion"""
    try:
        import aiohttp

        payload = {
            "job_id": job_id,
            "status": "completed",
            "results": results,
            "timestamp": datetime.utcnow().isoformat()
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(callback_url, json=payload) as response:
                if response.status != 200:
                    logger.warning(f"Callback failed for job {job_id}: {response.status}")
                else:
                    logger.info(f"Callback successful for job {job_id}")

    except Exception as e:
        logger.error(f"Error calling callback for job {job_id}: {e}")


@router.get("/performance/stats")
async def get_batch_performance_stats(
    engine: BulkComputationEngine = Depends(get_bulk_engine)
) -> dict[str, Any]:
    """
    Get batch processing performance statistics

    Returns:
        Performance metrics and statistics
    """
    try:
        stats = await engine.get_performance_stats()

        return {
            "performance_stats": stats,
            "configuration": {
                "max_batch_size": settings.API_V2_BATCH_SIZE,
                "parallel_workers": engine.parallel_workers,
                "cache_enabled": True
            },
            "timestamp": datetime.utcnow().isoformat()
        }

    except Exception as e:
        logger.exception(f"Error getting performance stats: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e
