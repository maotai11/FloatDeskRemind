"""
TaskRepository: CRUD + date-range queries + batch updates.

All write methods accept an optional ``conn`` parameter.
- conn=None  (default): opens its own connection and commits immediately.
- conn=<Connection>: uses the caller-supplied connection without committing.
  The caller is responsible for COMMIT / ROLLBACK (typically via transaction()).
"""
from __future__ import annotations
import sqlite3
import uuid
from pathlib import Path
from typing import List, Optional

from src.data.database import get_connection
from src.data.models import Task
from src.core.paths import DB_PATH
from src.core.utils import now_iso as _now_iso


class TaskRepository:
    def __init__(self, db_path: Path = None):
        self._db = db_path or DB_PATH

    def _conn(self):
        return get_connection(self._db)

    # ------------------------------------------------------------------
    # Create
    # ------------------------------------------------------------------
    def create(self, task: Task, conn: Optional[sqlite3.Connection] = None) -> Task:
        now = _now_iso()
        if not task.id:
            task.id = str(uuid.uuid4())
        task.created_at = now
        task.updated_at = now

        sql = '''INSERT INTO tasks
                   (id, title, description, status, priority, parent_id,
                    sort_order, start_date, due_date, due_time,
                    is_countdown, countdown_target, is_recurring,
                    recurrence_rule, estimated_minutes,
                    auto_complete_with_children, completed_at, deleted_at,
                    created_at, updated_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)'''
        params = (
            task.id, task.title, task.description, task.status,
            task.priority, task.parent_id, task.sort_order,
            task.start_date, task.due_date, task.due_time,
            int(task.is_countdown), task.countdown_target,
            int(task.is_recurring), task.recurrence_rule,
            task.estimated_minutes,
            int(task.auto_complete_with_children),
            task.completed_at, task.deleted_at,
            task.created_at, task.updated_at,
        )
        if conn is not None:
            conn.execute(sql, params)
        else:
            with self._conn() as c:
                c.execute(sql, params)
                c.commit()
        return task

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------
    def get_by_id(self, task_id: str) -> Optional[Task]:
        with self._conn() as conn:
            row = conn.execute(
                'SELECT * FROM tasks WHERE id=?', (task_id,)
            ).fetchone()
        return Task.from_row(row) if row else None

    def get_all_non_deleted(self) -> List[Task]:
        """Return all tasks that are not deleted (includes pending, done, archived)."""
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM tasks WHERE status != 'deleted' ORDER BY sort_order"
            ).fetchall()
        return [Task.from_row(r) for r in rows]

    def get_by_due_dates(self, dates: List[str]) -> List[Task]:
        """Return non-deleted tasks whose due_date is in the given list."""
        if not dates:
            return []
        placeholders = ','.join('?' * len(dates))
        with self._conn() as conn:
            rows = conn.execute(
                f"SELECT * FROM tasks WHERE due_date IN ({placeholders}) "  # nosec B608 — placeholders contains only '?' chars; dates are parameterized
                f"AND status != 'deleted' "
                f"ORDER BY sort_order",
                dates
            ).fetchall()
        return [Task.from_row(r) for r in rows]

    def get_pending_due_in_range(self, from_dt: str, to_dt: str) -> List[Task]:
        """Return pending tasks whose due_date+due_time falls in [from_dt, to_dt].

        Both arguments must be ISO-format strings without seconds: 'YYYY-MM-DDTHH:MM'.
        Only tasks that have both due_date and due_time set are returned.
        """
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM tasks "
                "WHERE status = 'pending' "
                "  AND due_date IS NOT NULL "
                "  AND due_time IS NOT NULL "
                "  AND (due_date || 'T' || due_time) >= ? "
                "  AND (due_date || 'T' || due_time) <= ? "
                "ORDER BY due_date, due_time",
                (from_dt, to_dt),
            ).fetchall()
        return [Task.from_row(r) for r in rows]

    def get_children(self, parent_id: str) -> List[Task]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM tasks WHERE parent_id=? AND status!='deleted' ORDER BY sort_order",
                (parent_id,)
            ).fetchall()
        return [Task.from_row(r) for r in rows]

    def search(self, query: str) -> List[Task]:
        pattern = f'%{query}%'
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM tasks WHERE (title LIKE ? OR description LIKE ?) "
                "AND status NOT IN ('deleted') ORDER BY due_date, sort_order",
                (pattern, pattern)
            ).fetchall()
        return [Task.from_row(r) for r in rows]

    # ------------------------------------------------------------------
    # Update
    # ------------------------------------------------------------------
    def update(self, task: Task, conn: Optional[sqlite3.Connection] = None) -> Task:
        task.updated_at = _now_iso()
        sql = '''UPDATE tasks SET
                   title=?, description=?, status=?, priority=?,
                   parent_id=?, sort_order=?, start_date=?, due_date=?,
                   due_time=?, is_countdown=?, countdown_target=?,
                   is_recurring=?, recurrence_rule=?, estimated_minutes=?,
                   auto_complete_with_children=?, completed_at=?,
                   deleted_at=?, updated_at=?
                   WHERE id=?'''
        params = (
            task.title, task.description, task.status, task.priority,
            task.parent_id, task.sort_order, task.start_date,
            task.due_date, task.due_time, int(task.is_countdown),
            task.countdown_target, int(task.is_recurring),
            task.recurrence_rule, task.estimated_minutes,
            int(task.auto_complete_with_children), task.completed_at,
            task.deleted_at, task.updated_at, task.id,
        )
        if conn is not None:
            conn.execute(sql, params)
        else:
            with self._conn() as c:
                c.execute(sql, params)
                c.commit()
        return task

    def bulk_update_status(
        self,
        task_ids: List[str],
        status: str,
        conn: Optional[sqlite3.Connection] = None,
    ) -> None:
        if not task_ids:
            return
        now = _now_iso()
        completed_at = now if status == 'done' else None
        placeholders = ','.join('?' * len(task_ids))
        sql = (
            f'UPDATE tasks SET status=?, completed_at=?, updated_at=?'  # nosec B608
            f' WHERE id IN ({placeholders})'                             # placeholders = '?,?,...' only
        )
        args = [status, completed_at, now, *task_ids]
        if conn is not None:
            conn.execute(sql, args)
        else:
            with self._conn() as c:
                c.execute(sql, args)
                c.commit()

    # ------------------------------------------------------------------
    # Soft Delete + Recycle Bin
    # ------------------------------------------------------------------
    def soft_delete(self, task_id: str, conn: Optional[sqlite3.Connection] = None) -> None:
        """Mark task as deleted. Does NOT physically remove the row."""
        now = _now_iso()
        sql = "UPDATE tasks SET status='deleted', deleted_at=?, updated_at=? WHERE id=?"
        if conn is not None:
            conn.execute(sql, (now, now, task_id))
        else:
            with self._conn() as c:
                c.execute(sql, (now, now, task_id))
                c.commit()

    def bulk_soft_delete_children(
        self,
        parent_id: str,
        conn: Optional[sqlite3.Connection] = None,
    ) -> None:
        """Soft-delete all children of parent_id in a single SQL statement."""
        now = _now_iso()
        sql = "UPDATE tasks SET status='deleted', deleted_at=?, updated_at=? WHERE parent_id=?"
        if conn is not None:
            conn.execute(sql, (now, now, parent_id))
        else:
            with self._conn() as c:
                c.execute(sql, (now, now, parent_id))
                c.commit()

    def get_deleted(self) -> List[Task]:
        """Return all soft-deleted tasks, newest-deleted first."""
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM tasks WHERE status='deleted' ORDER BY deleted_at DESC"
            ).fetchall()
        return [Task.from_row(r) for r in rows]

    def restore_from_trash(self, task_id: str, conn: Optional[sqlite3.Connection] = None) -> None:
        """Restore a single deleted task to pending.
        Guard: WHERE status='deleted' prevents accidentally restoring done tasks."""
        now = _now_iso()
        sql = "UPDATE tasks SET status='pending', deleted_at=NULL, updated_at=? WHERE id=? AND status='deleted'"
        if conn is not None:
            conn.execute(sql, (now, task_id))
        else:
            with self._conn() as c:
                c.execute(sql, (now, task_id))
                c.commit()

    def permanently_delete(self, task_id: str, conn: Optional[sqlite3.Connection] = None) -> None:
        """Physical DELETE — only for confirmed trash emptying. Irreversible."""
        if conn is not None:
            conn.execute('DELETE FROM tasks WHERE id=?', (task_id,))
        else:
            with self._conn() as c:
                c.execute('DELETE FROM tasks WHERE id=?', (task_id,))
                c.commit()

    # ------------------------------------------------------------------
    # Delete
    # ------------------------------------------------------------------
    def hard_delete(self, task_id: str, conn: Optional[sqlite3.Connection] = None) -> None:
        if conn is not None:
            conn.execute('DELETE FROM tasks WHERE id=?', (task_id,))
        else:
            with self._conn() as c:
                c.execute('DELETE FROM tasks WHERE id=?', (task_id,))
                c.commit()

    def bulk_hard_delete_children(
        self,
        parent_id: str,
        conn: Optional[sqlite3.Connection] = None,
    ) -> None:
        """Delete all children of parent_id in a single SQL statement."""
        if conn is not None:
            conn.execute('DELETE FROM tasks WHERE parent_id=?', (parent_id,))
        else:
            with self._conn() as c:
                c.execute('DELETE FROM tasks WHERE parent_id=?', (parent_id,))
                c.commit()

    def unparent_children(
        self,
        parent_id: str,
        conn: Optional[sqlite3.Connection] = None,
    ) -> None:
        """Set parent_id=NULL for all children of the given task."""
        now = _now_iso()
        sql = 'UPDATE tasks SET parent_id=NULL, updated_at=? WHERE parent_id=?'
        if conn is not None:
            conn.execute(sql, (now, parent_id))
        else:
            with self._conn() as c:
                c.execute(sql, (now, parent_id))
                c.commit()
