"""v002: Add index on (status, deleted_at) to accelerate recycle bin queries."""
VERSION = 2


def run(conn) -> None:
    conn.execute(
        'CREATE INDEX IF NOT EXISTS idx_tasks_status_deleted_at '
        'ON tasks(status, deleted_at)'
    )
    conn.execute('INSERT OR IGNORE INTO db_version(version) VALUES (?)', (VERSION,))
    conn.commit()
