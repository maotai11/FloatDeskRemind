"""
Scenario B: confirm dialog when manually completing a parent with pending children.
"""
from __future__ import annotations
from typing import List

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QLabel, QHBoxLayout, QPushButton
)
from PySide6.QtCore import Qt

from src.data.models import Task


class ConfirmCompleteDialog(QDialog):
    """
    Returns:
        - accepted + include_children=True  → complete parent and all children
        - accepted + include_children=False → complete parent only
        - rejected → cancel
    """
    def __init__(self, parent_task: Task, pending_children: List[Task], parent=None):
        super().__init__(parent)
        self.setWindowTitle('完成任務確認')
        self.setModal(True)
        self.setMinimumWidth(360)
        self.include_children: bool = False
        self._build_ui(parent_task, pending_children)

    def _build_ui(self, parent_task: Task, children: List[Task]) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(16)

        msg = QLabel(
            f'「{parent_task.title}」還有 {len(children)} 個未完成的子任務。\n\n'
            '請選擇如何處理：'
        )
        msg.setWordWrap(True)
        layout.addWidget(msg)

        btn_with = QPushButton('完成父任務並完成所有子任務')
        btn_with.clicked.connect(self._on_complete_all)
        layout.addWidget(btn_with)

        btn_without = QPushButton('僅完成父任務，保留子任務狀態')
        btn_without.setProperty('class', 'secondary')
        btn_without.clicked.connect(self._on_complete_parent_only)
        layout.addWidget(btn_without)

        cancel_btn = QPushButton('取消')
        cancel_btn.setProperty('class', 'secondary')
        cancel_btn.clicked.connect(self.reject)
        layout.addWidget(cancel_btn)

    def _on_complete_all(self) -> None:
        self.include_children = True
        self.accept()

    def _on_complete_parent_only(self) -> None:
        self.include_children = False
        self.accept()
