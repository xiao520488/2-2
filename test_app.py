import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

# 不启动 streamlit，仅 import 模块并测纯函数
import app

tests = []
def check(name, cond):
    tests.append((name, cond))
    print(("PASS " if cond else "FAIL ") + name)

check("cross_label True", app.cross_label(True) == "跨年(次年)")
check("cross_label False", app.cross_label(False) == "同年")
check("month_range same", app.month_range_text(3, 5, 0) == "3月 ~ 5月")
check("month_range cross", app.month_range_text(11, 2, 1) == "11月 ~ 2月（跨年）")
check("month_range empty", app.month_range_text(None, None, 0) == "")
check("esc", app.esc('<a>&"') == "&lt;a&gt;&amp;&quot;")
check("MONTHS", app.MONTHS == list(range(1, 13)))
check("per_page", app.CARDS_PER_PAGE == 6)

print("TOTAL", sum(1 for _, c in tests if c), "/", len(tests))
