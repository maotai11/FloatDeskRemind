"""
Database connection management with WAL mode and migration runner.
Each call to get_connection() returns a fresh thread-safe connection.
"""
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Generator

from src.core.paths import DB_PATH, ensure_dirs
from src.core.logger import logger


def _apply_pragmas(conn: sqlite3.Connection) -> None:
    conn.execute('PRAGMA journal_mode=WAL')
    conn.execute('PRAGMA foreign_keys=ON')
    conn.execute('PRAGMA synchronous=NORMAL')
    conn.row_factory = sqlite3.Row


@contextmanager
def get_connection(db_path: Path = None) -> Generator[sqlite3.Connection, None, None]:
    """Context manager: yields a fresh SQLite connection, closes on exit."""
    path = db_path or DB_PATH
    conn = sqlite3.connect(str(path))
    _apply_pragmas(conn)
    try:
        yield conn
    finally:
        conn.close()


def get_current_version(db_path: Path = None) -> int:
    """Return current db_version, or 0 if table doesn't exist."""
    with get_connection(db_path) as conn:
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='db_version'"
        ).fetchone()
        if not row:
            return 0
        row = conn.execute('SELECT MAX(version) FROM db_version').fetchone()
        return row[0] if row and row[0] else 0


def run_migrations(db_path: Path = None) -> None:
    """Run all pending migrations in order."""
    ensure_dirs()
    from src.data.migrations import v001_initial

    migrations = [
        (1, v001_initial),
    ]

    current = get_current_version(db_path)
    logger.info(f'DB version: {current}')

    for version, module in migrations:
        if current < version:
            logger.info(f'Running migration v{version:03d}')
            try:
                with get_connection(db_path) as conn:
                    module.run(conn)
            except Exception as e:
                raise RuntimeError(f'資料庫初始化失敗（版本 {version}）') from e
            logger.info(f'Migration v{version:03d} done')
