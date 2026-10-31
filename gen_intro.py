"""
批量生成比赛「一句话简介」并写回 competitions.intro。

设计要点：
- 风格 B：参赛安利型，面向"要不要去参加"的读者，突出看点与适合人群。
- 长度：<= 60 字（中文字符计），超出则重试一次。
- 保守事实边界：只允许使用库内已有字段（name / category / level / level_label /
  报名月份区间 / 是否跨年），严禁编造主办方、具体日期、获奖率、含金量排名等事实。
- 幂等：默认跳过已有 intro 的记录；--force 可强制全部重生成；--only-id 可指定单条。
- 失败不写入：任何一条校验不过就记入失败清单，不影响其他记录。

用法：
    python gen_intro.py                 # 为所有 intro 为空的记录生成
    python gen_intro.py --force         # 全部重新生成
    python gen_intro.py --only-id 12    # 只生成 id=12
    python gen_intro.py --dry-run       # 只打印，不写库
"""

import argparse
import os
import re
import sys
import time

from dotenv import load_dotenv
from openai import OpenAI

import db

load_dotenv()

MAX_LEN = 60          # 简介最大字数
MAX_RETRY = 1         # 超长/不合规时的重试次数
MODEL = "deepseek-chat"
BASE_URL = "https://api.deepseek.com"


def build_client() -> OpenAI:
    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        raise RuntimeError("未找到 DEEPSEEK_API_KEY，请检查 .env 文件")
    return OpenAI(api_key=api_key, base_url=BASE_URL)


def month_range_text(comp: dict) -> str:
    """把月份区间转成人话，如 '4月-5月' / '12月-次年1月'。"""
    s, e = comp.get("reg_start_month"), comp.get("reg_end_month")
    if not s or not e:
        return "时间未标注"
    if comp.get("reg_cross_year"):
        return f"{s}月-次年{e}月"
    return f"{s}月-{e}月"


SYSTEM_PROMPT = (
    "你是一名高校竞赛科普编辑，擅长用一两句话告诉同学'这个比赛值不值得报名'。"
    "你的文字务实、具体、不夸张。"
)

USER_TMPL = """请为下面这个竞赛写一句「参赛安利型」简介。

【可用信息（这是你唯一可以依据的事实）】
- 竞赛名称：{name}
- 类别：{category}
- 级别：{level_label}
- 报名时段：{months}

【写作要求】
1. 一句话，不超过 {max_len} 个汉字，不要换行。
2. 语气是"向同学安利"：点出这个比赛大概考什么方向、适合什么样的同学参与。
3. 严格只用上面给出的信息。禁止编造主办方、具体比赛日期、获奖比例、含金量排名、
   保研加分政策等你不知道的事实。
4. 不要复述竞赛的全名（读者在标题已经看到了），不要用"该赛事""此竞赛"开头。
5. 不要使用引号包裹整句，不要加"简介："之类前缀。
6. 只输出这一句话，不要任何解释。

【风格示例（仅示范语气，内容与本竞赛无关）】
算法方向的同学可以把这里当成一次限时编码的实战演习，报名在春季。"""


def clean(text: str) -> str:
    """清理模型输出：去空白、去包裹引号、去前缀。"""
    t = (text or "").strip()
    t = t.replace("\n", "").replace("\r", "")
    t = re.sub(r"^(简介|一句话简介)[:：]\s*", "", t)
    t = t.strip().strip("“”\"'‘’「」")
    return t.strip()


def validate(intro: str, comp: dict) -> tuple[bool, str]:
    """返回 (是否通过, 原因)。"""
    if not intro:
        return False, "内容为空"
    # 长度按中文字符口径：去掉空格后计
    length = len(intro.replace(" ", ""))
    if length > MAX_LEN:
        return False, f"超长 {length} 字 (> {MAX_LEN})"
    # 事实边界：不允许出现具体数字型断言（如百分比、年份、届数）
    if re.search(r"\d+\s*%", intro):
        return False, "出现百分比等未授权数据"
    if re.search(r"(19|20)\d{2}\s*年", intro):
        return False, "出现具体年份"
    if re.search(r"第\s*\d+\s*届", intro):
        return False, "出现具体届数"
    return True, "ok"


def gen_one(client: OpenAI, comp: dict) -> tuple[str | None, str]:
    """为单条记录生成简介。返回 (intro 或 None, 说明)。"""
    prompt = USER_TMPL.format(
        name=comp["name"],
        category=comp.get("category") or "未分类",
        level_label=comp.get("level_label") or ("国家级" if comp.get("level") == "national" else "省级"),
        months=month_range_text(comp),
        max_len=MAX_LEN,
    )
    last_reason = ""
    for attempt in range(MAX_RETRY + 1):
        try:
            resp = client.chat.completions.create(
                model=MODEL,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.7,
                max_tokens=160,
            )
            raw = resp.choices[0].message.content or ""
        except Exception as e:  # 网络/接口异常，直接失败，不重试过久
            return None, f"调用异常：{e}"

        intro = clean(raw)
        ok, reason = validate(intro, comp)
        if ok:
            return intro, "ok" if attempt == 0 else f"ok(第{attempt + 1}次)"
        last_reason = reason
        # 超长时在提示词里追加收紧要求再试
        prompt = prompt + f"\n\n【重要】上次输出{reason}，请显著缩短，务必不超过 {MAX_LEN} 字。"

    return None, last_reason


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true", help="覆盖已有 intro")
    parser.add_argument("--only-id", type=int, default=None, help="只处理指定 id")
    parser.add_argument("--dry-run", action="store_true", help="只打印不写库")
    args = parser.parse_args()

    db.init_db()
    comps = db.list_competitions()

    if args.only_id is not None:
        comps = [c for c in comps if c["id"] == args.only_id]
        if not comps:
            print(f"未找到 id={args.only_id} 的记录")
            return
    if not args.force and args.only_id is None:
        comps = [c for c in comps if not c.get("intro")]

    if not comps:
        print("没有需要生成的记录（可用 --force 强制重生成）")
        return

    client = build_client()
    ok_count = fail_count = 0
    failures = []

    for i, comp in enumerate(comps, 1):
        intro, note = gen_one(client, comp)
        tag = f"[{i}/{len(comps)}] id={comp['id']} {comp['name']}"
        if intro is None:
            fail_count += 1
            failures.append((comp["id"], comp["name"], note))
            print(f"{tag}  ✗ {note}")
        else:
            ok_count += 1
            print(f"{tag}\n    → ({len(intro)}字) {intro}  [{note}]")
            if not args.dry_run:
                db.update_competition(comp["id"], {"intro": intro})
        time.sleep(0.3)  # 轻微限速，避免触发频控

    print("\n" + "=" * 60)
    print(f"完成：成功 {ok_count} 条，失败 {fail_count} 条")
    if failures:
        print("失败清单：")
        for fid, fname, freason in failures:
            print(f"  - id={fid} {fname}：{freason}")
    if args.dry_run:
        print("（dry-run 模式，未写入数据库）")


if __name__ == "__main__":
    main()
