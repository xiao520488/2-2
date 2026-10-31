"""
比赛信息管理系统 - 独立 HTTP 后端 (api.py)

注意：本文件是【可选】的独立后端。Streamlit 前端(app.py)并不依赖它，
      前端是直接调用 db.py 的函数。仅当需要给 index.html 之类的外部页面
      提供 REST API 时，才单独启动本服务：

          python api.py              # 默认 http://127.0.0.1:8000
          python api.py --port 8801

技术选型：仅用 Python 标准库 http.server，零新增依赖。
职责：
  1) 托管前端静态资源（index.html、static/bg.mp4 等）
  2) 提供 REST API，全部复用 db.py 的接口，不重复写 SQL

API 一览：
  GET    /api/competitions?category=&month=&keyword=   列表（组合筛选）
  GET    /api/categories                               类别去重（下拉框）
  GET    /api/timeline?month=1-12                      该月报名/比赛时间轴
  POST   /api/competitions                            新增（JSON body）
  PUT    /api/competitions/<id>                       更新（JSON body，部分字段）
  DELETE /api/competitions/<id>                       删除
"""

import json
import os
import re
import sys
import argparse
import mimetypes
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

import db

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")

# 允许写入的字段（与 schema.sql 一致）
WRITABLE_FIELDS = (
    "name", "category", "reg_start_month", "reg_end_month",
    "reg_cross_year", "official_url", "level", "sort_order",
    "intro",
)

VALID_LEVELS = ("national", "provincial")


# ============================================================
# 工具函数
# ============================================================

def _parse_int(value, field_name):
    """把查询参数转成 int，非法则抛 ValueError。"""
    try:
        return int(value)
    except (TypeError, ValueError):
        raise ValueError(f"参数 {field_name} 必须是整数，收到: {value!r}")


def _clean_payload(body: dict) -> dict:
    """从请求体里挑出可写字段，做基础类型/范围校验。"""
    data = {}
    for k in WRITABLE_FIELDS:
        if k not in body:
            continue
        v = body[k]
        if k in ("reg_start_month", "reg_end_month"):
            v = _parse_int(v, k)
            if not 1 <= v <= 12:
                raise ValueError(f"{k} 必须在 1-12 之间，收到: {v}")
        elif k == "reg_cross_year":
            v = _parse_int(v, k)
            if v not in (0, 1):
                raise ValueError(f"reg_cross_year 只能是 0 或 1，收到: {v}")
        elif k == "name":
            if not isinstance(v, str) or not v.strip():
                raise ValueError("name 不能为空")
            v = v.strip()
        elif k == "category":
            v = (v or "").strip()
        elif k == "official_url":
            v = (v or "").strip()
        elif k == "level":
            v = (v or "national").strip()
            if v not in VALID_LEVELS:
                raise ValueError(
                    f"level 只能是 {' / '.join(VALID_LEVELS)}，收到: {v}"
                )
        elif k == "sort_order":
            v = _parse_int(v, k)
        data[k] = v
    return data


# ============================================================
# 路由实现：返回 (status_code, payload_dict)
# ============================================================

def api_list_competitions(query: dict):
    category = (query.get("category") or [None])[0]
    keyword = (query.get("keyword") or [None])[0]
    raw_month = (query.get("month") or [None])[0]
    month = None
    if raw_month not in (None, "", "all"):
        month = _parse_int(raw_month, "month")
        if not 1 <= month <= 12:
            raise ValueError(f"month 必须在 1-12 之间，收到: {month}")

    items = db.list_competitions(category=category, month=month, keyword=keyword)
    return 200, {"ok": True, "count": len(items), "items": items}


def api_categories(_query):
    cats = db.get_categories()
    return 200, {"ok": True, "items": cats}


def api_timeline(query: dict):
    raw_month = (query.get("month") or [None])[0]
    if raw_month in (None, "", "all"):
        raise ValueError("缺少必填参数 month (1-12)")
    month = _parse_int(raw_month, "month")
    if not 1 <= month <= 12:
        raise ValueError(f"month 必须在 1-12 之间，收到: {month}")
    data = db.get_month_timeline(month)
    return 200, {"ok": True, **data}


def api_create(body: dict):
    data = _clean_payload(body)
    if "name" not in data:
        raise ValueError("缺少必填字段 name")
    new_id = db.add_competition(data)
    return 201, {"ok": True, "id": new_id, "item": db.get_competition(new_id)}


def api_update(cid: int, body: dict):
    if db.get_competition(cid) is None:
        return 404, {"ok": False, "error": f"比赛 id={cid} 不存在"}
    data = _clean_payload(body)
    if not data:
        raise ValueError("没有可更新的字段")
    ok = db.update_competition(cid, data)
    return 200, {"ok": bool(ok), "item": db.get_competition(cid)}


def api_delete(cid: int):
    if db.get_competition(cid) is None:
        return 404, {"ok": False, "error": f"比赛 id={cid} 不存在"}
    ok = db.delete_competition(cid)
    return 200, {"ok": bool(ok), "id": cid}


# ============================================================
# 请求处理器
# ============================================================

class Handler(BaseHTTPRequestHandler):
    server_version = "CompetitionAPI/1.0"

    # ---------- 输出工具 ----------
    def _send_json(self, status: int, payload: dict):
        raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(raw)

    def _send_file(self, filepath: str):
        if not os.path.isfile(filepath):
            self._send_json(404, {"ok": False, "error": "文件不存在"})
            return
        ctype, _ = mimetypes.guess_type(filepath)
        ctype = ctype or "application/octet-stream"
        size = os.path.getsize(filepath)
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(size))
        self.end_headers()
        with open(filepath, "rb") as f:
            while True:
                chunk = f.read(64 * 1024)
                if not chunk:
                    break
                self.wfile.write(chunk)

    def _read_json_body(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            return {}
        raw = self.rfile.read(length).decode("utf-8")
        if not raw.strip():
            return {}
        try:
            body = json.loads(raw)
        except json.JSONDecodeError as e:
            raise ValueError(f"请求体不是合法 JSON: {e}")
        if not isinstance(body, dict):
            raise ValueError("请求体必须是 JSON 对象")
        return body

    # ---------- 静态资源 ----------
    def _serve_static(self, path: str):
        if path in ("/", ""):
            path = "/index.html"
        # 防目录穿越
        rel = path.lstrip("/")
        target = os.path.normpath(os.path.join(BASE_DIR, rel))
        if not target.startswith(BASE_DIR):
            self._send_json(403, {"ok": False, "error": "非法路径"})
            return
        self._send_file(target)

    # ---------- 统一错误包装 ----------
    def _dispatch(self, fn, *args):
        try:
            return fn(*args)
        except ValueError as e:
            return 400, {"ok": False, "error": str(e)}
        except Exception as e:  # noqa: BLE001
            return 500, {"ok": False, "error": f"{type(e).__name__}: {e}"}

    # ---------- HTTP 方法 ----------
    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)

        if path == "/api/competitions":
            status, payload = self._dispatch(api_list_competitions, query)
            self._send_json(status, payload)
        elif path == "/api/categories":
            status, payload = self._dispatch(api_categories, query)
            self._send_json(status, payload)
        elif path == "/api/timeline":
            status, payload = self._dispatch(api_timeline, query)
            self._send_json(status, payload)
        elif path.startswith("/api/"):
            self._send_json(404, {"ok": False, "error": f"未知接口 {path}"})
        else:
            self._serve_static(path)

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/competitions":
            try:
                body = self._read_json_body()
            except ValueError as e:
                self._send_json(400, {"ok": False, "error": str(e)})
                return
            status, payload = self._dispatch(api_create, body)
            self._send_json(status, payload)
        else:
            self._send_json(404, {"ok": False, "error": f"未知接口 {parsed.path}"})

    def do_PUT(self):
        parsed = urlparse(self.path)
        m = re.fullmatch(r"/api/competitions/(\d+)", parsed.path)
        if not m:
            self._send_json(404, {"ok": False, "error": f"未知接口 {parsed.path}"})
            return
        cid = int(m.group(1))
        try:
            body = self._read_json_body()
        except ValueError as e:
            self._send_json(400, {"ok": False, "error": str(e)})
            return
        status, payload = self._dispatch(api_update, cid, body)
        self._send_json(status, payload)

    def do_DELETE(self):
        parsed = urlparse(self.path)
        m = re.fullmatch(r"/api/competitions/(\d+)", parsed.path)
        if not m:
            self._send_json(404, {"ok": False, "error": f"未知接口 {parsed.path}"})
            return
        status, payload = self._dispatch(api_delete, int(m.group(1)))
        self._send_json(status, payload)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,PUT,DELETE,OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def log_message(self, fmt, *args):
        sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))


def main():
    parser = argparse.ArgumentParser(description="比赛信息管理系统后端")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()

    db.init_db()  # 确保表存在（幂等）
    httpd = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"服务已启动: http://{args.host}:{args.port}/")
    print(f"API 示例:   http://{args.host}:{args.port}/api/competitions")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止")
    finally:
        httpd.server_close()


if __name__ == "__main__":
    main()
