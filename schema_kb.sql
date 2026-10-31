-- ============================================================
-- 竞赛知识库 (Knowledge Base) - 表结构
-- 数据库：SQLite（与 competitions 表同库：competitions.db，启用 WAL）
-- 说明：本脚本只负责知识库相关表，不触碰原有 competitions 表。
--       由 db.init_kb() 执行，可重复调用（IF NOT EXISTS）。
--
-- 设计分工（见架构方案）：
--   SQLite  = 结构化真值源：筛选 / 聚合 / 统计
--   Chroma  = 语义向量索引：相似度检索（可由 SQLite 全量重建）
-- ============================================================

-- ------------------------------------------------------------
-- 1. awards —— 获奖作品（核心表）
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS awards (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    -- 归属
    competition_id  INTEGER,            -- 关联 competitions.id，可空（线索未匹配时）
    competition_raw TEXT,               -- 原始赛名，便于回溯
    category        TEXT,               -- 类别（沿用 6 分类）
    level           TEXT,               -- national / provincial
    -- 作品
    year            INTEGER NOT NULL,   -- 届次年份，趋势分析主轴
    session         TEXT,               -- 届次描述，如"第11届"
    title           TEXT NOT NULL,      -- 作品名称
    team            TEXT,               -- 团队/学校
    award_grade     TEXT,               -- 一等奖/金奖/优胜奖
    track           TEXT,               -- 赛道/组别
    -- 内容（向量化 + 生成用的主料）
    summary         TEXT,               -- 作品简介（<=500字）
    tech_stack      TEXT,               -- JSON 数组 ["YOLOv8","Flask"]
    highlights      TEXT,               -- 亮点/创新点
    -- 溯源
    source_url      TEXT,
    source_type     TEXT    NOT NULL DEFAULT 'manual',  -- crawl/manual/import
    raw_html_path   TEXT,               -- 原始 HTML 快照路径
    -- 治理
    confidence      REAL    NOT NULL DEFAULT 1.0,       -- LLM 抽取置信度 0~1
    review_status   TEXT    NOT NULL DEFAULT 'pending', -- pending/approved/rejected
    embedding_state TEXT    NOT NULL DEFAULT 'none',    -- none/ok/stale
    content_hash    TEXT,               -- 去重指纹
    created_at      TEXT    NOT NULL DEFAULT (datetime('now','localtime')),
    updated_at      TEXT    NOT NULL DEFAULT (datetime('now','localtime')),
    CHECK (review_status   IN ('pending','approved','rejected')),
    CHECK (embedding_state IN ('none','ok','stale'))
);

-- ------------------------------------------------------------
-- 2. search_leads —— 搜索线索（自动更新入口）
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS search_leads (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    query          TEXT NOT NULL,       -- 命中的检索词
    title          TEXT,
    url            TEXT NOT NULL,
    snippet        TEXT,
    provider       TEXT,                -- serpapi/anysearch/mock
    keyword_hit    TEXT,                -- 命中的竞赛关键词
    status         TEXT NOT NULL DEFAULT 'new',  -- new/accepted/ignored/crawled
    competition_id INTEGER,             -- accepted 后关联
    created_at     TEXT NOT NULL DEFAULT (datetime('now','localtime')),
    CHECK (status IN ('new','accepted','ignored','crawled'))
);

-- ------------------------------------------------------------
-- 3. crawl_jobs —— 任务日志（可观测）
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS crawl_jobs (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    kind       TEXT NOT NULL,      -- discover/crawl/extract/analyze/reindex
    target     TEXT,
    status     TEXT NOT NULL DEFAULT 'running',  -- running/ok/failed
    items_in   INTEGER NOT NULL DEFAULT 0,
    items_out  INTEGER NOT NULL DEFAULT 0,
    cost_token INTEGER NOT NULL DEFAULT 0,
    error      TEXT,
    started_at TEXT NOT NULL DEFAULT (datetime('now','localtime')),
    ended_at   TEXT,
    CHECK (status IN ('running','ok','failed'))
);

-- ------------------------------------------------------------
-- 4. insights —— 生成的分析结论（带缓存，防重复烧钱）
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS insights (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    kind       TEXT NOT NULL,       -- experience/trend/gap
    scope      TEXT NOT NULL,       -- 作用域，如 "category:程序设计:2020-2025"
    content_md TEXT NOT NULL,       -- Markdown 正文
    evidence   TEXT,                -- JSON，引用的 award_id 列表（可溯源）
    model      TEXT,
    input_hash TEXT,                -- 幂等键：可空（trend/gap 不按输入判重）；唯一性由部分索引保证-- 幂等键：同输入不重复生成
    created_at TEXT NOT NULL DEFAULT (datetime('now','localtime')),
    CHECK (kind IN ('experience','trend','gap'))
);

-- ------------------------------------------------------------
-- 5. ideas —— 灵感清单
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS ideas (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    competition_id INTEGER,
    title          TEXT NOT NULL,
    pitch          TEXT,            -- 一句话卖点
    detail_md      TEXT,            -- 展开方案
    novelty        TEXT,            -- 差异化说明
    risk           TEXT,
    ref_awards     TEXT,            -- JSON: 借鉴的 award_id
    status         TEXT NOT NULL DEFAULT 'draft',  -- draft/starred/archived
    content_hash   TEXT,
    created_at     TEXT NOT NULL DEFAULT (datetime('now','localtime')),
    CHECK (status IN ('draft','starred','archived'))
);

-- ------------------------------------------------------------
-- 索引（在迁移补列之后创建）
-- ------------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_awards_year_cat  ON awards (year, category);
CREATE INDEX IF NOT EXISTS idx_awards_comp      ON awards (competition_id);
CREATE INDEX IF NOT EXISTS idx_awards_review    ON awards (review_status);
CREATE INDEX IF NOT EXISTS idx_awards_embed     ON awards (embedding_state);
CREATE UNIQUE INDEX IF NOT EXISTS ux_awards_hash ON awards (content_hash) WHERE content_hash IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS ux_leads_url  ON search_leads (url);
CREATE INDEX IF NOT EXISTS idx_leads_status     ON search_leads (status);

CREATE INDEX IF NOT EXISTS idx_jobs_kind        ON crawl_jobs (kind, status);
CREATE INDEX IF NOT EXISTS idx_insights_scope   ON insights (kind, scope);
CREATE UNIQUE INDEX IF NOT EXISTS ux_insights_hash ON insights (input_hash) WHERE input_hash IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_ideas_comp       ON ideas (competition_id);
CREATE UNIQUE INDEX IF NOT EXISTS ux_ideas_hash ON ideas (content_hash) WHERE content_hash IS NOT NULL;
