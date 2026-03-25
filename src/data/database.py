"""
Database connection management with WAL mode and migration runner.
Each call to get_connection() returns a fresh thread-safe connection.

transaction() provides a reusable Unit-of-Work context:
  - isolation_level=None (autocommit) so BEGIN/COMMIT/ROLLBACK are fully explicit
  - Pragmas applied BEFORE BEGIN (PRAGMA journal_mode cannot run inside a transaction)
  - On exception: ROLLBACK then re-raise, guaranteeing atomicity
  - Callers must NOT call conn.commit() or conn.rollback() inside the block
"""
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Generator

from src.core.paths import DB_PATH, ensure_dirs
from src.core.logger import logger


def _apply_pragmas(conn: sqlite3.Connection) -> None:
    """Apply WAL + FK + synchronous pragmas and set row_factory.
    Must be called BEFORE any BEGIN — some pragmas are disallowed inside transactions.
    """
    conn.execute('PRAGMA journal_mode=WAL')
    conn.execute('PRAGMA foreign_keys=ON')
    conn.execute('PRAGMA synchronous=NORMAL')
    conn.row_factory = sqlite3.Row


@contextmanager
def get_connection(db_path: Path = None) -> Generator[sqlite3.Connection, None, None]:
    """Yields a fresh auto-commit SQLite connection. Closes on exit.
    Use for single-statement operations where atomicity across calls is not required.
    """
    path = db_path or DB_PATH
    conn = sqlite3.connect(str(path))
    _apply_pragmas(conn)
    try:
        yield conn
    finally:
        conn.close()


@contextmanager
def transaction(db_path: Path = None) -> Generator[sqlite3.Connection, None, None]:
    """Unit-of-Work context manager.

    Yields a connection inside an explicit BEGIN / COMMIT block.
    All operations on the yielded connection are part of one atomic transaction.

    On clean exit  → COMMIT
    On exception   → ROLLBACK, then re-raise

    Usage::
        with transaction(db_path) as conn:
            repo.update(task, conn=conn)
            repo.bulk_update_status(ids, 'done', conn=conn)
        # COMMIT happens here automatically

    Caller must NOT call conn.commit() or conn.rollback() inside the block.
    """
    path = db_path or DB_PATH
    # isolation_level=None = Python's sqlite3 will NOT auto-issue BEGIN.
    # We control the transaction lifecycle entirely.
    conn = sqlite3.connect(str(path), isolation_level=None)
    _apply_pragmas(conn)
    conn.execute('BEGIN')
    try:
        yield conn
        conn.execute('COMMIT')
    except Exception:
        try:
            conn.execute('ROLLBACK')
        except Exception:
            pass  # nosec B110 — ROLLBACK on already-failed connection; best-effort
        raise
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
