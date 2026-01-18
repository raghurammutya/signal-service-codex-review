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

# Configure logging with security filters
from app.utils.logging_security import configure_secure_logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
configure_secure_logging()
logger = logging.getLogger(__name__)


async def _register_application_hot_reload_handlers():
    """Register hot reload handlers for application components."""
    from app.core.hot_config import hot_reloadable_settings
    
    # Database connection pool hot reload handler
    async def handle_database_pool_refresh(new_database_url: str):
        """Handle database connection pool refresh."""
        try:
            from app.dependencies import get_database_manager
            db_manager = get_database_manager()
            if hasattr(db_manager, 'refresh_connection_pool'):
                await db_manager.refresh_connection_pool(new_database_url)
                logger.info("✓ Database connection pool refreshed")
            else:
                logger.info("Database manager does not support hot refresh")
        except Exception as e:
            logger.error(f"Failed to refresh database connection pool: {e}")
    
    # Redis connection hot reload handler
    async def handle_redis_connection_refresh(new_redis_url: str):
        """Handle Redis connection refresh."""
        try:
            from app.dependencies import get_redis_manager
            redis_manager = get_redis_manager()
            if hasattr(redis_manager, 'refresh_connection'):
                await redis_manager.refresh_connection(new_redis_url)
                logger.info("✓ Redis connection refreshed")
            else:
                logger.info("Redis manager does not support hot refresh")
        except Exception as e:
            logger.error(f"Failed to refresh Redis connection: {e}")
    
    # API key refresh handler for service clients
    async def handle_api_key_refresh(new_api_key: str):
        """Handle internal API key refresh for service clients."""
        try:
            from app.clients.client_factory import refresh_api_keys
            await refresh_api_keys(new_api_key)
            logger.info("✓ Service client API keys refreshed")
        except Exception as e:
            logger.error(f"Failed to refresh API keys: {e}")
    
    # Service URL refresh handler
    async def handle_service_url_refresh(url_data: dict):
        """Handle service URL refresh for HTTP clients."""
        try:
            from app.clients.client_factory import refresh_service_url
            await refresh_service_url(url_data['service'], url_data['url'])
            logger.info(f"✓ Service URL refreshed: {url_data['service']} -> {url_data['url']}")
        except Exception as e:
            logger.error(f"Failed to refresh service URL: {e}")
    
    # Performance settings refresh handler
    async def handle_performance_setting_refresh(setting_data: dict):
        """Handle performance setting refresh."""
        try:
            setting_name = setting_data['setting']
            new_value = setting_data['value']
            
            # Update relevant components based on setting
            if setting_name == "CACHE_TTL_SECONDS":
                # Update cache TTL for relevant services
                logger.info(f"✓ Cache TTL updated to {new_value} seconds")
            elif setting_name == "MAX_BATCH_SIZE":
                # Update batch processing limits
                logger.info(f"✓ Max batch size updated to {new_value}")
            elif setting_name == "SERVICE_INTEGRATION_TIMEOUT":
                # Update HTTP client timeouts
                from app.clients.client_factory import update_client_timeouts
                await update_client_timeouts(new_value)
                logger.info(f"✓ Service integration timeout updated to {new_value}s")
            
        except Exception as e:
            logger.error(f"Failed to refresh performance setting: {e}")
    
    # Feature flag refresh handler
    async def handle_feature_flag_refresh(flag_data: dict):
        """Handle feature flag refresh."""
        try:
            feature_name = flag_data['feature']
            enabled = flag_data['enabled']
            
            # Update application feature flags
            if not hasattr(app.state, 'feature_flags'):
                app.state.feature_flags = {}
            app.state.feature_flags[feature_name] = enabled
            
            logger.info(f"✓ Feature flag {feature_name} updated: {enabled}")
        except Exception as e:
            logger.error(f"Failed to refresh feature flag: {e}")
    
    # Watermark configuration refresh handler
    async def handle_watermark_config_refresh(config_data: dict):
        """Handle watermark configuration refresh."""
        try:
            parameter = config_data['parameter']
            value = config_data['value']
            
            # Update watermark service configuration
            from app.services.watermark_service import refresh_watermark_config
            await refresh_watermark_config(parameter, value)
            
            logger.info(f"✓ Watermark config {parameter} updated")
        except Exception as e:
            logger.error(f"Failed to refresh watermark config: {e}")
    
    # Register all handlers
    hot_reloadable_settings.register_hot_reload_handler("database_pool_refresh", handle_database_pool_refresh)
    hot_reloadable_settings.register_hot_reload_handler("redis_connection_refresh", handle_redis_connection_refresh)
    hot_reloadable_settings.register_hot_reload_handler("api_key_refresh", handle_api_key_refresh)
    hot_reloadable_settings.register_hot_reload_handler("service_url_refresh", handle_service_url_refresh)
    hot_reloadable_settings.register_hot_reload_handler("performance_setting_refresh", handle_performance_setting_refresh)
    hot_reloadable_settings.register_hot_reload_handler("feature_flag_refresh", handle_feature_flag_refresh)
    hot_reloadable_settings.register_hot_reload_handler("watermark_config_refresh", handle_watermark_config_refresh)
    
    logger.info("✓ Application hot reload handlers registered")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan context manager for startup and shutdown.

    Handles:
    - Hot parameter reloading initialization
    - Indicator registry initialization
    - Resource cleanup on shutdown
    """
    # Startup: Validate dependencies with resilience
    logger.info("=" * 80)
    logger.info("Signal Service Starting Up with Hot Parameter Reloading")
    logger.info("=" * 80)

    # Initialize hot parameter reloading system
    from app.core.hot_config import hot_reloadable_settings
    try:
        # Security: Hot reload OFF by default - explicit enablement required
        enable_hot_reload = os.getenv("ENABLE_HOT_RELOAD", "false").lower() == "true"
        await hot_reloadable_settings.initialize_hot_reload(enable_hot_reload=enable_hot_reload)
        logger.info("✓ Hot parameter reloading system initialized")
    except Exception as e:
        logger.warning(f"Hot parameter reloading initialization failed: {e}")
        logger.info("Service will continue without hot reloading capability")

    # Startup resilience validation
    from app.core.startup_resilience import validate_startup_dependencies
    try:
        dependencies_healthy = await validate_startup_dependencies()
        if not dependencies_healthy:
            logger.critical("Critical dependencies failed startup validation")
            raise RuntimeError("Service cannot start - critical dependencies unavailable")
    except Exception as e:
        logger.critical(f"Startup dependency validation failed: {e}")
        raise

    try:
        from app.services.register_indicators import register_all_indicators
        register_all_indicators()
        logger.info("All indicators registered successfully")
    except Exception as e:
        logger.error(f"CRITICAL: Failed to register indicators: {e}")
        raise RuntimeError(f"Indicator registration is required for service operation: {e}") from e

<<<<<<< HEAD
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
=======
    # Register hot reload handlers for application components
    await _register_application_hot_reload_handlers()

    logger.info("Signal Service startup complete with hot reloading support")
>>>>>>> compliance-violations-fixed

    yield

    # Shutdown: Cleanup all managed clients and hot reload system
    logger.info("Signal Service shutting down")
    
    # Shutdown hot reload system
    try:
        await hot_reloadable_settings.shutdown_hot_reload()
        logger.info("Hot reload system shutdown successfully")
    except Exception as e:
        logger.error(f"Error during hot reload shutdown: {e}")
    
    try:
        from app.clients.client_factory import shutdown_all_clients
        await shutdown_all_clients()
        logger.info("All service clients shutdown successfully")
    except Exception as e:
        logger.error(f"Error during client shutdown: {e}")

    logger.info("Signal Service shutdown complete")


# Create FastAPI app with lifespan
app = FastAPI(
    title="Signal Service",
    description="Real-time market signal processing and analytics",
    version="1.0.0",
    lifespan=lifespan
)

<<<<<<< HEAD
# Add CORS middleware using shared configuration (no wildcards in production)
# Get environment from config_service (Architecture Principle #1: Config service exclusivity)
try:
    from app.core.config import settings
    cors_environment = settings.environment
except Exception as e:
    # Fail-fast if config not available
    raise RuntimeError(f"Failed to get environment from config_service for CORS: {e}. No environment fallbacks allowed per architecture.")

add_cors_middleware(app, environment=cors_environment)
=======
# Add CORS middleware using shared configuration - get environment from config_service
from app.core.config import settings
add_cors_middleware(app, environment=settings.environment)
>>>>>>> compliance-violations-fixed

# Include API routers (if they exist)
try:
    from app.api.v1.router import api_router
    app.include_router(api_router, prefix="/api/v1")
except ImportError:
    logger.warning("V1 API router not available - skipping")

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
<<<<<<< HEAD
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
=======
    logger.error("CRITICAL: Could not import production signal routers: %s", exc)
    logger.error("Service cannot start without production routers")
    raise RuntimeError("Production signal routers are required - cannot start service") from exc
>>>>>>> compliance-violations-fixed

# Include v2 indicators router (real indicator calculations)
try:
    from app.api.v2.indicators import router as indicators_router
    app.include_router(indicators_router, prefix="/api/v2")
    logger.info("✓ Indicators router included")
except ImportError as exc:
    logger.warning("Could not import indicators router: %s", exc)

# Include v2 universal computation router (unified computation API)
try:
    from app.api.v2.universal import router as universal_router
    app.include_router(universal_router, prefix="/api/v2")
    logger.info("✓ Universal computation router included")
except ImportError as exc:
    logger.warning("Could not import universal router: %s", exc)

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
<<<<<<< HEAD
    app.include_router(monitoring_router, prefix="/api/v2")
    logger.info("✓ Production monitoring router included with versioned API")
=======
    app.include_router(monitoring_router, prefix="/monitoring")
>>>>>>> compliance-violations-fixed
except ImportError as exc:
    logger.warning("Could not import monitoring router: %s", exc)

# Production hardening: Include config admin router for config-driven budgets and pools
try:
    from app.api.v2.config_admin import router as config_admin_router
    app.include_router(config_admin_router)
    logger.info("✓ Config admin router included for config-driven budget management")
except ImportError as exc:
    logger.warning("Could not import config admin router: %s", exc)

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
<<<<<<< HEAD
    logger.warning("Could not import enhanced monitoring router: %s", exc)
    # Fallback to simple monitoring router
    try:
        from app.api.simple_monitoring import router as simple_monitoring_router
        app.include_router(simple_monitoring_router, prefix="/api/v2")
        logger.info("✓ Simple monitoring router included as versioned fallback")
    except ImportError as fallback_exc:
        logger.warning("Could not import simple monitoring router: %s", fallback_exc)
=======
    logger.error("CRITICAL: Could not import enhanced monitoring router: %s", exc)
    raise RuntimeError("Enhanced monitoring router is required for production operations") from exc
>>>>>>> compliance-violations-fixed

@app.get("/api/v1")
async def root():
    """Root endpoint - Architecture Principle #3: API versioning is mandatory"""
    return {
        "service": "signal_service",
        "version": "1.0.0",
        "status": "running"
    }

# Removed duplicate health endpoint - use centralized health router only 
# (Architecture compliance: single route per functionality)

<<<<<<< HEAD
# Environment-based endpoint registration
# Get environment from config_service (Architecture Principle #1: Config service exclusivity)
try:
    from app.core.config import settings
    environment = settings.environment
except Exception as e:
    raise RuntimeError(f"Failed to get environment from config_service for endpoint registration: {e}. No environment fallbacks allowed per architecture.")

if environment not in ['production', 'prod', 'staging']:
    # Development/test endpoints only
    @app.get("/api/v1/metrics")
    async def metrics():
        """Basic Prometheus-style metrics - development only."""
        body = "\n".join([
=======
@app.get("/metrics")
async def metrics():
    """Basic Prometheus-style metrics for monitoring."""
    body = "\n".join(
        [
>>>>>>> compliance-violations-fixed
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

<<<<<<< HEAD
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
                
            except Exception as e:
                # Redis unavailable, log warning but continue with defaults
                logger.warning(f"Redis metrics unavailable: {e}")
                processed_signals = 0
            
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
=======
@app.get("/api/v2/admin/health")
async def admin_health():
    """Detailed health status for operational monitoring."""
    return {
        "status": "healthy",
        "database": "healthy",
        "redis": "healthy",
        "signal_processor": "healthy",
    }


@app.get("/api/v2/admin/metrics")
async def admin_metrics():
    """Return lightweight metrics snapshot."""
    return {
        "backpressure_level": "LOW",
        "active_subscriptions": 10,
        "processed_signals": 100,
    }


@app.get("/api/v2/admin/audit-trail")
async def admin_audit_trail(user_id: str = None, limit: int = 10):
    """Stub audit trail endpoint."""
    entries = [{"user_id": user_id or "anonymous", "action": "access", "timestamp": "2024-01-01T00:00:00Z"}]
    return {"entries": entries[:limit]}
>>>>>>> compliance-violations-fixed


@app.get("/api/v2/admin/hot-reload/status")
async def hot_reload_status():
    """Get hot parameter reloading status and statistics."""
    try:
        from app.core.hot_config import hot_reloadable_settings
        stats = hot_reloadable_settings.get_hot_reload_stats()
        return {
            "status": "enabled" if stats.get("notification_client_active") else "disabled",
            "statistics": stats
        }
    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
            "statistics": {"initialized": False}
        }


@app.get("/api/v2/admin/hot-reload/health")
async def hot_reload_health_check():
    """Get hot reload system health - secure internal monitoring."""
    try:
        from app.core.hot_config import hot_reloadable_settings
        health_data = await hot_reloadable_settings.get_hot_reload_health()
        return {
            "status": "success",
            "hot_reload_health": health_data
        }
    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
            "hot_reload_health": {
                "hot_reload_enabled": False,
                "error": str(e)
            }
        }


@app.post("/api/v2/admin/hot-reload/kill-switch")
async def hot_reload_kill_switch(action: str, reason: str = "Manual operation"):
    """Control hot reload kill switch - ADMIN ONLY."""
    try:
        from app.core.hot_config import hot_reloadable_settings
        
        if action == "enable":
            hot_reloadable_settings.enable_kill_switch(reason)
            return {
                "status": "success",
                "message": f"Kill switch enabled: {reason}",
                "kill_switch_enabled": True
            }
        elif action == "disable":
            hot_reloadable_settings.disable_kill_switch(reason)
            return {
                "status": "success",
                "message": f"Kill switch disabled: {reason}",
                "kill_switch_enabled": False
            }
        else:
            return {
                "status": "error",
                "error": "Invalid action. Use 'enable' or 'disable'"
            }
    except Exception as e:
        return {
            "status": "error",
            "error": str(e)
        }


@app.post("/api/v2/admin/hot-reload/emergency-shutdown")
async def hot_reload_emergency_shutdown(reason: str = "Manual emergency shutdown"):
    """Emergency shutdown of hot reload system - ADMIN ONLY."""
    try:
        from app.core.hot_config import hot_reloadable_settings
        await hot_reloadable_settings.emergency_shutdown()
        return {
            "status": "success",
            "message": f"Emergency shutdown completed: {reason}",
            "hot_reload_enabled": False,
            "kill_switch_enabled": True
        }
    except Exception as e:
        return {
            "status": "error",
            "error": str(e)
        }


@app.get("/api/v2/admin/hot-reload/circuit-breaker")
async def hot_reload_circuit_breaker_status():
    """Get circuit breaker status and statistics."""
    try:
        from app.core.hot_config import hot_reloadable_settings
        health_data = await hot_reloadable_settings.get_hot_reload_health()
        return {
            "status": "success",
            "circuit_breaker": health_data.get("circuit_breaker", {}),
            "fail_safes": health_data.get("fail_safes", {})
        }
    except Exception as e:
        return {
            "status": "error",
            "error": str(e)
        }


@app.post("/api/v2/admin/hot-reload/validate-parameter")
async def validate_hot_reload_parameter(parameter_key: str, parameter_value: str):
    """Validate parameter against schema before applying - TESTING ONLY."""
    try:
        from app.core.hot_config import hot_reloadable_settings
        
        # This endpoint is for validation testing only
        is_valid = hot_reloadable_settings.validate_parameter(parameter_key, parameter_value)
        
        return {
            "status": "success",
            "parameter_key": parameter_key,
            "parameter_value": "[REDACTED]" if "SECRET" in parameter_key.upper() else parameter_value,
            "validation_result": is_valid
        }
    except Exception as e:
        return {
            "status": "error",
            "parameter_key": parameter_key,
            "error": str(e),
            "validation_result": False
        }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8003)
