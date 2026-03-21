"""
FloatWindow: always-on-top frameless floating window.
Indigo header, rounded corners, draggable, transparent background.
"""
from __future__ import annotations
from typing import List, Dict

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QApplication
)
from PySide6.QtCore import Signal, Qt, QPoint, QRectF
from PySide6.QtGui import QPainter, QColor, QPen, QBrush, QCursor

from src.data.models import Task
from src.core.utils import next_n_days
from src.ui.components.task_list_widget import TaskListWidget
from src.ui.utils import restore_window_geometry
from src.core.config import AppConfig

HEADER_HEIGHT = 42
CORNER_RADIUS = 12


class FloatWindow(QWidget):
    task_completed = Signal(str)
    task_edit_requested = Signal(str)
    task_delete_requested = Signal(str)
    open_console_requested = Signal()
    geometry_changed = Signal(int, int, int, int)

    def __init__(self, config: AppConfig, parent=None):
        super().__init__(parent)
        self._config = config
        self._drag_pos: QPoint | None = None
        self._opacity = config.float_opacity
        self._build_ui()
        self._setup_window()
        self._restore_geometry()

    def _setup_window(self) -> None:
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)
        self.setMinimumSize(260, 320)

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Header
        self._header = QWidget()
        self._header.setFixedHeight(HEADER_HEIGHT)
        self._header.setObjectName('FloatHeader')
        self._header.setStyleSheet(
            f'background-color: #4F46E5; border-radius: {CORNER_RADIUS}px {CORNER_RADIUS}px 0 0;'
        )
        self._header.setCursor(QCursor(Qt.CursorShape.SizeAllCursor))

        hl = QHBoxLayout(self._header)
        hl.setContentsMargins(14, 0, 8, 0)
        hl.setSpacing(4)

        icon_lbl = QLabel('◆')
        icon_lbl.setStyleSheet('color: rgba(255,255,255,0.6); font-size: 9px;')
        hl.addWidget(icon_lbl)

        title = QLabel('FloatDesk')
        title.setStyleSheet(
            'color: white; font-weight: 700; font-size: 13px; letter-spacing: 0.5px;'
        )
        hl.addWidget(title)
        hl.addStretch()

        self._count_badge = QLabel('')
        self._count_badge.setStyleSheet(
            'background: rgba(255,255,255,0.22); color: white; '
            'border-radius: 9px; padding: 1px 7px; font-size: 11px; font-weight: 600;'
        )
        self._count_badge.hide()
        hl.addWidget(self._count_badge)

        console_btn = self._mk_header_btn('≡', '開啟主控台')
        console_btn.clicked.connect(self.open_console_requested)
        hl.addWidget(console_btn)

        hide_btn = self._mk_header_btn('−', '最小化')
        hide_btn.clicked.connect(self.hide)
        hl.addWidget(hide_btn)

        outer.addWidget(self._header)

        # Task list
        self._task_list = TaskListWidget()
        self._task_list.task_completed.connect(self.task_completed)
        self._task_list.task_edit_requested.connect(self.task_edit_requested)
        self._task_list.task_delete_requested.connect(self.task_delete_requested)
        self._task_list.setObjectName('FloatBody')
        outer.addWidget(self._task_list)

        # Bottom grip
        grip = QWidget()
        grip.setFixedHeight(5)
        grip.setStyleSheet(
            f'background-color: #E2E8F0; border-radius: 0 0 {CORNER_RADIUS}px {CORNER_RADIUS}px;'
        )
        outer.addWidget(grip)

    @staticmethod
    def _mk_header_btn(text: str, tip: str) -> QPushButton:
        btn = QPushButton(text)
        btn.setFixedSize(28, 28)
        btn.setToolTip(tip)
        btn.setStyleSheet(
            'QPushButton { background: transparent; color: rgba(255,255,255,0.85); '
            'border: none; font-size: 16px; border-radius: 6px; }'
            'QPushButton:hover { background: rgba(255,255,255,0.2); color: white; }'
        )
        return btn

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        alpha = int(self._opacity * 255)
        p.setBrush(QBrush(QColor(253, 252, 255, alpha)))
        p.setPen(QPen(QColor(226, 232, 240, 200), 1))
        p.drawRoundedRect(
            QRectF(self.rect().adjusted(0, 0, -1, -1)),
            CORNER_RADIUS, CORNER_RADIUS
        )

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            if event.position().y() <= HEADER_HEIGHT:
                self._drag_pos = (
                    event.globalPosition().toPoint() - self.frameGeometry().topLeft()
                )

    def mouseMoveEvent(self, event) -> None:
        if self._drag_pos and event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_pos)

    def mouseReleaseEvent(self, event) -> None:
        self._drag_pos = None
        self._save_geometry()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._save_geometry()

    def _save_geometry(self) -> None:
        geo = self.geometry()
        self.geometry_changed.emit(geo.x(), geo.y(), geo.width(), geo.height())

    def _restore_geometry(self) -> None:
        w = self._config.float_width
        h = self._config.float_height
        if not restore_window_geometry(self, self._config.float_pos_x, self._config.float_pos_y, w, h):
            screen = QApplication.primaryScreen()
            if screen:
                rect = screen.availableGeometry()
                self.move(rect.right() - w - 20, rect.top() + 40)

    def refresh(self, tasks: List[Task]) -> None:
        dates = next_n_days(self._config.display_days)
        tasks_by_date: Dict[str, List[Task]] = {d: [] for d in dates}
        for task in tasks:
            if task.due_date in tasks_by_date:
                tasks_by_date[task.due_date].append(task)
        total = sum(len(v) for v in tasks_by_date.values())
        if total > 0:
            self._count_badge.setText(str(total))
            self._count_badge.show()
        else:
            self._count_badge.hide()
        self._task_list.refresh(tasks_by_date)

    def set_opacity(self, opacity: float) -> None:
        self._opacity = max(0.1, min(1.0, opacity))
        self.update()
