# -*- coding: utf-8 -*-
"""竞赛信息检索 —— Streamlit 前端。

功能：
  - 侧边栏切换页面（列表 / 时间轴）
  - 列表页：类别筛选 + 月份筛选 + 关键词搜索 + 卡片网格 + 分页
  - 时间轴页：按月份展示各月在报名的比赛
  - 卡片按级别（国家级 / 省级 / 区域级）配色标记
  - 卡片布局：每行 3 个 × 每列 2 行 = 每页 6 张
"""
import re

import streamlit as st

import db
import retriever
import llm

# ---------------------------------------------------------------- 常量
MONTHS = list(range(1, 13))
MONTH_LABELS = [f"{m}月" for m in MONTHS]
CARDS_PER_ROW = 3        # 每行卡片数
CARD_ROWS_PER_PAGE = 2   # 每页卡片行数
CARDS_PER_PAGE = CARDS_PER_ROW * CARD_ROWS_PER_PAGE   # 3 × 2 = 6 张/页


# ---------------------------------------------------------------- 工具函数
def cross_label(cross_year):
    """跨年标签。"""
    return "跨年(次年)" if cross_year else "同年"


def month_range_text(start, end, cross_year):
    """把起止月份 + 跨年标记渲染成可读文本。"""
    if not start or not end:
        return ""
    txt = f"{start}月 ~ {end}月"
    if cross_year:
        txt += "（跨年）"
    return txt


def level_theme(level, level_label=""):
    """按级别返回 (主题类名, 主题名)。

    国家级 -> national；区域级 / 赛区 / 区域赛 -> regional；其余省级类 -> provincial。
    """
    label = level_label or ""
    if level == "national":
        return "national", "国家级"
    if any(k in label for k in ("区域", "赛区", "区域赛")):
        return "regional", "区域级"
    if level == "provincial":
        return "provincial", "省级"
    return "other", label or "其他"


@st.cache_data(show_spinner=False)
def cached_categories():
    """类别列表带缓存。"""
    return db.get_categories()


# ---------------------------------------------------------------- 样式
def inject_styles():
    st.markdown(
        """
        <style>
        /* ============================================================
           顶部栏：只隐藏 header / toolbar / 部署按钮
           ============================================================ */
        /* 注意：不能 display:none 整个 header，
           否则侧边栏收起后，长在 header 里的「展开侧边栏」按钮会一起消失。 */
        header[data-testid="stHeader"] {
            background: transparent !important;
            box-shadow: none !important;
            border-bottom: none !important;
        }
        /* 只隐藏工具栏右侧的部署/菜单控件，保留左侧「展开侧边栏」按钮。
           绝对不能隐藏整个 stToolbar —— 展开按钮 stExpandSidebarButton
           就渲染在 stToolbar 内；父级 display:none 会让按钮既看不见也点不到。 */
        div[data-testid="stToolbarActions"],
        div[data-testid="stDecoration"],
        div[data-testid="stStatusWidget"],
        div[data-testid="stAppDeployButton"] {
            display: none !important;
        }
        /* 工具栏本身保留，并保证展开按钮可见可点 */
        div[data-testid="stToolbar"] {
            display: flex !important;
            visibility: visible !important;
        }
        [data-testid="stExpandSidebarButton"] {
            display: inline-flex !important;
            visibility: visible !important;
            opacity: 1 !important;
            pointer-events: auto !important;
            cursor: pointer !important;
        }
        section.main > div.block-container,
        [data-testid="stMainBlockContainer"] {
            padding-top: 2.6rem !important;
            padding-bottom: 1.5rem !important;
            max-width: 100% !important;
            padding-left: 2rem !important;
            padding-right: 2rem !important;
        }

        /* ============================================================
           侧边栏：只调整外观，绝不干预宽度/显示。
           （曾经写过 display:block + min-width:260px !important，
             结果把侧边栏宽度钉死，导致收起按钮完全失效。）
           ============================================================ */
        section[data-testid="stSidebar"] {
            background: #ffffff !important;
            border-right: 1px solid #e2eefa;
        }
        section[data-testid="stSidebar"] h1 {
            font-size: 1.25rem !important;
            margin-bottom: .4rem !important;
        }
        section[data-testid="stSidebar"] div[role="radiogroup"] label {
            padding: 10px 14px !important;
            border-radius: 12px !important;
            margin-bottom: 6px !important;
            background: linear-gradient(180deg, #f7fbff 0%, #eef6ff 100%);
            border: 1px solid #dbeaf9;
            transition: all .16s ease;
            cursor: pointer;
        }
        section[data-testid="stSidebar"] div[role="radiogroup"] label:hover {
            background: #e6f1fe !important;
            border-color: #b6d6f6 !important;
        }
        section[data-testid="stSidebar"] div[role="radiogroup"] label p {
            color: #12416f !important;
            font-size: 1rem !important;
            font-weight: 600 !important;
        }

        /* ============================================================
           全局配色
           ============================================================ */
        .stApp {
            background: linear-gradient(160deg, #f4f9ff 0%, #eaf3fd 100%);
        }
        h1, h2, h3 {
            color: #12416f !important;
            letter-spacing: .5px;
        }

        /* ---------- 输入框 / 下拉框 ---------- */
        .stTextInput input,
        .stSelectbox div[data-baseweb="select"] > div {
            background: linear-gradient(180deg, #f7fbff 0%, #eef6ff 100%) !important;
            border: 1px solid #bfdcf8 !important;
            border-radius: 12px !important;
            transition: all .18s ease;
        }
        .stTextInput input:focus,
        .stSelectbox div[data-baseweb="select"] > div:focus-within {
            border-color: #4fa3ee !important;
            background: #ffffff !important;
            box-shadow: 0 0 0 3px rgba(79, 163, 238, .20) !important;
        }
        .stTextInput input::placeholder {
            color: #9db8d2 !important;
        }
        .stTextInput label,
        .stSelectbox label {
            color: #1f4a74 !important;
            font-weight: 700;
            letter-spacing: .3px;
        }
        [data-testid="stSelectSlider"] [role="slider"] {
            background: #3d95e8 !important;
        }

        /* ============================================================
           卡片网格：3 列铺满、等高
           ============================================================ */
        [data-testid="stHorizontalBlock"] {
            gap: 1.2rem 1.2rem !important;
            width: 100% !important;
        }
        [data-testid="stColumn"] {
            display: flex !important;
            flex: 1 1 0 !important;
            width: auto !important;
            min-width: 0 !important;
        }
        [data-testid="stColumn"] > div,
        [data-testid="stColumn"] [data-testid="stVerticalBlock"],
        [data-testid="stColumn"] [data-testid="stElementContainer"],
        [data-testid="stColumn"] [data-testid="stMarkdownContainer"],
        [data-testid="stColumn"] [data-testid="stMarkdown"] {
            width: 100% !important;
            height: 100% !important;
        }

        /* ---------- 卡片：撑满整格 ---------- */
        .comp-card {
            box-sizing: border-box;
            width: 100%;
            height: 100%;
            min-height: 270px;
            display: flex;
            flex-direction: column;
            background: #ffffff;
            border: 1px solid #dcebf9;
            border-left: 7px solid #b9cfe4;
            border-radius: 18px;
            padding: 22px 24px;
            margin: 0;
            box-shadow: 0 4px 16px rgba(47, 127, 209, .09);
            transition: transform .16s ease, box-shadow .16s ease;
        }
        .comp-card:hover {
            transform: translateY(-5px);
            box-shadow: 0 16px 38px rgba(47, 127, 209, .22);
        }
        .comp-card .c-name {
            font-size: 21px;
            font-weight: 800;
            color: #123d66;
            line-height: 1.35;
            margin-bottom: 16px;
            height: calc(1.35em * 2);
            display: -webkit-box;
            -webkit-line-clamp: 2;
            -webkit-box-orient: vertical;
            overflow: hidden;
            text-overflow: ellipsis;
        }
        .comp-card .c-intro {
            font-size: 14px;
            line-height: 1.6;
            color: #4a6580;
            margin-bottom: 14px;
            height: calc(1.6em * 2);
            display: -webkit-box;
            -webkit-line-clamp: 2;
            -webkit-box-orient: vertical;
            overflow: hidden;
            text-overflow: ellipsis;
        }
        .comp-card .c-intro.is-empty {
            color: #b6c6d6;
            font-style: italic;
        }
        .comp-card .c-badge-row {
            margin-bottom: 16px;
            height: 34px;
            overflow: hidden;
            white-space: nowrap;
        }
        .comp-card .c-badge {
            display: inline-block;
            font-size: 15px;
            font-weight: 700;
            line-height: 1;
            padding: 9px 16px;
            border-radius: 999px;
            border: 1px solid transparent;
            letter-spacing: .5px;
        }
        .comp-card .c-cat {
            display: inline-block;
            font-size: 13px;
            font-weight: 700;
            line-height: 1;
            padding: 7px 13px;
            margin-left: 8px;
            border-radius: 999px;
            border: 1px dashed transparent;
            letter-spacing: .5px;
            vertical-align: middle;
            background: #eef5fd;
            color: #4a76a8;
            border-color: #c7ddf5;
            white-space: nowrap;
        }
        /* 类别配色 */
        .comp-card .c-cat.cat-innov  { background: #fff4e8; color: #b9691a; border-color: #f6d3ac; }
        .comp-card .c-cat.cat-cs     { background: #eaf3ff; color: #2f6fb5; border-color: #c3dbf7; }
        .comp-card .c-cat.cat-prog   { background: #efeaff; color: #5b46b0; border-color: #d3c9f7; }
        .comp-card .c-cat.cat-sec    { background: #e8f7f1; color: #1f7a5a; border-color: #bde6d5; }
        .comp-card .c-cat.cat-iot    { background: #e9f8fb; color: #17707f; border-color: #bfe6ee; }
        .comp-card .c-cat.cat-test   { background: #fdeef4; color: #a83368; border-color: #f5cbdd; }
        .comp-card .c-cat.cat-other  { background: #f2f5f8; color: #64798d; border-color: #d8e2ec; }

        .comp-card .c-time-row {
            font-size: 17px;
            color: #2f7fd1;
            font-weight: 700;
            margin-bottom: 4px;
        }
        .comp-card .c-time-label {
            font-size: 13px;
            color: #8aa6c0;
            font-weight: 600;
            margin-right: 8px;
            letter-spacing: 1px;
        }
        .comp-card .c-foot {
            margin-top: auto;
            padding-top: 16px;
        }
        .comp-card .c-foot a {
            font-size: 15px;
            font-weight: 700;
            text-decoration: none;
            color: #2f7fd1;
        }
        .comp-card .c-foot a:hover {
            text-decoration: underline;
        }
        .comp-card .c-foot .c-empty {
            font-size: 14px;
            color: #b3c6d8;
        }

        /* ---------- 级别配色：国家级 / 省级 / 区域级 ---------- */
        .comp-card.lv-national {
            border-left-color: #ef4444;
            background: linear-gradient(180deg, #fff7f7 0%, #ffffff 55%);
        }
        .comp-card.lv-national .c-badge {
            color: #b91c1c;
            background: #ffe9e9;
            border-color: #fca5a5;
        }
        .comp-card.lv-national .c-name { color: #7f1d1d; }

        .comp-card.lv-provincial {
            border-left-color: #3d95e8;
            background: linear-gradient(180deg, #f5faff 0%, #ffffff 55%);
        }
        .comp-card.lv-provincial .c-badge {
            color: #1d4ed8;
            background: #e6f0ff;
            border-color: #93c5fd;
        }
        .comp-card.lv-provincial .c-name { color: #123d66; }

        .comp-card.lv-regional {
            border-left-color: #16a34a;
            background: linear-gradient(180deg, #f4fdf7 0%, #ffffff 55%);
        }
        .comp-card.lv-regional .c-badge {
            color: #15803d;
            background: #e6f8ec;
            border-color: #86efac;
        }
        .comp-card.lv-regional .c-name { color: #14532d; }

        .comp-card.lv-other {
            border-left-color: #94a3b8;
        }
        .comp-card.lv-other .c-badge {
            color: #475569;
            background: #eef2f7;
            border-color: #cbd5e1;
        }

        /* ---------------- 智能问答：引用来源卡片 ---------------- */
        .ref-card {
            background: #fff;
            border: 1px solid #e3ecf5;
            border-left: 3px solid #2f7fd1;
            border-radius: 8px;
            padding: 10px 14px;
            margin-bottom: 10px;
        }
        .ref-card .ref-idx {
            color: #2f7fd1;
            font-weight: 700;
            margin-right: 6px;
        }
        .ref-card .ref-title {
            font-weight: 600;
            color: #1f2d3d;
            margin-right: 8px;
        }
        .ref-card .ref-meta {
            font-size: 13px;
            color: #7b8fa3;
            margin-top: 4px;
        }
        .ref-card .ref-sum {
            font-size: 14px;
            color: #46586b;
            margin-top: 6px;
            line-height: 1.6;
        }
        /* ---------------- 灵感工作台 ---------------- */
        .idea-head {
            display: flex;
            align-items: center;
            gap: 10px;
            font-size: 17px;
            color: #1f2d3d;
            margin-bottom: 4px;
        }
        .idea-status {
            font-size: 12px;
            font-weight: 600;
            padding: 2px 8px;
            border-radius: 10px;
            border: 1px solid #d8e2ec;
            background: #f2f5f8;
            color: #64798d;
        }
        .idea-status.st-starred {
            background: #fff6e5;
            border-color: #f5d9a8;
            color: #a86a12;
        }
        .idea-status.st-archived {
            background: #eef2f7;
            color: #8697a8;
        }
        .idea-status.st-draft {
            background: #eaf3ff;
            border-color: #c3dbf7;
            color: #2f6fb5;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------- 卡片渲染
def esc(s):
    """HTML 转义，避免比赛名中的特殊字符破坏结构。"""
    if s is None:
        return ""
    return (
        str(s)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def short_level_label(level, level_label):
    """徽标上的短级别文字：去掉“·xxx”后缀。"""
    if level == "national":
        return "国家级"
    label = (level_label or "").strip()
    if not label:
        return "省级"
    base = re.split(r"[·・\s]", label)[0]
    return base if base else label


# 卡片展示用的类别标签（按赛事属性归一，仅用于展示，不改数据库 category）
CATEGORY_LABEL = {
    # 创新创业
    1: "创新创业", 2: "创新创业", 3: "创新创业", 4: "创新创业",
    5: "创新创业", 6: "创新创业", 7: "创新创业", 8: "创新创业",
    9: "创新创业", 29: "创新创业", 30: "创新创业",
    # 计算机综合
    10: "计算机综合", 11: "计算机综合", 12: "计算机综合",
    13: "计算机综合", 14: "计算机综合",
    23: "计算机综合", 24: "计算机综合",
    # 程序设计
    15: "程序设计", 16: "程序设计", 28: "程序设计",
    # 安全与 AI
    17: "安全与 AI", 18: "安全与 AI", 19: "安全与 AI", 26: "安全与 AI",
    # 物联网与嵌入式
    20: "物联网与嵌入式", 21: "物联网与嵌入式",
    22: "物联网与嵌入式", 27: "物联网与嵌入式",
    # 软件测试
    25: "软件测试",
}

# 类别 -> 配色主题（与级别徽标区分，类别用蓝绿暖色系）
CATEGORY_THEME = {
    "创新创业": "cat-innov",
    "计算机综合": "cat-cs",
    "程序设计": "cat-prog",
    "安全与 AI": "cat-sec",
    "物联网与嵌入式": "cat-iot",
    "软件测试": "cat-test",
}


def category_label(r):
    """取卡片展示用类别标签：优先用 id 映射，缺失时回退到 category 字段。"""
    lbl = CATEGORY_LABEL.get(r.get("id"))
    if lbl:
        return lbl
    return (r.get("category") or "").strip()


def render_card(r):
    """渲染单张比赛卡片（级别徽标 / 名称 / 报名时间 / 官网链接）。"""
    name = esc(r.get("name", ""))
    time_txt = month_range_text(
        r.get("reg_start_month"), r.get("reg_end_month"), r.get("reg_cross_year")
    )
    theme, _theme_name = level_theme(r.get("level"), r.get("level_label"))
    badge = esc(short_level_label(r.get("level"), r.get("level_label")))
    url = (r.get("official_url") or "").strip()

    if url:
        foot = (
            f'<div class="c-foot">'
            f'<a href="{esc(url)}" target="_blank" rel="noopener">查看官网 →</a>'
            f"</div>"
        )
    else:
        foot = '<div class="c-foot"><span class="c-empty">暂无官网链接</span></div>'

    time_row = (
        f'<div class="c-time-row">'
        f'<span class="c-time-label">报名时间</span>{esc(time_txt) or "待定"}'
        f"</div>"
    )

    intro = (r.get("intro") or "").strip()
    if intro:
        intro_row = f'<div class="c-intro">{esc(intro)}</div>'
    else:
        intro_row = '<div class="c-intro is-empty">暂无简介</div>'

    cat_txt = category_label(r)
    if cat_txt:
        cat_theme = CATEGORY_THEME.get(cat_txt, "cat-other")
        cat_html = (
            f'<span class="c-cat {cat_theme}">{esc(cat_txt)}</span>'
        )
    else:
        cat_html = ""

    html = (
        f'<div class="comp-card lv-{theme}">'
        f'<div class="c-name">{name}</div>'
        f"{intro_row}"
        f'<div class="c-badge-row">'
        f'<span class="c-badge">{badge}</span>'
        f"{cat_html}"
        f"</div>"
        f"{time_row}"
        f"{foot}"
        "</div>"
    )
    st.markdown(html, unsafe_allow_html=True)


def render_cards(rows, per_row=CARDS_PER_ROW):
    """按每行 per_row 个渲染卡片网格，卡片等高。"""
    if not rows:
        return
    for i in range(0, len(rows), per_row):
        chunk = rows[i:i + per_row]
        cols = st.columns(per_row, gap="medium")
        for j in range(per_row):
            with cols[j]:
                if j < len(chunk):
                    render_card(chunk[j])


def render_cards_paginated(rows, per_page=CARDS_PER_PAGE):
    """分页渲染卡片：每页 per_page 个（3 列 × 2 行），底部提供翻页控件。"""
    total = len(rows)
    if total == 0:
        st.info("没有符合条件的比赛")
        return

    pages = (total + per_page - 1) // per_page
    page = st.session_state.get("card_page", 1)
    if page > pages:
        page = pages
    if page < 1:
        page = 1

    start = (page - 1) * per_page
    render_cards(rows[start:start + per_page])

    if pages > 1:
        c1, c2, c3 = st.columns([1, 2, 1])
        with c1:
            if st.button("⬅ 上一页", disabled=(page <= 1), width="stretch"):
                st.session_state["card_page"] = page - 1
                st.rerun()
        with c2:
            st.markdown(
                f"<div style='text-align:center;padding-top:6px;'>"
                f"第 <b>{page}</b> / {pages} 页</div>",
                unsafe_allow_html=True,
            )
        with c3:
            if st.button("下一页 ➡", disabled=(page >= pages), width="stretch"):
                st.session_state["card_page"] = page + 1
                st.rerun()



# ---------------------------------------------------------------- 智能问答
QA_SYSTEM = (
    "你是高校竞赛选题与参赛规划顾问。请严格依据【参考资料】回答用户问题，"
    "不要编造资料中不存在的比赛、作品、数据或年份。"
    "如果资料不足，请明确说明「现有资料未覆盖」，再给出基于常识的保守建议。"
    "回答用中文，结构清晰（可用小标题 / 列表），关键处用 [编号] 标注引用来源。"
)


def render_local_fallback(question, rows, reason=""):
    """
    LLM 不可用（未配置 / 调用失败）时的兜底：直接展示检索摘要。

    不依赖任何网络，保证页面永远有可用输出。
    """
    if reason:
        st.warning(f"AI 回答不可用，已降级为检索摘要。原因：{reason}")
    else:
        st.info("当前未配置大模型，以下为本地检索结果的摘要展示。")

    if not rows:
        st.error("未检索到相关作品，换个问法或补充关键词试试。")
        return

    st.markdown(f"**围绕「{question}」检索到 {len(rows)} 条相关往届作品：**")
    for i, r in enumerate(rows, 1):
        stack = r.get("tech_stack") or []
        if isinstance(stack, (list, tuple)):
            stack = "、".join(str(s) for s in stack)
        with st.expander(
            f"[{i}] 《{r.get('title') or '未命名'}》 "
            f"{r.get('year') or ''} · {r.get('award_grade') or ''}",
            expanded=(i == 1),
        ):
            meta = "　".join(filter(None, [
                f"类别：{r.get('category')}" if r.get("category") else "",
                f"级别：{r.get('level')}" if r.get("level") else "",
                f"赛事：{r.get('competition_raw')}" if r.get("competition_raw") else "",
            ]))
            if meta:
                st.caption(meta)
            if r.get("summary"):
                st.markdown(f"**简介**：{r['summary']}")
            if stack:
                st.markdown(f"**技术栈**：{stack}")
            if r.get("highlights"):
                st.markdown(f"**亮点**：{r['highlights']}")
    st.caption("提示：配置 DEEPSEEK_API_KEY 后可获得 AI 归纳式回答。")


def ask_llm_stream(prompt, *, system, rows, question):
    """
    统一的问答出口：优先流式调用 LLM，失败则原地降级为检索摘要。

    返回 True 表示走了 AI，False 表示走了兜底。
    """
    if not llm.llm_available():
        render_local_fallback(question, rows, reason="")
        return False

    placeholder = st.empty()
    chunks = []
    try:
        for piece in llm.chat_stream(prompt, system=system, temperature=0.3):
            chunks.append(piece)
            placeholder.markdown("".join(chunks) + "▌")
        placeholder.markdown("".join(chunks))
        return True
    except Exception as exc:  # noqa: BLE001 - 任何异常都兜底，页面不能崩
        placeholder.empty()
        render_local_fallback(question, rows, reason=f"{type(exc).__name__}: {exc}")
        return False


IDEA_STATUS_FLOW = {
    "draft": ("starred", "⭐ 标星"),
    "starred": ("archived", "📦 采纳归档"),
    "archived": ("draft", "↩️ 退回草稿"),
}
IDEA_STATUS_LABEL = {"draft": "草稿", "starred": "⭐ 已收藏", "archived": "📦 已采纳"}


def update_idea_status(idea_id, status):
    """写回 ideas.status，返回是否成功。"""
    if status not in IDEA_STATUS_LABEL:
        return False
    conn = db.get_conn()
    try:
        cur = conn.execute("UPDATE ideas SET status = ? WHERE id = ?", (status, idea_id))
        conn.commit()
        return cur.rowcount > 0
    except Exception as exc:  # noqa: BLE001
        st.error(f"更新失败：{exc}")
        return False


def build_qa_prompt(question, rows):
    """把检索结果拼成带编号的参考资料上下文。"""
    blocks = []
    for i, r in enumerate(rows, 1):
        stack = r.get("tech_stack") or []
        if isinstance(stack, (list, tuple)):
            stack = "、".join(str(s) for s in stack)
        lines = [
            f"[{i}] 《{r.get('title') or ''}》",
            f"    年份：{r.get('year') or '未知'}　类别：{r.get('category') or '未知'}"
            f"　级别：{r.get('level') or ''}　奖项：{r.get('award_grade') or ''}",
            f"    所属赛事：{r.get('competition_raw') or '未知'}",
            f"    简介：{r.get('summary') or '无'}",
        ]
        if stack:
            lines.append(f"    技术栈：{stack}")
        if r.get("highlights"):
            lines.append(f"    亮点：{r.get('highlights')}")
        blocks.append("\n".join(lines))
    ctx = "\n\n".join(blocks) if blocks else "（本次未检索到相关作品）"
    return (
        f"【参考资料】（往届获奖作品库，共 {len(rows)} 条）\n{ctx}\n\n"
        f"【用户问题】\n{question}\n\n"
        "请基于上述资料作答，并在引用某条作品时标注 [编号]。"
    )


def render_refs(rows, key):
    """渲染问答的引用来源卡片（折叠面板）。"""
    if not rows:
        return
    with st.expander(f"📎 引用来源（{len(rows)} 条）", expanded=False):
        for i, r in enumerate(rows, 1):
            theme, _ = level_theme(r.get("level"), r.get("level_label"))
            stack = r.get("tech_stack") or []
            if isinstance(stack, (list, tuple)):
                stack = " · ".join(str(s) for s in stack)
            st.markdown(
                f'<div class="ref-card">'
                f'<span class="ref-idx">[{i}]</span>'
                f'<span class="ref-title">{esc(r.get("title"))}</span>'
                f'<span class="c-badge">{esc(short_level_label(r.get("level"), r.get("level_label")))}</span>'
                f'<div class="ref-meta">'
                f'{esc(str(r.get("year") or "未知"))} 年 · '
                f'{esc(r.get("category") or "未分类")} · '
                f'{esc(r.get("award_grade") or "")} · '
                f'{esc(r.get("competition_raw") or "")}'
                f'</div>'
                + (f'<div class="ref-meta">技术栈：{esc(stack)}</div>' if stack else "")
                + f'<div class="ref-sum">{esc(r.get("summary") or "")}</div>'
                f'</div>',
                unsafe_allow_html=True,
            )


def page_qa():
    st.header("智能问答")
    st.caption("基于往届获奖作品库的检索增强问答；回答仅供选题参考。")

    with st.form("qa_form", clear_on_submit=False):
        c1, c2 = st.columns([3, 1])
        with c1:
            question = st.text_input(
                "问题",
                placeholder="例：人工智能赛道近两年获奖作品都在用什么技术路线？我该怎样做出差异？",
                label_visibility="collapsed",
            )
        with c2:
            top_k = st.slider("检索条数", 3, 12, 6, label_visibility="collapsed")
        cat = st.selectbox("限定类别（可选）", ["不限"] + cached_categories())
        submitted = st.form_submit_button("提问", width="stretch")

    if submitted:
        q = (question or "").strip()
        if not q:
            st.warning("请先输入问题")
        else:
            with st.spinner("检索中…"):
                filters = None if cat == "不限" else {"category": cat}
                rows = retriever.retrieve(q, top_k=top_k, filters=filters)
            st.session_state["qa_q"] = q
            st.session_state["qa_rows"] = rows

    q = st.session_state.get("qa_q")
    rows = st.session_state.get("qa_rows")
    if not q:
        st.info("输入问题后点击「提问」，AI 会先检索作品库再作答。")
        return

    st.markdown(f"**你的问题：** {q}")
    if not rows:
        st.warning("没有检索到相关作品，请换个问法或放宽类别限制。")
        return

    st.subheader("回答")
    used_ai = ask_llm_stream(
        build_qa_prompt(q, rows),
        system=QA_SYSTEM,
        rows=rows,
        question=q,
    )
    if used_ai:
        render_refs(rows, "qa")


# ---------------------------------------------------------------- 灵感工作台
KIND_META = {
    "experience": ("💡 获奖经验", "exp"),
    "trend": ("📈 选题趋势", "trend"),
    "gap": ("🕳 空白机会", "gap"),
}
KIND_ORDER = ["experience", "trend", "gap"]


def load_insights():
    """按 kind 分组的洞察列表。"""
    conn = db.get_conn()
    rows = conn.execute(
        "SELECT id, kind, scope, content_md, evidence, created_at "
        "FROM insights ORDER BY kind, scope"
    ).fetchall()
    grouped = {k: [] for k in KIND_ORDER}
    for r in rows:
        d = dict(r)
        grouped.setdefault(d["kind"], []).append(d)
    return grouped


def load_ideas(status=None):
    conn = db.get_conn()
    sql = "SELECT * FROM ideas"
    args = ()
    if status and status != "全部":
        sql += " WHERE status = ?"
        args = (status,)
    sql += " ORDER BY id"
    return [dict(r) for r in conn.execute(sql, args).fetchall()]


def scope_text(scope):
    """把 category:XXX|year:2021-2025 渲染成可读文字。"""
    parts = []
    for seg in (scope or "").split("|"):
        if seg.startswith("category:"):
            parts.append(seg.split(":", 1)[1])
        elif seg.startswith("year:"):
            parts.append(seg.split(":", 1)[1])
    return " · ".join(parts) or (scope or "")


def render_insights(grouped):
    st.subheader("赛事洞察")
    st.caption("由往届作品库归纳出的经验 / 趋势 / 空白点，可作为选题依据。")

    tabs = st.tabs([KIND_META[k][0] for k in KIND_ORDER])
    for tab, kind in zip(tabs, KIND_ORDER):
        with tab:
            items = grouped.get(kind) or []
            if not items:
                st.info("暂无数据")
                continue
            for it in items:
                with st.expander(f"{scope_text(it['scope'])}", expanded=(len(items) == 1)):
                    st.markdown(it["content_md"])
                    ev = (it.get("evidence") or "").strip()
                    if ev:
                        st.caption(f"证据（作品编号）：{ev}")


def render_ideas(ideas):
    st.subheader("选题灵感")
    st.caption("结合洞察生成的候选选题，含差异化卖点与风险提示。可标星收藏、采纳归档。")

    if not ideas:
        st.info("该状态下暂无选题灵感，切换上方筛选看看。")
        return

    for it in ideas:
        iid = it["id"]
        cur_status = it.get("status") or "draft"
        head = (
            f'<div class="idea-head"><span class="idea-title">{esc(it.get("title"))}</span>'
            f'<span class="idea-status st-{esc(cur_status)}">'
            f'{esc(IDEA_STATUS_LABEL.get(cur_status, cur_status))}</span></div>'
        )
        st.markdown(head, unsafe_allow_html=True)

        if it.get("pitch"):
            st.markdown(f"> {it['pitch']}")

        with st.expander("展开：做法 / 差异化 / 风险"):
            if it.get("detail_md"):
                st.markdown(it["detail_md"])
            if it.get("novelty"):
                st.markdown("#### 差异化")
                st.markdown(it["novelty"])
            if it.get("risk"):
                st.markdown("#### 风险与对策")
                st.markdown(it["risk"])
            if it.get("ref_awards"):
                st.caption(f"参考作品编号：{it['ref_awards']}")

        # ---- 状态流转按钮 ----
        next_status, btn_label = IDEA_STATUS_FLOW[cur_status]
        help_txt = {
            "starred": "标星后进入「已收藏」，方便回看",
            "archived": "采纳后归档，代表已选定这个方向",
            "draft": "退回草稿池重新评估",
        }[next_status]

        col_a, col_b, _ = st.columns([1, 1, 4])
        with col_a:
            if st.button(btn_label, key=f"idea_adv_{iid}", help=help_txt,
                         use_container_width=True):
                if update_idea_status(iid, next_status):
                    st.toast(f"已更新为「{IDEA_STATUS_LABEL[next_status]}」")
                    st.rerun()
        with col_b:
            if cur_status != "draft":
                if st.button("↩️ 重置草稿", key=f"idea_rst_{iid}",
                             use_container_width=True):
                    if update_idea_status(iid, "draft"):
                        st.toast("已重置为草稿")
                        st.rerun()
        st.divider()



def page_ideas():
    st.header("灵感工作台")
    grouped = load_insights()
    n_ins = sum(len(v) for v in grouped.values())

    all_ideas = load_ideas()
    status_count = {"draft": 0, "starred": 0, "archived": 0}
    for it in all_ideas:
        status_count[it.get("status") or "draft"] = \
            status_count.get(it.get("status") or "draft", 0) + 1

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("洞察条目", n_ins)
    c2.metric("选题灵感", len(all_ideas))
    c3.metric("⭐ 已收藏", status_count.get("starred", 0))
    c4.metric("📦 已采纳", status_count.get("archived", 0))

    render_insights(grouped)
    st.markdown("---")

    status = st.radio(
        "筛选灵感", ["全部", "draft", "starred", "archived"],
        format_func=lambda s: {"全部": "全部", "draft": "草稿",
                               "starred": "⭐ 已收藏", "archived": "📦 已采纳"}[s],
        horizontal=True,
    )
    render_ideas(load_ideas(status))


# ---------------------------------------------------------------- 页面
def page_list():
    st.header("竞赛列表")

    categories = ["全部"] + cached_categories()
    col1, col2, col3 = st.columns([2, 2, 3])
    with col1:
        sel_cat = st.selectbox("类别", categories, index=0)
    with col2:
        sel_month = st.selectbox("报名月份", ["全部"] + MONTH_LABELS, index=0)
    with col3:
        kw = st.text_input("关键词搜索", placeholder="输入比赛名称关键词…")

    cat_arg = None if sel_cat == "全部" else sel_cat
    month_arg = None if sel_month == "全部" else MONTHS[MONTH_LABELS.index(sel_month)]
    kw_arg = (kw or "").strip() or None

    # 筛选变化时重置分页
    _filter_sig = (cat_arg, month_arg, kw_arg)
    if st.session_state.get("card_filter_sig") != _filter_sig:
        st.session_state["card_filter_sig"] = _filter_sig
        st.session_state["card_page"] = 1

    rows = db.list_competitions(category=cat_arg, month=month_arg, keyword=kw_arg)

    n_total = len(rows)
    n_nat = sum(1 for r in rows if level_theme(r.get("level"), r.get("level_label"))[0] == "national")
    n_pro = sum(1 for r in rows if level_theme(r.get("level"), r.get("level_label"))[0] == "provincial")
    n_reg = sum(1 for r in rows if level_theme(r.get("level"), r.get("level_label"))[0] == "regional")
    st.caption(
        f"共 {n_total} 条记录 · 国家级 {n_nat} · 省级 {n_pro} · 区域级 {n_reg}"
    )

    render_cards_paginated(rows, CARDS_PER_PAGE)


def page_timeline():
    st.header("报名时间轴")
    month = st.select_slider("选择月份", options=MONTHS, format_func=lambda m: f"{m}月")
    tl = db.get_month_timeline(month)

    reg = tl.get("registering") or []
    comp = tl.get("competing") or []

    st.subheader(f"{month}月报名中 · 共 {len(reg)} 项")
    if reg:
        render_cards(reg)
    else:
        st.info(f"{month}月暂无在报名的比赛")

    if comp:
        st.subheader(f"{month}月进行中 · 共 {len(comp)} 项")
        render_cards(comp)


def main():
    st.set_page_config(
        page_title="竞赛信息检索",
        page_icon="🏆",
        layout="wide",
        initial_sidebar_state="expanded",  # 仅控制首屏默认展开，用户可自由收起
    )
    db.init_db()
    inject_styles()

    st.sidebar.title("🏆 竞赛信息检索")
    page = st.sidebar.radio("页面", ["竞赛列表", "报名时间轴", "智能问答", "灵感工作台"])
    st.sidebar.caption("数据仅供查询参考")

    if page == "竞赛列表":
        page_list()
    elif page == "报名时间轴":
        page_timeline()
    elif page == "智能问答":
        page_qa()
    else:
        page_ideas()


if __name__ == "__main__":
    main()
