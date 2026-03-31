"""
Tests for Patch 12 — view_filter pure functions.

All tests use a fixed reference date (2026-04-10, Friday) so results are
deterministic regardless of when the suite is run.

TestFilterTasks  (28 tests)
TestCountViews   (4 tests)
"""
from __future__ import annotations

import uuid
from datetime import date
from typing import List, Optional

import pytest

from src.core.view_filter import (
    VIEW_ALL, VIEW_COMPLETED, VIEW_NO_DATE, VIEW_OVERDUE,
    VIEW_SEARCH, VIEW_TODAY, VIEW_UPCOMING,
    count_views, filter_tasks,
)
from src.data.models import Task


# ---------------------------------------------------------------------------
# Fixed reference date
# ---------------------------------------------------------------------------

TODAY = date(2026, 4, 10)   # Friday
YESTERDAY  = date(2026, 4, 9).isoformat()
TODAY_STR  = TODAY.isoformat()            # '2026-04-10'
TOMORROW   = date(2026, 4, 11).isoformat()
DAY_7      = date(2026, 4, 17).isoformat()   # today + 7  (boundary, inclusive)
DAY_8      = date(2026, 4, 18).isoformat()   # today + 8  (outside UPCOMING)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _task(
    *,
    status: str = 'pending',
    due_date: Optional[str] = None,
    is_recurring: bool = False,
) -> Task:
    return Task(
        id=str(uuid.uuid4()),
        title='Task',
        status=status,
        due_date=due_date,
        is_recurring=is_recurring,
    )


def _ids(tasks: List[Task]) -> set:
    return {t.id for t in tasks}


# ===========================================================================
# TestFilterTasks
# ===========================================================================

class TestFilterTasks:

    # ── VIEW_TODAY ────────────────────────────────────────────────────────────

    def test_today_includes_task_due_today(self):
        t = _task(due_date=TODAY_STR)
        result = filter_tasks([t], VIEW_TODAY, TODAY)
        assert t.id in _ids(result)

    def test_today_excludes_task_due_tomorrow(self):
        t = _task(due_date=TOMORROW)
        result = filter_tasks([t], VIEW_TODAY, TODAY)
        assert t.id not in _ids(result)

    def test_today_excludes_task_due_yesterday(self):
        t = _task(due_date=YESTERDAY)
        result = filter_tasks([t], VIEW_TODAY, TODAY)
        assert t.id not in _ids(result)

    def test_today_excludes_done_task(self):
        t = _task(due_date=TODAY_STR, status='done')
        result = filter_tasks([t], VIEW_TODAY, TODAY)
        assert t.id not in _ids(result)

    def test_today_excludes_deleted_task(self):
        t = _task(due_date=TODAY_STR, status='deleted')
        result = filter_tasks([t], VIEW_TODAY, TODAY)
        assert t.id not in _ids(result)

    # ── VIEW_UPCOMING ─────────────────────────────────────────────────────────

    def test_upcoming_includes_tomorrow(self):
        t = _task(due_date=TOMORROW)
        result = filter_tasks([t], VIEW_UPCOMING, TODAY)
        assert t.id in _ids(result)

    def test_upcoming_includes_day_7(self):
        t = _task(due_date=DAY_7)
        result = filter_tasks([t], VIEW_UPCOMING, TODAY)
        assert t.id in _ids(result)

    def test_upcoming_excludes_today(self):
        """today itself is VIEW_TODAY territory, not UPCOMING."""
        t = _task(due_date=TODAY_STR)
        result = filter_tasks([t], VIEW_UPCOMING, TODAY)
        assert t.id not in _ids(result)

    def test_upcoming_excludes_day_8(self):
        t = _task(due_date=DAY_8)
        result = filter_tasks([t], VIEW_UPCOMING, TODAY)
        assert t.id not in _ids(result)

    def test_upcoming_excludes_done_task(self):
        t = _task(due_date=TOMORROW, status='done')
        result = filter_tasks([t], VIEW_UPCOMING, TODAY)
        assert t.id not in _ids(result)

    def test_upcoming_excludes_no_date(self):
        t = _task(due_date=None)
        result = filter_tasks([t], VIEW_UPCOMING, TODAY)
        assert t.id not in _ids(result)

    # ── VIEW_OVERDUE ──────────────────────────────────────────────────────────

    def test_overdue_includes_yesterday_pending(self):
        t = _task(due_date=YESTERDAY)
        result = filter_tasks([t], VIEW_OVERDUE, TODAY)
        assert t.id in _ids(result)

    def test_overdue_excludes_today(self):
        """Today is not overdue yet."""
        t = _task(due_date=TODAY_STR)
        result = filter_tasks([t], VIEW_OVERDUE, TODAY)
        assert t.id not in _ids(result)

    def test_overdue_excludes_done_task(self):
        t = _task(due_date=YESTERDAY, status='done')
        result = filter_tasks([t], VIEW_OVERDUE, TODAY)
        assert t.id not in _ids(result)

    def test_overdue_excludes_deleted_task(self):
        t = _task(due_date=YESTERDAY, status='deleted')
        result = filter_tasks([t], VIEW_OVERDUE, TODAY)
        assert t.id not in _ids(result)

    def test_overdue_excludes_no_date(self):
        t = _task(due_date=None)
        result = filter_tasks([t], VIEW_OVERDUE, TODAY)
        assert t.id not in _ids(result)

    # ── VIEW_NO_DATE ──────────────────────────────────────────────────────────

    def test_no_date_includes_pending_task_without_date(self):
        t = _task(due_date=None, status='pending')
        result = filter_tasks([t], VIEW_NO_DATE, TODAY)
        assert t.id in _ids(result)

    def test_no_date_excludes_task_with_date(self):
        t = _task(due_date=TODAY_STR)
        result = filter_tasks([t], VIEW_NO_DATE, TODAY)
        assert t.id not in _ids(result)

    def test_no_date_excludes_done_task(self):
        t = _task(due_date=None, status='done')
        result = filter_tasks([t], VIEW_NO_DATE, TODAY)
        assert t.id not in _ids(result)

    def test_no_date_excludes_deleted_task(self):
        t = _task(due_date=None, status='deleted')
        result = filter_tasks([t], VIEW_NO_DATE, TODAY)
        assert t.id not in _ids(result)

    def test_no_date_excludes_archived_task(self):
        t = _task(due_date=None, status='archived')
        result = filter_tasks([t], VIEW_NO_DATE, TODAY)
        assert t.id not in _ids(result)

    # ── VIEW_ALL ──────────────────────────────────────────────────────────────

    def test_all_includes_pending(self):
        t = _task(status='pending', due_date=TODAY_STR)
        result = filter_tasks([t], VIEW_ALL, TODAY)
        assert t.id in _ids(result)

    def test_all_includes_done(self):
        t = _task(status='done')
        result = filter_tasks([t], VIEW_ALL, TODAY)
        assert t.id in _ids(result)

    def test_all_excludes_deleted(self):
        t = _task(status='deleted')
        result = filter_tasks([t], VIEW_ALL, TODAY)
        assert t.id not in _ids(result)

    def test_all_excludes_archived(self):
        t = _task(status='archived')
        result = filter_tasks([t], VIEW_ALL, TODAY)
        assert t.id not in _ids(result)

    # ── VIEW_COMPLETED ────────────────────────────────────────────────────────

    def test_completed_includes_done_task(self):
        t = _task(status='done')
        result = filter_tasks([t], VIEW_COMPLETED, TODAY)
        assert t.id in _ids(result)

    def test_completed_excludes_pending_task(self):
        t = _task(status='pending', due_date=TODAY_STR)
        result = filter_tasks([t], VIEW_COMPLETED, TODAY)
        assert t.id not in _ids(result)

    def test_completed_excludes_deleted_task(self):
        t = _task(status='deleted')
        result = filter_tasks([t], VIEW_COMPLETED, TODAY)
        assert t.id not in _ids(result)

    # ── VIEW_SEARCH ───────────────────────────────────────────────────────────

    def test_search_returns_all_non_deleted_non_archived(self):
        """SEARCH view returns pre-filtered results unchanged (all non-deleted)."""
        pending = _task(status='pending', due_date=TODAY_STR)
        done    = _task(status='done')
        deleted = _task(status='deleted')
        tasks   = [pending, done, deleted]

        result = filter_tasks(tasks, VIEW_SEARCH, TODAY)
        ids = _ids(result)
        assert pending.id in ids
        assert done.id in ids
        assert deleted.id not in ids

    # ── Cross-view: deleted task absent from all active views ─────────────────

    def test_deleted_task_excluded_from_all_active_views(self):
        deleted = _task(status='deleted', due_date=TODAY_STR)
        tasks = [deleted]

        for view in (VIEW_TODAY, VIEW_UPCOMING, VIEW_OVERDUE, VIEW_NO_DATE,
                     VIEW_ALL, VIEW_COMPLETED):
            result = filter_tasks(tasks, view, TODAY)
            assert deleted.id not in _ids(result), f'deleted appeared in {view}'


# ===========================================================================
# TestCountViews
# ===========================================================================

class TestCountViews:

    def test_all_zero_for_empty_list(self):
        counts = count_views([], TODAY)
        for v in (VIEW_TODAY, VIEW_UPCOMING, VIEW_OVERDUE, VIEW_NO_DATE,
                  VIEW_ALL, VIEW_COMPLETED):
            assert counts[v] == 0, f'{v} should be 0'

    def test_correct_counts_for_mixed_tasks(self):
        tasks = [
            _task(due_date=TODAY_STR, status='pending'),      # today
            _task(due_date=TOMORROW, status='pending'),        # upcoming
            _task(due_date=YESTERDAY, status='pending'),       # overdue
            _task(due_date=None, status='pending'),            # no_date
            _task(status='done'),                              # completed
            _task(status='deleted'),                           # excluded from all
        ]
        counts = count_views(tasks, TODAY)

        assert counts[VIEW_TODAY]     == 1
        assert counts[VIEW_UPCOMING]  == 1
        assert counts[VIEW_OVERDUE]   == 1
        assert counts[VIEW_NO_DATE]   == 1
        assert counts[VIEW_COMPLETED] == 1
        # ALL: pending(today)+pending(upcoming)+pending(overdue)+pending(no_date)+done = 5
        assert counts[VIEW_ALL]       == 5

    def test_search_not_in_counts(self):
        counts = count_views([], TODAY)
        assert VIEW_SEARCH not in counts

    def test_boundary_day_7_counted_in_upcoming(self):
        """Due date == today+7 must appear in UPCOMING count."""
        t = _task(due_date=DAY_7, status='pending')
        counts = count_views([t], TODAY)
        assert counts[VIEW_UPCOMING] == 1

    def test_boundary_day_8_not_counted_in_upcoming(self):
        """Due date == today+8 must NOT appear in UPCOMING count."""
        t = _task(due_date=DAY_8, status='pending')
        counts = count_views([t], TODAY)
        assert counts[VIEW_UPCOMING] == 0
