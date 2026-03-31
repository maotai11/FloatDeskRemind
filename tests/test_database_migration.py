"""
Test database migrations: idempotency, version correctness, and auto-discovery.

TestValidateAndSort  — unit tests for _validate_and_sort_migrations() using
                       in-memory mock modules (no DB, no disk I/O).
TestAutoDiscovery    — integration tests for _load_migration_modules() against
                       the real src.data.migrations package.
(top-level functions) — existing smoke tests kept for regression coverage.
"""
import types
import sqlite3
import pytest

from src.data.database import (
    run_migrations,
    get_current_version,
    _load_migration_modules,
    _validate_and_sort_migrations,
)


# ---------------------------------------------------------------------------
# Helper: build a throw-away module object
# ---------------------------------------------------------------------------

_UNSET = object()  # sentinel for "attribute not set"


def _make_module(name: str, *, version=_UNSET, run=_UNSET) -> tuple:
    """Return (name, module) with optional VERSION and run attributes."""
    mod = types.ModuleType(name)
    if version is not _UNSET:
        mod.VERSION = version
    if run is not _UNSET:
        mod.run = run
    return (name, mod)


# ---------------------------------------------------------------------------
# Existing regression tests (kept intact)
# ---------------------------------------------------------------------------

def test_migration_creates_tables(tmp_path):
    db = tmp_path / 'test.db'
    run_migrations(db)
    conn = sqlite3.connect(str(db))
    tables = {row[0] for row in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    )}
    conn.close()
    assert 'tasks' in tables
    assert 'task_tags' in tables
    assert 'task_reminders' in tables
    assert 'task_phases' in tables
    assert 'settings' in tables
    assert 'db_version' in tables


def test_migration_version(tmp_path):
    db = tmp_path / 'test.db'
    run_migrations(db)
    assert get_current_version(db) == 2


def test_migration_idempotent(tmp_path):
    db = tmp_path / 'test.db'
    run_migrations(db)
    run_migrations(db)  # second run must not fail or change version
    assert get_current_version(db) == 2


def test_default_settings_inserted(tmp_path):
    db = tmp_path / 'test.db'
    run_migrations(db)
    conn = sqlite3.connect(str(db))
    conn.row_factory = sqlite3.Row
    rows = {r['key']: r['value'] for r in conn.execute('SELECT key, value FROM settings')}
    conn.close()
    assert rows['theme'] == 'light'
    assert rows['font_size'] == 'medium'
    assert rows['float_opacity'] == '0.95'


# ---------------------------------------------------------------------------
# TestValidateAndSort — pure unit tests, no DB, no disk
# ---------------------------------------------------------------------------

class TestValidateAndSort:
    """Tests for _validate_and_sort_migrations() using mock module objects."""

    # ── Happy-path ──────────────────────────────────────────────────────────

    def test_empty_input_returns_empty(self):
        assert _validate_and_sort_migrations([]) == []

    def test_single_valid_module(self):
        mods = [_make_module('v001', version=1, run=lambda c: None)]
        result = _validate_and_sort_migrations(mods)
        assert len(result) == 1
        assert result[0][0] == 1

    def test_sorts_by_version_not_input_order(self):
        """Modules given in reverse order must be sorted by VERSION ascending."""
        mods = [
            _make_module('v003', version=3, run=lambda c: None),
            _make_module('v001', version=1, run=lambda c: None),
            _make_module('v002', version=2, run=lambda c: None),
        ]
        result = _validate_and_sort_migrations(mods)
        assert [v for v, _ in result] == [1, 2, 3]

    def test_non_consecutive_versions_allowed(self):
        """Gap in sequence (1, 3) is valid — only duplicates are rejected."""
        mods = [
            _make_module('v001', version=1, run=lambda c: None),
            _make_module('v003', version=3, run=lambda c: None),
        ]
        result = _validate_and_sort_migrations(mods)
        assert [v for v, _ in result] == [1, 3]

    def test_high_version_number_allowed(self):
        mods = [_make_module('v099', version=99, run=lambda c: None)]
        result = _validate_and_sort_migrations(mods)
        assert result[0][0] == 99

    # ── VERSION missing ─────────────────────────────────────────────────────

    def test_missing_version_raises(self):
        mods = [_make_module('v001', run=lambda c: None)]  # no VERSION
        with pytest.raises(RuntimeError, match="missing VERSION"):
            _validate_and_sort_migrations(mods)

    def test_missing_version_names_the_module(self):
        mods = [_make_module('v007_bad', run=lambda c: None)]
        with pytest.raises(RuntimeError, match="v007_bad"):
            _validate_and_sort_migrations(mods)

    # ── VERSION wrong type ──────────────────────────────────────────────────

    def test_version_string_raises(self):
        mods = [_make_module('v001', version='1', run=lambda c: None)]
        with pytest.raises(RuntimeError, match="must be int"):
            _validate_and_sort_migrations(mods)

    def test_version_float_raises(self):
        mods = [_make_module('v001', version=1.0, run=lambda c: None)]
        with pytest.raises(RuntimeError, match="must be int"):
            _validate_and_sort_migrations(mods)

    def test_version_none_raises(self):
        mods = [_make_module('v001', version=None, run=lambda c: None)]
        with pytest.raises(RuntimeError, match="must be int"):
            _validate_and_sort_migrations(mods)

    def test_version_bool_true_raises(self):
        """bool is a subclass of int — True must be rejected explicitly."""
        mods = [_make_module('v001', version=True, run=lambda c: None)]
        with pytest.raises(RuntimeError, match="got bool"):
            _validate_and_sort_migrations(mods)

    def test_version_bool_false_raises(self):
        """False is also bool and must be rejected (would also fail >= 1 check)."""
        mods = [_make_module('v001', version=False, run=lambda c: None)]
        with pytest.raises(RuntimeError, match="got bool"):
            _validate_and_sort_migrations(mods)

    # ── VERSION range ───────────────────────────────────────────────────────

    def test_version_zero_raises(self):
        mods = [_make_module('v001', version=0, run=lambda c: None)]
        with pytest.raises(RuntimeError, match=">= 1"):
            _validate_and_sort_migrations(mods)

    def test_version_negative_raises(self):
        mods = [_make_module('v001', version=-5, run=lambda c: None)]
        with pytest.raises(RuntimeError, match=">= 1"):
            _validate_and_sort_migrations(mods)

    # ── Duplicate VERSION ───────────────────────────────────────────────────

    def test_duplicate_version_raises(self):
        mods = [
            _make_module('v001a', version=1, run=lambda c: None),
            _make_module('v001b', version=1, run=lambda c: None),
        ]
        with pytest.raises(RuntimeError, match="Duplicate VERSION 1"):
            _validate_and_sort_migrations(mods)

    def test_duplicate_version_error_names_both_modules(self):
        mods = [
            _make_module('v002_alpha', version=2, run=lambda c: None),
            _make_module('v002_beta',  version=2, run=lambda c: None),
        ]
        with pytest.raises(RuntimeError) as exc_info:
            _validate_and_sort_migrations(mods)
        msg = str(exc_info.value)
        assert 'v002_alpha' in msg or 'v002_beta' in msg

    def test_three_modules_two_duplicates_raises(self):
        mods = [
            _make_module('v001', version=1, run=lambda c: None),
            _make_module('v002a', version=2, run=lambda c: None),
            _make_module('v002b', version=2, run=lambda c: None),
        ]
        with pytest.raises(RuntimeError, match="Duplicate VERSION 2"):
            _validate_and_sort_migrations(mods)

    # ── run() callable ──────────────────────────────────────────────────────

    def test_missing_run_raises(self):
        mods = [_make_module('v001', version=1)]  # no run attr
        with pytest.raises(RuntimeError, match="non-callable run"):
            _validate_and_sort_migrations(mods)

    def test_non_callable_run_string_raises(self):
        mods = [_make_module('v001', version=1, run='not_a_function')]
        with pytest.raises(RuntimeError, match="non-callable run"):
            _validate_and_sort_migrations(mods)

    def test_non_callable_run_integer_raises(self):
        mods = [_make_module('v001', version=1, run=42)]
        with pytest.raises(RuntimeError, match="non-callable run"):
            _validate_and_sort_migrations(mods)

    def test_run_none_raises(self):
        mods = [_make_module('v001', version=1, run=None)]
        with pytest.raises(RuntimeError, match="non-callable run"):
            _validate_and_sort_migrations(mods)

    # ── First-failing module is reported ────────────────────────────────────

    def test_first_bad_module_in_list_is_reported(self):
        """Validation stops at the first error (missing VERSION)."""
        mods = [
            _make_module('v001_good', version=1, run=lambda c: None),
            _make_module('v002_bad',  run=lambda c: None),  # missing VERSION
            _make_module('v003_good', version=3, run=lambda c: None),
        ]
        with pytest.raises(RuntimeError, match="v002_bad"):
            _validate_and_sort_migrations(mods)


# ---------------------------------------------------------------------------
# TestAutoDiscovery — integration tests against real migrations package
# ---------------------------------------------------------------------------

class TestAutoDiscovery:
    def test_discovers_both_production_migrations(self):
        """_load_migration_modules() finds v001 and v002 in the real package."""
        modules = _load_migration_modules()
        names = [n for n, _ in modules]
        assert 'v001_initial' in names
        assert 'v002_soft_delete_index' in names

    def test_discovery_count_matches_files(self):
        """Exactly 2 migration files exist in the package."""
        modules = _load_migration_modules()
        assert len(modules) == 2

    def test_discovered_modules_pass_validation(self):
        """All production modules pass _validate_and_sort_migrations."""
        modules = _load_migration_modules()
        result = _validate_and_sort_migrations(modules)
        assert len(result) == 2
        assert [v for v, _ in result] == [1, 2]

    def test_discovery_sorts_by_version_not_filesystem_order(self):
        """Sorted output is VERSION order regardless of pkgutil scan order."""
        modules = _load_migration_modules()
        result = _validate_and_sort_migrations(modules)
        versions = [v for v, _ in result]
        assert versions == sorted(versions)

    def test_run_migrations_fresh_db(self, tmp_path):
        """Fresh DB reaches latest version after run_migrations."""
        db = tmp_path / 'fresh.db'
        run_migrations(db)
        assert get_current_version(db) == 2

    def test_run_migrations_upgrade_from_v1(self, tmp_path):
        """DB already at v1 → run_migrations applies only v2 without re-running v1."""
        db = tmp_path / 'upgrade.db'
        # Bring DB to v1 state manually
        run_migrations(db)
        conn = sqlite3.connect(str(db))
        conn.execute('DELETE FROM db_version WHERE version > 1')
        conn.execute('DROP INDEX IF EXISTS idx_tasks_status_deleted_at')
        conn.commit()
        conn.close()
        assert get_current_version(db) == 1

        run_migrations(db)
        assert get_current_version(db) == 2

        # Verify the v2 index now exists
        conn = sqlite3.connect(str(db))
        idx = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' "
            "AND name='idx_tasks_status_deleted_at'"
        ).fetchone()
        conn.close()
        assert idx is not None

    def test_run_migrations_already_at_latest_is_noop(self, tmp_path):
        """DB at latest version: second run changes nothing."""
        db = tmp_path / 'noop.db'
        run_migrations(db)
        version_before = get_current_version(db)
        run_migrations(db)
        assert get_current_version(db) == version_before

    def test_skips_non_migration_files(self):
        """__init__.py and helper files (not v<digit>*) are not loaded."""
        modules = _load_migration_modules()
        names = [n for n, _ in modules]
        assert '__init__' not in names
        for name in names:
            assert name.startswith('v') and name[1].isdigit(), (
                f"Non-migration module leaked into results: {name!r}"
            )
