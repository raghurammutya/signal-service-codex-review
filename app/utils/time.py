"""Time utilities for signal service"""
from datetime import UTC, datetime


def utcnow():
    """Return current UTC time"""
    return datetime.now(UTC)
