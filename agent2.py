import os
import json
import subprocess
from openai import OpenAI
from dotenv import load_dotenv

# ================= 环境变量 =================
load_dotenv() 
client = OpenAI(
    api_key=os.environ.get("DEEPSEEK_API_KEY"), 
    base_url="https://api.deepseek.com/v1"
)

# ================= 上下文压缩配置 =================
MAX_CONTEXT_CHARS = 50000  
KEEP_RECENT_MESSAGES = 6   
MAX_TOOL_OUTPUT_LEN = 2000 

# ================= 3 个本地工具 =================
def run_bash(cmd: str) -> str:
    try:
        # 【修复核心】：强制指定 encoding='utf-8'，并且加上 errors='replace' 防止乱码导致崩溃
        result = subprocess.run(
            cmd, 
            shell=True, 
            capture_output=True, 
            text=True, 
            encoding="utf-8", 
            errors="replace", 
            timeout=20
        )
        return f"标准输出:\\n{result.stdout}\\n错误输出:\\n{result.stderr}"
    except subprocess.TimeoutExpired:
        return "执行超时（超过20秒）。如果是启动web服务，请交由用户自己运行。"
    except Exception as e:
        return f"执行出错: {e}"

def read_file(path: str) -> str:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        return f"读取失败: {e}"

def write_file(path: str, content: str) -> str:
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        return f"成功写入文件: {path}"
    except Exception as e:
        return f"写入失败: {e}"

tools = [
    {"type": "function", "function": {"name": "run_bash", "description": "执行终端命令并返回输出", "parameters": {"type": "object", "properties": {"cmd": {"type": "string", "description": "要执行的命令"}}, "required": ["cmd"]}}},
    {"type": "function", "function": {"name": "read_file", "description": "读取指定路径的文件内容", "parameters": {"type": "object", "properties": {"path": {"type": "string", "description": "文件路径"}}, "required": ["path"]}}},
    {"type": "function", "function": {"name": "write_file", "description": "将内容写入指定路径的文件", "parameters": {"type": "object", "properties": {"path": {"type": "string", "description": "文件路径"}, "content": {"type": "string", "description": "要写入的内容"}}, "required": ["path", "content"]}}}
]

tool_map = {"run_bash": run_bash, "read_file": read_file, "write_file": write_file}

# ================= 核心：上下文压缩函数 =================
def _safe_window_start(messages: list, keep_recent: int) -> int:
    """计算安全窗口起点，保证 messages[start:] 是一个自包含的尾段：
    1. 头消息不能是孤立的 role=tool（必须有对应的 assistant(tool_calls) 在段内）；
    2. 不能把某条 assistant(tool_calls) 和它的 tool 结果切散。
    做法：从目标起点不断向前回退，直到尾段完全自包含。
    """
    n = len(messages)
    start = max(1, n - keep_recent)  # 至少保留 system(索引0)
    # 注意：条件为 start > 0，确保 start==1 时也要校验自包含性
    while start > 0:
        # 到达索引0（system）或越过可用范围，停止回退
        if start >= n:
            return n
        first = messages[start]
        role = first.get("role")
        if role == "tool":
            # 孤立 tool，说明它的 assistant 在更前面；向前扩以纳入配对
            start -= 1
            continue
        if role == "assistant" and first.get("tool_calls"):
            # assistant 带 tool_calls，需确保它每个 tool_call_id 的 tool 响应都在 [start:] 内
            needed = {tc.get("id") for tc in first["tool_calls"]}
            present = {
                m.get("tool_call_id")
                for m in messages[start + 1:]
                if m.get("role") == "tool"
            }
            if needed.issubset(present):
                break  # 自包含，安全
            # 否则该 assistant 的 tool 被切出去了，连同它一起排除，向前扩
            start -= 1
            continue
        break

    # 兜底：若回退到索引1仍是孤立 tool（其 assistant 在 system 之前，根本不存在），
    # 属于脏历史，跳过开头连续的孤立 tool，返回第一个安全位置，保证尾段自包含。
    while start < n and start > 0 and messages[start].get("role") == "tool":
        start += 1

    return start


def compress_messages(messages: list) -> list:
    # 深拷贝一份，避免就地修改调用方传入的原始消息对象
    messages = [dict(m) for m in messages]
    for msg in messages:
        if msg.get("role") == "tool" and len(msg.get("content", "")) > MAX_TOOL_OUTPUT_LEN:
            content = msg["content"]
            half_len = MAX_TOOL_OUTPUT_LEN // 2
            msg["content"] = content[:half_len] + "\n\n... [中间内容已截断] ...\n\n" + content[-half_len:]

    total_chars = sum(len(str(m.get("content", ""))) + len(str(m.get("tool_calls", ""))) for m in messages)
    print(f"📊 [系统检查] 当前上下文长度约: {total_chars} 字符")

    if total_chars < MAX_CONTEXT_CHARS or len(messages) <= KEEP_RECENT_MESSAGES + 2:
        return messages

    print(f"⚠️ [触发压缩] 上下文过长，开始执行全局摘要压缩...")
    system_msg = messages[0]
    split = _safe_window_start(messages, KEEP_RECENT_MESSAGES)
    recent_msgs = messages[split:]
    middle_msgs = messages[1:split]

    summary_prompt = [
        {"role": "system", "content": "请精炼总结以下 AI 与工具之间的交互历史，提取出：1. 已完成的核心文件及代码逻辑；2. 已解决的 Bug；3. 当前进展。请用简短的列表输出。"},
        {"role": "user", "content": f"以下是历史记录：\n{json.dumps(middle_msgs, ensure_ascii=False)}"}
    ]

    try:
        summary_response = client.chat.completions.create(model="deepseek-chat", messages=summary_prompt, temperature=0.3)
        summary_content = summary_response.choices[0].message.content
        new_messages = [system_msg, {"role": "assistant", "content": f"[历史工作日志总结]:\n{summary_content}"}] + recent_msgs
        print(f"✅ [压缩完成] 上下文已压缩。")
        return new_messages
    except Exception as e:
        print(f"❌ [压缩失败] {e}，将使用滑动窗口策略。")
        # 兜底：滑动窗口，同样使用安全窗口起点，避免切散 tool_calls 配对
        safe_start = _safe_window_start(messages, KEEP_RECENT_MESSAGES)
        return [system_msg] + messages[safe_start:]

    
       # ================= 单个任务处理（内部包含工具执行循环） =================
def execute_agent_turn(messages: list, max_rounds: int = 50):
    """处理一次用户输入，允许内部进行多次工具调用，直到模型输出最终文本"""
    for round_num in range(1, max_rounds + 1):
        print(f"\n{'='*20} 思考与执行 第 {round_num} 轮 {'='*20}")
        messages = compress_messages(messages)

        try:
            response = client.chat.completions.create(
                model="deepseek-chat",
                messages=messages,
                tools=tools,
                tool_choice="auto"
            )
            msg = response.choices[0].message
        except Exception as e:
            print(f"❌ 调用模型失败: {e}")
            break

        # 模型没有发起工具调用，说明这一轮回答结束，返回结果给用户
        if not msg.tool_calls:
            print(f"\n🤖 [Agent]:\n{msg.content}")
            messages.append({"role": "assistant", "content": msg.content})
            return messages

       # 模型要调用工具，追加到历史（先转成字典）
        assistant_msg = {
            "role": "assistant",
            "content": msg.content,  # 显式给出，tool_calls 场景下可能为 None
            "tool_calls": [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                }
                for tc in msg.tool_calls
            ],
        }
        messages.append(assistant_msg)

        for tc in msg.tool_calls:
            tool_name = tc.function.name
            args = json.loads(tc.function.arguments)
            
            try:
                result = tool_map[tool_name](**args)
            except Exception as e:
                result = f"执行出错: {e}"

            print(f"🔧 [Trace - 工具调用]: 调用了 `{tool_name}`")
            print(f"📥 [Trace - 传入参数]: {list(args.keys())}") 
            
            messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": str(result)
            })
            
    return messages


# ================= 主程序入口 =================
if __name__ == "__main__":
    print("==== Agent已启动 ====")
    print("提示：你可以先向它提出你的软件设计思路，或者问它建议。输入 'exit' 退出。")
    
    # 【重点修改：把 messages 提出来，作为全局记忆】
    messages = [
        {
            "role": "system", 
            "content": """你是一个经验丰富的全栈软件开发助手。你的任务是通过对话，帮助用户一步一步完成系统的开发。
            

【交互原则】
- 不要自作主张一次性写完所有代码！不要抢跑！
- 请等待用户的指令。用户让你干嘛，你就干嘛。
- 如果用户没有思路，你可以主动提出设计建议。
- 每次写完代码后，主动运行测试（如果有必要），并把结果告诉用户。
- 注意：环境依赖（openai, python-dotenv, streamlit, pandas）已经安装好，无需重复安装。"""
        }
    ]

    while True:
        user_task = input("\n🧑‍💻 你: ")
        if user_task.lower() in ["exit", "quit", "退出"]:
            print("结束对话。")
            break
        if not user_task.strip():
            continue
        
        # 1. 将用户输入加入记忆
        messages.append({"role": "user", "content": user_task})
        
        # 2. 执行 Agent 思考与行动，它会带着之前的记忆，并且会原地更新 messages
        messages = execute_agent_turn(messages)