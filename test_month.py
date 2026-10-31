"""_month_in_range 单元测试：不碰数据库，纯逻辑验证。"""
import json
from db import _month_in_range

# (month, start, end, cross, expected, 描述)
cases = [
    # ---- 不跨年 ----
    (5, 5, 8, 0, True,  "5月区间[5-8]，查5月(边界起)"),
    (8, 5, 8, 0, True,  "5月区间[5-8]，查8月(边界止)"),
    (6, 5, 8, 0, True,  "5月区间[5-8]，查6月(中间)"),
    (4, 5, 8, 0, False, "5月区间[5-8]，查4月(外)"),
    (9, 5, 8, 0, False, "5月区间[5-8]，查9月(外)"),
    (10, 10, 10, 0, True, "单月区间[10-10]，查10月"),
    (11, 10, 10, 0, False, "单月区间[10-10]，查11月"),
    (12, 10, 12, 0, True, "区间[10-12]，查12月(边界止)"),

    # ---- 跨年 [5..12] ∪ [1..3] ----
    (5, 5, 3, 1, True,  "跨年[5月→次年3月]，查5月(边界起)"),
    (12, 5, 3, 1, True, "跨年[5月→次年3月]，查12月(上半年段)"),
    (8, 5, 3, 1, True,  "跨年[5月→次年3月]，查8月(中间)"),
    (1, 5, 3, 1, True,  "跨年[5月→次年3月]，查次年1月"),
    (3, 5, 3, 1, True,  "跨年[5月→次年3月]，查次年3月(边界止)"),
    (4, 5, 3, 1, False, "跨年[5月→次年3月]，查4月(不在区间)"),

    # ---- 跨年 12月→次年2月 ----
    (12, 12, 2, 1, True,  "跨年[12月→次年2月]，查12月"),
    (1, 12, 2, 1, True,  "跨年[12月→次年2月]，查次年1月"),
    (2, 12, 2, 1, True,  "跨年[12月→次年2月]，查次年2月"),
    (11, 12, 2, 1, False, "跨年[12月→次年2月]，查11月(外)"),
    (3, 12, 2, 1, False, "跨年[12月→次年2月]，查3月(外)"),
]

results = []
passed = 0
failed = 0
for m, s, e, c, exp, desc in cases:
    got = _month_in_range(m, s, e, c)
    ok = (got == exp)
    passed += ok
    failed += (not ok)
    results.append({
        "desc": desc, "month": m, "range": f"{s}-{e}", "cross": c,
        "expected": exp, "got": got, "pass": ok
    })

summary = {"total": len(cases), "passed": passed, "failed": failed, "detail": results}
json.dump(summary, open("_test_result.json", "w", encoding="utf-8"), ensure_ascii=False, indent=2)
print(f"TOTAL={len(cases)} PASSED={passed} FAILED={failed}")
