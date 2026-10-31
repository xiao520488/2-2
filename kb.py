"""
竞赛知识库 - 数据访问层 (kb.py)

职责：
    1. 开启 SQLite WAL 模式（读写并发不阻塞）
    2. 执行 schema_kb.sql 建表（幂等）
    3. 提供 awards / search_leads / crawl_jobs / insights / ideas 的通用读写辅助

设计约定：
    - 真值源永远是 SQLite；Chroma 只是可重建的向量索引
    - 所有写操作自动维护 updated_at
    - 返回 dict（sqlite3.Row -> dict），便于上层直接消费
"""

import json
import os
import sqlite3
from contextlib import contextmanager
from typing import Any, Iterable, Optional

# 与 db.py 共用同一个数据库文件
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "competitions.db")
SCHEMA_KB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "schema_kb.sql")

# 合法表名白名单（防注入，所有动态表名必须来自此处）
_TABLES = ("awards", "search_leads", "crawl_jobs", "insights", "ideas")


# ============================================================
# 一、连接与初始化
# ============================================================

def get_conn() -> sqlite3.Connection:
    """
    获取连接，并确保 WAL / busy_timeout 生效。

    - journal_mode=WAL：读写并发不互相阻塞（页面读时爬虫可写）
    - busy_timeout=5000：锁等待 5 秒后报错，而非立即失败
    - synchronous=NORMAL：WAL 下的安全/性能平衡点
    - foreign_keys=ON：预留外键约束
    """
    conn = sqlite3.connect(DB_PATH, timeout=10.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


@contextmanager
def conn_ctx():
    """
    上下文管理器：正确提交/回滚 + 关闭。

        with conn_ctx() as conn:
            conn.execute(...)
    """
    conn = get_conn()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_kb(db_path: Optional[str] = None) -> dict:
    """
    初始化知识库：建表 + 建索引（可重复调用）。

    返回:
        {"journal_mode": "wal", "tables": [...], "created_columns": {...}}
    """
    global DB_PATH
    if db_path:
        DB_PATH = db_path

    with open(SCHEMA_KB_PATH, encoding="utf-8") as f:
        schema_sql = f.read()

    with conn_ctx() as conn:
        # competitions 表补列（若该表存在）
        migrated = _migrate_competitions(conn)
        conn.executescript(schema_sql)
        mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
        tables = [
            r["name"]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' "
                "AND name NOT LIKE 'sqlite_%' ORDER BY name"
            ).fetchall()
        ]

    return {"journal_mode": mode, "tables": tables, "created_columns": migrated}


# competitions 需追加的列（架构方案 2.2 节）
_COMPETITION_NEW_COLUMNS = {
    "discover_source": "TEXT",
    "last_checked_at": "TEXT",
    "is_active": "INTEGER DEFAULT 1",
}


def _migrate_competitions(conn: sqlite3.Connection) -> list:
    """为已存在的 competitions 表补齐知识库所需列。表不存在则跳过。"""
    exists = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='competitions'"
    ).fetchone()
    if not exists:
        return []
    existing = {r["name"] for r in conn.execute("PRAGMA table_info(competitions)")}
    added = []
    for col, ddl in _COMPETITION_NEW_COLUMNS.items():
        if col not in existing:
            conn.execute(f"ALTER TABLE competitions ADD COLUMN {col} {ddl}")
            added.append(col)
    return added


# ============================================================
# 二、通用辅助
# ============================================================

def _check_table(table: str) -> str:
    if table not in _TABLES:
        raise ValueError(f"未知表名: {table}（允许: {_TABLES}）")
    return table


def _row_to_dict(row: Optional[sqlite3.Row]) -> Optional[dict]:
    return dict(row) if row is not None else None


def insert(table: str, data: dict, *, conn: Optional[sqlite3.Connection] = None) -> int:
    """插入一行，返回自增 id。冲突时抛 sqlite3.IntegrityError。"""
    table = _check_table(table)
    cols = list(data.keys())
    sql = (
        f"INSERT INTO {table} ({', '.join(cols)}) "
        f"VALUES ({', '.join('?' for _ in cols)})"
    )
    params = [data[c] for c in cols]

    if conn is not None:
        return conn.execute(sql, params).lastrowid
    with conn_ctx() as c:
        return c.execute(sql, params).lastrowid


def insert_ignore(table: str, data: dict, *, conn: Optional[sqlite3.Connection] = None) -> Optional[int]:
    """插入一行，唯一约束冲突时静默跳过。返回新 id 或 None。"""
    table = _check_table(table)
    cols = list(data.keys())
    sql = (
        f"INSERT OR IGNORE INTO {table} ({', '.join(cols)}) "
        f"VALUES ({', '.join('?' for _ in cols)})"
    )
    params = [data[c] for c in cols]

    if conn is not None:
        cur = conn.execute(sql, params)
        return cur.lastrowid if cur.rowcount else None
    with conn_ctx() as c:
        cur = c.execute(sql, params)
        return cur.lastrowid if cur.rowcount else None


def update(table: str, row_id: int, data: dict) -> bool:
    """按 id 更新，自动刷新 updated_at（仅 awards 有此列）。返回是否命中。"""
    table = _check_table(table)
    if not data:
        return False
    data = dict(data)
    if table == "awards":
        data["updated_at"] = _now()
    sets = ", ".join(f"{k}=?" for k in data)
    params = list(data.values()) + [row_id]
    with conn_ctx() as conn:
        cur = conn.execute(f"UPDATE {table} SET {sets} WHERE id=?", params)
        return cur.rowcount > 0


def get(table: str, row_id: int) -> Optional[dict]:
    table = _check_table(table)
    with conn_ctx() as conn:
        return _row_to_dict(
            conn.execute(f"SELECT * FROM {table} WHERE id=?", (row_id,)).fetchone()
        )


def query(sql: str, params: Iterable = ()) -> list:
    """
    执行自定义 SELECT，返回 list[dict]。
    仅供内部/高级用法；优先使用带语义的封装函数。
    """
    with conn_ctx() as conn:
        return [dict(r) for r in conn.execute(sql, tuple(params)).fetchall()]


def _now() -> str:
    with conn_ctx() as conn:
        return conn.execute("SELECT datetime('now','localtime')").fetchone()[0]


def json_dumps(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))


def json_loads(s: Optional[str], default: Any = None) -> Any:
    if not s:
        return default
    try:
        return json.loads(s)
    except (ValueError, TypeError):
        return default


# ============================================================
# 三、业务语义封装
# ============================================================

# ----------------- awards -----------------

def add_award(data: dict) -> int:
    """
    新增获奖作品。必填：title, year。
    自动计算 content_hash（title|year|team），并因内容变更标记需要重建向量。
    """
    data = _prepare_award(data)
    data["embedding_state"] = data.get("embedding_state", "stale")
    return insert("awards", data)


def upsert_award(data: dict) -> tuple:
    """
    按 content_hash 幂等写入。
    返回 (award_id, action)，action ∈ {"inserted","updated","skipped"}。
    """
    data = _prepare_award(data)
    h = data["content_hash"]
    with conn_ctx() as conn:
        row = conn.execute(
            "SELECT id, embedding_state FROM awards WHERE content_hash=?", (h,)
        ).fetchone()
        if row is None:
            data.setdefault("embedding_state", "stale")
            aid = insert("awards", data, conn=conn)
            return aid, "inserted"

        # 已存在：仅当关键内容变化时更新
        old = _row_to_dict(conn.execute("SELECT * FROM awards WHERE id=?", (row["id"],)).fetchone())
        changed = any(
            (data.get(k) or "") != (old.get(k) or "")
            for k in ("summary", "highlights", "tech_stack", "title")
        )
        if not changed:
            return row["id"], "skipped"

        data["embedding_state"] = "stale"
        data["updated_at"] = conn.execute("SELECT datetime('now','localtime')").fetchone()[0]
        sets = ", ".join(f"{k}=?" for k in data)
        conn.execute(
            f"UPDATE awards SET {sets} WHERE id=?", list(data.values()) + [row["id"]]
        )
        return row["id"], "updated"


def _prepare_award(data: dict) -> dict:
    """校验 + 归一化 + 计算指纹。"""
    d = dict(data)
    if not d.get("title"):
        raise ValueError("awards.title 必填")
    if d.get("year") is None:
        raise ValueError("awards.year 必填")
    d["year"] = int(d["year"])
    d.setdefault("source_type", "manual")
    d.setdefault("review_status", "pending")
    d.setdefault("confidence", 1.0)
    # tech_stack 允许传 list
    if isinstance(d.get("tech_stack"), (list, tuple)):
        d["tech_stack"] = json_dumps(list(d["tech_stack"]))
    if not d.get("content_hash"):
        d["content_hash"] = compute_award_hash(
            d["title"], d["year"], d.get("team")
        )
    # 去掉 None 值，避免覆盖默认值
    return {k: v for k, v in d.items() if v is not None}


def compute_award_hash(title: str, year: int, team: Optional[str]) -> str:
    import hashlib
    raw = f"{(title or '').strip()}|{year}|{(team or '').strip()}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def list_awards(
    *,
    year: Optional[int] = None,
    year_from: Optional[int] = None,
    year_to: Optional[int] = None,
    category: Optional[str] = None,
    competition_id: Optional[int] = None,
    review_status: Optional[str] = None,
    keyword: Optional[str] = None,
    limit: Optional[int] = None,
    offset: int = 0,
    order_by: str = "year DESC, id DESC",
) -> list:
    """按条件筛选获奖作品（结构化检索主力）。"""
    where, params = _awards_where(
        year=year, year_from=year_from, year_to=year_to, category=category,
        competition_id=competition_id, review_status=review_status, keyword=keyword,
    )
    sql = f"SELECT * FROM awards {where} ORDER BY {order_by}"
    if limit is not None:
        sql += " LIMIT ? OFFSET ?"
        params += [int(limit), int(offset)]
    return query(sql, params)


def count_awards(**kwargs) -> int:
    kwargs.pop("limit", None); kwargs.pop("offset", None); kwargs.pop("order_by", None)
    where, params = _awards_where(**kwargs)
    with conn_ctx() as conn:
        return conn.execute(f"SELECT COUNT(*) FROM awards {where}", params).fetchone()[0]


def _awards_where(**kw) -> tuple:
    conds, params = [], []
    if kw.get("year") is not None:
        conds.append("year=?"); params.append(int(kw["year"]))
    if kw.get("year_from") is not None:
        conds.append("year>=?"); params.append(int(kw["year_from"]))
    if kw.get("year_to") is not None:
        conds.append("year<=?"); params.append(int(kw["year_to"]))
    if kw.get("category"):
        conds.append("category=?"); params.append(kw["category"])
    if kw.get("competition_id") is not None:
        conds.append("competition_id=?"); params.append(int(kw["competition_id"]))
    if kw.get("review_status"):
        conds.append("review_status=?"); params.append(kw["review_status"])
    if kw.get("keyword"):
        conds.append("(title LIKE ? OR summary LIKE ? OR highlights LIKE ?)")
        like = f"%{kw['keyword']}%"
        params += [like, like, like]
    where = ("WHERE " + " AND ".join(conds)) if conds else ""
    return where, params


def find_award_ids(**kwargs) -> list:
    """只取 id 列表，用于「SQLite 粗筛 → Chroma 精排」两级检索。"""
    kwargs.pop("limit", None); kwargs.pop("offset", None); kwargs.pop("order_by", None)
    where, params = _awards_where(**kwargs)
    with conn_ctx() as conn:
        return [r["id"] for r in conn.execute(f"SELECT id FROM awards {where}", params)]


def award_stats_by_year(category: Optional[str] = None) -> list:
    """按年份聚合数量，供趋势分析。"""
    conds, params = "", []
    if category:
        conds = "WHERE category=?"
        params = [category]
    return query(
        f"SELECT year, COUNT(*) AS cnt FROM awards {conds} "
        f"GROUP BY year ORDER BY year", params
    )


def award_stats_by_category(year_from: Optional[int] = None, year_to: Optional[int] = None) -> list:
    """按类别聚合，供趋势分析。"""
    conds, params = [], []
    if year_from is not None:
        conds.append("year>=?"); params.append(int(year_from))
    if year_to is not None:
        conds.append("year<=?"); params.append(int(year_to))
    where = ("WHERE " + " AND ".join(conds)) if conds else ""
    return query(
        f"SELECT category, COUNT(*) AS cnt FROM awards {where} "
        f"GROUP BY category ORDER BY cnt DESC", params
    )


# ----------------- search_leads -----------------

def add_lead(query_text: str, title: str, url: str, snippet: str = "",
             provider: str = "mock", keyword_hit: str = "",
             status: str = "new") -> Optional[int]:
    """新增线索（url 重复则跳过），返回 id 或 None。"""
    return insert_ignore("search_leads", {
        "query": query_text, "title": title, "url": url,
        "snippet": snippet, "provider": provider,
        "keyword_hit": keyword_hit, "status": status,
    })


def list_leads(status: Optional[str] = None, limit: Optional[int] = None) -> list:
    where, params = ("WHERE status=?", [status]) if status else ("", [])
    sql = f"SELECT * FROM search_leads {where} ORDER BY id"
    if limit:
        sql += " LIMIT ?"; params.append(int(limit))
    return query(sql, params)


def mark_lead(lead_id: int, status: str, competition_id: Optional[int] = None) -> bool:
    data = {"status": status}
    if competition_id is not None:
        data["competition_id"] = competition_id
    return update("search_leads", lead_id, data)


# ----------------- crawl_jobs -----------------

def start_job(kind: str, target: str = "", items_in: int = 0) -> int:
    return insert("crawl_jobs", {
        "kind": kind, "target": target, "status": "running", "items_in": int(items_in),
    })


def finish_job(job_id: int, ok: bool = True, *, items_out: int = 0,
               cost_token: int = 0, error: Optional[str] = None) -> bool:
    with conn_ctx() as conn:
        cur = conn.execute(
            "UPDATE crawl_jobs SET status=?, items_out=?, cost_token=?, error=?, "
            "ended_at=datetime('now','localtime') WHERE id=?",
            ("ok" if ok else "failed", int(items_out), int(cost_token),
             (error or "")[:2000] or None, job_id),
        )
        return cur.rowcount > 0


# ----------------- insights -----------------

def save_insight(kind: str, scope: str, content_md: str, model: str = "",
                 evidence: Optional[list] = None, input_hash: Optional[str] = None) -> Optional[int]:
    """
    写入一条洞察。input_hash 相同则视为同数据，跳过重复（省 token）。
    返回 id 或 None（已存在）。
    """
    # input_hash 允许留空：trend/gap 是“每轮重算”的结论，不按输入判重；
    # experience 由调用方传入稳定 hash，靠部分唯一索引 ux_insights_hash 保证幂等。
    return insert_ignore("insights", {
        "kind": kind, "scope": scope, "content_md": content_md,
        "evidence": json_dumps(evidence) if evidence is not None else None,
        "model": model, "input_hash": input_hash or None,
    })


def get_insight(kind: str, scope: str) -> Optional[dict]:
    with conn_ctx() as conn:
        return _row_to_dict(conn.execute(
            "SELECT * FROM insights WHERE kind=? AND scope=? ORDER BY id DESC LIMIT 1",
            (kind, scope),
        ).fetchone())


# ----------------- ideas -----------------

def add_idea(title: str, **fields) -> tuple:
    """
    新增灵感。content_hash = sha1(title) 去重。
    返回 (id, action)，action ∈ {"inserted","skipped"}。
    """
    import hashlib
    h = fields.pop("content_hash", None) or hashlib.sha1(title.strip().encode()).hexdigest()
    data = {"title": title, "content_hash": h}
    for k, v in fields.items():
        if v is None:
            continue
        data[k] = json_dumps(v) if isinstance(v, (list, dict)) else v
    new_id = insert_ignore("ideas", data)
    return (new_id, "inserted") if new_id else (None, "skipped")


def list_ideas(status: Optional[str] = None, competition_id: Optional[int] = None) -> list:
    conds, params = [], []
    if status:
        conds.append("status=?"); params.append(status)
    if competition_id is not None:
        conds.append("competition_id=?"); params.append(int(competition_id))
    where = ("WHERE " + " AND ".join(conds)) if conds else ""
    return query(f"SELECT * FROM ideas {where} ORDER BY id DESC", params)
