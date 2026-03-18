"""
FloatWindow: always-on-top frameless floating window.
- Draggable by header
- Transparent background via QPainter (Windows 11 compatible)
- Qt.WA_TranslucentBackground + paintEvent
- Position and size persisted to config
"""
from __future__ import annotations
from typing import List, Dict, TYPE_CHECKING

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QSizePolicy
)
from PySide6.QtCore import Signal, Qt, QPoint
from PySide6.QtGui import QPainter, QColor, QPen, QBrush, QCursor

from src.data.models import Task
from src.core.utils import next_n_days
from src.ui.components.task_list_widget import TaskListWidget
from src.core.config import AppConfig

if TYPE_CHECKING:
    pass

HEADER_HEIGHT = 36


class FloatWindow(QWidget):
    task_completed = Signal(str)
    task_edit_requested = Signal(str)
    task_delete_requested = Signal(str)
    open_console_requested = Signal()
    closed = Signal()
    geometry_changed = Signal(int, int, int, int)  # x, y, w, h

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
        self.setMinimumSize(240, 300)

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Header (drag handle)
        self._header = QWidget()
        self._header.setFixedHeight(HEADER_HEIGHT)
        self._header.setObjectName('FloatHeader')
        self._header.setStyleSheet(
            'background-color: #1976D2; border-radius: 8px 8px 0 0;'
        )
        self._header.setCursor(QCursor(Qt.CursorShape.SizeAllCursor))
        header_layout = QHBoxLayout(self._header)
        header_layout.setContentsMargins(10, 0, 6, 0)

        title = QLabel('FloatDesk Remind')
        title.setStyleSheet('color: white; font-weight: bold; font-size: 13px;')
        header_layout.addWidget(title)
        header_layout.addStretch()

        console_btn = QPushButton('≡')
        console_btn.setFixedSize(24, 24)
        console_btn.setToolTip('開啟主控台')
        console_btn.setStyleSheet(
            'QPushButton { background: transparent; color: white; border: none; font-size: 16px; }'
            'QPushButton:hover { background: rgba(255,255,255,0.2); border-radius: 4px; }'
        )
        console_btn.clicked.connect(self.open_console_requested)
        header_layout.addWidget(console_btn)

        hide_btn = QPushButton('−')
        hide_btn.setFixedSize(24, 24)
        hide_btn.setToolTip('隱藏浮動視窗')
        hide_btn.setStyleSheet(
            'QPushButton { background: transparent; color: white; border: none; font-size: 18px; }'
            'QPushButton:hover { background: rgba(255,255,255,0.2); border-radius: 4px; }'
        )
        hide_btn.clicked.connect(self.hide)
        header_layout.addWidget(hide_btn)

        outer.addWidget(self._header)

        # Task list
        self._task_list = TaskListWidget()
        self._task_list.task_completed.connect(self.task_completed)
        self._task_list.task_edit_requested.connect(self.task_edit_requested)
        self._task_list.task_delete_requested.connect(self.task_delete_requested)
        self._task_list.setObjectName('FloatBody')

        # Body background via stylesheet (will also be painted in paintEvent)
        outer.addWidget(self._task_list)

        # Bottom resize grip
        grip = QWidget()
        grip.setFixedHeight(6)
        grip.setStyleSheet('background-color: #E0E0E0; border-radius: 0 0 8px 8px;')
        outer.addWidget(grip)

    def paintEvent(self, event) -> None:
        """Paint rounded semi-transparent background."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        alpha = int(self._opacity * 255)
        color = QColor(250, 250, 250, alpha)
        painter.setBrush(QBrush(color))
        painter.setPen(QPen(QColor(200, 200, 200, 180), 1))
        painter.drawRoundedRect(self.rect().adjusted(0, 0, -1, -1), 8, 8)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            if event.position().y() <= HEADER_HEIGHT:
                self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()

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
        self.resize(w, h)

        if self._config.float_pos_x >= 0 and self._config.float_pos_y >= 0:
            self.move(self._config.float_pos_x, self._config.float_pos_y)
        else:
            from PySide6.QtWidgets import QApplication
            screen = QApplication.primaryScreen()
            if screen:
                rect = screen.availableGeometry()
                self.move(rect.right() - w - 20, rect.top() + 40)

    def refresh(self, tasks: List[Task]) -> None:
        dates = next_n_days(3)
        tasks_by_date: Dict[str, List[Task]] = {d: [] for d in dates}
        for task in tasks:
            if task.due_date in tasks_by_date:
                tasks_by_date[task.due_date].append(task)
        self._task_list.refresh(tasks_by_date)

    def set_opacity(self, opacity: float) -> None:
        self._opacity = max(0.1, min(1.0, opacity))
        self.update()
