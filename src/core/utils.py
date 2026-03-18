"""
Shared utility functions used across layers.
"""
from datetime import datetime, date, timedelta, timezone
from typing import List


def now_iso() -> str:
    """Return current UTC time as ISO-8601 string (no microseconds)."""
    return datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S')


def next_n_days(n: int = 3, start: date = None) -> List[str]:
    """Return a list of n ISO date strings starting from today (or start)."""
    base = start or date.today()
    return [(base + timedelta(days=i)).isoformat() for i in range(n)]
