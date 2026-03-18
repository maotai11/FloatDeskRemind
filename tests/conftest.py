"""
Shared pytest fixtures for all tests.
"""
import sys
import os
import pytest

# Ensure project root is in path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture
def tmp_db(tmp_path):
    """Create an in-memory style temp DB file with migrations applied."""
    db_path = tmp_path / 'test.db'
    from src.data.database import run_migrations
    run_migrations(db_path)
    return db_path


@pytest.fixture
def task_repo(tmp_db):
    from src.data.task_repository import TaskRepository
    return TaskRepository(tmp_db)


@pytest.fixture
def task_service(task_repo):
    from src.services.task_service import TaskService
    return TaskService(task_repo)


@pytest.fixture
def settings_repo(tmp_db):
    from src.data.settings_repository import SettingsRepository
    return SettingsRepository(tmp_db)
