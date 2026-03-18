"""
Scenario E: confirm delete parent dialog.
- children <= 20: list each title
- children > 20: show total count only
"""
from __future__ import annotations
from typing import List

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QLabel, QHBoxLayout, QPushButton, QTextEdit
)
from PySide6.QtCore import Qt

from src.data.models import Task


class ConfirmDeleteDialog(QDialog):
    """
    Returns:
        - accepted + cascade=True  → delete parent and all children
        - accepted + cascade=False → delete parent, unparent children
        - rejected → cancel
    """
    def __init__(self, parent_task: Task, children: List[Task], parent=None):
        super().__init__(parent)
        self.setWindowTitle('刪除任務確認')
        self.setModal(True)
        self.setMinimumWidth(380)
        self.cascade: bool = True
        self._build_ui(parent_task, children)

    def _build_ui(self, parent_task: Task, children: List[Task]) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        header = QLabel(f'確定刪除「{parent_task.title}」？')
        header.setStyleSheet('font-weight: bold; font-size: 14px;')
        layout.addWidget(header)

        if children:
            if len(children) <= 20:
                detail_text = '此任務包含以下子任務：\n\n'
                detail_text += '\n'.join(f'  • {c.title}' for c in children)
            else:
                detail_text = f'此任務包含 {len(children)} 個子任務。'

            detail = QTextEdit()
            detail.setPlainText(detail_text)
            detail.setReadOnly(True)
            detail.setFixedHeight(min(120, 40 + len(children) * 20))
            layout.addWidget(detail)

            cascade_btn = QPushButton('刪除父任務及所有子任務')
            cascade_btn.setProperty('class', 'danger')
            cascade_btn.clicked.connect(self._on_cascade_delete)
            layout.addWidget(cascade_btn)

            unparent_btn = QPushButton('僅刪除父任務，保留子任務（解除關聯）')
            unparent_btn.setProperty('class', 'secondary')
            unparent_btn.clicked.connect(self._on_unparent_delete)
            layout.addWidget(unparent_btn)
        else:
            note = QLabel('此任務沒有子任務。刪除後無法復原。')
            note.setWordWrap(True)
            layout.addWidget(note)

            confirm_btn = QPushButton('確認刪除')
            confirm_btn.setProperty('class', 'danger')
            confirm_btn.clicked.connect(self._on_cascade_delete)
            layout.addWidget(confirm_btn)

        cancel_btn = QPushButton('取消')
        cancel_btn.setProperty('class', 'secondary')
        cancel_btn.clicked.connect(self.reject)
        layout.addWidget(cancel_btn)

    def _on_cascade_delete(self) -> None:
        self.cascade = True
        self.accept()

    def _on_unparent_delete(self) -> None:
        self.cascade = False
        self.accept()
