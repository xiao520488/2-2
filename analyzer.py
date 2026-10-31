# -*- coding: utf-8 -*-
"""
S3-1 离线批处理分析器（analyzer.py）

职责
    读取知识库中的获奖数据（awards），调用 DeepSeek 生成两类成果并落库：
      1) 经验总结 insights（kind = experience / trend / gap）
      2) 今年赛事的 idea 方案 ideas

命令行用法（不启动任何服务，跑完即退出）
    python analyzer.py                      # 默认：近 5 年、每个类别都分析 + 生成 idea
    python analyzer.py --years 3            # 只分析近 3 年
    python analyzer.py --category 人工智能  # 只做单个类别
    python analyzer.py --only insight       # 只生成经验总结，不生成 idea
    python analyzer.py --only idea          # 只生成 idea
    python analyzer.py --idea-n 6           # 每个类别生成 6 条 idea（默认 4）
    python analyzer.py --dry-run            # 只打印统计和 prompt 预览，不调 LLM、不写库
    python analyzer.py --force              # 忽略 input_hash 去重，强制重生成

设计要点
    1. 幂等：insights 走 save_insight 的 input_hash 去重；ideas 走 add_idea 的 title 去重。
    2. 数据瘦身：只把「必要字段 + 截断后的长文本」喂给模型，控制 token。
    3. 结构化输出：全部用 chat_json + schema_hint，避免解析失败。
    4. 单类别失败不影响其它类别：逐类别 try/except，最后汇总报告。
    5. 费用可观测：结束时打印 llm.get_usage()。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from typing import Optional

import kb
import llm

# ---------------------------------------------------------------- 常量
DEFAULT_YEARS = 5          # 默认回看年数
MAX_AWARDS_PER_SCOPE = 60  # 单次喂给模型的最大作品条数
MAX_FIELD_CHARS = 300      # 单个长文本字段截断长度
DEFAULT_IDEA_N = 4         # 每个类别默认生成 idea 条数

# 年份上限：以库中最大获奖年份为准（"今年比赛"的基线）
MODEL_NAME = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")


# ---------------------------------------------------------------- 工具
def _clip(s: Optional[str], n: int = MAX_FIELD_CHARS) -> str:
    """截断长文本，避免喂爆 token。"""
    if not s:
        return ""
    s = " ".join(str(s).split())
    return s if len(s) <= n else s[:n] + "…"


def _fair_sample(rows: list, k: int) -> list:
    """跨年份均匀抽样，避免只拿到某一年的作品。"""
    if len(rows) <= k:
        return rows
    step = len(rows) / k
    return [rows[int(i * step)] for i in range(k)]


def _digest(obj) -> str:
    """把输入内容压成 sha1，作为 input_hash / 变更检测依据。"""
    raw = json.dumps(obj, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def _slim_award(r: dict) -> dict:
    """获奖记录瘦身：只保留对分析有价值的字段。"""
    return {
        "id": r.get("id"),
        "year": r.get("year"),
        "competition": r.get("competition_raw") or "",
        "level": r.get("level"),
        "award": r.get("award_grade") or r.get("award") or "",
        "title": _clip(r.get("title"), 120),
        "summary": _clip(r.get("summary")),
        "highlights": _clip(r.get("highlights")),
        "tech_stack": _clip(r.get("tech_stack"), 120),
    }


def _awards_of(category: Optional[str], year_from: int, year_to: int) -> list:
    rows = kb.list_awards(
        year_from=year_from, year_to=year_to,
        category=category,
        order_by="year DESC, id DESC",
    )
    return rows


def _scope_of(category: Optional[str], year_from: int, year_to: int) -> str:
    cat = category or "全部"
    return f"category:{cat}|year:{year_from}-{year_to}"


# ---------------------------------------------------------------- 经验总结
_SYS_INSIGHT = (
    "你是一名资深的学科竞赛指导老师，擅长从历年获奖作品中提炼可复用的备赛方法论。"
    "只输出 JSON，不要任何解释性文字。"
)


def gen_insights(category: Optional[str], year_from: int, year_to: int,
                 rows: list, *, force: bool = False) -> dict:
    """为一组获奖数据生成 experience / trend / gap 三类洞察并落库。"""
    scope = _scope_of(category, year_from, year_to)
    payload = [_slim_award(r) for r in _fair_sample(rows, MAX_AWARDS_PER_SCOPE)]
    input_hash = _digest({"scope": scope, "data": payload, "v": 2})

    if not force:
        old = kb.get_insight("experience", scope)
        if old and old.get("input_hash") == input_hash:
            return {"scope": scope, "status": "skipped(unchanged)", "n": len(payload)}

    prompt = f"""下面是「{category or '全部类别'}」在 {year_from}-{year_to} 年的获奖作品数据（已截断）：
{json.dumps(payload, ensure_ascii=False)}

请基于这些真实数据（不要编造数据中不存在的事实）输出三份 Markdown 分析：

1. experience：获奖共性经验。分点写，每点给出「做法 + 为什么有效 + 可执行建议」。
2. trend：选题与技术趋势。说明近几年的变化方向，指出上升/下降的题材或技术栈。
3. gap：尚未被充分占据的选题空白与差异化机会，指出哪些方向竞争过热。

要求：
- 全部用中文，Markdown 小标题组织，总长度控制在 1200 字以内。
- 结论必须能追溯到给定数据中的具体作品特征。
"""

    schema_hint = json.dumps({
        "experience": "string (Markdown)",
        "trend": "string (Markdown)",
        "gap": "string (Markdown)",
        "evidence_ids": "array of int, 引用的作品 id",
    }, ensure_ascii=False)

    result = llm.chat_json(prompt, system=_SYS_INSIGHT,
                           schema_hint=schema_hint, temperature=0.3, max_tokens=2600)

    evidence = result.get("evidence_ids") or [r.get("id") for r in payload]
    saved = {}
    for kind in ("experience", "trend", "gap"):
        md = (result.get(kind) or "").strip()
        if not md:
            saved[kind] = "empty"
            continue
        rid = kb.save_insight(
            kind, scope, md,
            model=MODEL_NAME,
            evidence=evidence if isinstance(evidence, list) else None,
            input_hash=input_hash if kind == "experience" else None,
        )
        saved[kind] = "inserted" if rid else "skipped(dup)"

    return {"scope": scope, "status": saved, "n": len(payload)}


# ---------------------------------------------------------------- idea 生成
_SYS_IDEA = (
    "你是一名竞赛选题顾问，擅长把往届获奖规律转化为今年可落地、可差异化的参赛方案。"
    "只输出 JSON，不要任何解释性文字。"
)


def gen_ideas(category: Optional[str], year_from: int, year_to: int,
              rows: list, *, n: int = DEFAULT_IDEA_N) -> dict:
    """为一组获奖数据生成今年的 idea 清单，写入 ideas 表。"""
    scope = _scope_of(category, year_from, year_to)
    payload = [_slim_award(r) for r in _fair_sample(rows, MAX_AWARDS_PER_SCOPE)]

    prompt = f"""下面是「{category or '全部类别'}」在 {year_from}-{year_to} 年的获奖作品数据：
{json.dumps(payload, ensure_ascii=False)}

请基于上面的获奖规律，为「{year_to + 1} 年」的比赛设计 {n} 个新的参赛 idea。
要求：
- 每个 idea 必须与已有获奖作品有明确差异，不要照抄 data 中已出现的题目。
- 结合真实可获取的数据/技术，方案要能在 3-6 个月内由 3-5 人小组完成。
- ref_awards 填你借鉴的、上面 data 中真实存在的作品 id。
"""

    schema_hint = json.dumps({
        "ideas": [{
            "title": "string, idea 名称",
            "pitch": "string, 一句话价值主张",
            "detail_md": "string, Markdown 展开方案：背景/做法/交付物",
            "novelty": "string, 与往届获奖作品的差异化说明",
            "risk": "string, 主要风险与规避",
            "ref_awards": "array of int, 借鉴的作品 id",
        }]
    }, ensure_ascii=False)

    result = llm.chat_json(prompt, system=_SYS_IDEA,
                           schema_hint=schema_hint, temperature=0.8, max_tokens=3000)
    items = result.get("ideas") or []

    inserted, skipped = 0, 0
    for it in items:
        title = (it.get("title") or "").strip()
        if not title:
            continue
        _, action = kb.add_idea(
            title,
            pitch=_clip(it.get("pitch"), 200),
            detail_md=it.get("detail_md"),
            novelty=_clip(it.get("novelty"), 400),
            risk=_clip(it.get("risk"), 400),
            ref_awards=it.get("ref_awards") or [],
            status="draft",
        )
        if action == "inserted":
            inserted += 1
        else:
            skipped += 1

    return {"scope": scope, "status": "ok",
            "inserted": inserted, "skipped": skipped, "n": len(payload)}


# ---------------------------------------------------------------- 主流程
def pick_categories(only_category: Optional[str]) -> list:
    """确定要分析的类别列表（None 表示"全部类别"这一整体）。"""
    if only_category:
        return [only_category]
    rows = kb.query(
        "SELECT category, COUNT(*) c FROM awards WHERE category IS NOT NULL "
        "AND category <> '' GROUP BY category ORDER BY c DESC"
    )
    cats = [r["category"] for r in rows if r.get("category")]
    return cats or [None]


def run(years: int, only_category: Optional[str], only: str,
        idea_n: int, dry_run: bool, force: bool) -> None:
    total = kb.query("SELECT COUNT(*) c, MIN(year) mn, MAX(year) mx FROM awards")
    stat = total[0] if total else {"c": 0, "mn": None, "mx": None}
    if not stat.get("c"):
        print("[!] awards 表为空，请先导入获奖数据（import_excel.py / kb.upsert_award）。")
        return

    year_to = int(stat["mx"])
    year_from = max(int(stat["mn"] or year_to), year_to - years + 1)
    print(f"[i] 库中共 {stat['c']} 条获奖记录，分析区间 {year_from}-{year_to}")

    categories = pick_categories(only_category)
    print(f"[i] 待分析类别 {len(categories)} 个：{categories}")
    print(f"[i] 模式：only={only}, idea_n={idea_n}, dry_run={dry_run}, force={force}")

    report = []
    for cat in categories:
        rows = _awards_of(cat, year_from, year_to)
        print(f"\n--- {cat or '全部类别'}：命中 {len(rows)} 条 ---")
        if not rows:
            report.append({"category": cat, "status": "no-data"})
            continue

        if dry_run:
            preview = [_slim_award(r) for r in _fair_sample(rows, MAX_AWARDS_PER_SCOPE)]
            print(f"[dry-run] 将喂给模型 {len(preview)} 条，样例如下：")
            print(json.dumps(preview[:2], ensure_ascii=False, indent=2))
            report.append({"category": cat, "status": "dry-run", "n": len(preview)})
            continue

        if only in ("all", "insight"):
            try:
                r = gen_insights(cat, year_from, year_to, rows, force=force)
                print(f"[insight] {r}")
                report.append({"category": cat, "insight": r})
            except llm.LLMError as exc:
                print(f"[x] insight 失败（{cat}）：{exc}")
                report.append({"category": cat, "insight": f"error: {exc}"})

        if only in ("all", "idea"):
            try:
                r = gen_ideas(cat, year_from, year_to, rows, n=idea_n)
                print(f"[idea] {r}")
                report.append({"category": cat, "idea": r})
            except llm.LLMError as exc:
                print(f"[x] idea 失败（{cat}）：{exc}")
                report.append({"category": cat, "idea": f"error: {exc}"})

        time.sleep(0.5)  # 温和限速

    print("\n================ 汇总 ================")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print("\n[token] ", llm.get_usage())


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="S3 获奖数据分析器：生成经验总结(insights) 与 idea 方案(ideas)")
    p.add_argument("--years", type=int, default=DEFAULT_YEARS,
                   help=f"回看年数，默认 {DEFAULT_YEARS}")
    p.add_argument("--category", type=str, default=None,
                   help="只分析指定类别，默认分析全部类别")
    p.add_argument("--only", choices=["all", "insight", "idea"], default="all",
                   help="只跑经验总结 / 只跑 idea / 两者都跑（默认）")
    p.add_argument("--idea-n", type=int, default=DEFAULT_IDEA_N,
                   help=f"每个类别生成的 idea 条数，默认 {DEFAULT_IDEA_N}")
    p.add_argument("--dry-run", action="store_true",
                   help="只打印统计与样例，不调用 LLM、不写库")
    p.add_argument("--force", action="store_true",
                   help="忽略 input_hash 去重，强制重新生成")
    return p


def main(argv: Optional[list] = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        kb.init_kb()
    except Exception as exc:  # noqa: BLE001
        print(f"[!] 初始化知识库失败：{exc}", file=sys.stderr)
        return 1
    run(args.years, args.category, args.only, args.idea_n, args.dry_run, args.force)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
