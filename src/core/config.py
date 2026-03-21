"""
Application configuration — backed by the settings table.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.data.settings_repository import SettingsRepository

def _safe_float(s: str, default: float) -> float:
    try:
        return float(s)
    except (ValueError, TypeError):
        return default


def _safe_int(s: str, default: int) -> int:
    try:
        return int(s)
    except (ValueError, TypeError):
        return default


DEFAULTS = {
    'theme': 'light',
    'accent_color': 'blue',
    'font_size': 'medium',
    'float_opacity': '0.95',
    'display_days': '3',
    'auto_backup': 'daily',
    'auto_start': 'false',
    'language': 'zh-TW',
    'float_pos_x': '',
    'float_pos_y': '',
    'float_width': '320',
    'float_height': '480',
    'console_x': '',
    'console_y': '',
    'console_width': '1100',
    'console_height': '700',
    'console_splitter': '600',
}


@dataclass
class AppConfig:
    theme: str = 'light'
    accent_color: str = 'blue'
    font_size: str = 'medium'
    float_opacity: float = 0.95
    display_days: int = 3
    auto_backup: str = 'daily'
    auto_start: bool = False
    language: str = 'zh-TW'
    float_pos_x: int = -1
    float_pos_y: int = -1
    float_width: int = 320
    float_height: int = 480
    console_x: int = -1
    console_y: int = -1
    console_width: int = 1100
    console_height: int = 700
    console_splitter: int = 600

    @classmethod
    def load(cls, repo: 'SettingsRepository') -> 'AppConfig':
        cfg = cls()
        all_s = repo.get_all()

        def _get(key: str) -> str:
            return all_s.get(key, DEFAULTS.get(key, ''))

        cfg.theme = _get('theme')
        cfg.accent_color = _get('accent_color')
        cfg.font_size = _get('font_size')
        cfg.float_opacity = _safe_float(_get('float_opacity'), 0.95)
        cfg.display_days = _safe_int(_get('display_days'), 3)
        cfg.auto_backup = _get('auto_backup')
        cfg.auto_start = _get('auto_start') == 'true'
        cfg.language = _get('language')
        px, py = _get('float_pos_x'), _get('float_pos_y')
        cfg.float_pos_x = _safe_int(px, -1) if px else -1
        cfg.float_pos_y = _safe_int(py, -1) if py else -1
        cfg.float_width = _safe_int(_get('float_width'), 320)
        cfg.float_height = _safe_int(_get('float_height'), 480)
        cx, cy = _get('console_x'), _get('console_y')
        cfg.console_x = _safe_int(cx, -1) if cx else -1
        cfg.console_y = _safe_int(cy, -1) if cy else -1
        cfg.console_width = _safe_int(_get('console_width'), 1100)
        cfg.console_height = _safe_int(_get('console_height'), 700)
        cfg.console_splitter = _safe_int(_get('console_splitter'), 600)
        return cfg

    def save(self, repo: 'SettingsRepository') -> None:
        repo.set_many({
            'theme': self.theme,
            'accent_color': self.accent_color,
            'font_size': self.font_size,
            'float_opacity': str(self.float_opacity),
            'display_days': str(self.display_days),
            'auto_backup': self.auto_backup,
            'auto_start': 'true' if self.auto_start else 'false',
            'language': self.language,
            'float_pos_x': str(self.float_pos_x),
            'float_pos_y': str(self.float_pos_y),
            'float_width': str(self.float_width),
            'float_height': str(self.float_height),
            'console_x': str(self.console_x),
            'console_y': str(self.console_y),
            'console_width': str(self.console_width),
            'console_height': str(self.console_height),
            'console_splitter': str(self.console_splitter),
        })
