"""
SettingsRepository: simple key/value store backed by the settings table.
"""
from __future__ import annotations
from pathlib import Path
from typing import Optional

from src.data.database import get_connection
from src.core.paths import DB_PATH


class SettingsRepository:
    def __init__(self, db_path: Path = None):
        self._db = db_path or DB_PATH

    def get(self, key: str, default: str = '') -> str:
        with get_connection(self._db) as conn:
            row = conn.execute(
                'SELECT value FROM settings WHERE key=?', (key,)
            ).fetchone()
        return row['value'] if row else default

    def set(self, key: str, value: str) -> None:
        with get_connection(self._db) as conn:
            conn.execute(
                'INSERT INTO settings(key, value) VALUES(?,?) '
                'ON CONFLICT(key) DO UPDATE SET value=excluded.value',
                (key, value)
            )
            conn.commit()

    def get_all(self) -> dict:
        with get_connection(self._db) as conn:
            rows = conn.execute('SELECT key, value FROM settings').fetchall()
        return {r['key']: r['value'] for r in rows}
