# -*- coding: utf-8 -*-
"""
💡 灵感工作台（pages/灵感工作台.py）—— S3

职责
    展示 analyzer.py 离线生成的两类成果：
      1) 经验总结 insights（experience / trend / gap）
      2) idea 方案清单 ideas

    并提供轻量的状态管理（草稿 / 收藏 / 归档），便于人工筛选。

数据来源
    analyzer.py 跑完后写入 SQLite（competitions.db）的 insights / ideas 表。
    本页面本身不调用 LLM，只读库、只改状态，秒开。

设计要点
    1. 只在页面层做「分组 + 过滤 + 排序」，避免为展示再造视图表。
    2. evidence / ref_awards 是 JSON 文本，统一走 kb.json_loads 容错解析。
    3. 全部读取走 kb.query，带 try/except，库未初始化时给出友好引导。
"""

import streamlit as st

import kb

KIND_LABEL = {"experience": "🏆 获奖共性经验", "trend": "📈 选题与技术趋势",
              "gap": "🕳 选题空白与机会"}
KIND_ORDER = ["experience", "trend", "gap"]
STATUS_LABEL = {"draft": "📝 草稿", "starred": "⭐ 已收藏", "archived": "📦 已归档"}
STATUS_ORDER = ["draft", "starred", "archived"]


# ---------------------------------------------------------------- 数据读取
@st.cache_data(ttl=30, show_spinner=False)
def load_insights() -> list:
    try:
        return kb.query("SELECT * FROM insights ORDER BY scope, kind, id DESC")
    except Exception:  # noqa: BLE001
        return []


@st.cache_data(ttl=30, show_spinner=False)
def load_ideas() -> list:
    try:
        return kb.query("SELECT * FROM ideas ORDER BY "
                        "CASE status WHEN 'starred' THEN 0 WHEN 'draft' THEN 1 ELSE 2 END, "
                        "id DESC")
    except Exception:  # noqa: BLE001
        return []


def _scope_parts(scope: str) -> tuple:
    """把 'category:X|year:2020-2025' 拆成 (类别, 年份区间)。"""
    cat, years = "全部", ""
    for seg in (scope or "").split("|"):
        if seg.startswith("category:"):
            cat = seg[len("category:"):] or "全部"
        elif seg.startswith("year:"):
            years = seg[len("year:"):]
    return cat, years


def _as_list(v) -> list:
    data = kb.json_loads(v, default=None)
    if isinstance(data, list):
        return data
    return []


def _scopes(insights: list) -> list:
    seen = []
    for r in insights:
        s = r.get("scope") or ""
        if s and s not in seen:
            seen.append(s)
    return sorted(seen)


# ---------------------------------------------------------------- 经验总结视图
def view_insights(insights: list) -> None:
    scopes = _scopes(insights)
    if not scopes:
        st.info("还没有生成任何经验总结。请先在终端运行：`python analyzer.py`")
        return

    c1, c2 = st.columns([2, 1])
    with c1:
        scope = st.selectbox("分析范围", scopes, key="insight_scope")
    with c2:
        kind = st.selectbox(
            "洞察类型", ["全部"] + KIND_ORDER,
            format_func=lambda k: "全部" if k == "全部" else KIND_LABEL.get(k, k),
            key="insight_kind",
        )

    cat, years = _scope_parts(scope)
    st.caption(f"类别：**{cat}** ｜ 年份区间：**{years or '—'}**")

    rows = [r for r in insights if (r.get("scope") or "") == scope]
    kinds = [kind] if kind != "全部" else KIND_ORDER
    shown = 0
    for k in kinds:
        group = [r for r in rows if r.get("kind") == k]
        if not group:
            continue
        with st.expander(KIND_LABEL.get(k, k), expanded=True):
            latest = group[0]
            st.markdown(latest.get("content_md") or "_（空）_")
            meta = []
            if latest.get("model"):
                meta.append(f"模型 `{latest['model']}`")
            if latest.get("created_at"):
                meta.append(f"生成于 {latest['created_at']}")
            ev = _as_list(latest.get("evidence"))
            if ev:
                meta.append(f"引用作品 {len(ev)} 条")
            if meta:
                st.caption(" ｜ ".join(meta))
            if ev:
                with st.popover("查看引用作品 ID"):
                    st.write(ev)
            shown += 1

    if not shown:
        st.warning("该范围下暂无对应类型的洞察。")


# ---------------------------------------------------------------- idea 清单视图
def _idea_card(it: dict, idx: int) -> None:
    st.markdown(f"#### {idx}. {it.get('title', '(无标题)')}")
    if it.get("pitch"):
        st.markdown(f"> {it['pitch']}")

    badge = STATUS_LABEL.get(it.get("status", "draft"), it.get("status", ""))
    meta = [badge]
    if it.get("competition_id"):
        meta.append(f"赛事 #{it['competition_id']}")
    if it.get("created_at"):
        meta.append(it["created_at"])
    st.caption(" ｜ ".join(str(m) for m in meta))

    if it.get("detail_md"):
        with st.expander("展开方案细节"):
            st.markdown(it["detail_md"])
            if it.get("novelty"):
                st.markdown(f"**差异化**：{it['novelty']}")
            if it.get("risk"):
                st.markdown(f"**风险与规避**：{it['risk']}")
            refs = _as_list(it.get("ref_awards"))
            if refs:
                st.caption(f"借鉴作品 ID：{refs}")

    # ---- 状态操作 ----
    cols = st.columns([1, 1, 1, 3])
    cur = it.get("status", "draft")
    for col, (sid, label) in zip(cols, STATUS_LABEL.items()):
        with col:
            btn = st.button(
                label, key=f"idea_{it['id']}_{sid}",
                disabled=(cur == sid),
                use_container_width=True,
            )
            if btn:
                kb.update("ideas", it["id"], {"status": sid})
                st.cache_data.clear()
                st.rerun()
    st.divider()


def view_ideas(ideas: list) -> None:
    if not ideas:
        st.info("还没有生成任何 idea。请先在终端运行：`python analyzer.py --only idea`")
        return

    c1, c2, c3 = st.columns([1, 1, 2])
    with c1:
        status = st.selectbox(
            "状态", ["全部"] + STATUS_ORDER,
            format_func=lambda s: "全部" if s == "全部" else STATUS_LABEL.get(s, s),
        )
    with c2:
        kw = st.text_input("关键字", placeholder="标题/主张/细节")
    with c3:
        st.write("")
        st.caption(f"共 {len(ideas)} 条 idea")

    rows = ideas
    if status != "全部":
        rows = [r for r in rows if r.get("status") == status]
    if kw.strip():
        k = kw.strip().lower()
        rows = [r for r in rows
                if k in (r.get("title") or "").lower()
                or k in (r.get("pitch") or "").lower()
                or k in (r.get("detail_md") or "").lower()]

    if not rows:
        st.warning("没有符合条件的 idea。")
        return

    st.divider()
    for i, it in enumerate(rows, 1):
        _idea_card(it, i)


# ---------------------------------------------------------------- 主入口
def main() -> None:
    st.set_page_config(page_title="灵感工作台", page_icon="💡", layout="wide")
    st.title("💡 灵感工作台")
    st.caption("S3 · 展示 analyzer.py 生成的获奖经验总结与今年赛事 idea 方案")

    insights = load_insights()
    ideas = load_ideas()

    m1, m2, m3 = st.columns(3)
    m1.metric("经验总结", len(insights))
    m2.metric("idea 总数", len(ideas))
    m3.metric("已收藏", sum(1 for r in ideas if r.get("status") == "starred"))

    if st.button("🔄 刷新数据（analyzer.py 跑完后点此）"):
        st.cache_data.clear()
        st.rerun()

    tab1, tab2 = st.tabs(["🏆 经验总结", "🚀 idea 清单"])
    with tab1:
        view_insights(insights)
    with tab2:
        view_ideas(ideas)


if __name__ == "__main__":
    main()
else:
    main()
