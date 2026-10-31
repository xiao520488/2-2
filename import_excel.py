# -*- coding: utf-8 -*-
"""把 计算机类竞赛.xlsx 导入 competitions 表。

字段映射：
  竞赛名称     -> name
  报名开始月   -> reg_start_month
  报名结束月   -> reg_end_month
  官网链接     -> official_url
  类别         -> category
  序号         -> 丢弃

特殊处理：
  - 结束月写成「次年X月」的，视为跨年，reg_cross_year=1，结束月取 X。
  - 月份无法解析（如「未明确」）的记录默认跳过。
"""
import json
import re

import openpyxl

import db

XLSX = 'D:/agent-lab/3/计算机类竞赛.xlsx'


def parse_month(text):
    """'5月' -> 5；'次年3月' -> (3, True)；解析失败 -> (None, False)"""
    if text is None:
        return None, False
    s = str(text).strip()
    cross = '次年' in s
    m = re.search(r'(\d{1,2})', s)
    if not m:
        return None, False
    month = int(m.group(1))
    if not (1 <= month <= 12):
        return None, False
    return month, cross


def load_rows():
    wb = openpyxl.load_workbook(XLSX)
    ws = wb.active
    rows = [list(r) for r in ws.iter_rows(values_only=True)]
    header, body = rows[0], rows[1:]

    records, skipped = [], []
    for r in body:
        if r[1] is None:
            continue
        name = str(r[1]).strip()
        start, _ = parse_month(r[2])
        end, end_cross = parse_month(r[3])
        url = (str(r[4]).strip() if r[4] else '')
        category = (str(r[5]).strip() if r[5] else '')

        if start is None or end is None:
            skipped.append({'name': name, 'raw_start': r[2], 'raw_end': r[3]})
            continue

        # 跨年：结束月标了「次年」，或起始月 > 结束月
        cross_year = 1 if (end_cross or start > end) else 0
        records.append({
            'name': name,
            'category': category,
            'reg_start_month': start,
            'reg_end_month': end,
            'reg_cross_year': cross_year,
            'official_url': url,
        })
    return header, records, skipped


def main():
    db.init_db()
    header, records, skipped = load_rows()

    # 清空旧数据 + 逐条插入，放在同一个事务里：
    # 任何一条插入失败都会整体回滚，保留导入前的原始数据，避免"中途失败丢数据"。
    conn = db.get_conn()
    try:
        conn.execute('DELETE FROM competitions')
        conn.execute("DELETE FROM sqlite_sequence WHERE name='competitions'")
        insert_sql = (
            "INSERT INTO competitions "
            "(name, category, reg_start_month, reg_end_month, reg_cross_year, official_url) "
            "VALUES (?, ?, ?, ?, ?, ?)"
        )
        for rec in records:
            conn.execute(insert_sql, (
                rec.get('name'),
                rec.get('category'),
                rec.get('reg_start_month'),
                rec.get('reg_end_month'),
                1 if rec.get('reg_cross_year') else 0,
                rec.get('official_url'),
            ))
        conn.commit()
    except Exception as e:
        conn.rollback()
        conn.close()
        print('导入失败，已回滚，原数据保持不变:', e)
        raise
    finally:
        try:
            conn.close()
        except Exception:
            pass

    total = len(db.list_competitions())
    cross = [c for c in db.list_competitions() if c['reg_cross_year']]
    dec = db.get_registering_by_month(12)

    result = {
        'imported': len(records),
        'skipped': skipped,
        'total_in_db': total,
        'cross_year_records': [{'name': c['name'],
                                'range': f"{c['reg_start_month']}-{c['reg_end_month']}"}
                               for c in cross],
        'december_registering': [c['name'] for c in dec],
        'categories': sorted({c['category'] for c in db.list_competitions()}),
    }
    with open('D:/agent-lab/3/_import_result.json', 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=1)
    print('imported', len(records))


if __name__ == '__main__':
    main()
