"""
Tests for Patch 10 — Recurrence Engine.

TestRecurrenceEngine   (13 tests): pure-function tests for src/core/recurrence.py
TestTaskServiceRecurrence (14 tests): DB-backed service tests
"""
from __future__ import annotations

import uuid
from datetime import date, timedelta
from pathlib import Path

import pytest

from src.core.recurrence import RecurrenceError, _add_one_month, next_due_date
from src.data.database import run_migrations
from src.data.models import Task
from src.data.task_repository import TaskRepository
from src.services.task_service import CompleteResult, TaskService


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def db(tmp_path) -> Path:
    db_path = tmp_path / 'test.db'
    run_migrations(db_path)
    return db_path


@pytest.fixture
def repo(db) -> TaskRepository:
    return TaskRepository(db)


@pytest.fixture
def svc(repo) -> TaskService:
    return TaskService(repo)


def _task(
    *,
    title: str = 'Test',
    due_date: str = '2026-03-01',
    is_recurring: bool = True,
    recurrence_rule: str = 'daily',
    parent_id: str = None,
    start_date: str = None,
    status: str = 'pending',
) -> Task:
    return Task(
        id=str(uuid.uuid4()),
        title=title,
        status=status,
        due_date=due_date,
        is_recurring=is_recurring,
        recurrence_rule=recurrence_rule,
        parent_id=parent_id,
        start_date=start_date,
    )


def _create(repo: TaskRepository, **kwargs) -> Task:
    t = _task(**kwargs)
    return repo.create(t)


def _all_pending(repo: TaskRepository, title: str = None) -> list[Task]:
    tasks = repo.get_all_non_deleted()
    result = [t for t in tasks if t.status == 'pending']
    if title:
        result = [t for t in result if t.title == title]
    return result


# ===========================================================================
# TestRecurrenceEngine  — pure functions
# ===========================================================================

class TestRecurrenceEngine:

    # daily ------------------------------------------------------------------

    def test_daily_advances_one_day(self):
        assert next_due_date('2026-03-01', 'daily') == '2026-03-02'

    def test_daily_new_year_boundary(self):
        assert next_due_date('2025-12-31', 'daily') == '2026-01-01'

    def test_daily_case_insensitive(self):
        assert next_due_date('2026-03-01', 'Daily') == '2026-03-02'

    def test_daily_strips_whitespace(self):
        assert next_due_date('2026-03-01', '  daily  ') == '2026-03-02'

    # weekly -----------------------------------------------------------------

    def test_weekly_advances_seven_days(self):
        assert next_due_date('2026-03-01', 'weekly') == '2026-03-08'

    def test_weekly_crosses_month_boundary(self):
        assert next_due_date('2026-03-29', 'weekly') == '2026-04-05'

    # monthly ----------------------------------------------------------------

    def test_monthly_normal_day(self):
        assert next_due_date('2026-03-15', 'monthly') == '2026-04-15'

    def test_monthly_year_rollover(self):
        assert next_due_date('2025-12-15', 'monthly') == '2026-01-15'

    def test_monthly_jan31_clamps_to_feb28(self):
        assert next_due_date('2026-01-31', 'monthly') == '2026-02-28'

    def test_monthly_jan31_clamps_to_feb29_leap(self):
        # 2024 is a leap year
        assert next_due_date('2024-01-31', 'monthly') == '2024-02-29'

    def test_monthly_oct31_clamps_to_nov30(self):
        assert next_due_date('2026-10-31', 'monthly') == '2026-11-30'

    # error cases ------------------------------------------------------------

    def test_unknown_rule_raises(self):
        with pytest.raises(RecurrenceError, match='Unknown recurrence rule'):
            next_due_date('2026-03-01', 'biweekly')

    def test_invalid_date_raises(self):
        with pytest.raises(RecurrenceError, match='Invalid due_date'):
            next_due_date('not-a-date', 'daily')

    def test_empty_rule_raises(self):
        with pytest.raises(RecurrenceError, match='Unknown recurrence rule'):
            next_due_date('2026-03-01', '')


# ===========================================================================
# TestAddOneMonth — internal helper
# ===========================================================================

class TestAddOneMonth:
    def test_normal(self):
        assert _add_one_month(date(2026, 3, 15)) == date(2026, 4, 15)

    def test_december(self):
        assert _add_one_month(date(2026, 12, 31)) == date(2027, 1, 31)

    def test_clamp_feb(self):
        assert _add_one_month(date(2026, 1, 31)) == date(2026, 2, 28)


# ===========================================================================
# TestTaskServiceRecurrence — DB-backed
# ===========================================================================

class TestTaskServiceRecurrence:

    # ------------------------------------------------------------------
    # Non-recurring: no spawn
    # ------------------------------------------------------------------

    def test_non_recurring_complete_no_spawn(self, svc, repo):
        t = _create(repo, is_recurring=False, recurrence_rule=None, due_date='2026-03-01')
        svc.complete_task_manual(t.id)
        pending = _all_pending(repo, title=t.title)
        assert pending == []

    # ------------------------------------------------------------------
    # daily / weekly / monthly via complete_task_manual
    # ------------------------------------------------------------------

    def test_daily_spawns_next_task(self, svc, repo):
        t = _create(repo, recurrence_rule='daily', due_date='2026-03-01')
        svc.complete_task_manual(t.id)

        pending = _all_pending(repo, title=t.title)
        assert len(pending) == 1
        assert pending[0].due_date == '2026-03-02'

    def test_weekly_spawns_next_task(self, svc, repo):
        t = _create(repo, recurrence_rule='weekly', due_date='2026-03-01')
        svc.complete_task_manual(t.id)

        pending = _all_pending(repo, title=t.title)
        assert len(pending) == 1
        assert pending[0].due_date == '2026-03-08'

    def test_monthly_spawns_next_task(self, svc, repo):
        t = _create(repo, recurrence_rule='monthly', due_date='2026-03-15')
        svc.complete_task_manual(t.id)

        pending = _all_pending(repo, title=t.title)
        assert len(pending) == 1
        assert pending[0].due_date == '2026-04-15'

    def test_monthly_clamp_spawns_correct_date(self, svc, repo):
        t = _create(repo, recurrence_rule='monthly', due_date='2026-01-31')
        svc.complete_task_manual(t.id)

        pending = _all_pending(repo, title=t.title)
        assert len(pending) == 1
        assert pending[0].due_date == '2026-02-28'

    # ------------------------------------------------------------------
    # Spawned task fields
    # ------------------------------------------------------------------

    def test_spawned_task_inherits_key_fields(self, svc, repo):
        t = _create(
            repo,
            title='Stand-up',
            recurrence_rule='daily',
            due_date='2026-03-01',
        )
        t.description = 'morning sync'
        t.priority = 'high'
        t.estimated_minutes = 15
        repo.update(t)

        svc.complete_task_manual(t.id)

        pending = _all_pending(repo, title='Stand-up')
        assert len(pending) == 1
        spawned = pending[0]
        assert spawned.description == 'morning sync'
        assert spawned.priority == 'high'
        assert spawned.estimated_minutes == 15
        assert spawned.is_recurring is True
        assert spawned.recurrence_rule == 'daily'

    def test_spawned_task_has_no_parent_id(self, svc, repo):
        """Spawned recurring task must always be a root task."""
        t = _create(repo, recurrence_rule='daily', due_date='2026-03-01')
        svc.complete_task_manual(t.id)

        pending = _all_pending(repo, title=t.title)
        assert pending[0].parent_id is None

    def test_spawned_task_has_no_completed_at(self, svc, repo):
        t = _create(repo, recurrence_rule='daily', due_date='2026-03-01')
        svc.complete_task_manual(t.id)

        pending = _all_pending(repo, title=t.title)
        assert pending[0].completed_at is None

    def test_start_date_adjusted_proportionally(self, svc, repo):
        """start_date should shift by the same delta as due_date."""
        # start is 2 days before due
        t = _create(
            repo,
            recurrence_rule='weekly',
            due_date='2026-03-08',
            start_date='2026-03-06',   # -2 days relative to due
        )
        svc.complete_task_manual(t.id)

        pending = _all_pending(repo, title=t.title)
        assert len(pending) == 1
        spawned = pending[0]
        assert spawned.due_date == '2026-03-15'
        assert spawned.start_date == '2026-03-13'  # still -2 days

    # ------------------------------------------------------------------
    # Skip conditions
    # ------------------------------------------------------------------

    def test_missing_due_date_skips_spawn(self, svc, repo):
        t = _create(repo, recurrence_rule='daily', due_date=None)
        # Patch model after create (create assigns due_date from arg)
        t_fresh = repo.get_by_id(t.id)
        t_fresh.due_date = None
        repo.update(t_fresh)

        svc.complete_task_manual(t_fresh.id)
        # No new pending task should appear
        all_tasks = repo.get_all_non_deleted()
        pending = [x for x in all_tasks if x.status == 'pending' and x.id != t_fresh.id]
        assert pending == []

    def test_parent_id_skips_spawn(self, svc, repo):
        """V1: recurring tasks with parent_id must not spawn next occurrence."""
        # Create a root parent first
        parent = _create(repo, title='Parent', is_recurring=False, recurrence_rule=None)
        # Create a child that is_recurring
        child = Task(
            id=str(uuid.uuid4()),
            title='RecurringChild',
            status='pending',
            is_recurring=True,
            recurrence_rule='daily',
            due_date='2026-03-01',
            parent_id=parent.id,
        )
        repo.create(child)

        # complete_task_manual can complete a child task too
        svc.complete_task_manual(child.id)

        # No new task should be spawned
        all_tasks = repo.get_all_non_deleted()
        new_pending = [
            t for t in all_tasks
            if t.status == 'pending' and t.id not in (parent.id, child.id)
        ]
        assert new_pending == []

    def test_missing_recurrence_rule_skips_spawn(self, svc, repo):
        t = _task(is_recurring=True, recurrence_rule=None, due_date='2026-03-01')
        repo.create(t)
        svc.complete_task_manual(t.id)

        all_tasks = repo.get_all_non_deleted()
        pending = [x for x in all_tasks if x.status == 'pending']
        assert pending == []

    # ------------------------------------------------------------------
    # Completion paths: complete_child_task (auto-complete parent)
    # ------------------------------------------------------------------

    def test_auto_completed_parent_spawns_recurrence(self, svc, repo):
        """When all children complete and auto_complete_with_children triggers
        the parent, the parent's recurrence must be spawned."""
        parent = Task(
            id=str(uuid.uuid4()),
            title='RecurringParent',
            status='pending',
            is_recurring=True,
            recurrence_rule='daily',
            due_date='2026-03-01',
            auto_complete_with_children=True,
        )
        repo.create(parent)

        child = Task(
            id=str(uuid.uuid4()),
            title='OnlyChild',
            status='pending',
            parent_id=parent.id,
        )
        repo.create(child)

        svc.complete_child_task(child.id)

        # Parent should now be done
        parent_fresh = repo.get_by_id(parent.id)
        assert parent_fresh.status == 'done'

        # A new pending RecurringParent should exist
        pending = _all_pending(repo, title='RecurringParent')
        assert len(pending) == 1
        assert pending[0].due_date == '2026-03-02'

    # ------------------------------------------------------------------
    # Completion paths: complete_parent_with_children
    # ------------------------------------------------------------------

    def test_complete_parent_with_children_spawns_recurrence(self, svc, repo):
        parent = Task(
            id=str(uuid.uuid4()),
            title='WeeklyStandup',
            status='pending',
            is_recurring=True,
            recurrence_rule='weekly',
            due_date='2026-03-08',
        )
        repo.create(parent)

        child = Task(
            id=str(uuid.uuid4()),
            title='SubTask',
            status='pending',
            parent_id=parent.id,
        )
        repo.create(child)

        svc.complete_parent_with_children(parent.id, include_children=True)

        pending = _all_pending(repo, title='WeeklyStandup')
        assert len(pending) == 1
        assert pending[0].due_date == '2026-03-15'

    # ------------------------------------------------------------------
    # Spawn failure does NOT rollback completion
    # ------------------------------------------------------------------

    def test_spawn_failure_does_not_rollback_completion(self, svc, repo, monkeypatch):
        """If _spawn_next_recurrence raises, the completed task must still be done."""
        t = _create(repo, recurrence_rule='daily', due_date='2026-03-01')

        monkeypatch.setattr(
            svc,
            '_spawn_next_recurrence',
            lambda task: (_ for _ in ()).throw(RuntimeError('DB full')),
        )

        svc.complete_task_manual(t.id)

        done = repo.get_by_id(t.id)
        assert done.status == 'done'

    # ------------------------------------------------------------------
    # No duplicate spawn on same completion path
    # ------------------------------------------------------------------

    def test_no_duplicate_spawn_on_single_complete(self, svc, repo):
        """Completing once must produce exactly one new pending task."""
        t = _create(repo, recurrence_rule='daily', due_date='2026-03-01')
        svc.complete_task_manual(t.id)

        pending = _all_pending(repo, title=t.title)
        assert len(pending) == 1
