"""
Historical Data Manager - Production Implementation Redirect

This module redirects to the production implementation that uses ticker_service API delegation.
Maintains backward compatibility for existing imports.
"""

# Import production implementation
from app.services.historical_data_manager_production import (
    ProductionHistoricalDataManager,
    get_production_historical_data_manager
)

# Maintain backward compatibility by creating an alias
HistoricalDataManager = ProductionHistoricalDataManager

# Export the singleton getter function for new code
get_historical_data_manager = get_production_historical_data_manager
