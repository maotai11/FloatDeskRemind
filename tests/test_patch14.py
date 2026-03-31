"""
Patch 14 — Quick Add / Inbox Capture tests.

Tests are split into two classes:

  TestQuickAddDialogLogic  — unit tests that exercise the internal accept/
                             validate logic without running an event loop.
                             We call _on_accept() directly after setting up
                             widget state, then inspect _result_task and
                             _remind_at.

  TestQuickAddServiceIntegration — verify that a task produced by the dialog
                                   can be persisted via TaskService with the
                                   expected defaults (priority=none, no due
                                   date = inbox-style).
"""
from __future__ import annotations

import uuid
from typing import Optional

import pytest

# PySide6 QApplication must be created before any QWidget.
# pytest-qt provides `qtbot` which handles this; we also check conftest
# doesn't already create one.  If no qtbot fixture is needed we fall back
# to a module-level QApplication.

try:
    from PySide6.QtWidgets import QApplication
    import sys
    _app = QApplication.instance() or QApplication(sys.argv)
except Exception:
    _app = None


from src.ui.dialogs.quick_add_dialog import QuickAddDialog
from src.data.models import Task
from src.ui.utils import NO_DATE

from PySide6.QtCore import QDate, QDateTime, QTime


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_dialog() -> QuickAddDialog:
    """Return a fresh QuickAddDialog without showing it."""
    dlg = QuickAddDialog()
    return dlg


def _set_title(dlg: QuickAddDialog, text: str) -> None:
    dlg._title.setText(text)


def _set_due_date(dlg: QuickAddDialog, date_str: str) -> None:
    """Set a valid due date (YYYY-MM-DD)."""
    dlg._due_date.setDate(QDate.fromString(date_str, 'yyyy-MM-dd'))


def _enable_recurring(dlg: QuickAddDialog, rule: str) -> None:
    dlg._is_recurring.setChecked(True)
    for i in range(dlg._recurrence_rule.count()):
        if dlg._recurrence_rule.itemData(i) == rule:
            dlg._recurrence_rule.setCurrentIndex(i)
            break


def _enable_reminder(dlg: QuickAddDialog, dt_str: str = '2026-05-01T09:00:00') -> None:
    dlg._remind_enabled.setChecked(True)
    dt = QDateTime.fromString(dt_str, 'yyyy-MM-ddTHH:mm:ss')
    dlg._remind_dt.setDateTime(dt)


# ---------------------------------------------------------------------------
# TestQuickAddDialogLogic
# ---------------------------------------------------------------------------

class TestQuickAddDialogLogic:

    # ── Title validation ───────────────────────────────────────────────────

    def test_empty_title_blocks_save(self):
        dlg = _make_dialog()
        _set_title(dlg, '')
        dlg._on_accept()
        assert dlg._result_task is None
        assert not dlg._msg.isHidden()   # show() was called; isVisible() is False while dialog is not on screen
        assert '任務名稱' in dlg._msg.text()

    def test_whitespace_only_title_blocks_save(self):
        dlg = _make_dialog()
        _set_title(dlg, '   ')
        dlg._on_accept()
        assert dlg._result_task is None

    def test_valid_title_saves(self):
        dlg = _make_dialog()
        _set_title(dlg, '買牛奶')
        dlg._on_accept()
        assert dlg._result_task is not None
        assert dlg._result_task.title == '買牛奶'

    # ── Default values ─────────────────────────────────────────────────────

    def test_default_no_due_date(self):
        dlg = _make_dialog()
        _set_title(dlg, '任務')
        dlg._on_accept()
        assert dlg._result_task.due_date is None

    def test_default_priority_none(self):
        dlg = _make_dialog()
        _set_title(dlg, '任務')
        dlg._on_accept()
        assert dlg._result_task.priority == 'none'

    def test_default_status_pending(self):
        dlg = _make_dialog()
        _set_title(dlg, '任務')
        dlg._on_accept()
        assert dlg._result_task.status == 'pending'

    def test_default_no_remind_at(self):
        dlg = _make_dialog()
        _set_title(dlg, '任務')
        dlg._on_accept()
        assert dlg.get_remind_at() is None

    def test_default_not_recurring(self):
        dlg = _make_dialog()
        _set_title(dlg, '任務')
        dlg._on_accept()
        assert dlg._result_task.is_recurring is False
        assert dlg._result_task.recurrence_rule is None

    # ── With due date ──────────────────────────────────────────────────────

    def test_with_due_date(self):
        dlg = _make_dialog()
        _set_title(dlg, '任務')
        _set_due_date(dlg, '2026-05-15')
        dlg._on_accept()
        assert dlg._result_task.due_date == '2026-05-15'

    # ── Recurrence ────────────────────────────────────────────────────────

    def test_recurring_without_due_date_blocked(self):
        dlg = _make_dialog()
        _set_title(dlg, '每天站會')
        _enable_recurring(dlg, 'daily')
        # due_date stays at NO_DATE (= "無期限")
        dlg._on_accept()
        assert dlg._result_task is None
        assert '循環任務' in dlg._msg.text()

    def test_recurring_with_due_date_saves(self):
        dlg = _make_dialog()
        _set_title(dlg, '每天站會')
        _set_due_date(dlg, '2026-05-10')
        _enable_recurring(dlg, 'daily')
        dlg._on_accept()
        assert dlg._result_task is not None
        assert dlg._result_task.is_recurring is True
        assert dlg._result_task.recurrence_rule == 'daily'
        assert dlg._result_task.due_date == '2026-05-10'

    def test_recurring_weekly_rule(self):
        dlg = _make_dialog()
        _set_title(dlg, '週會')
        _set_due_date(dlg, '2026-05-12')
        _enable_recurring(dlg, 'weekly')
        dlg._on_accept()
        assert dlg._result_task.recurrence_rule == 'weekly'

    def test_recurring_monthly_rule(self):
        dlg = _make_dialog()
        _set_title(dlg, '月報')
        _set_due_date(dlg, '2026-05-31')
        _enable_recurring(dlg, 'monthly')
        dlg._on_accept()
        assert dlg._result_task.recurrence_rule == 'monthly'

    def test_not_recurring_rule_is_none(self):
        """When is_recurring=False the recurrence_rule must be None even if combobox has value."""
        dlg = _make_dialog()
        _set_title(dlg, '任務')
        # Do NOT check is_recurring
        dlg._on_accept()
        assert dlg._result_task.recurrence_rule is None

    # ── Reminder ──────────────────────────────────────────────────────────

    def test_reminder_disabled_by_default(self):
        dlg = _make_dialog()
        _set_title(dlg, '任務')
        dlg._on_accept()
        assert dlg.get_remind_at() is None

    def test_reminder_enabled_returns_iso_string(self):
        dlg = _make_dialog()
        _set_title(dlg, '任務')
        _enable_reminder(dlg, '2026-05-01T09:00:00')
        dlg._on_accept()
        remind_at = dlg.get_remind_at()
        assert remind_at is not None
        assert remind_at.startswith('2026-05-01T09:00')

    def test_reminder_does_not_require_due_date(self):
        """Reminder can be set even if there is no due_date."""
        dlg = _make_dialog()
        _set_title(dlg, '任務')
        _enable_reminder(dlg)
        dlg._on_accept()
        assert dlg._result_task is not None
        assert dlg.get_remind_at() is not None

    # ── get_task / get_remind_at before accept ────────────────────────────

    def test_get_task_returns_none_before_accept(self):
        dlg = _make_dialog()
        assert dlg.get_task() is None

    def test_get_remind_at_returns_none_before_accept(self):
        dlg = _make_dialog()
        assert dlg.get_remind_at() is None

    # ── Validation message hidden after fix ───────────────────────────────

    def test_error_message_hidden_after_valid_save(self):
        dlg = _make_dialog()
        # First trigger an error
        _set_title(dlg, '')
        dlg._on_accept()
        assert not dlg._msg.isHidden()   # error shown
        # Now fix the title and save again
        _set_title(dlg, '已修正')
        dlg._on_accept()
        assert dlg._msg.isHidden()       # error hidden after valid save

    # ── Task id is always a new UUID ──────────────────────────────────────

    def test_task_has_unique_id(self):
        dlg1 = _make_dialog()
        _set_title(dlg1, '任務 A')
        dlg1._on_accept()

        dlg2 = _make_dialog()
        _set_title(dlg2, '任務 B')
        dlg2._on_accept()

        assert dlg1._result_task.id != dlg2._result_task.id


# ---------------------------------------------------------------------------
# TestQuickAddServiceIntegration
# ---------------------------------------------------------------------------

class TestQuickAddServiceIntegration:
    """Simulate what ConsoleWindow does after dialog.exec() returns Accepted."""

    def _simulate_quick_add(
        self,
        task_service,
        title: str,
        due_date: Optional[str] = None,
        is_recurring: bool = False,
        recurrence_rule: Optional[str] = None,
        remind_at: Optional[str] = None,
    ) -> Task:
        """Build a Task as QuickAddDialog would and persist via TaskService."""
        task = Task(
            id=str(uuid.uuid4()),
            title=title,
            status='pending',
            priority='none',
            due_date=due_date,
            is_recurring=is_recurring,
            recurrence_rule=recurrence_rule,
        )
        task_service.create_task(task)
        return task

    # ── Title-only = inbox ─────────────────────────────────────────────────

    def test_title_only_creates_task(self, task_service, task_repo):
        task = self._simulate_quick_add(task_service, '買牛奶')
        saved = task_repo.get_by_id(task.id)
        assert saved is not None
        assert saved.title == '買牛奶'
        assert saved.status == 'pending'

    def test_title_only_has_no_due_date(self, task_service, task_repo):
        task = self._simulate_quick_add(task_service, '收信')
        saved = task_repo.get_by_id(task.id)
        assert saved.due_date is None

    def test_title_only_priority_none(self, task_service, task_repo):
        task = self._simulate_quick_add(task_service, '記事')
        saved = task_repo.get_by_id(task.id)
        assert saved.priority == 'none'

    def test_title_only_appears_in_no_date_view(self, task_service, task_repo):
        from src.core.view_filter import filter_tasks, VIEW_NO_DATE
        task = self._simulate_quick_add(task_service, '無期限任務')
        all_tasks = task_repo.get_all_non_deleted()
        visible = filter_tasks(all_tasks, VIEW_NO_DATE)
        ids = {t.id for t in visible}
        assert task.id in ids

    # ── With due date ──────────────────────────────────────────────────────

    def test_with_due_date_appears_in_today_view(self, task_service, task_repo):
        from datetime import date
        from src.core.view_filter import filter_tasks, VIEW_TODAY
        today_str = date.today().isoformat()
        task = self._simulate_quick_add(task_service, '今日任務', due_date=today_str)
        all_tasks = task_repo.get_all_non_deleted()
        visible = filter_tasks(all_tasks, VIEW_TODAY)
        assert task.id in {t.id for t in visible}

    # ── Recurrence ────────────────────────────────────────────────────────

    def test_recurring_task_persisted(self, task_service, task_repo):
        task = self._simulate_quick_add(
            task_service, '站會',
            due_date='2026-05-10',
            is_recurring=True,
            recurrence_rule='daily',
        )
        saved = task_repo.get_by_id(task.id)
        assert saved.is_recurring is True
        assert saved.recurrence_rule == 'daily'

    def test_recurring_task_completes_and_spawns(self, task_service, task_repo):
        task = self._simulate_quick_add(
            task_service, '每日報告',
            due_date='2026-05-10',
            is_recurring=True,
            recurrence_rule='daily',
        )
        task_service.complete_task_manual(task.id)
        all_tasks = task_repo.get_all_non_deleted()
        spawned = [t for t in all_tasks if t.title == '每日報告' and t.status == 'pending']
        assert len(spawned) == 1
        assert spawned[0].due_date == '2026-05-11'

    # ── Multiple quick-adds don't interfere ───────────────────────────────

    def test_multiple_quick_adds_independent(self, task_service, task_repo):
        t1 = self._simulate_quick_add(task_service, '任務一')
        t2 = self._simulate_quick_add(task_service, '任務二')
        t3 = self._simulate_quick_add(task_service, '任務三')

        all_tasks = task_repo.get_all_non_deleted()
        ids = {t.id for t in all_tasks}
        assert {t1.id, t2.id, t3.id}.issubset(ids)
