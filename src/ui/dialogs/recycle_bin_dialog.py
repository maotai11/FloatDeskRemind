"""
RecycleBinDialog: view, restore, and permanently delete soft-deleted tasks.

Layout:
  ┌────────────────────────────────────┐
  │ 回收桶                    [共 N 筆] │
  ├────────────────────────────────────┤
  │ 標題           刪除時間     類型    │  ← table (hidden when empty)
  │ …                                  │
  ├── OR ──────────────────────────────┤
  │      回收桶目前為空                 │  ← empty-state label
  ├────────────────────────────────────┤
  │ [還原選取]  [永久刪除]     [關閉]  │
  └────────────────────────────────────┘

Signal flow:
  Dialog calls task_service directly for both operations.
  After each successful operation the dialog:
    1. Refreshes its own table
    2. Emits tasks_changed → AppController.task_changed → main UI refresh
  Errors are shown via QMessageBox.critical (never silent).
"""
from __future__ import annotations

from typing import List

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from src.data.models import Task
from src.services.task_service import TaskService


def _fmt_deleted_at(raw: str) -> str:
    """Format ISO deleted_at string to 'YYYY-MM-DD HH:MM'.

    Handles both 'T' and ' ' separator variants gracefully.
    Returns the raw string unchanged on any parse error.
    """
    if not raw:
        return ''
    try:
        normalized = raw.replace('T', ' ')
        return normalized[:16]   # 'YYYY-MM-DD HH:MM'
    except Exception:
        return raw


class RecycleBinDialog(QDialog):
    """View, restore, and permanently delete soft-deleted tasks.

    tasks_changed is emitted after any successful restore or permanent delete.
    Connect this signal to AppController.task_changed to keep the main UI in sync.
    """

    tasks_changed = Signal()  # emitted after any successful modify operation

    def __init__(self, task_service: TaskService, parent: QWidget = None) -> None:
        super().__init__(parent)
        self._task_service = task_service
        self._tasks: List[Task] = []

        self.setWindowTitle('回收桶')
        self.setMinimumSize(660, 420)
        self.resize(700, 460)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)

        self._build_ui()
        self._refresh()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setSpacing(12)
        root.setContentsMargins(16, 16, 16, 16)

        # ---- Header: title + count label ----
        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)

        title_lbl = QLabel('回收桶')
        title_lbl.setStyleSheet('font-size: 14px; font-weight: bold;')
        header.addWidget(title_lbl)

        header.addStretch()

        self._count_lbl = QLabel('')
        self._count_lbl.setStyleSheet('color: #888; font-size: 12px;')
        header.addWidget(self._count_lbl)

        root.addLayout(header)

        # ---- Stacked: table / empty-state ----
        self._stack = QStackedWidget()

        # Page 0: task table
        self._table = QTableWidget(0, 3)
        self._table.setHorizontalHeaderLabels(['標題', '刪除時間', '類型'])
        hdr = self._table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self._table.verticalHeader().hide()
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.setAlternatingRowColors(True)
        self._table.setShowGrid(False)
        self._table.itemSelectionChanged.connect(self._on_selection_changed)
        self._stack.addWidget(self._table)

        # Page 1: empty state
        empty_widget = QWidget()
        empty_layout = QVBoxLayout(empty_widget)
        empty_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_lbl = QLabel('回收桶目前為空')
        empty_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_lbl.setStyleSheet('color: #aaa; font-size: 14px;')
        empty_layout.addWidget(empty_lbl)
        self._stack.addWidget(empty_widget)

        root.addWidget(self._stack)

        # ---- Status label ----
        self._status_lbl = QLabel('')
        self._status_lbl.setStyleSheet('color: #666; font-size: 12px;')
        self._status_lbl.setWordWrap(True)
        self._status_lbl.setFixedHeight(28)
        root.addWidget(self._status_lbl)

        # ---- Footer: restore + delete + close ----
        footer = QHBoxLayout()
        footer.setContentsMargins(0, 0, 0, 0)

        self._restore_btn = QPushButton('還原選取')
        self._restore_btn.setEnabled(False)
        self._restore_btn.setToolTip('將選取的任務還原為待辦狀態')
        self._restore_btn.clicked.connect(self._on_restore)
        footer.addWidget(self._restore_btn)

        self._perm_delete_btn = QPushButton('永久刪除')
        self._perm_delete_btn.setEnabled(False)
        self._perm_delete_btn.setToolTip('從資料庫永久移除此任務（不可復原）')
        self._perm_delete_btn.setStyleSheet('color: #c0392b;')
        self._perm_delete_btn.clicked.connect(self._on_permanently_delete)
        footer.addWidget(self._perm_delete_btn)

        footer.addStretch()

        close_btn = QPushButton('關閉')
        close_btn.setFixedWidth(80)
        close_btn.clicked.connect(self.close)
        footer.addWidget(close_btn)

        root.addLayout(footer)

    # ------------------------------------------------------------------
    # Data
    # ------------------------------------------------------------------

    def _refresh(self) -> None:
        """Reload deleted tasks from task_service and repopulate the table."""
        self._tasks = self._task_service.get_recycle_bin()
        self._table.setRowCount(0)

        if not self._tasks:
            self._stack.setCurrentIndex(1)   # show empty state
            self._count_lbl.setText('共 0 筆')
            self._restore_btn.setEnabled(False)
            self._perm_delete_btn.setEnabled(False)
            return

        self._stack.setCurrentIndex(0)   # show table
        self._count_lbl.setText(f'共 {len(self._tasks)} 筆')

        for task in self._tasks:
            row = self._table.rowCount()
            self._table.insertRow(row)

            title_item = QTableWidgetItem(task.title)
            title_item.setToolTip(task.description or task.title)

            deleted_str = _fmt_deleted_at(task.deleted_at or '')
            time_item = QTableWidgetItem(deleted_str)
            time_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

            kind = '子任務' if task.parent_id else '父任務'
            kind_item = QTableWidgetItem(kind)
            kind_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

            self._table.setItem(row, 0, title_item)
            self._table.setItem(row, 1, time_item)
            self._table.setItem(row, 2, kind_item)

        self._table.resizeRowsToContents()
        self._restore_btn.setEnabled(False)
        self._perm_delete_btn.setEnabled(False)

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    def _on_selection_changed(self) -> None:
        has = self._table.currentRow() >= 0
        self._restore_btn.setEnabled(has)
        self._perm_delete_btn.setEnabled(has)

    def _current_task(self) -> Task | None:
        row = self._table.currentRow()
        if row < 0 or row >= len(self._tasks):
            return None
        return self._tasks[row]

    def _on_restore(self) -> None:
        task = self._current_task()
        if task is None:
            return
        try:
            self._task_service.restore_from_trash(task.id)
            self.tasks_changed.emit()
            self._refresh()
            self._set_status(f'已還原：{task.title}', ok=True)
        except Exception as exc:
            QMessageBox.critical(
                self,
                '還原失敗',
                f'還原任務時發生錯誤：\n\n{exc}',
            )

    def _on_permanently_delete(self) -> None:
        task = self._current_task()
        if task is None:
            return

        reply = QMessageBox.question(
            self,
            '確認永久刪除',
            f'此操作不可復原，是否繼續？\n\n任務：{task.title}',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        try:
            self._task_service.permanently_delete(task.id)
            self.tasks_changed.emit()
            self._refresh()
            self._set_status(f'已永久刪除：{task.title}', ok=True)
        except Exception as exc:
            QMessageBox.critical(
                self,
                '永久刪除失敗',
                f'永久刪除任務時發生錯誤：\n\n{exc}',
            )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _set_status(self, text: str, ok: bool = True) -> None:
        colour = '#2a9d2a' if ok else '#c0392b'
        self._status_lbl.setText(text)
        self._status_lbl.setStyleSheet(f'color: {colour}; font-size: 12px;')
