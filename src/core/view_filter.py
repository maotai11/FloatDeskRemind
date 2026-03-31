"""
View filter — pure functions, zero Qt / DB dependency.

View identifiers:
    VIEW_TODAY     'today'      — due_date == today, status=pending
    VIEW_UPCOMING  'upcoming'   — today < due_date <= today+7, status=pending
    VIEW_OVERDUE   'overdue'    — due_date < today, status=pending
    VIEW_NO_DATE   'nodate'     — due_date is None, status=pending (not done/deleted/archived)
    VIEW_ALL       'all'        — all non-deleted, non-archived
    VIEW_COMPLETED 'completed'  — status='done'
    VIEW_SEARCH    'search'     — special: filtering is handled externally; returns all non-deleted

Public API:
    filter_tasks(tasks, view, today=None) -> List[Task]
    count_views(tasks, today=None)        -> Dict[str, int]
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Dict, List, Optional

from src.data.models import Task

# ---------------------------------------------------------------------------
# View identifiers
# ---------------------------------------------------------------------------

VIEW_TODAY     = 'today'
VIEW_UPCOMING  = 'upcoming'
VIEW_OVERDUE   = 'overdue'
VIEW_NO_DATE   = 'nodate'
VIEW_ALL       = 'all'
VIEW_COMPLETED = 'completed'
VIEW_SEARCH    = 'search'

# All non-search views that receive count badges
_COUNTABLE_VIEWS = (
    VIEW_TODAY, VIEW_UPCOMING, VIEW_OVERDUE,
    VIEW_NO_DATE, VIEW_ALL, VIEW_COMPLETED,
)

# Empty-state messages keyed by view
EMPTY_MESSAGES: Dict[str, str] = {
    VIEW_TODAY:     '今天沒有到期任務',
    VIEW_UPCOMING:  '未來 7 天沒有排程任務',
    VIEW_OVERDUE:   '沒有逾期任務，繼續保持！',
    VIEW_NO_DATE:   '所有任務都已設定期限',
    VIEW_ALL:       '還沒有任務，按 Ctrl+N 新增',
    VIEW_COMPLETED: '還沒有完成的任務',
    VIEW_SEARCH:    '沒有符合的搜尋結果',
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def filter_tasks(
    tasks: List[Task],
    view: str,
    today: Optional[date] = None,
) -> List[Task]:
    """Return the subset of *tasks* that belong to *view*.

    Args:
        tasks:  Full task list (already non-deleted if coming from the repo).
        view:   One of the VIEW_* constants.
        today:  Reference date; defaults to ``date.today()``.

    Notes:
        - VIEW_SEARCH returns all non-deleted tasks; callers replace the full
          list with search results before calling refresh(), so no extra
          filtering is needed here.
        - Archived tasks are excluded from all active views (consistent with
          the original ALL behaviour).
    """
    ref = today or date.today()
    today_str = ref.isoformat()
    upcoming_end = (ref + timedelta(days=7)).isoformat()

    if view == VIEW_TODAY:
        return [
            t for t in tasks
            if t.due_date == today_str and t.status == 'pending'
        ]

    if view == VIEW_UPCOMING:
        return [
            t for t in tasks
            if t.due_date
            and today_str < t.due_date <= upcoming_end
            and t.status == 'pending'
        ]

    if view == VIEW_OVERDUE:
        return [
            t for t in tasks
            if t.due_date and t.due_date < today_str and t.status == 'pending'
        ]

    if view == VIEW_NO_DATE:
        return [
            t for t in tasks
            if not t.due_date and t.status not in ('done', 'deleted', 'archived')
        ]

    if view == VIEW_COMPLETED:
        return [t for t in tasks if t.status == 'done']

    # VIEW_ALL and VIEW_SEARCH (search results are pre-filtered by the caller)
    return [t for t in tasks if t.status not in ('deleted', 'archived')]


def count_views(
    tasks: List[Task],
    today: Optional[date] = None,
) -> Dict[str, int]:
    """Return task counts for every countable view.

    Intended for LeftPanel badge labels.  Only COUNTABLE_VIEWS are counted;
    VIEW_SEARCH is omitted.
    """
    ref = today or date.today()
    return {
        view: len(filter_tasks(tasks, view, ref))
        for view in _COUNTABLE_VIEWS
    }
