"""
Tests for transaction() Unit-of-Work context manager and conn= parameter support.

Covers:
- transaction() commit on success
- transaction() rollback on exception (atomicity guarantee)
- conn= parameter: write operations participate in caller's transaction
- delete_task cascade/unparent atomicity via TaskService
- complete_parent_with_children atomicity via TaskService
"""
import uuid
import pytest
import sqlite3

from src.data.models import Task
from src.data.database import transaction, get_connection
from src.data.task_repository import TaskRepository
from src.services.task_service import TaskService


def _make_task(**kwargs) -> Task:
    defaults = dict(
        id=str(uuid.uuid4()),
        title='Test',
        created_at='',
        updated_at='',
    )
    defaults.update(kwargs)
    return Task(**defaults)


# ===========================================================================
# transaction() context manager — core behaviour
# ===========================================================================

class TestTransactionContextManager:
    def test_commit_on_success(self, tmp_db, task_repo):
        """Data written inside transaction() must persist after the block exits."""
        task = _make_task(title='Committed')
        with transaction(tmp_db) as conn:
            task_repo.create(task, conn=conn)

        fetched = task_repo.get_by_id(task.id)
        assert fetched is not None
        assert fetched.title == 'Committed'

    def test_rollback_on_exception(self, tmp_db, task_repo):
        """Data written inside transaction() must NOT persist when an exception is raised."""
        task = _make_task(title='Should not persist')
        with pytest.raises(RuntimeError, match='deliberate failure'):
            with transaction(tmp_db) as conn:
                task_repo.create(task, conn=conn)
                raise RuntimeError('deliberate failure')

        assert task_repo.get_by_id(task.id) is None

    def test_partial_write_rolls_back_entirely(self, tmp_db, task_repo):
        """All writes in the block roll back together — partial commits must not occur."""
        parent = _make_task(title='Parent')
        child = _make_task(title='Child', parent_id=parent.id)

        with pytest.raises(RuntimeError):
            with transaction(tmp_db) as conn:
                task_repo.create(parent, conn=conn)
                task_repo.create(child, conn=conn)
                raise RuntimeError('abort mid-block')

        assert task_repo.get_by_id(parent.id) is None
        assert task_repo.get_by_id(child.id) is None

    def test_re_raises_original_exception(self, tmp_db):
        """transaction() must not swallow the exception — it re-raises after rollback."""
        class _Sentinel(Exception):
            pass

        with pytest.raises(_Sentinel):
            with transaction(tmp_db):
                raise _Sentinel('keep me')

    def test_connection_is_closed_after_commit(self, tmp_db):
        """The connection yielded by transaction() must be closed when the CM exits."""
        captured = []
        with transaction(tmp_db) as conn:
            captured.append(conn)
        # Attempting any operation on a closed connection raises ProgrammingError
        with pytest.raises(Exception):
            captured[0].execute('SELECT 1')

    def test_connection_is_closed_after_rollback(self, tmp_db):
        """The connection must be closed even when the transaction rolls back."""
        captured = []
        with pytest.raises(RuntimeError):
            with transaction(tmp_db) as conn:
                captured.append(conn)
                raise RuntimeError('force rollback')
        with pytest.raises(Exception):
            captured[0].execute('SELECT 1')

    def test_nested_independent_transactions(self, tmp_db, task_repo):
        """Two sequential transactions should each commit independently."""
        t1 = _make_task(title='First')
        t2 = _make_task(title='Second')

        with transaction(tmp_db) as conn:
            task_repo.create(t1, conn=conn)

        with transaction(tmp_db) as conn:
            task_repo.create(t2, conn=conn)

        assert task_repo.get_by_id(t1.id) is not None
        assert task_repo.get_by_id(t2.id) is not None


# ===========================================================================
# repository conn= parameter — write methods participate in caller transaction
# ===========================================================================

class TestRepositoryConnParameter:
    def test_update_with_external_conn(self, tmp_db, task_repo):
        """update(conn=conn) must not auto-commit; changes only persist on tx COMMIT."""
        task = _make_task(title='Original')
        task_repo.create(task)

        task.title = 'Modified inside tx'
        with transaction(tmp_db) as conn:
            task_repo.update(task, conn=conn)
            # Before commit: same connection sees the change
            row = conn.execute('SELECT title FROM tasks WHERE id=?', (task.id,)).fetchone()
            assert row['title'] == 'Modified inside tx'
        # After COMMIT: change persists for a new connection
        assert task_repo.get_by_id(task.id).title == 'Modified inside tx'

    def test_update_rollback_with_external_conn(self, tmp_db, task_repo):
        """update(conn=conn) inside a rolled-back transaction must not persist."""
        task = _make_task(title='Stable')
        task_repo.create(task)

        task.title = 'Transient change'
        with pytest.raises(RuntimeError):
            with transaction(tmp_db) as conn:
                task_repo.update(task, conn=conn)
                raise RuntimeError('rollback this')

        assert task_repo.get_by_id(task.id).title == 'Stable'

    def test_bulk_update_status_with_conn(self, tmp_db, task_repo):
        tasks = [_make_task() for _ in range(3)]
        for t in tasks:
            task_repo.create(t)

        ids = [t.id for t in tasks]
        with transaction(tmp_db) as conn:
            task_repo.bulk_update_status(ids, 'done', conn=conn)

        for tid in ids:
            assert task_repo.get_by_id(tid).status == 'done'

    def test_bulk_update_status_rollback_with_conn(self, tmp_db, task_repo):
        tasks = [_make_task() for _ in range(3)]
        for t in tasks:
            task_repo.create(t)

        ids = [t.id for t in tasks]
        with pytest.raises(RuntimeError):
            with transaction(tmp_db) as conn:
                task_repo.bulk_update_status(ids, 'done', conn=conn)
                raise RuntimeError('abort')

        for tid in ids:
            assert task_repo.get_by_id(tid).status == 'pending'

    def test_hard_delete_with_conn(self, tmp_db, task_repo):
        task = _make_task()
        task_repo.create(task)

        with transaction(tmp_db) as conn:
            task_repo.hard_delete(task.id, conn=conn)

        assert task_repo.get_by_id(task.id) is None

    def test_hard_delete_rollback_with_conn(self, tmp_db, task_repo):
        task = _make_task()
        task_repo.create(task)

        with pytest.raises(RuntimeError):
            with transaction(tmp_db) as conn:
                task_repo.hard_delete(task.id, conn=conn)
                raise RuntimeError('abort')

        assert task_repo.get_by_id(task.id) is not None

    def test_bulk_hard_delete_children_with_conn(self, tmp_db, task_repo):
        parent = _make_task(title='Parent')
        task_repo.create(parent)
        children = [_make_task(parent_id=parent.id) for _ in range(3)]
        for c in children:
            task_repo.create(c)

        with transaction(tmp_db) as conn:
            task_repo.bulk_hard_delete_children(parent.id, conn=conn)

        assert task_repo.get_children(parent.id) == []

    def test_bulk_hard_delete_children_rollback(self, tmp_db, task_repo):
        parent = _make_task(title='Parent')
        task_repo.create(parent)
        children = [_make_task(parent_id=parent.id) for _ in range(2)]
        for c in children:
            task_repo.create(c)

        with pytest.raises(RuntimeError):
            with transaction(tmp_db) as conn:
                task_repo.bulk_hard_delete_children(parent.id, conn=conn)
                raise RuntimeError('abort')

        assert len(task_repo.get_children(parent.id)) == 2

    def test_unparent_children_with_conn(self, tmp_db, task_repo):
        parent = _make_task()
        task_repo.create(parent)
        child = _make_task(parent_id=parent.id)
        task_repo.create(child)

        with transaction(tmp_db) as conn:
            task_repo.unparent_children(parent.id, conn=conn)

        assert task_repo.get_by_id(child.id).parent_id is None

    def test_unparent_children_rollback(self, tmp_db, task_repo):
        parent = _make_task()
        task_repo.create(parent)
        child = _make_task(parent_id=parent.id)
        task_repo.create(child)

        with pytest.raises(RuntimeError):
            with transaction(tmp_db) as conn:
                task_repo.unparent_children(parent.id, conn=conn)
                raise RuntimeError('abort')

        assert task_repo.get_by_id(child.id).parent_id == parent.id


# ===========================================================================
# TaskService atomicity — delete_task and complete_parent_with_children
# ===========================================================================

class TestServiceAtomicity:
    def test_delete_cascade_atomic(self, tmp_db, task_repo, monkeypatch):
        """If hard_delete raises after bulk_hard_delete_children, the entire operation
        rolls back — children must survive (no orphan records, no partial state)."""
        parent = _make_task(title='Parent')
        task_repo.create(parent)
        child1 = _make_task(title='Child 1', parent_id=parent.id)
        child2 = _make_task(title='Child 2', parent_id=parent.id)
        task_repo.create(child1)
        task_repo.create(child2)

        original_hard_delete = task_repo.hard_delete

        def _failing_hard_delete(task_id, conn=None):
            raise RuntimeError('disk full — simulated failure')

        monkeypatch.setattr(task_repo, 'hard_delete', _failing_hard_delete)

        task_service = TaskService(task_repo)
        with pytest.raises(RuntimeError, match='disk full'):
            task_service.delete_task(parent.id, cascade=True)

        # Rollback: both parent and children must still exist
        assert task_repo.get_by_id(parent.id) is not None
        assert task_repo.get_by_id(child1.id) is not None
        assert task_repo.get_by_id(child2.id) is not None

    def test_delete_unparent_atomic(self, tmp_db, task_repo, monkeypatch):
        """If hard_delete raises after unparent_children, children remain parented."""
        parent = _make_task(title='Parent')
        task_repo.create(parent)
        child = _make_task(title='Child', parent_id=parent.id)
        task_repo.create(child)

        def _failing_hard_delete(task_id, conn=None):
            raise RuntimeError('simulated failure')

        monkeypatch.setattr(task_repo, 'hard_delete', _failing_hard_delete)

        task_service = TaskService(task_repo)
        with pytest.raises(RuntimeError):
            task_service.delete_task(parent.id, cascade=False)

        # Rollback: child must still be parented
        fetched = task_repo.get_by_id(child.id)
        assert fetched is not None
        assert fetched.parent_id == parent.id

    def test_delete_cascade_success(self, task_service, task_repo):
        """Normal cascade delete must remove parent and all children."""
        parent = _make_task(title='Parent')
        task_repo.create(parent)
        children = [_make_task(parent_id=parent.id) for _ in range(3)]
        for c in children:
            task_repo.create(c)

        task_service.delete_task(parent.id, cascade=True)

        assert task_repo.get_by_id(parent.id) is None
        for c in children:
            assert task_repo.get_by_id(c.id) is None

    def test_delete_unparent_success(self, task_service, task_repo):
        """Normal unparent delete must remove parent and clear children's parent_id."""
        parent = _make_task(title='Parent')
        task_repo.create(parent)
        child = _make_task(parent_id=parent.id)
        task_repo.create(child)

        task_service.delete_task(parent.id, cascade=False)

        assert task_repo.get_by_id(parent.id) is None
        fetched = task_repo.get_by_id(child.id)
        assert fetched is not None
        assert fetched.parent_id is None

    def test_complete_parent_with_children_atomic(self, tmp_db, task_repo, monkeypatch):
        """If update(parent) raises after bulk_update_status, children must remain pending."""
        parent = _make_task(title='Parent')
        task_repo.create(parent)
        child1 = _make_task(parent_id=parent.id)
        child2 = _make_task(parent_id=parent.id)
        task_repo.create(child1)
        task_repo.create(child2)

        original_update = task_repo.update

        call_count = {'n': 0}

        def _failing_update(task, conn=None):
            call_count['n'] += 1
            if call_count['n'] >= 1:
                raise RuntimeError('simulated parent update failure')
            return original_update(task, conn=conn)

        monkeypatch.setattr(task_repo, 'update', _failing_update)

        task_service = TaskService(task_repo)
        with pytest.raises(RuntimeError, match='simulated parent update failure'):
            task_service.complete_parent_with_children(parent.id, include_children=True)

        # Rollback: children must still be pending
        assert task_repo.get_by_id(child1.id).status == 'pending'
        assert task_repo.get_by_id(child2.id).status == 'pending'
        assert task_repo.get_by_id(parent.id).status == 'pending'

    def test_complete_parent_with_children_success(self, task_service, task_repo):
        """Normal complete_parent_with_children must mark parent + children as done."""
        parent = _make_task(title='Parent')
        task_repo.create(parent)
        child = _make_task(parent_id=parent.id)
        task_repo.create(child)

        task_service.complete_parent_with_children(parent.id, include_children=True)

        assert task_repo.get_by_id(parent.id).status == 'done'
        assert task_repo.get_by_id(child.id).status == 'done'

    def test_complete_parent_only_leaves_children_pending(self, task_service, task_repo):
        """complete_parent_with_children(include_children=False) must not touch children."""
        parent = _make_task(title='Parent')
        task_repo.create(parent)
        child = _make_task(parent_id=parent.id)
        task_repo.create(child)

        task_service.complete_parent_with_children(parent.id, include_children=False)

        assert task_repo.get_by_id(parent.id).status == 'done'
        assert task_repo.get_by_id(child.id).status == 'pending'
