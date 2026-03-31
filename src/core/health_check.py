"""
Startup health checks for FloatDesk Remind.

Two-phase design — callers must respect the order:

  Phase 1  run_preflight_checks()   ← call BEFORE run_migrations()
    check_app_data_dir_writable       [fatal]
    check_db_accessible               [fatal]

  Phase 2  run_post_migration_checks()  ← call AFTER run_migrations()
    check_log_dir_writable            [warning]
    check_backup_dir_writable         [warning]
    check_db_version_consistent       [warning]
    check_assets_exist                [warning]
    check_qss_exists                  [warning]
    check_data_mode_info              [info]

Neither phase function raises.  Fatal failures are handled by the caller
via get_fatal_failures(), which returns a list of user-facing messages.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Literal

from src.core.logger import logger

Severity = Literal['fatal', 'warning', 'info']

# Files that must exist inside ASSETS_DIR
_REQUIRED_ASSETS = ('icon.ico', 'icon.png')


@dataclass
class CheckResult:
    name: str        # snake_case identifier matching the check function name
    passed: bool
    severity: Severity
    message: str     # 繁體中文，user-facing
    detail: str = field(default='')   # technical detail for log only


# ---------------------------------------------------------------------------
# Shared helper
# ---------------------------------------------------------------------------

def _probe_write(directory: Path) -> bool:
    """Return True if *directory* accepts a write.

    Creates a transient .write_probe file and removes it.
    The finally block guarantees cleanup even when write or return raises.
    """
    probe = directory / '.write_probe'
    try:
        probe.write_text('ok', encoding='utf-8')
        return True
    except OSError:
        return False
    finally:
        try:
            probe.unlink(missing_ok=True)
        except OSError:
            pass  # nosec B110 — cleanup is best-effort; write result already captured


# ---------------------------------------------------------------------------
# Phase 1 — Preflight checks (BEFORE run_migrations)
# ---------------------------------------------------------------------------

def check_app_data_dir_writable() -> CheckResult:
    from src.core.paths import APP_DATA_DIR
    try:
        APP_DATA_DIR.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        return CheckResult(
            name='app_data_dir_writable',
            passed=False,
            severity='fatal',
            message=f'資料目錄無法建立：{APP_DATA_DIR}',
            detail=str(exc),
        )
    if not _probe_write(APP_DATA_DIR):
        return CheckResult(
            name='app_data_dir_writable',
            passed=False,
            severity='fatal',
            message=f'資料目錄不可寫入：{APP_DATA_DIR}',
            detail='probe write failed',
        )
    return CheckResult(
        name='app_data_dir_writable',
        passed=True,
        severity='fatal',
        message='資料目錄可寫入',
        detail=str(APP_DATA_DIR),
    )


def check_db_accessible() -> CheckResult:
    from src.core.paths import DB_PATH
    try:
        conn = sqlite3.connect(str(DB_PATH))
        conn.execute('SELECT 1')
        conn.close()
    except Exception as exc:
        return CheckResult(
            name='db_accessible',
            passed=False,
            severity='fatal',
            message=f'資料庫無法開啟：{DB_PATH}',
            detail=str(exc),
        )
    return CheckResult(
        name='db_accessible',
        passed=True,
        severity='fatal',
        message='資料庫可存取',
        detail=str(DB_PATH),
    )


def run_preflight_checks() -> List[CheckResult]:
    """Phase 1: run before run_migrations().  Never raises."""
    results: List[CheckResult] = []
    for fn in (check_app_data_dir_writable, check_db_accessible):
        try:
            r = fn()
        except Exception as exc:  # nosec B110 — individual check must not propagate
            r = CheckResult(
                name=fn.__name__,
                passed=False,
                severity='fatal',
                message=f'檢查執行失敗：{fn.__name__}',
                detail=str(exc),
            )
        _log_result(r)
        results.append(r)
    return results


# ---------------------------------------------------------------------------
# Phase 2 — Post-migration checks (AFTER run_migrations)
# ---------------------------------------------------------------------------

def check_log_dir_writable() -> CheckResult:
    from src.core.paths import LOG_DIR
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        return CheckResult(
            name='log_dir_writable',
            passed=False,
            severity='warning',
            message=f'日誌目錄無法建立：{LOG_DIR}',
            detail=str(exc),
        )
    if not _probe_write(LOG_DIR):
        return CheckResult(
            name='log_dir_writable',
            passed=False,
            severity='warning',
            message=f'日誌目錄不可寫入：{LOG_DIR}',
            detail='probe write failed',
        )
    return CheckResult(
        name='log_dir_writable',
        passed=True,
        severity='warning',
        message='日誌目錄可寫入',
        detail=str(LOG_DIR),
    )


def check_backup_dir_writable() -> CheckResult:
    from src.core.paths import BACKUP_DIR
    try:
        BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        return CheckResult(
            name='backup_dir_writable',
            passed=False,
            severity='warning',
            message=f'備份目錄無法建立：{BACKUP_DIR}',
            detail=str(exc),
        )
    if not _probe_write(BACKUP_DIR):
        return CheckResult(
            name='backup_dir_writable',
            passed=False,
            severity='warning',
            message=f'備份目錄不可寫入：{BACKUP_DIR}',
            detail='probe write failed',
        )
    return CheckResult(
        name='backup_dir_writable',
        passed=True,
        severity='warning',
        message='備份目錄可寫入',
        detail=str(BACKUP_DIR),
    )


def check_db_version_consistent() -> CheckResult:
    try:
        from src.data.database import (
            get_current_version,
            _load_migration_modules,
            _validate_and_sort_migrations,
        )
        modules = _load_migration_modules()
        if not modules:
            return CheckResult(
                name='db_version_consistent',
                passed=False,
                severity='warning',
                message='找不到任何 migration 模組',
                detail='_load_migration_modules() returned empty list',
            )
        migrations = _validate_and_sort_migrations(modules)
        expected = migrations[-1][0]
        actual = get_current_version()
        if actual != expected:
            return CheckResult(
                name='db_version_consistent',
                passed=False,
                severity='warning',
                message=f'資料庫版本不一致：DB={actual}，預期={expected}',
                detail=f'expected={expected}, actual={actual}',
            )
        return CheckResult(
            name='db_version_consistent',
            passed=True,
            severity='warning',
            message=f'資料庫版本一致（v{actual}）',
            detail=f'version={actual}',
        )
    except Exception as exc:
        return CheckResult(
            name='db_version_consistent',
            passed=False,
            severity='warning',
            message='版本一致性檢查失敗',
            detail=str(exc),
        )


def check_assets_exist() -> CheckResult:
    from src.core.paths import ASSETS_DIR
    if not ASSETS_DIR.is_dir():
        return CheckResult(
            name='assets_exist',
            passed=False,
            severity='warning',
            message=f'資源目錄不存在：{ASSETS_DIR}',
            detail=str(ASSETS_DIR),
        )
    missing = [name for name in _REQUIRED_ASSETS if not (ASSETS_DIR / name).exists()]
    if missing:
        return CheckResult(
            name='assets_exist',
            passed=False,
            severity='warning',
            message=f'資源檔案缺失：{", ".join(missing)}',
            detail=f'missing={missing}, assets_dir={ASSETS_DIR}',
        )
    return CheckResult(
        name='assets_exist',
        passed=True,
        severity='warning',
        message='資源檔案齊全',
        detail=f'checked={list(_REQUIRED_ASSETS)}, assets_dir={ASSETS_DIR}',
    )


def check_qss_exists() -> CheckResult:
    from src.core.paths import QSS_PATH
    if not QSS_PATH.exists():
        return CheckResult(
            name='qss_exists',
            passed=False,
            severity='warning',
            message=f'QSS 樣式檔不存在，將使用預設樣式：{QSS_PATH}',
            detail=str(QSS_PATH),
        )
    return CheckResult(
        name='qss_exists',
        passed=True,
        severity='warning',
        message='QSS 樣式檔存在',
        detail=str(QSS_PATH),
    )


def check_data_mode_info() -> CheckResult:
    from src.core.paths import DATA_MODE, APP_DATA_DIR
    return CheckResult(
        name='data_mode_info',
        passed=True,
        severity='info',
        message=f'資料模式：{DATA_MODE}',
        detail=f'DATA_MODE={DATA_MODE}, APP_DATA_DIR={APP_DATA_DIR}',
    )


def run_post_migration_checks() -> List[CheckResult]:
    """Phase 2: run after run_migrations().  Never raises."""
    results: List[CheckResult] = []
    for fn in (
        check_log_dir_writable,
        check_backup_dir_writable,
        check_db_version_consistent,
        check_assets_exist,
        check_qss_exists,
        check_data_mode_info,
    ):
        try:
            r = fn()
        except Exception as exc:  # nosec B110
            r = CheckResult(
                name=fn.__name__,
                passed=False,
                severity='warning',
                message=f'檢查執行失敗：{fn.__name__}',
                detail=str(exc),
            )
        _log_result(r)
        results.append(r)
    return results


# ---------------------------------------------------------------------------
# Shared utilities
# ---------------------------------------------------------------------------

def get_fatal_failures(results: List[CheckResult]) -> List[str]:
    """Return user-facing messages for every fatal+failed result."""
    return [r.message for r in results if r.severity == 'fatal' and not r.passed]


def _log_result(r: CheckResult) -> None:
    detail = f' | {r.detail}' if r.detail else ''
    if r.passed:
        logger.info(f'[health] {r.name}: OK — {r.message}{detail}')
    elif r.severity == 'fatal':
        logger.error(f'[health] {r.name}: FATAL — {r.message}{detail}')
    else:
        logger.warning(f'[health] {r.name}: WARN — {r.message}{detail}')
