"""
Lightweight logging helpers for the signal service.
"""

import logging
from typing import Any

_LOGGER = logging.getLogger("signal_service")


def log_info(message: Any, *args: Any, **kwargs: Any) -> None:
    """Log info-level messages."""
    _LOGGER.info(message, *args, **kwargs)


def log_warning(message: Any, *args: Any, **kwargs: Any) -> None:
    """Log warning-level messages."""
    _LOGGER.warning(message, *args, **kwargs)


def log_error(message: Any, *args: Any, **kwargs: Any) -> None:
    """Log error-level messages."""
    _LOGGER.error(message, *args, **kwargs)


def log_exception(message: Any, *args: Any, **kwargs: Any) -> None:
    """Log exceptions with stack trace."""
    _LOGGER.exception(message, *args, **kwargs)


def log_debug(message: Any, *args: Any, **kwargs: Any) -> None:
    """Log debug-level messages."""
    _LOGGER.debug(message, *args, **kwargs)
