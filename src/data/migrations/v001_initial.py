"""
Migration v001: Create all initial tables.
"""

SQL = """
CREATE TABLE IF NOT EXISTS tasks (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    description TEXT DEFAULT '',
    status TEXT NOT NULL DEFAULT 'pending',
    priority TEXT NOT NULL DEFAULT 'none',
    parent_id TEXT REFERENCES tasks(id) ON DELETE SET NULL,
    sort_order REAL NOT NULL DEFAULT 0,
    start_date TEXT,
    due_date TEXT,
    due_time TEXT,
    is_countdown INTEGER NOT NULL DEFAULT 0,
    countdown_target TEXT,
    is_recurring INTEGER NOT NULL DEFAULT 0,
    recurrence_rule TEXT,
    estimated_minutes INTEGER,
    auto_complete_with_children INTEGER NOT NULL DEFAULT 1,
    completed_at TEXT,
    deleted_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_tasks_parent ON tasks(parent_id);
CREATE INDEX IF NOT EXISTS idx_tasks_due_date ON tasks(due_date);
CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);

CREATE TABLE IF NOT EXISTS task_tags (
    task_id TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    tag TEXT NOT NULL,
    PRIMARY KEY (task_id, tag)
);

CREATE TABLE IF NOT EXISTS task_reminders (
    id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    mode TEXT NOT NULL DEFAULT 'before',
    minutes_before INTEGER,
    remind_at TEXT,
    is_fired INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS task_phases (
    id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    sort_order REAL NOT NULL DEFAULT 0,
    start_date TEXT,
    due_date TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    depends_on_previous INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS db_version (
    version INTEGER PRIMARY KEY
);
"""

DEFAULT_SETTINGS = [
    ('theme', 'light'),
    ('accent_color', 'blue'),
    ('font_size', 'medium'),
    ('float_opacity', '0.95'),
    ('display_days', '3'),
    ('auto_backup', 'daily'),
    ('auto_start', 'false'),
    ('language', 'zh-TW'),
]

VERSION = 1


def run(conn) -> None:
    # executescript handles multiple DDL statements safely without string-splitting
    conn.executescript(SQL)

    cursor = conn.cursor()
    for key, value in DEFAULT_SETTINGS:
        cursor.execute(
            'INSERT OR IGNORE INTO settings(key, value) VALUES (?, ?)',
            (key, value)
        )
    cursor.execute('INSERT OR IGNORE INTO db_version(version) VALUES (?)', (VERSION,))
    conn.commit()
