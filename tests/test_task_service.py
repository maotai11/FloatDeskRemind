"""
Test TaskService: scenarios A-E and validation.
"""
import uuid
import pytest

from src.data.models import Task
from src.services.task_service import TaskService, CompleteResult


def _make_task(**kwargs) -> Task:
    defaults = dict(
        id=str(uuid.uuid4()),
        title='Test',
        created_at='',
        updated_at='',
    )
    defaults.update(kwargs)
    return Task(**defaults)


# ------------------------------------------------------------------
# Validation
# ------------------------------------------------------------------
def test_grandchild_blocked(task_service, task_repo):
    parent = _make_task(title='Parent')
    task_repo.create(parent)

    child = _make_task(title='Child', parent_id=parent.id)
    task_repo.create(child)

    grandchild = _make_task(title='Grandchild', parent_id=child.id)
    with pytest.raises(ValueError):
        task_service.create_task(grandchild)


# ------------------------------------------------------------------
# Scenario A: auto-complete parent
# ------------------------------------------------------------------
def test_scenario_a_auto_complete(task_service, task_repo):
    parent = _make_task(title='Parent', auto_complete_with_children=True)
    task_repo.create(parent)

    child1 = _make_task(title='Child 1', parent_id=parent.id)
    child2 = _make_task(title='Child 2', parent_id=parent.id)
    task_repo.create(child1)
    task_repo.create(child2)

    # Complete child1 — parent should NOT auto-complete yet
    result, auto_parent_id = task_service.complete_child_task(child1.id)
    assert result == CompleteResult.OK
    assert auto_parent_id is None
    assert task_repo.get_by_id(parent.id).status == 'pending'

    # Complete child2 — all siblings done, parent should auto-complete
    result, auto_parent_id = task_service.complete_child_task(child2.id)
    assert result == CompleteResult.OK
    assert auto_parent_id == parent.id
    assert task_repo.get_by_id(parent.id).status == 'done'


def test_scenario_a_no_auto_complete_when_disabled(task_service, task_repo):
    parent = _make_task(title='Parent', auto_complete_with_children=False)
    task_repo.create(parent)

    child = _make_task(title='Child', parent_id=parent.id)
    task_repo.create(child)

    result, auto_parent_id = task_service.complete_child_task(child.id)
    assert result == CompleteResult.OK
    assert auto_parent_id is None
    assert task_repo.get_by_id(parent.id).status == 'pending'


# ------------------------------------------------------------------
# Scenario B: manual parent complete with pending children
# ------------------------------------------------------------------
def test_scenario_b_needs_confirm(task_service, task_repo):
    parent = _make_task(title='Parent')
    task_repo.create(parent)

    child = _make_task(title='Child', parent_id=parent.id)
    task_repo.create(child)

    result = task_service.complete_task_manual(parent.id)
    assert result == CompleteResult.NEEDS_CONFIRM


def test_scenario_b_complete_with_children(task_service, task_repo):
    parent = _make_task(title='Parent')
    task_repo.create(parent)

    child = _make_task(title='Child', parent_id=parent.id)
    task_repo.create(child)

    task_service.complete_parent_with_children(parent.id, include_children=True)

    assert task_repo.get_by_id(parent.id).status == 'done'
    assert task_repo.get_by_id(child.id).status == 'done'


def test_scenario_b_complete_parent_only(task_service, task_repo):
    parent = _make_task(title='Parent')
    task_repo.create(parent)

    child = _make_task(title='Child', parent_id=parent.id)
    task_repo.create(child)

    task_service.complete_parent_with_children(parent.id, include_children=False)

    assert task_repo.get_by_id(parent.id).status == 'done'
    assert task_repo.get_by_id(child.id).status == 'pending'


# ------------------------------------------------------------------
# Scenario D: restore only parent
# ------------------------------------------------------------------
def test_scenario_d_restore_parent_only(task_service, task_repo):
    parent = _make_task(title='Parent', status='done')
    task_repo.create(parent)

    child = _make_task(title='Child', parent_id=parent.id, status='done')
    task_repo.create(child)

    task_service.restore_task(parent.id)

    assert task_repo.get_by_id(parent.id).status == 'pending'
    assert task_repo.get_by_id(child.id).status == 'done'  # unchanged


# ------------------------------------------------------------------
# Scenario E: delete with cascade
# ------------------------------------------------------------------
def test_scenario_e_delete_cascade(task_service, task_repo):
    parent = _make_task(title='Parent')
    task_repo.create(parent)

    child1 = _make_task(title='Child 1', parent_id=parent.id)
    child2 = _make_task(title='Child 2', parent_id=parent.id)
    task_repo.create(child1)
    task_repo.create(child2)

    task_service.delete_task(parent.id, cascade=True)

    assert task_repo.get_by_id(parent.id) is None
    assert task_repo.get_by_id(child1.id) is None
    assert task_repo.get_by_id(child2.id) is None


def test_scenario_e_delete_unparent(task_service, task_repo):
    parent = _make_task(title='Parent')
    task_repo.create(parent)

    child = _make_task(title='Child', parent_id=parent.id)
    task_repo.create(child)

    task_service.delete_task(parent.id, cascade=False)

    assert task_repo.get_by_id(parent.id) is None
    fetched_child = task_repo.get_by_id(child.id)
    assert fetched_child is not None
    assert fetched_child.parent_id is None


def test_get_delete_preview(task_service, task_repo):
    parent = _make_task(title='Parent')
    task_repo.create(parent)

    for i in range(3):
        task_repo.create(_make_task(title=f'Child {i}', parent_id=parent.id))

    preview = task_service.get_delete_preview(parent.id)
    assert len(preview) == 3
