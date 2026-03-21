"""
Right panel: QFormLayout task editor + phase tasks section.
"""
from __future__ import annotations
from typing import Optional

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QFormLayout, QLineEdit, QTextEdit,
    QComboBox, QDateEdit, QHBoxLayout, QPushButton,
    QLabel, QCheckBox, QScrollArea, QFrame
)
from PySide6.QtCore import Signal, Qt, QDate

from src.data.models import Task, TaskPhase
from src.data.phase_repository import PhaseRepository
from src.ui.utils import set_combo_by_data, NO_DATE
from src.ui.components.time_picker_mixin import TimePickerMixin
from src.core.logger import logger


class RightPanel(QWidget, TimePickerMixin):
    save_requested = Signal(object)   # Task
    cancel_requested = Signal()
    add_child_requested = Signal(str)  # parent_id

    def __init__(self, phase_repo: PhaseRepository, parent=None):
        super().__init__(parent)
        self._task: Optional[Task] = None
        self._time_str: Optional[str] = None  # 'HH:MM' or None
        self._phase_repo = phase_repo
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

        # Phase section (hidden until task is loaded)
        self._phase_section = QWidget()
        phase_outer = QVBoxLayout(self._phase_section)
        phase_outer.setContentsMargins(0, 8, 0, 0)
        phase_outer.setSpacing(6)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet('color: #E2E8F0;')
        phase_outer.addWidget(sep)

        phase_hdr = QLabel('階段性任務')
        phase_hdr.setStyleSheet(
            'font-weight: 600; font-size: 12px; color: #475569; padding-bottom: 2px;'
        )
        phase_outer.addWidget(phase_hdr)

        self._phases_list = QVBoxLayout()
        self._phases_list.setSpacing(2)
        phase_outer.addLayout(self._phases_list)

        # Inline add row
        add_row = QWidget()
        ar = QHBoxLayout(add_row)
        ar.setContentsMargins(0, 0, 0, 0)
        ar.setSpacing(6)
        self._phase_input = QLineEdit()
        self._phase_input.setPlaceholderText('新增階段…')
        self._phase_input.setFixedHeight(28)
        self._phase_input.returnPressed.connect(self._on_add_phase)
        ar.addWidget(self._phase_input)
        add_phase_btn = QPushButton('+')
        add_phase_btn.setFixedSize(28, 28)
        add_phase_btn.setProperty('class', 'secondary')
        add_phase_btn.clicked.connect(self._on_add_phase)
        ar.addWidget(add_phase_btn)
        phase_outer.addWidget(add_row)

        self._phase_section.hide()
        layout.addWidget(self._phase_section)

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
        self._phase_section.hide()
        self._clear_phases_ui()

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

        # Load phases
        self._reload_phases()

    # ── Internal ─────────────────────────────────────────────────────────────
    def _clear_due_date(self) -> None:
        self._due_date.setDate(NO_DATE)

    def _on_add_child(self) -> None:
        if self._task:
            self.add_child_requested.emit(self._task.id)

    # ── Phase helpers ─────────────────────────────────────────────────────────
    def _clear_phases_ui(self) -> None:
        while self._phases_list.count():
            item = self._phases_list.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def _reload_phases(self) -> None:
        if not self._task:
            return
        self._clear_phases_ui()
        phases = self._phase_repo.get_phases(self._task.id)
        for phase in phases:
            self._add_phase_row(phase)
        self._phase_section.show()
        self._phase_input.clear()

    @staticmethod
    def _phase_style(is_done: bool) -> str:
        if is_done:
            return 'text-decoration: line-through; color: #94A3B8;'
        return 'color: #1E293B;'

    def _add_phase_row(self, phase: TaskPhase) -> None:
        row = QWidget()
        rl = QHBoxLayout(row)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(6)

        cb = QCheckBox(phase.name)
        cb.setChecked(phase.status == 'done')
        cb.setStyleSheet(self._phase_style(phase.status == 'done'))

        def _on_toggle(checked: bool, pid=phase.id, widget=cb) -> None:
            new_status = 'done' if checked else 'pending'
            try:
                self._phase_repo.set_status(pid, new_status)
                widget.setStyleSheet(self._phase_style(checked))
            except Exception as e:
                logger.error(f'Phase set_status failed: {e}')
                widget.blockSignals(True)
                try:
                    widget.setChecked(not checked)
                finally:
                    widget.blockSignals(False)

        cb.toggled.connect(_on_toggle)
        rl.addWidget(cb, stretch=1)

        del_btn = QPushButton('✕')
        del_btn.setFixedSize(22, 22)
        del_btn.setProperty('class', 'ghost')
        del_btn.setToolTip('刪除階段')

        def _on_delete(pid=phase.id, r=row) -> None:
            try:
                self._phase_repo.delete_phase(pid)
                r.deleteLater()
            except Exception as e:
                logger.error(f'Phase delete_phase failed: {e}')

        del_btn.clicked.connect(_on_delete)
        rl.addWidget(del_btn)

        self._phases_list.addWidget(row)

    def _on_add_phase(self) -> None:
        if not self._task:
            return
        name = self._phase_input.text().strip()
        if not name:
            return
        try:
            phase = self._phase_repo.add_phase(self._task.id, name)
            self._add_phase_row(phase)
            self._phase_input.clear()
        except Exception as e:
            logger.error(f'Phase add_phase failed: {e}')

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
