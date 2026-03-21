"""
Right panel: QFormLayout task editor.
"""
from __future__ import annotations
from typing import Optional

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QFormLayout, QLineEdit, QTextEdit,
    QComboBox, QDateEdit, QHBoxLayout, QPushButton,
    QLabel, QCheckBox, QScrollArea, QFrame
)
from PySide6.QtCore import Signal, Qt, QDate

from src.data.models import Task
from src.ui.utils import set_combo_by_data, NO_DATE


class RightPanel(QWidget):
    save_requested = Signal(object)   # Task
    cancel_requested = Signal()
    add_child_requested = Signal(str)  # parent_id

    def __init__(self, parent=None):
        super().__init__(parent)
        self._task: Optional[Task] = None
        self._time_str: Optional[str] = None  # 'HH:MM' or None
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
        self._due_date.setSpecialValueText('無期限')
        self._due_date.setMinimumDate(NO_DATE)
        form.addRow('期限日', self._due_date)

        self._clear_date_btn = QPushButton('清除日期')
        self._clear_date_btn.setProperty('class', 'secondary')
        self._clear_date_btn.setFixedHeight(28)
        self._clear_date_btn.clicked.connect(self._clear_due_date)
        form.addRow('', self._clear_date_btn)

        # Due time — clock picker button (avoids QTime(0,0) sentinel ambiguity)
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

    # ── Time picker ─────────────────────────────────────────────────────────
    def _open_time_picker(self) -> None:
        from src.ui.components.time_picker_dialog import TimePickerDialog
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
            self._apply_time_btn_selected()

    def _apply_time_btn_selected(self) -> None:
        self._time_btn.setText(self._time_str)
        self._time_btn.setStyleSheet(
            'background-color: #EEF2FF; color: #4F46E5; '
            'border: 1.5px solid #4F46E5; border-radius: 6px; '
            'padding: 7px 12px; font-weight: 600;'
        )
        self._clear_time_btn.show()

    def _clear_time(self) -> None:
        self._time_str = None
        self._time_btn.setText('＋ 設定時間（可選）')
        self._time_btn.setStyleSheet('')
        self._clear_time_btn.hide()

    # ── Public API ───────────────────────────────────────────────────────────
    def show_empty(self) -> None:
        self._task = None
        self._header.setText('選擇任務以編輯')
        self._title.clear()
        self._desc.clear()
        set_combo_by_data(self._status, 'pending')
        set_combo_by_data(self._priority, 'none')
        self._due_date.setDate(NO_DATE)
        self._clear_time()
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
            self._time_str = task.due_time[:5]
            self._apply_time_btn_selected()
        else:
            self._clear_time()

        self._auto_complete.setChecked(task.auto_complete_with_children)
        self._save_btn.setEnabled(True)
        self._add_child_btn.setVisible(task.parent_id is None)

    # ── Internal ─────────────────────────────────────────────────────────────
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
        self._task.due_date = d.toString('yyyy-MM-dd') if d.year() > NO_DATE.year() else None
        self._task.due_time = self._time_str  # None or 'HH:MM' — no sentinel ambiguity

        self.save_requested.emit(self._task)
