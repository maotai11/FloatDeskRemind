"""
Task add/edit dialog with clock-face time picker.

Patch 11 additions:
  - Recurrence section: "循環任務" checkbox + rule combobox (daily/weekly/monthly)
  - Reminder section: "啟用提醒" checkbox + QDateTimeEdit for remind_at
  - Validation: recurring task requires due_date (inline error, blocks save)
  - get_remind_at() → Optional[str] — caller passes this to AppController
    which saves the reminder after the task row is committed to DB.
"""
from __future__ import annotations
import uuid
from typing import Optional

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLineEdit, QTextEdit, QComboBox, QDateEdit, QDateTimeEdit,
    QPushButton, QLabel, QCheckBox, QDialogButtonBox, QWidget, QFrame
)
from PySide6.QtCore import Qt, QDate, QDateTime, QTime

from src.data.models import Task
from src.ui.utils import set_combo_by_data, NO_DATE
from src.ui.components.time_picker_mixin import TimePickerMixin


class TaskEditDialog(QDialog, TimePickerMixin):
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
        self._remind_at: Optional[str] = None  # set in _on_accept for caller to retrieve

        self.setWindowTitle('新增任務' if task is None else '編輯任務')
        self.setModal(True)
        self.setMinimumWidth(440)
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
        self._due_date.setMinimumDate(NO_DATE)
        self._due_date.setDate(QDate.currentDate())
        form.addRow('期限日', self._due_date)

        # Due time — clock picker button
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

        form.addRow('期限時', time_row)

        # ---- Section separator ----
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet('color: #E2E8F0; margin: 4px 0;')
        form.addRow(sep)

        # ---- Recurrence section ----
        recur_row = QWidget()
        rr = QHBoxLayout(recur_row)
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
        form.addRow('循環', recur_row)

        # ---- Reminder section ----
        remind_row = QWidget()
        rmr = QHBoxLayout(remind_row)
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
        form.addRow('到期提醒', remind_row)

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

    def _load_task(self, task: Task) -> None:
        self._title.setText(task.title)
        self._desc.setPlainText(task.description or '')
        set_combo_by_data(self._priority, task.priority)
        if task.due_date:
            self._due_date.setDate(QDate.fromString(task.due_date, 'yyyy-MM-dd'))
        if task.due_time:
            self._time_str = task.due_time[:5]
            self._apply_time_btn_selected()
        if hasattr(self, '_auto_complete'):
            self._auto_complete.setChecked(task.auto_complete_with_children)

        # Recurrence
        self._is_recurring.setChecked(task.is_recurring)
        self._recurrence_rule.setEnabled(task.is_recurring)
        if task.recurrence_rule:
            set_combo_by_data(self._recurrence_rule, task.recurrence_rule)

        # Reminder: TaskEditDialog is primarily used for new tasks; reminder
        # pre-population from DB is handled by RightPanel for existing tasks.

    def _on_accept(self) -> None:
        title = self._title.text().strip()
        if not title:
            self._msg.setText('請輸入任務名稱')
            self._msg.show()
            self._title.setFocus()
            return

        # Validate: recurring task must have a due_date
        if self._is_recurring.isChecked():
            d = self._due_date.date()
            has_due = d.isValid() and d.year() > NO_DATE.year()
            if not has_due:
                self._msg.setText('循環任務需要設定期限日')
                self._msg.show()
                self._due_date.setFocus()
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
        task.due_date = d.toString('yyyy-MM-dd') if d.isValid() and d.year() > NO_DATE.year() else None
        task.due_time = self._time_str

        if not self._parent_id and hasattr(self, '_auto_complete'):
            task.auto_complete_with_children = self._auto_complete.isChecked()

        # Recurrence
        task.is_recurring = self._is_recurring.isChecked()
        task.recurrence_rule = self._recurrence_rule.currentData() if task.is_recurring else None

        # Reminder: store for caller to retrieve via get_remind_at()
        # The actual DB save happens in AppController AFTER the task row is committed.
        if self._remind_enabled.isChecked():
            self._remind_at = self._remind_dt.dateTime().toString('yyyy-MM-ddTHH:mm:ss')
        else:
            self._remind_at = None

        self._result_task = task
        self.accept()

    def get_task(self) -> Optional[Task]:
        return self._result_task

    def get_remind_at(self) -> Optional[str]:
        """Return the remind_at ISO string if reminder is enabled, else None.

        Only valid after exec() returns Accepted.
        The caller (ConsoleWindow → AppController) is responsible for creating
        the TaskReminder row in the DB after the task itself is committed.
        """
        return self._remind_at
