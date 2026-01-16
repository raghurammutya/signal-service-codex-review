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

    # Initialize health checking
    try:
        from app.api.health import initialize_health_checker, initialize_distributed_health, start_health_monitoring
        from app.core.redis_manager import get_redis_client
        from common.storage.database import get_timescaledb_session
        
        # Initialize health dependencies
        redis_client = await get_redis_client()
        
        # Pass the session factory function, not a session instance
        initialize_health_checker(redis_client, get_timescaledb_session)
        
        initialize_distributed_health(redis_client)
        await start_health_monitoring()
        
        logger.info("Health monitoring initialized")
    except Exception as e:
        logger.error(f"Failed to initialize health monitoring: {e}")
        # Continue anyway - basic health endpoint will still work

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
# Get environment from config_service (Architecture Principle #1: Config service exclusivity)
try:
    from app.core.config import settings
    cors_environment = settings.environment
except Exception as e:
    # Fail-fast if config not available
    raise RuntimeError(f"Failed to get environment from config_service for CORS: {e}. No environment fallbacks allowed per architecture.")

add_cors_middleware(app, environment=cors_environment)

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
    logger.error("Failed to import production signal routers: %s", exc)
    
    # In production, NEVER fall back to test routers
    # Get environment from config_service (Architecture Principle #1: Config service exclusivity)
    try:
        from app.core.config import settings
        environment = settings.environment
    except Exception as e:
        raise RuntimeError(f"Failed to get environment from config_service for router selection: {e}. No environment fallbacks allowed per architecture.")
    
    # No environment-based fallbacks allowed per architecture - fail fast in all environments
    logger.critical("🚨 DEPLOYMENT BLOCKED: Critical import failure")
    logger.critical("Cannot load production signal routers - this is a critical configuration issue")
    logger.critical(f"Import error: {exc}")
    logger.critical("No test router fallbacks allowed per Architecture Principle #1")
    raise RuntimeError(f"Signal router deployment failed: {exc}. No fallbacks allowed per architecture.")

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
    app.include_router(monitoring_router, prefix="/api/v2")
    logger.info("✓ Production monitoring router included with versioned API")
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
    app.include_router(enhanced_monitoring_router, prefix="/api/v2")
    logger.info("✓ Enhanced monitoring router included with versioned API - production operations ready")
except ImportError as exc:
    logger.warning("Could not import enhanced monitoring router: %s", exc)
    # Fallback to simple monitoring router
    try:
        from app.api.simple_monitoring import router as simple_monitoring_router
        app.include_router(simple_monitoring_router, prefix="/api/v2")
        logger.info("✓ Simple monitoring router included as versioned fallback")
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

# Removed duplicate health endpoint - use centralized health router only 
# (Architecture compliance: single route per functionality)

# Environment-based endpoint registration
# Get environment from config_service (Architecture Principle #1: Config service exclusivity)
try:
    from app.core.config import settings
    environment = settings.environment
except Exception as e:
    raise RuntimeError(f"Failed to get environment from config_service for endpoint registration: {e}. No environment fallbacks allowed per architecture.")

if environment not in ['production', 'prod', 'staging']:
    # Development/test endpoints only
    @app.get("/metrics")
    async def metrics():
        """Basic Prometheus-style metrics - development only."""
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
        """Detailed health status - development only."""
        # Get real health status from health checker if available
        try:
            from app.api.health import get_health_checker
            checker = get_health_checker()
            if checker:
                detailed_health = await checker.check_health(detailed=True)
                return {
                    "status": detailed_health.get("status", "unknown"),
                    "database": detailed_health.get("database", {}).get("status", "unknown"),
                    "redis": detailed_health.get("redis", {}).get("status", "unknown"), 
                    "signal_processor": detailed_health.get("signal_processor", {}).get("status", "unknown"),
                    "details": detailed_health
                }
        except Exception as e:
            logger.warning(f"Could not get detailed health: {e}")
        
        # Fallback for development
        return {
            "status": "healthy",
            "database": "healthy", 
            "redis": "healthy",
            "signal_processor": "healthy",
            "note": "Development fallback - real health checking unavailable"
        }

    @app.get("/api/v2/admin/metrics")
    async def admin_metrics():
        """Return metrics snapshot - development only."""
        # Try to get real metrics
        try:
            # Get basic system metrics
            import psutil
            cpu_percent = psutil.cpu_percent(interval=0.1)
            memory = psutil.virtual_memory()
            
            # Try to get Redis-based metrics if available
            active_subscriptions = 0
            processed_signals = 0
            try:
                from app.utils.redis import get_redis_client
                redis_client = await get_redis_client()
                
                # Get subscription count if keys exist
                sub_keys = await redis_client.keys("subscription:*")
                active_subscriptions = len(sub_keys) if sub_keys else 0
                
                # Get signal count if available
                signal_count = await redis_client.get("metrics:signals_processed")
                processed_signals = int(signal_count) if signal_count else 0
                
            except Exception:
                # Redis unavailable, use fallback values
                pass
            
            # Determine backpressure based on system load
            backpressure_level = "LOW"
            if cpu_percent > 80 or memory.percent > 90:
                backpressure_level = "HIGH"
            elif cpu_percent > 60 or memory.percent > 75:
                backpressure_level = "MEDIUM"
                
            return {
                "backpressure_level": backpressure_level,
                "active_subscriptions": active_subscriptions,
                "processed_signals": processed_signals,
                "cpu_percent": round(cpu_percent, 1),
                "memory_percent": round(memory.percent, 1),
                "note": "Development metrics with real system data"
            }
            
        except Exception as e:
            logger.warning(f"Could not get real metrics: {e}")
            # Fallback to static values with clear indication
            return {
                "backpressure_level": "LOW",
                "active_subscriptions": 0,
                "processed_signals": 0,
                "note": "Development fallback - real metrics unavailable"
            }

    @app.get("/api/v2/admin/audit-trail")
    async def admin_audit_trail(user_id: str = None, limit: int = 10):
        """Audit trail endpoint - development only."""
        entries = [{"user_id": user_id or "test", "action": "access", "timestamp": "2024-01-01T00:00:00Z"}]
        return {"entries": entries[:limit]}
else:
    # Production: Admin endpoints are completely disabled
    logger.info("Admin endpoints disabled in production environment")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8003)
