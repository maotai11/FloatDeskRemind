"""
Shared PySide6 UI helpers.
"""
from __future__ import annotations
from PySide6.QtWidgets import QComboBox
from PySide6.QtCore import QDate

# Sentinel date used to represent "no date set" in QDateEdit (special value text).
# Year must be <= setMinimumDate so the special value text is shown at that value.
NO_DATE = QDate(2000, 1, 1)


def set_combo_by_data(combo: QComboBox, value: str) -> None:
    """Set combo current index by matching itemData (userData), not display text."""
    for i in range(combo.count()):
        if combo.itemData(i) == value:
            combo.setCurrentIndex(i)
            return
