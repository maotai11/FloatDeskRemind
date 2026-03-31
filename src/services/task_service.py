"""
TaskService: business logic for task operations.
Pure Python — no Qt dependency.

Completion scenarios A-E:
  A - Child completed: if all siblings done AND auto_complete_with_children=1, auto-complete parent
  B - Manual parent complete: parent has pending children → return NEEDS_CONFIRM
  C - Has phases: completion checks only children, not phases
  D - Restore: only restores parent, children stay as-is
  E - Delete parent: returns children list, caller decides cascade

Recurrence (Patch 10):
  When any completion path marks a task done and that task is_recurring=True:
    _try_spawn_recurrence() is called AFTER the completion write commits.
    If spawn fails the error is logged but the completed task stays done
    (spawn failure is non-fatal and must never roll back a completion).

  V1 constraints:
    - Recurring tasks with parent_id are skipped (no child-chain recurrence).
    - Tasks without due_date are skipped.
    - Supported rules: 'daily', 'weekly', 'monthly'.
"""
from __future__ import annotations

import uuid
from datetime import date
from enum import Enum, auto
from typing import List, Optional, Tuple

from src.core.logger import logger
from src.core.recurrence import RecurrenceError, next_due_date
from src.core.utils import now_iso as _now_iso
from src.data.database import transaction
from src.data.models import Task
from src.data.task_repository import TaskRepository


class CompleteResult(Enum):
    OK = auto()
    NEEDS_CONFIRM = auto()
    ALREADY_DONE = auto()


class DeleteResult(Enum):
    OK = auto()
    HAS_CHILDREN = auto()


class TaskService:
    def __init__(self, repo: TaskRepository):
        self._repo = repo

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------
    def _validate_no_grandchild(self, parent_id: Optional[str]) -> None:
        """Raise ValueError if parent_id would create a grandchild."""
        if parent_id is None:
            return
        parent = self._repo.get_by_id(parent_id)
        if parent and parent.parent_id is not None:
            raise ValueError('Grandchild tasks are not allowed (max one level)')

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------
    def create_task(self, task: Task) -> Task:
        self._validate_no_grandchild(task.parent_id)
        return self._repo.create(task)

    def update_task(self, task: Task) -> Task:
        if task.parent_id:
            self._validate_no_grandchild(task.parent_id)
        return self._repo.update(task)

    def get_task(self, task_id: str) -> Optional[Task]:
        return self._repo.get_by_id(task_id)

    def get_all_non_deleted(self) -> List[Task]:
        return self._repo.get_all_non_deleted()

    def get_by_due_dates(self, dates: List[str]) -> List[Task]:
        return self._repo.get_by_due_dates(dates)

    def search(self, query: str) -> List[Task]:
        return self._repo.search(query)

    # ------------------------------------------------------------------
    # Scenario A: child completed — maybe auto-complete parent
    # ------------------------------------------------------------------
    def complete_child_task(self, task_id: str) -> Tuple[CompleteResult, Optional[str]]:
        """
        Mark child task as done. If all siblings are done and
        auto_complete_with_children=1, also complete the parent.
        Returns (result, auto_completed_parent_id_or_None)

        Recurrence: child tasks carry parent_id so v1 rule skips them.
        The auto-completed parent (no parent_id) is eligible for recurrence.
        """
        task = self._repo.get_by_id(task_id)
        if not task:
            return CompleteResult.OK, None
        if task.status == 'done':
            return CompleteResult.ALREADY_DONE, None

        task.status = 'done'
        task.completed_at = _now_iso()
        self._repo.update(task)
        logger.debug(f'Task {task_id} marked done')

        # Child recurrence: skipped by v1 rule (has parent_id), but call
        # _try_spawn_recurrence anyway to produce the correct log message.
        self._try_spawn_recurrence(task)

        auto_completed_parent = None
        if task.parent_id:
            parent = self._repo.get_by_id(task.parent_id)
            if parent and parent.auto_complete_with_children and parent.status == 'pending':
                siblings = self._repo.get_children(task.parent_id)
                all_done = all(s.status == 'done' for s in siblings)
                if all_done:
                    parent.status = 'done'
                    parent.completed_at = _now_iso()
                    self._repo.update(parent)
                    auto_completed_parent = parent.id
                    logger.debug(f'Auto-completed parent {parent.id}')
                    # Parent has no parent_id → eligible for recurrence.
                    self._try_spawn_recurrence(parent)

        return CompleteResult.OK, auto_completed_parent

    # ------------------------------------------------------------------
    # Scenario B: manual complete parent
    # ------------------------------------------------------------------
    def complete_task_manual(self, task_id: str) -> CompleteResult:
        """
        Attempt to complete a task manually.
        Returns NEEDS_CONFIRM if it's a parent with pending children.

        Recurrence: spawns next occurrence after marking done (OK path only).
        """
        task = self._repo.get_by_id(task_id)
        if not task:
            return CompleteResult.OK
        if task.status == 'done':
            return CompleteResult.ALREADY_DONE

        children = self._repo.get_children(task_id)
        pending_children = [c for c in children if c.status != 'done']

        if pending_children:
            return CompleteResult.NEEDS_CONFIRM

        # No pending children or is a child task itself
        task.status = 'done'
        task.completed_at = _now_iso()
        self._repo.update(task)
        # Recurrence spawn is outside any transaction — failure is non-fatal.
        self._try_spawn_recurrence(task)
        return CompleteResult.OK

    def complete_parent_with_children(self, task_id: str, include_children: bool) -> None:
        """Called after user confirms scenario B dialog.
        bulk_update_status + update are wrapped in a single transaction
        so a crash between them cannot leave children done but parent pending.

        Recurrence: spawns for parent AFTER the transaction commits.
        Children carry parent_id → v1 rule skips them.
        """
        task = self._repo.get_by_id(task_id)
        if not task:
            return
        task.status = 'done'
        task.completed_at = _now_iso()
        with transaction(self._repo._db) as conn:
            if include_children:
                children = self._repo.get_children(task_id)
                pending = [c.id for c in children if c.status != 'done']
                if pending:
                    self._repo.bulk_update_status(pending, 'done', conn=conn)
            self._repo.update(task, conn=conn)
        # Transaction committed — now safe to attempt recurrence spawn.
        self._try_spawn_recurrence(task)

    # ------------------------------------------------------------------
    # Scenario D: restore
    # ------------------------------------------------------------------
    def restore_task(self, task_id: str) -> None:
        """Restore only the task itself; children stay as-is."""
        task = self._repo.get_by_id(task_id)
        if not task:
            return
        task.status = 'pending'
        task.completed_at = None
        self._repo.update(task)

    # ------------------------------------------------------------------
    # Scenario E: delete parent
    # ------------------------------------------------------------------
    def get_delete_preview(self, task_id: str) -> List[Task]:
        """Return list of children that would be affected by deletion."""
        return self._repo.get_children(task_id)

    def delete_task(self, task_id: str, cascade: bool) -> None:
        """
        Soft-delete: marks status='deleted', does NOT physically remove rows.

        cascade=True: soft-delete parent + all children atomically
        cascade=False: unparent children + soft-delete parent atomically

        Both steps are wrapped in a single transaction so a crash between
        them cannot leave partial state.
        """
        with transaction(self._repo._db) as conn:
            if cascade:
                self._repo.bulk_soft_delete_children(task_id, conn=conn)
            else:
                self._repo.unparent_children(task_id, conn=conn)
            self._repo.soft_delete(task_id, conn=conn)
        logger.debug(f'Soft deleted task {task_id} cascade={cascade}')

    # ------------------------------------------------------------------
    # Recycle bin
    # ------------------------------------------------------------------
    def get_recycle_bin(self) -> List[Task]:
        """Return all soft-deleted tasks for recycle bin view."""
        return self._repo.get_deleted()

    def restore_from_trash(self, task_id: str) -> None:
        """Restore a deleted task to pending.
        Distinct from restore_task() (done→pending); this is deleted→pending."""
        self._repo.restore_from_trash(task_id)

    def permanently_delete(self, task_id: str) -> None:
        """Permanently erase a task from the recycle bin. Irreversible."""
        self._repo.permanently_delete(task_id)

    # ------------------------------------------------------------------
    # Recurrence — private helpers
    # ------------------------------------------------------------------

    def _try_spawn_recurrence(self, completed_task: Task) -> Optional[Task]:
        """Attempt to spawn the next recurrence of a completed recurring task.

        Returns the spawned Task on success, None on skip or failure.
        NEVER raises — any exception is logged as ERROR and swallowed so that
        the caller's 'done' write is not rolled back.
        """
        try:
            return self._spawn_next_recurrence(completed_task)
        except Exception as exc:
            logger.error(
                '[recurrence] Failed to spawn next occurrence for task %s '
                '("%s"): %s',
                completed_task.id,
                completed_task.title,
                exc,
            )
            return None

    def _spawn_next_recurrence(self, completed_task: Task) -> Optional[Task]:
        """Compute and create the next recurring task instance.

        Returns the new Task or None (on a known skip condition).
        Raises RecurrenceError (or any other exception) on unexpected failure;
        the caller (_try_spawn_recurrence) handles those.

        Skip conditions (logged as WARNING):
          1. is_recurring is False or recurrence_rule is missing.
          2. Task has a parent_id (v1: child-chain recurrence not supported).
          3. due_date is missing (no anchor date to advance from).
        """
        if not completed_task.is_recurring:
            return None

        if not completed_task.recurrence_rule:
            logger.warning(
                '[recurrence] Task %s is_recurring=True but recurrence_rule is empty; skipping',
                completed_task.id,
            )
            return None

        if completed_task.parent_id:
            logger.warning(
                '[recurrence] Task %s has parent_id="%s" — v1 does not support '
                'parent/child recurrence chains; skipping',
                completed_task.id,
                completed_task.parent_id,
            )
            return None

        if not completed_task.due_date:
            logger.warning(
                '[recurrence] Task %s is_recurring=True but due_date is missing; skipping',
                completed_task.id,
            )
            return None

        new_due = next_due_date(completed_task.due_date, completed_task.recurrence_rule)

        # Shift start_date by the same calendar delta as due_date (best-effort).
        new_start: Optional[str] = None
        if completed_task.start_date:
            try:
                old_due_d = date.fromisoformat(completed_task.due_date)
                old_start_d = date.fromisoformat(completed_task.start_date)
                delta = old_start_d - old_due_d
                new_start = (date.fromisoformat(new_due) + delta).isoformat()
            except Exception as exc:
                logger.debug(
                    '[recurrence] Could not adjust start_date for task %s: %s',
                    completed_task.id,
                    exc,
                )

        next_task = Task(
            id=str(uuid.uuid4()),
            title=completed_task.title,
            description=completed_task.description,
            priority=completed_task.priority,
            status='pending',
            is_recurring=True,
            recurrence_rule=completed_task.recurrence_rule,
            due_date=new_due,
            due_time=completed_task.due_time,
            start_date=new_start,
            estimated_minutes=completed_task.estimated_minutes,
            auto_complete_with_children=completed_task.auto_complete_with_children,
            # Intentionally NOT copied:
            #   parent_id  — v1 spawned tasks are always root tasks
            #   completed_at, deleted_at — fresh task has no history
            #   is_countdown, countdown_target — not part of recurrence
        )

        created = self._repo.create(next_task)
        logger.info(
            '[recurrence] Spawned next occurrence %s for task "%s" → due %s',
            created.id,
            completed_task.title,
            new_due,
        )
        return created
