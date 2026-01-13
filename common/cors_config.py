"""
Mock CORS configuration for testing
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

def add_cors_middleware(app: FastAPI, environment: str = "test"):
    """Add CORS middleware to FastAPI application for testing."""
    # Allow all origins for testing
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    return app