"""
Test AppConfig load/save roundtrip.
"""
import pytest
from src.core.config import AppConfig


def test_default_values(settings_repo):
    cfg = AppConfig.load(settings_repo)
    assert cfg.theme == 'light'
    assert cfg.float_opacity == 0.95
    assert cfg.display_days == 3
    assert cfg.auto_start is False
    assert cfg.language == 'zh-TW'


def test_save_and_reload(settings_repo):
    cfg = AppConfig.load(settings_repo)
    cfg.float_opacity = 0.7
    cfg.display_days = 2
    cfg.auto_start = True
    cfg.float_pos_x = 100
    cfg.float_pos_y = 200
    cfg.save(settings_repo)

    cfg2 = AppConfig.load(settings_repo)
    assert cfg2.float_opacity == pytest.approx(0.7)
    assert cfg2.display_days == 2
    assert cfg2.auto_start is True
    assert cfg2.float_pos_x == 100
    assert cfg2.float_pos_y == 200
