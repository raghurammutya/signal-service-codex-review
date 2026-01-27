"""Updates to signal_service main.py for timeframe aggregation"""
import asyncio
import logging

from fastapi import FastAPI, HTTPException

from app.core.config import signal_settings

# Add these imports to the existing imports
from app.services.custom_indicators import register_custom_indicators
from app.services.historical_data_writer import get_historical_data_writer


def stop_service():
    """Placeholder for existing stop service function"""

logger = logging.getLogger(__name__)

def log_info(message: str):
    """Log info message"""
    logger.info(message)

def log_exception(message: str):
    """Log exception message"""
    logger.error(message)

# This would typically be initialized in main.py
app = FastAPI()


# Add to the initialize_signal_service function after existing initializations:
async def initialize_signal_service_additions():
    """Additional initializations for timeframe aggregation"""

    # Register custom indicators with pandas_ta
    try:
        register_custom_indicators()
        log_info("✅ Custom indicators registered (anchored_vwap, swing_high, swing_low)")
    except Exception as e:
        log_exception(f"Failed to register custom indicators: {e}")
        # Non-fatal - continue without custom indicators

    # Initialize and start historical data writer
    if signal_settings.ENABLE_HISTORICAL_WRITER:
        try:
            writer = await get_historical_data_writer()
            await writer.start()
            app.state.historical_data_writer = writer
            log_info("✅ Historical data writer started")
        except Exception as e:
            log_exception(f"Failed to start historical data writer: {e}")
            # Non-fatal - continue without historical writer

    # Initialize timeframe cache manager
    try:
        from app.services.timeframe_cache_manager import TimeframeCacheManager
        cache_manager = TimeframeCacheManager()
        await cache_manager.initialize()
        app.state.timeframe_cache_manager = cache_manager
        log_info("✅ Timeframe cache manager initialized")

        # Start cache cleanup task
        asyncio.create_task(cache_manager.cleanup_task())
    except Exception as e:
        log_exception(f"Failed to initialize timeframe cache manager: {e}")


# Add to startup event after existing initialization
# In the signal_service_startup function, after initialize_signal_service():
"""
    # Initialize signal service components
    try:
        await initialize_signal_service()
        await initialize_signal_service_additions()  # Add this line
    except Exception as e:
        log_exception(f"❌ Component initialization failed: {e}")
        # Continue startup with degraded functionality
        app.state.is_healthy = False
"""

# Add shutdown event handler
@app.on_event("shutdown")
async def signal_service_shutdown():
    """Graceful shutdown for signal service"""
    log_info("🛑 Signal service shutdown initiated")

    try:
        # Stop historical data writer
        if hasattr(app.state, 'historical_data_writer'):
            await app.state.historical_data_writer.stop()
            log_info("✅ Historical data writer stopped")

        # Stop timeframe cache manager
        if hasattr(app.state, 'timeframe_cache_manager'):
            await app.state.timeframe_cache_manager.stop()
            log_info("✅ Timeframe cache manager stopped")

        # Existing shutdown logic...
        await stop_service()

    except Exception as e:
        log_exception(f"Error during shutdown: {e}")


# Add new endpoints for monitoring
@app.get("/api/v1/timeframe-aggregation/status")
async def get_timeframe_aggregation_status():
    """Get status of timeframe aggregation components"""
    status = {
        "historical_writer": {
            "enabled": signal_settings.ENABLE_HISTORICAL_WRITER,
            "running": False
        },
        "custom_indicators": {
            "registered": False,
            "available": []
        },
        "cache_manager": {
            "initialized": False,
            "cache_count": 0
        }
    }

    # Check historical writer
    if hasattr(app.state, 'historical_data_writer'):
        status["historical_writer"]["running"] = app.state.historical_data_writer.running

    # Check custom indicators
    try:
        import pandas_ta as ta
        custom_indicators = ['anchored_vwap', 'swing_high', 'swing_low', 'combined_premium', 'premium_ratio']
        available = [ind for ind in custom_indicators if ind in ta.CUSTOM_TA]
        status["custom_indicators"]["registered"] = len(available) > 0
        status["custom_indicators"]["available"] = available
    except:
        pass

    # Check cache manager
    if hasattr(app.state, 'timeframe_cache_manager'):
        status["cache_manager"]["initialized"] = True
        status["cache_manager"]["cache_count"] = len(app.state.timeframe_cache_manager.cache_registry)

    return status


@app.post("/api/v1/timeframe-aggregation/force-write")
async def force_historical_write():
    """Force write current minute data (for testing)"""
    if not hasattr(app.state, 'historical_data_writer'):
        raise HTTPException(status_code=503, detail="Historical data writer not initialized")

    try:
        await app.state.historical_data_writer.force_write_current_minute()
        return {"status": "success", "message": "Forced write completed"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
