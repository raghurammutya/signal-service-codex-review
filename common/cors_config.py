"""
Production-ready CORS configuration with security controls.
Enforces strict origin policies and proper CORS headers for production deployment.
"""
import logging
import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from typing import List

logger = logging.getLogger(__name__)


def get_allowed_origins(environment: str) -> List[str]:
    """Get allowed origins based on environment with strict controls."""
    
    # Production requires explicit allowed origins
    allowed_origins_env = os.getenv("CORS_ALLOWED_ORIGINS")
    
    if environment == "production":
        if not allowed_origins_env:
            logger.critical("CORS_ALLOWED_ORIGINS not configured for production")
            raise ValueError("CORS_ALLOWED_ORIGINS must be configured for production environment")
            
        # Parse comma-separated origins and validate
        origins = [origin.strip() for origin in allowed_origins_env.split(",")]
        
        # Validate that no wildcard origins are used in production
        for origin in origins:
            if "*" in origin:
                logger.critical(f"Wildcard origin {origin} not allowed in production")
                raise ValueError(f"Wildcard origins not permitted in production: {origin}")
                
        logger.info(f"Production CORS origins configured: {len(origins)} origins")
        return origins
        
    elif environment in ["staging", "development"]:
        if allowed_origins_env:
            origins = [origin.strip() for origin in allowed_origins_env.split(",")]
            logger.info(f"{environment} CORS origins configured: {len(origins)} origins")
            return origins
        else:
            # Production requires explicit configuration - no default origins allowed
            logger.critical(f"CORS_ALLOWED_ORIGINS not configured for {environment} environment")
            raise ValueError(f"CORS_ALLOWED_ORIGINS must be configured for {environment} environment")
    else:
        logger.error(f"Unknown environment: {environment}")
        raise ValueError(f"Unknown environment for CORS configuration: {environment}")


def add_cors_middleware(app: FastAPI, environment: str = None):
    """Add production-ready CORS middleware to FastAPI application."""
    
    if not environment:
        environment = os.getenv("ENVIRONMENT", "production")
        
    try:
        allowed_origins = get_allowed_origins(environment)
        
        # Production CORS configuration with security controls
        cors_config = {
            "allow_origins": allowed_origins,
            "allow_credentials": True,  # Required for authentication
            "allow_methods": [
                "GET", 
                "POST", 
                "PUT", 
                "DELETE", 
                "OPTIONS"
            ],  # Explicit method list
            "allow_headers": [
                "Authorization",
                "Content-Type", 
                "X-User-ID",
                "X-Gateway-Secret",
                "X-API-Key",
                "X-Internal-API-Key",
                "Accept"
            ],  # Explicit header list
            "expose_headers": [
                "X-Total-Count",
                "X-Page-Count", 
                "X-Rate-Limit-Remaining"
            ]
        }
        
        app.add_middleware(CORSMiddleware, **cors_config)
        
        logger.info(f"CORS middleware configured for {environment} with {len(allowed_origins)} allowed origins")
        return app
        
    except Exception as e:
        logger.critical(f"Failed to configure CORS middleware: {e}")
        raise ValueError(f"CORS configuration failed: {e}")


def validate_cors_configuration(environment: str) -> bool:
    """Validate CORS configuration for the given environment."""
    try:
        get_allowed_origins(environment)
        logger.info(f"CORS configuration validation passed for {environment}")
        return True
    except Exception as e:
        logger.error(f"CORS configuration validation failed for {environment}: {e}")
        return False