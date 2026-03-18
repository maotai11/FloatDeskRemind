"""Simple search bar widget."""
from PySide6.QtWidgets import QWidget, QHBoxLayout, QLineEdit, QPushButton
from PySide6.QtCore import Signal, Qt


class SearchBar(QWidget):
    search_changed = Signal(str)
    search_cleared = Signal()

    def __init__(self, placeholder: str = '搜尋任務...', parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        self._edit = QLineEdit()
        self._edit.setPlaceholderText(placeholder)
        self._edit.textChanged.connect(self._on_text_changed)
        layout.addWidget(self._edit)

        self._clear_btn = QPushButton('x')
        self._clear_btn.setFixedSize(24, 24)
        self._clear_btn.setStyleSheet(
            'QPushButton { background: transparent; color: #999; border: none; font-size: 14px; }'
            'QPushButton:hover { color: #333; }'
        )
        self._clear_btn.clicked.connect(self._on_clear)
        self._clear_btn.hide()
        layout.addWidget(self._clear_btn)

    def _on_text_changed(self, text: str) -> None:
        self._clear_btn.setVisible(bool(text))
        self.search_changed.emit(text)

    def _on_clear(self) -> None:
        self._edit.clear()
        self.search_cleared.emit()

    def text(self) -> str:
        return self._edit.text()

    def set_focus(self) -> None:
        self._edit.setFocus()

    def clear(self) -> None:
        self._edit.clear()
