"""
Signal Service - Main Application
"""
import os
import sys
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Response

# Add common module to path for shared CORS config
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
from common.cors_config import add_cors_middleware

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan context manager for startup and shutdown.

    Handles:
    - Indicator registry initialization
    - Resource cleanup on shutdown
    """
    # Startup: Register all custom indicators
    logger.info("=" * 80)
    logger.info("Signal Service Starting Up")
    logger.info("=" * 80)

    try:
        from app.services.register_indicators import register_all_indicators
        register_all_indicators()
    except Exception as e:
        logger.error(f"Failed to register indicators: {e}")
        # Continue anyway - service can still work with pandas_ta

    logger.info("Signal Service startup complete")

    yield

    # Shutdown
    logger.info("Signal Service shutting down")


# Create FastAPI app with lifespan
app = FastAPI(
    title="Signal Service",
    description="Real-time market signal processing and analytics",
    version="1.0.0",
    lifespan=lifespan
)

# Add CORS middleware using shared configuration (no wildcards in production)
add_cors_middleware(app, environment=os.getenv("ENVIRONMENT", "production"))

# Include API routers (if they exist)
try:
    from app.api.v1.router import api_router
    app.include_router(api_router, prefix="/api/v1")
except ImportError:
    logger.warning("Could not import API router, skipping")

# Include v2 production signal routers (database-backed)
try:
    from app.api.v2 import realtime, historical, batch, websocket
    
    # Mount production routers with proper prefix
    api_prefix = "/api/v2/signals"
    app.include_router(realtime.router, prefix=api_prefix)
    app.include_router(historical.router, prefix=api_prefix)
    app.include_router(batch.router, prefix=api_prefix)
    app.include_router(websocket.router, prefix=api_prefix)
    
    logger.info("✓ Production signal routers included (database-backed)")
except ImportError as exc:
    logger.warning("Could not import production signal routers: %s", exc)
    
    # Fallback to test router if production routers fail
    try:
        from app.api.v2.router_test_fallback import router as v2_router
        app.include_router(v2_router)
        logger.warning("⚠️  Using test router as fallback")
    except ImportError:
        logger.error("No signal routers available!")

# Include v2 indicators router (real indicator calculations)
try:
    from app.api.v2.indicators import router as indicators_router
    app.include_router(indicators_router, prefix="/api/v2")
    logger.info("✓ Indicators router included")
except ImportError as exc:
    logger.warning("Could not import indicators router: %s", exc)

# Include v2 premium analysis router (Agent 2 implementation)
try:
    from app.api.v2.premium_analysis import router as premium_router
    app.include_router(premium_router, prefix="/api/v2")
    logger.info("✓ Premium analysis router included")
except ImportError as exc:
    logger.warning("Could not import premium analysis router: %s", exc)

# Sprint 5A: Include SDK signals router for unified signal delivery
try:
    from app.api.v2.sdk_signals import router as sdk_signals_router
    app.include_router(sdk_signals_router, prefix="/api/v2/signals")
    logger.info("✓ SDK signals router included (Sprint 5A)")
except ImportError as exc:
    logger.warning("Could not import SDK signals router: %s", exc)

# Sprint 5A: Include signal execution router for MinIO script execution
try:
    from app.api.v2.signal_execution import router as execution_router
    app.include_router(execution_router)
    logger.info("✓ Signal execution router included (Sprint 5A)")
except ImportError as exc:
    logger.warning("Could not import signal execution router: %s", exc)

# Sprint 5A: Include version policy router for author-controlled versioning
try:
    from app.api.v2.signal_version_policy import router as version_policy_router
    app.include_router(version_policy_router)
    logger.info("✓ Signal version policy router included (Sprint 5A)")
except ImportError as exc:
    logger.warning("Could not import signal version policy router: %s", exc)

# Architecture v3.0 - API Delegation Era: Signal delivery via service APIs
try:
    from app.services.signal_delivery_service import get_signal_delivery_service
    # Initialize signal delivery service for API delegation
    signal_delivery = get_signal_delivery_service()
    logger.info("✓ Signal delivery service initialized with API delegation to alert_service and comms_service")
except ImportError as exc:
    logger.warning("Could not import signal delivery service: %s", exc)

# Sprint 5A: Include email webhook router for inbound email processing
try:
    from app.api.v2.email_webhook import router as email_webhook_router
    app.include_router(email_webhook_router)
    logger.info("✓ Email webhook router included (Sprint 5A)")
except ImportError as exc:
    logger.warning("Could not import email webhook router: %s", exc)

# Production: Include monitoring router for observability and health checks
try:
    from app.api.monitoring import router as monitoring_router
    app.include_router(monitoring_router, prefix="/monitoring")
    logger.info("✓ Production monitoring router included")
except ImportError as exc:
    logger.warning("Could not import monitoring router: %s", exc)

# Production: Include health check router
try:
    from app.api.health import router as health_router
    app.include_router(health_router)
    logger.info("✓ Health check router included")
except ImportError as exc:
    logger.warning("Could not import health check router: %s", exc)

# Production: Include enhanced monitoring router for operations management
try:
    from app.api.enhanced_monitoring import router as enhanced_monitoring_router
    app.include_router(enhanced_monitoring_router)
    logger.info("✓ Enhanced monitoring router included - production operations ready")
except ImportError as exc:
    logger.warning("Could not import enhanced monitoring router: %s", exc)
    # Fallback to simple monitoring router
    try:
        from app.api.simple_monitoring import router as simple_monitoring_router
        app.include_router(simple_monitoring_router)
        logger.info("✓ Simple monitoring router included as fallback")
    except ImportError as fallback_exc:
        logger.warning("Could not import simple monitoring router: %s", fallback_exc)

@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "service": "signal_service",
        "version": "1.0.0",
        "status": "running"
    }

@app.get("/health")
async def health():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": "signal_service",
        "version": "1.0.0"
    }

@app.get("/metrics")
async def metrics():
    """Basic Prometheus-style metrics - secured for production."""
    # In production, this should be secured or replaced with real metrics
    environment = os.getenv('ENVIRONMENT', 'development')
    
    if environment in ['production', 'prod', 'staging']:
        # TODO: Replace with real Prometheus metrics or secure this endpoint
        # For now, return basic health indicator
        body = "\n".join([
            "# HELP signal_service_health Service health indicator",
            "# TYPE signal_service_health gauge", 
            "signal_service_health 1",
        ])
    else:
        # Development/test metrics with more details
        body = "\n".join([
            "# HELP signal_service_health Service health indicator",
            "# TYPE signal_service_health gauge",
            "signal_service_health 1",
            "# HELP signal_service_active_subscriptions Active subscription count",
            "# TYPE signal_service_active_subscriptions gauge",
            "signal_service_active_subscriptions 10",
        ])
    
    return Response(content=body, media_type="text/plain")


@app.get("/api/v2/admin/health")
async def admin_health():
    """Detailed health status - secured for production."""
    environment = os.getenv('ENVIRONMENT', 'development')
    
    # In production, this should be protected
    if environment in ['production', 'prod', 'staging']:
        # Check for admin authentication header
        # TODO: Implement proper admin authentication
        return {
            "status": "healthy",
            "message": "Admin endpoints require authentication in production",
            "environment": environment
        }
    else:
        # Development/test version with detailed status
        return {
            "status": "healthy",
            "database": "healthy", 
            "redis": "healthy",
            "signal_processor": "healthy",
        }


@app.get("/api/v2/admin/metrics")
async def admin_metrics():
    """Return metrics snapshot - secured for production."""
    environment = os.getenv('ENVIRONMENT', 'development')
    
    if environment in ['production', 'prod', 'staging']:
        # TODO: Implement authentication for admin endpoints
        return {
            "message": "Admin metrics require authentication in production",
            "environment": environment
        }
    else:
        # Development/test stub metrics
        return {
            "backpressure_level": "LOW",
            "active_subscriptions": 10,
            "processed_signals": 100,
        }


@app.get("/api/v2/admin/audit-trail")
async def admin_audit_trail(user_id: str = None, limit: int = 10):
    """Audit trail endpoint - secured for production."""
    environment = os.getenv('ENVIRONMENT', 'development')
    
    if environment in ['production', 'prod', 'staging']:
        # TODO: Implement authentication for admin endpoints
        return {
            "message": "Audit trail requires authentication in production",
            "environment": environment
        }
    else:
        # Development/test stub data
        entries = [{"user_id": user_id or "test", "action": "access", "timestamp": "2024-01-01T00:00:00Z"}]
        return {"entries": entries[:limit]}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8003)
