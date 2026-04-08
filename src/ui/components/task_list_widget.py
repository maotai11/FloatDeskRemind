"""
TaskListWidget: float window N-day task list with date section headers.
"""
from __future__ import annotations
from datetime import date
from typing import List, Dict

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QScrollArea, QFrame
)
from PySide6.QtCore import Signal, Qt

from src.data.models import Task
from src.services.sort_service import sort_tasks
from src.ui.components.task_item_widget import TaskItemWidget


def _date_delta(d_str: str, today: date) -> int:
    """Return (date - today).days; returns 999 on parse error."""
    try:
        return (date.fromisoformat(d_str) - today).days
    except ValueError:
        return 999


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
        scroll.setStyleSheet('background: transparent;')

        self._content = QWidget()
        self._content.setStyleSheet('background: transparent;')
        self._content_layout = QVBoxLayout(self._content)
        self._content_layout.setContentsMargins(8, 8, 8, 8)
        self._content_layout.setSpacing(0)
        self._content_layout.addStretch()

        scroll.setWidget(self._content)
        layout.addWidget(scroll)

    def refresh(self, tasks_by_date: Dict[str, List[Task]]) -> None:
        while self._content_layout.count() > 0:
            item = self._content_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._items.clear()

        today = date.today()
        today_str = today.isoformat()

        # --- 逾期區塊（優先顯示）---
        overdue = tasks_by_date.get('__overdue__', [])
        if overdue:
            header = QLabel('逾期')
            header.setStyleSheet(
                'color: #EF4444; font-weight: 700;'
                'font-size: 11px; padding: 10px 4px 4px 4px; background: transparent;'
            )
            self._content_layout.addWidget(header)
            for task in sort_tasks(overdue):
                item = TaskItemWidget(task, reference_date_str=today_str)
                item.completed.connect(self.task_completed)
                item.edit_requested.connect(self.task_edit_requested)
                item.delete_requested.connect(self.task_delete_requested)
                self._content_layout.addWidget(item)
                self._items[task.id] = item

        # --- 今天 / 明天 / 未來 ---
        dates = sorted(k for k in tasks_by_date if k != '__overdue__')

        # Separate dates: today (0), tomorrow (1), future (>1)
        today_dates    = [d for d in dates if _date_delta(d, today) == 0]
        tomorrow_dates = [d for d in dates if _date_delta(d, today) == 1]
        future_dates   = [d for d in dates if _date_delta(d, today) > 1]

        _WEEKDAYS = ('一', '二', '三', '四', '五', '六', '日')

        def _add_section(label_text: str, date_keys: list, is_today: bool = False,
                         show_date_headers: bool = False) -> None:
            header = QLabel(label_text)
            header.setStyleSheet(
                f'color: {"#4F46E5" if is_today else "#64748B"};'
                f'font-weight: {"700" if is_today else "500"};'
                'font-size: 11px; padding: 10px 4px 4px 4px; background: transparent;'
            )
            self._content_layout.addWidget(header)

            if show_date_headers:
                # Future section: show a date header per day, sorted chronologically
                for d in sorted(date_keys):
                    tasks_for_day = tasks_by_date.get(d, [])
                    if not tasks_for_day:
                        continue
                    try:
                        dt = date.fromisoformat(d)
                        day_label = f'{dt.month}/{dt.day}（{_WEEKDAYS[dt.weekday()]}）'
                    except ValueError:
                        day_label = d

                    day_hdr = QLabel(f'  {day_label}')
                    day_hdr.setStyleSheet(
                        'color: #94A3B8; font-weight: 500; font-size: 10px; '
                        'padding: 6px 4px 2px 4px; background: transparent;'
                    )
                    self._content_layout.addWidget(day_hdr)

                    for task in sort_tasks(tasks_for_day):
                        item = TaskItemWidget(task, reference_date_str=today_str)
                        item.completed.connect(self.task_completed)
                        item.edit_requested.connect(self.task_edit_requested)
                        item.delete_requested.connect(self.task_delete_requested)
                        self._content_layout.addWidget(item)
                        self._items[task.id] = item
            else:
                combined = []
                for d in date_keys:
                    combined.extend(tasks_by_date.get(d, []))
                for task in sort_tasks(combined):
                    item = TaskItemWidget(task, reference_date_str=today_str)
                    item.completed.connect(self.task_completed)
                    item.edit_requested.connect(self.task_edit_requested)
                    item.delete_requested.connect(self.task_delete_requested)
                    self._content_layout.addWidget(item)
                    self._items[task.id] = item

        if today_dates:
            _add_section('今天', today_dates, is_today=True)
        if tomorrow_dates:
            _add_section('明天', tomorrow_dates)
        if future_dates:
            _add_section('未來', future_dates, show_date_headers=True)

        self._content_layout.addStretch()

