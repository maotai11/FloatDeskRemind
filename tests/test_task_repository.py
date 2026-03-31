"""
Test TaskRepository with a real temp SQLite DB.
"""
import uuid
import pytest
from datetime import date, timedelta

from src.data.models import Task
from src.data.task_repository import TaskRepository


def _make_task(**kwargs) -> Task:
    defaults = dict(
        id=str(uuid.uuid4()),
        title='Test Task',
        created_at='',
        updated_at='',
    )
    defaults.update(kwargs)
    return Task(**defaults)


def test_create_and_get(task_repo):
    task = _make_task(title='Buy groceries', due_date='2026-03-20')
    created = task_repo.create(task)
    assert created.id == task.id

    fetched = task_repo.get_by_id(task.id)
    assert fetched is not None
    assert fetched.title == 'Buy groceries'
    assert fetched.due_date == '2026-03-20'


def test_get_nonexistent(task_repo):
    assert task_repo.get_by_id('nonexistent') is None


def test_update(task_repo):
    task = _make_task(title='Original')
    task_repo.create(task)
    task.title = 'Updated'
    task.priority = 'high'
    task_repo.update(task)

    fetched = task_repo.get_by_id(task.id)
    assert fetched.title == 'Updated'
    assert fetched.priority == 'high'


def test_soft_delete_sets_status_and_deleted_at(task_repo):
    task = _make_task(title='To delete')
    task_repo.create(task)
    task_repo.soft_delete(task.id)

    fetched = task_repo.get_by_id(task.id)
    assert fetched is not None
    assert fetched.status == 'deleted'
    assert fetched.deleted_at is not None


def test_soft_delete_hides_from_get_all_non_deleted(task_repo):
    task = _make_task(title='To delete')
    task_repo.create(task)
    task_repo.soft_delete(task.id)

    all_tasks = task_repo.get_all_non_deleted()
    assert not any(t.id == task.id for t in all_tasks)


def test_get_deleted_returns_soft_deleted(task_repo):
    task = _make_task(title='Deleted task')
    task_repo.create(task)
    task_repo.soft_delete(task.id)

    deleted = task_repo.get_deleted()
    assert any(t.id == task.id for t in deleted)


def test_get_deleted_newest_first(task_repo):
    t1 = _make_task(title='First deleted')
    t2 = _make_task(title='Second deleted')
    task_repo.create(t1)
    task_repo.create(t2)
    task_repo.soft_delete(t1.id)
    task_repo.soft_delete(t2.id)

    deleted = task_repo.get_deleted()
    ids = [t.id for t in deleted]
    assert ids.index(t2.id) < ids.index(t1.id)


def test_restore_from_trash_sets_pending(task_repo):
    task = _make_task(title='Restore me')
    task_repo.create(task)
    task_repo.soft_delete(task.id)
    task_repo.restore_from_trash(task.id)

    fetched = task_repo.get_by_id(task.id)
    assert fetched.status == 'pending'
    assert fetched.deleted_at is None


def test_restore_from_trash_does_not_restore_done_task(task_repo):
    task = _make_task(title='Done task', status='done')
    task_repo.create(task)
    task_repo.restore_from_trash(task.id)  # guard: WHERE status='deleted', should be no-op

    fetched = task_repo.get_by_id(task.id)
    assert fetched.status == 'done'  # unchanged


def test_permanently_delete_removes_row(task_repo):
    task = _make_task(title='Permanent')
    task_repo.create(task)
    task_repo.soft_delete(task.id)
    task_repo.permanently_delete(task.id)

    assert task_repo.get_by_id(task.id) is None


def test_bulk_soft_delete_children_marks_all(task_repo):
    parent = _make_task(title='Parent')
    task_repo.create(parent)
    children = [_make_task(parent_id=parent.id) for _ in range(3)]
    for c in children:
        task_repo.create(c)

    task_repo.bulk_soft_delete_children(parent.id)

    for c in children:
        fetched = task_repo.get_by_id(c.id)
        assert fetched.status == 'deleted'


def test_get_by_due_dates_includes_done_excludes_deleted(task_repo):
    today = date.today().isoformat()
    done_task = _make_task(title='Done task', due_date=today, status='done')
    deleted_task = _make_task(title='Deleted task', due_date=today)
    task_repo.create(done_task)
    task_repo.create(deleted_task)
    task_repo.soft_delete(deleted_task.id)

    results = task_repo.get_by_due_dates([today])
    ids = {t.id for t in results}
    assert done_task.id in ids        # done tasks are included
    assert deleted_task.id not in ids  # deleted tasks are excluded


def test_hard_delete(task_repo):
    task = _make_task()
    task_repo.create(task)
    task_repo.hard_delete(task.id)
    assert task_repo.get_by_id(task.id) is None


def test_get_by_due_dates(task_repo):
    today = date.today().isoformat()
    tomorrow = (date.today() + timedelta(days=1)).isoformat()

    t1 = _make_task(title='Today task', due_date=today)
    t2 = _make_task(title='Tomorrow task', due_date=tomorrow)
    t3 = _make_task(title='No date task')
    task_repo.create(t1)
    task_repo.create(t2)
    task_repo.create(t3)

    results = task_repo.get_by_due_dates([today, tomorrow])
    ids = {t.id for t in results}
    assert t1.id in ids
    assert t2.id in ids
    assert t3.id not in ids


def test_get_children(task_repo):
    parent = _make_task(title='Parent')
    child1 = _make_task(title='Child 1')
    child2 = _make_task(title='Child 2')

    task_repo.create(parent)
    child1.parent_id = parent.id
    child2.parent_id = parent.id
    task_repo.create(child1)
    task_repo.create(child2)

    children = task_repo.get_children(parent.id)
    assert len(children) == 2


def test_unparent_children(task_repo):
    parent = _make_task(title='Parent')
    child = _make_task(title='Child', parent_id=None)
    task_repo.create(parent)
    child.parent_id = parent.id
    task_repo.create(child)

    task_repo.unparent_children(parent.id)
    fetched_child = task_repo.get_by_id(child.id)
    assert fetched_child.parent_id is None


def test_bulk_update_status(task_repo):
    tasks = [_make_task(title=f'Task {i}') for i in range(3)]
    for t in tasks:
        task_repo.create(t)

    ids = [t.id for t in tasks]
    task_repo.bulk_update_status(ids, 'done')

    for tid in ids:
        t = task_repo.get_by_id(tid)
        assert t.status == 'done'
        assert t.completed_at is not None


def test_search(task_repo):
    task_repo.create(_make_task(title='Buy milk'))
    task_repo.create(_make_task(title='Call dentist'))
    task_repo.create(_make_task(title='Write report'))

    results = task_repo.search('milk')
    assert len(results) == 1
    assert results[0].title == 'Buy milk'
