"""
Universal Computation API
Provides a unified interface for all computation types across all asset classes
"""
import asyncio
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

from app.dependencies import get_universal_calculator
from app.services.computation_registry import computation_registry
from app.services.universal_calculator import AssetType, ComputationType, UniversalCalculator
from app.utils.logging_utils import log_exception, log_info

router = APIRouter(prefix="/universal", tags=["universal-computation"])


# Request/Response Models
from pydantic import BaseModel, Field


class ComputationRequest(BaseModel):
    """Single computation request"""
    type: str = Field(..., description="Type of computation (indicator, greeks, moneyness, etc.)")
    name: str | None = Field(None, description="Optional name for the result")
    params: dict[str, Any] = Field(default_factory=dict, description="Computation parameters")


class UniversalComputeRequest(BaseModel):
    """Universal computation request"""
    asset_type: str = Field(..., description="Asset type (equity, futures, options, etc.)")
    instrument_key: str = Field(..., description="Universal instrument key")
    computations: list[ComputationRequest] = Field(..., description="List of computations to perform")
    timeframe: str | None = Field("5m", description="Timeframe for data")
    mode: str | None = Field("realtime", description="Computation mode (realtime, historical, batch)")
    context: dict[str, Any] | None = Field(
        default_factory=dict,
        description="Additional context (spot price, risk-free rate, etc.)"
    )


class ComputationResult(BaseModel):
    """Result of a single computation"""
    name: str
    value: Any | None = None
    error: str | None = None
    metadata: dict[str, Any] | None = None
    timestamp: datetime | None = None


class UniversalComputeResponse(BaseModel):
    """Universal computation response"""
    instrument_key: str
    asset_type: str
    timestamp: datetime
    computations: dict[str, Any]
    metadata: dict[str, Any]
    execution_time_ms: float


@router.post("/compute", response_model=UniversalComputeResponse)
async def universal_compute(
    request: UniversalComputeRequest,
    calculator: UniversalCalculator = Depends(get_universal_calculator)
) -> UniversalComputeResponse:
    """
    Universal computation endpoint for all asset types and calculations

    This endpoint provides a unified interface for:
    - Technical indicators (SMA, RSI, MACD, etc.)
    - Option Greeks (Delta, Gamma, Theta, Vega, Rho)
    - Moneyness calculations
    - Volatility measures
    - Risk metrics
    - Custom formulas
    - And more...

    Supports all asset types:
    - Equities
    - Futures
    - Options
    - Indices
    - Commodities
    - Currencies
    - Crypto
    """
    try:
        start_time = datetime.utcnow()

        log_info(
            f"Universal compute request: {request.asset_type} - {request.instrument_key} - "
            f"{len(request.computations)} computations"
        )

        # Validate asset type
        try:
            asset_type = AssetType(request.asset_type.lower())
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid asset type: {request.asset_type}. "
                f"Valid types: {[t.value for t in AssetType]}"
            )

        # Prepare computation list
        computation_list = []
        for comp in request.computations:
            computation_list.append({
                "type": comp.type,
                "name": comp.name or comp.type,
                "params": comp.params
            })

        # Execute computations
        result = await calculator.compute(
            asset_type=asset_type,
            instrument_key=request.instrument_key,
            computations=computation_list,
            data=None,  # Let calculator fetch data as needed
            context=request.context
        )

        # Calculate execution time
        execution_time_ms = (datetime.utcnow() - start_time).total_seconds() * 1000

        # Format response
        response = UniversalComputeResponse(
            instrument_key=result["instrument_key"],
            asset_type=result["asset_type"],
            timestamp=result["timestamp"],
            computations=result["computations"],
            metadata={
                **result["metadata"],
                "execution_time_ms": execution_time_ms,
                "mode": request.mode,
                "timeframe": request.timeframe
            },
            execution_time_ms=execution_time_ms
        )

        log_info(
            f"Universal compute completed: {result['metadata']['successful_computations']} successful, "
            f"{result['metadata']['failed_computations']} failed, {execution_time_ms:.2f}ms"
        )

        return response

    except HTTPException:
        raise
    except Exception as e:
        log_exception(f"Error in universal compute: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/compute/batch")
async def universal_compute_batch(
    instruments: list[str],
    computations: list[ComputationRequest],
    asset_type: str,
    context: dict[str, Any] | None = None,
    calculator: UniversalCalculator = Depends(get_universal_calculator)
) -> dict[str, Any]:
    """
    Batch computation for multiple instruments

    Process the same set of computations for multiple instruments in parallel
    """
    try:
        start_time = datetime.utcnow()

        # Validate asset type
        try:
            asset_type_enum = AssetType(asset_type.lower())
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid asset type: {asset_type}"
            )

        # Prepare computation list
        computation_list = []
        for comp in computations:
            computation_list.append({
                "type": comp.type,
                "name": comp.name or comp.type,
                "params": comp.params
            })

        # Process instruments in parallel
        tasks = []
        for instrument in instruments:
            task = calculator.compute(
                asset_type=asset_type_enum,
                instrument_key=instrument,
                computations=computation_list,
                context=context
            )
            tasks.append(task)

        # Wait for all computations
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Format results
        batch_results = {}
        errors = {}

        for instrument, result in zip(instruments, results, strict=False):
            if isinstance(result, Exception):
                errors[instrument] = str(result)
            else:
                batch_results[instrument] = result["computations"]

        execution_time_ms = (datetime.utcnow() - start_time).total_seconds() * 1000

        return {
            "asset_type": asset_type,
            "instruments_processed": len(instruments),
            "successful": len(batch_results),
            "failed": len(errors),
            "results": batch_results,
            "errors": errors if errors else None,
            "execution_time_ms": execution_time_ms
        }

    except HTTPException:
        raise
    except Exception as e:
        log_exception(f"Error in batch compute: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/computations")
async def list_computations(
    asset_type: str | None = Query(None, description="Filter by asset type"),
    tags: list[str] | None = Query(None, description="Filter by tags")
) -> dict[str, Any]:
    """
    List available computations with optional filtering

    Returns all registered computations that can be used with the /compute endpoint
    """
    try:
        # Get filtered computations
        computations = computation_registry.list_computations(
            asset_type=asset_type,
            tags=tags
        )

        # Format response
        formatted_computations = []
        for comp in computations:
            formatted_computations.append({
                "name": comp.name,
                "description": comp.description,
                "asset_types": list(comp.asset_types),
                "parameters": comp.parameters,
                "returns": comp.returns,
                "tags": comp.tags,
                "version": comp.version,
                "examples": comp.examples
            })

        return {
            "total": len(formatted_computations),
            "filters": {
                "asset_type": asset_type,
                "tags": tags
            },
            "computations": formatted_computations
        }

    except Exception as e:
        log_exception(f"Error listing computations: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/computations/{computation_name}")
async def get_computation_details(computation_name: str) -> dict[str, Any]:
    """
    Get detailed information about a specific computation

    Returns complete documentation including parameters, examples, and supported assets
    """
    try:
        computation = computation_registry.get_computation(computation_name)

        if not computation:
            raise HTTPException(
                status_code=404,
                detail=f"Computation '{computation_name}' not found"
            )

        return {
            "name": computation.name,
            "description": computation.description,
            "asset_types": list(computation.asset_types),
            "parameters": computation.parameters,
            "returns": computation.returns,
            "tags": computation.tags,
            "version": computation.version,
            "examples": computation.examples,
            "created_at": computation.created_at.isoformat(),
            "last_updated": computation.last_updated.isoformat()
        }

    except HTTPException:
        raise
    except Exception as e:
        log_exception(f"Error getting computation details: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/validate")
async def validate_computation_request(
    request: UniversalComputeRequest
) -> dict[str, Any]:
    """
    Validate a computation request without executing it

    Useful for checking if a computation is valid before execution
    """
    try:
        # Validate asset type
        try:
            AssetType(request.asset_type.lower())
        except ValueError:
            return {
                "valid": False,
                "errors": [f"Invalid asset type: {request.asset_type}"]
            }

        errors = []
        warnings = []

        # Validate each computation
        for comp in request.computations:
            computation = computation_registry.get_computation(comp.type)

            if not computation:
                errors.append(f"Unknown computation type: {comp.type}")
                continue

            # Check if computation supports asset type
            if request.asset_type not in computation.asset_types:
                errors.append(
                    f"Computation '{comp.type}' not supported for asset type '{request.asset_type}'"
                )
                continue

            # Validate parameters
            try:
                computation_registry.validate_parameters(
                    comp.type,
                    comp.params
                )
            except Exception as e:
                errors.append(f"Parameter validation failed for '{comp.type}': {str(e)}")

        return {
            "valid": len(errors) == 0,
            "errors": errors if errors else None,
            "warnings": warnings if warnings else None,
            "computations_validated": len(request.computations)
        }

    except Exception as e:
        log_exception(f"Error validating request: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/examples/{asset_type}")
async def get_computation_examples(
    asset_type: str,
    computation_type: str | None = None
) -> dict[str, Any]:
    """
    Get example computation requests for a specific asset type

    Helpful for understanding how to use the universal compute endpoint
    """
    try:
        # Validate asset type
        try:
            asset_type_enum = AssetType(asset_type.lower())
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid asset type: {asset_type}"
            )

        examples = []

        # Equity example
        if asset_type_enum == AssetType.EQUITY:
            examples.append({
                "name": "Technical Analysis Bundle",
                "request": {
                    "asset_type": "equity",
                    "instrument_key": "NSE@RELIANCE@equity",
                    "computations": [
                        {"type": "indicator", "name": "sma20", "params": {"indicator": "sma", "period": 20}},
                        {"type": "indicator", "name": "rsi", "params": {"indicator": "rsi", "period": 14}},
                        {"type": "volatility", "params": {"type": "historical", "period": 20}},
                        {"type": "risk_metrics", "params": {"metrics": ["sharpe", "max_drawdown"]}}
                    ]
                }
            })

        # Options example
        elif asset_type_enum == AssetType.OPTIONS:
            examples.append({
                "name": "Options Analytics Bundle",
                "request": {
                    "asset_type": "options",
                    "instrument_key": "EXCHANGE@SYMBOL@STRIKE@EXPIRY@TYPE",
                    "computations": [
                        {"type": "greeks", "params": {"model": "black-scholes"}},
                        {"type": "moneyness", "params": {"reference": "spot"}},
                        {"type": "volatility", "params": {"type": "implied"}},
                        {"type": "risk_metrics", "params": {}}
                    ],
                    "context": {
                        "spot_price": 21800,
                        "strike_price": 22000,
                        "time_to_expiry": 0.068,
                        "option_type": "call"
                    }
                }
            })

        # Futures example
        elif asset_type_enum == AssetType.FUTURES:
            examples.append({
                "name": "Futures Analysis Bundle",
                "request": {
                    "asset_type": "futures",
                    "instrument_key": "EXCHANGE@SYMBOL@EXPIRY@FUT",
                    "computations": [
                        {"type": "moneyness", "params": {}},
                        {"type": "risk_metrics", "params": {"notional": 1000000}},
                        {"type": "volatility", "params": {"period": 20}}
                    ],
                    "context": {
                        "futures_price": 21850,
                        "spot_price": 21800,
                        "days_to_expiry": 8
                    }
                }
            })

        # Custom formula example (works for all assets)
        examples.append({
            "name": "Custom Formula Example",
            "request": {
                "asset_type": asset_type,
                "instrument_key": f"EXCHANGE@SYMBOL@{asset_type}",
                "computations": [
                    {
                        "type": "custom",
                        "name": "price_to_sma_ratio",
                        "params": {
                            "formula": "close / sma20",
                            "context": {
                                "sma20": {"type": "indicator", "indicator": "sma", "period": 20}
                            }
                        }
                    }
                ]
            }
        })

        # Filter by computation type if specified
        if computation_type:
            examples = [
                ex for ex in examples
                if any(comp["type"] == computation_type for comp in ex["request"]["computations"])
            ]

        return {
            "asset_type": asset_type,
            "computation_type": computation_type,
            "examples": examples
        }

    except HTTPException:
        raise
    except Exception as e:
        log_exception(f"Error getting examples: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/health")
async def universal_health_check() -> dict[str, Any]:
    """Health check for universal computation engine"""
    try:
        # Get registry info
        registry_info = computation_registry.get_computation_info()

        return {
            "status": "healthy",
            "service": "universal_computation_engine",
            "timestamp": datetime.utcnow().isoformat(),
            "capabilities": {
                "total_computations": registry_info["total_computations"],
                "asset_coverage": registry_info["asset_coverage"],
                "supported_assets": [t.value for t in AssetType],
                "computation_types": [t.value for t in ComputationType]
            }
        }

    except Exception as e:
        log_exception(f"Error in health check: {str(e)}")
        return {
            "status": "unhealthy",
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat()
        }
