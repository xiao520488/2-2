"""
LLM 封装 (llm.py) —— DeepSeek（OpenAI 兼容接口）

对外只暴露三个函数：
    chat()        -> 纯文本补全
    chat_json()   -> 强制 JSON 输出，带清洗/修复/重试，返回 dict
    ping()        -> 连通性自检
    LLMError      -> 统一异常

设计要点：
    - 单例 client，复用连接
    - 指数退避重试（网络抖动 / 5xx / 429）
    - 自动累计 token 用量，供 crawl_jobs.cost_token 记录
    - 兼容推理模型（deepseek-flash 等）：reasoning 会占用 completion 额度，
      故当 content 为空但 finish_reason==length 时，自动放大 max_tokens 重试
"""

import json
import os
import re
import time
from typing import Any, Optional

from dotenv import load_dotenv
from openai import OpenAI, APIError, APITimeoutError, RateLimitError

load_dotenv()

# ------------------------------------------------------------
# 配置
# ------------------------------------------------------------
API_KEY = os.getenv("DEEPSEEK_API_KEY", "").strip()
BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com").strip()
MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-chat").strip()

MAX_RETRIES = int(os.getenv("LLM_MAX_RETRIES", "3"))
RETRY_BASE_DELAY = float(os.getenv("LLM_RETRY_BASE_DELAY", "1.5"))
DEFAULT_TIMEOUT = float(os.getenv("LLM_TIMEOUT", "60"))
# 空正文自动扩容上限
MAX_TOKENS_CEILING = int(os.getenv("LLM_MAX_TOKENS_CEILING", "8192"))

_client: Optional[OpenAI] = None

# 累计用量（进程内）
_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "calls": 0}


class LLMError(RuntimeError):
    """LLM 调用失败（配置缺失 / 重试耗尽 / 返回不可用）。"""


class _EmptyContent(LLMError):
    """正文为空但 finish_reason=length 且疑似被推理内容占满 —— 可扩容重试。"""


# ------------------------------------------------------------
# 内部工具
# ------------------------------------------------------------

def _get_client() -> OpenAI:
    global _client
    if _client is None:
        if not API_KEY:
            raise LLMError("缺少 DEEPSEEK_API_KEY，请检查 .env")
        _client = OpenAI(api_key=API_KEY, base_url=BASE_URL, timeout=DEFAULT_TIMEOUT)
    return _client


def _should_retry(exc: Exception) -> bool:
    if isinstance(exc, (APITimeoutError, RateLimitError)):
        return True
    if isinstance(exc, APIError):
        status = getattr(exc, "status_code", None)
        return status is None or status >= 500 or status == 429
    return False


def _accumulate(usage: Any) -> None:
    if usage is None:
        return
    _usage["prompt_tokens"] += getattr(usage, "prompt_tokens", 0) or 0
    _usage["completion_tokens"] += getattr(usage, "completion_tokens", 0) or 0
    _usage["total_tokens"] += getattr(usage, "total_tokens", 0) or 0
    _usage["calls"] += 1


def get_usage() -> dict:
    """返回本次进程累计用量（含 calls 次数），并支持 reset_usage()。"""
    return dict(_usage)


def reset_usage() -> None:
    for k in _usage:
        _usage[k] = 0


def _is_reasoning_model(model: str) -> bool:
    """粗判是否为推理模型（其 completion 额度先产出 reasoning）。"""
    m = (model or "").lower()
    return any(tag in m for tag in ("flash", "reasoner", "-r1", "reasoning"))


def _call(messages: list, *, temperature: float, max_tokens: int,
          response_format: Optional[dict], model: str) -> str:
    """
    底层调用 + 重试。返回文本内容。

    对推理模型特化处理：
        若 content 为空且 finish_reason == 'length'（reasoning 吃光额度），
        将 max_tokens 翻倍后重试，直到 MAX_TOKENS_CEILING。
    """
    client = _get_client()
    last_exc: Optional[Exception] = None
    tokens = max_tokens

    for attempt in range(MAX_RETRIES):
        try:
            kwargs = {
                "model": model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": tokens,
            }
            if response_format:
                kwargs["response_format"] = response_format
            resp = client.chat.completions.create(**kwargs)
            _accumulate(getattr(resp, "usage", None))

            choice = resp.choices[0]
            content = choice.message.content
            if content and content.strip():
                return content

            # 空正文：判断是否为额度耗尽
            if choice.finish_reason == "length" and tokens < MAX_TOKENS_CEILING:
                tokens = min(tokens * 2, MAX_TOKENS_CEILING)
                last_exc = _EmptyContent(
                    f"正文为空(finish_reason=length)，max_tokens 扩容至 {tokens} 重试"
                )
                continue
            raise LLMError("LLM 返回空内容")
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            if attempt == MAX_RETRIES - 1 or not _should_retry(exc):
                break
            time.sleep(RETRY_BASE_DELAY * (2 ** attempt))

    raise LLMError(f"LLM 调用失败（{MAX_RETRIES} 次重试后）: {last_exc}") from last_exc


# ------------------------------------------------------------
# 一、纯文本补全
# ------------------------------------------------------------

def chat(prompt: str, *, system: Optional[str] = None, temperature: float = 0.7,
         max_tokens: int = 2048, model: Optional[str] = None) -> str:
    """
    单轮文本补全。

    参数:
        prompt:       用户输入
        system:       系统提示（可选）
        temperature:  0~2，事实抽取建议 0.1~0.3，创意生成可 0.8~1.0
        max_tokens:   推理模型下会被 reasoning 占用，故默认给足 2048
    返回:
        str 模型回复
    """
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    return _call(messages, temperature=temperature, max_tokens=max_tokens,
                 response_format=None, model=model or MODEL)


# ------------------------------------------------------------
# 二、JSON 输出
# ------------------------------------------------------------

_JSON_DECODER = json.JSONDecoder()


def _extract_json(text: str) -> Any:
    """
    从模型输出中尽力提取 JSON：
        1) 直接 json.loads
        2) 去 ```json 代码围栏
        3) 从第一个 { 或 [ 起 raw_decode（容忍前后废话）
    失败抛 ValueError。
    """
    t = text.strip()

    try:
        return json.loads(t)
    except ValueError:
        pass

    fence = re.search(r"```(?:json)?\s*(.*?)```", t, re.DOTALL | re.IGNORECASE)
    if fence:
        candidate = fence.group(1).strip()
        try:
            return json.loads(candidate)
        except ValueError:
            t = candidate

    for i, ch in enumerate(t):
        if ch in "{[":
            try:
                obj, _ = _JSON_DECODER.raw_decode(t[i:])
                return obj
            except ValueError:
                continue
    raise ValueError("响应中未找到合法 JSON")


def chat_json(prompt: str, *, system: Optional[str] = None, schema_hint: Optional[str] = None,
              temperature: float = 0.2, max_tokens: int = 2048,
              retries: int = 2, model: Optional[str] = None) -> Any:
    """
    强制模型输出 JSON，并解析为 Python 对象。

    参数:
        schema_hint: 期望结构的文字说明（追加到 prompt 末尾，提高稳定性）
        retries:     解析失败后追加纠错提示重问的次数
    返回:
        dict 或 list
    抛出:
        LLMError 若最终仍无法解析
    """
    sys_msg = system or (
        "你是一个严谨的信息抽取引擎。只输出 JSON，不要输出任何解释性文字、"
        "不要使用 Markdown 代码围栏。"
    )
    user_msg = prompt
    if schema_hint:
        user_msg = f"{prompt}\n\n【输出格式要求】\n{schema_hint}"

    messages = [
        {"role": "system", "content": sys_msg},
        {"role": "user", "content": user_msg},
    ]

    last_err: Optional[Exception] = None
    for attempt in range(retries + 1):
        text = _call(messages, temperature=temperature, max_tokens=max_tokens,
                     response_format={"type": "json_object"}, model=model or MODEL)
        try:
            return _extract_json(text)
        except ValueError as exc:
            last_err = exc
            if attempt >= retries:
                break
            messages.append({"role": "assistant", "content": text})
            messages.append({
                "role": "user",
                "content": "上面的输出不是合法 JSON。请只输出合法 JSON，不要任何其它内容。",
            })

    raise LLMError(f"JSON 解析失败: {last_err}")


# ------------------------------------------------------------
# 三、健康检查
# ------------------------------------------------------------

def ping(model: Optional[str] = None) -> dict:
    """
    连通性自检：发一个极小请求，只要求模型回一个字。

    注意：推理模型的 reasoning 会占用 completion 额度，
          故此处 max_tokens 给足 512，而非 16。

    返回 {"ok": bool, "model": str, "latency_ms": int, "error": str|None}
    """
    t0 = time.time()
    m = model or MODEL
    try:
        _get_client()
        chat("请只回复两个字：正常", temperature=0.0, max_tokens=512, model=m)
        return {"ok": True, "model": m,
                "latency_ms": int((time.time() - t0) * 1000), "error": None}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "model": m,
                "latency_ms": int((time.time() - t0) * 1000), "error": str(exc)}


# ------------------------------------------------------------
# 四、流式补全（供前端 st.write_stream 使用）
# ------------------------------------------------------------

def chat_stream(prompt: str, *, system: Optional[str] = None,
                temperature: float = 0.5, max_tokens: int = 2048,
                model: Optional[str] = None):
    """
    流式文本补全：逐段 yield 文本增量。

    用途：Streamlit 里 `st.write_stream(llm.chat_stream(...))` 实时打字机效果。

    参数与 chat() 一致。
    注意：流式不走重试（首包失败直接抛异常，由调用方兜底）。
    """
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    client = _get_client()
    stream = client.chat.completions.create(
        model=model or MODEL,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
        stream=True,
    )
    for chunk in stream:
        try:
            delta = chunk.choices[0].delta
        except (IndexError, AttributeError):
            continue
        piece = getattr(delta, "content", None)
        if piece:
            yield piece


def llm_available() -> bool:
    """
    粗粒度探测：本地配置是否齐备（不发起网络请求，不消耗额度）。

    用于 UI 决定走「真流式」还是「本地检索摘要兜底」。
    真正的网络异常仍由调用方 try/except 兜住。
    """
    return bool(API_KEY)


def llm_config_hint() -> str:
    """给 UI 显示的配置提示，不含密钥明文。"""
    if not API_KEY:
        return "未检测到 DEEPSEEK_API_KEY，将使用本地检索摘要兜底。"
    return f"已配置 {MODEL} @ {BASE_URL}"
