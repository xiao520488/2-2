# -*- coding: utf-8 -*-
"""
修复后的 test_pagination.py：
1. 卡片现在由 st.html 渲染，需同时扫描 markdown 与 html 两类节点。
2. 只统计真正的卡片 HTML，排除注入全局 CSS 的 <style> markdown 块。
"""
import math
import io
import sys
import re
from streamlit.testing.v1 import AppTest

# 强制 stdout 用 utf-8，避免 Windows GBK 打印中文/箭头报错
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

at = AppTest.from_file("app.py", default_timeout=30)
at.run()
assert not at.exception, at.exception

total = None
for c in at.caption:
    m = re.search(r"共\s*(\d+)\s*条记录", c.value)
    if m:
        total = int(m.group(1))
        break
print("total =", total)
assert total is not None

total_pages = max(1, math.ceil(total / 6))
print("total_pages =", total_pages)

# 卡片开头形如：<div class="comp-card lv-national">，类名后可跟 level 修饰类，
# 因此不写死结尾的 ">"，用正则匹配。
MARK_RE = re.compile(r'<div class="comp-card(?![\w-])')


def card_count(t):
    """统计页面上的卡片数量：兼容 st.markdown 与 st.html 两种渲染方式，
    并排除 <style> 全局 CSS 块（其中只含选择器文本，不含 MARK）。"""
    n = 0
    for attr in ("markdown", "html"):
        for el in getattr(t, attr, []):
            v = getattr(el, "value", "") or ""
            if MARK_RE.search(v):
                n += 1
    return n


def btn(t, label_part):
    for b in t.button:
        if label_part in b.label:
            return b
    raise AssertionError("button not found: " + label_part)


page1_cards = card_count(at)
print("page1 cards =", page1_cards)
assert page1_cards == min(6, total), page1_cards

prev = btn(at, "上一页")
nxt = btn(at, "下一页")
assert prev.disabled is True

if total_pages > 1:
    nxt.click().run()
    assert not at.exception, at.exception
    p2 = card_count(at)
    expected_p2 = min(6, total - 6)
    print("page2 cards =", p2, "expected", expected_p2)
    assert p2 == expected_p2, p2
    assert btn(at, "上一页").disabled is False

    for _ in range(total_pages - 2):
        btn(at, "下一页").click().run()
        assert not at.exception, at.exception
    last_cards = card_count(at)
    expected_last = total - (total_pages - 1) * 6
    print("last page cards =", last_cards, "expected", expected_last)
    assert last_cards == expected_last, last_cards
    assert btn(at, "下一页").disabled is True

    # 再点上一页，验证回退
    btn(at, "上一页").click().run()
    assert not at.exception, at.exception
    print("after prev, cards =", card_count(at))
else:
    assert btn(at, "下一页").disabled is True

print("PAGINATION TEST PASSED")
