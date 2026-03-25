"""
TimePickerMixin: shared time-picker button behaviour.
Used by TaskEditDialog and RightPanel.
Concrete class must initialise self._time_str, self._time_btn, self._clear_time_btn.
"""
from __future__ import annotations
from typing import Optional


class TimePickerMixin:
    _time_str: Optional[str]

    def _open_time_picker(self) -> None:
        from src.ui.components.time_picker_dialog import TimePickerDialog
        h, m, pm = 9, 0, False
        if self._time_str:
            try:
                parts = self._time_str.split(':')
                h24 = int(parts[0])
                m = int(parts[1])
                pm = h24 >= 12
                h = h24 % 12 or 12
            except Exception:
                pass  # nosec B110 — malformed stored time string; fall back to defaults (9:00 AM)
        dlg = TimePickerDialog(hour=h, minute=m, is_pm=pm, parent=self)
        if dlg.exec():
            self._time_str = dlg.get_time_str()
            self._apply_time_btn_selected()

    def _apply_time_btn_selected(self) -> None:
        self._time_btn.setText(self._time_str)
        self._time_btn.setStyleSheet(
            'background-color: #EEF2FF; color: #4F46E5; '
            'border: 1.5px solid #4F46E5; border-radius: 6px; '
            'padding: 7px 12px; font-weight: 600;'
        )
        self._clear_time_btn.show()

    def _clear_time(self) -> None:
        self._time_str = None
        self._time_btn.setText('＋ 設定時間（可選）')
        self._time_btn.setStyleSheet('')
        self._clear_time_btn.hide()
