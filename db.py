"""
比赛信息管理系统 - 数据访问层接口定义 (db.py)

本文件当前仅定义【接口骨架】：
- 函数签名、参数、返回结构已确定；
- 函数体均为 NotImplementedError 占位，尚未实现，不会连库、不会写数据。

字段约定（与 schema.sql 一致）：
    id, name, category, reg_start_month, reg_end_month,
    reg_cross_year, official_url, created_at
"""

from typing import Optional
import os
import sqlite3

# 数据库文件路径（与 db.py 同目录）
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "competitions.db")
# 建表脚本路径
SCHEMA_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "schema.sql")


# 计算机类类别关键词（命中则视为计算机类，排在最前）
_COMPUTER_KEYWORDS = ("计算机", "软件", "程序设计", "算法", "人工智能", "AI",
                      "大数据", "信息安全", "网络安全", "服务外包", "电子信息",
                      "物联网", "嵌入式", "ICT")

# 创新创业类关键词：即使与计算机类有交叉（如"创新创业/软件服务"），
# 也整体排在纯计算机类之后。
_INNOVATION_KEYWORDS = ("创新创业", "创客", "创业")

# 排序子句（四级）：
#  1) 赛道分组 group_rank：
#       0 = 计算机类（category 命中计算机关键词，且不含创新创业）
#       1 = 创新创业类（category 命中创新创业关键词）
#       2 = 其它
#  2) is_national DESC —— 国家级优先于省级
#  3) sort_order ASC   —— 手动权重，NULL 视为 9999
#  4) id ASC
_COMPUTER_EXPR = "(" + " OR ".join(
    f"category LIKE '%{k}%'" for k in _COMPUTER_KEYWORDS) + ")"
_INNOVATION_EXPR = "(" + " OR ".join(
    f"category LIKE '%{k}%'" for k in _INNOVATION_KEYWORDS) + ")"

_ORDER_BY_CLAUSE = (
    # 1) 赛道分组：纯计算机 0 < 创新创业 1 < 其它 2
    f"CASE WHEN {_COMPUTER_EXPR} AND NOT {_INNOVATION_EXPR} THEN 0 "
    f"WHEN {_INNOVATION_EXPR} THEN 1 ELSE 2 END, "
    # 2) 级别
    "CASE WHEN level = 'national' THEN 0 ELSE 1 END, "
    # 3) 手动权重
    "COALESCE(sort_order, 9999), "
    # 4) 兜底
    "id"
)

# 级别 -> 默认显示文案
_LEVEL_LABELS = {
    "national": "国家级",
    "provincial": "省级",
}


def level_label_of(row: dict) -> str:
    """
    取比赛的级别显示文案：
        level_label 非空则优先使用（如"区域级"），否则由 level 推导。
    """
    label = row.get("level_label")
    if label:
        return label
    return _LEVEL_LABELS.get(row.get("level") or "national", "国家级")


def _enrich(row: dict) -> dict:
    """补全 level_label，保证对外返回的行始终带中文级别文案。"""
    row = dict(row)
    row["level"] = row.get("level") or "national"
    row["level_label"] = level_label_of(row)
    return row


def get_conn() -> sqlite3.Connection:
    """
    获取数据库连接。
    - 返回的行用 sqlite3.Row，便于按列名取值转 dict
    - 开启外键约束（当前无外键，预留）
    """
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """
    初始化数据库：执行 schema.sql 建表（IF NOT EXISTS，可重复调用）。
    不会插入任何业务数据。
    """
    with open(SCHEMA_PATH, encoding="utf-8") as f:
        schema_sql = f.read()
    conn = get_conn()
    try:
        conn.executescript(schema_sql)
        _migrate_columns(conn)
        conn.executescript(INDEXES_SQL)
        conn.commit()
    finally:
        conn.close()


# 索引脚本（须在建表 + 迁移补列之后执行）
INDEXES_SQL = """
CREATE INDEX IF NOT EXISTS idx_competitions_category ON competitions (category);
CREATE INDEX IF NOT EXISTS idx_competitions_reg_month ON competitions (reg_start_month, reg_end_month);
CREATE INDEX IF NOT EXISTS idx_competitions_level ON competitions (level);
"""

# 旧库升级所需的新增列定义（列名 -> 列定义）
_MIGRATION_COLUMNS = {
    "level": "TEXT NOT NULL DEFAULT 'national'",
    "level_label": "TEXT",
    "sort_order": "INTEGER",
    "intro": "TEXT",
}


def _migrate_columns(conn: sqlite3.Connection) -> None:
    """
    轻量迁移：为已存在的 competitions 表补齐新增列。
    CREATE TABLE IF NOT EXISTS 不会给老表加列，故在此显式 ALTER TABLE。
    可重复调用（已存在列则跳过）。
    """
    existing = {
        row["name"]
        for row in conn.execute("PRAGMA table_info(competitions)").fetchall()
    }
    for col, ddl in _MIGRATION_COLUMNS.items():
        if col not in existing:
            conn.execute(f"ALTER TABLE competitions ADD COLUMN {col} {ddl}")


# ============================================================
# 一、基础增删改（维护比赛库）
# ============================================================

def add_competition(data: dict) -> int:
    """
    新增一条比赛。

    参数:
        data: dict，需含以下键（created_at 由数据库自动生成，可不传）：
            name (str, 必填)
            category (str)
            reg_start_month (int, 1-12)
            reg_end_month (int, 1-12)
            reg_cross_year (int, 0/1)
            official_url (str)
    返回:
        新插入记录的 id (int)
    """
    conn = get_conn()
    try:
        level = data.get("level") or "national"
        if level not in ("national", "provincial"):
            level = "national"
        cur = conn.execute(
            """INSERT INTO competitions
               (name, category, reg_start_month, reg_end_month, reg_cross_year,
                official_url, level, level_label, sort_order)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                data.get("name"),
                data.get("category"),
                data.get("reg_start_month"),
                data.get("reg_end_month"),
                (1 if data.get("reg_cross_year") else 0),
                data.get("official_url"),
                level,
                data.get("level_label"),
                data.get("sort_order"),
            ),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def update_competition(cid: int, data: dict) -> bool:
    """
    按 id 更新比赛。

    参数:
        cid: 比赛 id
        data: 需要更新的字段 dict（可部分字段）
    返回:
        是否更新成功 (bool)；id 不存在返回 False
    """
    allowed = ("name", "category", "reg_start_month", "reg_end_month",
               "reg_cross_year", "official_url",
               "level", "level_label", "sort_order", "intro")
    fields = {k: v for k, v in data.items() if k in allowed}
    # reg_cross_year 归一化：None/假值 -> 0，真值 -> 1，避免写入 NULL 违反 NOT NULL 约束
    if "reg_cross_year" in fields:
        fields["reg_cross_year"] = 1 if fields["reg_cross_year"] else 0
    if not fields:
        return False
    set_clause = ", ".join(f"{k} = ?" for k in fields)
    params = list(fields.values()) + [cid]
    conn = get_conn()
    try:
        cur = conn.execute(
            f"UPDATE competitions SET {set_clause} WHERE id = ?", params
        )
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def delete_competition(cid: int) -> bool:
    """
    按 id 删除比赛。

    返回:
        是否删除成功 (bool)；id 不存在返回 False
    """
    conn = get_conn()
    try:
        cur = conn.execute("DELETE FROM competitions WHERE id = ?", (cid,))
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def get_competition(cid: int) -> Optional[dict]:
    """
    按 id 取单条比赛详情。

    返回:
        dict（一行）或 None
    """
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT * FROM competitions WHERE id = ?", (cid,)
        ).fetchone()
        return _enrich(row) if row else None
    finally:
        conn.close()


# ============================================================
# 二、查询 / 筛选 / 搜索
# ============================================================

def list_competitions(
    category: Optional[str] = None,
    month: Optional[int] = None,
    keyword: Optional[str] = None,
) -> list[dict]:
    """
    列出比赛，支持组合筛选。

    参数:
        category: 类别，包含匹配 (LIKE %category%)，None 表示不限
        month:    目标月份 1-12，返回“报名区间覆盖该月”的比赛，None 表示不限
        keyword:  关键词，在 name 上模糊匹配 (LIKE %keyword%)，None 表示不限
    返回:
        list[dict]，每项一行；三者均 None 时返回全部
    """
    sql = "SELECT * FROM competitions WHERE 1=1"
    params = []
    if category:
        sql += " AND category LIKE ?"
        params.append(f"%{category}%")
    if keyword:
        sql += " AND name LIKE ?"
        params.append(f"%{keyword}%")
    # 排序规则：计算机类优先 -> 国家级优先 -> sort_order -> id
    sql += f" ORDER BY {_ORDER_BY_CLAUSE}"

    conn = get_conn()
    try:
        rows = conn.execute(sql, params).fetchall()
    finally:
        conn.close()

    result = [_enrich(r) for r in rows]
    # month 用精确的跨年区间判断（在 Python 层过滤）
    if month is not None:
        result = [
            r for r in result
            if r["reg_start_month"] is not None and r["reg_end_month"] is not None
            and _month_in_range(month, r["reg_start_month"], r["reg_end_month"],
                                r["reg_cross_year"])
        ]
    return result


def get_categories() -> list[str]:
    """
    获取所有类别（去重），供下拉框使用。

    返回:
        list[str] 类别列表
    """
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT DISTINCT category FROM competitions "
            "WHERE category IS NOT NULL AND category != '' ORDER BY category"
        ).fetchall()
        return [r["category"] for r in rows]
    finally:
        conn.close()


# ============================================================
# 三、日历 / 时间轴
# ============================================================

def get_registering_by_month(month: int) -> list[dict]:
    """
    获取指定月份“正在报名”的比赛（报名区间覆盖该月）。

    参数:
        month: 1-12
    返回:
        list[dict] 比赛列表
    """
    return list_competitions(month=month)


def get_month_timeline(month: int) -> dict:
    """
    获取某月的时间轴概览。

    参数:
        month: 1-12
    返回:
        dict:
            {
              "month": month,
              "registering": list[dict],   # 该月在报名的比赛
              "competing": list[dict],     # 该月在比赛的比赛（暂无数据来源，先空列表）
            }
    说明:
        当前数据只有报名时间，无比赛时间，competing 预留为空。
    """
    registering = list_competitions(month=month)
    return {
        "month": month,
        "registering": registering,
        "competing": [],
    }


# ============================================================
# 四、内部辅助（非对外接口）
# ============================================================

def _month_in_range(month: int, start: int, end: int, cross_year: int) -> bool:
    """
    判断某月是否落在报名区间内（含跨年处理）。

    规则:
        不跨年 (cross_year=0): start <= month <= end
        跨年   (cross_year=1): month >= start or month <= end
                               （如 5月→次年3月，区间为 [5..12] ∪ [1..3]）

    参数:
        month: 目标月 1-12
        start: 报名开始月 1-12
        end:   报名结束月 1-12
        cross_year: 0/1
    返回:
        bool
    """
    if cross_year:
        return month >= start or month <= end
    return start <= month <= end
