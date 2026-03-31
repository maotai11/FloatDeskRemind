"""
ReminderRepository: CRUD for the task_reminders table.

Schema (v001_initial, unchanged):
    id             TEXT PRIMARY KEY
    task_id        TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE
    mode           TEXT NOT NULL DEFAULT 'before'
    minutes_before INTEGER
    remind_at      TEXT              -- ISO 'YYYY-MM-DDTHH:MM:SS'
    is_fired       INTEGER NOT NULL DEFAULT 0

DueReminder is a minimal projection returned by list_due() that includes the
task title (from a JOIN) so the scheduler does not need a second DB trip.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from src.data.database import get_connection
from src.data.models import TaskReminder
from src.core.paths import DB_PATH


# ---------------------------------------------------------------------------
# Projection dataclass
# ---------------------------------------------------------------------------

@dataclass
class DueReminder:
    """Minimal read-only projection used by ReminderScheduler.

    Includes task_title (JOIN from tasks) so no secondary lookup is needed.
    """
    reminder_id: str
    task_id: str
    task_title: str
    remind_at: str


# ---------------------------------------------------------------------------
# Repository
# ---------------------------------------------------------------------------

class ReminderRepository:
    """CRUD and query operations for the task_reminders table."""

    def __init__(self, db_path: Path = None) -> None:
        self._db = db_path or DB_PATH

    def _conn(self):
        return get_connection(self._db)

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    def list_due(self, now_iso: str) -> List[DueReminder]:
        """Return unfired reminders whose remind_at <= now_iso for non-deleted tasks.

        Filters:
          - is_fired = 0
          - remind_at IS NOT NULL
          - remind_at <= now_iso   (ISO string comparison works because format is fixed)
          - tasks.status != 'deleted'

        Results are ordered by remind_at ascending so oldest-overdue fire first.
        """
        sql = """
            SELECT r.id, r.task_id, t.title, r.remind_at
            FROM task_reminders r
            JOIN tasks t ON r.task_id = t.id
            WHERE r.is_fired = 0
              AND r.remind_at IS NOT NULL
              AND r.remind_at <= ?
              AND t.status != 'deleted'
            ORDER BY r.remind_at ASC
        """
        with self._conn() as conn:
            rows = conn.execute(sql, (now_iso,)).fetchall()
        return [
            DueReminder(
                reminder_id=row['id'],
                task_id=row['task_id'],
                task_title=row['title'],
                remind_at=row['remind_at'],
            )
            for row in rows
        ]

    def get_by_id(self, reminder_id: str) -> Optional[TaskReminder]:
        """Return a single TaskReminder by primary key, or None if not found."""
        with self._conn() as conn:
            row = conn.execute(
                'SELECT * FROM task_reminders WHERE id = ?', (reminder_id,)
            ).fetchone()
        if row is None:
            return None
        d = dict(row)
        return TaskReminder(
            id=d['id'],
            task_id=d['task_id'],
            mode=d.get('mode', 'at'),
            minutes_before=d.get('minutes_before'),
            remind_at=d.get('remind_at'),
            is_fired=bool(d.get('is_fired', 0)),
        )

    def get_by_task_id(self, task_id: str) -> Optional[TaskReminder]:
        """Return the first reminder for a task, preferring unfired ones.

        Returns None if the task has no reminders.
        Used by the task edit UI to pre-populate reminder fields.
        """
        sql = """
            SELECT * FROM task_reminders
            WHERE task_id = ?
            ORDER BY is_fired ASC, remind_at ASC
            LIMIT 1
        """
        with self._conn() as conn:
            row = conn.execute(sql, (task_id,)).fetchone()
        if row is None:
            return None
        d = dict(row)
        return TaskReminder(
            id=d['id'],
            task_id=d['task_id'],
            mode=d.get('mode', 'at'),
            minutes_before=d.get('minutes_before'),
            remind_at=d.get('remind_at'),
            is_fired=bool(d.get('is_fired', 0)),
        )

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def create(self, reminder: TaskReminder) -> TaskReminder:
        """Insert a new reminder row.  Assigns a UUID if reminder.id is empty."""
        if not reminder.id:
            reminder.id = str(uuid.uuid4())
        sql = """
            INSERT INTO task_reminders (id, task_id, mode, minutes_before, remind_at, is_fired)
            VALUES (?, ?, ?, ?, ?, ?)
        """
        with self._conn() as conn:
            conn.execute(sql, (
                reminder.id,
                reminder.task_id,
                reminder.mode,
                reminder.minutes_before,
                reminder.remind_at,
                int(reminder.is_fired),
            ))
            conn.commit()
        return reminder

    def mark_fired(self, reminder_id: str) -> None:
        """Set is_fired = 1 for the given reminder.

        Called by ReminderScheduler BEFORE emitting the notification signal
        to guarantee at-most-once delivery even if the signal handler raises.
        """
        with self._conn() as conn:
            conn.execute(
                'UPDATE task_reminders SET is_fired = 1 WHERE id = ?',
                (reminder_id,),
            )
            conn.commit()

    def delete(self, reminder_id: str) -> None:
        """Physically delete a reminder by primary key."""
        with self._conn() as conn:
            conn.execute(
                'DELETE FROM task_reminders WHERE id = ?', (reminder_id,)
            )
            conn.commit()

    def delete_by_task_id(self, task_id: str) -> None:
        """Physically delete ALL reminders for a task_id.

        Used when the user disables reminders for a task via the edit UI.
        """
        with self._conn() as conn:
            conn.execute(
                'DELETE FROM task_reminders WHERE task_id = ?', (task_id,)
            )
            conn.commit()
