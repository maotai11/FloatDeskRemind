"""
TaskItemWidget: card-style task row for the float window.
Left-side priority color bar + checkbox + title + time badge.
Right-click context menu for edit/delete.
"""
from __future__ import annotations

from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QCheckBox, QLabel, QSizePolicy, QMenu
)
from PySide6.QtCore import Signal, Qt
from PySide6.QtGui import QAction

from src.data.models import Task
from src.ui.styles.theme import (
    PRIORITY_HIGH, PRIORITY_MEDIUM, PRIORITY_LOW, PRIORITY_NONE,
    TEXT_OVERDUE, TEXT_SECONDARY
)

_PRIORITY_COLOR = {
    'high':   PRIORITY_HIGH,
    'medium': PRIORITY_MEDIUM,
    'low':    PRIORITY_LOW,
    'none':   'transparent',
}


class TaskItemWidget(QWidget):
    completed      = Signal(str)  # task_id
    edit_requested = Signal(str)
    delete_requested = Signal(str)

    def __init__(self, task: Task, reference_date_str: str = '', parent=None):
        super().__init__(parent)
        self._task = task
        self._ref_date = reference_date_str
        self._build_ui()
        self.setFixedHeight(40)

    def _build_ui(self) -> None:
        self.setStyleSheet(
            'TaskItemWidget {'
            '  background: white;'
            '  border-radius: 6px;'
            '  margin: 2px 0;'
            '}'
            'TaskItemWidget:hover { background: #F8FAFC; }'
        )

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 8, 0)
        layout.setSpacing(0)

        # Priority color bar (3px left stripe)
        bar = QWidget()
        bar.setFixedWidth(4)
        bar.setFixedHeight(28)
        color = _PRIORITY_COLOR.get(self._task.priority, 'transparent')
        bar.setStyleSheet(
            f'background-color: {color}; border-radius: 2px; margin: 2px 6px 2px 4px;'
        )
        layout.addWidget(bar)

        # Checkbox
        self._check = QCheckBox()
        self._check.setChecked(self._task.status == 'done')
        self._check.setFixedSize(20, 20)
        self._check.toggled.connect(self._on_check)
        layout.addWidget(self._check)
        layout.addSpacing(6)

        # Title
        is_overdue = (
            self._task.due_date and self._ref_date
            and self._task.due_date < self._ref_date
            and self._task.status != 'done'
        )
        is_done = self._task.status == 'done'

        self._label = QLabel(self._task.title)
        self._label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self._label.setWordWrap(False)

        if is_done:
            self._label.setStyleSheet('color: #CBD5E1; text-decoration: line-through; font-size: 13px;')
        elif is_overdue:
            self._label.setStyleSheet(f'color: {TEXT_OVERDUE}; font-weight: 600; font-size: 13px;')
        else:
            self._label.setStyleSheet('color: #1E293B; font-size: 13px;')

        layout.addWidget(self._label)

        # Time badge
        if self._task.due_time:
            time_badge = QLabel(self._task.due_time[:5])
            time_badge.setStyleSheet(
                'color: #64748B; font-size: 11px; '
                'background: #F1F5F9; border-radius: 4px; '
                'padding: 1px 5px; margin-left: 4px;'
            )
            layout.addWidget(time_badge)

        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)

    def _on_check(self, checked: bool) -> None:
        if checked and self._task.status != 'done':
            self.completed.emit(self._task.id)

    def _show_context_menu(self, pos) -> None:
        menu = QMenu(self)
        edit_a = QAction('編輯', self)
        edit_a.triggered.connect(lambda: self.edit_requested.emit(self._task.id))
        menu.addAction(edit_a)

        del_a = QAction('刪除', self)
        del_a.triggered.connect(lambda: self.delete_requested.emit(self._task.id))
        menu.addAction(del_a)

        menu.exec(self.mapToGlobal(pos))

    def update_task(self, task: Task) -> None:
        self._task = task
        self._check.setChecked(task.status == 'done')
        self._label.setText(task.title)
