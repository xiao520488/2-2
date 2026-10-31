import io, sys, re
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
from streamlit.testing.v1 import AppTest

at = AppTest.from_file("app.py", default_timeout=30)
at.run()
assert not at.exception, at.exception

# 切到 报名时间轴
at.sidebar.radio[0].set_value("报名时间轴").run()
assert not at.exception, at.exception
print("timeline page OK; subheaders:", [s.value for s in at.subheader])

# 切回 竞赛列表，校验卡片正常渲染
at.sidebar.radio[0].set_value("竞赛列表").run()
assert not at.exception, at.exception
cards = 0
for el in at.markdown:
    if re.search(r'<div class="comp-card(?![-\w])', el.value):
        cards += 1
print("list page OK; cards:", cards)
assert cards > 0, "列表页未渲染任何卡片"

print("ALL PAGES OK")
