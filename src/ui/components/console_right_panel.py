"""
Right panel: QFormLayout task editor.
"""
from __future__ import annotations
from typing import Optional

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QFormLayout, QLineEdit, QTextEdit,
    QComboBox, QDateEdit, QTimeEdit, QHBoxLayout, QPushButton,
    QLabel, QCheckBox, QScrollArea, QFrame, QSizePolicy
)
from PySide6.QtCore import Signal, Qt, QDate, QTime

from src.data.models import Task
from src.ui.utils import set_combo_by_data, NO_DATE


class RightPanel(QWidget):
    save_requested = Signal(object)   # Task
    cancel_requested = Signal()
    add_child_requested = Signal(str)  # parent_id

    def __init__(self, parent=None):
        super().__init__(parent)
        self._task: Optional[Task] = None
        self._build_ui()
        self.show_empty()

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Header
        self._header = QLabel('任務詳情')
        self._header.setStyleSheet(
            'background-color: #F5F5F5; border-bottom: 1px solid #E0E0E0; '
            'padding: 12px 16px; font-weight: bold; font-size: 14px;'
        )
        outer.addWidget(self._header)

        # Scroll area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        form.setSpacing(8)

        # Title
        self._title = QLineEdit()
        self._title.setPlaceholderText('任務名稱')
        form.addRow('名稱', self._title)

        # Description
        self._desc = QTextEdit()
        self._desc.setPlaceholderText('描述（可選）')
        self._desc.setFixedHeight(80)
        form.addRow('描述', self._desc)

        # Status
        self._status = QComboBox()
        for val, lbl in (('pending', '待辦'), ('done', '完成'), ('archived', '歸檔')):
            self._status.addItem(lbl, val)
        form.addRow('狀態', self._status)

        # Priority
        self._priority = QComboBox()
        for val, lbl in (('none', '無'), ('low', '低'), ('medium', '中'), ('high', '高')):
            self._priority.addItem(lbl, val)
        form.addRow('優先', self._priority)

        # Due date
        self._due_date = QDateEdit()
        self._due_date.setCalendarPopup(True)
        self._due_date.setDisplayFormat('yyyy-MM-dd')
        self._due_date.setSpecialValueText('（無）')
        self._due_date.setMinimumDate(NO_DATE)
        form.addRow('期限日', self._due_date)

        self._clear_date_btn = QPushButton('清除日期')
        self._clear_date_btn.setProperty('class', 'secondary')
        self._clear_date_btn.setFixedHeight(28)
        self._clear_date_btn.clicked.connect(self._clear_due_date)
        form.addRow('', self._clear_date_btn)

        # Due time
        self._due_time = QTimeEdit()
        self._due_time.setDisplayFormat('HH:mm')
        self._due_time.setSpecialValueText('（無時間）')
        form.addRow('期限時', self._due_time)

        # Auto complete
        self._auto_complete = QCheckBox('子任務全完成時自動完成此任務')
        form.addRow('', self._auto_complete)

        layout.addLayout(form)

        # Add child button (only shown for top-level tasks)
        self._add_child_btn = QPushButton('+ 新增子任務')
        self._add_child_btn.setProperty('class', 'secondary')
        self._add_child_btn.clicked.connect(self._on_add_child)
        layout.addWidget(self._add_child_btn)

        layout.addStretch()
        scroll.setWidget(content)
        outer.addWidget(scroll)

        # Action buttons
        btn_bar = QWidget()
        btn_bar.setStyleSheet('background-color: #F5F5F5; border-top: 1px solid #E0E0E0;')
        btn_layout = QHBoxLayout(btn_bar)
        btn_layout.setContentsMargins(12, 8, 12, 8)
        btn_layout.setSpacing(8)

        self._save_btn = QPushButton('儲存')
        self._save_btn.setFixedWidth(80)
        self._save_btn.clicked.connect(self._on_save)
        btn_layout.addStretch()
        btn_layout.addWidget(self._save_btn)

        cancel_btn = QPushButton('取消')
        cancel_btn.setProperty('class', 'secondary')
        cancel_btn.setFixedWidth(80)
        cancel_btn.clicked.connect(self.cancel_requested)
        btn_layout.addWidget(cancel_btn)

        outer.addWidget(btn_bar)

    def show_empty(self) -> None:
        self._task = None
        self._header.setText('選擇任務以編輯')
        self._title.clear()
        self._desc.clear()
        set_combo_by_data(self._status, 'pending')
        set_combo_by_data(self._priority, 'none')
        self._due_date.setDate(NO_DATE)
        self._save_btn.setEnabled(False)
        self._add_child_btn.hide()

    def load_task(self, task: Task) -> None:
        self._task = task
        self._header.setText(f'編輯：{task.title[:20]}')
        self._title.setText(task.title)
        self._desc.setPlainText(task.description or '')
        set_combo_by_data(self._status, task.status)
        set_combo_by_data(self._priority, task.priority)

        if task.due_date:
            d = QDate.fromString(task.due_date, 'yyyy-MM-dd')
            self._due_date.setDate(d)
        else:
            self._due_date.setDate(NO_DATE)

        if task.due_time:
            t = QTime.fromString(task.due_time[:5], 'HH:mm')
            self._due_time.setTime(t)
        else:
            self._due_time.setTime(QTime(0, 0))

        self._auto_complete.setChecked(task.auto_complete_with_children)
        self._save_btn.setEnabled(True)
        # Show add child only for top-level tasks
        self._add_child_btn.setVisible(task.parent_id is None)

    def _clear_due_date(self) -> None:
        self._due_date.setDate(NO_DATE)

    def _on_add_child(self) -> None:
        if self._task:
            self.add_child_requested.emit(self._task.id)

    def _on_save(self) -> None:
        if not self._task:
            return
        title = self._title.text().strip()
        if not title:
            return

        self._task.title = title
        self._task.description = self._desc.toPlainText().strip()
        self._task.status = self._status.currentData()
        self._task.priority = self._priority.currentData()
        self._task.auto_complete_with_children = self._auto_complete.isChecked()

        d = self._due_date.date()
        if d.year() > NO_DATE.year():
            self._task.due_date = d.toString('yyyy-MM-dd')
        else:
            self._task.due_date = None

        t = self._due_time.time()
        if t != QTime(0, 0):
            self._task.due_time = t.toString('HH:mm')
        else:
            self._task.due_time = None

        self.save_requested.emit(self._task)
