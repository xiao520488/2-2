# -*- coding: utf-8 -*-
"""
迁移 insights 表：input_hash 由 NOT NULL UNIQUE -> 可空 + 部分唯一索引。
备份原表 -> 建新表 -> 搬数据 -> 校验 -> 删除备份（失败则回滚）。
"""
import sqlite3, shutil, os, datetime, sys

DB = r"D:\agent-lab\3\competitions.db"
STAMP = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
BAK = DB + ".bak_" + STAMP

shutil.copy2(DB, BAK)
print("BACKUP ->", BAK)

con = sqlite3.connect(DB)
con.execute("PRAGMA foreign_keys=OFF")
try:
    before = list(con.execute("SELECT COUNT(*) FROM insights"))[0][0]
    print("insights before:", before)

    con.execute("BEGIN")
    con.execute("""
        CREATE TABLE insights_new (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            kind       TEXT NOT NULL,
            scope      TEXT NOT NULL,
            content_md TEXT NOT NULL,
            evidence   TEXT,
            model      TEXT,
            input_hash TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now','localtime')),
            CHECK (kind IN ('experience','trend','gap'))
        )
    """)
    con.execute("""
        INSERT INTO insights_new (id, kind, scope, content_md, evidence, model, input_hash, created_at)
        SELECT id, kind, scope, content_md, evidence, model, input_hash, created_at FROM insights
    """)
    moved = con.execute("SELECT COUNT(*) FROM insights_new").fetchone()[0]
    print("rows moved:", moved)
    assert moved == before, "row count mismatch"

    con.execute("DROP TABLE insights")
    con.execute("ALTER TABLE insights_new RENAME TO insights")
    con.execute("""
        CREATE UNIQUE INDEX idx_insights_hash
        ON insights(input_hash) WHERE input_hash IS NOT NULL
    """)
    con.execute("CREATE INDEX idx_insights_kind_scope ON insights(kind, scope)")
    con.execute("COMMIT")
    print("MIGRATE_OK")
except Exception as e:
    con.execute("ROLLBACK")
    print("MIGRATE_FAILED:", type(e).__name__, e)
    con.close()
    sys.exit(1)

# ---- 校验 ----
print("=== new schema ===")
for r in con.execute("PRAGMA table_info(insights)"):
    print(r)
print("=== indexes ===")
for r in con.execute("PRAGMA index_list(insights)"):
    print(r)

print("=== rows ===")
for r in con.execute("SELECT id,kind,scope,input_hash FROM insights ORDER BY id"):
    print(r)

print("=== 允许 NULL 插入（模拟 trend/gap 不写 hash）===")
con.execute("""INSERT INTO insights(kind,scope,content_md,model,input_hash)
               VALUES('trend','__NULLTEST__','x','m',NULL)""")
con.execute("""INSERT INTO insights(kind,scope,content_md,model,input_hash)
               VALUES('trend','__NULLTEST__','y','m',NULL)""")
print("两条 NULL hash 插入成功（UNIQUE 对 NULL 不生效）")

print("=== 非 NULL 重复 hash 必须被拒 ===")
try:
    con.execute("""INSERT INTO insights(kind,scope,content_md,model,input_hash)
                   VALUES('gap','__DUP__','z','m','SAMEHASH')""")
    con.execute("""INSERT INTO insights(kind,scope,content_md,model,input_hash)
                   VALUES('gap','__DUP2__','w','m','SAMEHASH')""")
    print("BUG: 重复 hash 竟然插入成功")
except sqlite3.IntegrityError as e:
    print("OK, 重复 hash 被拒绝:", e)

con.execute("DELETE FROM insights WHERE scope IN ('__NULLTEST__','__DUP__','__DUP2__')")
con.commit()
print("cleanup test rows -> remaining:", con.execute("SELECT COUNT(*) FROM insights").fetchone()[0])
con.close()
print("DONE")
