"""
Tests for Patch 11 — Reminder + Recurrence minimal UI wiring.

Covers:
  - ReminderRepository.get_by_task_id()
  - ReminderRepository.delete_by_task_id()
  - Service-level integration: create task with recurrence fields
  - Service-level integration: create task then add reminder (AppController pattern)
  - Service-level integration: update/replace reminder
  - Service-level integration: disable reminder → reminder deleted
  - Recurrence + no due_date → Patch 10 engine still skips spawn (regression guard)
  - Child task with is_recurring=True + parent_id → v1 skip still works
"""
from __future__ import annotations

import uuid
from pathlib import Path
from typing import Optional

import pytest

from src.data.database import run_migrations
from src.data.models import Task, TaskReminder
from src.data.reminder_repository import ReminderRepository
from src.data.task_repository import TaskRepository
from src.services.task_service import TaskService


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def db(tmp_path) -> Path:
    db_path = tmp_path / 'test.db'
    run_migrations(db_path)
    return db_path


@pytest.fixture
def task_repo(db) -> TaskRepository:
    return TaskRepository(db)


@pytest.fixture
def reminder_repo(db) -> ReminderRepository:
    return ReminderRepository(db)


@pytest.fixture
def svc(task_repo) -> TaskService:
    return TaskService(task_repo)


def _mk_task(
    *,
    title: str = 'Task',
    due_date: Optional[str] = '2026-04-01',
    is_recurring: bool = False,
    recurrence_rule: Optional[str] = None,
    parent_id: Optional[str] = None,
) -> Task:
    return Task(
        id=str(uuid.uuid4()),
        title=title,
        status='pending',
        due_date=due_date,
        is_recurring=is_recurring,
        recurrence_rule=recurrence_rule,
        parent_id=parent_id,
    )


def _mk_reminder(task_id: str, remind_at: str = '2026-04-01T09:00:00', is_fired: bool = False) -> TaskReminder:
    return TaskReminder(
        id=str(uuid.uuid4()),
        task_id=task_id,
        mode='at',
        remind_at=remind_at,
        is_fired=is_fired,
    )


# ===========================================================================
# TestReminderRepositoryGetByTaskId
# ===========================================================================

class TestReminderRepositoryGetByTaskId:

    def test_returns_none_when_no_reminder(self, task_repo, reminder_repo):
        t = _mk_task()
        task_repo.create(t)
        assert reminder_repo.get_by_task_id(t.id) is None

    def test_returns_reminder_when_exists(self, task_repo, reminder_repo):
        t = _mk_task()
        task_repo.create(t)
        r = _mk_reminder(t.id, '2026-04-01T09:00:00')
        reminder_repo.create(r)

        found = reminder_repo.get_by_task_id(t.id)
        assert found is not None
        assert found.task_id == t.id
        assert found.remind_at == '2026-04-01T09:00:00'

    def test_prefers_unfired_when_both_exist(self, task_repo, reminder_repo):
        """If a task has a fired + unfired reminder, unfired is returned first."""
        t = _mk_task()
        task_repo.create(t)

        fired = _mk_reminder(t.id, '2026-03-01T09:00:00', is_fired=True)
        unfired = _mk_reminder(t.id, '2026-04-01T09:00:00', is_fired=False)
        reminder_repo.create(fired)
        reminder_repo.create(unfired)

        found = reminder_repo.get_by_task_id(t.id)
        assert found is not None
        assert found.is_fired is False
        assert found.remind_at == '2026-04-01T09:00:00'

    def test_returns_none_for_unknown_task_id(self, reminder_repo):
        assert reminder_repo.get_by_task_id('nonexistent-task-id') is None


# ===========================================================================
# TestReminderRepositoryDeleteByTaskId
# ===========================================================================

class TestReminderRepositoryDeleteByTaskId:

    def test_deletes_all_reminders_for_task(self, task_repo, reminder_repo):
        t = _mk_task()
        task_repo.create(t)
        reminder_repo.create(_mk_reminder(t.id, '2026-04-01T09:00:00'))
        reminder_repo.create(_mk_reminder(t.id, '2026-04-02T09:00:00'))

        reminder_repo.delete_by_task_id(t.id)

        assert reminder_repo.get_by_task_id(t.id) is None

    def test_noop_when_no_reminders(self, task_repo, reminder_repo):
        t = _mk_task()
        task_repo.create(t)
        # Must not raise
        reminder_repo.delete_by_task_id(t.id)

    def test_does_not_affect_other_tasks(self, task_repo, reminder_repo):
        t1 = _mk_task(title='Task 1')
        t2 = _mk_task(title='Task 2')
        task_repo.create(t1)
        task_repo.create(t2)
        reminder_repo.create(_mk_reminder(t1.id))
        reminder_repo.create(_mk_reminder(t2.id))

        reminder_repo.delete_by_task_id(t1.id)

        assert reminder_repo.get_by_task_id(t1.id) is None
        assert reminder_repo.get_by_task_id(t2.id) is not None


# ===========================================================================
# TestTaskRecurrenceFields — saving recurrence info via service
# ===========================================================================

class TestTaskRecurrenceFields:

    def test_create_recurring_task_persists_fields(self, svc, task_repo):
        t = _mk_task(is_recurring=True, recurrence_rule='weekly', due_date='2026-04-08')
        svc.create_task(t)

        fetched = task_repo.get_by_id(t.id)
        assert fetched.is_recurring is True
        assert fetched.recurrence_rule == 'weekly'

    def test_create_non_recurring_task_has_null_rule(self, svc, task_repo):
        t = _mk_task(is_recurring=False, recurrence_rule=None)
        svc.create_task(t)

        fetched = task_repo.get_by_id(t.id)
        assert fetched.is_recurring is False
        assert fetched.recurrence_rule is None

    def test_update_task_adds_recurrence(self, svc, task_repo):
        t = _mk_task()
        svc.create_task(t)

        t.is_recurring = True
        t.recurrence_rule = 'monthly'
        svc.update_task(t)

        fetched = task_repo.get_by_id(t.id)
        assert fetched.is_recurring is True
        assert fetched.recurrence_rule == 'monthly'

    def test_update_task_removes_recurrence(self, svc, task_repo):
        t = _mk_task(is_recurring=True, recurrence_rule='daily')
        svc.create_task(t)

        t.is_recurring = False
        t.recurrence_rule = None
        svc.update_task(t)

        fetched = task_repo.get_by_id(t.id)
        assert fetched.is_recurring is False
        assert fetched.recurrence_rule is None


# ===========================================================================
# TestCreateTaskWithReminder — simulates AppController._on_add_task flow
# ===========================================================================

class TestCreateTaskWithReminder:

    def _app_controller_flow(self, svc, reminder_repo, task: Task, remind_at: Optional[str]):
        """Simulate AppController._on_add_task(task, remind_at)."""
        svc.create_task(task)
        if remind_at:
            r = TaskReminder(id='', task_id=task.id, mode='at', remind_at=remind_at)
            reminder_repo.create(r)

    def test_creates_reminder_alongside_task(self, svc, task_repo, reminder_repo):
        t = _mk_task(due_date='2026-04-01')
        remind_at = '2026-04-01T08:00:00'

        self._app_controller_flow(svc, reminder_repo, t, remind_at)

        r = reminder_repo.get_by_task_id(t.id)
        assert r is not None
        assert r.remind_at == remind_at
        assert r.task_id == t.id
        assert r.is_fired is False

    def test_no_reminder_when_remind_at_is_none(self, svc, reminder_repo):
        t = _mk_task()
        self._app_controller_flow(svc, reminder_repo, t, None)

        assert reminder_repo.get_by_task_id(t.id) is None

    def test_task_created_even_if_remind_at_present(self, svc, task_repo, reminder_repo):
        t = _mk_task()
        self._app_controller_flow(svc, reminder_repo, t, '2026-04-01T09:00:00')

        fetched = task_repo.get_by_id(t.id)
        assert fetched is not None
        assert fetched.title == t.title


# ===========================================================================
# TestRightPanelReminderSavePattern — simulates RightPanel._save_reminder flow
# ===========================================================================

class TestRightPanelReminderSavePattern:

    def _save_reminder(self, reminder_repo: ReminderRepository, task_id: str, remind_at: Optional[str]) -> None:
        """Simulate RightPanel._save_reminder logic (delete-then-insert)."""
        if remind_at:
            reminder_repo.delete_by_task_id(task_id)
            r = TaskReminder(id='', task_id=task_id, mode='at', remind_at=remind_at)
            reminder_repo.create(r)
        else:
            reminder_repo.delete_by_task_id(task_id)

    def test_save_creates_new_reminder(self, task_repo, reminder_repo):
        t = _mk_task()
        task_repo.create(t)

        self._save_reminder(reminder_repo, t.id, '2026-05-01T10:00:00')

        r = reminder_repo.get_by_task_id(t.id)
        assert r is not None
        assert r.remind_at == '2026-05-01T10:00:00'

    def test_save_replaces_existing_reminder(self, task_repo, reminder_repo):
        t = _mk_task()
        task_repo.create(t)
        reminder_repo.create(_mk_reminder(t.id, '2026-04-01T09:00:00'))

        self._save_reminder(reminder_repo, t.id, '2026-05-15T10:00:00')

        r = reminder_repo.get_by_task_id(t.id)
        assert r is not None
        assert r.remind_at == '2026-05-15T10:00:00'
        # Only one reminder should exist
        rows = [r]  # get_by_task_id returns 1; verify no duplicates via list_due
        due = reminder_repo.list_due('2026-12-31T23:59:59')
        task_dues = [d for d in due if d.task_id == t.id]
        assert len(task_dues) == 1

    def test_disable_reminder_deletes_existing(self, task_repo, reminder_repo):
        t = _mk_task()
        task_repo.create(t)
        reminder_repo.create(_mk_reminder(t.id, '2026-04-01T09:00:00'))

        self._save_reminder(reminder_repo, t.id, None)  # remind_at=None → delete

        assert reminder_repo.get_by_task_id(t.id) is None

    def test_disable_when_none_exists_is_safe(self, task_repo, reminder_repo):
        t = _mk_task()
        task_repo.create(t)

        # Must not raise
        self._save_reminder(reminder_repo, t.id, None)


# ===========================================================================
# TestRecurrenceNoDueDateV1 — regression: UI validation ensures due_date is set,
# but even if bypassed, Patch 10 engine handles it gracefully
# ===========================================================================

class TestRecurrenceNoDueDateV1:

    def test_complete_recurring_task_no_due_date_does_not_spawn(self, svc, task_repo):
        """If due_date is missing (UI validation bypass), no spawn must occur."""
        t = _mk_task(is_recurring=True, recurrence_rule='daily', due_date=None)
        svc.create_task(t)
        # Manually clear due_date in DB to simulate bypass
        t.due_date = None
        task_repo.update(t)

        svc.complete_task_manual(t.id)

        # No new pending task should be spawned
        all_tasks = task_repo.get_all_non_deleted()
        pending = [x for x in all_tasks if x.status == 'pending' and x.id != t.id]
        assert pending == []

    def test_complete_child_recurring_task_skips_spawn(self, svc, task_repo):
        """Child task with parent_id: v1 rule skips recurrence spawn."""
        parent = _mk_task(title='Parent', is_recurring=False)
        svc.create_task(parent)

        child = Task(
            id=str(uuid.uuid4()),
            title='RecurringChild',
            status='pending',
            is_recurring=True,
            recurrence_rule='daily',
            due_date='2026-04-01',
            parent_id=parent.id,
        )
        task_repo.create(child)

        svc.complete_task_manual(child.id)

        # No new task spawned
        all_tasks = task_repo.get_all_non_deleted()
        new_pending = [
            t for t in all_tasks
            if t.status == 'pending' and t.id not in (parent.id, child.id)
        ]
        assert new_pending == []
