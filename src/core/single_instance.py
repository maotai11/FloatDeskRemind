"""
Windows single-instance lock using win32api.CreateMutex.
"""
import sys

try:
    import win32api
    import win32con
    import pywintypes
    HAS_WIN32 = True
except ImportError:
    HAS_WIN32 = False

MUTEX_NAME = 'FloatDeskRemind_SingleInstance_Mutex'
_mutex_handle = None


def acquire_lock() -> bool:
    """
    Attempt to acquire the single-instance mutex.
    Returns True if this is the first instance, False otherwise.
    """
    global _mutex_handle
    if not HAS_WIN32:
        return True

    try:
        _mutex_handle = win32api.CreateMutex(None, True, MUTEX_NAME)
        last_error = win32api.GetLastError()
        if last_error == 183:  # ERROR_ALREADY_EXISTS
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
