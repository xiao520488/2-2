-- ============================================================
-- 比赛信息管理系统 - 数据库结构
-- 数据库：SQLite
-- 表：competitions
-- 说明：时间为"月份(1-12)整数 + 跨年标记"，不含具体日期/年份
-- ============================================================

CREATE TABLE IF NOT EXISTS competitions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,  -- 主键，自增
    name            TEXT    NOT NULL,                   -- 竞赛名称
    category        TEXT,                               -- 类别（原样存字符串，如 "创新创业/软件服务"）
    reg_start_month INTEGER CHECK (reg_start_month BETWEEN 1 AND 12),  -- 报名开始月 1-12
    reg_end_month   INTEGER CHECK (reg_end_month   BETWEEN 1 AND 12),  -- 报名结束月 1-12
    reg_cross_year  INTEGER NOT NULL DEFAULT 0          -- 是否跨年：0=不跨年，1=跨年（如"次年3月"）
                    CHECK (reg_cross_year IN (0, 1)),
    official_url    TEXT,                               -- 官网链接
    -- 级别：national=国家级，provincial=省级（含区域级）
    level           TEXT    NOT NULL DEFAULT 'national'
                    CHECK (level IN ('national', 'provincial')),
    -- 级别显示文案：国家级 / 省级 / 区域级（留空时由 level 自动推导）
    level_label     TEXT,
    -- 手动排序权重，越小越靠前；NULL 时按默认规则排序
    sort_order      INTEGER,
    -- 一句话简介（参赛安利型，<=60字，仅依据库内字段描述，不编造事实）
    intro           TEXT,
    created_at      TEXT    NOT NULL DEFAULT (datetime('now', 'localtime'))  -- 创建时间
);

-- 索引在 db.init_db() 的迁移补列之后创建（见 db.py 中 INDEXES_SQL），
-- 避免老库尚无新增列时建索引失败。
