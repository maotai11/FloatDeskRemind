"""
Settings dialog — matches AppConfig fields from the spec.
Sections: 一般 / 浮動視窗 / 系統
"""
from __future__ import annotations
from typing import TYPE_CHECKING

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QFormLayout, QHBoxLayout,
    QCheckBox, QSlider, QLabel, QComboBox,
    QDialogButtonBox, QWidget, QGroupBox, QSpinBox
)
from PySide6.QtCore import Qt

from src.core.autostart import is_autostart_enabled
from src.ui.utils import set_combo_by_data

if TYPE_CHECKING:
    from src.core.config import AppConfig


class SettingsDialog(QDialog):
    def __init__(self, config: 'AppConfig', parent=None):
        super().__init__(parent)
        self._config = config
        self.setWindowTitle('設定')
        self.setModal(True)
        self.setMinimumWidth(400)
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(14)

        title = QLabel('設定')
        title.setStyleSheet('font-size: 17px; font-weight: 700; color: #1E293B;')
        layout.addWidget(title)

        # ── 一般設定 ──────────────────────────────────────────────────────
        general_box = QGroupBox('一般')
        gf = QFormLayout(general_box)
        gf.setSpacing(10)
        gf.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        # 顯示天數
        self._display_days = QSpinBox()
        self._display_days.setRange(1, 7)
        self._display_days.setValue(self._config.display_days)
        self._display_days.setSuffix(' 天')
        self._display_days.setFixedWidth(100)
        gf.addRow('浮動視窗顯示天數', self._display_days)

        # 字體大小
        self._font_size = QComboBox()
        for val, lbl in (('small', '小'), ('medium', '中'), ('large', '大')):
            self._font_size.addItem(lbl, val)
        set_combo_by_data(self._font_size, self._config.font_size)
        gf.addRow('字體大小', self._font_size)

        layout.addWidget(general_box)

        # ── 浮動視窗 ──────────────────────────────────────────────────────
        float_box = QGroupBox('浮動視窗')
        ff = QFormLayout(float_box)
        ff.setSpacing(10)
        ff.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        # 透明度
        opacity_row = QWidget()
        or_ = QHBoxLayout(opacity_row)
        or_.setContentsMargins(0, 0, 0, 0)
        or_.setSpacing(8)

        self._opacity_slider = QSlider(Qt.Orientation.Horizontal)
        self._opacity_slider.setRange(30, 100)
        self._opacity_slider.setValue(int(self._config.float_opacity * 100))
        self._opacity_slider.setFixedWidth(160)

        self._opacity_label = QLabel(f'{int(self._config.float_opacity * 100)}%')
        self._opacity_label.setFixedWidth(36)
        self._opacity_slider.valueChanged.connect(
            lambda v: self._opacity_label.setText(f'{v}%')
        )
        or_.addWidget(self._opacity_slider)
        or_.addWidget(self._opacity_label)
        ff.addRow('透明度', opacity_row)

        layout.addWidget(float_box)

        # ── 系統 ──────────────────────────────────────────────────────────
        sys_box = QGroupBox('系統')
        sf = QFormLayout(sys_box)
        sf.setSpacing(10)
        sf.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        # 開機自動啟動
        self._autostart = QCheckBox('開機時自動啟動')
        self._autostart.setChecked(is_autostart_enabled())
        sf.addRow('開機自動啟動', self._autostart)

        # 自動備份
        self._auto_backup = QComboBox()
        for val, lbl in (('daily', '每日'), ('weekly', '每週'), ('never', '從不')):
            self._auto_backup.addItem(lbl, val)
        set_combo_by_data(self._auto_backup, self._config.auto_backup)
        sf.addRow('自動備份', self._auto_backup)

        layout.addWidget(sys_box)

        # ── Buttons ───────────────────────────────────────────────────────
        btn_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        btn_box.button(QDialogButtonBox.StandardButton.Ok).setText('套用')
        btn_box.button(QDialogButtonBox.StandardButton.Cancel).setText('取消')
        btn_box.accepted.connect(self.accept)
        btn_box.rejected.connect(self.reject)
        layout.addWidget(btn_box)

    # ── Result properties ────────────────────────────────────────────────
    @property
    def autostart(self) -> bool:
        return self._autostart.isChecked()

    @property
    def float_opacity(self) -> float:
        return self._opacity_slider.value() / 100.0

    @property
    def display_days(self) -> int:
        return self._display_days.value()

    @property
    def font_size(self) -> str:
        return self._font_size.currentData()

    @property
    def auto_backup(self) -> str:
        return self._auto_backup.currentData()
