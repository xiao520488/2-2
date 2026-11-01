# -*- coding: utf-8 -*-
"""云端冷启动自动初始化。

Streamlit Community Cloud 每次部署都是全新的容器，仓库里不会带 .db 文件
（也不应该带）。本模块负责在首次访问时把空库变成"可用的演示环境"：

    1. 建表（competitions + 知识库表）
    2. 若 competitions / awards 为空 → 灌入 seed_data 演示数据
    3. 把 approved 状态的 awards 同步进 Chroma 向量库
    4. 任一步失败都不阻断应用启动，只记录警告

对外只暴露 ensure_ready()，由 app.py 在 main() 开头调用一次。
"""

import threading
import time
import traceback

import streamlit as st

import db
import kb
import retriever


_SS_KEY = "_bootstrap_done"
_SS_WARN = "_bootstrap_warnings"
_SS_REPORT = "_bootstrap_report"

# --- 模块级一次性守卫（进程级），兜底 st.cache_resource 失效的场景 ---
_BOOT_LOCK = threading.Lock()
_BOOTED = False
_BOOT_REPORT = None


def _count(table: str) -> int:
    """安全计数，表不存在时返回 0。"""
    try:
        with kb.conn_ctx() as conn:
            row = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
            return int(row[0]) if row else 0
    except Exception:
        return 0


def _is_empty() -> bool:
    """数据库是否为空（competitions 与 awards 都为空才算空）。"""
    return _count("competitions") == 0 and _count("awards") == 0


def _seed_competitions() -> int:
    """写入演示竞赛数据，返回新增条数（逐条容错）。"""
    import seed_data

    n = 0
    for item in seed_data.COMPETITIONS:
        try:
            db.add_competition(item)
            n += 1
        except Exception as e:
            st.warning(f"竞赛种子写入失败：{item.get('name')} — {e}")
    return n


def _seed_awards() -> int:
    """写入演示获奖数据，并按竞赛名称回填 competition_id。"""
    import seed_data

    # name -> id 映射，用于关联竞赛
    name2id = {}
    try:
        for row in db.list_competitions():
            name2id[row["name"]] = row["id"]
    except Exception:
        pass

    n = 0
    for item in seed_data.AWARDS:
        data = dict(item)
        cname = data.pop("competition_name", None)
        if cname and cname in name2id:
            data["competition_id"] = name2id[cname]
        # 云端演示数据直接标记为已审核，让问答检索立刻可用
        data.setdefault("review_status", "approved")
        try:
            _aid, action = kb.upsert_award(data)
            if action in ("inserted", "updated"):
                n += 1
        except Exception as e:
            st.warning(f"获奖种子写入失败：{item.get('title')} — {e}")
    return n


def _sync_chroma(limit: int = 64) -> dict:
    """把 approved awards 同步进 Chroma。

    返回 {"total","synced","indexed"}；失败返回 {"error": ...}。
    """
    try:
        return retriever.sync_awards_to_chroma(only_approved=True, limit=limit)
    except Exception as e:
        st.warning(f"向量库同步失败（问答检索可能为空）：{e}")
        return {"error": str(e)}


def _seed_insights() -> int:
    """补灌洞察数据（kind/scope/content_md/evidence/model/input_hash）。

    走 kb.save_insight，靠 input_hash 部分唯一索引幂等：
    已存在的条目返回 None，不会重复写入，也不会重复消耗 token。
    """
    import seed_data

    n = 0
    for item in getattr(seed_data, "INSIGHTS", []):
        try:
            evidence = item.get("evidence")
            if isinstance(evidence, str):
                evidence = kb.json_loads(evidence)
            new_id = kb.save_insight(
                kind=item["kind"],
                scope=item["scope"],
                content_md=item["content_md"],
                model=item.get("model") or "",
                evidence=evidence,
                input_hash=item.get("input_hash"),
            )
            if new_id:
                n += 1
        except Exception as e:
            st.warning(f"洞察种子写入失败：{item.get('scope')} — {e}")
    return n


def _seed_ideas() -> int:
    """补灌灵感数据（title/pitch/detail_md/novelty/risk/ref_awards/status）。

    走 kb.add_idea，按 content_hash = sha1(title) 幂等，重复条目返回 skipped。
    ref_awards 在 seed 里已是 JSON 字符串，原样透传即可（add_idea 不会二次序列化 str）。
    """
    import seed_data

    n = 0
    for item in getattr(seed_data, "IDEAS", []):
        try:
            data = dict(item)
            title = data.pop("title")
            _new_id, action = kb.add_idea(title, **data)
            if action == "inserted":
                n += 1
        except Exception as e:
            st.warning(f"灵感种子写入失败：{item.get('title')} — {e}")
    return n


def _seed_kb_tables() -> dict:
    """按表独立兜底：哪张知识库表空了就单独补灌哪张。

    与 _is_empty() 的区别：_is_empty() 只判断 competitions/awards 是否都为空，
    一旦线上库已有竞赛和作品、却被误删了 insights/ideas，就走不到灌数分支。
    这里对两张表分别计数，缺失即补，幂等且不重复消耗 embedding。
    """
    result = {"insights": 0, "ideas": 0}
    if _count("insights") == 0:
        result["insights"] = _seed_insights()
    if _count("ideas") == 0:
        result["ideas"] = _seed_ideas()
    return result


def _run_bootstrap_once() -> dict:
    """真正的初始化逻辑，整个进程只成功执行一次。"""
    report = {
        "ok": True, "skipped": False, "error": None,
        "seeded_comp": 0, "seeded_awards": 0, "sync": {},
        "seeded_insights": 0, "seeded_ideas": 0,
    }

    # --- 1. 建表（失败则直接放弃，后续都依赖表） ---
    try:
        db.init_db()
        kb.init_kb()
    except Exception as e:
        report["ok"] = False
        report["error"] = f"建表失败：{e}"
        return report

    # --- 2/3. 主数据：空库才灌竞赛与作品 ---
    try:
        empty = _is_empty()
    except Exception as e:
        report["error"] = f"空库检测失败：{e}"
        return report

    if empty:
        report["seeded_comp"] = _seed_competitions()
        report["seeded_awards"] = _seed_awards()
    else:
        # 库非空：主数据不重灌，但知识库表可能被清空过，交给第 4 步兜底
        report["skipped"] = True

    # --- 4. 知识库表兜底：insights / ideas 缺哪张补哪张（幂等） ---
    try:
        kb_seeded = _seed_kb_tables()
        report["seeded_insights"] = kb_seeded.get("insights", 0)
        report["seeded_ideas"] = kb_seeded.get("ideas", 0)
    except Exception as e:
        report["error"] = f"知识库种子补灌失败：{e}"

    # --- 5. 同步向量库 ---
    report["sync"] = _sync_chroma(limit=64)

    return report


def _bootstrap_cached() -> dict:
    """进程级一次性初始化（模块级锁兜底，绝不重复造数/embed）。"""
    global _BOOTED, _BOOT_REPORT

    if _BOOTED and _BOOT_REPORT is not None:
        return _BOOT_REPORT

    with _BOOT_LOCK:
        if _BOOTED and _BOOT_REPORT is not None:
            return _BOOT_REPORT
        report = _run_bootstrap_once()
        _BOOT_REPORT = report
        if report.get("ok"):
            _BOOTED = True
        return report


def ensure_ready(verbose: bool = True) -> dict:
    """应用启动入口。幂等，多次调用安全。"""
    if st.session_state.get(_SS_KEY):
        return st.session_state.get(_SS_REPORT, {})

    t0 = time.time()
    try:
        report = _bootstrap_cached()
    except Exception:
        report = {"ok": False, "error": traceback.format_exc(limit=3)}
    report["cost"] = round(time.time() - t0, 2)

    st.session_state[_SS_KEY] = True
    st.session_state[_SS_REPORT] = report

    if verbose:
        if report.get("error"):
            st.session_state[_SS_WARN] = report["error"]
        elif not report.get("skipped"):
            parts = []
            if report.get("seeded_comp"):
                parts.append(f"竞赛 {report['seeded_comp']} 条")
            if report.get("seeded_awards"):
                parts.append(f"作品 {report['seeded_awards']} 条")
            if report.get("seeded_insights"):
                parts.append(f"洞察 {report['seeded_insights']} 条")
            if report.get("seeded_ideas"):
                parts.append(f"灵感 {report['seeded_ideas']} 条")
            if parts:
                st.toast(f"演示数据初始化完成：{' · '.join(parts)}（{report['cost']}s）")
    return report


def show_banner() -> None:
    """在页面顶部展示初始化异常（仅展示一次）。"""
    w = st.session_state.get(_SS_WARN)
    if w:
        st.warning(f"⚠️ 初始化提示：{w}")


def is_empty_db() -> bool:
    """供 UI 判断是否为空库。"""
    return _is_empty()
