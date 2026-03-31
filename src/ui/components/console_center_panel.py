"""
Center panel: QTreeWidget showing parent/child tasks.

Patch 12:
  - Filtering delegated to src.core.view_filter.filter_tasks().
  - New views: UPCOMING, OVERDUE, NO_DATE, COMPLETED (replaces the old DONE).
  - Empty-state overlay shown when filtered result is empty.
  - Overdue items: title is bold + red (was red-only).
  - Recurring indicator: title suffixed with '↻' for is_recurring tasks.

Patch 13:
  - edit_requested signal: emitted on double-click → ConsoleWindow loads RightPanel.
  - Enter / Numpad-Enter on tree: complete the selected task if pending (not restore).
    Implemented via installEventFilter so it only fires when the tree has focus,
    avoiding conflicts with form inputs in the right panel.
  - Double-click opens the task in the right panel (edit_requested).
  - Right-click context menu: existing 完成/還原 + 刪除 actions (unchanged).
  - Up/Down navigation: native QTreeWidget behaviour (no change needed).

Patch 15:
  - Description preview: column-0 items show a second dimmed line with the
    first line of description (up to 60 chars) via _TaskItemDelegate.
  - TASK_DESC_ROLE stored in each QTreeWidgetItem for the delegate to read.
  - Tooltip on column-0 now includes description when non-empty.
"""
from __future__ import annotations

from datetime import date
from typing import List, Optional, Dict

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QStackedWidget, QTreeWidget, QTreeWidgetItem,
    QHBoxLayout, QPushButton, QHeaderView, QAbstractItemView, QLabel,
    QStyledItemDelegate, QStyleOptionViewItem, QStyle,
)
from PySide6.QtCore import Signal, Qt, QEvent, QObject, QSize, QRect
from PySide6.QtGui import QColor, QFont, QFontMetrics

from src.data.models import Task
from src.services.sort_service import sort_tasks
from src.core.view_filter import (
    filter_tasks,
    VIEW_TODAY, VIEW_UPCOMING, VIEW_OVERDUE, VIEW_NO_DATE,
    VIEW_ALL, VIEW_COMPLETED, VIEW_SEARCH,
    EMPTY_MESSAGES,
)
from src.ui.styles.theme import TEXT_OVERDUE, PRIORITY_HIGH, PRIORITY_MEDIUM

TASK_ID_ROLE   = Qt.ItemDataRole.UserRole
TASK_DESC_ROLE = Qt.ItemDataRole.UserRole + 1   # stores description for delegate

# Module-level constants — not re-created on every tree rebuild
_PRIORITY_LABELS: Dict[str, str] = {'high': '高', 'medium': '中', 'low': '低', 'none': ''}
_STATUS_LABELS: Dict[str, str]   = {'pending': '待辦', 'done': '完成', 'archived': '歸檔'}

_COLOR_DONE            = QColor('#AAAAAA')
_COLOR_OVERDUE         = QColor(TEXT_OVERDUE)
_COLOR_PRIORITY_HIGH   = QColor(PRIORITY_HIGH)
_COLOR_PRIORITY_MEDIUM = QColor(PRIORITY_MEDIUM)
_COLOR_DESC_PREVIEW    = QColor('#94A3B8')

# Enter / numpad-Enter Qt key codes
_ENTER_KEYS = frozenset({Qt.Key.Key_Return, Qt.Key.Key_Enter})

# Description preview constants
_PREVIEW_MAX_LEN  = 60   # characters
_PREVIEW_EXTRA_H  = 15   # pixels added to row height when description present


# ---------------------------------------------------------------------------
# Description preview delegate
# ---------------------------------------------------------------------------

class _TaskItemDelegate(QStyledItemDelegate):
    """Renders column-0 tree items with an optional description preview on a
    second line.  All other columns fall through to the default renderer.

    Layout (when description is present):
        ┌──────────────────────────────────────┐  ← option.rect.top()
        │  [expand] [icon]  Title text          │  title portion
        │             description preview…      │  description strip (_PREVIEW_EXTRA_H px)
        └──────────────────────────────────────┘  ← option.rect.bottom()
    """

    def sizeHint(self, option: QStyleOptionViewItem, index) -> QSize:
        base = super().sizeHint(option, index)
        if index.column() == 0 and index.data(TASK_DESC_ROLE):
            return QSize(base.width(), base.height() + _PREVIEW_EXTRA_H)
        return base

    def paint(self, painter, option: QStyleOptionViewItem, index) -> None:
        if index.column() != 0:
            super().paint(painter, option, index)
            return

        desc = index.data(TASK_DESC_ROLE)
        if not desc:
            super().paint(painter, option, index)
            return

        # --- Draw title in the top portion of the row ---
        title_opt = QStyleOptionViewItem(option)
        title_opt.rect = QRect(
            option.rect.x(),
            option.rect.y(),
            option.rect.width(),
            option.rect.height() - _PREVIEW_EXTRA_H,
        )
        super().paint(painter, title_opt, index)

        # --- Draw description preview strip ---
        # Build the one-line preview
        first_line = desc.split('\n')[0]
        if len(first_line) > _PREVIEW_MAX_LEN:
            preview = first_line[:_PREVIEW_MAX_LEN] + '…'
        elif len(desc) > len(first_line):   # multi-line: append ellipsis
            preview = first_line + '…'
        else:
            preview = first_line

        desc_rect = QRect(
            option.rect.x() + 20,          # small indent to clear expand arrow
            option.rect.bottom() - _PREVIEW_EXTRA_H,
            option.rect.width() - 24,
            _PREVIEW_EXTRA_H,
        )

        # Use white (semi-transparent) when item is selected, grey otherwise
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        if selected:
            color = QColor(255, 255, 255, 180)
        else:
            color = _COLOR_DESC_PREVIEW

        desc_font = QFont(option.font)
        ps = desc_font.pointSize()
        if ps > 0:
            desc_font.setPointSize(max(ps - 1, 7))

        painter.save()
        painter.setFont(desc_font)
        painter.setPen(color)
        painter.drawText(
            desc_rect,
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            preview,
        )
        painter.restore()


# ---------------------------------------------------------------------------
# CenterPanel
# ---------------------------------------------------------------------------

class CenterPanel(QWidget):
    task_selected             = Signal(object)  # Task or None
    add_requested             = Signal()
    delete_requested          = Signal(str)     # task_id
    toggle_complete_requested = Signal(str)     # task_id  (Space: toggle)
    complete_requested        = Signal(str)     # task_id  (Enter: complete-only)
    edit_requested            = Signal(str)     # task_id  (double-click)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._current_view = VIEW_TODAY
        self._all_tasks: List[Task] = []
        self._task_map: Dict[str, Task] = {}
        self._item_map: Dict[str, QTreeWidgetItem] = {}
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

        hint = QLabel('Ctrl+N')
        hint.setStyleSheet('color: #94A3B8; font-size: 11px;')
        tb_layout.addWidget(hint)

        layout.addWidget(topbar)

        # ── Stacked widget: tree (0) / empty state (1) ────────────────────
        self._stack = QStackedWidget()

        # Page 0 — task tree
        self._tree = QTreeWidget()
        self._tree.setColumnCount(4)
        self._tree.setHeaderLabels(['標題', '優先', '期限', '狀態'])
        self._tree.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self._tree.header().setDefaultSectionSize(80)
        self._tree.setAlternatingRowColors(True)
        self._tree.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._tree.setRootIsDecorated(True)
        self._tree.itemSelectionChanged.connect(self._on_selection_changed)
        self._tree.itemDoubleClicked.connect(self._on_item_double_clicked)
        self._tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._tree.customContextMenuRequested.connect(self._show_context_menu)

        # Description preview delegate for column 0
        self._delegate = _TaskItemDelegate(self._tree)
        self._tree.setItemDelegateForColumn(0, self._delegate)

        # Enter-to-complete: intercept key events on the tree widget
        # only when it has focus — does not affect form inputs in other panels.
        self._tree.installEventFilter(self)

        self._stack.addWidget(self._tree)               # index 0

        # Page 1 — empty state
        empty_container = QWidget()
        empty_layout = QVBoxLayout(empty_container)
        empty_layout.setContentsMargins(20, 40, 20, 40)
        self._empty_label = QLabel()
        self._empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_label.setWordWrap(True)
        self._empty_label.setStyleSheet(
            'color: #94A3B8; font-size: 14px; font-weight: 500;'
        )
        empty_layout.addStretch()
        empty_layout.addWidget(self._empty_label)
        empty_layout.addStretch()
        self._stack.addWidget(empty_container)          # index 1

        layout.addWidget(self._stack)

    # ── Event filter ──────────────────────────────────────────────────────────

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        """Intercept Enter/Return on the tree to complete the selected task.

        Only fires when the tree widget itself has focus.
        Enter (Return / numpad Enter) → complete_requested if task is pending.
        Enter on a done task → no-op (v1: opening is not implemented).
        """
        if watched is self._tree and event.type() == QEvent.Type.KeyPress:
            if event.key() in _ENTER_KEYS:
                task_id = self.get_selected_task_id()
                if task_id:
                    task = self._task_map.get(task_id)
                    if task and task.status == 'pending':
                        self.complete_requested.emit(task_id)
                return True  # consume the event regardless (prevent tree expand/collapse)
        return super().eventFilter(watched, event)

    # ── Public API ────────────────────────────────────────────────────────────

    def refresh(self, tasks: List[Task], view: str = None) -> None:
        if view:
            self._current_view = view
        self._all_tasks = tasks
        self._task_map = {t.id: t for t in tasks}
        selected_id = self.get_selected_task_id()
        self._rebuild_tree()
        if selected_id:
            self.select_task(selected_id)

    def get_selected_task_id(self) -> Optional[str]:
        items = self._tree.selectedItems()
        if not items:
            return None
        return items[0].data(0, TASK_ID_ROLE)

    def select_task(self, task_id: str) -> None:
        item = self._item_map.get(task_id)
        if item:
            self._tree.setCurrentItem(item)

    # ── Internal ──────────────────────────────────────────────────────────────

    def _rebuild_tree(self) -> None:
        self._tree.clear()
        self._item_map.clear()

        today_str = date.today().isoformat()
        visible = filter_tasks(self._all_tasks, self._current_view)

        if not visible:
            msg = EMPTY_MESSAGES.get(self._current_view, '沒有符合的結果')
            self._empty_label.setText(msg)
            self._stack.setCurrentIndex(1)
            return

        self._stack.setCurrentIndex(0)

        # Separate root tasks and their children
        parents = [t for t in visible if not t.parent_id]
        child_map: Dict[str, List[Task]] = {}
        for t in visible:
            if t.parent_id:
                child_map.setdefault(t.parent_id, []).append(t)

        for parent in sort_tasks(parents):
            p_item = self._make_item(parent, today_str)
            self._tree.addTopLevelItem(p_item)

            for child in sort_tasks(child_map.get(parent.id, [])):
                p_item.addChild(self._make_item(child, today_str))

            p_item.setExpanded(True)

        # Orphan children: parent not visible in this view
        shown_parent_ids = {p.id for p in parents}
        for t in visible:
            if t.parent_id and t.parent_id not in shown_parent_ids:
                self._tree.addTopLevelItem(self._make_item(t, today_str))

    def _make_item(self, task: Task, today_str: str) -> QTreeWidgetItem:
        # Append ↻ to recurring task titles
        title = f'{task.title} ↻' if task.is_recurring else task.title

        item = QTreeWidgetItem([
            title,
            _PRIORITY_LABELS.get(task.priority, ''),
            task.due_date or '',
            _STATUS_LABELS.get(task.status, task.status),
        ])
        item.setData(0, TASK_ID_ROLE, task.id)

        # Store description for the preview delegate
        desc = (task.description or '').strip()
        item.setData(0, TASK_DESC_ROLE, desc if desc else None)

        # Tooltip: title always; description appended if non-empty
        tooltip = task.title
        if desc:
            preview_line = desc.split('\n')[0]
            if len(preview_line) > 80:
                preview_line = preview_line[:80] + '…'
            elif len(desc) > len(preview_line):
                preview_line += '…'
            tooltip = f'{task.title}\n{preview_line}'
        item.setToolTip(0, tooltip)

        self._item_map[task.id] = item

        if task.status == 'done':
            for col in range(4):
                item.setForeground(col, _COLOR_DONE)
            font = item.font(0)
            font.setStrikeOut(True)
            item.setFont(0, font)

        elif task.due_date and task.due_date < today_str and task.status == 'pending':
            # Overdue: red + bold title
            item.setForeground(0, _COLOR_OVERDUE)
            item.setForeground(2, _COLOR_OVERDUE)
            font = item.font(0)
            font.setBold(True)
            item.setFont(0, font)

        if task.priority == 'high':
            item.setForeground(1, _COLOR_PRIORITY_HIGH)
        elif task.priority == 'medium':
            item.setForeground(1, _COLOR_PRIORITY_MEDIUM)

        return item

    def _on_item_double_clicked(self, item: QTreeWidgetItem, column: int) -> None:
        """Double-click: open the task in the right panel for editing."""
        task_id = item.data(0, TASK_ID_ROLE)
        if task_id:
            task = self._task_map.get(task_id)
            # Allow editing pending, done, archived — but not deleted
            if task and task.status != 'deleted':
                self.edit_requested.emit(task_id)

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

        if task.status == 'pending':
            done_action = QAction('完成  (Enter)', self)
            done_action.triggered.connect(lambda: self.toggle_complete_requested.emit(task_id))
            menu.addAction(done_action)
        elif task.status == 'done':
            restore_action = QAction('還原', self)
            restore_action.triggered.connect(lambda: self.toggle_complete_requested.emit(task_id))
            menu.addAction(restore_action)

        edit_action = QAction('編輯  (雙擊)', self)
        edit_action.triggered.connect(lambda: self.edit_requested.emit(task_id))
        menu.addAction(edit_action)

        menu.addSeparator()

        del_action = QAction('刪除  (Delete)', self)
        del_action.triggered.connect(lambda: self.delete_requested.emit(task_id))
        menu.addAction(del_action)

        menu.exec(self._tree.viewport().mapToGlobal(pos))
