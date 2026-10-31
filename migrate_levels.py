# -*- coding: utf-8 -*-
"""
迁移脚本：为赛事补充级别字段 + 插入 8 条省级/区域级赛事
- 现有 22 条全部标注 level='national'
- 插入 8 条 level='provincial' 的省级/区域赛事
可重复执行：现有条目的级别标注是幂等的；省级条目按名称去重插入。
"""
import sys, io
sys.stdout.reconfigure(encoding="utf-8")
import db

# ---------- 1. 现有 22 条统一标注为国家级 ----------
conn = db.get_conn()
try:
    cur = conn.execute(
        "UPDATE competitions SET level='national' "
        "WHERE level IS NULL OR level = ''"
    )
    conn.commit()
    print(f"[1] 标注国家级: {cur.rowcount} 条")
finally:
    conn.close()

# ---------- 2. 待插入的 8 条省级/区域级赛事 ----------
PROVINCIAL = [
    # name, category, start, end, cross_year, level_label
    ("全国大学生计算机设计大赛·省级赛",       "计算机综合与软件", 3,  5,  0, "省级"),
    ("中国高校计算机大赛·省级选拔赛",         "计算机综合与软件", 3,  4,  0, "省级"),
    ("全国大学生软件测试大赛·省赛",           "计算机综合与软件", 9, 10,  0, "省级"),
    ("全国大学生信息安全竞赛·省级赛区选拔赛",  "安全与人工智能",   4,  5,  0, "省级"),
    ("全国大学生物联网设计竞赛·华东赛区",      "物联网/嵌入式/ICT", 4,  6,  0, "区域级"),
    ("“蓝桥杯”全国软件大赛·省赛",            "程序设计",        10, 12,  0, "省级"),
    ("中国大学生服务外包创新创业大赛·省赛",    "创新创业/软件服务", 2,  3,  0, "区域赛"),
    ("“挑战杯”省级大学生课外学术科技作品竞赛",  "创新创业",         3,  5,  0, "省级"),
]

existing_names = {r["name"] for r in db.list_competitions()}
added, skipped = 0, 0
for name, cat, s, e, x, label in PROVINCIAL:
    if name in existing_names:
        print(f"    skip(已存在): {name}")
        skipped += 1
        continue
    db.add_competition({
        "name": name,
        "category": cat,
        "reg_start_month": s,
        "reg_end_month": e,
        "reg_cross_year": x,
        "official_url": None,
        "level": "provincial",
        "level_label": label,
    })
    added += 1

print(f"[2] 省级赛事新增: {added} 条, 跳过: {skipped} 条")
print(f"[3] 当前总数: {len(db.list_competitions())} 条")
