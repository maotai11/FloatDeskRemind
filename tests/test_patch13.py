"""
Patch 13 — Task Interaction Enhancement: service-level integration tests.

Tests cover:
  - complete pending task via complete_requested path
  - complete_requested on done task: no-op
  - delete task → soft-deleted (status='deleted')
  - recurring task completed → next occurrence spawned
  - non-recurring task completed → no spawn
  - delete cascade: parent + children all soft-deleted
  - no exception on any of the above paths
"""
from __future__ import annotations

import uuid
from typing import Optional

import pytest

from src.data.models import Task
from src.services.task_service import TaskService, CompleteResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _task(
    *,
    title: str = 'Task',
    status: str = 'pending',
    due_date: Optional[str] = None,
    parent_id: Optional[str] = None,
    is_recurring: bool = False,
    recurrence_rule: Optional[str] = None,
    auto_complete_with_children: bool = False,
) -> Task:
    return Task(
        id=str(uuid.uuid4()),
        title=title,
        status=status,
        due_date=due_date,
        parent_id=parent_id,
        is_recurring=is_recurring,
        recurrence_rule=recurrence_rule,
        auto_complete_with_children=auto_complete_with_children,
    )


# ---------------------------------------------------------------------------
# Complete pending task (Enter-key path)
# ---------------------------------------------------------------------------

class TestCompletePendingTask:

    def test_complete_pending_sets_done(self, task_service, task_repo):
        t = _task(status='pending')
        task_repo.create(t)
        task_service.complete_task_manual(t.id)
        assert task_repo.get_by_id(t.id).status == 'done'

    def test_complete_done_task_is_noop(self, task_service, task_repo):
        """complete_task_manual on a done task must not raise and must return ALREADY_DONE."""
        t = _task(status='done')
        task_repo.create(t)
        result = task_service.complete_task_manual(t.id)
        assert result == CompleteResult.ALREADY_DONE
        assert task_repo.get_by_id(t.id).status == 'done'

    def test_complete_nonexistent_task_is_noop(self, task_service):
        """complete_task_manual on unknown id must not raise."""
        result = task_service.complete_task_manual(str(uuid.uuid4()))
        assert result == CompleteResult.OK  # returns OK when task not found (graceful no-op)

    def test_complete_pending_does_not_raise(self, task_service, task_repo):
        t = _task(status='pending')
        task_repo.create(t)
        try:
            task_service.complete_task_manual(t.id)
        except Exception as exc:
            pytest.fail(f'complete_task_manual raised unexpectedly: {exc}')


# ---------------------------------------------------------------------------
# Delete task (soft-delete path)
# ---------------------------------------------------------------------------

class TestDeleteTask:

    def test_delete_sets_status_deleted(self, task_service, task_repo):
        t = _task()
        task_repo.create(t)
        task_service.delete_task(t.id, cascade=False)
        row = task_repo.get_by_id(t.id)
        assert row.status == 'deleted'

    def test_delete_not_hard_remove(self, task_service, task_repo):
        """Soft-delete: row must still exist in DB after delete."""
        t = _task()
        task_repo.create(t)
        task_service.delete_task(t.id, cascade=False)
        assert task_repo.get_by_id(t.id) is not None

    def test_delete_cascade_also_deletes_children(self, task_service, task_repo):
        parent = _task(title='Parent')
        child1 = _task(title='Child 1', parent_id=parent.id)
        child2 = _task(title='Child 2', parent_id=parent.id)
        task_repo.create(parent)
        task_repo.create(child1)
        task_repo.create(child2)

        task_service.delete_task(parent.id, cascade=True)

        assert task_repo.get_by_id(parent.id).status == 'deleted'
        assert task_repo.get_by_id(child1.id).status == 'deleted'
        assert task_repo.get_by_id(child2.id).status == 'deleted'

    def test_delete_no_cascade_unparents_children(self, task_service, task_repo):
        parent = _task(title='Parent')
        child = _task(title='Child', parent_id=parent.id)
        task_repo.create(parent)
        task_repo.create(child)

        task_service.delete_task(parent.id, cascade=False)

        assert task_repo.get_by_id(parent.id).status == 'deleted'
        # child should still exist and be unparented
        updated_child = task_repo.get_by_id(child.id)
        assert updated_child is not None
        assert updated_child.status != 'deleted'
        assert updated_child.parent_id is None

    def test_delete_does_not_raise(self, task_service, task_repo):
        t = _task()
        task_repo.create(t)
        try:
            task_service.delete_task(t.id, cascade=False)
        except Exception as exc:
            pytest.fail(f'delete_task raised unexpectedly: {exc}')


# ---------------------------------------------------------------------------
# Recurrence on completion
# ---------------------------------------------------------------------------

class TestRecurrenceOnComplete:

    def test_recurring_task_spawns_next_on_complete(self, task_service, task_repo):
        t = _task(
            title='Daily standup',
            status='pending',
            due_date='2026-04-10',
            is_recurring=True,
            recurrence_rule='daily',
        )
        task_repo.create(t)
        task_service.complete_task_manual(t.id)

        all_tasks = task_repo.get_all_non_deleted()
        titles = [x.title for x in all_tasks]
        assert 'Daily standup' in titles

        # Spawned task has a later due date
        spawned = [x for x in all_tasks if x.id != t.id and x.title == 'Daily standup']
        assert len(spawned) == 1
        assert spawned[0].due_date == '2026-04-11'
        assert spawned[0].status == 'pending'

    def test_non_recurring_task_does_not_spawn(self, task_service, task_repo):
        t = _task(
            title='One-off',
            status='pending',
            due_date='2026-04-10',
            is_recurring=False,
        )
        task_repo.create(t)
        task_service.complete_task_manual(t.id)

        all_tasks = task_repo.get_all_non_deleted()
        pending = [x for x in all_tasks if x.status == 'pending']
        assert len(pending) == 0

    def test_recurring_weekly_spawns_7_days_later(self, task_service, task_repo):
        t = _task(
            title='Weekly review',
            status='pending',
            due_date='2026-04-10',
            is_recurring=True,
            recurrence_rule='weekly',
        )
        task_repo.create(t)
        task_service.complete_task_manual(t.id)

        all_tasks = task_repo.get_all_non_deleted()
        spawned = [x for x in all_tasks if x.id != t.id and x.title == 'Weekly review']
        assert len(spawned) == 1
        assert spawned[0].due_date == '2026-04-17'

    def test_recurring_monthly_spawns_one_month_later(self, task_service, task_repo):
        t = _task(
            title='Monthly report',
            status='pending',
            due_date='2026-03-31',
            is_recurring=True,
            recurrence_rule='monthly',
        )
        task_repo.create(t)
        task_service.complete_task_manual(t.id)

        all_tasks = task_repo.get_all_non_deleted()
        spawned = [x for x in all_tasks if x.id != t.id and x.title == 'Monthly report']
        assert len(spawned) == 1
        assert spawned[0].due_date == '2026-04-30'  # month-end clamp

    def test_recurring_child_task_does_not_spawn(self, task_service, task_repo):
        """v1: child tasks never spawn recurrences."""
        parent = _task(title='Parent')
        child = _task(
            title='Recurring child',
            parent_id=parent.id,
            due_date='2026-04-10',
            is_recurring=True,
            recurrence_rule='daily',
        )
        task_repo.create(parent)
        task_repo.create(child)
        task_service.complete_child_task(child.id)

        all_tasks = task_repo.get_all_non_deleted()
        spawned = [
            x for x in all_tasks
            if x.title == 'Recurring child' and x.status == 'pending'
        ]
        assert len(spawned) == 0

    def test_recurrence_spawn_failure_does_not_rollback_completion(
        self, task_service, task_repo, monkeypatch
    ):
        """If spawn raises, the original task is still marked done."""
        t = _task(
            title='Boom',
            status='pending',
            due_date='2026-04-10',
            is_recurring=True,
            recurrence_rule='daily',
        )
        task_repo.create(t)

        # Force _spawn_next_recurrence to raise
        monkeypatch.setattr(
            task_service, '_spawn_next_recurrence',
            lambda task: (_ for _ in ()).throw(RuntimeError('spawn error'))
        )

        task_service.complete_task_manual(t.id)
        assert task_repo.get_by_id(t.id).status == 'done'


# ---------------------------------------------------------------------------
# Restore task (done → pending)
# ---------------------------------------------------------------------------

class TestRestoreTask:

    def test_restore_done_task_sets_pending(self, task_service, task_repo):
        t = _task(status='done')
        task_repo.create(t)
        task_service.restore_task(t.id)
        assert task_repo.get_by_id(t.id).status == 'pending'

    def test_restore_pending_task_is_noop(self, task_service, task_repo):
        t = _task(status='pending')
        task_repo.create(t)
        task_service.restore_task(t.id)
        assert task_repo.get_by_id(t.id).status == 'pending'
