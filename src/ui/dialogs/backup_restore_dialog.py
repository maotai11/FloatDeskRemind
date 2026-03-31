"""
BackupRestoreDialog: Backup listing, manual backup, and deferred restore.

Layout:
  ┌─────────────────────────────────────┐
  │ 備份列表              [立即備份]     │
  ├─────────────────────────────────────┤
  │ 備份時間     類型   檔名            │
  │ ...                                 │
  ├─────────────────────────────────────┤
  │ [還原選取備份]         [關閉]        │
  └─────────────────────────────────────┘

Signal flow:
  - Manual backup  : calls backup_service.manual_backup() directly
  - Restore        : emits restore_confirmed(backup_path) → AppController
                     AppController calls request_restore() then QApplication.quit()
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from src.core.backup import BackupError
from src.services.backup_service import BackupService


class BackupRestoreDialog(QDialog):
    """Backup listing + manual backup + deferred-restore trigger.

    restore_confirmed(backup_path) is emitted when the user confirms a restore.
    The caller (AppController) is responsible for calling request_restore() and
    quitting the application.
    """

    restore_confirmed = Signal(Path)  # backup_path chosen by the user

    def __init__(self, backup_service: BackupService, parent: QWidget = None) -> None:
        super().__init__(parent)
        self._backup_service = backup_service
        self._backups = []   # List[BackupInfo], parallel to table rows

        self.setWindowTitle('備份與還原')
        self.setMinimumSize(680, 420)
        self.resize(720, 460)
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

        # ---- Header: label + manual backup button ----
        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)

        title_lbl = QLabel('備份列表')
        title_lbl.setStyleSheet('font-size: 14px; font-weight: bold;')
        header.addWidget(title_lbl)

        header.addStretch()

        self._manual_btn = QPushButton('立即備份')
        self._manual_btn.setFixedWidth(100)
        self._manual_btn.setToolTip('建立一份手動備份（不計入自動備份排程）')
        self._manual_btn.clicked.connect(self._on_manual_backup)
        header.addWidget(self._manual_btn)

        root.addLayout(header)

        # ---- Backup table ----
        self._table = QTableWidget(0, 3)
        self._table.setHorizontalHeaderLabels(['備份時間', '類型', '檔名'])
        hdr = self._table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self._table.verticalHeader().hide()
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.setAlternatingRowColors(True)
        self._table.setShowGrid(False)
        self._table.itemSelectionChanged.connect(self._on_selection_changed)
        root.addWidget(self._table)

        # ---- Status label (success / error feedback) ----
        self._status_lbl = QLabel('')
        self._status_lbl.setStyleSheet('color: #666; font-size: 12px;')
        self._status_lbl.setWordWrap(True)
        self._status_lbl.setFixedHeight(32)
        root.addWidget(self._status_lbl)

        # ---- Footer: restore + close ----
        footer = QHBoxLayout()
        footer.setContentsMargins(0, 0, 0, 0)

        self._restore_btn = QPushButton('還原選取備份')
        self._restore_btn.setEnabled(False)
        self._restore_btn.setToolTip('以選取的備份覆蓋目前資料庫（將重新啟動應用程式）')
        self._restore_btn.clicked.connect(self._on_restore)
        footer.addWidget(self._restore_btn)

        footer.addStretch()

        close_btn = QPushButton('關閉')
        close_btn.setFixedWidth(80)
        close_btn.clicked.connect(self.close)
        footer.addWidget(close_btn)

        root.addLayout(footer)

    # ------------------------------------------------------------------
    # Data refresh
    # ------------------------------------------------------------------

    def _refresh(self) -> None:
        """Reload backup list from BackupService and repopulate table."""
        self._backups = self._backup_service.list_backups()
        self._table.setRowCount(0)

        for info in self._backups:
            row = self._table.rowCount()
            self._table.insertRow(row)

            time_str = info.created_at.strftime('%Y-%m-%d  %H:%M:%S')
            label_str = '手動' if info.label == 'manual' else '自動'

            time_item = QTableWidgetItem(time_str)
            time_item.setTextAlignment(
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft
            )
            label_item = QTableWidgetItem(label_str)
            label_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            name_item = QTableWidgetItem(info.path.name)
            name_item.setToolTip(str(info.path))

            self._table.setItem(row, 0, time_item)
            self._table.setItem(row, 1, label_item)
            self._table.setItem(row, 2, name_item)

        self._table.resizeRowsToContents()
        self._restore_btn.setEnabled(False)
        self._status_lbl.setText(
            f'共 {len(self._backups)} 份備份'
            if self._backups else '尚無備份'
        )

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    def _on_selection_changed(self) -> None:
        self._restore_btn.setEnabled(self._table.currentRow() >= 0)

    def _on_manual_backup(self) -> None:
        """Create a manual backup and refresh the list."""
        self._manual_btn.setEnabled(False)
        self._status_lbl.setText('備份中…')
        try:
            path = self._backup_service.manual_backup()
            self._refresh()
            self._status_lbl.setText(f'備份成功：{path.name}')
            self._status_lbl.setStyleSheet('color: #2a9d2a; font-size: 12px;')
        except BackupError as exc:
            self._status_lbl.setText(f'備份失敗：{exc}')
            self._status_lbl.setStyleSheet('color: #c0392b; font-size: 12px;')
            QMessageBox.critical(
                self,
                '備份失敗',
                f'建立備份時發生錯誤：\n\n{exc}',
            )
        finally:
            self._manual_btn.setEnabled(True)

    def _on_restore(self) -> None:
        """Confirm and emit restore_confirmed signal."""
        row = self._table.currentRow()
        if row < 0 or row >= len(self._backups):
            return

        info = self._backups[row]
        time_str = info.created_at.strftime('%Y-%m-%d %H:%M:%S')
        label_str = '手動' if info.label == 'manual' else '自動'

        reply = QMessageBox.question(
            self,
            '確認還原',
            f'此操作將覆蓋目前資料，且需重新啟動，是否繼續？\n\n'
            f'備份類型：{label_str}\n'
            f'備份時間：{time_str}\n'
            f'備份檔名：{info.path.name}',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.restore_confirmed.emit(info.path)
