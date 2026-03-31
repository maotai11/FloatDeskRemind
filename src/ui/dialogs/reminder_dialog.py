"""
Reminder dialog shown when a task's due time arrives.

Presents the task title/time and offers:
  - 確認關閉  — dismisses the reminder for this session
  - Snooze    — re-notifies after N minutes (5 / 15 / 30)

Non-modal: multiple reminders may be open simultaneously.
"""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog, QLabel, QHBoxLayout, QPushButton, QVBoxLayout, QWidget,
)

from src.data.models import Task

_SNOOZE_OPTIONS: list[tuple[str, int]] = [
    ('5 分鐘', 5),
    ('15 分鐘', 15),
    ('30 分鐘', 30),
]


class ReminderDialog(QDialog):
    """Emits confirmed(task_id) or snoozed(task_id, minutes) then closes."""

    confirmed = Signal(str)       # task_id
    snoozed = Signal(str, int)    # task_id, minutes

    def __init__(self, task: Task, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._task_id = task.id

        self.setWindowTitle('任務提醒')
        self.setWindowFlags(
            Qt.WindowType.Dialog
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.WindowCloseButtonHint
        )
        self.setModal(False)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)

        self._build_ui(task)
        self.adjustSize()

    # ------------------------------------------------------------------
    def _build_ui(self, task: Task) -> None:
        root = QVBoxLayout(self)
        root.setSpacing(12)
        root.setContentsMargins(20, 16, 20, 16)

        # Header icon + title
        title_lbl = QLabel(f'⏰  {task.title}')
        title_lbl.setWordWrap(True)
        title_lbl.setStyleSheet('font-size: 15px; font-weight: bold;')
        root.addWidget(title_lbl)

        # Due date + time
        time_str = task.due_time[:5] if task.due_time else ''
        due_lbl = QLabel(f'到期：{task.due_date or ""}  {time_str}')
        due_lbl.setStyleSheet('color: #888; font-size: 12px;')
        root.addWidget(due_lbl)

        root.addSpacing(4)

        # Snooze row
        snooze_row = QWidget()
        snooze_layout = QHBoxLayout(snooze_row)
        snooze_layout.setContentsMargins(0, 0, 0, 0)
        snooze_layout.setSpacing(6)

        snooze_label = QLabel('延時：')
        snooze_layout.addWidget(snooze_label)

        for label, minutes in _SNOOZE_OPTIONS:
            btn = QPushButton(label)
            btn.setFixedWidth(70)
            btn.clicked.connect(lambda checked=False, m=minutes: self._on_snooze(m))
            snooze_layout.addWidget(btn)

        snooze_layout.addStretch()
        root.addWidget(snooze_row)

        # Confirm button
        confirm_btn = QPushButton('確認關閉')
        confirm_btn.setDefault(True)
        confirm_btn.clicked.connect(self._on_confirm)
        root.addWidget(confirm_btn)

    # ------------------------------------------------------------------
    def _on_confirm(self) -> None:
        self.confirmed.emit(self._task_id)
        self.close()

    def _on_snooze(self, minutes: int) -> None:
        self.snoozed.emit(self._task_id, minutes)
        self.close()
