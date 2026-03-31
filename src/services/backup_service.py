"""
BackupService: orchestrates auto/manual backup and listing.
Thin facade over src.core.backup pure functions.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import List, Optional

from src.core.backup import (
    BackupError,
    BackupInfo,
    check_last_auto_backup_time,
    create_backup,
    list_backups,
    prune_old_backups,
)
from src.core.logger import logger


class BackupService:
    """Orchestrates backup operations for a specific db_path / backup_dir pair.

    No global constants are read — all paths are injected at construction.
    """

    _AUTO_KEEP = 7
    _MANUAL_KEEP = 14

    def __init__(self, db_path: Path, backup_dir: Path) -> None:
        self._db_path = db_path
        self._backup_dir = backup_dir

    def auto_backup_if_needed(self, interval_hours: int = 24) -> Optional[Path]:
        """Create an auto backup if no auto backup exists within interval_hours.

        Eligibility is determined solely by the newest AUTO backup timestamp.
        Manual and safety backups do NOT affect the schedule.
        Failures are logged as warnings and not re-raised (non-fatal).
        Prunes to keep newest _AUTO_KEEP auto backups after success.

        Returns the created backup Path, or None if backup was not needed.
        """
        try:
            last = check_last_auto_backup_time(self._backup_dir)
            if last is not None:
                elapsed = (datetime.now() - last).total_seconds()
                if elapsed < interval_hours * 3600:
                    return None
            path = create_backup(self._db_path, self._backup_dir, 'auto')
            prune_old_backups(self._backup_dir, 'auto', keep=self._AUTO_KEEP)
            return path
        except BackupError as exc:
            logger.warning(f'[backup] Auto backup failed (non-fatal): {exc}')
            return None
        except Exception as exc:
            logger.warning(f'[backup] Auto backup unexpected error: {exc}')
            return None

    def manual_backup(self) -> Path:
        """Create a manual backup.

        Raises BackupError on failure (caller must handle and show UI error).
        Prunes to keep newest _MANUAL_KEEP manual backups after success.
        """
        path = create_backup(self._db_path, self._backup_dir, 'manual')
        prune_old_backups(self._backup_dir, 'manual', keep=self._MANUAL_KEEP)
        return path

    def list_backups(self) -> List[BackupInfo]:
        """Return auto + manual backups, newest-first.

        Safety snapshots are excluded from this listing.
        """
        all_backups = list_backups(self._backup_dir)
        return [b for b in all_backups if b.label in ('auto', 'manual')]
