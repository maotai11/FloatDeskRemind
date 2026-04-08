"""
Windows single-instance lock using win32event.CreateMutex.

NOTE: CreateMutex lives in win32event, NOT win32api.  After PyInstaller
freezing the win32api symbol table is trimmed, so the old win32api.CreateMutex
call raised AttributeError at runtime.  win32event.CreateMutex is the
canonical, documented location for this API in pywin32.
"""
import sys

try:
    import win32event
    import win32api
    import win32con
    import pywintypes
    HAS_WIN32 = True
except ImportError:
    HAS_WIN32 = False

MUTEX_NAME = 'FloatDeskRemind_SingleInstance_Mutex'
_mutex_handle = None

# Windows error code for "already exists"
_ERROR_ALREADY_EXISTS = 183


def acquire_lock() -> bool:
    """
    Attempt to acquire the single-instance mutex.
    Returns True if this is the first instance, False otherwise.
    """
    global _mutex_handle
    if not HAS_WIN32:
        return True

    try:
        # win32event.CreateMutex is the correct, documented location for this
        # API.  win32api.CreateMutex was an alias that breaks in frozen builds.
        _mutex_handle = win32event.CreateMutex(None, True, MUTEX_NAME)
        last_error = win32api.GetLastError()
        if last_error == _ERROR_ALREADY_EXISTS:
            return False
        return True
    except pywintypes.error:
        return True


def release_lock() -> None:
    global _mutex_handle
    if _mutex_handle and HAS_WIN32:
        try:
            win32api.CloseHandle(_mutex_handle)
        except Exception:
            pass  # nosec B110 — cleanup path; handle close failure is unrecoverable
        _mutex_handle = None
