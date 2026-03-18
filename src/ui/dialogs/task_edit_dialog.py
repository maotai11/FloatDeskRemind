"""
Quick add/edit task dialog.
"""
from __future__ import annotations
import uuid
from typing import Optional
from datetime import date

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLineEdit, QTextEdit, QComboBox, QDateEdit, QTimeEdit,
    QPushButton, QLabel, QCheckBox, QDialogButtonBox
)
from PySide6.QtCore import Qt, QDate, QTime

from src.data.models import Task


class TaskEditDialog(QDialog):
    def __init__(
        self,
        task: Optional[Task] = None,
        parent_id: Optional[str] = None,
        parent=None
    ):
        super().__init__(parent)
        self._task = task
        self._parent_id = parent_id
        self._result_task: Optional[Task] = None

        self.setWindowTitle('新增任務' if task is None else '編輯任務')
        self.setModal(True)
        self.setMinimumWidth(400)
        self._build_ui()
        if task:
            self._load_task(task)

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        form.setSpacing(8)

        self._title = QLineEdit()
        self._title.setPlaceholderText('任務名稱（必填）')
        form.addRow('名稱 *', self._title)

        self._desc = QTextEdit()
        self._desc.setPlaceholderText('描述（可選）')
        self._desc.setFixedHeight(70)
        form.addRow('描述', self._desc)

        self._priority = QComboBox()
        self._priority.addItems(['none', 'low', 'medium', 'high'])
        form.addRow('優先', self._priority)

        self._due_date = QDateEdit()
        self._due_date.setCalendarPopup(True)
        self._due_date.setDisplayFormat('yyyy-MM-dd')
        self._due_date.setSpecialValueText('（無期限）')
        self._due_date.setDate(QDate.currentDate())
        form.addRow('期限日', self._due_date)

        self._due_time = QTimeEdit()
        self._due_time.setDisplayFormat('HH:mm')
        self._due_time.setSpecialValueText('（無時間）')
        self._due_time.setTime(QTime(0, 0))
        form.addRow('期限時', self._due_time)

        self._auto_complete = QCheckBox('子任務全完成時自動完成此任務')
        self._auto_complete.setChecked(True)
        if self._parent_id:
            self._auto_complete.hide()
        form.addRow('', self._auto_complete)

        layout.addLayout(form)

        # Buttons
        btn_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        btn_box.button(QDialogButtonBox.StandardButton.Ok).setText('確認')
        btn_box.button(QDialogButtonBox.StandardButton.Cancel).setText('取消')
        btn_box.accepted.connect(self._on_accept)
        btn_box.rejected.connect(self.reject)
        layout.addWidget(btn_box)

    def _load_task(self, task: Task) -> None:
        self._title.setText(task.title)
        self._desc.setPlainText(task.description or '')
        self._priority.setCurrentText(task.priority)
        if task.due_date:
            self._due_date.setDate(QDate.fromString(task.due_date, 'yyyy-MM-dd'))
        if task.due_time:
            self._due_time.setTime(QTime.fromString(task.due_time[:5], 'HH:mm'))
        self._auto_complete.setChecked(task.auto_complete_with_children)

    def _on_accept(self) -> None:
        title = self._title.text().strip()
        if not title:
            self._title.setPlaceholderText('請輸入任務名稱！')
            return

        if self._task:
            task = self._task
        else:
            task = Task(id=str(uuid.uuid4()), title='', created_at='', updated_at='')
            task.parent_id = self._parent_id

        task.title = title
        task.description = self._desc.toPlainText().strip()
        task.priority = self._priority.currentText()
        task.auto_complete_with_children = self._auto_complete.isChecked()

        d = self._due_date.date()
        task.due_date = d.toString('yyyy-MM-dd') if d.isValid() else None

        t = self._due_time.time()
        task.due_time = t.toString('HH:mm') if t != QTime(0, 0) else None

        self._result_task = task
        self.accept()

    def get_task(self) -> Optional[Task]:
        return self._result_task
