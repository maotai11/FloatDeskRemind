"""
Test database migrations: idempotency and version correctness.
"""
import pytest
from src.data.database import run_migrations, get_current_version


def test_migration_creates_tables(tmp_path):
    db = tmp_path / 'test.db'
    run_migrations(db)
    import sqlite3
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
    assert get_current_version(db) == 1


def test_migration_idempotent(tmp_path):
    db = tmp_path / 'test.db'
    run_migrations(db)
    run_migrations(db)  # second run should not fail
    assert get_current_version(db) == 1


def test_default_settings_inserted(tmp_path):
    db = tmp_path / 'test.db'
    run_migrations(db)
    import sqlite3
    conn = sqlite3.connect(str(db))
    conn.row_factory = sqlite3.Row
    rows = {r['key']: r['value'] for r in conn.execute('SELECT key, value FROM settings')}
    conn.close()
    assert rows['theme'] == 'light'
    assert rows['font_size'] == 'medium'
    assert rows['float_opacity'] == '0.95'
