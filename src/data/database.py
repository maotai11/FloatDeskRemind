"""
Database connection management with WAL mode and migration runner.
Each call to get_connection() returns a fresh thread-safe connection.

transaction() provides a reusable Unit-of-Work context:
  - isolation_level=None (autocommit) so BEGIN/COMMIT/ROLLBACK are fully explicit
  - Pragmas applied BEFORE BEGIN (PRAGMA journal_mode cannot run inside a transaction)
  - On exception: ROLLBACK then re-raise, guaranteeing atomicity
  - Callers must NOT call conn.commit() or conn.rollback() inside the block

Migration auto-discovery (run_migrations):
  Scans src.data.migrations for modules named v[digit]*.py, validates each
  module's VERSION attribute, and executes pending migrations sorted by VERSION.
  No manual registration in this file is needed when adding new migration files.

VERSION rules — enforced at startup, raise RuntimeError on any violation:
  - Each module must define VERSION (missing → error)
  - VERSION must be int; bool is explicitly rejected (bool is int subclass)
  - VERSION must be >= 1
  - No two modules may share the same VERSION
  - Each module must expose a callable run(conn) function
"""
import sqlite3
import types
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Generator, List, Tuple

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


# ---------------------------------------------------------------------------
# Migration auto-discovery helpers
# ---------------------------------------------------------------------------

def _load_migration_modules(
    pkg: Any = None,
) -> List[Tuple[str, types.ModuleType]]:
    """Scan the migrations package and return (name, module) pairs.

    Only loads modules whose names start with 'v' followed by a digit
    (e.g. v001_initial, v002_soft_delete_index).  Package sub-packages,
    __init__, and helper files are silently skipped.

    pkg: optional package object for testing (defaults to src.data.migrations).
    """
    import pkgutil
    import importlib

    if pkg is None:
        import src.data.migrations as pkg  # noqa: PLC0415

    result: List[Tuple[str, types.ModuleType]] = []
    for _, name, is_pkg in pkgutil.iter_modules(pkg.__path__):
        if is_pkg:
            continue
        # Accept only v<digit>... names — filters out __init__, helpers, etc.
        if not (name.startswith('v') and len(name) > 1 and name[1].isdigit()):
            continue
        full_name = f'{pkg.__name__}.{name}'
        mod = importlib.import_module(full_name)
        result.append((name, mod))
    return result


def _validate_and_sort_migrations(
    named_modules: List[Tuple[str, types.ModuleType]],
) -> List[Tuple[int, types.ModuleType]]:
    """Validate VERSION attributes and return [(version, module)] sorted ascending.

    Raises RuntimeError for any of:
      - Missing VERSION attribute
      - VERSION is bool (bool is int subclass — must be rejected explicitly)
      - VERSION is not int
      - VERSION < 1
      - Duplicate VERSION values across modules
      - Missing or non-callable run() function

    An empty input list is valid and returns [].
    """
    validated: List[Tuple[int, types.ModuleType, str]] = []

    for name, mod in named_modules:
        # --- VERSION presence ---
        if not hasattr(mod, 'VERSION'):
            raise RuntimeError(
                f"Migration {name!r}: missing VERSION attribute. "
                f"Add VERSION = <positive int> to the module."
            )
        version = mod.VERSION

        # --- VERSION type — bool must be rejected before int check ---
        if isinstance(version, bool):
            raise RuntimeError(
                f"Migration {name!r}: VERSION must be int, got bool. "
                f"Use an integer literal, e.g. VERSION = 1."
            )
        if not isinstance(version, int):
            raise RuntimeError(
                f"Migration {name!r}: VERSION must be int, "
                f"got {type(version).__name__!r}"
            )

        # --- VERSION range ---
        if version < 1:
            raise RuntimeError(
                f"Migration {name!r}: VERSION must be >= 1, got {version}"
            )

        # --- run() callable ---
        run_fn = getattr(mod, 'run', None)
        if run_fn is None or not callable(run_fn):
            raise RuntimeError(
                f"Migration {name!r}: missing or non-callable run(conn) function"
            )

        validated.append((version, mod, name))

    # --- Duplicate VERSION check ---
    seen: dict = {}
    for version, _, name in validated:
        if version in seen:
            raise RuntimeError(
                f"Duplicate VERSION {version}: "
                f"found in {seen[version]!r} and {name!r}"
            )
        seen[version] = name

    # Sort by VERSION — execution order is determined by VERSION, not filename
    validated.sort(key=lambda x: x[0])
    return [(v, mod) for v, mod, _ in validated]


def run_migrations(db_path: Path = None) -> None:
    """Run all pending migrations in order.

    Migrations are auto-discovered from src.data.migrations, validated, and
    sorted by module.VERSION.  No manual registration in this file is required
    when adding new migration files — just drop a v*.py with VERSION and run().

    Raises RuntimeError if:
      - Any module fails VERSION validation
      - Any migration's run() raises an exception
    """
    ensure_dirs()

    named_modules = _load_migration_modules()
    migrations = _validate_and_sort_migrations(named_modules)

    current = get_current_version(db_path)
    logger.info(f'DB version: {current}, available: {[v for v, _ in migrations]}')

    for version, module in migrations:
        if current >= version:
            continue
        logger.info(f'Running migration v{version:03d}')
        try:
            with get_connection(db_path) as conn:
                module.run(conn)
        except Exception as e:
            raise RuntimeError(f'資料庫初始化失敗（版本 {version}）') from e
        logger.info(f'Migration v{version:03d} done')
