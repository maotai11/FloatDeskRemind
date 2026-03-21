"""
PhaseRepository: CRUD for task_phases.
"""
from __future__ import annotations
import uuid
from pathlib import Path
from typing import List

from src.data.database import get_connection
from src.data.models import TaskPhase
from src.core.paths import DB_PATH


class PhaseRepository:
    def __init__(self, db_path: Path = None):
        self._db = db_path or DB_PATH

    def get_phases(self, task_id: str) -> List[TaskPhase]:
        with get_connection(self._db) as conn:
            rows = conn.execute(
                'SELECT * FROM task_phases WHERE task_id=? ORDER BY sort_order',
                (task_id,)
            ).fetchall()
        return [TaskPhase(
            id=r['id'], task_id=r['task_id'], name=r['name'],
            sort_order=float(r['sort_order']),
            start_date=r['start_date'], due_date=r['due_date'],
            status=r['status'],
            depends_on_previous=bool(r['depends_on_previous']),
        ) for r in rows]

    def add_phase(self, task_id: str, name: str) -> TaskPhase:
        phase_id = str(uuid.uuid4())
        with get_connection(self._db) as conn:
            max_row = conn.execute(
                'SELECT COALESCE(MAX(sort_order), 0) FROM task_phases WHERE task_id=?',
                (task_id,)
            ).fetchone()
            sort_order = float(max_row[0]) + 1.0
            conn.execute(
                'INSERT INTO task_phases(id, task_id, name, sort_order, status) '
                'VALUES(?,?,?,?,?)',
                (phase_id, task_id, name, sort_order, 'pending')
            )
            conn.commit()
        return TaskPhase(id=phase_id, task_id=task_id, name=name,
                         sort_order=sort_order)

    def set_status(self, phase_id: str, status: str) -> None:
        with get_connection(self._db) as conn:
            conn.execute(
                'UPDATE task_phases SET status=? WHERE id=?', (status, phase_id)
            )
            conn.commit()

    def delete_phase(self, phase_id: str) -> None:
        with get_connection(self._db) as conn:
            conn.execute('DELETE FROM task_phases WHERE id=?', (phase_id,))
            conn.commit()
