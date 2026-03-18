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


def test_soft_delete(task_repo):
    task = _make_task(title='To delete')
    task_repo.create(task)
    task_repo.soft_delete(task.id)

    all_active = task_repo.get_all_active()
    assert not any(t.id == task.id for t in all_active)


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
