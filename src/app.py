"""
AppController: central hub connecting all layers.
Owns repositories, services, and windows.
Signal routing: UI events → Service → Repository → DB → refresh signals → UI
"""
from __future__ import annotations
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import List, Optional

from PySide6.QtCore import QObject, Signal, QTimer
from PySide6.QtWidgets import QApplication, QMessageBox, QSystemTrayIcon

from src.core.config import AppConfig
from src.core.logger import logger
from src.core.paths import APP_DATA_DIR, DB_PATH, BACKUP_DIR
from src.core.utils import next_n_days
from src.data.database import run_migrations
from src.services.backup_service import BackupService
from src.core.health_check import (
    run_preflight_checks,
    run_post_migration_checks,
    get_fatal_failures,
)
from src.ui.styles.theme import FONT_SIZE_MAP
from src.data.task_repository import TaskRepository
from src.data.settings_repository import SettingsRepository
from src.data.phase_repository import PhaseRepository
from src.data.models import Task
from src.services.task_service import TaskService, CompleteResult
from src.data.reminder_repository import ReminderRepository
from src.services.reminder_scheduler import ReminderScheduler
from src.data.models import TaskReminder
from src.ui.dialogs.confirm_complete_dialog import ConfirmCompleteDialog
from src.ui.dialogs.confirm_delete_dialog import ConfirmDeleteDialog
from src.ui.tray.tray_icon import TrayIcon
from src.ui.windows.float_window import FloatWindow
from src.ui.windows.console_window import ConsoleWindow


class AppController(QObject):
    task_changed = Signal()  # Broadcast to all UI

    def __init__(self, parent=None):
        super().__init__(parent)

        # Phase 1: preflight — verify writable dirs and DB access before touching the DB
        preflight = run_preflight_checks()
        fatal = get_fatal_failures(preflight)
        if fatal:
            raise RuntimeError('啟動自檢失敗：\n' + '\n'.join(fatal))

        # Run migrations so tables exist before any repo call
        run_migrations()

        # Phase 2: post-migration — verify dirs, version, and static assets
        post = run_post_migration_checks()
        post_fatal = get_fatal_failures(post)
        if post_fatal:
            raise RuntimeError('啟動後自檢失敗：\n' + '\n'.join(post_fatal))

        # Repositories & services
        self._settings_repo = SettingsRepository()
        self._task_repo = TaskRepository()
        self._phase_repo = PhaseRepository()
        self._task_service = TaskService(self._task_repo)
        self._config = AppConfig.load(self._settings_repo)
        self._backup_service = BackupService(DB_PATH, BACKUP_DIR)
        self._reminder_repo = ReminderRepository()
        self._reminder_scheduler = ReminderScheduler(self._reminder_repo)
        self._reminder_scheduler.notification_requested.connect(self._show_tray_notification)

        # Windows
        self._float_window: Optional[FloatWindow] = None
        self._console_window: Optional[ConsoleWindow] = None
        self._tray: Optional[TrayIcon] = None

        self.task_changed.connect(self._refresh_all)

        # Debounce timer: writes geometry to DB 800ms after the last move/resize
        self._geo_save_timer = QTimer()
        self._geo_save_timer.setSingleShot(True)
        self._geo_save_timer.setInterval(800)
        self._geo_save_timer.timeout.connect(self._save_config)

        # Reminder timer: checks due tasks every minute
        self._remind_session_start: str = ''   # set in start(); ISO 'YYYY-MM-DDTHH:MM'
        self._notified_ids: set = set()        # confirmed this session → never re-fires
        self._snoozed: dict = {}               # {task_id: snooze_until ISO str}
        self._remind_timer = QTimer()
        self._remind_timer.setInterval(60_000)
        self._remind_timer.timeout.connect(self._check_reminders)

    def start(self) -> None:
        """Initialize and show the app."""
        self._apply_font_size()
        self._setup_tray()
        self._setup_float_window()
        self._setup_console_window()
        self._refresh_all()
        self._float_window.show()

        # Start reminder timer; record session start so pre-existing overdue
        # tasks (before this launch) are not spuriously re-notified.
        self._remind_session_start = datetime.now().strftime('%Y-%m-%dT%H:%M')
        self._remind_timer.start()

        # Reminder scheduler: scan task_reminders every 30 s.
        # scan_now() fires an immediate scan so reminders due at startup are not
        # delayed up to 30 s.
        self._reminder_scheduler.start()
        self._reminder_scheduler.scan_now()

        # Auto backup (respects user config: never / daily / weekly)
        if self._config.auto_backup != 'never':
            _interval = 168 if self._config.auto_backup == 'weekly' else 24
            self._backup_service.auto_backup_if_needed(interval_hours=_interval)

    def _apply_font_size(self) -> None:
        pt = FONT_SIZE_MAP.get(self._config.font_size, 13)
        font = QApplication.font()
        font.setPointSize(pt)
        QApplication.setFont(font)

    # ------------------------------------------------------------------
    # Setup
    # ------------------------------------------------------------------
    def _setup_tray(self) -> None:
        self._tray = TrayIcon()
        self._tray.show_float_requested.connect(self._show_float)
        self._tray.show_console_requested.connect(self._show_console)
        self._tray.show_settings_requested.connect(self._show_settings)
        self._tray.quit_requested.connect(self._quit)
        self._tray.show()

    def _setup_float_window(self) -> None:
        self._float_window = FloatWindow(self._config)
        self._float_window.task_completed.connect(self._on_complete_task)
        self._float_window.task_edit_requested.connect(self._on_float_edit)
        self._float_window.task_delete_requested.connect(self._on_float_delete)
        self._float_window.open_console_requested.connect(self._show_console)
        self._float_window.geometry_changed.connect(self._on_float_geometry_changed)

    def _setup_console_window(self) -> None:
        self._console_window = ConsoleWindow(
            self._config, self._phase_repo, reminder_repo=self._reminder_repo
        )
        self._console_window.task_add_requested.connect(self._on_add_task)
        self._console_window.task_update_requested.connect(self._on_update_task)
        self._console_window.task_delete_requested.connect(self._on_delete_task)
        self._console_window.task_complete_requested.connect(self._on_complete_task)
        self._console_window.task_restore_requested.connect(self._on_restore_task)
        self._console_window.search_requested.connect(self._on_search)
        self._console_window.console_geometry_changed.connect(self._on_console_geometry_changed)
        self._console_window.backup_restore_requested.connect(self._show_backup_restore_dialog)
        self._console_window.recycle_bin_requested.connect(self._show_recycle_bin_dialog)

    # ------------------------------------------------------------------
    # Window management
    # ------------------------------------------------------------------
    def _show_float(self) -> None:
        if self._float_window:
            self._float_window.show()
            self._float_window.raise_()
            self._float_window.activateWindow()

    def _show_console(self) -> None:
        if self._console_window:
            self._console_window.show()
            self._console_window.raise_()
            self._console_window.activateWindow()
            # Always refresh on show: start() skips invisible console
            tasks = self._task_service.get_all_non_deleted()
            self._console_window.refresh(tasks)

    def _quit(self) -> None:
        self._reminder_scheduler.stop()
        if self._console_window:
            geo = self._console_window.geometry()
            self._config.console_x = geo.x()
            self._config.console_y = geo.y()
            self._config.console_width = geo.width()
            self._config.console_height = geo.height()
            self._config.console_splitter = self._console_window.get_splitter_size()
        self._save_config()
        QApplication.quit()

    # ------------------------------------------------------------------
    # Refresh
    # ------------------------------------------------------------------
    def _refresh_all(self) -> None:
        tasks = self._task_service.get_all_non_deleted()
        today_str = date.today().isoformat()
        float_dates = set(next_n_days(self._config.display_days))
        float_tasks = [
            t for t in tasks
            if t.status == 'pending' and t.due_date
            and (t.due_date < today_str or t.due_date in float_dates)
        ]

        if self._float_window:
            self._float_window.refresh(float_tasks)
        if self._console_window and self._console_window.isVisible():
            self._console_window.refresh(tasks)

    # ------------------------------------------------------------------
    # Reminder
    # ------------------------------------------------------------------

    def _show_tray_notification(self, title: str, message: str) -> None:
        """Show a tray balloon notification for a fired reminder.

        Silently skipped if the tray icon is not available or not visible
        (e.g. running headless in tests).
        """
        if self._tray and self._tray.isVisible():
            self._tray.showMessage(
                title,
                message,
                QSystemTrayIcon.MessageIcon.Information,
                5000,   # ms — 5 seconds
            )
            logger.info('[app] Tray notification shown: "%s"', title)
        else:
            logger.debug('[app] Tray not visible; skipping notification for "%s"', title)

    def _check_reminders(self) -> None:
        """Show reminder dialogs for tasks that became due since session start."""
        if not self._tray or not self._remind_session_start:
            return
        now_str = datetime.now().strftime('%Y-%m-%dT%H:%M')
        tasks = self._task_repo.get_pending_due_in_range(
            self._remind_session_start, now_str
        )
        for task in tasks:
            # Still in snooze window — skip
            snooze_until = self._snoozed.get(task.id)
            if snooze_until:
                if now_str < snooze_until:
                    continue
                del self._snoozed[task.id]   # snooze expired → fall through
            elif task.id in self._notified_ids:
                continue  # already confirmed this session
            self._show_reminder_dialog(task)

    def _show_reminder_dialog(self, task: Task) -> None:
        from src.ui.dialogs.reminder_dialog import ReminderDialog
        time_str = task.due_time[:5] if task.due_time else ''
        logger.info(f'Reminder: "{task.title}" {task.due_date} {time_str}')
        dlg = ReminderDialog(task)
        dlg.confirmed.connect(self._on_reminder_confirmed)
        dlg.snoozed.connect(self._on_reminder_snoozed)
        dlg.show()

    def _on_reminder_confirmed(self, task_id: str) -> None:
        self._notified_ids.add(task_id)
        self._snoozed.pop(task_id, None)

    def _on_reminder_snoozed(self, task_id: str, minutes: int) -> None:
        until = datetime.now() + timedelta(minutes=minutes)
        self._snoozed[task_id] = until.strftime('%Y-%m-%dT%H:%M')
        logger.info(f'Reminder snoozed {minutes}m: task={task_id}')

    # ------------------------------------------------------------------
    # Backup & Restore
    # ------------------------------------------------------------------

    def _show_backup_restore_dialog(self) -> None:
        """Open BackupRestoreDialog as a modal child of ConsoleWindow."""
        from src.ui.dialogs.backup_restore_dialog import BackupRestoreDialog
        parent_widget = self._console_window if self._console_window else None
        dlg = BackupRestoreDialog(self._backup_service, parent=parent_widget)
        dlg.restore_confirmed.connect(self._on_restore_from_backup)
        dlg.exec()

    def _on_restore_from_backup(self, backup_path: Path) -> None:
        """Schedule deferred restore, inform the user, then quit.

        This is the AppController-side handler for BackupRestoreDialog.restore_confirmed.
        Calls request_restore() (Phase 1 of the two-phase restore design).
        The actual file replacement happens at next startup via run_pending_restore().

        On success  : informational QMessageBox, then QApplication.quit().
        On BackupError: error QMessageBox; does NOT quit (user can retry or cancel).
        """
        from src.core.restore import request_restore
        from src.core.backup import BackupError
        try:
            request_restore(
                backup_path,
                db_path=DB_PATH,
                backup_dir=BACKUP_DIR,
                pending_dir=APP_DATA_DIR,
            )
            QMessageBox.information(
                None,
                'FloatDesk Remind — 還原已排程',
                f'已排程還原。\n'
                f'備份：{backup_path.name}\n\n'
                f'程式即將關閉，下次啟動時將自動還原資料庫。',
            )
            logger.info(f'[app] Restore scheduled from {backup_path.name}; quitting.')
            QApplication.quit()
        except BackupError as exc:
            logger.error(f'[app] request_restore failed: {exc}')
            QMessageBox.critical(
                None,
                'FloatDesk Remind — 排程還原失敗',
                f'排程還原時發生錯誤：\n\n{exc}\n\n'
                f'資料庫未被修改，請重試或選擇其他備份。',
            )

    # ------------------------------------------------------------------
    # Recycle Bin
    # ------------------------------------------------------------------

    def _show_recycle_bin_dialog(self) -> None:
        """Open RecycleBinDialog as a modal child of ConsoleWindow.

        The dialog calls task_service directly for restore and permanent delete.
        tasks_changed signal is connected to self.task_changed so the main UI
        refreshes whenever the recycle bin is modified.
        """
        from src.ui.dialogs.recycle_bin_dialog import RecycleBinDialog
        parent_widget = self._console_window if self._console_window else None
        dlg = RecycleBinDialog(self._task_service, parent=parent_widget)
        dlg.tasks_changed.connect(self.task_changed.emit)
        dlg.exec()

    def _on_restore_from_trash(self, task_id: str) -> None:
        """Restore a soft-deleted task to pending status.

        Can be called independently of RecycleBinDialog (e.g. future keyboard shortcut).
        Emits task_changed on success so all UI panels refresh.
        Errors are shown via QMessageBox.critical.
        """
        try:
            self._task_service.restore_from_trash(task_id)
            self.task_changed.emit()
            logger.info(f'[app] Restored task from trash: {task_id}')
        except Exception as exc:
            logger.error(f'[app] restore_from_trash failed: {exc}')
            QMessageBox.critical(
                None,
                'FloatDesk Remind — 還原失敗',
                f'還原任務時發生錯誤：\n\n{exc}',
            )

    def _on_permanently_delete(self, task_id: str) -> None:
        """Permanently erase a task from the database (irreversible).

        Can be called independently of RecycleBinDialog.
        Emits task_changed on success so all UI panels refresh.
        Errors are shown via QMessageBox.critical.
        """
        try:
            self._task_service.permanently_delete(task_id)
            self.task_changed.emit()
            logger.info(f'[app] Permanently deleted task: {task_id}')
        except Exception as exc:
            logger.error(f'[app] permanently_delete failed: {exc}')
            QMessageBox.critical(
                None,
                'FloatDesk Remind — 永久刪除失敗',
                f'永久刪除任務時發生錯誤：\n\n{exc}',
            )

    # ------------------------------------------------------------------
    # Task CRUD handlers
    # ------------------------------------------------------------------
    def _on_add_task(self, task: Task, remind_at: str = None) -> None:
        """Create a new task and optionally attach a reminder.

        remind_at is emitted alongside the Task by ConsoleWindow so we can
        commit the task first (to satisfy the reminder FK constraint) and then
        create the reminder in the same synchronous call chain.
        """
        try:
            self._task_service.create_task(task)
            logger.info(f'Task created: {task.id}')
        except ValueError as e:
            logger.warning(f'Create task failed: {e}')
            return
        if remind_at:
            try:
                r = TaskReminder(id='', task_id=task.id, mode='at', remind_at=remind_at)
                self._reminder_repo.create(r)
                logger.info(f'[app] Reminder created for task {task.id} → {remind_at}')
            except Exception as exc:
                logger.error(f'[app] Failed to create reminder for task {task.id}: {exc}')
        self.task_changed.emit()

    def _on_update_task(self, task: Task) -> None:
        try:
            self._task_service.update_task(task)
            self.task_changed.emit()
        except Exception as e:
            logger.error(f'Update task failed: {e}')

    def _on_delete_task(self, task_id: str, cascade: bool) -> None:
        self._task_service.delete_task(task_id, cascade)
        self.task_changed.emit()

    def _on_complete_task(self, task_id: str) -> None:
        """Unified completion handler for both float window and console."""
        task = self._task_service.get_task(task_id)
        if not task:
            return

        # Child task → scenario A (auto-complete parent if all siblings done)
        if task.parent_id:
            self._task_service.complete_child_task(task_id)
            self.task_changed.emit()
            return

        # Parent task → scenario B (may need confirmation)
        result = self._task_service.complete_task_manual(task_id)
        if result == CompleteResult.NEEDS_CONFIRM:
            children = self._task_repo.get_children(task_id)
            pending = [c for c in children if c.status != 'done']
            parent_widget = self._console_window if self._console_window and self._console_window.isVisible() \
                else self._float_window
            dlg = ConfirmCompleteDialog(task, pending, parent=parent_widget)
            if dlg.exec():
                self._task_service.complete_parent_with_children(task_id, dlg.include_children)
                self.task_changed.emit()
        elif result == CompleteResult.OK:
            self.task_changed.emit()

    def _on_restore_task(self, task_id: str) -> None:
        self._task_service.restore_task(task_id)
        self.task_changed.emit()

    def _on_float_edit(self, task_id: str) -> None:
        self._show_console()
        task = self._task_service.get_task(task_id)
        if task and self._console_window:
            self._console_window.show_task(task)

    def _on_float_delete(self, task_id: str) -> None:
        task = self._task_service.get_task(task_id)
        if not task:
            return
        children = self._task_repo.get_children(task_id)
        dlg = ConfirmDeleteDialog(task, children, parent=self._float_window)
        if dlg.exec():
            self._task_service.delete_task(task_id, dlg.cascade)
            self.task_changed.emit()

    def _on_search(self, query: str) -> None:
        results = self._task_service.search(query)
        if self._console_window:
            self._console_window.refresh(results, f'搜尋「{query}」：{len(results)} 筆', is_search=True)

    # ------------------------------------------------------------------
    # Float window geometry
    # ------------------------------------------------------------------
    def _on_float_geometry_changed(self, x: int, y: int, w: int, h: int) -> None:
        self._config.float_pos_x = x
        self._config.float_pos_y = y
        self._config.float_width = w
        self._config.float_height = h
        self._geo_save_timer.start()  # debounced write — fires 800ms after last move

    def _on_console_geometry_changed(self, x: int, y: int, w: int, h: int, splitter: int) -> None:
        self._config.console_x = x
        self._config.console_y = y
        self._config.console_width = w
        self._config.console_height = h
        self._config.console_splitter = splitter
        self._geo_save_timer.start()

    # ------------------------------------------------------------------
    # Settings
    # ------------------------------------------------------------------
    def _show_settings(self) -> None:
        from src.ui.dialogs.settings_dialog import SettingsDialog
        from src.core.autostart import set_autostart
        dlg = SettingsDialog(self._config, parent=None)
        if dlg.exec():
            self._config.auto_start    = dlg.autostart
            self._config.float_opacity = dlg.float_opacity
            self._config.display_days  = dlg.display_days
            self._config.font_size     = dlg.font_size
            self._config.auto_backup   = dlg.auto_backup
            set_autostart(dlg.autostart)
            if self._float_window:
                self._float_window.set_opacity(dlg.float_opacity)
                self._float_window.update()
            self._apply_font_size()
            self._save_config()

    # ------------------------------------------------------------------
    # Config persistence
    # ------------------------------------------------------------------
    def _save_config(self) -> None:
        try:
            self._config.save(self._settings_repo)
        except Exception as e:
            logger.error(f'Save config failed: {e}')
