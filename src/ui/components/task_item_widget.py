"""
TaskItemWidget: a single task row in the float window.
Shows checkbox, title, right-click context menu.
"""
from __future__ import annotations
from typing import TYPE_CHECKING, Callable

from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QCheckBox, QLabel, QSizePolicy, QMenu
)
from PySide6.QtCore import Signal, Qt
from PySide6.QtGui import QAction

from src.data.models import Task
from src.ui.styles.theme import TEXT_OVERDUE, TEXT_SECONDARY

if TYPE_CHECKING:
    pass


class TaskItemWidget(QWidget):
    completed = Signal(str)       # task_id
    edit_requested = Signal(str)  # task_id
    delete_requested = Signal(str)

    def __init__(self, task: Task, reference_date_str: str = '', parent=None):
        super().__init__(parent)
        self._task = task
        self._ref_date = reference_date_str
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 2, 4, 2)
        layout.setSpacing(6)

        self._check = QCheckBox()
        self._check.setChecked(self._task.status == 'done')
        self._check.toggled.connect(self._on_check)
        layout.addWidget(self._check)

        self._label = QLabel(self._task.title)
        self._label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self._label.setWordWrap(False)

        # Overdue styling
        if self._task.due_date and self._ref_date and self._task.due_date < self._ref_date:
            self._label.setStyleSheet(f'color: {TEXT_OVERDUE}; font-weight: bold;')

        if self._task.status == 'done':
            self._label.setStyleSheet('color: #AAAAAA; text-decoration: line-through;')

        layout.addWidget(self._label)

        if self._task.due_time:
            time_lbl = QLabel(self._task.due_time[:5])
            time_lbl.setStyleSheet(f'color: {TEXT_SECONDARY}; font-size: 11px;')
            layout.addWidget(time_lbl)

        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)

    def _on_check(self, checked: bool) -> None:
        if checked and self._task.status != 'done':
            self.completed.emit(self._task.id)

    def _show_context_menu(self, pos) -> None:
        menu = QMenu(self)
        edit_action = QAction('編輯', self)
        edit_action.triggered.connect(lambda: self.edit_requested.emit(self._task.id))
        menu.addAction(edit_action)

        delete_action = QAction('刪除', self)
        delete_action.triggered.connect(lambda: self.delete_requested.emit(self._task.id))
        menu.addAction(delete_action)

        menu.exec(self.mapToGlobal(pos))

    def update_task(self, task: Task) -> None:
        self._task = task
        self._check.setChecked(task.status == 'done')
        self._label.setText(task.title)
