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

    # Soft delete: rows still exist but status='deleted'
    assert task_repo.get_by_id(parent.id).status == 'deleted'
    assert task_repo.get_by_id(child1.id).status == 'deleted'
    assert task_repo.get_by_id(child2.id).status == 'deleted'


def test_scenario_e_delete_unparent(task_service, task_repo):
    parent = _make_task(title='Parent')
    task_repo.create(parent)

    child = _make_task(title='Child', parent_id=parent.id)
    task_repo.create(child)

    task_service.delete_task(parent.id, cascade=False)

    # Parent soft-deleted; child unparented and still pending
    assert task_repo.get_by_id(parent.id).status == 'deleted'
    fetched_child = task_repo.get_by_id(child.id)
    assert fetched_child is not None
    assert fetched_child.parent_id is None
    assert fetched_child.status == 'pending'


# ------------------------------------------------------------------
# Recycle bin
# ------------------------------------------------------------------
def test_delete_task_soft_deletes_not_hard(task_service, task_repo):
    task = _make_task(title='Soft deleted')
    task_repo.create(task)
    task_service.delete_task(task.id, cascade=False)

    fetched = task_repo.get_by_id(task.id)
    assert fetched is not None
    assert fetched.status == 'deleted'


def test_delete_cascade_soft_deletes_children(task_service, task_repo):
    parent = _make_task(title='Parent')
    task_repo.create(parent)
    child = _make_task(parent_id=parent.id)
    task_repo.create(child)

    task_service.delete_task(parent.id, cascade=True)

    assert task_repo.get_by_id(child.id).status == 'deleted'


def test_get_recycle_bin(task_service, task_repo):
    task = _make_task(title='In trash')
    task_repo.create(task)
    task_service.delete_task(task.id, cascade=False)

    bin_tasks = task_service.get_recycle_bin()
    assert any(t.id == task.id for t in bin_tasks)


def test_restore_from_trash_via_service(task_service, task_repo):
    task = _make_task(title='Restore me')
    task_repo.create(task)
    task_service.delete_task(task.id, cascade=False)
    task_service.restore_from_trash(task.id)

    fetched = task_repo.get_by_id(task.id)
    assert fetched.status == 'pending'
    assert fetched.deleted_at is None


def test_permanently_delete_via_service(task_service, task_repo):
    task = _make_task(title='Permanent')
    task_repo.create(task)
    task_service.delete_task(task.id, cascade=False)
    task_service.permanently_delete(task.id)

    assert task_repo.get_by_id(task.id) is None


def test_get_delete_preview(task_service, task_repo):
    parent = _make_task(title='Parent')
    task_repo.create(parent)

    for i in range(3):
        task_repo.create(_make_task(title=f'Child {i}', parent_id=parent.id))

    preview = task_service.get_delete_preview(parent.id)
    assert len(preview) == 3
