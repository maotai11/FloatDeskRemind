"""
Task add/edit dialog with clock-face time picker.
"""
from __future__ import annotations
import uuid
from typing import Optional

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLineEdit, QTextEdit, QComboBox, QDateEdit,
    QPushButton, QLabel, QCheckBox, QDialogButtonBox, QWidget
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
        self._time_str: Optional[str] = None   # 'HH:MM' or None

        self.setWindowTitle('新增任務' if task is None else '編輯任務')
        self.setModal(True)
        self.setMinimumWidth(420)
        self._build_ui()
        if task:
            self._load_task(task)

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(16)

        # Section header
        header = QLabel('新增任務' if self._task is None else '編輯任務')
        header.setStyleSheet(
            'font-size: 17px; font-weight: 700; color: #1E293B; margin-bottom: 4px;'
        )
        layout.addWidget(header)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        form.setSpacing(10)
        form.setContentsMargins(0, 0, 0, 0)

        # Title
        self._title = QLineEdit()
        self._title.setPlaceholderText('任務名稱（必填）')
        form.addRow('名稱 *', self._title)

        # Description
        self._desc = QTextEdit()
        self._desc.setPlaceholderText('備註（可選）')
        self._desc.setFixedHeight(72)
        form.addRow('備註', self._desc)

        # Priority
        self._priority = QComboBox()
        for val, lbl in (('none', '無'), ('low', '低'), ('medium', '中'), ('high', '高')):
            self._priority.addItem(lbl, val)
        form.addRow('優先', self._priority)

        # Due date
        self._due_date = QDateEdit()
        self._due_date.setCalendarPopup(True)
        self._due_date.setDisplayFormat('yyyy-MM-dd')
        self._due_date.setSpecialValueText('無期限')
        self._due_date.setMinimumDate(QDate(2000, 1, 1))
        self._due_date.setDate(QDate.currentDate())
        form.addRow('期限日', self._due_date)

        # Time — clock picker button
        time_row = QWidget()
        tr = QHBoxLayout(time_row)
        tr.setContentsMargins(0, 0, 0, 0)
        tr.setSpacing(8)

        self._time_btn = QPushButton('＋ 設定時間（可選）')
        self._time_btn.setProperty('class', 'secondary')
        self._time_btn.clicked.connect(self._open_time_picker)
        tr.addWidget(self._time_btn)

        self._clear_time_btn = QPushButton('✕')
        self._clear_time_btn.setFixedWidth(32)
        self._clear_time_btn.setToolTip('清除時間')
        self._clear_time_btn.setProperty('class', 'ghost')
        self._clear_time_btn.clicked.connect(self._clear_time)
        self._clear_time_btn.hide()
        tr.addWidget(self._clear_time_btn)

        form.addRow('提醒時間', time_row)

        # Auto-complete (hidden for child tasks)
        self._auto_complete = QCheckBox('子任務全完成時自動完成此任務')
        self._auto_complete.setChecked(True)
        if self._parent_id:
            self._auto_complete.hide()
        else:
            form.addRow('', self._auto_complete)

        layout.addLayout(form)

        # Validation message
        self._msg = QLabel('')
        self._msg.setStyleSheet('color: #EF4444; font-size: 12px;')
        self._msg.hide()
        layout.addWidget(self._msg)

        # Buttons
        btn_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        btn_box.button(QDialogButtonBox.StandardButton.Ok).setText('儲存')
        btn_box.button(QDialogButtonBox.StandardButton.Cancel).setText('取消')
        btn_box.accepted.connect(self._on_accept)
        btn_box.rejected.connect(self.reject)
        layout.addWidget(btn_box)

    def _open_time_picker(self) -> None:
        from src.ui.components.time_picker_dialog import TimePickerDialog
        # Parse existing time if set
        h, m, pm = 9, 0, False
        if self._time_str:
            try:
                parts = self._time_str.split(':')
                h24 = int(parts[0])
                m = int(parts[1])
                pm = h24 >= 12
                h = h24 % 12 or 12
            except Exception:
                pass
        dlg = TimePickerDialog(hour=h, minute=m, is_pm=pm, parent=self)
        if dlg.exec():
            self._time_str = dlg.get_time_str()
            self._time_btn.setText(f'  {self._time_str}')
            self._time_btn.setStyleSheet(
                'background-color: #EEF2FF; color: #4F46E5; '
                'border: 1.5px solid #4F46E5; border-radius: 6px; '
                'padding: 7px 12px; font-weight: 600;'
            )
            self._clear_time_btn.show()

    def _clear_time(self) -> None:
        self._time_str = None
        self._time_btn.setText('＋ 設定時間（可選）')
        self._time_btn.setStyleSheet('')  # revert to QSS default
        self._clear_time_btn.hide()

    def _load_task(self, task: Task) -> None:
        self._title.setText(task.title)
        self._desc.setPlainText(task.description or '')
        for i in range(self._priority.count()):
            if self._priority.itemData(i) == task.priority:
                self._priority.setCurrentIndex(i)
                break
        if task.due_date:
            self._due_date.setDate(QDate.fromString(task.due_date, 'yyyy-MM-dd'))
        if task.due_time:
            self._time_str = task.due_time[:5]
            self._time_btn.setText(f'  {self._time_str}')
            self._time_btn.setStyleSheet(
                'background-color: #EEF2FF; color: #4F46E5; '
                'border: 1.5px solid #4F46E5; border-radius: 6px; '
                'padding: 7px 12px; font-weight: 600;'
            )
            self._clear_time_btn.show()
        if hasattr(self, '_auto_complete'):
            self._auto_complete.setChecked(task.auto_complete_with_children)

    def _on_accept(self) -> None:
        title = self._title.text().strip()
        if not title:
            self._msg.setText('請輸入任務名稱')
            self._msg.show()
            self._title.setFocus()
            return
        self._msg.hide()

        if self._task:
            task = self._task
        else:
            task = Task(id=str(uuid.uuid4()), title='', created_at='', updated_at='')
            task.parent_id = self._parent_id

        task.title = title
        task.description = self._desc.toPlainText().strip()
        task.priority = self._priority.currentData()

        d = self._due_date.date()
        task.due_date = d.toString('yyyy-MM-dd') if d.isValid() and d.year() >= 2001 else None
        task.due_time = self._time_str

        if not self._parent_id and hasattr(self, '_auto_complete'):
            task.auto_complete_with_children = self._auto_complete.isChecked()

        self._result_task = task
        self.accept()

    def get_task(self) -> Optional[Task]:
        return self._result_task
