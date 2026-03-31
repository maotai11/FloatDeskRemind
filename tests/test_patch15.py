"""
Patch 15 — Task Detail / Notes tests.

Classes:
  TestDescriptionCRUD        — description create / save / read-back via repository
  TestDescriptionEmptyState  — empty description handling
  TestDirtyTracking          — RightPanel _is_dirty flag and auto-save timer
  TestAutoSaveOnSwitch       — flush-save triggered when switching to a different task
  TestDescriptionPreview     — TASK_DESC_ROLE stored in tree items for delegate
"""
from __future__ import annotations

import sys
import uuid
from typing import Optional
from unittest.mock import MagicMock, patch

import pytest

# Bootstrap QApplication before any QWidget import
try:
    from PySide6.QtWidgets import QApplication
    _app = QApplication.instance() or QApplication(sys.argv)
except Exception:
    _app = None

from src.data.models import Task
from src.ui.components.console_center_panel import CenterPanel, TASK_DESC_ROLE
from src.ui.components.console_right_panel import RightPanel
from src.core.view_filter import VIEW_ALL
from PySide6.QtCore import Qt


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _task(
    title: str = 'Task',
    description: str = '',
    status: str = 'pending',
    due_date: Optional[str] = None,
    is_recurring: bool = False,
    recurrence_rule: Optional[str] = None,
) -> Task:
    return Task(
        id=str(uuid.uuid4()),
        title=title,
        description=description,
        status=status,
        due_date=due_date,
        is_recurring=is_recurring,
        recurrence_rule=recurrence_rule,
    )


def _make_right_panel() -> RightPanel:
    """Return a RightPanel with a stub PhaseRepository."""
    from src.data.phase_repository import PhaseRepository
    phase_repo = MagicMock(spec=PhaseRepository)
    phase_repo.get_phases.return_value = []
    return RightPanel(phase_repo=phase_repo)


# ---------------------------------------------------------------------------
# TestDescriptionCRUD
# ---------------------------------------------------------------------------

class TestDescriptionCRUD:

    def test_create_task_with_description(self, task_repo):
        t = _task(title='有備註的任務', description='第一步\n第二步\n第三步')
        task_repo.create(t)
        saved = task_repo.get_by_id(t.id)
        assert saved.description == '第一步\n第二步\n第三步'

    def test_create_task_without_description(self, task_repo):
        t = _task(title='無備註的任務')
        task_repo.create(t)
        saved = task_repo.get_by_id(t.id)
        assert saved.description == '' or saved.description is None

    def test_update_description(self, task_repo):
        t = _task(title='任務', description='舊備註')
        task_repo.create(t)
        t.description = '新備註，更詳細的說明'
        task_repo.update(t)
        saved = task_repo.get_by_id(t.id)
        assert saved.description == '新備註，更詳細的說明'

    def test_clear_description(self, task_repo):
        t = _task(title='任務', description='有備註')
        task_repo.create(t)
        t.description = ''
        task_repo.update(t)
        saved = task_repo.get_by_id(t.id)
        assert not saved.description   # empty string or None, both acceptable

    def test_description_survives_status_change(self, task_service, task_repo):
        t = _task(title='任務', description='重要備註')
        task_repo.create(t)
        task_service.complete_task_manual(t.id)
        saved = task_repo.get_by_id(t.id)
        assert saved.description == '重要備註'

    def test_description_survives_restore(self, task_service, task_repo):
        t = _task(title='任務', description='備註', status='done')
        task_repo.create(t)
        task_service.restore_task(t.id)
        saved = task_repo.get_by_id(t.id)
        assert saved.description == '備註'

    def test_long_description_persisted(self, task_repo):
        long_desc = '測試行\n' * 100  # 100 lines
        t = _task(title='長備註', description=long_desc)
        task_repo.create(t)
        saved = task_repo.get_by_id(t.id)
        assert saved.description == long_desc

    def test_description_via_service_create(self, task_service, task_repo):
        t = _task(title='Service建立', description='服務層備註')
        task_service.create_task(t)
        saved = task_repo.get_by_id(t.id)
        assert saved.description == '服務層備註'


# ---------------------------------------------------------------------------
# TestDescriptionEmptyState
# ---------------------------------------------------------------------------

class TestDescriptionEmptyState:

    def test_empty_description_placeholder_in_right_panel(self):
        """QTextEdit placeholder text is set to the expected string."""
        panel = _make_right_panel()
        assert '補充說明' in panel._desc.placeholderText()

    def test_empty_description_field_after_show_empty(self):
        panel = _make_right_panel()
        # Load a task with description first
        t = _task(title='任務', description='備註')
        panel.load_task(t)
        assert panel._desc.toPlainText() == '備註'

        # Now clear
        panel.show_empty()
        assert panel._desc.toPlainText() == ''

    def test_no_description_not_stored_in_desc_role(self):
        """Tree item with no description stores None in TASK_DESC_ROLE."""
        panel = CenterPanel()
        t = _task(title='無備註')
        panel.refresh([t], view=VIEW_ALL)
        item = panel._item_map.get(t.id)
        assert item is not None
        assert item.data(0, TASK_DESC_ROLE) is None


# ---------------------------------------------------------------------------
# TestDirtyTracking
# ---------------------------------------------------------------------------

class TestDirtyTracking:

    def test_not_dirty_initially(self):
        panel = _make_right_panel()
        assert not panel.is_dirty

    def test_not_dirty_after_load_task(self):
        panel = _make_right_panel()
        t = _task(title='任務')
        panel.load_task(t)
        assert not panel.is_dirty

    def test_dirty_after_title_change(self):
        panel = _make_right_panel()
        t = _task(title='任務')
        panel.load_task(t)
        panel._title.setText('修改後的標題')
        assert panel.is_dirty

    def test_dirty_after_description_change(self):
        panel = _make_right_panel()
        t = _task(title='任務')
        panel.load_task(t)
        panel._desc.setPlainText('新備註')
        assert panel.is_dirty

    def test_not_dirty_after_show_empty(self):
        panel = _make_right_panel()
        t = _task(title='任務')
        panel.load_task(t)
        panel._title.setText('changed')  # make dirty
        assert panel.is_dirty

        panel.show_empty()
        assert not panel.is_dirty

    def test_not_dirty_after_explicit_save(self):
        panel = _make_right_panel()
        save_calls = []
        panel.save_requested.connect(lambda t: save_calls.append(t))

        t = _task(title='任務')
        panel.load_task(t)
        panel._title.setText('修改')
        assert panel.is_dirty

        panel._on_save()
        assert not panel.is_dirty

    def test_header_shows_asterisk_when_dirty(self):
        panel = _make_right_panel()
        t = _task(title='任務')
        panel.load_task(t)
        panel._title.setText('修改後')
        assert '*' in panel._header.text()

    def test_header_no_asterisk_after_save(self):
        panel = _make_right_panel()
        panel.save_requested.connect(lambda t: None)
        t = _task(title='任務')
        panel.load_task(t)
        panel._title.setText('修改後')
        panel._on_save()
        assert '*' not in panel._header.text()

    def test_loading_flag_prevents_dirty_during_load(self):
        """Field changes during load_task() must not set is_dirty."""
        panel = _make_right_panel()
        t = _task(title='任務', description='備註')
        # Simulate: load a task, then check that is_dirty is False
        panel.load_task(t)
        # Direct verification: _loading should be False after load completes
        assert not panel._loading
        assert not panel.is_dirty

    def test_autosave_timer_started_when_dirty(self):
        panel = _make_right_panel()
        t = _task(title='任務')
        panel.load_task(t)
        assert not panel._autosave_timer.isActive()

        panel._desc.setPlainText('change')
        assert panel._autosave_timer.isActive()

    def test_autosave_timer_stopped_after_save(self):
        panel = _make_right_panel()
        panel.save_requested.connect(lambda t: None)
        t = _task(title='任務')
        panel.load_task(t)
        panel._desc.setPlainText('change')
        assert panel._autosave_timer.isActive()

        panel._on_save()
        assert not panel._autosave_timer.isActive()

    def test_on_autosave_calls_save_when_dirty(self):
        panel = _make_right_panel()
        save_calls = []
        panel.save_requested.connect(lambda t: save_calls.append(t))

        t = _task(title='任務')
        panel.load_task(t)
        panel._title.setText('修改後')
        assert panel.is_dirty

        panel._on_autosave()
        assert len(save_calls) == 1
        assert not panel.is_dirty

    def test_on_autosave_noop_when_not_dirty(self):
        panel = _make_right_panel()
        save_calls = []
        panel.save_requested.connect(lambda t: save_calls.append(t))

        t = _task(title='任務')
        panel.load_task(t)
        assert not panel.is_dirty

        panel._on_autosave()
        assert save_calls == []

    def test_on_autosave_noop_when_no_task(self):
        panel = _make_right_panel()
        save_calls = []
        panel.save_requested.connect(lambda t: save_calls.append(t))

        panel._on_autosave()   # no task loaded
        assert save_calls == []


# ---------------------------------------------------------------------------
# TestAutoSaveOnSwitch
# ---------------------------------------------------------------------------

class TestAutoSaveOnSwitch:

    def test_switching_to_different_task_flushes_save(self):
        """load_task(taskB) while dirty with taskA → emits save_requested(taskA)."""
        panel = _make_right_panel()
        save_calls = []
        panel.save_requested.connect(lambda t: save_calls.append(t.id))

        task_a = _task(title='任務 A')
        task_b = _task(title='任務 B')

        panel.load_task(task_a)
        panel._title.setText('修改 A')   # make dirty
        assert panel.is_dirty

        panel.load_task(task_b)          # switch → should flush-save taskA first
        # save_requested was emitted at least once with taskA's id
        assert task_a.id in save_calls

    def test_after_flush_save_panel_shows_task_b(self):
        panel = _make_right_panel()
        panel.save_requested.connect(lambda t: None)

        task_a = _task(title='任務 A')
        task_b = _task(title='任務 B', description='B 的備註')

        panel.load_task(task_a)
        panel._desc.setPlainText('A 的修改備註')

        panel.load_task(task_b)
        assert panel._desc.toPlainText() == 'B 的備註'
        assert panel._title.text() == '任務 B'

    def test_switching_to_same_task_no_double_save(self):
        """load_task with the same task.id must NOT flush-save."""
        panel = _make_right_panel()
        save_calls = []
        panel.save_requested.connect(lambda t: save_calls.append(t))

        task_a = _task(title='任務 A')
        panel.load_task(task_a)
        panel._title.setText('修改')

        # Reload same task (e.g. after a refresh)
        panel.load_task(task_a)
        assert save_calls == []   # no flush-save triggered

    def test_not_dirty_no_save_on_switch(self):
        panel = _make_right_panel()
        save_calls = []
        panel.save_requested.connect(lambda t: save_calls.append(t))

        task_a = _task(title='任務 A')
        task_b = _task(title='任務 B')
        panel.load_task(task_a)
        assert not panel.is_dirty

        panel.load_task(task_b)
        assert save_calls == []   # nothing to save → no emit

    def test_dirty_reset_after_load_new_task(self):
        panel = _make_right_panel()
        panel.save_requested.connect(lambda t: None)

        task_a = _task(title='任務 A')
        task_b = _task(title='任務 B')
        panel.load_task(task_a)
        panel._desc.setPlainText('dirty')
        assert panel.is_dirty

        panel.load_task(task_b)
        assert not panel.is_dirty   # fresh after loading taskB


# ---------------------------------------------------------------------------
# TestDescriptionPreview
# ---------------------------------------------------------------------------

class TestDescriptionPreview:
    """All tests pass view=VIEW_ALL so tasks without due_date are visible."""

    def test_item_stores_description_in_desc_role(self):
        panel = CenterPanel()
        t = _task(title='有備註', description='第一行\n第二行')
        panel.refresh([t], view=VIEW_ALL)

        item = panel._item_map.get(t.id)
        assert item is not None
        assert item.data(0, TASK_DESC_ROLE) == '第一行\n第二行'

    def test_item_with_empty_description_stores_none(self):
        panel = CenterPanel()
        t = _task(title='無備註', description='')
        panel.refresh([t], view=VIEW_ALL)

        item = panel._item_map.get(t.id)
        assert item is not None
        assert item.data(0, TASK_DESC_ROLE) is None

    def test_item_with_whitespace_only_stores_none(self):
        panel = CenterPanel()
        t = _task(title='空白備註', description='   \n  ')
        panel.refresh([t], view=VIEW_ALL)

        item = panel._item_map.get(t.id)
        assert item is not None
        assert item.data(0, TASK_DESC_ROLE) is None

    def test_tooltip_includes_description_first_line(self):
        panel = CenterPanel()
        t = _task(title='任務', description='第一行摘要\n第二行詳情')
        panel.refresh([t], view=VIEW_ALL)

        item = panel._item_map.get(t.id)
        assert item is not None
        tooltip = item.toolTip(0)
        assert '第一行摘要' in tooltip

    def test_tooltip_includes_ellipsis_for_multiline(self):
        panel = CenterPanel()
        t = _task(title='任務', description='第一行\n第二行')
        panel.refresh([t], view=VIEW_ALL)

        item = panel._item_map.get(t.id)
        assert item is not None
        assert '…' in item.toolTip(0)

    def test_tooltip_no_ellipsis_for_single_short_line(self):
        panel = CenterPanel()
        t = _task(title='任務', description='簡短備註')
        panel.refresh([t], view=VIEW_ALL)

        item = panel._item_map.get(t.id)
        assert item is not None
        assert '…' not in item.toolTip(0)

    def test_description_updated_on_refresh(self):
        panel = CenterPanel()
        t = _task(title='任務', description='舊備註')
        panel.refresh([t], view=VIEW_ALL)
        assert panel._item_map[t.id].data(0, TASK_DESC_ROLE) == '舊備註'

        t.description = '新備註'
        panel.refresh([t], view=VIEW_ALL)
        assert panel._item_map[t.id].data(0, TASK_DESC_ROLE) == '新備註'

    def test_multiple_tasks_correct_descriptions(self):
        panel = CenterPanel()
        t1 = _task(title='任務一', description='備註一')
        t2 = _task(title='任務二', description='')
        t3 = _task(title='任務三', description='備註三')
        panel.refresh([t1, t2, t3], view=VIEW_ALL)

        assert panel._item_map[t1.id].data(0, TASK_DESC_ROLE) == '備註一'
        assert panel._item_map[t2.id].data(0, TASK_DESC_ROLE) is None
        assert panel._item_map[t3.id].data(0, TASK_DESC_ROLE) == '備註三'
