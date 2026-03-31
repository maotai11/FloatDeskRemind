"""
Recurrence engine — pure functions, zero DB / Qt dependency.

Recurrence rule format (v1):
    Plain string, one of: 'daily' | 'weekly' | 'monthly'

    The value is stored in tasks.recurrence_rule and is case-insensitive.
    Leading/trailing whitespace is stripped before parsing.

    Future compatibility: the format is intentionally kept as a plain string
    so that richer rules (e.g. 'weekly:MO,WE,FR') can be added in v2 without
    a schema migration — just extend the parser.

Public API:
    next_due_date(due_date: str, rule: str) -> str
        Return the next occurrence as 'YYYY-MM-DD'.
        Raises RecurrenceError for unknown rules or malformed dates.

Monthly edge case (clamping):
    If source day exceeds the last day of the target month, clamp to that
    month's last day.
    Examples:
      Jan 31 + 1 month → Feb 28 (or Feb 29 in a leap year)
      Oct 31 + 1 month → Nov 30
      Dec 31 + 1 month → Jan 31 (no clamp needed)
"""
from __future__ import annotations

import calendar
from datetime import date, timedelta

VALID_RULES: frozenset = frozenset({'daily', 'weekly', 'monthly'})


class RecurrenceError(ValueError):
    """Raised when the recurrence rule is unrecognised or the date is malformed."""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def next_due_date(due_date: str, rule: str) -> str:
    """Return the next due date given the current *due_date* and a *rule*.

    Args:
        due_date: ISO date string 'YYYY-MM-DD'.
        rule:     One of 'daily', 'weekly', 'monthly' (case-insensitive).

    Returns:
        Next due date as 'YYYY-MM-DD'.

    Raises:
        RecurrenceError: if *rule* is not in VALID_RULES, or *due_date* cannot
                         be parsed as a valid ISO date.
    """
    normalized = rule.strip().lower() if rule else ''
    if normalized not in VALID_RULES:
        raise RecurrenceError(
            f'Unknown recurrence rule: {rule!r}. '
            f'Must be one of {sorted(VALID_RULES)}'
        )
    try:
        d = date.fromisoformat(due_date)
    except (ValueError, TypeError, AttributeError) as exc:
        raise RecurrenceError(f'Invalid due_date: {due_date!r}') from exc

    if normalized == 'daily':
        return (d + timedelta(days=1)).isoformat()
    if normalized == 'weekly':
        return (d + timedelta(weeks=1)).isoformat()
    # monthly
    return _add_one_month(d).isoformat()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _add_one_month(d: date) -> date:
    """Add exactly one calendar month, clamping to month-end when necessary."""
    month = d.month + 1
    year = d.year
    if month > 12:
        month = 1
        year += 1
    last_day = calendar.monthrange(year, month)[1]
    day = min(d.day, last_day)
    return date(year, month, day)
