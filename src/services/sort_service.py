"""
SortService: sort tasks within a date bucket.

Order:
  1. Overdue tasks (due_date < today) — shown at top with red marker
  2. Tasks with due_time — sorted by time ascending
  3. Tasks without due_time — sorted by priority (high > medium > low > none)
  4. Ties broken by sort_order
"""
from __future__ import annotations
from datetime import date
from typing import List

from src.data.models import Task

PRIORITY_ORDER = {'high': 0, 'medium': 1, 'low': 2, 'none': 3}


def sort_tasks(tasks: List[Task], reference_date: date = None) -> List[Task]:
    today = reference_date or date.today()
    today_str = today.isoformat()

    def key(t: Task):
        is_overdue = 0
        if t.due_date and t.due_date < today_str:
            is_overdue = -1  # negative = first bucket

        has_time = 0 if t.due_time else 1
        time_val = t.due_time or '99:99'
        priority_val = PRIORITY_ORDER.get(t.priority, 3)
        sort_order = t.sort_order

        return (is_overdue, has_time, time_val, priority_val, sort_order)

    return sorted(tasks, key=key)
