"""验证 init_db：创建数据库并检查表结构。不导入任何业务数据。"""
import json
import os
import sqlite3
import db

# 1) 执行建库
db.init_db()
print("db file exists:", os.path.exists(db.DB_PATH))

# 2) 直接查 sqlite_master，看表与索引
conn = sqlite3.connect(db.DB_PATH)
conn.row_factory = sqlite3.Row

tables = [dict(r) for r in conn.execute(
    "SELECT type, name FROM sqlite_master WHERE type IN ('table','index') ORDER BY type, name"
)]
cols = [dict(r) for r in conn.execute("PRAGMA table_info(competitions)")]
count = conn.execute("SELECT COUNT(*) AS c FROM competitions").fetchone()["c"]
conn.close()

out = {"tables": tables, "columns": cols, "row_count": count}
json.dump(out, open("_init_check.json", "w", encoding="utf-8"), ensure_ascii=False, indent=2)
print("row_count:", count)
