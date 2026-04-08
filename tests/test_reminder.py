"""
Tests for Patch 9 — Reminder Scheduler.

TestReminderRepository (12 tests): pure DB, no Qt dependency
TestReminderScheduler  (7 tests):  uses mock repo; QApplication fixture for Qt
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest

from src.data.database import run_migrations
from src.data.models import TaskReminder
from src.data.reminder_repository import DueReminder, ReminderRepository
from src.services.reminder_scheduler import ReminderScheduler, _fmt_remind_at


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _iso(offset_seconds: int = 0) -> str:
    """Return now ± offset_seconds as ISO 'YYYY-MM-DDTHH:MM:SS'."""
    dt = datetime.now() + timedelta(seconds=offset_seconds)
    return dt.strftime('%Y-%m-%dT%H:%M:%S')


def _make_reminder(task_id: str, remind_at: str, is_fired: bool = False) -> TaskReminder:
    return TaskReminder(
        id=str(uuid.uuid4()),
        task_id=task_id,
        mode='before',
        minutes_before=5,
        remind_at=remind_at,
        is_fired=is_fired,
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def db(tmp_path) -> Path:
    """Migrated DB in a temp dir."""
    db_path = tmp_path / 'test.db'
    run_migrations(db_path)
    return db_path


@pytest.fixture
def repo(db) -> ReminderRepository:
    return ReminderRepository(db)


@pytest.fixture
def task_repo(db):
    from src.data.task_repository import TaskRepository
    return TaskRepository(db)


def _create_task(task_repo, title: str = 'Test Task', status: str = 'pending') -> str:
    """Insert a task row and return its id."""
    from src.data.models import Task
    import uuid
    t = Task(
        id=str(uuid.uuid4()),
        title=title,
        status=status,
    )
    task_repo.create(t)
    return t.id


# ---------------------------------------------------------------------------
# QApplication fixture (needed for QObject / QTimer creation)
# ---------------------------------------------------------------------------

@pytest.fixture(scope='session')
def qapp():
    """Session-scoped QApplication for scheduler tests."""
    import sys
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


# ===========================================================================
# TestReminderRepository
# ===========================================================================

class TestReminderRepository:

    # ------------------------------------------------------------------
    # create / get_by_id
    # ------------------------------------------------------------------

    def test_create_assigns_id_if_empty(self, repo, task_repo):
        tid = _create_task(task_repo)
        r = _make_reminder(tid, _iso(-60))
        r.id = ''
        created = repo.create(r)
        assert created.id != ''

    def test_create_uses_provided_id(self, repo, task_repo):
        tid = _create_task(task_repo)
        r = _make_reminder(tid, _iso(-60))
        created = repo.create(r)
        assert created.id == r.id

    def test_get_by_id_returns_reminder(self, repo, task_repo):
        tid = _create_task(task_repo)
        r = _make_reminder(tid, _iso(-60))
        repo.create(r)
        fetched = repo.get_by_id(r.id)
        assert fetched is not None
        assert fetched.id == r.id
        assert fetched.task_id == tid

    def test_get_by_id_returns_none_if_missing(self, repo):
        assert repo.get_by_id('nonexistent-id') is None

    # ------------------------------------------------------------------
    # list_due — basic
    # ------------------------------------------------------------------

    def test_list_due_returns_overdue_reminder(self, repo, task_repo):
        tid = _create_task(task_repo)
        r = _make_reminder(tid, _iso(-120))    # 2 min ago
        repo.create(r)
        due = repo.list_due(_iso())
        assert any(d.reminder_id == r.id for d in due)

    def test_list_due_excludes_future_reminder(self, repo, task_repo):
        tid = _create_task(task_repo)
        r = _make_reminder(tid, _iso(+3600))   # 1 h from now
        repo.create(r)
        due = repo.list_due(_iso())
        assert all(d.reminder_id != r.id for d in due)

    def test_list_due_excludes_fired_reminder(self, repo, task_repo):
        tid = _create_task(task_repo)
        r = _make_reminder(tid, _iso(-60))
        repo.create(r)
        repo.mark_fired(r.id)
        due = repo.list_due(_iso())
        assert all(d.reminder_id != r.id for d in due)

    def test_list_due_excludes_deleted_task(self, repo, task_repo):
        tid = _create_task(task_repo, status='deleted')
        r = _make_reminder(tid, _iso(-60))
        repo.create(r)
        due = repo.list_due(_iso())
        assert all(d.reminder_id != r.id for d in due)

    def test_list_due_excludes_null_remind_at(self, repo, task_repo):
        tid = _create_task(task_repo)
        r = TaskReminder(
            id=str(uuid.uuid4()),
            task_id=tid,
            mode='before',
            minutes_before=5,
            remind_at=None,
            is_fired=False,
        )
        repo.create(r)
        due = repo.list_due(_iso())
        assert all(d.reminder_id != r.id for d in due)

    def test_list_due_sorted_oldest_first(self, repo, task_repo):
        tid = _create_task(task_repo)
        r1 = _make_reminder(tid, _iso(-120))   # older
        r2 = _make_reminder(tid, _iso(-60))    # newer
        repo.create(r1)
        repo.create(r2)
        due = repo.list_due(_iso())
        ids = [d.reminder_id for d in due]
        assert ids.index(r1.id) < ids.index(r2.id)

    def test_list_due_includes_task_title(self, repo, task_repo):
        tid = _create_task(task_repo, title='Buy groceries')
        r = _make_reminder(tid, _iso(-60))
        repo.create(r)
        due = repo.list_due(_iso())
        match = next(d for d in due if d.reminder_id == r.id)
        assert match.task_title == 'Buy groceries'

    # ------------------------------------------------------------------
    # mark_fired
    # ------------------------------------------------------------------

    def test_mark_fired_hides_from_list_due(self, repo, task_repo):
        tid = _create_task(task_repo)
        r = _make_reminder(tid, _iso(-60))
        repo.create(r)
        repo.mark_fired(r.id)
        due = repo.list_due(_iso())
        assert all(d.reminder_id != r.id for d in due)

    def test_mark_fired_sets_is_fired_flag(self, repo, task_repo):
        tid = _create_task(task_repo)
        r = _make_reminder(tid, _iso(-60))
        repo.create(r)
        repo.mark_fired(r.id)
        fetched = repo.get_by_id(r.id)
        assert fetched.is_fired is True

    # ------------------------------------------------------------------
    # delete
    # ------------------------------------------------------------------

    def test_delete_removes_reminder(self, repo, task_repo):
        tid = _create_task(task_repo)
        r = _make_reminder(tid, _iso(-60))
        repo.create(r)
        repo.delete(r.id)
        assert repo.get_by_id(r.id) is None


# ===========================================================================
# TestReminderScheduler
# ===========================================================================

class TestReminderScheduler:
    """Uses a mock ReminderRepository — no real DB or Qt timer needed."""

    def _make_due(self, title: str = 'Task A', remind_at: str = '2026-01-01T10:00:00') -> DueReminder:
        return DueReminder(
            reminder_id=str(uuid.uuid4()),
            task_id=str(uuid.uuid4()),
            task_title=title,
            remind_at=remind_at,
        )

    def test_scan_emits_notification_for_due_reminder(self, qapp):
        mock_repo = MagicMock(spec=ReminderRepository)
        due = self._make_due('Buy milk', '2026-01-01T09:00:00')
        mock_repo.list_due.return_value = [due]

        scheduler = ReminderScheduler(mock_repo)
        received = []
        scheduler.notification_requested.connect(
            lambda tid, title, msg: received.append((tid, title, msg))
        )

        scheduler.scan_now()

        assert len(received) == 1
        assert received[0][1] == 'Buy milk'  # title is 2nd arg now

    def test_scan_calls_mark_fired_before_emit(self, qapp):
        """mark_fired must be called before notification_requested is emitted."""
        mock_repo = MagicMock(spec=ReminderRepository)
        due = self._make_due()
        mock_repo.list_due.return_value = [due]

        call_order = []
        mock_repo.mark_fired.side_effect = lambda rid: call_order.append('mark_fired')

        scheduler = ReminderScheduler(mock_repo)
        scheduler.notification_requested.connect(
            lambda tid, title, msg: call_order.append('signal')
        )

        scheduler.scan_now()

        assert call_order == ['mark_fired', 'signal']

    def test_scan_no_due_reminders_emits_nothing(self, qapp):
        mock_repo = MagicMock(spec=ReminderRepository)
        mock_repo.list_due.return_value = []

        scheduler = ReminderScheduler(mock_repo)
        received = []
        scheduler.notification_requested.connect(
            lambda tid, title, msg: received.append((tid, title, msg))
        )

        scheduler.scan_now()

        assert received == []
        mock_repo.mark_fired.assert_not_called()

    def test_per_reminder_error_does_not_stop_loop(self, qapp):
        """If mark_fired raises for reminder 1, reminder 2 is still processed."""
        mock_repo = MagicMock(spec=ReminderRepository)
        r1 = self._make_due('Task 1')
        r2 = self._make_due('Task 2')
        mock_repo.list_due.return_value = [r1, r2]

        fired = []
        mock_repo.mark_fired.side_effect = [
            RuntimeError('DB error'),  # r1 fails
            None,                      # r2 succeeds
        ]

        received = []
        scheduler = ReminderScheduler(mock_repo)
        scheduler.notification_requested.connect(
            lambda tid, title, msg: received.append(title)
        )

        scheduler.scan_now()

        # r2 should still be processed
        assert 'Task 2' in received
        # r1 signal should NOT have been emitted (mark_fired raised before emit)
        assert 'Task 1' not in received

    def test_outer_exception_does_not_crash(self, qapp):
        """If list_due raises, scan_now must not propagate the exception."""
        mock_repo = MagicMock(spec=ReminderRepository)
        mock_repo.list_due.side_effect = RuntimeError('connection lost')

        scheduler = ReminderScheduler(mock_repo)
        # Must not raise
        scheduler.scan_now()

    def test_start_and_stop(self, qapp):
        """start() activates the timer; stop() deactivates it."""
        mock_repo = MagicMock(spec=ReminderRepository)
        mock_repo.list_due.return_value = []
        scheduler = ReminderScheduler(mock_repo)

        assert not scheduler._timer.isActive()
        scheduler.start()
        assert scheduler._timer.isActive()
        scheduler.stop()
        assert not scheduler._timer.isActive()

    def test_start_idempotent(self, qapp):
        """Calling start() twice does not create a second timer."""
        mock_repo = MagicMock(spec=ReminderRepository)
        mock_repo.list_due.return_value = []
        scheduler = ReminderScheduler(mock_repo)

        scheduler.start()
        scheduler.start()   # second call — should be a no-op
        assert scheduler._timer.isActive()
        scheduler.stop()


# ===========================================================================
# TestFmtRemindAt (helper)
# ===========================================================================

class TestFmtRemindAt:
    def test_t_separator(self):
        assert _fmt_remind_at('2026-03-29T14:30:00') == '2026-03-29 14:30'

    def test_space_separator(self):
        assert _fmt_remind_at('2026-03-29 14:30:00') == '2026-03-29 14:30'

    def test_empty_string(self):
        assert _fmt_remind_at('') == ''

    def test_short_string_no_crash(self):
        # Strings shorter than 16 chars should not crash; raw value returned or truncated
        result = _fmt_remind_at('2026')
        assert isinstance(result, str)
