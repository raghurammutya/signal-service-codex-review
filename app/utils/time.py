"""Time utilities for signal service"""
from datetime import datetime, timezone

def utcnow():
    """Return current UTC time"""
    return datetime.now(timezone.utc)