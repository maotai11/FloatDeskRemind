"""Custom status bar for the console window."""
from PySide6.QtWidgets import QStatusBar, QLabel
from PySide6.QtCore import QTimer


class AppStatusBar(QStatusBar):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._perm_label = QLabel('')
        self.addPermanentWidget(self._perm_label)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._clear_temp)

    def show_message(self, message: str, timeout_ms: int = 3000) -> None:
        self.showMessage(message, timeout_ms)

    def show_permanent(self, message: str) -> None:
        self._perm_label.setText(message)

    def _clear_temp(self) -> None:
        self.clearMessage()
