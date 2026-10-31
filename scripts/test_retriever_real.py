# -*- coding: utf-8 -*-
"""
S1 检索内核自测 (test_retriever.py)

策略：
    - 强制 Mock 向量（KB_EMBED_MODE=mock），不依赖外网 / 模型下载
    - 使用临时 SQLite 库 + 临时 Chroma 目录，跑完即删，不污染正式数据
    - 覆盖：索引同步 / 两级检索 / 结构化过滤 / 未审核降级 / 空查询 / 重建

运行：
    python test_retriever.py
"""

import os
import shutil
import sys
import tempfile

os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"
os.environ["KB_EMBED_MODE"] = "real"

sys.stdout.reconfigure(encoding="utf-8")

TMP = tempfile.mkdtemp(prefix="kb_s1_")
os.environ["KB_CHROMA_DIR"] = os.path.join(TMP, "chroma")

import kb  # noqa: E402
import retriever  # noqa: E402

kb.DB_PATH = os.path.join(TMP, "test.db")
kb.SCHEMA_KB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "schema_kb.sql")

_PASS, _FAIL = 0, 0


def check(name, cond, extra=""):
    global _PASS, _FAIL
    if cond:
        _PASS += 1
        print(f"  [PASS] {name}")
    else:
        _FAIL += 1
        print(f"  [FAIL] {name} {extra}")


SEEDS = [
    dict(competition_raw="全国大学生智能汽车竞赛", category="人工智能", level="national",
         year=2023, title="基于YOLOv8的智能车视觉循迹系统", award_grade="一等奖",
         summary="使用YOLOv8做车道线与障碍物检测，STM32控制底盘完成循迹。",
         highlights="实时性好，边缘端部署", tech_stack=["YOLOv8", "OpenCV", "STM32"],
         review_status="approved"),
    dict(competition_raw="全国大学生智能汽车竞赛", category="人工智能", level="national",
         year=2022, title="智能车视觉识别与路径规划", award_grade="二等奖",
         summary="基于传统图像处理的赛道识别，配合A*路径规划。",
         tech_stack=["OpenCV", "Python"], review_status="approved"),
    dict(competition_raw="中国大学生计算机设计大赛", category="软件开发", level="national",
         year=2023, title="校园二手交易小程序", award_grade="一等奖",
         summary="微信小程序 + SpringBoot，校园闲置物品交易与撮合。",
         tech_stack=["SpringBoot", "微信小程序"], review_status="approved"),
    dict(competition_raw="蓝桥杯", category="程序设计", level="provincial",
         year=2021, title="蓝桥杯算法训练辅助平台", award_grade="三等奖",
         summary="面向算法竞赛的刷题与错题本平台。",
         tech_stack=["Vue", "Flask"], review_status="approved"),
    dict(competition_raw="全国大学生智能汽车竞赛", category="人工智能", level="national",
         year=2024, title="智能车多传感器融合定位", award_grade="一等奖",
         summary="融合IMU与视觉的定位方案。",
         tech_stack=["ROS", "C++"], review_status="pending"),  # 未审核，应被过滤
]


def seed():
    with kb.conn_ctx() as conn:
        for d in SEEDS:
            data = kb._prepare_award(dict(d))
            cols = ",".join(data.keys())
            qs = ",".join("?" * len(data))
            conn.execute(f"INSERT INTO awards ({cols}) VALUES ({qs})", list(data.values()))
    return kb.query("SELECT id FROM awards ORDER BY id")


def main():
    print("=" * 64)
    print("S1 检索内核自测")
    print(f"临时目录: {TMP}")
    print("=" * 64)

    # 0. 建表
    print("\n[0] 初始化表结构")
    info = kb.init_kb()
    check("init_kb 成功", isinstance(info, dict), str(info))
    check("WAL 已开启", kb.get_conn().execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal")

    # 1. 造数据
    print("\n[1] 造 5 条 awards（1 条 pending）")
    rows = seed()
    check("插入 5 条", len(rows) == 5, str(len(rows)))

    # 2. 同步索引（仅 approved）
    print("\n[2] SQLite -> Chroma 同步")
    res = retriever.sync_awards_to_chroma(rebuild=True)
    check("同步 4 条 approved", res["synced"] == 4, str(res))
    check("索引条数 = 4", retriever.count_indexed() == 4, str(retriever.count_indexed()))
    check("embedding_state 已置 ok",
          kb.query("SELECT COUNT(*) c FROM awards WHERE embedding_state='ok'")[0]["c"] == 4)

    # 3. 基础检索
    print("\n[3] 两级检索（无过滤）")
    hits = retriever.retrieve("智能车 视觉识别", top_k=3, with_debug=True)
    check("返回 3 条", len(hits) == 3, str(len(hits)))
    check("结果按 final_score 降序",
          all(hits[i]["final_score"] >= hits[i + 1]["final_score"] for i in range(len(hits) - 1)))
    check("含 final_score / bonus / l1_count",
          all(k in hits[0] for k in ("final_score", "bonus", "l1_count")))
    check("pending 记录未被召回",
          all(h["award_id"] != rows[4]["id"] for h in hits))
    print("    top1:", hits[0]["title"], "| score", hits[0]["score"], "->", hits[0]["final_score"])

    # 4. 结构化过滤（Chroma where + L2 加成）
    print("\n[4] 结构化过滤")
    only_ai = retriever.retrieve("平台", top_k=5, filters={"category": "人工智能"})
    check("category=人工智能 只返回人工智能",
          len(only_ai) > 0 and all(h["category"] == "人工智能" for h in only_ai), str(only_ai))
    check("过滤命中产生 bonus",
          any(h["bonus"] > 0 for h in only_ai))

    y2022 = retriever.retrieve("智能车", top_k=5, filters={"year_from": 2022, "year_to": 2022})
    check("year 范围过滤生效",
          all(h["year"] == 2022 for h in y2022) and len(y2022) >= 1, str(y2022))

    prov = retriever.retrieve("算法", top_k=5, filters={"level": "provincial"})
    check("level=provincial 只返回省级",
          len(prov) >= 1 and all(h["level"] == "provincial" for h in prov))

    # 5. 边界
    print("\n[5] 边界场景")
    check("空查询返回 []", retriever.retrieve("   ", top_k=5) == [])
    check("top_k=1 只返回 1 条", len(retriever.retrieve("智能车", top_k=1)) == 1)
    many = retriever.retrieve("智能车", top_k=99)
    check("top_k 超量不报错且不超索引数", len(many) <= retriever.count_indexed())

    # 6. 真值变更后 L2 降级（把一条改回 pending）
    print("\n[6] L2 以 SQLite 为准（真值变 pending 应被丢弃）")
    victim = hits[0]["award_id"]
    kb.update("awards", victim, {"review_status": "pending"})
    after = retriever.retrieve("智能车 视觉识别", top_k=4)
    check("改 pending 后不再返回该条", all(h["award_id"] != victim for h in after))
    kb.update("awards", victim, {"review_status": "approved"})

    # 7. 重建索引
    print("\n[7] 索引重建")
    retriever.reset_index()
    check("reset 后索引为 0", retriever.count_indexed() == 0)
    check("空索引检索返回 []", retriever.retrieve("智能车", top_k=3) == [])
    res2 = retriever.sync_awards_to_chroma()
    check("重建后索引 = 4", res2["indexed"] == 4, str(res2))

    # 8. 统计
    print("\n[8] stats()")
    st = retriever.stats()
    check("stats 字段齐全",
          all(k in st for k in ("chroma_dir", "collection", "indexed", "embedder")))
    check("embedder backend = st", st["embedder"]["backend"] == "st")

    print("\n" + "=" * 64)
    print(f"结果: PASS={_PASS}  FAIL={_FAIL}")
    print("=" * 64)
    return 0 if _FAIL == 0 else 1


if __name__ == "__main__":
    try:
        code = main()
    finally:
        shutil.rmtree(TMP, ignore_errors=True)
    sys.exit(code)
