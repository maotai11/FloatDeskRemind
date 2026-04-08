"""
ToastNotification: reliable on-screen notification widget.

Windows 10/11 suppresses QSystemTrayIcon.showMessage() under Focus Assist /
Do Not Disturb. This widget is a custom always-on-top QWidget that appears
reliably regardless of Windows notification settings.

Design:
  - Appears at the bottom-right corner of the primary screen
  - Auto-closes after AUTO_CLOSE_MS (6 s) with a draining progress bar
  - Has a dismiss (×) button
  - Stacks: multiple toasts offset upward so they don't overlap
  - No taskbar entry (Tool window flag)
"""
from __future__ import annotations

from typing import List

from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QApplication
from PySide6.QtCore import Qt, QTimer, QRectF
from PySide6.QtGui import QPainter, QColor, QBrush, QPen

AUTO_CLOSE_MS = 6_000   # ms before auto-dismiss
_SPACING      = 10      # px gap between stacked toasts
_MARGIN_RIGHT = 18      # px from screen right
_MARGIN_BOT   = 48      # px from taskbar

# Track all active toasts for stacking
_active: List['ToastNotification'] = []


def _restack() -> None:
    """Reposition all active toasts so they stack without overlapping."""
    screen = QApplication.primaryScreen()
    if not screen:
        return
    rect = screen.availableGeometry()
    y = rect.bottom() - _MARGIN_BOT
    for t in reversed(_active):
        t.adjustSize()
        x = rect.right() - t.width() - _MARGIN_RIGHT
        t.move(x, y - t.height())
        y -= t.height() + _SPACING


class ToastNotification(QWidget):
    """A transient, always-on-top notification card."""

    def __init__(self, title: str, message: str, parent=None):
        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool |
            Qt.WindowType.WindowDoesNotAcceptFocus,
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setFixedWidth(300)

        self._progress = 1.0   # 1.0 → 0.0 over AUTO_CLOSE_MS
        self._build_ui(title, message)

        # Auto-close
        self._close_timer = QTimer(self)
        self._close_timer.setSingleShot(True)
        self._close_timer.setInterval(AUTO_CLOSE_MS)
        self._close_timer.timeout.connect(self._dismiss)

        # Progress drain (updates every 100ms)
        self._tick_timer = QTimer(self)
        self._tick_timer.setInterval(100)
        self._tick_timer.timeout.connect(self._tick)

        _active.append(self)
        _restack()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _build_ui(self, title: str, message: str) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # ── Header ────────────────────────────────────────────────────
        header = QWidget()
        header.setFixedHeight(34)
        header.setStyleSheet(
            'background-color: #4F46E5;'
            'border-radius: 10px 10px 0 0;'
        )
        hl = QHBoxLayout(header)
        hl.setContentsMargins(12, 0, 8, 0)
        hl.setSpacing(6)

        bell = QLabel('⏰')
        bell.setStyleSheet('color: white; font-size: 13px; background: transparent;')
        hl.addWidget(bell)

        app_lbl = QLabel('FloatDesk Remind')
        app_lbl.setStyleSheet(
            'color: white; font-weight: 700; font-size: 12px; background: transparent;'
        )
        hl.addWidget(app_lbl)
        hl.addStretch()

        close_btn = QPushButton('×')
        close_btn.setFixedSize(22, 22)
        close_btn.setStyleSheet(
            'QPushButton {'
            '  background: rgba(255,255,255,0.15); color: white;'
            '  border: none; border-radius: 11px; font-size: 14px;'
            '}'
            'QPushButton:hover { background: rgba(255,255,255,0.3); }'
        )
        close_btn.clicked.connect(self._dismiss)
        hl.addWidget(close_btn)
        outer.addWidget(header)

        # ── Body ──────────────────────────────────────────────────────
        body = QWidget()
        body.setStyleSheet(
            'background-color: #FFFFFF;'
            'border-radius: 0 0 10px 10px;'
            'border: 1px solid #E2E8F0;'
            'border-top: none;'
        )
        bl = QVBoxLayout(body)
        bl.setContentsMargins(14, 10, 14, 12)
        bl.setSpacing(4)

        title_lbl = QLabel(title)
        title_lbl.setWordWrap(True)
        title_lbl.setStyleSheet(
            'color: #1E293B; font-weight: 700; font-size: 13px; background: transparent;'
        )
        bl.addWidget(title_lbl)

        msg_lbl = QLabel(message)
        msg_lbl.setWordWrap(True)
        msg_lbl.setStyleSheet(
            'color: #64748B; font-size: 12px; background: transparent;'
        )
        bl.addWidget(msg_lbl)

        outer.addWidget(body)

        # ── Progress bar slot ─────────────────────────────────────────
        # Drawn in paintEvent via _progress (0.0–1.0)

    def paintEvent(self, event) -> None:  # type: ignore[override]
        super().paintEvent(event)
        if self._progress <= 0:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        # Draw thin indigo drain bar at the bottom of the widget
        bar_h = 3
        bar_w = int(self.width() * self._progress)
        p.setBrush(QBrush(QColor('#4F46E5')))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(QRectF(0, self.height() - bar_h, bar_w, bar_h), 2, 2)

    def showEvent(self, event) -> None:  # type: ignore[override]
        super().showEvent(event)
        self._close_timer.start()
        self._tick_timer.start()

    def closeEvent(self, event) -> None:  # type: ignore[override]
        self._close_timer.stop()
        self._tick_timer.stop()
        if self in _active:
            _active.remove(self)
        _restack()
        super().closeEvent(event)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _tick(self) -> None:
        self._progress = max(0.0, self._progress - 100 / AUTO_CLOSE_MS)
        self.update()

    def _dismiss(self) -> None:
        self.close()


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def show_toast(title: str, message: str) -> ToastNotification:
    """Create, position, and show a ToastNotification. Returns the widget."""
    t = ToastNotification(title, message)
    t.show()
    t.raise_()
    return t
