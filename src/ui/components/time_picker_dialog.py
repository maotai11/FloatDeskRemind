"""
TimePickerDialog: visual clock-face time picker.
Phase 1 = select hour, Phase 2 = select minute (5-min steps).
Click on the clock ring to pick, or use +/- buttons.
"""
from __future__ import annotations
import math

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QWidget, QDialogButtonBox
)
from PySide6.QtCore import Qt, QRectF, Signal
from PySide6.QtGui import (
    QPainter, QColor, QPen, QBrush, QFont
)
from src.ui.styles.theme import (
    ACCENT, ACCENT_LIGHT, BG_BASE, TEXT_PRIMARY, BORDER_LIGHT, BORDER_NORMAL
)


CLOCK_SIZE = 220          # px — clock face square
RADIUS_FACE = 100         # outer circle
RADIUS_NUM = 78           # where numbers are drawn

# Hoisted fonts — created once, reused every paintEvent
_FONT_NORMAL = QFont()
_FONT_NORMAL.setPointSize(10)
_FONT_BOLD = QFont()
_FONT_BOLD.setPointSize(10)
_FONT_BOLD.setBold(True)

# Hoisted paint colors — avoid QColor allocation per paintEvent
_COLOR_FACE_BG     = QColor(BG_BASE)
_COLOR_FACE_BORDER = QColor(BORDER_LIGHT)
_COLOR_ACCENT      = QColor(ACCENT)
_COLOR_TICK        = QColor(BORDER_NORMAL)
_COLOR_TEXT        = QColor(TEXT_PRIMARY)
_COLOR_WHITE       = QColor('#FFFFFF')

# Tab/button active/inactive styles
_STYLE_ACTIVE   = f'background:{ACCENT}; color:white; border:none; border-radius:6px; font-weight:600;'
_STYLE_INACTIVE = f'background:{ACCENT_LIGHT}; color:{ACCENT}; border:none; border-radius:6px;'


def _angle(index: int, total: int) -> float:
    """Clockwise angle in radians from 12 o'clock for step `index` of `total`."""
    return (index / total) * 2 * math.pi - math.pi / 2


def _xy(cx: float, cy: float, r: float, angle_rad: float):
    return cx + r * math.cos(angle_rad), cy + r * math.sin(angle_rad)


class ClockFace(QWidget):
    """Interactive clock-face widget."""
    value_changed = Signal(int)   # hour (1-12) or minute (0-55 step 5)

    PHASE_HOUR = 'hour'
    PHASE_MIN  = 'min'

    def __init__(self, hour: int = 12, minute: int = 0, parent=None):
        super().__init__(parent)
        self._hour = max(1, min(12, hour))
        self._minute = (minute // 5) * 5
        self._phase = self.PHASE_HOUR
        self.setFixedSize(CLOCK_SIZE, CLOCK_SIZE)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    # ── Public API ──────────────────────────────────────────────────────────
    @property
    def phase(self) -> str:
        return self._phase

    def set_phase(self, phase: str) -> None:
        self._phase = phase
        self.update()

    def set_hour(self, h: int) -> None:
        self._hour = max(1, min(12, h))
        self.update()

    def set_minute(self, m: int) -> None:
        self._minute = (m // 5) * 5 % 60
        self.update()

    @property
    def hour(self) -> int:
        return self._hour

    @property
    def minute(self) -> int:
        return self._minute

    # ── Paint ───────────────────────────────────────────────────────────────
    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        cx = cy = CLOCK_SIZE / 2

        # Background circle
        p.setBrush(QBrush(_COLOR_FACE_BG))
        p.setPen(QPen(_COLOR_FACE_BORDER, 2))
        p.drawEllipse(QRectF(cx - RADIUS_FACE, cy - RADIUS_FACE,
                             RADIUS_FACE * 2, RADIUS_FACE * 2))

        if self._phase == self.PHASE_HOUR:
            self._draw_hours(p, cx, cy)
        else:
            self._draw_minutes(p, cx, cy)

        # Center dot
        p.setBrush(QBrush(_COLOR_ACCENT))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(QRectF(cx - 4, cy - 4, 8, 8))

    def _draw_hours(self, p: QPainter, cx: float, cy: float) -> None:
        for h in range(1, 13):
            a = _angle(h, 12)
            x, y = _xy(cx, cy, RADIUS_NUM, a)
            selected = (h == self._hour)
            self._draw_number(p, x, y, str(h), selected)
            if selected:
                self._draw_hand(p, cx, cy, x, y)

    def _draw_minutes(self, p: QPainter, cx: float, cy: float) -> None:
        labels = {0: '0', 5: '5', 10: '10', 15: '15',
                  20: '20', 25: '25', 30: '30', 35: '35',
                  40: '40', 45: '45', 50: '50', 55: '55'}
        for step in range(12):
            m = step * 5
            a = _angle(step, 12)
            x, y = _xy(cx, cy, RADIUS_NUM, a)
            selected = (m == self._minute)
            self._draw_number(p, x, y, labels.get(m, ''), selected)
            if selected:
                self._draw_hand(p, cx, cy, x, y)

        # Minute tick marks (1-min resolution between labels)
        p.setPen(QPen(_COLOR_TICK, 1))
        for t in range(60):
            if t % 5 == 0:
                continue
            a = _angle(t, 60)
            tx, ty = _xy(cx, cy, RADIUS_FACE - 8, a)
            tx2, ty2 = _xy(cx, cy, RADIUS_FACE - 14, a)
            p.drawLine(int(tx), int(ty), int(tx2), int(ty2))

    def _draw_hand(self, p: QPainter, cx, cy, x, y) -> None:
        p.setPen(QPen(_COLOR_ACCENT, 2, Qt.PenStyle.SolidLine,
                       Qt.PenCapStyle.RoundCap))
        p.drawLine(int(cx), int(cy), int(x), int(y))
        p.setBrush(QBrush(_COLOR_ACCENT))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(QRectF(x - 14, y - 14, 28, 28))

    def _draw_number(self, p: QPainter, x: float, y: float,
                     text: str, selected: bool) -> None:
        if selected:
            p.setBrush(QBrush(_COLOR_ACCENT))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawEllipse(QRectF(x - 14, y - 14, 28, 28))
            p.setPen(QPen(_COLOR_WHITE))
        else:
            p.setPen(QPen(_COLOR_TEXT))

        p.setFont(_FONT_BOLD if selected else _FONT_NORMAL)

        rect = QRectF(x - 16, y - 14, 32, 28)
        p.drawText(rect, Qt.AlignmentFlag.AlignCenter, text)

    # ── Mouse ───────────────────────────────────────────────────────────────
    def mousePressEvent(self, event) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            return
        cx = cy = CLOCK_SIZE / 2
        mx, my = event.position().x(), event.position().y()
        dist = math.hypot(mx - cx, my - cy)

        # Only respond if clicking near the number ring
        if dist < RADIUS_FACE * 0.3 or dist > RADIUS_FACE * 1.1:
            return

        if self._phase == self.PHASE_HOUR:
            best_h, best_d = 12, float('inf')
            for h in range(1, 13):
                a = _angle(h, 12)
                nx, ny = _xy(cx, cy, RADIUS_NUM, a)
                d = math.hypot(mx - nx, my - ny)
                if d < best_d:
                    best_d, best_h = d, h
            self._hour = best_h
            self.value_changed.emit(self._hour)
        else:
            best_step, best_d = 0, float('inf')
            for step in range(12):
                a = _angle(step, 12)
                nx, ny = _xy(cx, cy, RADIUS_NUM, a)
                d = math.hypot(mx - nx, my - ny)
                if d < best_d:
                    best_d, best_step = d, step
            self._minute = best_step * 5
            self.value_changed.emit(self._minute)

        self.update()


class TimePickerDialog(QDialog):
    """Modal dialog wrapping ClockFace."""

    def __init__(self, hour: int = 9, minute: int = 0,
                 is_pm: bool = False, parent=None):
        super().__init__(parent)
        self.setWindowTitle('選擇時間')
        self.setModal(True)
        self.setFixedSize(300, 420)

        self._hour = max(1, min(12, hour))
        self._minute = (minute // 5) * 5
        self._is_pm = is_pm

        self._build_ui()
        self._update_display()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(12)

        # ── Time display ────────────────────────────────────────
        self._display = QLabel()
        self._display.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._display.setStyleSheet(
            f'font-size: 36px; font-weight: 700; color: {TEXT_PRIMARY}; '
            f'background: {ACCENT_LIGHT}; border-radius: 10px; padding: 10px 0;'
        )
        layout.addWidget(self._display)

        # ── Phase selector (Hour / Minute tabs) ─────────────────
        phase_row = QWidget()
        pr = QHBoxLayout(phase_row)
        pr.setContentsMargins(0, 0, 0, 0)
        pr.setSpacing(8)

        self._hour_tab = QPushButton('時')
        self._min_tab  = QPushButton('分')
        for btn in (self._hour_tab, self._min_tab):
            btn.setCheckable(True)
            btn.setFixedHeight(30)
            btn.setFixedWidth(56)
        self._hour_tab.setChecked(True)
        self._hour_tab.clicked.connect(lambda: self._set_phase(ClockFace.PHASE_HOUR))
        self._min_tab.clicked.connect(lambda: self._set_phase(ClockFace.PHASE_MIN))
        pr.addStretch()
        pr.addWidget(self._hour_tab)
        pr.addWidget(self._min_tab)
        pr.addStretch()

        # AM/PM
        self._am_btn = QPushButton('AM')
        self._pm_btn = QPushButton('PM')
        for btn in (self._am_btn, self._pm_btn):
            btn.setFixedSize(48, 30)
            btn.setCheckable(True)
        self._am_btn.setChecked(not self._is_pm)
        self._pm_btn.setChecked(self._is_pm)
        self._am_btn.clicked.connect(lambda: self._set_pm(False))
        self._pm_btn.clicked.connect(lambda: self._set_pm(True))
        pr.addWidget(self._am_btn)
        pr.addWidget(self._pm_btn)
        layout.addWidget(phase_row)

        # ── Clock face ──────────────────────────────────────────
        self._clock = ClockFace(self._hour, self._minute)
        self._clock.value_changed.connect(self._on_clock_value)

        clock_container = QWidget()
        cl = QHBoxLayout(clock_container)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.addStretch()
        cl.addWidget(self._clock)
        cl.addStretch()
        layout.addWidget(clock_container)

        # ── Buttons ─────────────────────────────────────────────
        btn_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel
        )
        btn_box.button(QDialogButtonBox.StandardButton.Ok).setText('確認')
        btn_box.button(QDialogButtonBox.StandardButton.Cancel).setText('取消')
        btn_box.accepted.connect(self.accept)
        btn_box.rejected.connect(self.reject)
        layout.addWidget(btn_box)

        self._update_tab_styles()

    # ── Internal ────────────────────────────────────────────────────────────
    def _update_display(self) -> None:
        m = f'{self._minute:02d}'
        suffix = 'PM' if self._is_pm else 'AM'
        if self._clock.phase == ClockFace.PHASE_HOUR:
            text = f'<span style="color:{ACCENT}">{self._hour:02d}</span>:{m} {suffix}'
        else:
            text = f'{self._hour:02d}:<span style="color:{ACCENT}">{m}</span> {suffix}'
        self._display.setText(text)

    def _update_tab_styles(self) -> None:
        if self._clock.phase == ClockFace.PHASE_HOUR:
            self._hour_tab.setStyleSheet(_STYLE_ACTIVE)
            self._min_tab.setStyleSheet(_STYLE_INACTIVE)
        else:
            self._hour_tab.setStyleSheet(_STYLE_INACTIVE)
            self._min_tab.setStyleSheet(_STYLE_ACTIVE)
        self._am_btn.setStyleSheet(_STYLE_INACTIVE if self._is_pm else _STYLE_ACTIVE)
        self._pm_btn.setStyleSheet(_STYLE_ACTIVE if self._is_pm else _STYLE_INACTIVE)

    def _set_phase(self, phase: str) -> None:
        self._clock.set_phase(phase)
        self._hour_tab.setChecked(phase == ClockFace.PHASE_HOUR)
        self._min_tab.setChecked(phase == ClockFace.PHASE_MIN)
        self._update_tab_styles()
        self._update_display()

    def _set_pm(self, is_pm: bool) -> None:
        self._is_pm = is_pm
        self._am_btn.setChecked(not is_pm)
        self._pm_btn.setChecked(is_pm)
        self._update_tab_styles()
        self._update_display()

    def _on_clock_value(self, val: int) -> None:
        if self._clock.phase == ClockFace.PHASE_HOUR:
            self._hour = val
            # Auto-advance to minute selection
            self._set_phase(ClockFace.PHASE_MIN)
        else:
            self._minute = val
        self._update_display()

    # ── Result ──────────────────────────────────────────────────────────────
    def get_time_24h(self) -> tuple[int, int]:
        """Return (hour_24, minute) in 24h format."""
        h = self._hour % 12
        if self._is_pm:
            h += 12
        return h, self._minute

    def get_time_str(self) -> str:
        h, m = self.get_time_24h()
        return f'{h:02d}:{m:02d}'
