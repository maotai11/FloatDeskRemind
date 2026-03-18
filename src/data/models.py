"""
Dataclass models mapping to DB tables.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional
from datetime import datetime


@dataclass
class Task:
    id: str
    title: str
    description: str = ''
    status: str = 'pending'          # pending / done / archived / deleted
    priority: str = 'none'           # high / medium / low / none
    parent_id: Optional[str] = None
    sort_order: float = 0.0
    start_date: Optional[str] = None
    due_date: Optional[str] = None
    due_time: Optional[str] = None
    is_countdown: bool = False
    countdown_target: Optional[str] = None
    is_recurring: bool = False
    recurrence_rule: Optional[str] = None
    estimated_minutes: Optional[int] = None
    auto_complete_with_children: bool = True
    completed_at: Optional[str] = None
    deleted_at: Optional[str] = None
    created_at: str = ''
    updated_at: str = ''

    @classmethod
    def from_row(cls, row) -> 'Task':
        d = dict(row)
        return cls(
            id=d['id'],
            title=d['title'],
            description=d.get('description') or '',
            status=d.get('status', 'pending'),
            priority=d.get('priority', 'none'),
            parent_id=d.get('parent_id'),
            sort_order=d.get('sort_order', 0.0),
            start_date=d.get('start_date'),
            due_date=d.get('due_date'),
            due_time=d.get('due_time'),
            is_countdown=bool(d.get('is_countdown', 0)),
            countdown_target=d.get('countdown_target'),
            is_recurring=bool(d.get('is_recurring', 0)),
            recurrence_rule=d.get('recurrence_rule'),
            estimated_minutes=d.get('estimated_minutes'),
            auto_complete_with_children=bool(d.get('auto_complete_with_children', 1)),
            completed_at=d.get('completed_at'),
            deleted_at=d.get('deleted_at'),
            created_at=d.get('created_at', ''),
            updated_at=d.get('updated_at', ''),
        )


@dataclass
class TaskTag:
    task_id: str
    tag: str


@dataclass
class TaskReminder:
    id: str
    task_id: str
    mode: str = 'before'
    minutes_before: Optional[int] = None
    remind_at: Optional[str] = None
    is_fired: bool = False


@dataclass
class TaskPhase:
    id: str
    task_id: str
    name: str
    sort_order: float = 0.0
    start_date: Optional[str] = None
    due_date: Optional[str] = None
    status: str = 'pending'
    depends_on_previous: bool = False
