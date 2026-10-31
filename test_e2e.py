import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
import db

db.init_db()
allrows = db.list_competitions()
print("TOTAL_ROWS:", len(allrows))
print("CATEGORIES:", db.get_categories()[:6])

if allrows:
    print("SAMPLE_KEYS:", sorted(allrows[0].keys()))
    print("SAMPLE_NAME:", allrows[0].get("name"))
    print("SAMPLE_LEVEL:", allrows[0].get("level"), allrows[0].get("level_label"))

# 月份筛选
for m in (3, 9):
    print("MONTH", m, "->", len(db.list_competitions(month=m)))
# 关键词
cats = db.get_categories()
if cats:
    print("CAT", cats[0], "->", len(db.list_competitions(category=cats[0])))
# 时间轴
tl = db.get_month_timeline(9)
print("TIMELINE 9 keys:", sorted(tl.keys()), "count:", len(tl.get("competitions", [])))
