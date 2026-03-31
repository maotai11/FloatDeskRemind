"""
Centralized path management for FloatDesk Remind.
Supports both frozen (PyInstaller onedir) and dev modes.

DATA_MODE is determined once at import time — never changes at runtime:
  'appdata'  — data stored in %APPDATA%/FloatDeskRemind  (default)
  'portable' — data stored in <exe_dir>/data             (portable.flag next to exe)

Read-only resource paths (BASE_DIR, ASSETS_DIR, QSS_PATH) are rooted at
_MEIPASS in frozen builds and the project root in dev mode.
ALL writable paths are rooted at APP_DATA_DIR, which is guaranteed to be
outside _MEIPASS.

ensure_dirs() raises OSError in portable mode if the data directory is not
writable.  It never silently falls back to appdata mode.
"""
import sys
import os
from pathlib import Path


# ---------------------------------------------------------------------------
# Pure helper functions (called at module level; also directly testable)
# ---------------------------------------------------------------------------

def _get_exe_dir() -> Path:
    """Return the directory that 'owns' the running process.

    - Frozen (PyInstaller): directory containing the EXE.
    - Dev: project root resolved from __file__ — independent of cwd.
    """
    if getattr(sys, 'frozen', False):
        return Path(sys.executable).parent
    # Walk up: src/core/paths.py → src/core → src → project root
    return Path(__file__).resolve().parent.parent.parent


def _get_base_dir() -> Path:
    """Asset root.  Read-only in all cases.

    - Frozen: sys._MEIPASS (PyInstaller extraction dir, read-only).
    - Dev: project root (same tree as EXE_DIR, semantically distinct).
    """
    if getattr(sys, 'frozen', False):
        return Path(getattr(sys, '_MEIPASS', Path(sys.executable).parent))
    return Path(__file__).resolve().parent.parent.parent


def _resolve_data_mode(exe_dir: Path) -> str:
    """Pure: return 'portable' if portable.flag exists next to exe, else 'appdata'."""
    return 'portable' if (exe_dir / 'portable.flag').exists() else 'appdata'


def _resolve_app_data_dir(exe_dir: Path, data_mode: str) -> Path:
    """Pure: resolve APP_DATA_DIR from exe_dir and data_mode.

    portable → exe_dir / 'data'
    appdata  → %APPDATA%/FloatDeskRemind  (fallback: ~/FloatDeskRemind)
    """
    if data_mode == 'portable':
        return exe_dir / 'data'
    appdata = os.environ.get('APPDATA') or str(Path.home())
    return Path(appdata) / 'FloatDeskRemind'


# ---------------------------------------------------------------------------
# Module-level constants — resolved once at import time
# ---------------------------------------------------------------------------

EXE_DIR: Path = _get_exe_dir()
BASE_DIR: Path = _get_base_dir()
DATA_MODE: str = _resolve_data_mode(EXE_DIR)
APP_DATA_DIR: Path = _resolve_app_data_dir(EXE_DIR, DATA_MODE)

# Writable data paths — all children of APP_DATA_DIR, never of BASE_DIR
DB_PATH: Path = APP_DATA_DIR / 'floatdesk.db'
LOG_DIR: Path = APP_DATA_DIR / 'logs'
BACKUP_DIR: Path = APP_DATA_DIR / 'backups'

# Read-only resource paths — children of BASE_DIR / _MEIPASS only
ASSETS_DIR: Path = BASE_DIR / 'assets'
QSS_PATH: Path = BASE_DIR / 'src' / 'ui' / 'styles' / 'main.qss'


# ---------------------------------------------------------------------------
# Directory initialisation
# ---------------------------------------------------------------------------

def ensure_dirs() -> None:
    """Create all writable data directories: APP_DATA_DIR, LOG_DIR, BACKUP_DIR.

    Portable mode contract:
      If APP_DATA_DIR cannot be created or written to, raises OSError with a
      message instructing the user to remove portable.flag or fix permissions.
      There is NO silent fallback to appdata mode.

    Never touches BASE_DIR, ASSETS_DIR, or QSS_PATH (read-only resources).
    """
    if DATA_MODE == 'portable':
        try:
            APP_DATA_DIR.mkdir(parents=True, exist_ok=True)
            # Verify write access with a transient probe file
            _probe = APP_DATA_DIR / '.write_probe'
            _probe.write_text('ok', encoding='utf-8')
            _probe.unlink()
        except OSError as exc:
            raise OSError(
                f'Portable mode: 資料目錄無法建立或不可寫入：{APP_DATA_DIR}\n'
                f'請移除 portable.flag 以改用 APPDATA 模式，或修正目錄寫入權限。\n'
                f'原因：{exc}'
            ) from exc
    else:
        APP_DATA_DIR.mkdir(parents=True, exist_ok=True)

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
