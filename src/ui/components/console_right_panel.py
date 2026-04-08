"""
Right panel: QFormLayout task editor + phase tasks section.

Patch 11 additions:
  - Recurrence section: "循環任務" checkbox + rule combobox (daily/weekly/monthly)
  - Reminder section: "啟用提醒" checkbox + QDateTimeEdit for remind_at
  - load_task(): pre-populates recurrence fields from task + reminder from repo
  - show_empty(): resets recurrence + reminder fields
  - _on_save(): writes recurrence fields to task; saves/updates/deletes reminder inline

RightPanel calls ReminderRepository directly (same pattern as RecycleBinDialog
calling TaskService directly). The task already exists in DB when _on_save() is
called, so we can safely upsert the reminder immediately.

Patch 15 additions:
  - Description field enlarged (min-height 140), placeholder updated to
    '補充說明、步驟、備忘…', empty state hint shown when no description.
  - Dirty tracking: _is_dirty flag + asterisk in header when unsaved.
  - Auto-save debounce: 1 second QTimer fires _on_autosave() after any field change.
  - On switch: if dirty and switching to a different task, flush-save immediately
    before loading the new task (prevents data loss on task switch).
  - _loading guard: field signals during load_task() are ignored by _mark_dirty().
"""
from __future__ import annotations
from typing import Optional

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QFormLayout, QLineEdit, QTextEdit,
    QComboBox, QDateEdit, QDateTimeEdit, QHBoxLayout, QPushButton,
    QLabel, QCheckBox, QScrollArea, QFrame
)
from PySide6.QtCore import Signal, Qt, QDate, QDateTime, QTime, QTimer

from src.data.models import Task, TaskPhase, TaskReminder
from src.data.phase_repository import PhaseRepository
from src.data.reminder_repository import ReminderRepository
from src.ui.utils import set_combo_by_data, NO_DATE
from src.ui.components.time_picker_mixin import TimePickerMixin
from src.core.logger import logger

# How long (ms) after the last keystroke before auto-saving
_AUTOSAVE_DELAY_MS = 1_000


class RightPanel(QWidget, TimePickerMixin):
    save_requested = Signal(object)   # Task
    cancel_requested = Signal()
    add_child_requested = Signal(str)  # parent_id

    def __init__(
        self,
        phase_repo: PhaseRepository,
        reminder_repo: Optional[ReminderRepository] = None,
        parent=None,
    ):
        super().__init__(parent)
        self._task: Optional[Task] = None
        self._time_str: Optional[str] = None  # 'HH:MM' or None
        self._phase_repo = phase_repo
        self._reminder_repo = reminder_repo

        # Dirty / auto-save state
        self._is_dirty: bool = False
        self._loading: bool = False   # True while load_task() is populating fields

        self._autosave_timer = QTimer(self)
        self._autosave_timer.setSingleShot(True)
        self._autosave_timer.setInterval(_AUTOSAVE_DELAY_MS)
        self._autosave_timer.timeout.connect(self._on_autosave)

        self._build_ui()
        self.show_empty()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Header (shows task title + asterisk when dirty)
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

        # ── Title ──────────────────────────────────────────────────────
        self._title = QLineEdit()
        self._title.setPlaceholderText('任務名稱')
        self._title.textChanged.connect(self._mark_dirty)
        form.addRow('名稱', self._title)

        # ── Description (Patch 15: enlarged + better placeholder) ──────
        self._desc = QTextEdit()
        self._desc.setPlaceholderText('補充說明、步驟、備忘…')
        self._desc.setMinimumHeight(140)
        self._desc.setMaximumHeight(320)
        self._desc.textChanged.connect(self._mark_dirty)
        form.addRow('說明', self._desc)

        # ── Status ────────────────────────────────────────────────────
        self._status = QComboBox()
        for val, lbl in (('pending', '待辦'), ('done', '完成'), ('archived', '歸檔')):
            self._status.addItem(lbl, val)
        self._status.currentIndexChanged.connect(self._mark_dirty)
        form.addRow('狀態', self._status)

        # ── Priority ──────────────────────────────────────────────────
        self._priority = QComboBox()
        for val, lbl in (('none', '無'), ('low', '低'), ('medium', '中'), ('high', '高')):
            self._priority.addItem(lbl, val)
        self._priority.currentIndexChanged.connect(self._mark_dirty)
        form.addRow('優先', self._priority)

        # ── Due date ──────────────────────────────────────────────────
        self._due_date = QDateEdit()
        self._due_date.setCalendarPopup(True)
        self._due_date.setDisplayFormat('yyyy-MM-dd')
        self._due_date.setSpecialValueText('無期限')
        self._due_date.setMinimumDate(NO_DATE)
        self._due_date.dateChanged.connect(self._mark_dirty)
        form.addRow('期限日', self._due_date)

        self._clear_date_btn = QPushButton('清除日期')
        self._clear_date_btn.setProperty('class', 'secondary')
        self._clear_date_btn.setFixedHeight(28)
        self._clear_date_btn.clicked.connect(self._clear_due_date)
        form.addRow('', self._clear_date_btn)

        # ── Due time — clock picker button ────────────────────────────
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

        # ── Auto complete ─────────────────────────────────────────────
        self._auto_complete = QCheckBox('子任務全完成時自動完成此任務')
        self._auto_complete.toggled.connect(self._mark_dirty)
        form.addRow('', self._auto_complete)

        # ── Section separator ─────────────────────────────────────────
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet('color: #E2E8F0; margin: 4px 0;')
        form.addRow(sep)

        # ── Recurrence section ────────────────────────────────────────
        recur_row = QWidget()
        rr = QHBoxLayout(recur_row)
        rr.setContentsMargins(0, 0, 0, 0)
        rr.setSpacing(10)

        self._is_recurring = QCheckBox('循環任務')
        self._is_recurring.toggled.connect(self._mark_dirty)
        rr.addWidget(self._is_recurring)

        self._recurrence_rule = QComboBox()
        for val, lbl in (('daily', '每天'), ('weekly', '每週'), ('monthly', '每月')):
            self._recurrence_rule.addItem(lbl, val)
        self._recurrence_rule.setEnabled(False)
        self._recurrence_rule.currentIndexChanged.connect(self._mark_dirty)
        rr.addWidget(self._recurrence_rule)
        rr.addStretch()

        self._is_recurring.toggled.connect(self._recurrence_rule.setEnabled)
        form.addRow('循環', recur_row)

        # ── Reminder section ──────────────────────────────────────────
        remind_row = QWidget()
        rmr = QHBoxLayout(remind_row)
        rmr.setContentsMargins(0, 0, 0, 0)
        rmr.setSpacing(10)

        self._remind_enabled = QCheckBox('啟用提醒')
        self._remind_enabled.toggled.connect(self._mark_dirty)
        rmr.addWidget(self._remind_enabled)

        self._remind_dt = QDateTimeEdit()
        self._remind_dt.setDisplayFormat('yyyy-MM-dd HH:mm')
        self._remind_dt.setCalendarPopup(True)
        self._remind_dt.setDateTime(
            QDateTime(QDate.currentDate().addDays(1), QTime(9, 0))
        )
        self._remind_dt.setEnabled(False)
        self._remind_dt.dateTimeChanged.connect(self._mark_dirty)
        rmr.addWidget(self._remind_dt)

        self._remind_enabled.toggled.connect(self._remind_dt.setEnabled)
        form.addRow('到期提醒', remind_row)

        layout.addLayout(form)

        # ── Add child button ──────────────────────────────────────────
        self._add_child_btn = QPushButton('+ 新增子任務')
        self._add_child_btn.setProperty('class', 'secondary')
        self._add_child_btn.clicked.connect(self._on_add_child)
        layout.addWidget(self._add_child_btn)

        # ── Phase section (hidden until task is loaded) ───────────────
        self._phase_section = QWidget()
        phase_outer = QVBoxLayout(self._phase_section)
        phase_outer.setContentsMargins(0, 8, 0, 0)
        phase_outer.setSpacing(6)

        phase_sep = QFrame()
        phase_sep.setFrameShape(QFrame.Shape.HLine)
        phase_sep.setStyleSheet('color: #E2E8F0;')
        phase_outer.addWidget(phase_sep)

        phase_hdr = QLabel('階段性任務')
        phase_hdr.setStyleSheet(
            'font-weight: 600; font-size: 12px; color: #475569; padding-bottom: 2px;'
        )
        phase_outer.addWidget(phase_hdr)

        self._phases_list = QVBoxLayout()
        self._phases_list.setSpacing(2)
        phase_outer.addLayout(self._phases_list)

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

        # ── Action buttons ────────────────────────────────────────────
        btn_bar = QWidget()
        btn_bar.setStyleSheet(
            'background-color: #F5F5F5; border-top: 1px solid #E0E0E0; '
            'padding: 0;'
        )
        btn_layout = QHBoxLayout(btn_bar)
        btn_layout.setContentsMargins(12, 10, 12, 10)
        btn_layout.setSpacing(10)

        self._save_btn = QPushButton('儲存')
        self._save_btn.setFixedHeight(36)
        self._save_btn.setMinimumWidth(90)
        self._save_btn.setStyleSheet(
            'QPushButton {'
            '  background-color: #4F46E5;'
            '  color: #FFFFFF;'
            '  border: none;'
            '  border-radius: 8px;'
            '  padding: 0 20px;'
            '  font-size: 13px;'
            '  font-weight: 700;'
            '}'
            'QPushButton:hover { background-color: #3730A3; }'
            'QPushButton:pressed { background-color: #312E81; }'
            'QPushButton:disabled { background-color: #CBD5E1; color: #F8FAFC; }'
        )
        self._save_btn.clicked.connect(self._on_save)
        btn_layout.addStretch()
        btn_layout.addWidget(self._save_btn)

        cancel_btn = QPushButton('取消')
        cancel_btn.setFixedHeight(36)
        cancel_btn.setMinimumWidth(90)
        cancel_btn.setStyleSheet(
            'QPushButton {'
            '  background-color: transparent;'
            '  color: #4F46E5;'
            '  border: 1.5px solid #4F46E5;'
            '  border-radius: 8px;'
            '  padding: 0 20px;'
            '  font-size: 13px;'
            '  font-weight: 600;'
            '}'
            'QPushButton:hover { background-color: #EEF2FF; }'
        )
        cancel_btn.clicked.connect(self.cancel_requested)
        btn_layout.addWidget(cancel_btn)

        outer.addWidget(btn_bar)

    # ------------------------------------------------------------------
    # Dirty tracking helpers
    # ------------------------------------------------------------------

    def _mark_dirty(self) -> None:
        """Called by any field-change signal. Ignored during load_task() population."""
        if self._loading:
            return
        self._is_dirty = True
        self._update_header()
        if self._task:
            self._autosave_timer.start()  # restart debounce on every change

    def _update_header(self) -> None:
        if not self._task:
            self._header.setText('選擇任務以編輯')
            return
        short_title = self._task.title[:20]
        if self._is_dirty:
            self._header.setText(f'編輯：{short_title} *')
        else:
            self._header.setText(f'編輯：{short_title}')

    def _on_autosave(self) -> None:
        """Called by debounce timer — auto-save if still dirty."""
        if self._is_dirty and self._task:
            self._on_save()

    @property
    def is_dirty(self) -> bool:
        """True if there are unsaved changes in the form."""
        return self._is_dirty

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def show_empty(self) -> None:
        self._autosave_timer.stop()
        self._task = None
        self._is_dirty = False

        self._loading = True
        try:
            self._header.setText('選擇任務以編輯')
            self._title.clear()
            self._desc.clear()
            set_combo_by_data(self._status, 'pending')
            set_combo_by_data(self._priority, 'none')
            self._due_date.setDate(NO_DATE)
            self._clear_time()
            self._auto_complete.setChecked(True)

            # Reset recurrence
            self._is_recurring.setChecked(False)
            self._recurrence_rule.setEnabled(False)
            set_combo_by_data(self._recurrence_rule, 'daily')

            # Reset reminder
            self._remind_enabled.setChecked(False)
            self._remind_dt.setEnabled(False)
            self._remind_dt.setDateTime(
                QDateTime(QDate.currentDate().addDays(1), QTime(9, 0))
            )
        finally:
            self._loading = False

        self._save_btn.setEnabled(False)
        self._add_child_btn.hide()
        self._phase_section.hide()
        self._clear_phases_ui()

    def load_task(self, task: Task) -> None:
        # Stop any pending auto-save timer
        self._autosave_timer.stop()

        # Auto-save current task if dirty and switching to a DIFFERENT task.
        # _is_dirty is reset to False inside _on_save() BEFORE emitting
        # save_requested, so any re-entrant load_task() triggered by the
        # subsequent refresh will see _is_dirty=False and skip this block.
        if self._is_dirty and self._task and self._task.id != task.id:
            self._on_save()

        # Populate fields without triggering dirty tracking
        self._loading = True
        try:
            self._task = task
            self._is_dirty = False
            self._update_header()

            self._title.setText(task.title)
            self._desc.setPlainText(task.description or '')
            set_combo_by_data(self._status, task.status)
            set_combo_by_data(self._priority, task.priority)

            if task.due_date:
                self._due_date.setDate(QDate.fromString(task.due_date, 'yyyy-MM-dd'))
            else:
                self._due_date.setDate(NO_DATE)

            if task.due_time:
                self._time_str = task.due_time[:5]
                self._apply_time_btn_selected()
            else:
                self._clear_time()

            self._auto_complete.setChecked(task.auto_complete_with_children)

            # Recurrence
            self._is_recurring.setChecked(task.is_recurring)
            self._recurrence_rule.setEnabled(task.is_recurring)
            if task.recurrence_rule:
                set_combo_by_data(self._recurrence_rule, task.recurrence_rule)
            else:
                set_combo_by_data(self._recurrence_rule, 'daily')

            # Reminder — load from repo if available
            self._load_reminder(task.id)

        finally:
            self._loading = False

        self._save_btn.setEnabled(True)
        self._add_child_btn.setVisible(task.parent_id is None)

        # Load phases (outside _loading block; phase changes use their own
        # direct repo calls and don't go through the dirty mechanism)
        self._reload_phases()

    def _load_reminder(self, task_id: str) -> None:
        """Pre-populate the reminder section from the DB, or reset to defaults."""
        default_dt = QDateTime(QDate.currentDate().addDays(1), QTime(9, 0))

        if not self._reminder_repo:
            self._remind_enabled.setChecked(False)
            self._remind_dt.setEnabled(False)
            self._remind_dt.setDateTime(default_dt)
            return

        try:
            existing = self._reminder_repo.get_by_task_id(task_id)
        except Exception as exc:
            logger.warning('[right_panel] Failed to load reminder for task %s: %s', task_id, exc)
            existing = None

        if existing and existing.remind_at and not existing.is_fired:
            dt_str = existing.remind_at.replace('T', ' ')[:16]  # 'YYYY-MM-DD HH:MM'
            dt = QDateTime.fromString(dt_str, 'yyyy-MM-dd HH:mm')
            if not dt.isValid():
                dt = default_dt
            self._remind_dt.setDateTime(dt)
            self._remind_enabled.setChecked(True)
            self._remind_dt.setEnabled(True)
        else:
            self._remind_enabled.setChecked(False)
            self._remind_dt.setEnabled(False)
            self._remind_dt.setDateTime(default_dt)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _clear_due_date(self) -> None:
        self._due_date.setDate(NO_DATE)

    def _on_add_child(self) -> None:
        if self._task:
            self.add_child_requested.emit(self._task.id)

    # ── Phase helpers ─────────────────────────────────────────────────

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

    # ------------------------------------------------------------------
    # Save
    # ------------------------------------------------------------------

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
        self._task.due_time = self._time_str  # None or 'HH:MM'

        # Recurrence
        self._task.is_recurring = self._is_recurring.isChecked()
        self._task.recurrence_rule = (
            self._recurrence_rule.currentData()
            if self._task.is_recurring
            else None
        )

        # Reset dirty state BEFORE emitting to prevent re-entrant saves
        self._is_dirty = False
        self._autosave_timer.stop()
        self._update_header()

        # Reminder: upsert or delete inline (task already exists in DB)
        self._save_reminder(self._task.id)

        self.save_requested.emit(self._task)

    def _save_reminder(self, task_id: str) -> None:
        """Create, replace, or delete the reminder for the given task.

        Strategy (simple upsert via delete-then-insert):
          - Reminder enabled  → delete existing (if any) + create new with is_fired=0
          - Reminder disabled → delete existing (if any)

        Any error is logged but does not block the task save.
        """
        if not self._reminder_repo:
            return
        try:
            if self._remind_enabled.isChecked():
                remind_at = self._remind_dt.dateTime().toString('yyyy-MM-ddTHH:mm:ss')
                self._reminder_repo.delete_by_task_id(task_id)
                new_r = TaskReminder(
                    id='',
                    task_id=task_id,
                    mode='at',
                    remind_at=remind_at,
                    is_fired=False,
                )
                self._reminder_repo.create(new_r)
                logger.info('[right_panel] Reminder set for task %s → %s', task_id, remind_at)
            else:
                self._reminder_repo.delete_by_task_id(task_id)
                logger.debug('[right_panel] Reminder removed for task %s', task_id)
        except Exception as exc:
            logger.error('[right_panel] Failed to save reminder for task %s: %s', task_id, exc)
