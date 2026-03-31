"""
Left panel: view switcher with count badges.

Views:
    今日 / 即將到期 / 逾期 / 無期限 / 全部任務 / 已完成 / 搜尋

Patch 12:
  - Replaced VIEW_3DAYS / VIEW_DONE with the full set of view constants
    from src.core.view_filter.
  - update_counts(counts) updates button text to show per-view task counts.
  - Overdue button highlights in amber when count > 0.
"""
from __future__ import annotations

from typing import Dict

from PySide6.QtWidgets import QWidget, QVBoxLayout, QPushButton, QLabel, QFrame
from PySide6.QtCore import Signal, Qt

# Re-export all view constants so existing callers that import from this module
# continue to work without change.
from src.core.view_filter import (
    VIEW_TODAY, VIEW_UPCOMING, VIEW_OVERDUE, VIEW_NO_DATE,
    VIEW_ALL, VIEW_COMPLETED, VIEW_SEARCH,
)

# Backward-compat aliases removed in Patch 12:
#   VIEW_3DAYS → VIEW_UPCOMING (different semantics; alias omitted intentionally)
#   VIEW_DONE  → VIEW_COMPLETED
VIEW_DONE = VIEW_COMPLETED   # kept so any indirect reference doesn't hard-crash

VIEWS = [
    (VIEW_TODAY,     '今日'),
    (VIEW_UPCOMING,  '即將到期'),
    (VIEW_OVERDUE,   '逾期'),
    (VIEW_NO_DATE,   '無期限'),
    (VIEW_ALL,       '全部任務'),
    (VIEW_COMPLETED, '已完成'),
    (VIEW_SEARCH,    '搜尋'),
]


class LeftPanel(QWidget):
    view_changed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(150)
        self._buttons: Dict[str, QPushButton] = {}
        self._base_labels: Dict[str, str] = {vid: lbl for vid, lbl in VIEWS}
        self._current_view = VIEW_TODAY
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 16, 8, 16)
        layout.setSpacing(2)

        # App brand
        brand = QLabel('FloatDesk')
        brand.setAlignment(Qt.AlignmentFlag.AlignCenter)
        brand.setStyleSheet(
            'font-size: 14px; font-weight: 800; color: #4F46E5; '
            'letter-spacing: 0.5px; margin-bottom: 16px;'
        )
        layout.addWidget(brand)

        # Divider
        div = QFrame()
        div.setFrameShape(QFrame.Shape.HLine)
        div.setStyleSheet('color: #E2E8F0; margin-bottom: 8px;')
        layout.addWidget(div)

        for view_id, label in VIEWS:
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.setFixedHeight(36)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda checked, v=view_id: self._on_view_click(v))
            layout.addWidget(btn)
            self._buttons[view_id] = btn

        layout.addStretch()

        # Version hint
        ver = QLabel('v0.1')
        ver.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ver.setStyleSheet('color: #CBD5E1; font-size: 11px;')
        layout.addWidget(ver)

        self._buttons[VIEW_TODAY].setChecked(True)
        self._update_styles()

    # ── Button styling ────────────────────────────────────────────────────────

    def _btn_style(self, active: bool, overdue_alert: bool = False) -> str:
        """Return QSS for a nav button.

        overdue_alert=True adds an amber accent to draw attention to overdue tasks.
        """
        if active:
            return (
                'QPushButton {'
                '  background-color: #4F46E5;'
                '  color: #FFFFFF;'
                '  font-weight: 700;'
                '  border: none;'
                '  border-radius: 8px;'
                '  padding: 0 12px;'
                '  text-align: left;'
                '}'
            )
        if overdue_alert:
            return (
                'QPushButton {'
                '  background-color: #FEF3C7;'
                '  color: #B45309;'
                '  border: none;'
                '  border-radius: 8px;'
                '  padding: 0 12px;'
                '  text-align: left;'
                '  font-weight: 600;'
                '}'
                'QPushButton:hover {'
                '  background-color: #FDE68A;'
                '  color: #92400E;'
                '}'
            )
        return (
            'QPushButton {'
            '  background-color: transparent;'
            '  color: #64748B;'
            '  border: none;'
            '  border-radius: 8px;'
            '  padding: 0 12px;'
            '  text-align: left;'
            '  font-weight: 500;'
            '}'
            'QPushButton:hover {'
            '  background-color: #EEF2FF;'
            '  color: #4F46E5;'
            '}'
        )

    def _on_view_click(self, view_id: str) -> None:
        self._current_view = view_id
        self._update_styles()
        self.view_changed.emit(view_id)

    def _update_styles(self, overdue_count: int = 0) -> None:
        for view_id, btn in self._buttons.items():
            active = (view_id == self._current_view)
            alert = (view_id == VIEW_OVERDUE and overdue_count > 0 and not active)
            btn.setChecked(active)
            btn.setStyleSheet(self._btn_style(active, overdue_alert=alert))

    # ── Public API ────────────────────────────────────────────────────────────

    def update_counts(self, counts: Dict[str, int]) -> None:
        """Update button labels with per-view task counts.

        Called from ConsoleWindow.refresh() with counts from count_views().
        SEARCH button is never annotated with a count.
        The OVERDUE button receives an amber highlight when its count > 0.
        """
        overdue_count = counts.get(VIEW_OVERDUE, 0)
        for view_id, base_label in self._base_labels.items():
            btn = self._buttons[view_id]
            if view_id != VIEW_SEARCH:
                n = counts.get(view_id, 0)
                btn.setText(f'{base_label}  {n}' if n > 0 else base_label)
        self._update_styles(overdue_count=overdue_count)

    def set_view(self, view_id: str) -> None:
        self._current_view = view_id
        self._update_styles()
