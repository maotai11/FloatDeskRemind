"""
Test SortService sorting rules.
"""
import uuid
import pytest
from datetime import date, timedelta

from src.data.models import Task
from src.services.sort_service import sort_tasks


def _make_task(**kwargs) -> Task:
    defaults = dict(
        id=str(uuid.uuid4()),
        title='Test',
        created_at='',
        updated_at='',
    )
    defaults.update(kwargs)
    return Task(**defaults)


def test_overdue_first():
    today = date.today()
    yesterday = (today - timedelta(days=1)).isoformat()
    today_str = today.isoformat()

    overdue = _make_task(title='Overdue', due_date=yesterday)
    normal = _make_task(title='Normal', due_date=today_str)

    sorted_tasks = sort_tasks([normal, overdue], reference_date=today)
    assert sorted_tasks[0].title == 'Overdue'


def test_due_time_before_no_time():
    today = date.today()
    today_str = today.isoformat()

    timed = _make_task(title='Timed', due_date=today_str, due_time='09:00')
    untimed = _make_task(title='Untimed', due_date=today_str)

    sorted_tasks = sort_tasks([untimed, timed], reference_date=today)
    assert sorted_tasks[0].title == 'Timed'


def test_time_ascending():
    today = date.today()
    today_str = today.isoformat()

    t1 = _make_task(title='Late', due_date=today_str, due_time='15:00')
    t2 = _make_task(title='Early', due_date=today_str, due_time='08:00')

    sorted_tasks = sort_tasks([t1, t2], reference_date=today)
    assert sorted_tasks[0].title == 'Early'


def test_priority_order_without_time():
    today = date.today()
    today_str = today.isoformat()

    high = _make_task(title='High', due_date=today_str, priority='high')
    medium = _make_task(title='Medium', due_date=today_str, priority='medium')
    low = _make_task(title='Low', due_date=today_str, priority='low')
    none_ = _make_task(title='None', due_date=today_str, priority='none')

    sorted_tasks = sort_tasks([none_, low, medium, high], reference_date=today)
    titles = [t.title for t in sorted_tasks]
    assert titles == ['High', 'Medium', 'Low', 'None']


def test_sort_order_tiebreaker():
    today = date.today()
    today_str = today.isoformat()

    t1 = _make_task(title='B', due_date=today_str, priority='high', sort_order=2.0)
    t2 = _make_task(title='A', due_date=today_str, priority='high', sort_order=1.0)

    sorted_tasks = sort_tasks([t1, t2], reference_date=today)
    assert sorted_tasks[0].title == 'A'


def test_empty_list():
    assert sort_tasks([]) == []
