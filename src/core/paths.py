"""
Centralized path management for FloatDesk Remind.
Supports both frozen (PyInstaller) and dev modes.
"""
import sys
from pathlib import Path


def _get_base_dir() -> Path:
    # onefile frozen: data files are extracted to sys._MEIPASS (temp dir), NOT exe dir
    if getattr(sys, 'frozen', False):
        return Path(getattr(sys, '_MEIPASS', Path(sys.executable).parent))
    return Path(__file__).parent.parent.parent


def _get_app_data_dir() -> Path:
    import os
    appdata = os.environ.get('APPDATA', Path.home())
    return Path(appdata) / 'FloatDeskRemind'


BASE_DIR: Path = _get_base_dir()
APP_DATA_DIR: Path = _get_app_data_dir()
DB_PATH: Path = APP_DATA_DIR / 'floatdesk.db'
LOG_DIR: Path = APP_DATA_DIR / 'logs'
ASSETS_DIR: Path = BASE_DIR / 'assets'
QSS_PATH: Path = BASE_DIR / 'src' / 'ui' / 'styles' / 'main.qss'


def ensure_dirs() -> None:
    APP_DATA_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
