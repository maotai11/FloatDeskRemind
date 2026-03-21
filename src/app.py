"""
AppController: central hub connecting all layers.
Owns repositories, services, and windows.
Signal routing: UI events → Service → Repository → DB → refresh signals → UI
"""
from __future__ import annotations
from typing import List, Optional

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QApplication

from src.core.config import AppConfig
from src.core.logger import logger
from src.core.utils import next_n_days
from src.data.database import run_migrations
from src.data.task_repository import TaskRepository
from src.data.settings_repository import SettingsRepository
from src.data.models import Task
from src.services.task_service import TaskService, CompleteResult
from src.ui.dialogs.confirm_complete_dialog import ConfirmCompleteDialog
from src.ui.dialogs.confirm_delete_dialog import ConfirmDeleteDialog
from src.ui.tray.tray_icon import TrayIcon
from src.ui.windows.float_window import FloatWindow
from src.ui.windows.console_window import ConsoleWindow


class AppController(QObject):
    task_changed = Signal()  # Broadcast to all UI

    def __init__(self, parent=None):
        super().__init__(parent)

        # Run migrations first so tables exist before any repo call
        run_migrations()

        # Repositories & services
        self._settings_repo = SettingsRepository()
        self._task_repo = TaskRepository()
        self._task_service = TaskService(self._task_repo)
        self._config = AppConfig.load(self._settings_repo)

        # Windows
        self._float_window: Optional[FloatWindow] = None
        self._console_window: Optional[ConsoleWindow] = None
        self._tray: Optional[TrayIcon] = None

        self.task_changed.connect(self._refresh_all)

    def start(self) -> None:
        """Initialize and show the app."""
        self._apply_font_size()
        self._setup_tray()
        self._setup_float_window()
        self._setup_console_window()
        self._refresh_all()
        self._float_window.show()

    def _apply_font_size(self) -> None:
        from src.ui.styles.theme import FONT_SIZE_MAP
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
        self._console_window = ConsoleWindow()
        self._console_window.task_add_requested.connect(self._on_add_task)
        self._console_window.task_update_requested.connect(self._on_update_task)
        self._console_window.task_delete_requested.connect(self._on_delete_task)
        self._console_window.task_complete_requested.connect(self._on_complete_task)
        self._console_window.task_restore_requested.connect(self._on_restore_task)
        self._console_window.search_requested.connect(self._on_search)

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
            tasks = self._task_service.get_all_active()
            self._console_window.refresh(tasks)

    def _quit(self) -> None:
        self._save_config()
        QApplication.quit()

    # ------------------------------------------------------------------
    # Refresh
    # ------------------------------------------------------------------
    def _refresh_all(self) -> None:
        tasks = self._task_service.get_all_active()
        float_dates = set(next_n_days(self._config.display_days))
        float_tasks = [t for t in tasks if t.due_date in float_dates and t.status == 'pending']

        if self._float_window:
            self._float_window.refresh(float_tasks)
        if self._console_window and self._console_window.isVisible():
            self._console_window.refresh(tasks)

    # ------------------------------------------------------------------
    # Task CRUD handlers
    # ------------------------------------------------------------------
    def _on_add_task(self, task: Task) -> None:
        try:
            self._task_service.create_task(task)
            self.task_changed.emit()
            logger.info(f'Task created: {task.id}')
        except ValueError as e:
            logger.warning(f'Create task failed: {e}')

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
            self._console_window.refresh(results, f'搜尋「{query}」：{len(results)} 筆')

    # ------------------------------------------------------------------
    # Float window geometry
    # ------------------------------------------------------------------
    def _on_float_geometry_changed(self, x: int, y: int, w: int, h: int) -> None:
        self._config.float_pos_x = x
        self._config.float_pos_y = y
        self._config.float_width = w
        self._config.float_height = h

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
            self._run_backup_if_due()
        except Exception as e:
            logger.error(f'Save config failed: {e}')

    def _run_backup_if_due(self) -> None:
        """Copy the DB file to the backups directory if auto_backup policy requires it."""
        if self._config.auto_backup == 'never':
            return
        try:
            import shutil
            from datetime import date
            from src.core.paths import APP_DATA_DIR, DB_PATH
            backup_dir = APP_DATA_DIR / 'backups'
            backup_dir.mkdir(exist_ok=True)
            stamp = date.today().isoformat()
            # weekly: use ISO week number as stamp suffix
            if self._config.auto_backup == 'weekly':
                stamp = f'{date.today().isocalendar()[0]}-W{date.today().isocalendar()[1]:02d}'
            dest = backup_dir / f'floatdesk_{stamp}.db'
            if not dest.exists():
                shutil.copy2(DB_PATH, dest)
                logger.info(f'DB backed up to {dest}')
            # Keep only last 7 backup files
            backups = sorted(backup_dir.glob('floatdesk_*.db'))
            for old in backups[:-7]:
                old.unlink(missing_ok=True)
        except Exception as e:
            logger.warning(f'Backup failed (non-fatal): {e}')
