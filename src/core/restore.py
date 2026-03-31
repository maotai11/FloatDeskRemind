"""
Deferred Restore for FloatDesk Remind — Patch 6B.

Two-phase design:

  Phase 1 (in-app):  request_restore()
    - Validates DB is not locked (TOCTOU-aware lock probe)
    - Validates backup_path integrity (_integrity_check: structure + db_version)
    - Creates safety snapshot via create_backup(..., 'safety'), prunes to keep=3
    - Atomically writes pending_restore.json (tmp -> os.replace)
    Returns: safety snapshot Path
    Raises:  BackupError on any failure; DB and pending file are never modified

  Phase 2 (startup, before any DB connection):  run_pending_restore()
    - Fast-path returns RestoreOutcome('skipped') when no pending file exists
    - Parse errors produce RestoreOutcome('warning') — never silent
    - WAL/SHM cleared BEFORE restore (remove stale sidecars)
    - shutil.copy2(backup -> db_path)
    - WAL/SHM cleared AFTER restore (remove orphaned sidecars)
    - _integrity_check on restored DB
    - On copy or integrity failure: rollback from safety snapshot
    - On rollback failure: _handle_double_failure -> raises RestoreError
    Returns: RestoreOutcome('success' | 'skipped' | 'warning')
    Raises:  RestoreError only on double-failure (restore AND rollback both fail)

pending_restore.json placement (DB_PATH.parent / APP_DATA_DIR):
  - Guarantees os.replace atomicity (same filesystem as DB_PATH)
  - Semantic fit: it is a request about the DB, not a backup artifact
  - Accessible before any service layer is initialised (only paths.py required)
  - Works identically in portable and appdata modes

WAL/SHM files (floatdesk.db.db-wal, floatdesk.db.db-shm):
  Cleared BEFORE copy2:  removes stale sidecars from abnormal prior exits
  Cleared AFTER  copy2:  removes any orphaned sidecars that survived the copy
"""
from __future__ import annotations

import json
import os
import shutil
import sqlite3
import traceback
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

from src.core.backup import BackupError, _integrity_check, create_backup, prune_old_backups
from src.core.logger import logger
from src.core.paths import APP_DATA_DIR, BACKUP_DIR, DB_PATH, LOG_DIR


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_PENDING_FILENAME = 'pending_restore.json'
_PENDING_VERSION = 1
_SAFETY_KEEP = 3


# ---------------------------------------------------------------------------
# Public types
# ---------------------------------------------------------------------------

class RestoreError(Exception):
    """Raised only when BOTH restore and rollback fail (double-failure).

    Callers must show a critical UI message and not continue; the DB may be
    in an unknown state.  The error message includes the safety snapshot path
    and crash report path for manual recovery instructions.
    """


@dataclass
class RestoreOutcome:
    """Result of run_pending_restore().

    status: one of 'success' | 'skipped' | 'warning'
      - 'success': restore completed and verified
      - 'skipped': no pending_restore.json found (normal startup)
      - 'warning': restore attempted but failed/rolled-back, or parse error
                   — message contains user-visible explanation
    message: human-readable description (empty string for 'skipped')
    detail:  extra technical context (e.g. original exception string)
    """
    status: str
    message: str
    detail: str = field(default='')


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _clear_wal(db_path: Path) -> None:
    """Remove .db-wal and .db-shm sidecar files for db_path.

    Uses Path(str(db_path) + suffix) which is the correct SQLite sidecar naming
    convention (e.g. floatdesk.db -> floatdesk.db.db-wal, not floatdesk-wal.db).
    Failures are logged as warnings and never re-raised.
    """
    for suffix in ('.db-wal', '.db-shm'):
        sidecar = Path(str(db_path) + suffix)
        try:
            sidecar.unlink(missing_ok=True)
        except OSError as exc:
            logger.warning(f'[restore] Cannot remove {sidecar.name}: {exc}')


def _probe_db_not_locked(db_path: Path) -> None:
    """Verify the live DB is openable (not locked by another process).

    Uses a 1-second timeout so the caller is not blocked indefinitely.
    If db_path does not exist, returns immediately (no lock is possible).
    Raises BackupError if the DB is locked or otherwise inaccessible.
    """
    if not db_path.exists():
        return
    try:
        conn = sqlite3.connect(str(db_path), timeout=1.0)
        conn.execute('SELECT 1')
        conn.close()
    except sqlite3.OperationalError as exc:
        raise BackupError(f'DB 目前被鎖定，無法進行還原請求：{exc}') from exc
    except Exception as exc:
        raise BackupError(f'DB 無法開啟：{exc}') from exc


def _write_crash_report(
    db_path: Path,
    backup_path: Path,
    safety_path: Path,
    corrupt_db_path: Optional[Path],
    restore_exc: Exception,
    rollback_exc: Exception,
    log_dir: Path,
) -> Path:
    """Write a dual-format crash report (human-readable + JSON) to log_dir.

    Returns the report path even if writing failed (path is still computed).
    Never raises.
    """
    stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    report_path = log_dir / f'restore_failure_{stamp}.txt'

    restore_tb = ''.join(
        traceback.format_exception(type(restore_exc), restore_exc, restore_exc.__traceback__)
    )
    rollback_tb = ''.join(
        traceback.format_exception(type(rollback_exc), rollback_exc, rollback_exc.__traceback__)
    )
    now_iso = datetime.now().isoformat()

    machine_data = {
        'version': 1,
        'timestamp': now_iso,
        'operation': 'deferred_restore',
        'status': 'double_failure',
        'db_path': str(db_path),
        'backup_path': str(backup_path),
        'safety_path': str(safety_path),
        'corrupt_db_path': str(corrupt_db_path) if corrupt_db_path else None,
        'restore_error': str(restore_exc),
        'restore_traceback': restore_tb,
        'rollback_error': str(rollback_exc),
        'rollback_traceback': rollback_tb,
    }

    human_lines = [
        '=== FloatDesk Remind — Restore Failure Report ===',
        f'Generated: {now_iso}',
        'Version: 1.0',
        '',
        '--- HUMAN READABLE SUMMARY ---',
        'Operation: Deferred restore',
        'Status: FAILED (restore failed AND rollback failed)',
        '',
        f'DB Path:      {db_path}',
        f'Backup Path:  {backup_path}',
        f'Safety Path:  {safety_path}',
        '',
        'Restore Error:',
        f'  {restore_exc}',
        '',
        'Rollback Error:',
        f'  {rollback_exc}',
        '',
        'RECOVERY INSTRUCTIONS:',
        '  1. Close all instances of FloatDesk Remind.',
        f'  2. Navigate to: {safety_path.parent}',
        f'  3. Copy {safety_path.name}',
        f'     to: {db_path}',
        '  4. Restart FloatDesk Remind.',
        '',
        '--- MACHINE READABLE (JSON) ---',
        json.dumps(machine_data, ensure_ascii=False, indent=2),
        '--- END REPORT ---',
    ]

    try:
        log_dir.mkdir(parents=True, exist_ok=True)
        report_path.write_text('\n'.join(human_lines), encoding='utf-8')
    except Exception as exc:
        logger.warning(f'[restore] Failed to write crash report: {exc}')

    return report_path


def _handle_double_failure(
    db_path: Path,
    backup_path: Path,
    safety_path: Path,
    restore_exc: Exception,
    rollback_exc: Exception,
    log_dir: Path,
) -> None:
    """Log CRITICAL, rename corrupt DB, write crash report, raise RestoreError.

    Always raises RestoreError — never returns normally.
    """
    logger.critical('[restore] CRITICAL: both restore and rollback failed')
    logger.critical(f'[restore]   db_path:      {db_path}')
    logger.critical(f'[restore]   backup_path:  {backup_path}')
    logger.critical(f'[restore]   safety_path:  {safety_path}')
    logger.critical(f'[restore]   restore_exc:  {restore_exc!r}')
    logger.critical(f'[restore]   rollback_exc: {rollback_exc!r}')

    # Attempt to rename the (potentially-corrupt) DB so the app does not open it
    corrupt_path: Optional[Path] = None
    corrupt_dest = Path(str(db_path) + '.corrupt')
    try:
        if db_path.exists():
            os.replace(str(db_path), str(corrupt_dest))
            corrupt_path = corrupt_dest
            logger.critical(f'[restore]   corrupt DB renamed to: {corrupt_dest.name}')
    except Exception as rename_exc:
        logger.warning(f'[restore] Failed to rename corrupt DB: {rename_exc}')

    # Write dual-format crash report
    report_path = _write_crash_report(
        db_path, backup_path, safety_path, corrupt_path,
        restore_exc, rollback_exc, log_dir,
    )
    logger.critical(f'[restore]   crash report: {report_path}')

    raise RestoreError(
        f'還原與復原均失敗。\n'
        f'DB 可能損毀：{db_path}\n'
        f'安全備份位置（可手動恢復）：{safety_path}\n'
        f'詳細報告：{report_path}'
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def request_restore(
    backup_path: Path,
    db_path: Path = None,
    backup_dir: Path = None,
    pending_dir: Path = None,
) -> Path:
    """Request a deferred restore to run at the next application startup.

    Steps (all-or-nothing: any failure leaves DB and pending file unchanged):
      1. _probe_db_not_locked — verify no active lock on the live DB
      2. Validate backup_path exists and passes _integrity_check
      3. create_backup(..., 'safety') — pre-restore snapshot
      4. prune_old_backups('safety', keep=3) — cap safety snapshots
      5. Atomically write pending_restore.json (write tmp, then os.replace)

    Returns:
      Path to the safety snapshot (for caller confirmation messages).

    Raises:
      BackupError — DB locked, backup corrupt/missing, or I/O failure.
    """
    _db_path = db_path or DB_PATH
    _backup_dir = backup_dir or BACKUP_DIR
    _pending_dir = pending_dir or APP_DATA_DIR

    # Step 1: lock check
    _probe_db_not_locked(_db_path)

    # Step 2: validate backup
    if not backup_path.exists():
        raise BackupError(f'備份檔案不存在：{backup_path}')
    if not _integrity_check(backup_path):
        raise BackupError(f'備份完整性驗證失敗，無法還原：{backup_path.name}')

    # Step 3 & 4: safety snapshot + prune
    safety_path = create_backup(_db_path, _backup_dir, 'safety')
    prune_old_backups(_backup_dir, 'safety', keep=_SAFETY_KEEP)

    # Step 5: atomic write of pending_restore.json
    pending = _pending_dir / _PENDING_FILENAME
    tmp = _pending_dir / f'{_PENDING_FILENAME}.tmp'

    payload = {
        'version': _PENDING_VERSION,
        'requested_at': datetime.now().isoformat(),
        'backup_path': str(backup_path),
        'safety_path': str(safety_path),
        'db_path': str(_db_path),
    }
    try:
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
        os.replace(str(tmp), str(pending))
    except Exception as exc:
        tmp.unlink(missing_ok=True)
        raise BackupError(f'寫入還原請求失敗：{exc}') from exc

    logger.info(f'[restore] Restore requested: {backup_path.name} → {_db_path.name}')
    logger.info(f'[restore] Safety snapshot: {safety_path.name}')
    return safety_path


def run_pending_restore(
    pending_dir: Path = None,
    db_path: Path = None,
    log_dir: Path = None,
) -> RestoreOutcome:
    """Execute any pending restore at startup, before any DB connections.

    Must be called BEFORE run_migrations() so the migration runs on the
    restored database, not the pre-restore one.

    Returns RestoreOutcome — never raises EXCEPT on double-failure
    (RestoreError), which callers must treat as fatal.

    RestoreOutcome.status values:
      'skipped' — no pending_restore.json (fast path, normal startup)
      'warning' — parse error, invalid backup, restore failed/rolled-back
      'success' — restore completed and integrity-verified
    """
    _pending_dir = pending_dir or APP_DATA_DIR
    _db_path = db_path or DB_PATH
    _log_dir = log_dir or LOG_DIR
    pending = _pending_dir / _PENDING_FILENAME

    # ---- Fast path ----
    if not pending.exists():
        return RestoreOutcome('skipped', '')

    # ---- Parse JSON ----
    try:
        raw = pending.read_text(encoding='utf-8')
        data = json.loads(raw)
        if not isinstance(data, dict):
            raise ValueError('root must be a JSON object')
        if data.get('version') != _PENDING_VERSION:
            raise ValueError(f"unsupported version: {data.get('version')!r}")
        for required in ('backup_path', 'safety_path', 'db_path'):
            if required not in data:
                raise KeyError(f'missing required field: {required!r}')
    except Exception as parse_exc:
        logger.error(f'[restore] pending_restore.json 格式無效：{parse_exc}')
        invalid_path = pending.with_suffix('.json.invalid')
        try:
            os.replace(str(pending), str(invalid_path))
        except Exception as mv_exc:
            logger.warning(f'[restore] Cannot rename invalid pending file: {mv_exc}')
        return RestoreOutcome(
            'warning',
            f'上次還原請求的記錄檔格式異常，已自動跳過。\n'
            f'若您需要還原，請重新執行還原操作。\n'
            f'無效記錄檔位置：{invalid_path}',
            detail=str(parse_exc),
        )

    _restore_db_path = Path(data['db_path'])
    backup_path = Path(data['backup_path'])
    safety_path = Path(data['safety_path'])

    # ---- Validate backup ----
    if not backup_path.exists() or not _integrity_check(backup_path):
        logger.error(f'[restore] 備份無效或不存在，跳過還原：{backup_path}')
        pending.unlink(missing_ok=True)
        return RestoreOutcome(
            'warning',
            f'還原備份無效或已不存在，已跳過本次還原。\n'
            f'備份位置：{backup_path}',
        )

    # ---- WAL clear — BEFORE restore ----
    _clear_wal(_restore_db_path)

    # ---- Attempt restore copy ----
    try:
        shutil.copy2(str(backup_path), str(_restore_db_path))
    except Exception as restore_exc:
        logger.error(f'[restore] copy2 失敗（restore → db_path）：{restore_exc}')
        _clear_wal(_restore_db_path)  # clean up partial write
        try:
            shutil.copy2(str(safety_path), str(_restore_db_path))
        except Exception as rollback_exc:
            _handle_double_failure(
                _restore_db_path, backup_path, safety_path,
                restore_exc, rollback_exc, _log_dir,
            )  # always raises RestoreError
        _clear_wal(_restore_db_path)
        pending.unlink(missing_ok=True)
        return RestoreOutcome(
            'warning',
            f'還原失敗，已回復至還原前狀態。\n原因：{restore_exc}',
        )

    # ---- WAL clear — AFTER restore ----
    _clear_wal(_restore_db_path)

    # ---- Integrity check on restored DB ----
    if not _integrity_check(_restore_db_path):
        logger.error('[restore] 還原後完整性驗證失敗，執行回復')
        try:
            shutil.copy2(str(safety_path), str(_restore_db_path))
        except Exception as rollback_exc:
            _handle_double_failure(
                _restore_db_path, backup_path, safety_path,
                RuntimeError('integrity check failed after restore'),
                rollback_exc, _log_dir,
            )  # always raises RestoreError
        _clear_wal(_restore_db_path)
        pending.unlink(missing_ok=True)
        return RestoreOutcome(
            'warning',
            '還原完整性驗證失敗，已回復至還原前狀態。',
        )

    # ---- Success ----
    pending.unlink(missing_ok=True)
    logger.info(f'[restore] 還原成功：{backup_path.name} → {_restore_db_path.name}')
    return RestoreOutcome(
        'success',
        f'資料庫已從備份成功還原。\n備份：{backup_path.name}',
    )
