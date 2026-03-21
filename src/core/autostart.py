"""
Windows Registry autostart management.
Reads/writes HKCU\Software\Microsoft\Windows\CurrentVersion\Run
"""
import sys
import logging

_log = logging.getLogger('floatdesk')

try:
    import winreg
    HAS_WINREG = True
except ImportError:
    HAS_WINREG = False

APP_NAME = 'FloatDeskRemind'
RUN_KEY = r'Software\Microsoft\Windows\CurrentVersion\Run'


def _get_exe_path() -> str:
    if getattr(sys, 'frozen', False):
        return sys.executable
    return f'"{sys.executable}" "{sys.argv[0]}"'


def is_autostart_enabled() -> bool:
    if not HAS_WINREG:
        return False
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_READ)
        winreg.QueryValueEx(key, APP_NAME)
        winreg.CloseKey(key)
        return True
    except FileNotFoundError:
        return False
    except Exception as e:
        _log.warning(f'autostart check failed: {e}')
        return False


def set_autostart(enabled: bool) -> bool:
    if not HAS_WINREG:
        return False
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE)
        if enabled:
            winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, _get_exe_path())
        else:
            try:
                winreg.DeleteValue(key, APP_NAME)
            except FileNotFoundError:
                pass
        winreg.CloseKey(key)
        return True
    except Exception as e:
        _log.warning(f'autostart set failed (enabled={enabled}): {e}')
        return False
