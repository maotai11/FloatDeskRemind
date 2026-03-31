"""
QuickAddDialog — lightweight task capture dialog (Patch 14).

Fields: title (required), due_date (optional), recurrence (optional), reminder (optional).
No description editor, no priority, no due_time, no auto_complete.

API is intentionally identical to TaskEditDialog's subset so existing
ConsoleWindow → AppController wiring (task_add_requested signal) works unchanged.

Keyboard:
    Enter   — submit (when title is non-empty and form is valid)
    Esc     — cancel

Focus:
    Title field receives focus automatically on open.

Validation:
    - Title must be non-empty.
    - Recurring task requires due_date.
"""
from __future__ import annotations

import uuid
from typing import Optional

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLineEdit, QDateEdit, QDateTimeEdit,
    QPushButton, QLabel, QCheckBox, QComboBox, QFrame,
)
from PySide6.QtCore import Qt, QDate, QDateTime, QTime

from src.data.models import Task
from src.ui.utils import NO_DATE


class QuickAddDialog(QDialog):
    """Minimal task capture dialog — title + optional date/recurrence/reminder."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle('快速新增任務')
        self.setModal(True)
        self.setMinimumWidth(380)
        self._result_task: Optional[Task] = None
        self._remind_at: Optional[str] = None
        self._build_ui()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(14)

        # Header
        header = QLabel('快速新增任務')
        header.setStyleSheet(
            'font-size: 16px; font-weight: 700; color: #1E293B; margin-bottom: 2px;'
        )
        layout.addWidget(header)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        form.setSpacing(10)
        form.setContentsMargins(0, 0, 0, 0)

        # ── Title (required) ──────────────────────────────────────────
        self._title = QLineEdit()
        self._title.setPlaceholderText('任務名稱（必填）')
        form.addRow('名稱 *', self._title)

        # ── Due date (optional) ───────────────────────────────────────
        self._due_date = QDateEdit()
        self._due_date.setCalendarPopup(True)
        self._due_date.setDisplayFormat('yyyy-MM-dd')
        self._due_date.setSpecialValueText('無期限')
        self._due_date.setMinimumDate(NO_DATE)
        self._due_date.setDate(NO_DATE)          # default = no date (shows "無期限")
        form.addRow('期限日', self._due_date)

        # ── Separator ─────────────────────────────────────────────────
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet('color: #E2E8F0; margin: 2px 0;')
        form.addRow(sep)

        # ── Recurrence ────────────────────────────────────────────────
        recur_row_w = QFrame()
        rr = QHBoxLayout(recur_row_w)
        rr.setContentsMargins(0, 0, 0, 0)
        rr.setSpacing(10)

        self._is_recurring = QCheckBox('循環任務')
        rr.addWidget(self._is_recurring)

        self._recurrence_rule = QComboBox()
        for val, lbl in (('daily', '每天'), ('weekly', '每週'), ('monthly', '每月')):
            self._recurrence_rule.addItem(lbl, val)
        self._recurrence_rule.setEnabled(False)
        rr.addWidget(self._recurrence_rule)
        rr.addStretch()

        self._is_recurring.toggled.connect(self._recurrence_rule.setEnabled)
        form.addRow('循環', recur_row_w)

        # ── Reminder ──────────────────────────────────────────────────
        remind_row_w = QFrame()
        rmr = QHBoxLayout(remind_row_w)
        rmr.setContentsMargins(0, 0, 0, 0)
        rmr.setSpacing(10)

        self._remind_enabled = QCheckBox('啟用提醒')
        rmr.addWidget(self._remind_enabled)

        self._remind_dt = QDateTimeEdit()
        self._remind_dt.setDisplayFormat('yyyy-MM-dd HH:mm')
        self._remind_dt.setCalendarPopup(True)
        self._remind_dt.setDateTime(
            QDateTime(QDate.currentDate().addDays(1), QTime(9, 0))
        )
        self._remind_dt.setEnabled(False)
        rmr.addWidget(self._remind_dt)

        self._remind_enabled.toggled.connect(self._remind_dt.setEnabled)
        form.addRow('到期提醒', remind_row_w)

        layout.addLayout(form)

        # ── Validation message ────────────────────────────────────────
        self._msg = QLabel('')
        self._msg.setStyleSheet('color: #EF4444; font-size: 12px;')
        self._msg.hide()
        layout.addWidget(self._msg)

        # ── Buttons ───────────────────────────────────────────────────
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        btn_row.addStretch()

        cancel_btn = QPushButton('取消')
        cancel_btn.setFixedHeight(34)
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)

        self._save_btn = QPushButton('新增')
        self._save_btn.setFixedHeight(34)
        self._save_btn.setDefault(True)      # Enter triggers this button
        self._save_btn.setStyleSheet(
            'QPushButton {'
            '  background-color: #4F46E5; color: #FFFFFF;'
            '  border: none; border-radius: 6px;'
            '  padding: 0 20px; font-weight: 700;'
            '}'
            'QPushButton:hover { background-color: #3730A3; }'
            'QPushButton:pressed { background-color: #312E81; }'
        )
        self._save_btn.clicked.connect(self._on_accept)
        btn_row.addWidget(self._save_btn)

        layout.addLayout(btn_row)

    # ------------------------------------------------------------------
    # Validation + accept
    # ------------------------------------------------------------------

    def _on_accept(self) -> None:
        title = self._title.text().strip()
        if not title:
            self._msg.setText('請輸入任務名稱')
            self._msg.show()
            self._title.setFocus()
            return

        # Recurring task must have a due_date
        if self._is_recurring.isChecked():
            d = self._due_date.date()
            has_due = d.isValid() and d.year() > NO_DATE.year()
            if not has_due:
                self._msg.setText('循環任務需要設定期限日')
                self._msg.show()
                self._due_date.setFocus()
                return

        self._msg.hide()

        task = Task(id=str(uuid.uuid4()), title='', created_at='', updated_at='')
        task.title = title
        task.priority = 'none'
        task.status = 'pending'

        d = self._due_date.date()
        task.due_date = (
            d.toString('yyyy-MM-dd')
            if d.isValid() and d.year() > NO_DATE.year()
            else None
        )

        task.is_recurring = self._is_recurring.isChecked()
        task.recurrence_rule = (
            self._recurrence_rule.currentData() if task.is_recurring else None
        )

        if self._remind_enabled.isChecked():
            self._remind_at = self._remind_dt.dateTime().toString('yyyy-MM-ddTHH:mm:ss')
        else:
            self._remind_at = None

        self._result_task = task
        self.accept()

    # ------------------------------------------------------------------
    # Public API (same interface as TaskEditDialog)
    # ------------------------------------------------------------------

    def get_task(self) -> Optional[Task]:
        """Return the constructed Task, or None if dialog was cancelled."""
        return self._result_task

    def get_remind_at(self) -> Optional[str]:
        """Return remind_at ISO string if reminder is enabled, else None.

        Only valid after exec() returns Accepted.
        Caller (ConsoleWindow → AppController) creates the TaskReminder row
        after the task itself is committed to DB.
        """
        return self._remind_at

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def showEvent(self, event) -> None:  # type: ignore[override]
        super().showEvent(event)
        self._title.setFocus()
