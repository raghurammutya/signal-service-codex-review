"""
Central Indicator Registry System

Provides unified access to indicators from multiple libraries:
- pandas_ta (150+ indicators)
- smartmoneyconcepts (Smart Money Concepts)
- scipy.signal (Signal processing)
- Custom algorithms (Patterns, pivots, fibonacci)
- trendln (Trendline detection)
- findpeaks (Advanced peak detection)
- scikit-learn (Clustering)

Users call indicators by name without knowing the underlying library.
All indicators follow the same caching, subscription, and batch processing model.
"""
import logging
from collections.abc import Callable
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class IndicatorCategory(str, Enum):
    """Indicator categories for organization"""
    SMART_MONEY = "smart_money"
    SIGNAL_PROCESSING = "signal_processing"
    PATTERN_RECOGNITION = "pattern_recognition"
    TRENDLINES = "trendlines"
    CLUSTERING = "clustering"
    ADVANCED_PEAKS = "advanced_peaks"
    CUSTOM = "custom"
    PANDAS_TA = "pandas_ta"
    GREEKS = "greeks"
    OPTIONS = "options"


class IndicatorMetadata:
    """Metadata for a registered indicator"""

    def __init__(
        self,
        name: str,
        function: Callable,
        category: IndicatorCategory,
        library: str,
        description: str,
        parameters: dict[str, Any],
        output_type: str = "series"
    ):
        self.name = name
        self.function = function
        self.category = category
        self.library = library
        self.description = description
        self.parameters = parameters
        self.output_type = output_type  # "series", "dataframe", "dict", "float"

    def to_dict(self) -> dict[str, Any]:
        """Convert metadata to dictionary for API responses"""
        return {
            "name": self.name,
            "category": self.category.value,
            "library": self.library,
            "description": self.description,
            "parameters": self.parameters,
            "output_type": self.output_type
        }


class IndicatorRegistry:
    """
    Central registry for all technical indicators.

    Features:
    - Unified access to indicators from multiple libraries
    - Automatic discovery and documentation
    - Parameter validation
    - Category-based organization
    """

    _indicators: dict[str, IndicatorMetadata] = {}
    _initialized = False

    @classmethod
    def register(
        cls,
        name: str,
        function: Callable,
        category: IndicatorCategory,
        library: str,
        description: str,
        parameters: dict[str, Any],
        output_type: str = "series"
    ):
        """
        Register an indicator in the central registry.

        Args:
            name: Unique indicator name (used in API calls)
            function: Callable that computes the indicator
            category: Category for organization
            library: Source library name
            description: Human-readable description
            parameters: Dict of parameter names and defaults
            output_type: Type of output (series, dataframe, dict, float)
        """
        if name in cls._indicators:
            logger.warning(f"Indicator '{name}' already registered, overwriting")

        metadata = IndicatorMetadata(
            name=name,
            function=function,
            category=category,
            library=library,
            description=description,
            parameters=parameters,
            output_type=output_type
        )

        cls._indicators[name] = metadata
        logger.debug(f"Registered indicator: {name} ({library})")

    @classmethod
    def get(cls, name: str) -> IndicatorMetadata | None:
        """Get indicator metadata by name"""
        return cls._indicators.get(name)

    @classmethod
    def exists(cls, name: str) -> bool:
        """Check if indicator is registered"""
        return name in cls._indicators

    @classmethod
    def list_all(cls) -> dict[str, list[dict[str, Any]]]:
        """
        List all indicators organized by category.

        Returns:
            {
                "smart_money": [{"name": "bos", "description": "...", ...}],
                "signal_processing": [...],
                ...
            }
        """
        categories: dict[str, list[dict[str, Any]]] = {}

        for indicator in cls._indicators.values():
            cat = indicator.category.value
            if cat not in categories:
                categories[cat] = []

            categories[cat].append(indicator.to_dict())

        # Sort each category by name
        for cat in categories:
            categories[cat] = sorted(categories[cat], key=lambda x: x['name'])

        return categories

    @classmethod
    def list_by_category(cls, category: IndicatorCategory) -> list[dict[str, Any]]:
        """List all indicators in a specific category"""
        return [
            ind.to_dict()
            for ind in cls._indicators.values()
            if ind.category == category
        ]

    @classmethod
    def search(cls, query: str) -> list[dict[str, Any]]:
        """
        Search indicators by name or description.

        Args:
            query: Search term (case-insensitive)

        Returns:
            List of matching indicator metadata
        """
        query = query.lower()
        results = []

        for indicator in cls._indicators.values():
            if (query in indicator.name.lower() or
                query in indicator.description.lower() or
                query in indicator.library.lower()):
                results.append(indicator.to_dict())

        return results

    @classmethod
    def get_parameter_defaults(cls, name: str) -> dict[str, Any]:
        """Get default parameters for an indicator"""
        indicator = cls.get(name)
        if indicator:
            return indicator.parameters.copy()
        return {}

    @classmethod
    def count(cls) -> int:
        """Total number of registered indicators"""
        return len(cls._indicators)

    @classmethod
    def count_by_category(cls) -> dict[str, int]:
        """Count indicators by category"""
        counts = {}
        for indicator in cls._indicators.values():
            cat = indicator.category.value
            counts[cat] = counts.get(cat, 0) + 1
        return counts

    @classmethod
    def is_initialized(cls) -> bool:
        """Check if registry has been initialized"""
        return cls._initialized

    @classmethod
    def mark_initialized(cls):
        """Mark registry as initialized"""
        cls._initialized = True
        logger.info(f"Indicator registry initialized with {cls.count()} indicators")

    @classmethod
    def reset(cls):
        """Reset registry (used for testing)"""
        cls._indicators.clear()
        cls._initialized = False


def register_indicator(
    name: str,
    category: IndicatorCategory,
    library: str,
    description: str,
    parameters: dict[str, Any] | None = None,
    output_type: str = "series"
):
    """
    Decorator for registering indicators.

    Usage:
        @register_indicator(
            name="break_of_structure",
            category=IndicatorCategory.SMART_MONEY,
            library="smartmoneyconcepts",
            description="Detects Break of Structure (BOS) signals",
            parameters={"swing_length": 10}
        )
        def break_of_structure(df, swing_length=10):
            ...
    """
    def decorator(func: Callable) -> Callable:
        IndicatorRegistry.register(
            name=name,
            function=func,
            category=category,
            library=library,
            description=description,
            parameters=parameters or {},
            output_type=output_type
        )
        return func

    return decorator
