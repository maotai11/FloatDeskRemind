"""
Application configuration — backed by the settings table.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.data.settings_repository import SettingsRepository

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
        cfg.theme = repo.get('theme', DEFAULTS['theme'])
        cfg.accent_color = repo.get('accent_color', DEFAULTS['accent_color'])
        cfg.font_size = repo.get('font_size', DEFAULTS['font_size'])
        cfg.float_opacity = float(repo.get('float_opacity', DEFAULTS['float_opacity']))
        cfg.display_days = int(repo.get('display_days', DEFAULTS['display_days']))
        cfg.auto_backup = repo.get('auto_backup', DEFAULTS['auto_backup'])
        cfg.auto_start = repo.get('auto_start', DEFAULTS['auto_start']) == 'true'
        cfg.language = repo.get('language', DEFAULTS['language'])
        px = repo.get('float_pos_x', DEFAULTS['float_pos_x'])
        py = repo.get('float_pos_y', DEFAULTS['float_pos_y'])
        cfg.float_pos_x = int(px) if px else -1
        cfg.float_pos_y = int(py) if py else -1
        cfg.float_width = int(repo.get('float_width', DEFAULTS['float_width']))
        cfg.float_height = int(repo.get('float_height', DEFAULTS['float_height']))
        cx = repo.get('console_x', DEFAULTS['console_x'])
        cy = repo.get('console_y', DEFAULTS['console_y'])
        cfg.console_x = int(cx) if cx else -1
        cfg.console_y = int(cy) if cy else -1
        cfg.console_width = int(repo.get('console_width', DEFAULTS['console_width']))
        cfg.console_height = int(repo.get('console_height', DEFAULTS['console_height']))
        cfg.console_splitter = int(repo.get('console_splitter', DEFAULTS['console_splitter']))
        return cfg

    def save(self, repo: 'SettingsRepository') -> None:
        repo.set('theme', self.theme)
        repo.set('accent_color', self.accent_color)
        repo.set('font_size', self.font_size)
        repo.set('float_opacity', str(self.float_opacity))
        repo.set('display_days', str(self.display_days))
        repo.set('auto_backup', self.auto_backup)
        repo.set('auto_start', 'true' if self.auto_start else 'false')
        repo.set('language', self.language)
        repo.set('float_pos_x', str(self.float_pos_x))
        repo.set('float_pos_y', str(self.float_pos_y))
        repo.set('float_width', str(self.float_width))
        repo.set('float_height', str(self.float_height))
        repo.set('console_x', str(self.console_x))
        repo.set('console_y', str(self.console_y))
        repo.set('console_width', str(self.console_width))
        repo.set('console_height', str(self.console_height))
        repo.set('console_splitter', str(self.console_splitter))
