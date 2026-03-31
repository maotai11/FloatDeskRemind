# Migration Authoring Guidelines

適用於 `src/data/migrations/` 下的所有 migration 模組。

---

## 1. 命名與結構

每個 migration 是一個獨立的 Python 模組，放在 `src/data/migrations/` 下：

```
src/data/migrations/
    v001_initial.py
    v002_soft_delete_index.py
    v003_your_feature.py   ← 新增時遵循此格式
```

**命名規則**：`v<三位數版本號>_<簡短說明>.py`，例如 `v003_add_priority_column.py`

每個模組必須定義：

```python
VERSION = 3          # 正整數，全域唯一，不可與其他模組重複
                     # 不得使用 bool（True/False）、float、str

def run(conn) -> None:
    """Apply this migration. Must be idempotent."""
    ...
```

---

## 2. 冪等性要求（Idempotency）

**所有 migration 必須支援重複執行，結果不變。**

若 migration 失敗後重試（例如：網路中斷、磁碟滿、程序被強制關閉），系統會重新跑同一個 migration。非冪等的操作將導致資料損壞或啟動永遠失敗。

### DDL — 使用 `IF NOT EXISTS` / `IF EXISTS`

```python
# ✅ 正確
conn.execute('''
    CREATE TABLE IF NOT EXISTS task_phases (
        id    TEXT PRIMARY KEY,
        name  TEXT NOT NULL
    )
''')

conn.execute('''
    CREATE INDEX IF NOT EXISTS idx_tasks_status_deleted_at
    ON tasks(status, deleted_at)
''')

conn.execute('DROP INDEX IF EXISTS idx_old_unused')
```

```python
# ❌ 錯誤 — 第二次執行會拋 OperationalError: table already exists
conn.execute('CREATE TABLE task_phases (id TEXT PRIMARY KEY, name TEXT NOT NULL)')
```

### DML — 使用 `INSERT OR IGNORE` / `INSERT OR REPLACE` / `WHERE NOT EXISTS`

```python
# ✅ 正確 — 重複執行不新增重複資料
conn.execute(
    "INSERT OR IGNORE INTO settings(key, value) VALUES (?, ?)",
    ('theme', 'light')
)

# ✅ 正確 — 版本號記錄
conn.execute(
    'INSERT OR IGNORE INTO db_version(version) VALUES (?)',
    (VERSION,)
)
```

```python
# ❌ 錯誤 — 重複執行會插入重複列
conn.execute("INSERT INTO settings(key, value) VALUES ('theme', 'light')")
```

### ALTER TABLE — 先查欄位是否存在

SQLite 不支援 `ALTER TABLE ADD COLUMN IF NOT EXISTS`，需手動查詢：

```python
# ✅ 正確
def _column_exists(conn, table: str, column: str) -> bool:
    rows = conn.execute(f'PRAGMA table_info({table})').fetchall()
    return any(row['name'] == column for row in rows)

def run(conn) -> None:
    if not _column_exists(conn, 'tasks', 'priority'):
        conn.execute('ALTER TABLE tasks ADD COLUMN priority INTEGER DEFAULT 0')
    conn.execute('INSERT OR IGNORE INTO db_version(version) VALUES (?)', (VERSION,))
    conn.commit()
```

---

## 3. DDL / DML 混用風險

**同一個 migration 若同時包含 DDL（建表/建索引/ALTER）和 DML（INSERT/UPDATE），需特別注意執行順序。**

### 安全的混用順序

```python
def run(conn) -> None:
    # Step 1: 先做 DDL（結構變更）
    conn.execute('ALTER TABLE tasks ADD COLUMN archived_at TEXT')

    # Step 2: 再做 DML（資料填補），使用冪等寫法
    conn.execute(
        "UPDATE tasks SET archived_at = updated_at WHERE status = 'archived' AND archived_at IS NULL"
    )

    # Step 3: 版本號 + commit 放在最後
    conn.execute('INSERT OR IGNORE INTO db_version(version) VALUES (?)', (VERSION,))
    conn.commit()
```

### 危險的混用模式

```python
# ❌ 危險 — commit 在中途，若後續 DML 失敗，DDL 已不可回滾
def run(conn) -> None:
    conn.execute('CREATE TABLE foo (...)')
    conn.commit()   # ← 中途 commit
    conn.execute("INSERT INTO foo VALUES (...)")   # 若這裡失敗，表已建但資料未插入
    conn.commit()
```

**規則**：一個 `run()` 函式只呼叫一次 `conn.commit()`，放在函式最末尾。

---

## 4. conn.commit() 的位置

```python
def run(conn) -> None:
    # ... 所有 DDL 和 DML 操作 ...
    conn.execute('INSERT OR IGNORE INTO db_version(version) VALUES (?)', (VERSION,))
    conn.commit()   # ← 必須是 run() 的最後一行，且只呼叫一次
```

- `run()` 收到的 `conn` 是由 `get_connection()` 提供的 autocommit 連線。
- 若 migration runner 改為使用 `transaction()` 包覆，`conn.commit()` 可省略（由外層 CM 負責）。目前版本仍需在 `run()` 內呼叫。
- **不得在 `run()` 內呼叫 `conn.rollback()`**；失敗時拋出例外即可，migration runner 會捕獲並包裝為 RuntimeError。

---

## 5. 測試要求

每個新 migration 需有對應的測試，驗證以下三項：

### 5.1 結構正確性

```python
def test_v003_creates_column(tmp_path):
    run_migrations(tmp_path / 'test.db')
    conn = sqlite3.connect(str(tmp_path / 'test.db'))
    cols = {row[1] for row in conn.execute('PRAGMA table_info(tasks)')}
    conn.close()
    assert 'priority' in cols
```

### 5.2 冪等性

```python
def test_v003_idempotent(tmp_path):
    db = tmp_path / 'test.db'
    run_migrations(db)
    run_migrations(db)   # 第二次不得 raise，版本不得改變
    assert get_current_version(db) == 3
```

### 5.3 從上一版升級（不重跑已套用的 migration）

```python
def test_upgrade_from_v2_to_v3(tmp_path):
    db = tmp_path / 'upgrade.db'
    run_migrations(db)
    # 手動降回 v2
    conn = sqlite3.connect(str(db))
    conn.execute('DELETE FROM db_version WHERE version > 2')
    conn.execute('ALTER TABLE tasks RENAME COLUMN priority TO _priority_bak')  # 模擬 v3 未跑
    conn.commit()
    conn.close()

    run_migrations(db)
    assert get_current_version(db) == 3
```

新 migration 的測試加入 `tests/test_database_migration.py` 的 `TestAutoDiscovery` class。

---

## 6. 失敗重跑要求

Migration runner 的行為：

| 狀況 | 行為 |
|------|------|
| migration 拋出例外 | 包裝為 RuntimeError，停止所有後續 migration，阻止 app 啟動 |
| migration 成功 | `db_version` 寫入版本號，下次啟動自動跳過 |
| migration 部分成功（沒 commit）| 重新跑同一 migration——**因此 run() 必須冪等** |
| 版本號已存在 | 跳過（`current >= version` 判斷） |

### 常見的「部分成功」情境

- DDL 執行成功，但 `conn.commit()` 前 process 被 kill → 重跑時 `CREATE TABLE IF NOT EXISTS` 安全通過
- DML 執行一半，commit 前斷電 → 重跑時 `INSERT OR IGNORE` 不產生重複資料

**因此：確保 DDL 用 `IF NOT EXISTS`，DML 用 `OR IGNORE`，才能保證重跑安全。**

---

## 7. 禁止事項

| 禁止 | 原因 |
|------|------|
| `DROP TABLE` / `DROP COLUMN`（無 IF EXISTS） | 重跑會失敗 |
| `INSERT` 不加 `OR IGNORE` / `OR REPLACE` | 重跑產生重複資料 |
| `conn.commit()` 在 `run()` 中途呼叫多次 | 無法原子回滾 |
| 在 `run()` 內呼叫 `conn.rollback()` | 干擾 migration runner 的錯誤處理 |
| `VERSION` 使用 bool、float、str、負數、0 | runtime 驗證會 raise RuntimeError |
| 兩個模組使用相同 `VERSION` | 啟動時 raise RuntimeError（Duplicate VERSION） |
| 修改已套用的 migration | 已上線的 migration 永不修改；新需求建新版本 |
