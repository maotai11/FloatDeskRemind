"""
Backup utilities for FloatDesk Remind.

All public functions accept explicit db_path / backup_dir arguments.
They never read global path constants.

Backup filename format:
    floatdesk_{label}_{YYYYMMDD}_{HHMMSS}_{ffffff}.db
    - label:   'auto' | 'manual' | 'safety'
    - ffffff:  microseconds (6 digits, zero-padded)

Collision policy:
    If the destination file already exists, BackupError is raised.
    Microseconds make collision essentially impossible (< 1e-6 / second per label),
    but we never silently overwrite.
"""
from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from src.core.logger import logger

_VALID_LABELS = frozenset({'auto', 'manual', 'safety'})
_FILENAME_RE = re.compile(
    r'^floatdesk_(auto|manual|safety)_(\d{8})_(\d{6})_(\d{6})\.db$'
)


@dataclass(frozen=True)
class BackupInfo:
    path: Path
    label: str          # 'auto' | 'manual' | 'safety'
    created_at: datetime


class BackupError(Exception):
    """Raised when any backup operation fails."""


# ---------------------------------------------------------------------------
# Filename helpers
# ---------------------------------------------------------------------------

def _make_backup_filename(label: str) -> str:
    """Return 'floatdesk_{label}_{YYYYMMDD}_{HHMMSS}_{ffffff}.db'.

    Microseconds reduce same-second collision probability to < 1e-6.
    Callers must still check for pre-existing files (we never overwrite).
    """
    ts = datetime.now().strftime('%Y%m%d_%H%M%S_%f')
    return f'floatdesk_{label}_{ts}.db'


def _parse_backup_filename(filename: str) -> Optional[tuple[str, datetime]]:
    """Parse (label, created_at) from a backup filename.

    Returns None if the filename does not match the expected pattern.
    """
    m = _FILENAME_RE.match(filename)
    if not m:
        return None
    try:
        created_at = datetime.strptime(
            f'{m.group(2)}_{m.group(3)}_{m.group(4)}', '%Y%m%d_%H%M%S_%f'
        )
    except ValueError:
        return None
    return m.group(1), created_at


# ---------------------------------------------------------------------------
# Integrity check
# ---------------------------------------------------------------------------

def _integrity_check(db_path: Path) -> bool:
    """Verify db_path is a valid, consistent SQLite DB with at least one db_version row.

    Opens a fresh connection independent of any live connections.
    Checks:
      1. PRAGMA integrity_check → must return single row 'ok'
      2. PRAGMA foreign_key_check → must return zero rows
      3. SELECT COUNT(*) FROM db_version → must be >= 1
    Never raises — returns False on any exception.
    """
    try:
        conn = sqlite3.connect(str(db_path))
        try:
            rows = conn.execute('PRAGMA integrity_check').fetchall()
            if len(rows) != 1 or rows[0][0] != 'ok':
                return False
            if conn.execute('PRAGMA foreign_key_check').fetchall():
                return False
            if conn.execute('SELECT COUNT(*) FROM db_version').fetchone()[0] < 1:
                return False
        finally:
            conn.close()
    except Exception:
        return False
    return True


# ---------------------------------------------------------------------------
# Core backup function
# ---------------------------------------------------------------------------

def create_backup(db_path: Path, backup_dir: Path, label: str) -> Path:
    """Hot-backup db_path using SQLite Online Backup API (WAL-safe).

    Steps:
      1. Validate label and db_path existence
      2. Ensure backup_dir exists (auto-created)
      3. Generate timestamped filename with microseconds
      4. Raise BackupError if destination already exists (never overwrite)
      5. sqlite3.backup() — WAL-aware, safe with live connections
      6. _integrity_check the output
      7. Return dest Path

    Partial output files are cleaned up on any failure.
    """
    if label not in _VALID_LABELS:
        raise BackupError(
            f'無效的 backup label：{label!r}，必須為 {sorted(_VALID_LABELS)}'
        )
    if not db_path.exists():
        raise BackupError(f'來源 DB 不存在：{db_path}')

    backup_dir.mkdir(parents=True, exist_ok=True)

    dest = backup_dir / _make_backup_filename(label)
    if dest.exists():
        raise BackupError(
            f'備份檔案已存在（微秒碰撞）：{dest.name}\n'
            f'策略：微秒時間戳使碰撞機率 < 10\u207b\u2076/秒，但仍需顯式拒絕覆蓋。'
        )

    try:
        src = sqlite3.connect(str(db_path))
        dst = sqlite3.connect(str(dest))
        try:
            src.backup(dst, pages=-1)
        finally:
            dst.close()
            src.close()
    except Exception as exc:
        dest.unlink(missing_ok=True)
        raise BackupError(f'SQLite backup API 失敗：{exc}') from exc

    if not _integrity_check(dest):
        dest.unlink(missing_ok=True)
        raise BackupError(f'備份完整性驗證失敗：{dest.name}')

    logger.info(f'[backup] Created {label} backup: {dest.name}')
    return dest


# ---------------------------------------------------------------------------
# List and prune
# ---------------------------------------------------------------------------

def list_backups(backup_dir: Path, label: str = None) -> List[BackupInfo]:
    """Return BackupInfo list for backup_dir, sorted newest-first.

    label=None returns all parseable files.
    Files that don't match the expected filename pattern are silently skipped
    (with a warning log).
    """
    if not backup_dir.is_dir():
        return []
    results: List[BackupInfo] = []
    for path in backup_dir.glob('floatdesk_*.db'):
        parsed = _parse_backup_filename(path.name)
        if parsed is None:
            logger.warning(f'[backup] Skipping unparseable file: {path.name}')
            continue
        file_label, created_at = parsed
        if label is not None and file_label != label:
            continue
        results.append(BackupInfo(path=path, label=file_label, created_at=created_at))
    results.sort(key=lambda b: b.created_at, reverse=True)
    return results


def prune_old_backups(backup_dir: Path, label: str, keep: int) -> List[Path]:
    """Delete oldest backups for the given label, keeping the newest `keep` files.

    Safety backups (label='safety') are only pruned if explicitly called with
    label='safety' — they are never touched by auto or manual prune calls.
    Returns list of deleted paths.
    """
    backups = list_backups(backup_dir, label=label)
    to_delete = backups[keep:]
    deleted: List[Path] = []
    for info in to_delete:
        try:
            info.path.unlink(missing_ok=True)
            deleted.append(info.path)
            logger.info(f'[backup] Pruned: {info.path.name}')
        except OSError as exc:
            logger.warning(f'[backup] Failed to prune {info.path.name}: {exc}')
    return deleted


def check_last_auto_backup_time(backup_dir: Path) -> Optional[datetime]:
    """Return the created_at of the newest 'auto' backup, or None if none exists."""
    backups = list_backups(backup_dir, label='auto')
    return backups[0].created_at if backups else None
