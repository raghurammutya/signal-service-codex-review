"""
Register All Custom Indicators

This module imports all indicator modules and ensures they are registered
with the central IndicatorRegistry on startup.

Must be called during application initialization (in main.py lifespan).
"""
import logging

# Import all indicator modules to trigger @register_indicator decorators
from app.services.indicator_registry import IndicatorRegistry

logger = logging.getLogger(__name__)


def register_all_indicators():
    """
    Register all custom indicators with the central registry.

    This function should be called during application startup.
    It ensures all indicator modules are imported and their
    @register_indicator decorators have executed.
    """
    # The import statements above trigger all @register_indicator decorators

    # Mark registry as initialized
    IndicatorRegistry.mark_initialized()

    # Log summary
    indicator_count = IndicatorRegistry.count()
    category_counts = IndicatorRegistry.count_by_category()

    logger.info("=" * 80)
    logger.info("SMART INDICATOR LIBRARY INITIALIZED")
    logger.info("=" * 80)
    logger.info(f"Total Indicators Registered: {indicator_count}")
    logger.info("")
    logger.info("Indicators by Category:")
    for category, count in sorted(category_counts.items()):
        logger.info(f"  - {category}: {count} indicators")
    logger.info("=" * 80)

    # Log all registered indicators (debug level)
    all_indicators = IndicatorRegistry.list_all()
    logger.debug("Registered Indicators:")
    for category, indicators in all_indicators.items():
        logger.debug(f"\n  {category.upper()}:")
        for ind in indicators:
            logger.debug(f"    - {ind['name']} ({ind['library']})")


def get_indicator_summary() -> dict:
    """
    Get a summary of all registered indicators.

    Returns:
        Dict with counts and category breakdowns
    """
    return {
        "total_count": IndicatorRegistry.count(),
        "by_category": IndicatorRegistry.count_by_category(),
        "initialized": IndicatorRegistry.is_initialized()
    }
