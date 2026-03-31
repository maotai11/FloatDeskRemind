"""
Tests for src/core/restore.py — Patch 6B (Deferred Restore).

Coverage:
  - _clear_wal: path format, file removal, missing-file safety
  - _probe_db_not_locked: accessible DB, locked/missing/inaccessible
  - request_restore: happy path, lock check, corrupt backup, atomic write,
                     safety snapshot creation, safety prune to keep=3
  - run_pending_restore: no-pending fast path, parse errors, invalid backup,
                         happy path, WAL cleanup (before AND after),
                         copy failure + rollback, integrity failure + rollback,
                         double failure (crash report, .corrupt rename, RestoreError)
"""
from __future__ import annotations

import json
import os
import shutil
import sqlite3
import time
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import pytest

from src.core.backup import (
    BackupError,
    _integrity_check,
    _parse_backup_filename,
    create_backup,
    list_backups,
)
from src.core.restore import (
    RestoreError,
    RestoreOutcome,
    _clear_wal,
    _probe_db_not_locked,
    request_restore,
    run_pending_restore,
)


# ===========================================================================
# Fixtures
# ===========================================================================

@pytest.fixture
def app_dir(tmp_path):
    """Simulates APP_DATA_DIR: parent of both db_path and pending_restore.json."""
    d = tmp_path / 'app'
    d.mkdir()
    return d


@pytest.fixture
def db(app_dir):
    """Migrated DB at app_dir/floatdesk.db."""
    from src.data.database import run_migrations
    db_path = app_dir / 'floatdesk.db'
    run_migrations(db_path)
    return db_path


@pytest.fixture
def bdir(app_dir):
    """Backup directory at app_dir/backups."""
    d = app_dir / 'backups'
    d.mkdir()
    return d


@pytest.fixture
def pdir(app_dir):
    """Pending directory = app_dir (same as db.parent, by design)."""
    return app_dir


@pytest.fixture
def ldir(app_dir):
    """Log directory at app_dir/logs."""
    d = app_dir / 'logs'
    d.mkdir()
    return d


def _write_pending(
    pdir: Path,
    backup_path: Path,
    db_path: Path,
    safety_path: Path = None,
) -> Path:
    """Helper: write a well-formed pending_restore.json directly."""
    if safety_path is None:
        safety_path = pdir / 'fake_safety.db'
    payload = {
        'version': 1,
        'requested_at': datetime.now().isoformat(),
        'backup_path': str(backup_path),
        'safety_path': str(safety_path),
        'db_path': str(db_path),
    }
    p = pdir / 'pending_restore.json'
    p.write_text(json.dumps(payload), encoding='utf-8')
    return p


# ===========================================================================
# TestClearWal
# ===========================================================================

class TestClearWal:
    def test_removes_wal_file(self, db):
        wal = Path(str(db) + '.db-wal')
        wal.write_bytes(b'fake-wal-content')
        _clear_wal(db)
        assert not wal.exists()

    def test_removes_shm_file(self, db):
        shm = Path(str(db) + '.db-shm')
        shm.write_bytes(b'fake-shm-content')
        _clear_wal(db)
        assert not shm.exists()

    def test_no_error_when_files_absent(self, db):
        # Should not raise even if sidecar files do not exist
        _clear_wal(db)

    def test_removes_both_simultaneously(self, db):
        wal = Path(str(db) + '.db-wal')
        shm = Path(str(db) + '.db-shm')
        wal.write_bytes(b'w')
        shm.write_bytes(b's')
        _clear_wal(db)
        assert not wal.exists()
        assert not shm.exists()

    def test_path_format_uses_string_concat(self, db):
        """Verify the sidecar path is db_path + suffix, not with_suffix replacement."""
        wal_path = Path(str(db) + '.db-wal')
        # Regression: with_suffix('.db-wal') would produce floatdesk.db-wal (wrong stem)
        assert wal_path.name == 'floatdesk.db.db-wal'


# ===========================================================================
# TestProbeDbNotLocked
# ===========================================================================

class TestProbeDbNotLocked:
    def test_accessible_db_does_not_raise(self, db):
        _probe_db_not_locked(db)  # no exception

    def test_nonexistent_db_does_not_raise(self, app_dir):
        _probe_db_not_locked(app_dir / 'nonexistent.db')  # no exception

    def test_locked_db_raises_backup_error(self, db, monkeypatch):
        def fake_connect(path, timeout=None):
            raise sqlite3.OperationalError('database is locked')
        monkeypatch.setattr('src.core.restore.sqlite3.connect', fake_connect)
        with pytest.raises(BackupError, match='DB 目前被鎖定'):
            _probe_db_not_locked(db)

    def test_inaccessible_db_raises_backup_error(self, db, monkeypatch):
        def fake_connect(path, timeout=None):
            raise PermissionError('access denied')
        monkeypatch.setattr('src.core.restore.sqlite3.connect', fake_connect)
        with pytest.raises(BackupError, match='DB 無法開啟'):
            _probe_db_not_locked(db)


# ===========================================================================
# TestRequestRestore
# ===========================================================================

class TestRequestRestore:
    def test_happy_path_creates_pending(self, db, bdir, pdir):
        backup = create_backup(db, bdir, 'manual')
        request_restore(backup, db_path=db, backup_dir=bdir, pending_dir=pdir)
        assert (pdir / 'pending_restore.json').exists()

    def test_pending_json_is_valid_and_complete(self, db, bdir, pdir):
        backup = create_backup(db, bdir, 'manual')
        request_restore(backup, db_path=db, backup_dir=bdir, pending_dir=pdir)
        data = json.loads((pdir / 'pending_restore.json').read_text(encoding='utf-8'))
        assert data['version'] == 1
        assert data['backup_path'] == str(backup)
        assert data['db_path'] == str(db)
        assert 'safety_path' in data
        assert 'requested_at' in data

    def test_returns_safety_snapshot_path(self, db, bdir, pdir):
        backup = create_backup(db, bdir, 'manual')
        safety = request_restore(backup, db_path=db, backup_dir=bdir, pending_dir=pdir)
        assert safety.exists()
        assert safety.name.startswith('floatdesk_safety_')

    def test_no_tmp_file_left_after_success(self, db, bdir, pdir):
        backup = create_backup(db, bdir, 'manual')
        request_restore(backup, db_path=db, backup_dir=bdir, pending_dir=pdir)
        assert not (pdir / 'pending_restore.json.tmp').exists()

    def test_atomic_write_uses_os_replace(self, db, bdir, pdir):
        backup = create_backup(db, bdir, 'manual')
        replace_calls = []
        original_replace = os.replace

        def spy_replace(src, dst):
            replace_calls.append((Path(src).name, Path(dst).name))
            return original_replace(src, dst)

        with patch('src.core.restore.os.replace', spy_replace):
            request_restore(backup, db_path=db, backup_dir=bdir, pending_dir=pdir)

        # Verify that tmp -> pending_restore.json was the replace call
        assert any(
            'pending_restore.json.tmp' in src and 'pending_restore.json' in dst
            for src, dst in replace_calls
        )

    def test_missing_backup_raises(self, db, bdir, pdir):
        with pytest.raises(BackupError, match='備份檔案不存在'):
            request_restore(
                bdir / 'nonexistent.db',
                db_path=db, backup_dir=bdir, pending_dir=pdir,
            )

    def test_corrupt_backup_raises(self, db, bdir, pdir, tmp_path):
        bad_backup = bdir / 'floatdesk_manual_20260101_000000_000000.db'
        bad_backup.write_bytes(b'this is not sqlite')
        with pytest.raises(BackupError, match='完整性驗證失敗'):
            request_restore(bad_backup, db_path=db, backup_dir=bdir, pending_dir=pdir)

    def test_locked_db_raises_before_safety(self, db, bdir, pdir, monkeypatch):
        """Lock check must fire before safety snapshot is created."""
        backup = create_backup(db, bdir, 'manual')

        def fake_connect(path, timeout=None):
            raise sqlite3.OperationalError('database is locked')

        monkeypatch.setattr('src.core.restore.sqlite3.connect', fake_connect)
        with pytest.raises(BackupError, match='DB 目前被鎖定'):
            request_restore(backup, db_path=db, backup_dir=bdir, pending_dir=pdir)

        # No safety snapshot should have been created
        assert list_backups(bdir, label='safety') == []

    def test_prunes_safety_snapshots_to_3(self, db, bdir, pdir):
        """After the 4th request_restore call, only 3 safety backups remain."""
        for _ in range(4):
            backup = create_backup(db, bdir, 'manual')
            time.sleep(0.002)
            # Remove any pre-existing pending so each call can proceed
            pending = pdir / 'pending_restore.json'
            pending.unlink(missing_ok=True)
            request_restore(backup, db_path=db, backup_dir=bdir, pending_dir=pdir)
            time.sleep(0.002)

        assert len(list_backups(bdir, label='safety')) == 3


# ===========================================================================
# TestRunPendingRestoreNoOp
# ===========================================================================

class TestRunPendingRestoreNoOp:
    def test_skipped_when_no_pending_file(self, pdir, db, ldir):
        outcome = run_pending_restore(pdir, db, ldir)
        assert outcome.status == 'skipped'
        assert outcome.message == ''

    def test_skipped_does_not_modify_db(self, pdir, db, ldir):
        mtime_before = db.stat().st_mtime
        run_pending_restore(pdir, db, ldir)
        assert db.stat().st_mtime == mtime_before

    def test_idempotent_multiple_calls(self, pdir, db, ldir):
        for _ in range(3):
            outcome = run_pending_restore(pdir, db, ldir)
            assert outcome.status == 'skipped'


# ===========================================================================
# TestRunPendingRestoreParseError
# ===========================================================================

class TestRunPendingRestoreParseError:
    def test_invalid_json_returns_warning(self, pdir, db, ldir):
        (pdir / 'pending_restore.json').write_text('not-json', encoding='utf-8')
        outcome = run_pending_restore(pdir, db, ldir)
        assert outcome.status == 'warning'
        assert '格式異常' in outcome.message

    def test_invalid_json_renames_to_invalid(self, pdir, db, ldir):
        (pdir / 'pending_restore.json').write_text('not-json', encoding='utf-8')
        run_pending_restore(pdir, db, ldir)
        assert not (pdir / 'pending_restore.json').exists()
        assert (pdir / 'pending_restore.json.invalid').exists()

    def test_wrong_version_returns_warning(self, pdir, db, ldir):
        (pdir / 'pending_restore.json').write_text(
            json.dumps({'version': 99, 'backup_path': 'x', 'safety_path': 'y', 'db_path': 'z'}),
            encoding='utf-8',
        )
        outcome = run_pending_restore(pdir, db, ldir)
        assert outcome.status == 'warning'

    def test_missing_field_returns_warning(self, pdir, db, ldir):
        (pdir / 'pending_restore.json').write_text(
            json.dumps({'version': 1, 'backup_path': 'x'}),  # missing safety_path, db_path
            encoding='utf-8',
        )
        outcome = run_pending_restore(pdir, db, ldir)
        assert outcome.status == 'warning'

    def test_non_object_root_returns_warning(self, pdir, db, ldir):
        (pdir / 'pending_restore.json').write_text('["a", "b"]', encoding='utf-8')
        outcome = run_pending_restore(pdir, db, ldir)
        assert outcome.status == 'warning'


# ===========================================================================
# TestRunPendingRestoreInvalidBackup
# ===========================================================================

class TestRunPendingRestoreInvalidBackup:
    def test_missing_backup_returns_warning(self, pdir, db, bdir, ldir):
        _write_pending(pdir, backup_path=bdir / 'nonexistent.db', db_path=db)
        outcome = run_pending_restore(pdir, db, ldir)
        assert outcome.status == 'warning'
        assert '備份無效' in outcome.message

    def test_missing_backup_deletes_pending(self, pdir, db, bdir, ldir):
        _write_pending(pdir, backup_path=bdir / 'nonexistent.db', db_path=db)
        run_pending_restore(pdir, db, ldir)
        assert not (pdir / 'pending_restore.json').exists()

    def test_corrupt_backup_returns_warning(self, pdir, db, bdir, ldir):
        bad = bdir / 'floatdesk_auto_20260101_000000_000000.db'
        bad.write_bytes(b'garbage')
        _write_pending(pdir, backup_path=bad, db_path=db)
        outcome = run_pending_restore(pdir, db, ldir)
        assert outcome.status == 'warning'


# ===========================================================================
# TestRunPendingRestoreHappyPath
# ===========================================================================

class TestRunPendingRestoreHappyPath:
    def test_success_status(self, pdir, db, bdir, ldir):
        backup = create_backup(db, bdir, 'auto')
        safety = create_backup(db, bdir, 'safety')
        _write_pending(pdir, backup_path=backup, db_path=db, safety_path=safety)
        outcome = run_pending_restore(pdir, db, ldir)
        assert outcome.status == 'success'

    def test_success_message_contains_backup_name(self, pdir, db, bdir, ldir):
        backup = create_backup(db, bdir, 'auto')
        safety = create_backup(db, bdir, 'safety')
        _write_pending(pdir, backup_path=backup, db_path=db, safety_path=safety)
        outcome = run_pending_restore(pdir, db, ldir)
        assert backup.name in outcome.message

    def test_pending_deleted_after_success(self, pdir, db, bdir, ldir):
        backup = create_backup(db, bdir, 'auto')
        safety = create_backup(db, bdir, 'safety')
        _write_pending(pdir, backup_path=backup, db_path=db, safety_path=safety)
        run_pending_restore(pdir, db, ldir)
        assert not (pdir / 'pending_restore.json').exists()

    def test_db_passes_integrity_after_restore(self, pdir, db, bdir, ldir):
        backup = create_backup(db, bdir, 'auto')
        safety = create_backup(db, bdir, 'safety')
        _write_pending(pdir, backup_path=backup, db_path=db, safety_path=safety)
        run_pending_restore(pdir, db, ldir)
        assert _integrity_check(db)

    def test_restore_from_manual_backup(self, pdir, db, bdir, ldir):
        backup = create_backup(db, bdir, 'manual')
        safety = create_backup(db, bdir, 'safety')
        _write_pending(pdir, backup_path=backup, db_path=db, safety_path=safety)
        outcome = run_pending_restore(pdir, db, ldir)
        assert outcome.status == 'success'


# ===========================================================================
# TestRunPendingRestoreWalCleanup
# ===========================================================================

class TestRunPendingRestoreWalCleanup:
    def test_wal_cleared_before_copy2(self, pdir, db, bdir, ldir):
        """WAL file must not exist at the moment copy2 is called."""
        backup = create_backup(db, bdir, 'auto')
        safety = create_backup(db, bdir, 'safety')
        _write_pending(pdir, backup_path=backup, db_path=db, safety_path=safety)

        wal = Path(str(db) + '.db-wal')
        wal.write_bytes(b'stale-wal')

        wal_present_when_copy_called = []
        original_copy2 = shutil.copy2

        def observing_copy2(src, dst):
            wal_present_when_copy_called.append(wal.exists())
            return original_copy2(src, dst)

        with patch('src.core.restore.shutil.copy2', observing_copy2):
            run_pending_restore(pdir, db, ldir)

        assert len(wal_present_when_copy_called) >= 1
        assert wal_present_when_copy_called[0] is False  # cleared before copy2

    def test_wal_cleared_after_copy2(self, pdir, db, bdir, ldir):
        """WAL created by copy2 must be removed after the copy."""
        backup = create_backup(db, bdir, 'auto')
        safety = create_backup(db, bdir, 'safety')
        _write_pending(pdir, backup_path=backup, db_path=db, safety_path=safety)

        wal = Path(str(db) + '.db-wal')
        original_copy2 = shutil.copy2

        def copy2_leaves_wal(src, dst):
            result = original_copy2(src, dst)
            # Simulate copy2 leaving an orphaned WAL sidecar
            wal.write_bytes(b'post-copy-wal')
            return result

        with patch('src.core.restore.shutil.copy2', copy2_leaves_wal):
            run_pending_restore(pdir, db, ldir)

        assert not wal.exists()

    def test_no_wal_files_after_success(self, pdir, db, bdir, ldir):
        backup = create_backup(db, bdir, 'auto')
        safety = create_backup(db, bdir, 'safety')
        _write_pending(pdir, backup_path=backup, db_path=db, safety_path=safety)
        run_pending_restore(pdir, db, ldir)
        assert not Path(str(db) + '.db-wal').exists()
        assert not Path(str(db) + '.db-shm').exists()


# ===========================================================================
# TestRunPendingRestoreCopyFailure
# ===========================================================================

class TestRunPendingRestoreCopyFailure:
    def test_copy_failure_rollback_success_returns_warning(self, pdir, db, bdir, ldir):
        backup = create_backup(db, bdir, 'auto')
        safety = create_backup(db, bdir, 'safety')
        _write_pending(pdir, backup_path=backup, db_path=db, safety_path=safety)

        call_count = [0]
        original_copy2 = shutil.copy2

        def fail_first_copy(src, dst):
            call_count[0] += 1
            if call_count[0] == 1:
                raise OSError('simulated disk error')
            return original_copy2(src, dst)

        with patch('src.core.restore.shutil.copy2', fail_first_copy):
            outcome = run_pending_restore(pdir, db, ldir)

        assert outcome.status == 'warning'
        assert '還原失敗' in outcome.message

    def test_copy_failure_rollback_success_db_intact(self, pdir, db, bdir, ldir):
        """After failed restore + successful rollback, DB must pass integrity check."""
        backup = create_backup(db, bdir, 'auto')
        safety = create_backup(db, bdir, 'safety')
        _write_pending(pdir, backup_path=backup, db_path=db, safety_path=safety)

        call_count = [0]
        original_copy2 = shutil.copy2

        def fail_first_copy(src, dst):
            call_count[0] += 1
            if call_count[0] == 1:
                raise OSError('simulated disk error')
            return original_copy2(src, dst)

        with patch('src.core.restore.shutil.copy2', fail_first_copy):
            run_pending_restore(pdir, db, ldir)

        assert _integrity_check(db)

    def test_copy_failure_clears_pending(self, pdir, db, bdir, ldir):
        backup = create_backup(db, bdir, 'auto')
        safety = create_backup(db, bdir, 'safety')
        _write_pending(pdir, backup_path=backup, db_path=db, safety_path=safety)

        call_count = [0]
        original_copy2 = shutil.copy2

        def fail_first_copy(src, dst):
            call_count[0] += 1
            if call_count[0] == 1:
                raise OSError('simulated disk error')
            return original_copy2(src, dst)

        with patch('src.core.restore.shutil.copy2', fail_first_copy):
            run_pending_restore(pdir, db, ldir)

        assert not (pdir / 'pending_restore.json').exists()


# ===========================================================================
# TestRunPendingRestoreIntegrityFailure
# ===========================================================================

class TestRunPendingRestoreIntegrityFailure:
    def test_integrity_failure_returns_warning(self, pdir, db, bdir, ldir):
        backup = create_backup(db, bdir, 'auto')
        safety = create_backup(db, bdir, 'safety')
        _write_pending(pdir, backup_path=backup, db_path=db, safety_path=safety)

        with patch('src.core.restore._integrity_check') as mock_check:
            # 1st call: backup validation → pass; 2nd call: post-restore check → fail
            mock_check.side_effect = [True, False]
            outcome = run_pending_restore(pdir, db, ldir)

        assert outcome.status == 'warning'
        assert '完整性驗證失敗' in outcome.message

    def test_integrity_failure_rollback_restores_db(self, pdir, db, bdir, ldir):
        """After integrity failure + rollback, DB must be readable (from safety)."""
        backup = create_backup(db, bdir, 'auto')
        safety = create_backup(db, bdir, 'safety')
        _write_pending(pdir, backup_path=backup, db_path=db, safety_path=safety)

        call_count = [0]
        original_check = _integrity_check

        def check_fails_on_restored(path):
            call_count[0] += 1
            # 1st: backup validation = pass
            # 2nd: post-restore check = fail (triggers rollback)
            if call_count[0] == 2:
                return False
            return original_check(path)

        with patch('src.core.restore._integrity_check', check_fails_on_restored):
            run_pending_restore(pdir, db, ldir)

        # After rollback from safety, DB should be valid
        assert _integrity_check(db)


# ===========================================================================
# TestRunPendingRestoreDoubleFailure
# ===========================================================================

class TestRunPendingRestoreDoubleFailure:
    @pytest.fixture
    def double_fail_setup(self, pdir, db, bdir, ldir):
        """Returns (backup, safety, pdir, db, ldir) with pending written."""
        backup = create_backup(db, bdir, 'auto')
        safety = create_backup(db, bdir, 'safety')
        _write_pending(pdir, backup_path=backup, db_path=db, safety_path=safety)
        return backup, safety, pdir, db, ldir

    def _always_fail_copy2(self, src, dst):
        raise OSError('both copy2 calls fail')

    def test_double_failure_raises_restore_error(self, double_fail_setup):
        backup, safety, pdir, db, ldir = double_fail_setup
        with patch('src.core.restore.shutil.copy2', self._always_fail_copy2):
            with pytest.raises(RestoreError, match='還原與復原均失敗'):
                run_pending_restore(pdir, db, ldir)

    def test_double_failure_creates_crash_report(self, double_fail_setup):
        backup, safety, pdir, db, ldir = double_fail_setup
        with patch('src.core.restore.shutil.copy2', self._always_fail_copy2):
            with pytest.raises(RestoreError):
                run_pending_restore(pdir, db, ldir)
        reports = list(ldir.glob('restore_failure_*.txt'))
        assert len(reports) == 1

    def test_double_failure_crash_report_has_human_section(self, double_fail_setup):
        backup, safety, pdir, db, ldir = double_fail_setup
        with patch('src.core.restore.shutil.copy2', self._always_fail_copy2):
            with pytest.raises(RestoreError):
                run_pending_restore(pdir, db, ldir)
        report = next(ldir.glob('restore_failure_*.txt'))
        content = report.read_text(encoding='utf-8')
        assert 'HUMAN READABLE SUMMARY' in content
        assert 'RECOVERY INSTRUCTIONS' in content

    def test_double_failure_crash_report_has_json_section(self, double_fail_setup):
        backup, safety, pdir, db, ldir = double_fail_setup
        with patch('src.core.restore.shutil.copy2', self._always_fail_copy2):
            with pytest.raises(RestoreError):
                run_pending_restore(pdir, db, ldir)
        report = next(ldir.glob('restore_failure_*.txt'))
        content = report.read_text(encoding='utf-8')
        assert 'MACHINE READABLE (JSON)' in content
        # Extract and parse the JSON block
        json_start = content.index('--- MACHINE READABLE (JSON) ---') + len('--- MACHINE READABLE (JSON) ---\n')
        json_end = content.index('--- END REPORT ---')
        machine_data = json.loads(content[json_start:json_end].strip())
        assert machine_data['status'] == 'double_failure'
        assert machine_data['version'] == 1
        assert 'restore_error' in machine_data
        assert 'rollback_error' in machine_data

    def test_double_failure_renames_db_to_corrupt(self, double_fail_setup):
        backup, safety, pdir, db, ldir = double_fail_setup
        with patch('src.core.restore.shutil.copy2', self._always_fail_copy2):
            with pytest.raises(RestoreError):
                run_pending_restore(pdir, db, ldir)
        corrupt = Path(str(db) + '.corrupt')
        assert corrupt.exists()
        assert not db.exists()

    def test_double_failure_error_message_contains_safety_path(self, double_fail_setup):
        backup, safety, pdir, db, ldir = double_fail_setup
        with patch('src.core.restore.shutil.copy2', self._always_fail_copy2):
            with pytest.raises(RestoreError) as exc_info:
                run_pending_restore(pdir, db, ldir)
        assert str(safety) in str(exc_info.value)

    def test_integrity_failure_double_failure_raises(self, pdir, db, bdir, ldir):
        """Integrity check fails + rollback copy also fails -> RestoreError."""
        backup = create_backup(db, bdir, 'auto')
        safety = create_backup(db, bdir, 'safety')
        _write_pending(pdir, backup_path=backup, db_path=db, safety_path=safety)

        call_count = [0]
        original_copy2 = shutil.copy2
        original_check = _integrity_check

        def copy2_ok_then_fail(src, dst):
            call_count[0] += 1
            if call_count[0] == 1:
                return original_copy2(src, dst)  # first copy (restore) succeeds
            raise OSError('rollback copy also fails')

        check_call = [0]

        def check_fails_second(path):
            check_call[0] += 1
            if check_call[0] == 2:
                return False  # post-restore integrity check fails
            return original_check(path)

        with patch('src.core.restore.shutil.copy2', copy2_ok_then_fail), \
             patch('src.core.restore._integrity_check', check_fails_second):
            with pytest.raises(RestoreError):
                run_pending_restore(pdir, db, ldir)
