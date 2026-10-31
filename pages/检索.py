# -*- coding: utf-8 -*-
"""
🔍 语义检索页（pages/检索.py）—— S2

职责
    把 S1 的检索内核（retriever.retrieve）接成可视化页面：
      - 自然语言语义搜索 + 结构化过滤（类别 / 级别 / 奖项等级 / 年份区间 / 仅已审核）
      - 赛事名子串过滤（competition_raw）
      - 卡片式结果展示：标题 + 相关度分数 + 元数据 + 摘要/亮点/技术栈

设计要点
    1. 过滤选项优先从 SQLite 动态读取（distinct），读不到时退回预置枚举，
       避免空库时下拉框空白。
    2. 赛事名过滤（competition_raw）不在 retrieve() 的 filters 支持范围内，
       因此在页面层做后置过滤；为降低“先截断再筛选”的漏召回，
       命中赛事名过滤时放大 top_k（候选倍数），筛完再截断回用户要求条数。
    3. 索引为空时给出引导：一键从 SQLite 全量同步到 Chroma。
    4. 所有重操作（模型加载 / 索引同步）用 st.cache_resource / spinner 包裹。
"""

import streamlit as st

import kb
import retriever
import embedder

# ---------------------------------------------------------------- 常量
DEFAULT_CATEGORIES = [
    "人工智能", "机器人", "软件开发", "电子信息",
    "数学建模", "创新创业", "机械设计", "其他",
]
DEFAULT_LEVELS = [("national", "国家级"), ("provincial", "省级")]
DEFAULT_GRADES = ["一等奖", "二等奖", "三等奖", "特等奖", "金奖", "银奖", "铜奖", "优秀奖"]

LEVEL_LABEL = {"national": "国家级", "provincial": "省级", "regional": "区域级"}
LEVEL_COLOR = {"national": "#dbeafe", "provincial": "#dcfce7", "regional": "#fef3c7"}

# 赛事名过滤时，先多召回一些候选再筛
COMPETITION_FILTER_OVERFETCH = 5


# ---------------------------------------------------------------- 数据读取
@st.cache_data(ttl=300, show_spinner=False)
def load_filter_options():
    """从 SQLite 动态读取过滤选项；空库时退回预置枚举。"""
    def distinct(col):
        try:
            rows = kb.query(
                f"SELECT DISTINCT {col} FROM awards "
                f"WHERE {col} IS NOT NULL AND TRIM({col}) != '' ORDER BY {col}"
            )
            return [str(r[col]) for r in rows] if rows else []
        except Exception:
            return []

    categories = distinct("category") or DEFAULT_CATEGORIES[:]
    levels = distinct("level")
    grades = distinct("award_grade") or DEFAULT_GRADES[:]

    try:
        rows = kb.query("SELECT MIN(year) AS y0, MAX(year) AS y1 FROM awards")
        y0 = rows[0]["y0"] if rows and rows[0]["y0"] is not None else None
        y1 = rows[0]["y1"] if rows and rows[0]["y1"] is not None else None
    except Exception:
        y0 = y1 = None

    return {
        "categories": categories,
        "levels": levels,
        "grades": grades,
        "year_min": y0,
        "year_max": y1,
    }


@st.cache_resource(show_spinner=False)
def warm_embedder():
    """预热向量后端（真实模型首次加载较慢），返回 backend 名称。"""
    try:
        embedder.self_test()
        return embedder.get_backend()
    except Exception as e:  # noqa: BLE001
        return f"error: {e}"


def index_stats():
    """安全获取索引统计。"""
    try:
        return retriever.stats()
    except Exception as e:  # noqa: BLE001
        return {"indexed": 0, "error": str(e)}


def _approved_id_set(ids):
    """批量查询 approved 的 award_id 集合。查询失败时不误杀，全部放行。"""
    if not ids:
        return set()
    try:
        placeholders = ",".join("?" for _ in ids)
        rows = kb.query(
            f"SELECT id FROM awards WHERE id IN ({placeholders}) "
            f"AND review_status = 'approved'",
            tuple(ids),
        )
        return {r["id"] for r in rows}
    except Exception:
        return set(ids)


# ---------------------------------------------------------------- 渲染
def render_card(item, rank):
    """渲染单条结果为卡片。"""
    title = item.get("title") or "(无标题)"
    score = item.get("final_score")
    raw_score = item.get("score")
    bonus = item.get("bonus") or 0.0

    level = item.get("level")
    level_text = LEVEL_LABEL.get(level, level or "—")
    badge_bg = LEVEL_COLOR.get(level, "#f1f5f9")

    with st.container(border=True):
        head_l, head_r = st.columns([5, 1])
        with head_l:
            st.markdown(f"**{rank}. {title}**")
        with head_r:
            if score is not None:
                st.markdown(
                    f"<div style='text-align:right;font-size:1.05rem;"
                    f"font-weight:700;color:#0f766e'>{score:.4f}</div>",
                    unsafe_allow_html=True,
                )

        meta_bits = []
        if item.get("year") is not None:
            meta_bits.append(f"📅 {item['year']}")
        if item.get("category"):
            meta_bits.append(f"🏷️ {item['category']}")
        if level:
            meta_bits.append(
                f"<span style='background:{badge_bg};padding:1px 6px;"
                f"border-radius:6px'>🏅 {level_text}</span>"
            )
        if item.get("award_grade"):
            meta_bits.append(f"🥇 {item['award_grade']}")
        if meta_bits:
            st.markdown(
                "<div style='font-size:0.85rem;color:#475569;margin:2px 0 6px'>"
                + " &nbsp;·&nbsp; ".join(meta_bits)
                + "</div>",
                unsafe_allow_html=True,
            )

        if item.get("competition_raw"):
            st.caption(f"🏫 {item['competition_raw']}")

        if item.get("summary"):
            summary = item["summary"]
            if len(summary) > 220:
                summary = summary[:220] + "…"
            st.write(summary)

        tech = item.get("tech_stack") or []
        if tech:
            chips = " ".join(
                f"<span style='background:#eef2ff;color:#3730a3;padding:1px 8px;"
                f"border-radius:10px;font-size:0.78rem'>{t}</span>"
                for t in tech
            )
            st.markdown(chips, unsafe_allow_html=True)

        detail_bits = []
        if raw_score is not None:
            detail_bits.append(f"L1 语义分 `{raw_score:.4f}`")
        if bonus:
            detail_bits.append(f"结构化加成 `+{bonus:.4f}`")
        if detail_bits:
            st.caption("　".join(detail_bits))

        if item.get("highlights"):
            with st.expander("💡 亮点 / 创新点"):
                st.write(item["highlights"])

        if item.get("source_url"):
            st.caption(f"🔗 {item['source_url']}")


# ---------------------------------------------------------------- 主流程
def main():
    st.set_page_config(page_title="语义检索 · 竞赛知识库", page_icon="🔍", layout="wide")

    st.title("🔍 语义检索")
    st.caption("自然语言描述你想找的作品，系统会做语义匹配，并可用结构化条件收窄结果。")

    stats = index_stats()
    indexed = stats.get("indexed", 0)
    backend = warm_embedder()
    backend_ok = not str(backend).startswith("error")

    info_l, info_r = st.columns([3, 2])
    with info_l:
        if indexed > 0:
            st.success(f"向量索引就绪：{indexed} 条（后端：{backend}）")
        else:
            st.warning("向量索引为空，请先点击右侧按钮从数据库同步。")
    with info_r:
        if st.button("🔄 从 SQLite 同步 / 重建索引", use_container_width=True):
            with st.spinner("正在同步：SQLite → Chroma…"):
                try:
                    res = retriever.sync_awards_to_chroma()
                    st.success(f"同步完成：本次索引 {res.get('indexed', 0)} 条")
                    st.cache_data.clear()
                    st.rerun()
                except Exception as e:  # noqa: BLE001
                    st.error(f"同步失败：{e}")

    if not backend_ok:
        st.error(f"向量后端异常：{backend}")

    st.divider()

    # ---------------- 查询区
    query = st.text_input(
        "查询内容",
        placeholder="例如：智能车视觉识别与路径规划 / 用 YOLO 做缺陷检测 / 无人机编队控制",
    )

    with st.expander("⚙️ 过滤条件", expanded=indexed == 0):
        opts = load_filter_options()

        f1, f2, f3 = st.columns(3)
        with f1:
            category = st.selectbox("类别", ["(全部)"] + opts["categories"])
        with f2:
            level_pairs = [("", "(全部)")] + (
                [(lv, LEVEL_LABEL.get(lv, lv)) for lv in opts["levels"]]
                if opts["levels"]
                else DEFAULT_LEVELS
            )
            level_label = st.selectbox("级别", [p[1] for p in level_pairs])
            level_val = dict((p[1], p[0]) for p in level_pairs)[level_label]
        with f3:
            grade = st.selectbox("奖项等级", ["(全部)"] + opts["grades"])

        f4, f5, f6 = st.columns(3)
        ymin, ymax = opts["year_min"], opts["year_max"]
        with f4:
            year_from = st.number_input(
                "起始年份", min_value=1900, max_value=2100,
                value=int(ymin) if ymin else 2015, step=1,
            )
        with f5:
            year_to = st.number_input(
                "结束年份", min_value=1900, max_value=2100,
                value=int(ymax) if ymax else 2025, step=1,
            )
        with f6:
            top_k = st.slider("返回条数", 1, 30, 10, 1)

        f7, f8 = st.columns([2, 1])
        with f7:
            comp_kw = st.text_input(
                "赛事名搜索（模糊匹配）",
                placeholder="例如：智能汽车 / 互联网+ / 数学建模",
            )
        with f8:
            only_approved = st.checkbox("仅已审核", value=True)

        use_year = st.checkbox(
            "启用年份区间过滤", value=False,
            help="勾选后按“起始~结束年份”过滤；不勾选则忽略年份条件",
        )

    # ---------------- 组装 filters
    filters = {}
    if category and category != "(全部)":
        filters["category"] = category
    if level_val:
        filters["level"] = level_val
    if grade and grade != "(全部)":
        filters["award_grade"] = grade
    if use_year:
        if year_from > year_to:
            st.warning("起始年份大于结束年份，已自动交换。")
            year_from, year_to = year_to, year_from
        filters["year_from"] = int(year_from)
        filters["year_to"] = int(year_to)

    # ---------------- 检索
    search = st.button("🚀 开始检索", type="primary", use_container_width=True)

    if search:
        if not query.strip():
            st.info("请输入查询内容后再检索。")
            st.stop()
        if not backend_ok:
            st.error("向量后端不可用，无法检索。")
            st.stop()
        if indexed == 0:
            st.warning("索引为空，请先同步索引。")
            st.stop()

        fetch_k = top_k * COMPETITION_FILTER_OVERFETCH if comp_kw.strip() else top_k

        with st.spinner("检索中…"):
            try:
                results = retriever.retrieve(
                    query, top_k=fetch_k, filters=filters or None, with_debug=True
                )
            except Exception as e:  # noqa: BLE001
                st.error(f"检索失败：{e}")
                st.stop()

        kw = comp_kw.strip().lower()
        if kw:
            results = [
                r for r in results
                if kw in (r.get("competition_raw") or "").lower()
            ]

        if only_approved:
            approved_ids = _approved_id_set([r["award_id"] for r in results])
            results = [r for r in results if r["award_id"] in approved_ids]

        results = results[:top_k]
        st.session_state["last_results"] = results

    results = st.session_state.get("last_results", [])

    if results:
        st.divider()
        st.subheader(f"命中 {len(results)} 条结果")
        for i, item in enumerate(results, 1):
            render_card(item, i)
    elif search:
        st.info("没有匹配的结果，试试放宽过滤条件或换个说法。")


if __name__ == "__main__":
    main()
else:
    # Streamlit 多页模式：以模块形式导入时也执行渲染
    main()
