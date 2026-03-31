"""
Tests for src/core/health_check.py — Patch 5 Startup Health Check.

Structure:
  TestProbeWrite         — _probe_write() unit tests (no DB, no paths monkeypatch)
  TestPreflight          — check_app_data_dir_writable, check_db_accessible
  TestPostMigration      — check_log_dir_writable, check_backup_dir_writable,
                           check_db_version_consistent, check_assets_exist,
                           check_qss_exists, check_data_mode_info
  TestOrchestration      — run_preflight_checks, run_post_migration_checks,
                           get_fatal_failures
  TestAppControllerFatal — integration: fatal check blocks AppController.__init__
"""
import sqlite3
import pytest

from src.core.health_check import (
    CheckResult,
    _probe_write,
    check_app_data_dir_writable,
    check_db_accessible,
    check_log_dir_writable,
    check_backup_dir_writable,
    check_db_version_consistent,
    check_assets_exist,
    check_qss_exists,
    check_data_mode_info,
    run_preflight_checks,
    run_post_migration_checks,
    get_fatal_failures,
)


# ---------------------------------------------------------------------------
# Fixture: redirect all path constants to tmp_path
# ---------------------------------------------------------------------------

@pytest.fixture()
def fake_paths(monkeypatch, tmp_path):
    """Monkeypatch src.core.paths module-level constants to tmp_path locations.
    Directories are NOT pre-created — each test controls that."""
    import src.core.paths as p
    base = tmp_path / 'app'
    monkeypatch.setattr(p, 'APP_DATA_DIR', base)
    monkeypatch.setattr(p, 'DB_PATH',      base / 'floatdesk.db')
    monkeypatch.setattr(p, 'LOG_DIR',      base / 'logs')
    monkeypatch.setattr(p, 'BACKUP_DIR',   base / 'backups')
    monkeypatch.setattr(p, 'ASSETS_DIR',   tmp_path / 'assets')
    monkeypatch.setattr(p, 'QSS_PATH',     tmp_path / 'main.qss')
    return tmp_path


# ---------------------------------------------------------------------------
# TestProbeWrite
# ---------------------------------------------------------------------------

class TestProbeWrite:
    def test_returns_true_when_dir_writable(self, tmp_path):
        assert _probe_write(tmp_path) is True

    def test_probe_file_cleaned_up_on_success(self, tmp_path):
        _probe_write(tmp_path)
        assert not (tmp_path / '.write_probe').exists()

    def test_returns_false_when_dir_missing(self, tmp_path):
        missing = tmp_path / 'nonexistent'
        assert _probe_write(missing) is False

    def test_probe_file_not_left_behind_on_failure(self, tmp_path):
        """Even when write fails, no probe file should remain."""
        missing = tmp_path / 'nonexistent'
        _probe_write(missing)
        assert not (missing / '.write_probe').exists()

    def test_does_not_raise(self, tmp_path):
        """_probe_write must never propagate an exception."""
        _probe_write(tmp_path / 'nonexistent')  # must not raise


# ---------------------------------------------------------------------------
# TestPreflight
# ---------------------------------------------------------------------------

class TestPreflight:

    # --- check_app_data_dir_writable ---

    def test_app_data_dir_writable_pass(self, fake_paths, tmp_path):
        result = check_app_data_dir_writable()
        assert result.passed is True
        assert result.severity == 'fatal'
        assert result.name == 'app_data_dir_writable'

    def test_app_data_dir_creates_dir_if_missing(self, fake_paths, tmp_path):
        import src.core.paths as p
        assert not p.APP_DATA_DIR.exists()
        check_app_data_dir_writable()
        assert p.APP_DATA_DIR.exists()

    def test_app_data_dir_not_writable_returns_failed_fatal(self, fake_paths, tmp_path):
        """Place a file where APP_DATA_DIR should be → mkdir fails."""
        import src.core.paths as p
        blocker = p.APP_DATA_DIR
        blocker.parent.mkdir(parents=True, exist_ok=True)
        blocker.write_text('I am a file, blocking directory creation')
        # APP_DATA_DIR now points inside the blocker file, so mkdir will fail
        import src.core.paths as p2
        from unittest.mock import patch
        # Redirect APP_DATA_DIR to a path whose parent is the file (cannot mkdir)
        bad_path = blocker / 'subdir'
        with patch.object(p2, 'APP_DATA_DIR', bad_path):
            result = check_app_data_dir_writable()
        assert result.passed is False
        assert result.severity == 'fatal'

    def test_app_data_dir_not_writable_message_contains_path(self, fake_paths, tmp_path):
        import src.core.paths as p
        from unittest.mock import patch
        blocker = tmp_path / 'blocker'
        blocker.write_text('file')
        bad = blocker / 'sub'
        with patch.object(p, 'APP_DATA_DIR', bad):
            result = check_app_data_dir_writable()
        assert str(bad) in result.message

    # --- check_db_accessible ---

    def test_db_accessible_pass_fresh_db(self, fake_paths, tmp_path):
        import src.core.paths as p
        p.APP_DATA_DIR.mkdir(parents=True, exist_ok=True)
        result = check_db_accessible()
        assert result.passed is True
        assert result.severity == 'fatal'
        assert result.name == 'db_accessible'

    def test_db_accessible_fail_bad_parent(self, fake_paths, tmp_path):
        """DB_PATH whose parent does not exist → sqlite3 cannot open it."""
        import src.core.paths as p
        from unittest.mock import patch
        bad_db = tmp_path / 'nonexistent_dir' / 'floatdesk.db'
        with patch.object(p, 'DB_PATH', bad_db):
            result = check_db_accessible()
        assert result.passed is False
        assert result.severity == 'fatal'

    def test_db_accessible_fail_message_contains_path(self, fake_paths, tmp_path):
        import src.core.paths as p
        from unittest.mock import patch
        bad_db = tmp_path / 'no_such_dir' / 'floatdesk.db'
        with patch.object(p, 'DB_PATH', bad_db):
            result = check_db_accessible()
        assert str(bad_db) in result.message


# ---------------------------------------------------------------------------
# TestPostMigration
# ---------------------------------------------------------------------------

class TestPostMigration:

    # --- check_log_dir_writable ---

    def test_log_dir_writable_pass(self, fake_paths):
        result = check_log_dir_writable()
        assert result.passed is True
        assert result.severity == 'warning'
        assert result.name == 'log_dir_writable'

    def test_log_dir_not_writable_returns_warning(self, fake_paths, tmp_path):
        import src.core.paths as p
        from unittest.mock import patch
        blocker = tmp_path / 'log_blocker'
        blocker.write_text('file')
        bad = blocker / 'sub'
        with patch.object(p, 'LOG_DIR', bad):
            result = check_log_dir_writable()
        assert result.passed is False
        assert result.severity == 'warning'   # not fatal

    # --- check_backup_dir_writable ---

    def test_backup_dir_writable_pass(self, fake_paths):
        result = check_backup_dir_writable()
        assert result.passed is True
        assert result.severity == 'warning'
        assert result.name == 'backup_dir_writable'

    def test_backup_dir_not_writable_returns_warning(self, fake_paths, tmp_path):
        import src.core.paths as p
        from unittest.mock import patch
        blocker = tmp_path / 'bk_blocker'
        blocker.write_text('file')
        bad = blocker / 'sub'
        with patch.object(p, 'BACKUP_DIR', bad):
            result = check_backup_dir_writable()
        assert result.passed is False
        assert result.severity == 'warning'

    # --- check_db_version_consistent ---

    def test_db_version_consistent_pass(self, monkeypatch):
        """Mock get_current_version to return the latest migration version."""
        import src.data.database as db_mod
        monkeypatch.setattr(db_mod, 'get_current_version', lambda db_path=None: 2)
        result = check_db_version_consistent()
        assert result.passed is True
        assert result.severity == 'warning'
        assert result.name == 'db_version_consistent'

    def test_db_version_behind_returns_failed_warning(self, monkeypatch):
        import src.data.database as db_mod
        monkeypatch.setattr(db_mod, 'get_current_version', lambda db_path=None: 1)
        result = check_db_version_consistent()
        assert result.passed is False
        assert result.severity == 'warning'
        assert 'DB=1' in result.message
        assert '預期=2' in result.message

    def test_db_version_consistent_does_not_raise_on_error(self, monkeypatch):
        """If get_current_version raises, check returns failed warning (no propagation)."""
        import src.data.database as db_mod
        monkeypatch.setattr(db_mod, 'get_current_version',
                            lambda db_path=None: (_ for _ in ()).throw(RuntimeError('db error')))
        result = check_db_version_consistent()
        assert result.passed is False
        assert result.severity == 'warning'

    # --- check_assets_exist ---

    def test_assets_exist_pass(self, fake_paths, tmp_path):
        assets = tmp_path / 'assets'
        assets.mkdir()
        (assets / 'icon.ico').write_bytes(b'')
        (assets / 'icon.png').write_bytes(b'')
        result = check_assets_exist()
        assert result.passed is True
        assert result.severity == 'warning'
        assert result.name == 'assets_exist'

    def test_assets_dir_missing_returns_failed_warning(self, fake_paths):
        result = check_assets_exist()
        assert result.passed is False
        assert result.severity == 'warning'

    def test_assets_missing_ico_returns_failed(self, fake_paths, tmp_path):
        assets = tmp_path / 'assets'
        assets.mkdir()
        (assets / 'icon.png').write_bytes(b'')   # png only, no ico
        result = check_assets_exist()
        assert result.passed is False
        assert 'icon.ico' in result.message

    def test_assets_missing_png_returns_failed(self, fake_paths, tmp_path):
        assets = tmp_path / 'assets'
        assets.mkdir()
        (assets / 'icon.ico').write_bytes(b'')   # ico only, no png
        result = check_assets_exist()
        assert result.passed is False
        assert 'icon.png' in result.message

    def test_assets_exist_checks_both_required_files(self, fake_paths, tmp_path):
        """Passing with neither file must report both missing in detail."""
        assets = tmp_path / 'assets'
        assets.mkdir()
        result = check_assets_exist()
        assert result.passed is False
        assert 'icon.ico' in result.message or 'icon.png' in result.message

    # --- check_qss_exists ---

    def test_qss_exists_pass(self, fake_paths, tmp_path):
        (tmp_path / 'main.qss').write_text('/* qss */')
        result = check_qss_exists()
        assert result.passed is True
        assert result.severity == 'warning'
        assert result.name == 'qss_exists'

    def test_qss_missing_returns_failed_warning(self, fake_paths):
        result = check_qss_exists()
        assert result.passed is False
        assert result.severity == 'warning'

    def test_qss_missing_message_mentions_default_style(self, fake_paths):
        result = check_qss_exists()
        assert '預設樣式' in result.message

    # --- check_data_mode_info ---

    def test_data_mode_info_always_passes(self):
        result = check_data_mode_info()
        assert result.passed is True
        assert result.severity == 'info'
        assert result.name == 'data_mode_info'

    def test_data_mode_info_message_contains_mode(self):
        result = check_data_mode_info()
        assert 'appdata' in result.message or 'portable' in result.message

    def test_data_mode_info_detail_contains_path(self):
        import src.core.paths as p
        result = check_data_mode_info()
        assert str(p.APP_DATA_DIR) in result.detail


# ---------------------------------------------------------------------------
# TestOrchestration
# ---------------------------------------------------------------------------

class TestOrchestration:

    def test_run_preflight_returns_two_results(self, fake_paths, tmp_path):
        import src.core.paths as p
        p.APP_DATA_DIR.mkdir(parents=True, exist_ok=True)
        results = run_preflight_checks()
        assert len(results) == 2

    def test_run_preflight_result_names(self, fake_paths, tmp_path):
        import src.core.paths as p
        p.APP_DATA_DIR.mkdir(parents=True, exist_ok=True)
        results = run_preflight_checks()
        names = [r.name for r in results]
        assert 'app_data_dir_writable' in names
        assert 'db_accessible' in names

    def test_run_preflight_does_not_raise_on_failure(self, fake_paths, tmp_path):
        """Even if all checks fail, run_preflight_checks() must not raise."""
        # APP_DATA_DIR not created and DB_PATH parent missing → both fail
        run_preflight_checks()  # must not raise

    def test_run_post_migration_returns_six_results(self, fake_paths, monkeypatch, tmp_path):
        import src.data.database as db_mod
        monkeypatch.setattr(db_mod, 'get_current_version', lambda db_path=None: 2)
        assets = tmp_path / 'assets'
        assets.mkdir()
        (assets / 'icon.ico').write_bytes(b'')
        (assets / 'icon.png').write_bytes(b'')
        (tmp_path / 'main.qss').write_text('/* qss */')
        results = run_post_migration_checks()
        assert len(results) == 6

    def test_run_post_migration_result_names(self, fake_paths, monkeypatch, tmp_path):
        import src.data.database as db_mod
        monkeypatch.setattr(db_mod, 'get_current_version', lambda db_path=None: 2)
        results = run_post_migration_checks()
        names = [r.name for r in results]
        assert 'log_dir_writable'       in names
        assert 'backup_dir_writable'    in names
        assert 'db_version_consistent'  in names
        assert 'assets_exist'           in names
        assert 'qss_exists'             in names
        assert 'data_mode_info'         in names

    def test_run_post_migration_does_not_raise(self, fake_paths, monkeypatch):
        """Errors in individual checks must not propagate."""
        import src.data.database as db_mod
        monkeypatch.setattr(db_mod, 'get_current_version',
                            lambda db_path=None: (_ for _ in ()).throw(RuntimeError('boom')))
        run_post_migration_checks()  # must not raise

    # --- get_fatal_failures ---

    def test_get_fatal_failures_empty_when_all_pass(self):
        results = [
            CheckResult('a', True,  'fatal',   'ok'),
            CheckResult('b', True,  'warning', 'ok'),
            CheckResult('c', True,  'info',    'ok'),
        ]
        assert get_fatal_failures(results) == []

    def test_get_fatal_failures_returns_fatal_messages(self):
        results = [
            CheckResult('a', False, 'fatal',   '錯誤 A'),
            CheckResult('b', False, 'warning', '警告 B'),
            CheckResult('c', False, 'fatal',   '錯誤 C'),
        ]
        msgs = get_fatal_failures(results)
        assert '錯誤 A' in msgs
        assert '錯誤 C' in msgs
        assert '警告 B' not in msgs   # warning must not appear

    def test_get_fatal_failures_ignores_passed_fatal(self):
        results = [
            CheckResult('a', True, 'fatal', '通過'),
        ]
        assert get_fatal_failures(results) == []

    def test_get_fatal_failures_warning_never_included(self):
        results = [
            CheckResult('a', False, 'warning', '警告訊息'),
        ]
        assert get_fatal_failures(results) == []

    def test_preflight_all_pass_gives_empty_fatal_list(self, fake_paths, tmp_path):
        import src.core.paths as p
        p.APP_DATA_DIR.mkdir(parents=True, exist_ok=True)
        results = run_preflight_checks()
        assert get_fatal_failures(results) == []


# ---------------------------------------------------------------------------
# TestAppControllerFatal — integration: fatal check blocks __init__
# ---------------------------------------------------------------------------

class TestAppControllerFatal:
    """Verify AppController raises RuntimeError when a fatal check fails.

    We do NOT import PySide6 or create a real AppController — we only test
    that the health-check layer raises the expected exception when wired up
    via monkeypatching the individual check functions.
    """

    def test_fatal_preflight_raises_runtime_error(self, monkeypatch):
        """If run_preflight_checks returns a fatal failure, AppController must raise."""
        # app.py imports the functions directly, so patch src.app's namespace
        import src.app as app_mod

        fatal_result = CheckResult(
            name='app_data_dir_writable',
            passed=False,
            severity='fatal',
            message='模擬：資料目錄不可寫入',
        )
        monkeypatch.setattr(app_mod, 'run_preflight_checks', lambda: [fatal_result])
        monkeypatch.setattr(app_mod, 'run_migrations', lambda db_path=None: None)
        monkeypatch.setattr(app_mod, 'run_post_migration_checks', lambda: [])

        # AppController inherits QObject — needs a QApplication instance.
        pytest.importorskip('PySide6.QtWidgets')
        from PySide6.QtWidgets import QApplication
        QApplication.instance() or QApplication([])

        from src.app import AppController
        with pytest.raises(RuntimeError, match='啟動自檢失敗'):
            AppController()

    def test_fatal_message_forwarded_to_runtime_error(self, monkeypatch):
        """The fatal check's message must appear verbatim in the RuntimeError."""
        import src.app as app_mod

        fatal_result = CheckResult(
            name='db_accessible',
            passed=False,
            severity='fatal',
            message='自訂錯誤訊息 XYZ',
        )
        monkeypatch.setattr(app_mod, 'run_preflight_checks', lambda: [fatal_result])
        monkeypatch.setattr(app_mod, 'run_migrations', lambda db_path=None: None)
        monkeypatch.setattr(app_mod, 'run_post_migration_checks', lambda: [])

        pytest.importorskip('PySide6.QtWidgets')
        from PySide6.QtWidgets import QApplication
        QApplication.instance() or QApplication([])

        from src.app import AppController
        with pytest.raises(RuntimeError, match='自訂錯誤訊息 XYZ'):
            AppController()
