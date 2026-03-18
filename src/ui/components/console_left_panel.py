"""
Left panel: view switcher (Today / Next 3 Days / All / Done / Search).
"""
from __future__ import annotations
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QPushButton, QLabel, QButtonGroup, QSizePolicy
)
from PySide6.QtCore import Signal, Qt


VIEW_TODAY = 'today'
VIEW_3DAYS = '3days'
VIEW_ALL = 'all'
VIEW_DONE = 'done'
VIEW_SEARCH = 'search'

VIEWS = [
    (VIEW_TODAY, '今日'),
    (VIEW_3DAYS, '近三日'),
    (VIEW_ALL, '全部'),
    (VIEW_DONE, '已完成'),
    (VIEW_SEARCH, '搜尋'),
]


class LeftPanel(QWidget):
    view_changed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(140)
        self._buttons: dict[str, QPushButton] = {}
        self._current_view = VIEW_TODAY
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 16, 8, 8)
        layout.setSpacing(4)

        title = QLabel('FloatDesk')
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet('font-size: 14px; font-weight: bold; color: #1976D2; margin-bottom: 12px;')
        layout.addWidget(title)

        for view_id, label in VIEWS:
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.setStyleSheet(self._btn_style(False))
            btn.clicked.connect(lambda checked, v=view_id: self._on_view_click(v))
            layout.addWidget(btn)
            self._buttons[view_id] = btn

        layout.addStretch()
        self._buttons[VIEW_TODAY].setChecked(True)
        self._update_styles()

    def _btn_style(self, active: bool) -> str:
        if active:
            return (
                'QPushButton { background-color: #E3F2FD; color: #1976D2; '
                'font-weight: bold; border: none; border-radius: 6px; '
                'padding: 8px 12px; text-align: left; }'
            )
        return (
            'QPushButton { background-color: transparent; color: #1A1A1A; '
            'border: none; border-radius: 6px; padding: 8px 12px; text-align: left; }'
            'QPushButton:hover { background-color: #F5F5F5; }'
        )

    def _on_view_click(self, view_id: str) -> None:
        self._current_view = view_id
        self._update_styles()
        self.view_changed.emit(view_id)

    def _update_styles(self) -> None:
        for view_id, btn in self._buttons.items():
            btn.setChecked(view_id == self._current_view)
            btn.setStyleSheet(self._btn_style(view_id == self._current_view))

    def set_view(self, view_id: str) -> None:
        self._current_view = view_id
        self._update_styles()
