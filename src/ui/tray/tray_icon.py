"""
System tray icon with right-click menu.
"""
from __future__ import annotations
from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtWidgets import QSystemTrayIcon, QMenu
from PySide6.QtGui import QIcon, QAction
from PySide6.QtCore import Signal, QObject

from src.core.paths import ASSETS_DIR

if TYPE_CHECKING:
    from src.app import AppController


class TrayIcon(QSystemTrayIcon):
    show_float_requested = Signal()
    show_console_requested = Signal()
    show_settings_requested = Signal()
    quit_requested = Signal()

    def __init__(self, parent: QObject = None):
        super().__init__(parent)

        icon_path = ASSETS_DIR / 'icon.png'
        if icon_path.exists():
            self.setIcon(QIcon(str(icon_path)))
        else:
            from PySide6.QtGui import QPixmap
            px = QPixmap(32, 32)
            px.fill()
            self.setIcon(QIcon(px))

        self.setToolTip('FloatDesk Remind')
        self._build_menu()
        self.activated.connect(self._on_activated)

    def _build_menu(self) -> None:
        menu = QMenu()

        action_float = QAction('顯示浮動視窗', self)
        action_float.triggered.connect(self.show_float_requested)
        menu.addAction(action_float)

        action_console = QAction('開啟主控台', self)
        action_console.triggered.connect(self.show_console_requested)
        menu.addAction(action_console)

        action_settings = QAction('設定', self)
        action_settings.triggered.connect(self.show_settings_requested)
        menu.addAction(action_settings)

        menu.addSeparator()

        action_quit = QAction('結束', self)
        action_quit.triggered.connect(self.quit_requested)
        menu.addAction(action_quit)

        self.setContextMenu(menu)

    def _on_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self.show_console_requested.emit()
        elif reason == QSystemTrayIcon.ActivationReason.Trigger:
            self.show_float_requested.emit()
