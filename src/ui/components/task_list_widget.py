"""
TaskListWidget: float window 3-day task list with date section headers.
"""
from __future__ import annotations
from datetime import date
from typing import List, Dict

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QScrollArea, QFrame, QSizePolicy
)
from PySide6.QtCore import Signal, Qt

from src.data.models import Task
from src.services.sort_service import sort_tasks
from src.core.utils import next_n_days
from src.ui.components.task_item_widget import TaskItemWidget


DAY_LABELS = ['今日', '明日', '後日']


class TaskListWidget(QWidget):
    task_completed = Signal(str)
    task_edit_requested = Signal(str)
    task_delete_requested = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._items: Dict[str, TaskItemWidget] = {}
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self._content = QWidget()
        self._content_layout = QVBoxLayout(self._content)
        self._content_layout.setContentsMargins(4, 4, 4, 4)
        self._content_layout.setSpacing(0)
        self._content_layout.addStretch()

        scroll.setWidget(self._content)
        layout.addWidget(scroll)

    def refresh(self, tasks_by_date: Dict[str, List[Task]]) -> None:
        """Rebuild the list from a dict of {date_str: [tasks]}."""
        # Clear existing
        while self._content_layout.count() > 0:
            item = self._content_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._items.clear()

        dates = next_n_days(3)

        for i, d in enumerate(dates):
            tasks = tasks_by_date.get(d, [])
            sorted_tasks = sort_tasks(tasks)

            header = QLabel(f'  {DAY_LABELS[i]}  {d}')
            header.setProperty('class', 'section-header')
            header.setStyleSheet(
                'background-color: #E3F2FD; color: #1976D2; '
                'font-weight: bold; font-size: 12px; '
                'padding: 4px 8px; border-radius: 3px; margin: 2px 0;'
            )
            self._content_layout.addWidget(header)

            if not sorted_tasks:
                empty = QLabel('  無任務')
                empty.setStyleSheet('color: #AAAAAA; font-size: 12px; padding: 4px 12px;')
                self._content_layout.addWidget(empty)
            else:
                for task in sorted_tasks:
                    item = TaskItemWidget(task, reference_date_str=today.isoformat())
                    item.completed.connect(self.task_completed)
                    item.edit_requested.connect(self.task_edit_requested)
                    item.delete_requested.connect(self.task_delete_requested)
                    self._content_layout.addWidget(item)
                    self._items[task.id] = item

        self._content_layout.addStretch()
