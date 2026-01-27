"""
Minimal logging configuration helper for the signal service.
"""

import logging


def get_logger(name: str | None = None) -> logging.Logger:
    """
    Return a standard Python logger.

    Args:
        name: Optional logger name. Defaults to module calling this helper.
    """
    return logging.getLogger(name or __name__)
