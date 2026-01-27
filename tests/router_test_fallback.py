"""Lightweight v2 API router with in-memory behavior for tests and dev."""

import asyncio
import json
from datetime import datetime, timedelta
from typing import Any

import pandas as pd
from fastapi import APIRouter, HTTPException, Query, WebSocket, WebSocketDisconnect

from app.core.config import settings
from app.utils.redis import get_redis_client

# PRODUCTION SAFETY: Prevent test router from being used in production
if settings.environment.lower() in ['production', 'prod', 'staging']:
    raise RuntimeError(
        "Test fallback router cannot be used in production environment. "
        "This router contains synthetic test data and should only be used in development/testing."
    )

router = APIRouter(prefix="/api/v2/signals", tags=["signals"])

# Simple in-memory state so tests can observe side effects without external services.
STATE: dict[str, Any] = {
    "latest_greeks": {},          # instrument_key -> greeks payload
    "historical_greeks": {},      # instrument_key -> list of greeks snapshots
    "frequency_subs": [],         # list of subscription dicts
    "audit": [],                  # list of audit entries
    "ws_subscriptions": {},       # websocket -> list of subscription dicts
}
WS_CLIENTS: list[WebSocket] = []


def _compute_stub_greeks(price: float) -> dict[str, Any]:
    """Deterministic but simple greeks calculation for tests."""
    delta = round(min(max(price / 1000.0, 0.05), 0.95), 3)
    return {
        "delta": delta,
        "gamma": 0.01,
        "theta": -0.02,
        "vega": 0.1,
        "rho": 0.05,
    }


async def _broadcast_signal(instrument_key: str, channel: str, payload: dict[str, Any]):
    """Send updates to any subscribed websocket clients."""
    if not WS_CLIENTS:
        return
    message = {
        "type": "signal_update",
        "channel": channel,
        "instrument": instrument_key,
        "data": payload,
        "timestamp": datetime.utcnow().isoformat(),
    }
    coros = []
    for ws in list(WS_CLIENTS):
        subs = STATE["ws_subscriptions"].get(ws, [])
        if any(sub.get("instrument") == instrument_key and sub.get("channel") == channel for sub in subs):
            coros.append(ws.send_text(json.dumps(message)))
    if coros:
        await asyncio.gather(*coros, return_exceptions=True)


async def _cache_greeks(instrument_key: str, greeks: dict[str, Any]):
    """Persist latest greeks into fake Redis and in-memory history."""
    redis = await get_redis_client()
    greeks_payload = {**greeks, "timestamp": datetime.utcnow().isoformat()}
    cache_key = f"signal:latest:{instrument_key}:greeks"
    await redis.set(cache_key, json.dumps(greeks_payload))
    STATE["latest_greeks"][instrument_key] = greeks_payload
    STATE["historical_greeks"].setdefault(instrument_key, []).append(greeks_payload)
    return greeks_payload


@router.post("/process-tick")
async def process_tick(tick_data: dict[str, Any]):
    """Process a tick by computing simple greeks and caching the result."""
    instrument_key = tick_data.get("instrument_key")
    if not instrument_key or "last_price" not in tick_data:
        raise HTTPException(status_code=400, detail="Invalid tick payload")
    greeks = _compute_stub_greeks(float(tick_data["last_price"]))
    greeks_payload = await _cache_greeks(instrument_key, greeks)
    await _broadcast_signal(instrument_key, "greeks", greeks_payload)
    STATE["audit"].append({"event": "process_tick", "instrument_key": instrument_key, "ts": datetime.utcnow().isoformat()})
    return {"status": "processed", "instrument_key": instrument_key, "greeks": greeks_payload}


@router.post("/subscriptions/frequency")
async def set_frequency_subscription(subscription: dict[str, Any]):
    """Store a frequency subscription so tests can assert side effects."""
    STATE["frequency_subs"].append(subscription)
    user_id = subscription.get("user_id", "unknown")
    channel = f"signal:frequency:{user_id}:{subscription.get('instrument')}:{subscription.get('signal_type')}"
    redis = await get_redis_client()
    aggregated = {"aggregated_greeks": _compute_stub_greeks(21500.0), **subscription}
    await redis.set(channel, json.dumps({**aggregated, "frequency": subscription.get("frequency")}))
    return {"status": "subscribed", "subscription": subscription}


@router.get("/realtime/greeks/{instrument_key}")
async def realtime_greeks(instrument_key: str) -> dict[str, Any]:
    """Return the latest cached greeks for an instrument (or stub)."""
    if "INVALID" in instrument_key.upper():
        raise HTTPException(status_code=404, detail="instrument not found")
    payload = STATE["latest_greeks"].get(instrument_key)
    if not payload:
        payload = await _cache_greeks(instrument_key, _compute_stub_greeks(21500.0))
    return {"instrument_key": instrument_key, "timestamp": payload["timestamp"], "greeks": {k: v for k, v in payload.items() if k != "timestamp"}}


@router.get("/realtime/indicators/{instrument_token}/{indicator}")
async def realtime_indicator(instrument_token: int, indicator: str, period: int = Query(14, ge=1, le=200)) -> dict[str, Any]:
    """
    Real-time indicator calculation endpoint.

    ⚠️  DEPRECATED: Use POST /api/v2/indicators/calculate/dynamic/{indicator} for full functionality.
    ⚠️  LEGACY: This endpoint uses instrument_token instead of instrument_key (signal_service standard).
    ⚠️  TODO: Remove this endpoint - use the new instrument_key-based APIs instead.

    Args:
        instrument_token: Kite instrument token (e.g., 256265) - LEGACY FORMAT
        indicator: Indicator name (e.g., rsi, sma, ema)
        period: Period for indicator calculation
    """
    from app.api.v2.indicators import indicator_calculator

    try:
        # Map common timeframes
        timeframe = "5minute"  # Default to 5-minute data

        # LEGACY: Fetch historical data using instrument_token
        # TODO: This should be updated to use instrument_key when endpoint is modernized
        df = await indicator_calculator.get_historical_data(
            instrument_token=instrument_token,
            timeframe=timeframe,
            periods=max(period * 2 + 50, 100)  # Ensure enough data
        )

        if df.empty:
            raise HTTPException(status_code=404, detail=f"No data found for instrument_token={instrument_token} (LEGACY)")

        # Calculate indicator
        result_df = await indicator_calculator.calculate_dynamic_indicator(
            df, indicator, length=period
        )

        # Extract latest value
        if len(result_df.columns) == 1:
            value = result_df.iloc[-1, 0]
            if pd.isna(value):
                value = None
            else:
                value = round(float(value), 4)
        else:
            # Multiple columns - return first column's value
            value = round(float(result_df.iloc[-1, 0]), 4)

        return {
            "instrument_token": instrument_token,  # LEGACY - should be instrument_key
            "indicator": indicator,
            "period": period,
            "value": value,
            "timestamp": df.index[-1].isoformat() if not df.empty else datetime.utcnow().isoformat(),
        }

    except HTTPException:
        raise
    except Exception as e:
        # Log error and return informative message
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=f"Error calculating indicator: {str(e)}. Use POST /api/v2/indicators/calculate/dynamic/{indicator} for full control."
        )


@router.get("/realtime/moneyness/{underlying}/greeks/{moneyness_level}")
async def realtime_moneyness_greeks(underlying: str, moneyness_level: str):
    """Return stubbed moneyness greeks payload."""
    greeks = _compute_stub_greeks(underlying.__hash__() % 10000 / 10 or 100.0)
    greeks["iv"] = 0.2
    return {
        "underlying": underlying,
        "moneyness_level": moneyness_level,
        "aggregated_greeks": {"all": {**greeks, "count": 1}},
        "timestamp": datetime.utcnow().isoformat(),
        "greeks": greeks,
    }


@router.get("/realtime/moneyness/{underlying}/atm-iv")
async def realtime_atm_iv(underlying: str, expiry_date: str, timeframe: str = Query("5m", pattern="^[0-9]+m$")):
    """Return stub ATM IV response."""
    return {"underlying": underlying, "moneyness": "ATM", "iv": 0.25, "expiry": expiry_date, "timeframe": timeframe}


@router.get("/realtime/moneyness/{underlying}/otm-delta")
async def realtime_otm_delta(underlying: str, delta: float, option_type: str, expiry_date: str = None):
    """Return stub delta-matched greeks."""
    return {
        "underlying": underlying,
        "delta_target": delta,
        "option_type": option_type,
        "greeks": {"delta": delta, "gamma": 0.01, "theta": -0.02, "vega": 0.1, "rho": 0.05},
        "timestamp": datetime.utcnow().isoformat(),
    }


@router.get("/historical/greeks/{instrument_key}")
async def historical_greeks(instrument_key: str, start_time: str = "", end_time: str = "", timeframe: str = "5m"):
    """Return historical greeks from in-memory cache."""
    if "INVALID" in instrument_key.upper():
        raise HTTPException(status_code=404, detail="invalid instrument")
    series = STATE["historical_greeks"].get(instrument_key, [])
    if not series:
        now = datetime.utcnow()
        series = [
            {"timestamp": (now - timedelta(minutes=idx * 5)).isoformat(), "delta": 0.5, "gamma": 0.01, "iv": 0.2, "value": {"iv": 0.2, "strike_count": 3}}
            for idx in range(3)
        ]
    metadata: dict[str, Any] = {"timeframe": timeframe, "requested_start": start_time, "requested_end": end_time}
    if instrument_key.startswith("MONEYNESS@"):
        parts = instrument_key.split("@")
        metadata.update({"moneyness_level": parts[2] if len(parts) > 2 else "ATM", "underlying": parts[1] if len(parts) > 1 else ""})
    return {"instrument_key": instrument_key, "timeframe": timeframe, "time_series": series, "metadata": metadata}


@router.get("/historical/moneyness/{underlying}/greeks/{moneyness_level}")
async def historical_moneyness_greeks(underlying: str, moneyness_level: str, start_time: str, end_time: str, timeframe: str = "15m"):
    now = datetime.utcnow()
    series = [
        {"timestamp": (now - timedelta(minutes=idx * 15)).isoformat(), "value": {"iv": 0.2 + idx * 0.01, "strike_count": 5}}
        for idx in range(3)
    ]
    return {"underlying": underlying, "moneyness_level": moneyness_level, "timeframe": timeframe, "time_series": series}


@router.get("/historical/indicators/{instrument_key}/{indicator}")
async def historical_indicators(instrument_key: str, indicator: str, start_time: str, end_time: str, timeframe: str = "5m"):
    """Return stub historical indicators."""
    now = datetime.utcnow()
    series = [
        {"timestamp": (now - timedelta(minutes=idx * 5)).isoformat(), "value": 42.0}
        for idx in range(3)
    ]
    return {"instrument_key": instrument_key, "indicator": indicator, "timeframe": timeframe, "time_series": series}


@router.get("/historical/available-timeframes/{instrument_key}")
async def available_timeframes(instrument_key: str, signal_type: str):
    """Return available timeframes list."""
    standard = ["1m", "5m", "15m", "1h"]
    custom = ["7m"]
    return {
        "instrument_key": instrument_key,
        "signal_type": signal_type,
        "standard_timeframes": standard,
        "custom_timeframes": custom,
        "all_timeframes": sorted(set(standard + custom)),
    }


def _build_market_profile_payload(instrument_key: str) -> dict[str, Any]:
    price_levels = [100.0 + i for i in range(10)]
    volumes = [100 + i * 50 for i in range(10)]
    value_area = {"vah": max(price_levels), "val": min(price_levels), "poc": price_levels[volumes.index(max(volumes))], "volume_percentage": 70}
    profile = {"price_levels": price_levels, "volumes": volumes, "value_area": value_area, "poc": value_area["poc"]}
    market_structure = {"pattern": "Normal Day", "distribution_shape": "balanced", "balance_area": {}, "peaks": [value_area["poc"], price_levels[-1]]}
    return {"profile": profile, "metadata": {"instrument_key": instrument_key}, "market_structure": market_structure}


@router.get("/market-profile/{instrument_key}")
async def market_profile(instrument_key: str, interval: str = "30m", lookback_period: str = "1d", profile_type: str = "volume"):
    """Return stub market profile payload."""
    if "INVALID" in instrument_key.upper():
        raise HTTPException(status_code=404, detail="invalid instrument")
    payload = _build_market_profile_payload(instrument_key)
    payload["metadata"].update({"interval": interval, "lookback_period": lookback_period, "profile_type": profile_type})
    return payload


@router.get("/market-profile/{instrument_key}/developing")
async def developing_profile(instrument_key: str, interval: str = "30m"):
    developing = {
        "current_poc": 100.0,
        "current_value_area": {"vah": 105.0, "val": 95.0, "poc": 100.0, "volume_percentage": 70},
        "time_progression": 5,
    }
    return {
        "developing_profile": developing,
        "completion_percentage": 50,
        "estimated_final_structure": {"pattern": "Developing", "peaks": [100.0]},
    }


@router.post("/batch/compute")
async def batch_compute(request: dict[str, Any]):
    instruments = request.get("instruments", [])
    results = []
    start = datetime.utcnow()
    for inst in instruments:
        greeks = _compute_stub_greeks(21500.0)
        results.append({"instrument_key": inst, "greeks": greeks})
        await _cache_greeks(inst, greeks)
    duration_ms = int((datetime.utcnow() - start).total_seconds() * 1000)
    return {"results": results, "metadata": {"processing_time_ms": duration_ms, "count": len(results)}}


@router.post("/batch/historical-iv")
async def batch_historical_iv(request: dict[str, Any]):
    strikes = request.get("strikes", [])
    now = datetime.utcnow()
    surface = {
        "strikes": strikes,
        "time_series": [
            {"timestamp": (now - timedelta(hours=i)).isoformat(), "iv": 0.2 + i * 0.01, "strike": strike}
            for i, strike in enumerate(strikes[:3])
        ],
    }
    analysis = {"iv_skew": "neutral", "term_structure": "contango"}
    return {"iv_surface": surface, "analysis": analysis}


@router.post("/batch/option-chain")
async def option_chain(request: dict[str, Any]):
    underlying = request.get("underlying")  # No default - require explicit underlying
    if not underlying:
        raise HTTPException(status_code=400, detail="underlying parameter is required")
    expiry = request.get("expiry", datetime.utcnow().date().isoformat())
    strikes = request.get("strikes", "100,200,300")
    strike_list = [s for s in str(strikes).split(",") if s]
    options = [{"strike": float(s), "type": "call", "iv": 0.2, "underlying": underlying, "expiry": expiry} for s in strike_list]
    return {"options": options}


@router.post("/batch/iv-surface")
async def iv_surface(request: dict[str, Any]):
    underlying = request.get("underlying")  # No default - require explicit underlying
    if not underlying:
        raise HTTPException(status_code=400, detail="underlying parameter is required")
    analysis_type = request.get("analysis_type", "skew")
    surface = {"underlying": underlying, "analysis_type": analysis_type, "points": [{"strike": 100, "iv": 0.2}]}
    return {"surface": surface}


@router.get("/subscriptions/websocket")
async def websocket_info():
    """Provide WebSocket connection info (also ensures OpenAPI path exists)."""
    return {"status": "ready", "url": "ws://localhost:8003/api/v2/signals/subscriptions/websocket"}


@router.websocket("/subscriptions/websocket")
async def websocket_endpoint(websocket: WebSocket, client_id: str | None = None):
    await websocket.accept()
    WS_CLIENTS.append(websocket)
    STATE["ws_subscriptions"][websocket] = []
    try:
        while True:
            message = await websocket.receive_text()
            try:
                data = json.loads(message)
            except Exception:
                await websocket.send_text(json.dumps({"type": "error", "message": "invalid_json"}))
                continue
            msg_type = data.get("type")
            if msg_type == "subscribe":
                subscription = {
                    "channel": data.get("channel"),
                    "instrument": data.get("instrument") or data.get("instrument_key"),
                    "params": data.get("params", {}),
                }
                STATE["ws_subscriptions"][websocket].append(subscription)
                await websocket.send_text(json.dumps({"type": "subscription_confirmed", **subscription}))
            elif msg_type == "unsubscribe":
                STATE["ws_subscriptions"][websocket] = []
                await websocket.send_text(json.dumps({"type": "subscription_cancelled"}))
            else:
                await websocket.send_text(json.dumps({"type": "ack"}))
    except WebSocketDisconnect:
        STATE["ws_subscriptions"].pop(websocket, None)
        if websocket in WS_CLIENTS:
            WS_CLIENTS.remove(websocket)
