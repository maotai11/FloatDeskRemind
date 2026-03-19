"""
Center panel: QTreeWidget showing parent/child tasks.
"""
from __future__ import annotations
from datetime import date
from typing import List, Optional, Dict

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QTreeWidget, QTreeWidgetItem,
    QHBoxLayout, QPushButton, QHeaderView, QAbstractItemView, QLabel
)
from PySide6.QtCore import Signal, Qt
from PySide6.QtGui import QColor

from src.data.models import Task
from src.services.sort_service import sort_tasks
from src.core.utils import next_n_days
from src.ui.components.console_left_panel import (
    VIEW_TODAY, VIEW_3DAYS, VIEW_ALL, VIEW_DONE, VIEW_SEARCH
)
from src.ui.styles.theme import TEXT_OVERDUE, PRIORITY_HIGH, PRIORITY_MEDIUM

TASK_ID_ROLE = Qt.ItemDataRole.UserRole

# Module-level constants — not re-created on every tree rebuild
_PRIORITY_LABELS: Dict[str, str] = {'high': '高', 'medium': '中', 'low': '低', 'none': ''}
_STATUS_LABELS: Dict[str, str] = {'pending': '待辦', 'done': '完成', 'archived': '歸檔'}

_COLOR_DONE     = QColor('#AAAAAA')
_COLOR_OVERDUE  = QColor(TEXT_OVERDUE)
_COLOR_PRIORITY_HIGH   = QColor(PRIORITY_HIGH)
_COLOR_PRIORITY_MEDIUM = QColor(PRIORITY_MEDIUM)


class CenterPanel(QWidget):
    task_selected = Signal(object)   # Task or None
    add_requested = Signal()
    delete_requested = Signal(str)   # task_id
    toggle_complete_requested = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._current_view = VIEW_TODAY
        self._all_tasks: List[Task] = []
        self._task_map: Dict[str, Task] = {}
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ── Top bar: prominent add button ─────────────────────────────────
        topbar = QWidget()
        topbar.setFixedHeight(56)
        topbar.setStyleSheet(
            'background-color: #FFFFFF; border-bottom: 1px solid #E2E8F0;'
        )
        tb_layout = QHBoxLayout(topbar)
        tb_layout.setContentsMargins(12, 8, 12, 8)
        tb_layout.setSpacing(8)

        # Large, unmissable add button
        add_btn = QPushButton('＋  新增任務')
        add_btn.setFixedHeight(38)
        add_btn.setMinimumWidth(140)
        add_btn.setStyleSheet(
            'QPushButton {'
            '  background-color: #4F46E5;'
            '  color: #FFFFFF;'
            '  border: none;'
            '  border-radius: 8px;'
            '  padding: 0 20px;'
            '  font-size: 14px;'
            '  font-weight: 700;'
            '  letter-spacing: 0.5px;'
            '}'
            'QPushButton:hover { background-color: #3730A3; }'
            'QPushButton:pressed { background-color: #312E81; }'
        )
        add_btn.setToolTip('新增任務  (Ctrl+N)')
        add_btn.clicked.connect(self.add_requested)
        tb_layout.addWidget(add_btn)
        tb_layout.addStretch()

        # Shortcut hint
        hint = QLabel('Ctrl+N')
        hint.setStyleSheet('color: #94A3B8; font-size: 11px;')
        tb_layout.addWidget(hint)

        layout.addWidget(topbar)

        # ── Task tree ──────────────────────────────────────────────────────
        self._tree = QTreeWidget()
        self._tree.setColumnCount(4)
        self._tree.setHeaderLabels(['標題', '優先', '期限', '狀態'])
        self._tree.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self._tree.header().setDefaultSectionSize(80)
        self._tree.setAlternatingRowColors(True)
        self._tree.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._tree.setRootIsDecorated(True)
        self._tree.itemSelectionChanged.connect(self._on_selection_changed)
        self._tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._tree.customContextMenuRequested.connect(self._show_context_menu)
        layout.addWidget(self._tree)

    def refresh(self, tasks: List[Task], view: str = None) -> None:
        if view:
            self._current_view = view
        self._all_tasks = tasks
        self._task_map = {t.id: t for t in tasks}
        self._rebuild_tree()

    def _filter_tasks(self) -> List[Task]:
        today_str = date.today().isoformat()

        match self._current_view:
            case v if v == VIEW_TODAY:
                return [t for t in self._all_tasks
                        if t.due_date == today_str and t.status == 'pending']
            case v if v == VIEW_3DAYS:
                d3 = set(next_n_days(3))
                return [t for t in self._all_tasks
                        if t.due_date in d3 and t.status == 'pending']
            case v if v == VIEW_DONE:
                return [t for t in self._all_tasks if t.status == 'done']
            case _:
                return [t for t in self._all_tasks
                        if t.status not in ('deleted', 'archived')]

    def _rebuild_tree(self) -> None:
        self._tree.clear()
        visible = self._filter_tasks()
        today_str = date.today().isoformat()

        # Separate parents and children
        parents = [t for t in visible if not t.parent_id]
        child_map: dict[str, List[Task]] = {}
        for t in visible:
            if t.parent_id:
                child_map.setdefault(t.parent_id, []).append(t)

        parents_sorted = sort_tasks(parents)

        for parent in parents_sorted:
            p_item = self._make_item(parent, today_str)
            self._tree.addTopLevelItem(p_item)

            children = child_map.get(parent.id, [])
            for child in sort_tasks(children):
                c_item = self._make_item(child, today_str)
                p_item.addChild(c_item)

            p_item.setExpanded(True)

        # Orphan children (parent deleted or not in current view)
        shown_parent_ids = {p.id for p in parents}
        for t in visible:
            if t.parent_id and t.parent_id not in shown_parent_ids:
                item = self._make_item(t, today_str)
                self._tree.addTopLevelItem(item)

    def _make_item(self, task: Task, today_str: str) -> QTreeWidgetItem:
        item = QTreeWidgetItem([
            task.title,
            _PRIORITY_LABELS.get(task.priority, ''),
            task.due_date or '',
            _STATUS_LABELS.get(task.status, task.status),
        ])
        item.setData(0, TASK_ID_ROLE, task.id)

        if task.status == 'done':
            for col in range(4):
                item.setForeground(col, _COLOR_DONE)
            font = item.font(0)
            font.setStrikeOut(True)
            item.setFont(0, font)
        elif task.due_date and task.due_date < today_str:
            item.setForeground(0, _COLOR_OVERDUE)
            item.setForeground(2, _COLOR_OVERDUE)

        if task.priority == 'high':
            item.setForeground(1, _COLOR_PRIORITY_HIGH)
        elif task.priority == 'medium':
            item.setForeground(1, _COLOR_PRIORITY_MEDIUM)

        return item

    def _on_selection_changed(self) -> None:
        items = self._tree.selectedItems()
        if not items:
            self.task_selected.emit(None)
            return
        task_id = items[0].data(0, TASK_ID_ROLE)
        self.task_selected.emit(self._task_map.get(task_id))

    def _show_context_menu(self, pos) -> None:
        from PySide6.QtWidgets import QMenu
        from PySide6.QtGui import QAction
        items = self._tree.selectedItems()
        if not items:
            return
        task_id = items[0].data(0, TASK_ID_ROLE)
        task = self._task_map.get(task_id)
        if not task:
            return

        menu = QMenu(self)
        if task.status != 'done':
            done_action = QAction('完成', self)
            done_action.triggered.connect(lambda: self.toggle_complete_requested.emit(task_id))
            menu.addAction(done_action)
        else:
            restore_action = QAction('還原', self)
            restore_action.triggered.connect(lambda: self.toggle_complete_requested.emit(task_id))
            menu.addAction(restore_action)

        menu.addSeparator()

        del_action = QAction('刪除', self)
        del_action.triggered.connect(lambda: self.delete_requested.emit(task_id))
        menu.addAction(del_action)

        menu.exec(self._tree.viewport().mapToGlobal(pos))

    def get_selected_task_id(self) -> Optional[str]:
        items = self._tree.selectedItems()
        if not items:
            return None
        return items[0].data(0, TASK_ID_ROLE)

    def select_task(self, task_id: str) -> None:
        for item in self._tree.findItems(
            '', Qt.MatchFlag.MatchContains | Qt.MatchFlag.MatchRecursive
        ):
            if item.data(0, TASK_ID_ROLE) == task_id:
                self._tree.setCurrentItem(item)
                return
