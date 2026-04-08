"""
ReminderScheduler: polls task_reminders every 30 s and emits notification signals.

Design:
  - QTimer fires every INTERVAL_MS (30 000 ms)
  - _scan() queries ReminderRepository.list_due(now_iso)
  - For each due reminder:
      1. mark_fired(reminder_id)  ← at-most-once guarantee BEFORE signal emit
      2. emit notification_requested(task_title, remind_at)
  - All exceptions are caught per-reminder (inner) and per-scan (outer)
    so one bad reminder never stops the scheduler.
  - scan_now() triggers an immediate scan on startup.

Signals:
  notification_requested(title: str, message: str)
    title   — task title
    message — formatted remind_at string ('YYYY-MM-DD HH:MM')

Thread model: single-threaded Qt main thread only.
"""
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from PySide6.QtCore import QObject, QTimer, Signal

from src.core.logger import logger

if TYPE_CHECKING:
    from src.data.reminder_repository import ReminderRepository


class ReminderScheduler(QObject):
    """Polls task_reminders on a 30-second interval and emits notification signals.

    Instantiate, connect notification_requested, call start().
    Call stop() on app shutdown to avoid timer callbacks after teardown.
    """

    INTERVAL_MS: int = 30_000

    notification_requested = Signal(str, str, str)  # (task_id, task_title, message)

    def __init__(self, repo: 'ReminderRepository', parent: QObject = None) -> None:
        super().__init__(parent)
        self._repo = repo
        self._timer = QTimer(self)
        self._timer.setInterval(self.INTERVAL_MS)
        self._timer.timeout.connect(self._scan)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Start the periodic scan timer."""
        if not self._timer.isActive():
            self._timer.start()
            logger.debug('[scheduler] Reminder timer started (interval=%dms)', self.INTERVAL_MS)

    def stop(self) -> None:
        """Stop the periodic scan timer."""
        self._timer.stop()
        logger.debug('[scheduler] Reminder timer stopped')

    def scan_now(self) -> None:
        """Trigger an immediate scan (called once at startup)."""
        self._scan()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _scan(self) -> None:
        """Query due reminders and emit notification_requested for each.

        Outer try/except: unexpected errors (DB down, import error) are logged
        as ERROR but do NOT stop the timer.
        Inner try/except: per-reminder errors are logged as WARNING and the loop
        continues to the next reminder.
        """
        try:
            now_iso = datetime.now().strftime('%Y-%m-%dT%H:%M:%S')
            due = self._repo.list_due(now_iso)
            if not due:
                return
            logger.debug('[scheduler] %d due reminder(s) found at %s', len(due), now_iso)

            for reminder in due:
                try:
                    # mark_fired BEFORE emit — at-most-once guarantee.
                    # If the signal handler raises, the reminder is already
                    # marked fired and will not fire again next scan.
                    self._repo.mark_fired(reminder.reminder_id)

                    # Format message for the notification
                    message = _fmt_remind_at(reminder.remind_at)

                    logger.info(
                        '[scheduler] Firing reminder %s — task="%s"',
                        reminder.reminder_id[:8],
                        reminder.task_title,
                    )
                    self.notification_requested.emit(reminder.task_id, reminder.task_title, message)

                except Exception as exc:  # noqa: BLE001
                    logger.warning(
                        '[scheduler] Failed to process reminder %s: %s',
                        reminder.reminder_id,
                        exc,
                    )

        except Exception as exc:  # noqa: BLE001
            logger.error('[scheduler] Scan failed (timer continues): %s', exc)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fmt_remind_at(raw: str) -> str:
    """Format ISO remind_at to 'YYYY-MM-DD HH:MM' for the notification body.

    Handles both 'T' and ' ' separators.
    Returns the raw string unchanged on any parse error.
    """
    if not raw:
        return ''
    try:
        normalized = raw.replace('T', ' ')
        return normalized[:16]   # 'YYYY-MM-DD HH:MM'
    except Exception:
        return raw
