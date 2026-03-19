"""
Shared PySide6 UI helpers.
"""
from __future__ import annotations
from PySide6.QtWidgets import QComboBox


def set_combo_by_data(combo: QComboBox, value: str) -> None:
    """Set combo current index by matching itemData (userData), not display text."""
    for i in range(combo.count()):
        if combo.itemData(i) == value:
            combo.setCurrentIndex(i)
            return
