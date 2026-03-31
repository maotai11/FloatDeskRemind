"""
Tests for src/core/paths.py — Portable Mode (Patch 3).

Strategy:
  - Pure function tests: call _resolve_data_mode / _resolve_app_data_dir directly.
    No module reload needed; independent of cwd.
  - ensure_dirs tests: monkeypatch module-level constants to tmp_path-based dirs.
    Python looks up module globals at call time, so monkeypatch works without reload.
  - Reload integration tests: frozen_exe fixture patches sys.frozen/executable then
    calls importlib.reload() to verify module-level constants resolve correctly.
"""
import sys
import importlib
import pytest
from pathlib import Path


# ===========================================================================
# Pure function tests — no reload, no cwd dependency
# ===========================================================================

class TestResolveDataMode:
    def test_no_flag_returns_appdata(self, tmp_path):
        from src.core.paths import _resolve_data_mode
        assert _resolve_data_mode(tmp_path) == 'appdata'

    def test_flag_present_returns_portable(self, tmp_path):
        from src.core.paths import _resolve_data_mode
        (tmp_path / 'portable.flag').write_text('')
        assert _resolve_data_mode(tmp_path) == 'portable'

    def test_flag_content_irrelevant(self, tmp_path):
        """portable.flag only needs to exist; content is ignored."""
        from src.core.paths import _resolve_data_mode
        (tmp_path / 'portable.flag').write_text('anything here')
        assert _resolve_data_mode(tmp_path) == 'portable'

    def test_flag_in_subdirectory_does_not_count(self, tmp_path):
        """Only portable.flag directly next to exe counts."""
        from src.core.paths import _resolve_data_mode
        sub = tmp_path / 'sub'
        sub.mkdir()
        (sub / 'portable.flag').write_text('')
        assert _resolve_data_mode(tmp_path) == 'appdata'


class TestResolveAppDataDir:
    def test_portable_returns_exe_dir_data(self, tmp_path):
        from src.core.paths import _resolve_app_data_dir
        result = _resolve_app_data_dir(tmp_path, 'portable')
        assert result == tmp_path / 'data'

    def test_appdata_returns_floatdeskremin_dir(self, tmp_path):
        from src.core.paths import _resolve_app_data_dir
        result = _resolve_app_data_dir(tmp_path, 'appdata')
        assert result.name == 'FloatDeskRemind'

    def test_appdata_falls_back_to_home_when_no_appdata_env(self, tmp_path, monkeypatch):
        """If APPDATA env var is missing, falls back to Path.home() / FloatDeskRemind."""
        from src.core.paths import _resolve_app_data_dir
        monkeypatch.delenv('APPDATA', raising=False)
        result = _resolve_app_data_dir(tmp_path, 'appdata')
        assert result.name == 'FloatDeskRemind'

    def test_portable_and_appdata_dirs_are_different(self, tmp_path):
        from src.core.paths import _resolve_app_data_dir
        portable_dir = _resolve_app_data_dir(tmp_path, 'portable')
        appdata_dir  = _resolve_app_data_dir(tmp_path, 'appdata')
        assert portable_dir != appdata_dir


# ===========================================================================
# Derived constants consistency — no reload needed
# ===========================================================================

class TestDerivedConstants:
    def test_db_path_parent_is_app_data_dir(self):
        import src.core.paths as paths
        assert paths.DB_PATH.parent == paths.APP_DATA_DIR

    def test_log_dir_parent_is_app_data_dir(self):
        import src.core.paths as paths
        assert paths.LOG_DIR.parent == paths.APP_DATA_DIR

    def test_backup_dir_parent_is_app_data_dir(self):
        import src.core.paths as paths
        assert paths.BACKUP_DIR.parent == paths.APP_DATA_DIR

    def test_backup_dir_name(self):
        import src.core.paths as paths
        assert paths.BACKUP_DIR.name == 'backups'

    def test_base_dir_not_equal_app_data_dir(self):
        """Read-only BASE_DIR must be separate from writable APP_DATA_DIR."""
        import src.core.paths as paths
        # In dev mode both are the project root — but DATA_MODE=='appdata' means
        # APP_DATA_DIR points to %APPDATA%/FloatDeskRemind, so they differ.
        if not getattr(sys, 'frozen', False):
            assert paths.BASE_DIR != paths.APP_DATA_DIR

    def test_exe_dir_dev_mode_is_project_root(self):
        """In dev mode, EXE_DIR is the project root (contains src/ and tests/)."""
        if getattr(sys, 'frozen', False):
            pytest.skip('only relevant in dev mode')
        import src.core.paths as paths
        assert (paths.EXE_DIR / 'src').is_dir()
        assert (paths.EXE_DIR / 'tests').is_dir()


# ===========================================================================
# ensure_dirs — monkeypatch constants, no reload needed
# ===========================================================================

class TestEnsureDirs:
    def _patch_dirs(self, monkeypatch, paths, base, mode='appdata'):
        monkeypatch.setattr(paths, 'DATA_MODE',    mode)
        monkeypatch.setattr(paths, 'APP_DATA_DIR', base)
        monkeypatch.setattr(paths, 'LOG_DIR',      base / 'logs')
        monkeypatch.setattr(paths, 'BACKUP_DIR',   base / 'backups')

    def test_creates_app_data_log_backup_dirs(self, tmp_path, monkeypatch):
        import src.core.paths as paths
        self._patch_dirs(monkeypatch, paths, tmp_path / 'app', mode='appdata')
        paths.ensure_dirs()
        assert (tmp_path / 'app').is_dir()
        assert (tmp_path / 'app' / 'logs').is_dir()
        assert (tmp_path / 'app' / 'backups').is_dir()

    def test_portable_mode_creates_dirs(self, tmp_path, monkeypatch):
        import src.core.paths as paths
        self._patch_dirs(monkeypatch, paths, tmp_path / 'data', mode='portable')
        paths.ensure_dirs()
        assert (tmp_path / 'data').is_dir()
        assert (tmp_path / 'data' / 'logs').is_dir()
        assert (tmp_path / 'data' / 'backups').is_dir()

    def test_portable_mode_raises_when_unwritable(self, tmp_path, monkeypatch):
        """portable mode must raise OSError — not silently fallback — when dir unusable."""
        import src.core.paths as paths
        # Place a file at the expected directory path so mkdir fails
        blocker = tmp_path / 'data'
        blocker.write_text('I am a file, blocking directory creation')
        self._patch_dirs(monkeypatch, paths, blocker / 'subdir', mode='portable')

        with pytest.raises(OSError, match='Portable mode'):
            paths.ensure_dirs()

    def test_appdata_mode_mkdir_failure_propagates_naturally(self, tmp_path, monkeypatch):
        """appdata mode: OSError from mkdir propagates without wrapping."""
        import src.core.paths as paths
        blocker = tmp_path / 'app'
        blocker.write_text('file blocking dir')
        self._patch_dirs(monkeypatch, paths, blocker / 'sub', mode='appdata')

        with pytest.raises(OSError) as exc_info:
            paths.ensure_dirs()
        # Should NOT contain the 'Portable mode' prefix (that's only for portable)
        assert 'Portable mode' not in str(exc_info.value)

    def test_does_not_create_base_dir(self, tmp_path, monkeypatch):
        """ensure_dirs() must not create BASE_DIR, ASSETS_DIR, or QSS dirs."""
        import src.core.paths as paths
        fake_base = tmp_path / 'base'
        self._patch_dirs(monkeypatch, paths, tmp_path / 'app', mode='appdata')
        monkeypatch.setattr(paths, 'BASE_DIR',   fake_base)
        monkeypatch.setattr(paths, 'ASSETS_DIR', fake_base / 'assets')
        monkeypatch.setattr(paths, 'QSS_PATH',   fake_base / 'src' / 'ui' / 'main.qss')

        paths.ensure_dirs()

        assert not fake_base.exists()

    def test_idempotent(self, tmp_path, monkeypatch):
        """Calling ensure_dirs() twice must not raise."""
        import src.core.paths as paths
        self._patch_dirs(monkeypatch, paths, tmp_path / 'app', mode='appdata')
        paths.ensure_dirs()
        paths.ensure_dirs()  # second call should be a no-op


# ===========================================================================
# Reload integration tests — verify module-level constants after reload
# ===========================================================================

_MISSING = object()


@pytest.fixture()
def frozen_exe(tmp_path):
    """Patch sys to simulate a frozen exe running from tmp_path, reload paths module.
    Restores sys attrs and reloads the module in teardown.
    """
    import src.core.paths as paths_module

    orig_frozen   = getattr(sys, 'frozen',    _MISSING)
    orig_exe      = sys.executable
    orig_meipass  = getattr(sys, '_MEIPASS',  _MISSING)

    sys.frozen     = True
    sys.executable = str(tmp_path / 'FloatDeskRemind.exe')
    sys._MEIPASS   = str(tmp_path / '_internal')

    importlib.reload(paths_module)
    yield paths_module, tmp_path

    # --- teardown: restore sys then reload to original state ---
    if orig_frozen is _MISSING:
        try:
            del sys.frozen
        except AttributeError:
            pass
    else:
        sys.frozen = orig_frozen

    sys.executable = orig_exe

    if orig_meipass is _MISSING:
        try:
            del sys._MEIPASS
        except AttributeError:
            pass
    else:
        sys._MEIPASS = orig_meipass

    importlib.reload(paths_module)


class TestModuleLevelConstants:
    def test_appdata_mode_no_flag(self, frozen_exe):
        """No portable.flag → DATA_MODE='appdata', APP_DATA_DIR is FloatDeskRemind."""
        paths_module, _ = frozen_exe
        assert paths_module.DATA_MODE == 'appdata'
        assert paths_module.APP_DATA_DIR.name == 'FloatDeskRemind'

    def test_portable_mode_with_flag(self, frozen_exe):
        """portable.flag present → all writable dirs under exe/data."""
        paths_module, tmp_path = frozen_exe
        (tmp_path / 'portable.flag').write_text('')
        importlib.reload(paths_module)

        assert paths_module.DATA_MODE == 'portable'
        assert paths_module.APP_DATA_DIR == tmp_path / 'data'
        assert paths_module.DB_PATH      == tmp_path / 'data' / 'floatdesk.db'
        assert paths_module.LOG_DIR      == tmp_path / 'data' / 'logs'
        assert paths_module.BACKUP_DIR   == tmp_path / 'data' / 'backups'

    def test_base_dir_points_to_meipass(self, frozen_exe):
        """In frozen mode, BASE_DIR must equal _MEIPASS, not APP_DATA_DIR."""
        paths_module, tmp_path = frozen_exe
        assert paths_module.BASE_DIR == tmp_path / '_internal'
        assert paths_module.BASE_DIR != paths_module.APP_DATA_DIR

    def test_writable_paths_not_under_meipass(self, frozen_exe):
        """DB_PATH, LOG_DIR, BACKUP_DIR must all be outside _MEIPASS."""
        paths_module, tmp_path = frozen_exe
        meipass = tmp_path / '_internal'
        for writable in (paths_module.DB_PATH, paths_module.LOG_DIR, paths_module.BACKUP_DIR):
            assert not str(writable).startswith(str(meipass)), (
                f'{writable.name} must not be inside _MEIPASS ({meipass})'
            )

    def test_exe_dir_is_exe_parent_in_frozen(self, frozen_exe):
        """EXE_DIR == directory containing the EXE in frozen mode."""
        paths_module, tmp_path = frozen_exe
        assert paths_module.EXE_DIR == tmp_path

    def test_portable_flag_removed_reverts_to_appdata(self, frozen_exe):
        """Removing portable.flag and reloading reverts to appdata mode."""
        paths_module, tmp_path = frozen_exe
        flag = tmp_path / 'portable.flag'
        flag.write_text('')
        importlib.reload(paths_module)
        assert paths_module.DATA_MODE == 'portable'

        flag.unlink()
        importlib.reload(paths_module)
        assert paths_module.DATA_MODE == 'appdata'
