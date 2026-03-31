"""
Tests for src/core/backup.py and src/services/backup_service.py — Patch 6A.
"""
from __future__ import annotations

import re
import sqlite3
import time
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import pytest

from src.core.backup import (
    BackupError,
    BackupInfo,
    _integrity_check,
    _make_backup_filename,
    _parse_backup_filename,
    check_last_auto_backup_time,
    create_backup,
    list_backups,
    prune_old_backups,
)
from src.services.backup_service import BackupService


_FILENAME_RE = re.compile(r'^floatdesk_(auto|manual|safety)_\d{8}_\d{6}_\d{6}\.db$')


@pytest.fixture
def db(tmp_path):
    """Migrated DB in tmp_path."""
    from src.data.database import run_migrations
    db_path = tmp_path / 'test.db'
    run_migrations(db_path)
    return db_path


@pytest.fixture
def bdir(tmp_path):
    """Backup dir path — NOT pre-created, to test auto-creation."""
    return tmp_path / 'backups'


# ===========================================================================
# TestMakeFilename
# ===========================================================================
class TestMakeFilename:
    def test_auto_matches_pattern(self):
        assert _FILENAME_RE.match(_make_backup_filename('auto'))

    def test_manual_matches_pattern(self):
        assert _FILENAME_RE.match(_make_backup_filename('manual'))

    def test_safety_matches_pattern(self):
        assert _FILENAME_RE.match(_make_backup_filename('safety'))

    def test_has_microsecond_segment(self):
        name = _make_backup_filename('auto')
        # floatdesk _ auto _ YYYYMMDD _ HHMMSS _ ffffff .db
        parts = name.replace('.db', '').split('_')
        assert len(parts) == 5
        assert len(parts[4]) == 6   # microseconds are exactly 6 digits

    def test_successive_calls_do_not_raise(self):
        # Rapid calls must not crash even if some share a microsecond
        names = [_make_backup_filename('auto') for _ in range(10)]
        assert len(names) == 10


# ===========================================================================
# TestParseFilename
# ===========================================================================
class TestParseFilename:
    def test_valid_auto(self):
        result = _parse_backup_filename('floatdesk_auto_20260327_143022_123456.db')
        assert result is not None
        label, dt = result
        assert label == 'auto'
        assert dt == datetime(2026, 3, 27, 14, 30, 22, 123456)

    def test_valid_manual(self):
        result = _parse_backup_filename('floatdesk_manual_20260327_143022_000000.db')
        assert result is not None
        assert result[0] == 'manual'

    def test_valid_safety(self):
        result = _parse_backup_filename('floatdesk_safety_20260327_143022_999999.db')
        assert result is not None
        assert result[0] == 'safety'

    def test_old_format_returns_none(self):
        # Pre-6A naming: floatdesk_2026-03-27.db
        assert _parse_backup_filename('floatdesk_2026-03-27.db') is None

    def test_random_string_returns_none(self):
        assert _parse_backup_filename('notabackup.db') is None

    def test_wrong_extension_returns_none(self):
        assert _parse_backup_filename('floatdesk_auto_20260327_143022_123456.txt') is None

    def test_missing_microseconds_returns_none(self):
        assert _parse_backup_filename('floatdesk_auto_20260327_143022.db') is None

    def test_filenames_sort_lexicographically_by_time(self):
        names = [
            'floatdesk_auto_20260327_100000_000000.db',
            'floatdesk_auto_20260327_120000_000000.db',
            'floatdesk_auto_20260326_150000_000000.db',
        ]
        sorted_names = sorted(names)
        times = [_parse_backup_filename(n)[1] for n in sorted_names]
        assert times == sorted(times)


# ===========================================================================
# TestIntegrityCheck
# ===========================================================================
class TestIntegrityCheck:
    def test_pass_on_migrated_db(self, db):
        assert _integrity_check(db) is True

    def test_fail_on_corrupt_file(self, tmp_path):
        bad = tmp_path / 'corrupt.db'
        bad.write_bytes(b'this is not a sqlite file at all' * 10)
        assert _integrity_check(bad) is False

    def test_fail_on_empty_file(self, tmp_path):
        empty = tmp_path / 'empty.db'
        empty.write_bytes(b'')
        assert _integrity_check(empty) is False

    def test_fail_when_no_db_version_table(self, tmp_path):
        path = tmp_path / 'noversion.db'
        conn = sqlite3.connect(str(path))
        conn.execute('CREATE TABLE foo (id INTEGER PRIMARY KEY)')
        conn.commit()
        conn.close()
        assert _integrity_check(path) is False

    def test_never_raises_on_nonexistent(self, tmp_path):
        # sqlite3.connect creates an empty file → no db_version → False
        result = _integrity_check(tmp_path / 'ghost.db')
        assert isinstance(result, bool)

    def test_never_raises_on_directory(self, tmp_path):
        result = _integrity_check(tmp_path)
        assert isinstance(result, bool)

    def test_never_raises_on_garbage_input(self, tmp_path):
        path = tmp_path / 'garbage.db'
        path.write_bytes(bytes(range(256)))
        assert isinstance(_integrity_check(path), bool)


# ===========================================================================
# TestCreateBackup
# ===========================================================================
class TestCreateBackup:
    def test_creates_file(self, db, bdir):
        path = create_backup(db, bdir, 'auto')
        assert path.exists()

    def test_auto_creates_backup_dir(self, db, bdir):
        assert not bdir.exists()
        create_backup(db, bdir, 'auto')
        assert bdir.exists()

    def test_filename_matches_pattern(self, db, bdir):
        path = create_backup(db, bdir, 'auto')
        assert _FILENAME_RE.match(path.name)

    def test_manual_label_in_filename(self, db, bdir):
        path = create_backup(db, bdir, 'manual')
        assert path.name.startswith('floatdesk_manual_')

    def test_safety_label_in_filename(self, db, bdir):
        path = create_backup(db, bdir, 'safety')
        assert path.name.startswith('floatdesk_safety_')

    def test_output_passes_integrity_check(self, db, bdir):
        path = create_backup(db, bdir, 'auto')
        assert _integrity_check(path)

    def test_output_is_queryable_sqlite(self, db, bdir):
        path = create_backup(db, bdir, 'auto')
        conn = sqlite3.connect(str(path))
        assert conn.execute('SELECT 1').fetchone() == (1,)
        conn.close()

    def test_backup_contains_db_version(self, db, bdir):
        path = create_backup(db, bdir, 'auto')
        conn = sqlite3.connect(str(path))
        count = conn.execute('SELECT COUNT(*) FROM db_version').fetchone()[0]
        conn.close()
        assert count >= 1

    def test_invalid_label_raises(self, db, bdir):
        with pytest.raises(BackupError, match='無效的 backup label'):
            create_backup(db, bdir, 'bad_label')

    def test_nonexistent_db_raises(self, tmp_path, bdir):
        with pytest.raises(BackupError, match='來源 DB 不存在'):
            create_backup(tmp_path / 'nope.db', bdir, 'auto')

    def test_never_overwrites_on_collision(self, db, bdir):
        """If the same microsecond filename is generated twice, second call raises."""
        fixed = datetime(2026, 3, 27, 14, 30, 22, 123456)

        class FakeDT:
            @staticmethod
            def now():
                return fixed
            strptime = staticmethod(datetime.strptime)

        with patch('src.core.backup.datetime', FakeDT):
            create_backup(db, bdir, 'auto')
            with pytest.raises(BackupError, match='已存在'):
                create_backup(db, bdir, 'auto')

    def test_wal_mode_backup_with_active_connection(self, db, bdir):
        """Backup must produce a consistent snapshot even with a live connection open."""
        live_conn = sqlite3.connect(str(db))
        live_conn.execute('PRAGMA journal_mode=WAL')
        try:
            path = create_backup(db, bdir, 'auto')
            assert _integrity_check(path)
        finally:
            live_conn.close()

    def test_integrity_failure_cleans_partial_file(self, db, bdir):
        """If integrity check fails, no file is left behind."""
        with patch('src.core.backup._integrity_check', return_value=False):
            with pytest.raises(BackupError, match='完整性驗證失敗'):
                create_backup(db, bdir, 'auto')
        if bdir.exists():
            assert list(bdir.glob('floatdesk_*.db')) == []


# ===========================================================================
# TestListBackups
# ===========================================================================
class TestListBackups:
    def test_empty_dir_returns_empty(self, bdir):
        bdir.mkdir()
        assert list_backups(bdir) == []

    def test_nonexistent_dir_returns_empty(self, bdir):
        assert not bdir.exists()
        assert list_backups(bdir) == []

    def test_returns_backupinfo_objects(self, db, bdir):
        create_backup(db, bdir, 'auto')
        results = list_backups(bdir)
        assert len(results) == 1
        assert isinstance(results[0], BackupInfo)

    def test_sorted_newest_first(self, db, bdir):
        p1 = create_backup(db, bdir, 'auto')
        time.sleep(0.002)
        p2 = create_backup(db, bdir, 'manual')
        results = list_backups(bdir)
        assert results[0].path == p2
        assert results[1].path == p1

    def test_filter_auto(self, db, bdir):
        create_backup(db, bdir, 'auto')
        create_backup(db, bdir, 'manual')
        results = list_backups(bdir, label='auto')
        assert all(r.label == 'auto' for r in results)
        assert len(results) == 1

    def test_filter_manual(self, db, bdir):
        create_backup(db, bdir, 'auto')
        create_backup(db, bdir, 'manual')
        results = list_backups(bdir, label='manual')
        assert len(results) == 1 and results[0].label == 'manual'

    def test_filter_safety(self, db, bdir):
        create_backup(db, bdir, 'safety')
        results = list_backups(bdir, label='safety')
        assert len(results) == 1 and results[0].label == 'safety'

    def test_none_label_returns_all(self, db, bdir):
        create_backup(db, bdir, 'auto')
        create_backup(db, bdir, 'manual')
        create_backup(db, bdir, 'safety')
        assert len(list_backups(bdir)) == 3

    def test_unparseable_files_skipped(self, bdir):
        bdir.mkdir()
        (bdir / 'floatdesk_2026-03-27.db').write_bytes(b'')   # old format
        (bdir / 'random_garbage.db').write_bytes(b'')
        assert list_backups(bdir) == []

    def test_created_at_matches_filename(self, db, bdir):
        path = create_backup(db, bdir, 'auto')
        results = list_backups(bdir)
        assert results[0].created_at == _parse_backup_filename(path.name)[1]

    def test_path_in_result_matches_actual_file(self, db, bdir):
        path = create_backup(db, bdir, 'auto')
        results = list_backups(bdir)
        assert results[0].path == path


# ===========================================================================
# TestPruneOldBackups
# ===========================================================================
class TestPruneOldBackups:
    def test_prune_keeps_n_newest(self, db, bdir):
        for _ in range(5):
            create_backup(db, bdir, 'auto')
            time.sleep(0.002)
        pruned = prune_old_backups(bdir, 'auto', keep=3)
        assert len(pruned) == 2
        assert len(list_backups(bdir, label='auto')) == 3

    def test_prune_does_not_affect_other_labels(self, db, bdir):
        for _ in range(4):
            create_backup(db, bdir, 'auto')
            time.sleep(0.002)
        create_backup(db, bdir, 'manual')
        prune_old_backups(bdir, 'auto', keep=2)
        assert len(list_backups(bdir, label='manual')) == 1

    def test_prune_under_keep_limit_deletes_nothing(self, db, bdir):
        create_backup(db, bdir, 'auto')
        assert prune_old_backups(bdir, 'auto', keep=7) == []

    def test_prune_returns_deleted_paths(self, db, bdir):
        for _ in range(3):
            create_backup(db, bdir, 'auto')
            time.sleep(0.002)
        pruned = prune_old_backups(bdir, 'auto', keep=1)
        assert len(pruned) == 2
        for p in pruned:
            assert not p.exists()

    def test_safety_not_pruned_by_auto_prune_call(self, db, bdir):
        for _ in range(4):
            create_backup(db, bdir, 'auto')
            time.sleep(0.002)
        create_backup(db, bdir, 'safety')
        prune_old_backups(bdir, 'auto', keep=2)
        assert len(list_backups(bdir, label='safety')) == 1

    def test_safety_can_be_explicitly_pruned(self, db, bdir):
        for _ in range(4):
            create_backup(db, bdir, 'safety')
            time.sleep(0.002)
        pruned = prune_old_backups(bdir, 'safety', keep=2)
        assert len(pruned) == 2


# ===========================================================================
# TestCheckLastAutoBackupTime
# ===========================================================================
class TestCheckLastAutoBackupTime:
    def test_returns_none_when_no_auto_backups(self, bdir):
        bdir.mkdir()
        assert check_last_auto_backup_time(bdir) is None

    def test_returns_none_when_dir_missing(self, bdir):
        assert check_last_auto_backup_time(bdir) is None

    def test_returns_datetime_of_newest_auto(self, db, bdir):
        create_backup(db, bdir, 'auto')
        time.sleep(0.002)
        p2 = create_backup(db, bdir, 'auto')
        last = check_last_auto_backup_time(bdir)
        assert last == _parse_backup_filename(p2.name)[1]

    def test_not_affected_by_manual_backup(self, db, bdir):
        create_backup(db, bdir, 'auto')
        time.sleep(0.002)
        create_backup(db, bdir, 'manual')
        last = check_last_auto_backup_time(bdir)
        auto_backups = list_backups(bdir, label='auto')
        assert last == auto_backups[0].created_at

    def test_not_affected_by_safety_snapshot(self, db, bdir):
        create_backup(db, bdir, 'auto')
        time.sleep(0.002)
        create_backup(db, bdir, 'safety')
        last = check_last_auto_backup_time(bdir)
        auto_backups = list_backups(bdir, label='auto')
        assert last == auto_backups[0].created_at


# ===========================================================================
# TestBackupService
# ===========================================================================
class TestBackupService:
    @pytest.fixture
    def svc(self, db, bdir):
        return BackupService(db, bdir)

    def test_manual_backup_creates_file(self, svc, bdir):
        path = svc.manual_backup()
        assert path.exists()
        assert path.name.startswith('floatdesk_manual_')

    def test_manual_backup_output_passes_integrity(self, svc):
        path = svc.manual_backup()
        assert _integrity_check(path)

    def test_manual_backup_raises_on_bad_db(self, tmp_path, bdir):
        svc = BackupService(tmp_path / 'nope.db', bdir)
        with pytest.raises(BackupError):
            svc.manual_backup()

    def test_auto_backup_creates_on_first_run(self, svc):
        path = svc.auto_backup_if_needed()
        assert path is not None and path.exists()

    def test_auto_backup_skips_within_interval(self, svc):
        svc.auto_backup_if_needed(interval_hours=24)
        result = svc.auto_backup_if_needed(interval_hours=24)
        assert result is None   # within 24h interval

    def test_auto_backup_only_checks_auto_timestamp(self, svc):
        """A manual backup must NOT prevent auto backup from running."""
        svc.manual_backup()
        path = svc.auto_backup_if_needed()
        assert path is not None

    def test_auto_backup_failure_returns_none_not_raise(self, tmp_path, bdir):
        """auto_backup_if_needed must be non-fatal even when DB is missing."""
        svc = BackupService(tmp_path / 'nope.db', bdir)
        assert svc.auto_backup_if_needed() is None

    def test_auto_backup_prunes_to_7(self, svc, bdir, monkeypatch):
        """After 8 forced auto backups + prune, only 7 remain."""
        monkeypatch.setattr(
            'src.services.backup_service.check_last_auto_backup_time',
            lambda bd: None,   # always trigger backup
        )
        for _ in range(8):
            svc.auto_backup_if_needed()
            time.sleep(0.002)
        assert len(list_backups(bdir, label='auto')) == 7

    def test_manual_backup_prunes_to_14(self, svc, bdir):
        """After 15 manual backups, only 14 remain."""
        for _ in range(15):
            svc.manual_backup()
            time.sleep(0.002)
        assert len(list_backups(bdir, label='manual')) == 14

    def test_list_backups_excludes_safety(self, svc, db, bdir):
        svc.manual_backup()
        svc.auto_backup_if_needed()
        create_backup(db, bdir, 'safety')   # add safety directly
        results = svc.list_backups()
        assert all(r.label in ('auto', 'manual') for r in results)
        assert not any(r.label == 'safety' for r in results)

    def test_list_backups_sorted_newest_first(self, svc):
        svc.auto_backup_if_needed()
        time.sleep(0.002)
        svc.manual_backup()
        results = svc.list_backups()
        assert results[0].label == 'manual'
        assert results[1].label == 'auto'

    def test_list_backups_empty_on_fresh_dir(self, db, bdir):
        svc = BackupService(db, bdir)
        assert svc.list_backups() == []
