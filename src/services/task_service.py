"""
TaskService: business logic for task operations.
Pure Python — no Qt dependency.

Completion scenarios A-E:
  A - Child completed: if all siblings done AND auto_complete_with_children=1, auto-complete parent
  B - Manual parent complete: parent has pending children → return NEEDS_CONFIRM
  C - Has phases: completion checks only children, not phases
  D - Restore: only restores parent, children stay as-is
  E - Delete parent: returns children list, caller decides cascade
"""
from __future__ import annotations
from enum import Enum, auto
from typing import List, Optional, Tuple

from src.data.models import Task
from src.data.task_repository import TaskRepository
from src.data.database import transaction
from src.core.logger import logger
from src.core.utils import now_iso as _now_iso


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

    def get_all_active(self) -> List[Task]:
        return self._repo.get_all_active()

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

        return CompleteResult.OK, auto_completed_parent

    # ------------------------------------------------------------------
    # Scenario B: manual complete parent
    # ------------------------------------------------------------------
    def complete_task_manual(self, task_id: str) -> CompleteResult:
        """
        Attempt to complete a task manually.
        Returns NEEDS_CONFIRM if it's a parent with pending children.
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
        return CompleteResult.OK

    def complete_parent_with_children(self, task_id: str, include_children: bool) -> None:
        """Called after user confirms scenario B dialog.
        bulk_update_status + update are wrapped in a single transaction
        so a crash between them cannot leave children done but parent pending.
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
        cascade=True: delete parent + all children atomically
        cascade=False: unparent children + delete parent atomically

        Both steps are wrapped in a single transaction so a crash between
        them cannot leave children deleted while the parent still exists,
        or a parent deleted while children are still parented to it.
        """
        with transaction(self._repo._db) as conn:
            if cascade:
                self._repo.bulk_hard_delete_children(task_id, conn=conn)
            else:
                self._repo.unparent_children(task_id, conn=conn)
            self._repo.hard_delete(task_id, conn=conn)
        logger.debug(f'Deleted task {task_id} cascade={cascade}')

