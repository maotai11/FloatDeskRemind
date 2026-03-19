"""
Settings dialog: autostart + float opacity.
"""
from __future__ import annotations
from typing import TYPE_CHECKING

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QFormLayout, QCheckBox,
    QSlider, QLabel, QHBoxLayout, QDialogButtonBox
)
from PySide6.QtCore import Qt

from src.core.autostart import is_autostart_enabled

if TYPE_CHECKING:
    from src.core.config import AppConfig


class SettingsDialog(QDialog):
    def __init__(self, config: 'AppConfig', parent=None):
        super().__init__(parent)
        self._config = config
        self.setWindowTitle('設定')
        self.setModal(True)
        self.setMinimumWidth(360)
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(16)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        form.setSpacing(10)

        # Autostart
        self._autostart = QCheckBox('開機時自動啟動 FloatDesk Remind')
        self._autostart.setChecked(is_autostart_enabled())
        form.addRow('開機自動啟動', self._autostart)

        # Float opacity slider
        form.addRow('浮動視窗透明度', self._make_opacity_row())

        layout.addLayout(form)

        # Buttons
        btn_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        btn_box.button(QDialogButtonBox.StandardButton.Ok).setText('套用')
        btn_box.button(QDialogButtonBox.StandardButton.Cancel).setText('取消')
        btn_box.accepted.connect(self.accept)
        btn_box.rejected.connect(self.reject)
        layout.addWidget(btn_box)

    def _make_opacity_row(self):
        from PySide6.QtWidgets import QWidget
        container = QWidget()
        h = QHBoxLayout(container)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(8)

        self._opacity_slider = QSlider(Qt.Orientation.Horizontal)
        self._opacity_slider.setRange(30, 100)
        self._opacity_slider.setValue(int(self._config.float_opacity * 100))
        self._opacity_slider.setFixedWidth(180)

        self._opacity_label = QLabel(f'{int(self._config.float_opacity * 100)}%')
        self._opacity_label.setFixedWidth(40)
        self._opacity_slider.valueChanged.connect(
            lambda v: self._opacity_label.setText(f'{v}%')
        )

        h.addWidget(self._opacity_slider)
        h.addWidget(self._opacity_label)
        return container

    @property
    def autostart(self) -> bool:
        return self._autostart.isChecked()

    @property
    def float_opacity(self) -> float:
        return self._opacity_slider.value() / 100.0
