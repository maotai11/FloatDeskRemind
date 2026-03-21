"""
ConsoleWindow: 3-column main console.
Left: view switcher
Center: task tree
Right: edit panel
Keyboard shortcuts: Ctrl+N, Ctrl+F, Delete, Space, Ctrl+A
"""
from __future__ import annotations
from typing import Optional, List, Dict

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QSplitter
)
from PySide6.QtCore import Signal, Qt
from PySide6.QtGui import QShortcut, QKeySequence, QCloseEvent, QIcon

from src.data.models import Task
from src.data.phase_repository import PhaseRepository
from src.core.config import AppConfig
from src.core.paths import ASSETS_DIR
from src.ui.utils import restore_window_geometry
from src.ui.components.console_left_panel import LeftPanel, VIEW_SEARCH
from src.ui.components.console_center_panel import CenterPanel
from src.ui.components.console_right_panel import RightPanel
from src.ui.components.search_bar import SearchBar
from src.ui.components.status_bar import AppStatusBar
from src.ui.dialogs.confirm_delete_dialog import ConfirmDeleteDialog
from src.ui.dialogs.task_edit_dialog import TaskEditDialog


class ConsoleWindow(QMainWindow):
    # Emitted to AppController
    task_add_requested = Signal(object)        # Task (new)
    task_update_requested = Signal(object)     # Task (edited)
    task_delete_requested = Signal(str, bool)  # task_id, cascade
    task_complete_requested = Signal(str)      # task_id
    task_restore_requested = Signal(str)       # task_id
    search_requested = Signal(str)             # query
    console_geometry_changed = Signal(int, int, int, int, int)  # x, y, w, h, splitter

    def __init__(self, config: AppConfig, phase_repo: PhaseRepository, parent=None):
        super().__init__(parent)
        self._config = config
        self._phase_repo = phase_repo
        self.setWindowTitle('FloatDesk Remind — 主控台')
        self.setMinimumSize(900, 600)
        self._task_map: Dict[str, Task] = {}
        self._setup_icon()
        self._build_ui()
        self._setup_shortcuts()
        self._restore_geometry()

    def _setup_icon(self) -> None:
        icon_path = ASSETS_DIR / 'icon.png'
        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))

    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QHBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Left panel
        self._left = LeftPanel()
        self._left.view_changed.connect(self._on_view_changed)
        main_layout.addWidget(self._left)

        # Splitter for center + right
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setHandleWidth(1)

        # Center area (search bar + tree)
        center_container = QWidget()
        center_v = QVBoxLayout(center_container)
        center_v.setContentsMargins(0, 0, 0, 0)
        center_v.setSpacing(0)

        self._search_bar = SearchBar()
        self._search_bar.search_changed.connect(self._on_search)
        self._search_bar.setFixedHeight(40)
        self._search_bar.setContentsMargins(8, 4, 8, 4)
        center_v.addWidget(self._search_bar)

        self._center = CenterPanel()
        self._center.task_selected.connect(self._on_task_selected)
        self._center.add_requested.connect(self._on_add_task)
        self._center.delete_requested.connect(self._on_delete_task)
        self._center.toggle_complete_requested.connect(self._on_toggle_complete)
        center_v.addWidget(self._center)

        splitter.addWidget(center_container)

        # Right panel
        self._right = RightPanel(phase_repo=self._phase_repo)
        self._right.save_requested.connect(self._on_save_task)
        self._right.cancel_requested.connect(self._on_cancel_edit)
        self._right.add_child_requested.connect(self._on_add_child_task)
        splitter.addWidget(self._right)

        self._splitter = splitter
        splitter.setSizes([self._config.console_splitter,
                           self._config.console_width - self._config.console_splitter])
        main_layout.addWidget(splitter)

        self._status = AppStatusBar()
        self.setStatusBar(self._status)

    def _setup_shortcuts(self) -> None:
        QShortcut(QKeySequence('Ctrl+N'), self).activated.connect(self._on_add_task)
        QShortcut(QKeySequence('Ctrl+F'), self).activated.connect(self._search_bar.set_focus)
        QShortcut(QKeySequence('Delete'), self).activated.connect(self._on_delete_selected)
        QShortcut(QKeySequence('Space'), self).activated.connect(self._on_space_toggle)

    def _restore_geometry(self) -> None:
        restore_window_geometry(
            self, self._config.console_x, self._config.console_y,
            self._config.console_width, self._config.console_height
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def refresh(self, tasks: List[Task], status_msg: str = '', is_search: bool = False) -> None:
        if not is_search:
            self._task_map = {t.id: t for t in tasks}
        self._center.refresh(tasks)
        if status_msg:
            self._status.show_message(status_msg)
        pending_count = sum(1 for t in tasks if t.status == 'pending')
        self._status.show_permanent(f'待辦：{pending_count}')

    def show_task(self, task: Task) -> None:
        """Show and select a specific task (called from AppController)."""
        self._right.load_task(task)
        self._center.select_task(task.id)

    def get_splitter_size(self) -> int:
        return self._splitter.sizes()[0]

    # ------------------------------------------------------------------
    # View change
    # ------------------------------------------------------------------
    def _on_view_changed(self, view: str) -> None:
        self._center.refresh(list(self._task_map.values()), view)
        self._search_bar.clear()
        if view == VIEW_SEARCH:
            self._search_bar.set_focus()

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------
    def _on_search(self, query: str) -> None:
        if query:
            self.search_requested.emit(query)
        else:
            self._center.refresh(list(self._task_map.values()))

    # ------------------------------------------------------------------
    # Task selection
    # ------------------------------------------------------------------
    def _on_task_selected(self, task: Optional[Task]) -> None:
        if task:
            self._right.load_task(task)
        else:
            self._right.show_empty()

    # ------------------------------------------------------------------
    # Add task
    # ------------------------------------------------------------------
    def _on_add_task(self) -> None:
        dlg = TaskEditDialog(parent=self)
        if dlg.exec():
            task = dlg.get_task()
            if task:
                self.task_add_requested.emit(task)

    def _on_add_child_task(self, parent_id: str) -> None:
        dlg = TaskEditDialog(parent_id=parent_id, parent=self)
        if dlg.exec():
            task = dlg.get_task()
            if task:
                self.task_add_requested.emit(task)

    # ------------------------------------------------------------------
    # Save / Cancel
    # ------------------------------------------------------------------
    def _on_save_task(self, task: Task) -> None:
        self.task_update_requested.emit(task)

    def _on_cancel_edit(self) -> None:
        self._right.show_empty()

    # ------------------------------------------------------------------
    # Delete — get children from local task_map (no extra DB call)
    # ------------------------------------------------------------------
    def _on_delete_task(self, task_id: str) -> None:
        task = self._task_map.get(task_id)
        if not task:
            return
        children = [t for t in self._task_map.values() if t.parent_id == task_id]
        dlg = ConfirmDeleteDialog(task, children, parent=self)
        if dlg.exec():
            self.task_delete_requested.emit(task_id, dlg.cascade)

    def _on_delete_selected(self) -> None:
        task_id = self._center.get_selected_task_id()
        if task_id:
            self._on_delete_task(task_id)

    # ------------------------------------------------------------------
    # Complete / Restore
    # ------------------------------------------------------------------
    def _on_toggle_complete(self, task_id: str) -> None:
        task = self._task_map.get(task_id)
        if not task:
            return
        if task.status == 'done':
            self.task_restore_requested.emit(task_id)
        else:
            self.task_complete_requested.emit(task_id)

    def _on_space_toggle(self) -> None:
        task_id = self._center.get_selected_task_id()
        if task_id:
            self._on_toggle_complete(task_id)

    # ------------------------------------------------------------------
    # Close → hide (not quit), save geometry
    # ------------------------------------------------------------------
    def closeEvent(self, event: QCloseEvent) -> None:
        event.ignore()
        geo = self.geometry()
        splitter_center = self._splitter.sizes()[0]
        self.console_geometry_changed.emit(
            geo.x(), geo.y(), geo.width(), geo.height(), splitter_center
        )
        self.hide()
