"""
Data Enrichment API for Historical Data Service Integration
Provides batch enrichment of historical data with computations
"""
from fastapi import APIRouter, HTTPException, Depends
from typing import Dict, List, Optional, Any
from datetime import datetime
import asyncio

from app.utils.logging_utils import log_info, log_error, log_exception
from app.services.universal_calculator import UniversalCalculator
from app.dependencies import get_universal_calculator
from app.schemas.universal_schemas import (
    AssetTypeEnum, ComputationRequest, BatchComputeRequest, BatchComputeResponse
)


router = APIRouter(prefix="/enrichment", tags=["data-enrichment"])


@router.post("/historical/batch")
async def enrich_historical_batch(
    request: Dict[str, Any],
    calculator: UniversalCalculator = Depends(get_universal_calculator)
) -> Dict[str, Any]:
    """
    Enrich historical data with computations for the Historical Data Service
    
    This endpoint is designed to be called by the Historical Data Service
    to add computed indicators and metrics to historical data.
    
    Request format:
    {
        "job_id": "uuid",
        "data": [
            {
                "instrument_key": "NSE@RELIANCE@equity",
                "asset_type": "equity",
                "data_points": [
                    {
                        "timestamp": "2024-01-01T10:00:00Z",
                        "open": 2450.00,
                        "high": 2465.00,
                        "low": 2440.00,
                        "close": 2460.00,
                        "volume": 1000000
                    }
                ]
            }
        ],
        "enrichments": [
            {
                "type": "indicator",
                "name": "sma20",
                "params": {"indicator": "sma", "period": 20}
            },
            {
                "type": "indicator", 
                "name": "rsi",
                "params": {"indicator": "rsi", "period": 14}
            }
        ]
    }
    """
    try:
        start_time = datetime.utcnow()
        
        job_id = request.get("job_id")
        data_items = request.get("data", [])
        enrichments = request.get("enrichments", [])
        
        if not job_id:
            raise HTTPException(status_code=400, detail="job_id is required")
        
        if not data_items:
            raise HTTPException(status_code=400, detail="data is required")
        
        if not enrichments:
            raise HTTPException(status_code=400, detail="enrichments are required")
        
        log_info(f"Processing enrichment job {job_id}: {len(data_items)} instruments, {len(enrichments)} enrichments")
        
        # Process each instrument
        enriched_data = []
        errors = []
        
        for item in data_items:
            instrument_key = item.get("instrument_key")
            asset_type = item.get("asset_type")
            data_points = item.get("data_points", [])
            
            if not instrument_key or not asset_type:
                errors.append(f"Invalid data item: missing instrument_key or asset_type")
                continue
            
            try:
                # Convert data points to DataFrame format
                import pandas as pd
                df = pd.DataFrame(data_points)
                if not df.empty:
                    df['timestamp'] = pd.to_datetime(df['timestamp'])
                    df.set_index('timestamp', inplace=True)
                
                # Prepare computation requests
                computation_requests = []
                for enrichment in enrichments:
                    computation_requests.append({
                        "type": enrichment.get("type"),
                        "name": enrichment.get("name"),
                        "params": enrichment.get("params", {})
                    })
                
                # Calculate enrichments
                enrichment_results = await calculator.compute(
                    asset_type=asset_type,
                    instrument_key=instrument_key,
                    computations=computation_requests,
                    data=df if not df.empty else None
                )
                
                # Format enriched data
                enriched_item = {
                    "instrument_key": instrument_key,
                    "asset_type": asset_type,
                    "data_points": data_points,
                    "enrichments": enrichment_results.get("computations", {}),
                    "metadata": {
                        "enrichment_timestamp": datetime.utcnow().isoformat(),
                        "successful_enrichments": enrichment_results.get("metadata", {}).get("successful_computations", 0),
                        "failed_enrichments": enrichment_results.get("metadata", {}).get("failed_computations", 0)
                    }
                }
                
                enriched_data.append(enriched_item)
                
            except Exception as e:
                log_error(f"Error enriching {instrument_key}: {str(e)}")
                errors.append(f"Error enriching {instrument_key}: {str(e)}")
        
        execution_time_ms = (datetime.utcnow() - start_time).total_seconds() * 1000
        
        return {
            "job_id": job_id,
            "status": "completed",
            "timestamp": datetime.utcnow().isoformat(),
            "processed_instruments": len(data_items),
            "successful_enrichments": len(enriched_data),
            "failed_enrichments": len(errors),
            "execution_time_ms": execution_time_ms,
            "enriched_data": enriched_data,
            "errors": errors if errors else None
        }
        
    except HTTPException:
        raise
    except Exception as e:
        log_exception(f"Error in historical enrichment: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/realtime/stream")
async def enrich_realtime_stream(
    request: Dict[str, Any],
    calculator: UniversalCalculator = Depends(get_universal_calculator)
) -> Dict[str, Any]:
    """
    Enrich real-time data stream with computations
    
    This endpoint is designed for real-time data enrichment as data flows
    through the system.
    
    Request format:
    {
        "stream_id": "stream_uuid",
        "instrument_key": "NSE@RELIANCE@equity",
        "asset_type": "equity",
        "tick_data": {
            "timestamp": "2024-01-01T10:00:00Z",
            "ltp": 2460.00,
            "volume": 1000000,
            "change": 10.00,
            "change_percent": 0.41
        },
        "enrichments": [
            {
                "type": "indicator",
                "name": "sma20",
                "params": {"indicator": "sma", "period": 20}
            }
        ],
        "context": {
            "spot_price": 2460.00,
            "volatility": 0.25
        }
    }
    """
    try:
        stream_id = request.get("stream_id")
        instrument_key = request.get("instrument_key")
        asset_type = request.get("asset_type")
        tick_data = request.get("tick_data")
        enrichments = request.get("enrichments", [])
        context = request.get("context", {})
        
        if not all([stream_id, instrument_key, asset_type, tick_data]):
            raise HTTPException(
                status_code=400,
                detail="stream_id, instrument_key, asset_type, and tick_data are required"
            )
        
        # Prepare computation requests
        computation_requests = []
        for enrichment in enrichments:
            computation_requests.append({
                "type": enrichment.get("type"),
                "name": enrichment.get("name"),
                "params": enrichment.get("params", {})
            })
        
        # Add tick data to context
        if tick_data:
            context.update({
                "current_price": tick_data.get("ltp"),
                "current_volume": tick_data.get("volume"),
                "timestamp": tick_data.get("timestamp")
            })
        
        # Calculate enrichments
        enrichment_results = await calculator.compute(
            asset_type=asset_type,
            instrument_key=instrument_key,
            computations=computation_requests,
            data=None,  # Real-time mode
            context=context
        )
        
        return {
            "stream_id": stream_id,
            "instrument_key": instrument_key,
            "asset_type": asset_type,
            "timestamp": datetime.utcnow().isoformat(),
            "tick_data": tick_data,
            "enrichments": enrichment_results.get("computations", {}),
            "metadata": {
                "enrichment_mode": "realtime",
                "successful_enrichments": enrichment_results.get("metadata", {}).get("successful_computations", 0),
                "failed_enrichments": enrichment_results.get("metadata", {}).get("failed_computations", 0),
                "execution_time_ms": enrichment_results.get("metadata", {}).get("execution_time_ms", 0)
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        log_exception(f"Error in realtime enrichment: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/templates/create")
async def create_enrichment_template(
    template: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Create a reusable enrichment template
    
    Templates allow the Historical Data Service to define common enrichment
    patterns that can be reused across multiple requests.
    
    Request format:
    {
        "name": "equity_technical_analysis",
        "description": "Standard technical analysis for equities",
        "asset_types": ["equity"],
        "enrichments": [
            {
                "type": "indicator",
                "name": "sma20",
                "params": {"indicator": "sma", "period": 20}
            },
            {
                "type": "indicator",
                "name": "rsi",
                "params": {"indicator": "rsi", "period": 14}
            },
            {
                "type": "volatility",
                "name": "volatility_20d",
                "params": {"period": 20, "type": "historical"}
            }
        ]
    }
    """
    try:
        name = template.get("name")
        description = template.get("description")
        asset_types = template.get("asset_types", [])
        enrichments = template.get("enrichments", [])
        
        if not name:
            raise HTTPException(status_code=400, detail="template name is required")
        
        if not enrichments:
            raise HTTPException(status_code=400, detail="enrichments are required")
        
        # Validate enrichments
        for enrichment in enrichments:
            if not enrichment.get("type") or not enrichment.get("name"):
                raise HTTPException(
                    status_code=400,
                    detail="Each enrichment must have 'type' and 'name'"
                )
        
        # Store template (in production, this would be stored in database)
        template_data = {
            "name": name,
            "description": description,
            "asset_types": asset_types,
            "enrichments": enrichments,
            "created_at": datetime.utcnow().isoformat(),
            "id": f"template_{name}_{int(datetime.utcnow().timestamp())}"
        }
        
        return {
            "status": "created",
            "template": template_data
        }
        
    except HTTPException:
        raise
    except Exception as e:
        log_exception(f"Error creating enrichment template: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/templates")
async def list_enrichment_templates() -> Dict[str, Any]:
    """
    List available enrichment templates
    
    Returns predefined templates that can be used for common enrichment patterns.
    """
    try:
        # Built-in templates
        templates = [
            {
                "name": "equity_basic",
                "description": "Basic technical analysis for equities",
                "asset_types": ["equity"],
                "enrichments": [
                    {"type": "indicator", "name": "sma20", "params": {"indicator": "sma", "period": 20}},
                    {"type": "indicator", "name": "sma50", "params": {"indicator": "sma", "period": 50}},
                    {"type": "indicator", "name": "rsi", "params": {"indicator": "rsi", "period": 14}},
                    {"type": "volatility", "name": "volatility", "params": {"period": 20}}
                ]
            },
            {
                "name": "equity_advanced",
                "description": "Advanced technical analysis for equities",
                "asset_types": ["equity"],
                "enrichments": [
                    {"type": "indicator", "name": "sma20", "params": {"indicator": "sma", "period": 20}},
                    {"type": "indicator", "name": "ema12", "params": {"indicator": "ema", "period": 12}},
                    {"type": "indicator", "name": "rsi", "params": {"indicator": "rsi", "period": 14}},
                    {"type": "indicator", "name": "macd", "params": {"indicator": "macd"}},
                    {"type": "volatility", "name": "volatility", "params": {"period": 20}},
                    {"type": "risk_metrics", "name": "risk", "params": {"metrics": ["var", "sharpe"]}}
                ]
            },
            {
                "name": "options_greeks",
                "description": "Options Greeks and risk metrics",
                "asset_types": ["options"],
                "enrichments": [
                    {"type": "greeks", "name": "greeks", "params": {"model": "black-scholes"}},
                    {"type": "moneyness", "name": "moneyness", "params": {"reference": "spot"}},
                    {"type": "volatility", "name": "implied_vol", "params": {"type": "implied"}},
                    {"type": "risk_metrics", "name": "risk", "params": {"metrics": ["pin_risk", "time_decay"]}}
                ]
            },
            {
                "name": "futures_analysis",
                "description": "Futures basis and risk analysis",
                "asset_types": ["futures"],
                "enrichments": [
                    {"type": "moneyness", "name": "basis", "params": {"reference": "spot"}},
                    {"type": "volatility", "name": "volatility", "params": {"period": 20}},
                    {"type": "risk_metrics", "name": "risk", "params": {"metrics": ["dv01", "roll_risk"]}}
                ]
            },
            {
                "name": "crypto_metrics",
                "description": "Cryptocurrency-specific metrics",
                "asset_types": ["crypto"],
                "enrichments": [
                    {"type": "indicator", "name": "sma20", "params": {"indicator": "sma", "period": 20}},
                    {"type": "indicator", "name": "rsi", "params": {"indicator": "rsi", "period": 14}},
                    {"type": "volatility", "name": "volatility_24h", "params": {"period": 24}},
                    {"type": "risk_metrics", "name": "crypto_risk", "params": {"extreme_threshold": 0.1}}
                ]
            }
        ]
        
        return {
            "total": len(templates),
            "templates": templates
        }
        
    except Exception as e:
        log_exception(f"Error listing enrichment templates: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/capabilities")
async def get_enrichment_capabilities() -> Dict[str, Any]:
    """
    Get enrichment capabilities for different asset types
    
    Returns information about what enrichments are available for each asset type.
    """
    try:
        from app.services.computation_registry import computation_registry
        
        capabilities = {}
        
        # Get capabilities for each asset type
        for asset_type in ["equity", "futures", "options", "index", "commodity", "currency", "crypto"]:
            computations = computation_registry.list_computations(asset_type=asset_type)
            
            capabilities[asset_type] = {
                "total_computations": len(computations),
                "available_computations": [
                    {
                        "name": comp.name,
                        "description": comp.description,
                        "parameters": comp.parameters,
                        "tags": comp.tags
                    }
                    for comp in computations
                ]
            }
        
        return {
            "capabilities": capabilities,
            "universal_computations": [
                comp.name for comp in computation_registry.list_computations()
                if len(comp.asset_types) > 3  # Universal if supports many asset types
            ]
        }
        
    except Exception as e:
        log_exception(f"Error getting enrichment capabilities: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/validate")
async def validate_enrichment_request(
    request: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Validate an enrichment request without executing it
    
    Useful for the Historical Data Service to validate enrichment configurations
    before processing large batches of data.
    """
    try:
        from app.services.computation_registry import computation_registry
        
        enrichments = request.get("enrichments", [])
        asset_type = request.get("asset_type")
        
        if not enrichments:
            return {
                "valid": False,
                "errors": ["No enrichments specified"]
            }
        
        if not asset_type:
            return {
                "valid": False,
                "errors": ["Asset type is required"]
            }
        
        errors = []
        warnings = []
        
        for enrichment in enrichments:
            enrichment_type = enrichment.get("type")
            enrichment_name = enrichment.get("name")
            params = enrichment.get("params", {})
            
            if not enrichment_type:
                errors.append(f"Enrichment missing 'type': {enrichment}")
                continue
            
            if not enrichment_name:
                errors.append(f"Enrichment missing 'name': {enrichment}")
                continue
            
            # Check if computation exists
            computation = computation_registry.get_computation(enrichment_type)
            if not computation:
                errors.append(f"Unknown enrichment type: {enrichment_type}")
                continue
            
            # Check if asset type is supported
            if asset_type not in computation.asset_types:
                errors.append(
                    f"Enrichment '{enrichment_type}' not supported for asset type '{asset_type}'"
                )
                continue
            
            # Validate parameters
            try:
                computation_registry.validate_parameters(enrichment_type, params)
            except Exception as e:
                errors.append(f"Invalid parameters for '{enrichment_type}': {str(e)}")
        
        return {
            "valid": len(errors) == 0,
            "errors": errors if errors else None,
            "warnings": warnings if warnings else None,
            "enrichments_validated": len(enrichments)
        }
        
    except Exception as e:
        log_exception(f"Error validating enrichment request: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))