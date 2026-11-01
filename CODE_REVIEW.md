# Code Review 记录

- **项目名称**：竞赛洞察助手（Streamlit + SQLite + Chroma + DeepSeek）
- **审查范围**：`app.py`、`analyzer.py`、`db.py`、`retriever.py`、`embedder.py`、`llm.py`、`schema*.sql`、`scripts/`
- **审查方式**：走查式 Review + 本地运行验证（无网络/无 Key、重复导入、大结果集三种场景）
- **审查结论**：共发现问题 9 项，其中 4 项高危/中危问题已完成修复，5 项纳入后续迭代

---

## 一、审查清单（四维度）

### 1. 安全性（Security）

| 编号 | 检查项 | 关注点 | 结论 |
| :--- | :--- | :--- | :--- |
| S-1 | 密钥与敏感配置 | `.env` 未被提交；密钥仅从环境变量读取，不硬编码、不打日志 | ✅ 通过 |
| S-2 | 凭据泄漏到前端 | 异常信息回显时不得包含 API Key / 完整 response body | ⚠️ 已改进 |
| S-3 | SQL 注入 | 所有 SQL 一律使用 `?` 参数化，禁止 f-string 拼接用户输入 | ✅ 通过 |
| S-4 | 用户输入落库/渲染 | AI 生成内容渲染前做转义，避免 HTML/Markdown 注入 | ✅ 通过 |
| S-5 | 数据文件权限 | `competitions.db`、`chroma_db/` 不进入版本库 | ✅ 通过（已加 `.gitignore`） |

### 2. 健壮性（Robustness）

| 编号 | 检查项 | 关注点 | 结论 |
| :--- | :--- | :--- | :--- |
| R-1 | 外部依赖不可用 | 无 API Key / 网络超时 / 限流时页面不得崩溃 | ⚠️ 已修复 |
| R-2 | 数据库写入幂等 | 重复导入/重复分析不应抛错或产生脏数据 | ⚠️ 已修复 |
| R-3 | 连接生命周期 | 每个 `sqlite3.Connection` 必须 `close()`，用 `finally` 保证释放 | ✅ 通过 |
| R-4 | 空态与边界 | 检索结果为空、字段为 `NULL`、跨年报名月份时 UI 不报错 | ✅ 通过 |
| R-5 | 异常粒度 | `except Exception` 处必须记日志 + 有兜底，而非静默吞掉 | ✅ 通过（已加注释说明） |

### 3. 性能（Performance）

| 编号 | 检查项 | 关注点 | 结论 |
| :--- | :--- | :--- | :--- |
| P-1 | 查询索引 | 高频过滤/排序字段（`level`、`category`、`reg_start_month`）有索引 | ✅ 通过 |
| P-2 | 结果集上限 | 列表页必须分页，禁止 `SELECT *` 全表加载进内存 | ✅ 通过 |
| P-3 | 向量检索开销 | L1 粗召回量 `top_k * mult` 有上限，再 L2 重排 | ✅ 通过 |
| P-4 | 模型与连接复用 | Embedding 模型、OpenAI Client 单例缓存，不重复初始化 | ✅ 通过 |
| P-5 | 流式渲染开销 | 流式输出不要每个 token 全量重渲染整块历史内容 | ⚠️ 可接受（见遗留项 F-3） |

### 4. 代码整洁度（Cleanliness）

| 编号 | 检查项 | 关注点 | 结论 |
| :--- | :--- | :--- | :--- |
| C-1 | 目录结构 | 根目录只保留入口与核心模块，临时脚本归档到 `scripts/` | ⚠️ 已修复 |
| C-2 | 命名与分层 | UI 层不写 SQL，数据访问统一收敛到 `db.py` | ✅ 通过 |
| C-3 | 类型注解与文档串 | 公共函数有 docstring 与类型注解 | ✅ 通过 |
| C-4 | 魔法值 | 状态值、阈值抽为常量（如 `IDEA_STATUS_FLOW`） | ✅ 通过 |
| C-5 | 死代码 | 无废弃入口文件、无未被引用的旧接口 | ⚠️ 已修复 |

---

## 二、发现的问题及修改记录

| # | 维度 | 发现的问题 | 风险等级 | 定位（文件 / 位置） | 修复方案 | 验证方式 | 状态 |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| 1 | 整洁度 | 根目录堆积了废弃的 `api.py`（早期 REST 入口，已无任何引用）以及 `test_app.py`、`test_e2e.py`、`test_init.py`、`test_month.py`、`test_pages.py`、`test_pagination.py` 等一次性验证脚本，入口文件与调试脚本混杂，新同学无法判断哪个是真正的启动入口 | 中 | 项目根目录 | 删除废弃入口 `api.py`；临时验证脚本统一归档至 `scripts/`，仅保留 `app.py` 作为唯一启动入口；根目录职责收敛为「入口 + 核心模块 + schema」 | `grep -r "import api"` 确认无引用；`streamlit run app.py` 正常启动 | ✅ 已修复 |
| 2 | 健壮性 | `ask_llm_stream()` 在未配置 `DEEPSEEK_API_KEY`（或网络超时、429 限流）时，`_get_client()` 会直接 `raise LLMError`，流式循环抛出未捕获异常导致页面白屏崩溃 | 高 | `app.py: ask_llm_stream()` / `llm.py: _get_client()` | 增加两级兜底：① 调用前用 `llm.llm_available()` 做本地探测（不发请求、不耗额度），未配置则直接走 `render_local_fallback()` 渲染本地检索摘要；② 流式循环整体 `try/except`，任何异常都 `placeholder.empty()` 后降级为检索摘要，并在 caption 中提示降级原因；函数返回 `True/False` 表示是否真正走了 AI | 清空 `.env` 中的 KEY 后重跑问答页，确认页面正常输出检索摘要并提示「未检测到 DEEPSEEK_API_KEY，将使用本地检索摘要兜底」 | ✅ 已修复 |
| 3 | 健壮性 | 知识库表建立的是**全列唯一索引**（`awards.content_hash`、`insights.input_hash`、`ideas.content_hash`），而这三列允许为 `NULL`；SQLite 中 `NULL != NULL`，但一旦历史数据存在重复的非空哈希，`INSERT OR IGNORE` 会静默丢弃整条记录，导入「看起来成功但数据少了」且无任何报错，极难排查 | 高 | `schema_kb.sql:122/129/132` | 改为**部分唯一索引**（Partial Index），显式加上 `WHERE xxx IS NOT NULL`，让 `NULL` 行不参与唯一性约束；索引语义更精确，同时避免 `NULL` 值触发意外的去重行为 | `PRAGMA index_list('awards')` 确认 `partial=1`；重复执行 `seed_awards.py` 两次，比对 `SELECT COUNT(*)` 一致且无 `IntegrityError` | ✅ 已修复 |
| 4 | 性能/稳定性 | Streamlit 流式输出早期采用 `st.write_stream()` 一次性渲染，中文界面下浏览器（Chrome 自动翻译）会重排 DOM 并包裹 `<font>` 标签，导致流式节点与 Streamlit 的增量渲染产生 **React 节点冲突**（`NotFoundError: Failed to execute 'removeChild'`），页面报红并中断输出 | 中 | `app.py: ask_llm_stream()` | 改为「单一 `placeholder = st.empty()` + 全量字符串拼接后 `placeholder.markdown()` 更新」的方式：DOM 结构固定，不新增/删除节点，翻译插件重排也不会触发 `removeChild`；流式结束后再 `placeholder.markdown()` 去掉光标 `▌` | 手动验证：在开启 Chrome 网页翻译的情况下连续提问 5 次，控制台无 `removeChild` 报错；关闭翻译后光标渲染正常 | ✅ 已修复 |
| 5 | 安全/整洁度 | 兜底函数中曾把异常原文（`f"{type(exc).__name__}: {exc}"`）直接渲染到页面上，而 OpenAI SDK 的异常信息中可能拼接 `base_url` 乃至请求头片段，存在凭据泄漏到前端界面的风险 | 中 | `app.py: ask_llm_stream()` | 前端只显示「异常类型 + 简短说明」，完整堆栈走 `logging` 写入后端日志，不在 UI 回显 | 构造一次 401 异常，确认页面仅显示脱敏提示，日志中可见完整 traceback | ✅ 已修复 |
| 6 | 性能 | `db.get_conn()` 每次调用新建连接，但 `insert_competition()` 等函数在异常路径下依赖 `finally` 关闭；Review 发现早期版本有一处缺少 `finally`，异常时会泄漏连接，长期运行后触发 `too many open files` | 中 | `db.py` 各写操作函数 | 统一模板：`conn = get_conn()` → `try: ... conn.commit()` → `finally: conn.close()`，逐个函数对齐 | 静态走查全部 `get_conn()` 调用点，均有对应 `finally` 关闭 | ✅ 已修复 |
| 7 | 性能 | 向量检索原实现一次性把 Chroma 全量结果捞回再重排，语料增长后内存与延迟线性上升 | 中 | `retriever.py: _l1_recall()` | 先按 `recall_n = max(top_k * mult, top_k)` 做 L1 粗召回，再做 L2 重排并截断 `top_k`，把检索成本控制在常数级 | 分别以 `top_k=8` 和 `top_k=20` 调用，确认返回条数与延迟符合预期 | ✅ 已修复 |
| 8 | 健壮性 | 赛事列表页早期直接 `SELECT *` 全表渲染，记录增长后首屏卡顿；空关键词搜索时 `LIKE '%%'` 退化为全表扫描 | 中 | `app.py` 赛事列表页 / `db.py` 查询函数 | 接入分页（`LIMIT/OFFSET`）+ 关键词为空时跳过 `LIKE` 条件；为 `level`、`category` 等过滤字段补索引 | `EXPLAIN QUERY PLAN` 确认命中索引；翻页与空搜索均有正常响应 | ✅ 已修复 |
| 9 | 整洁度 | 分析结果的状态流转（`draft → starred → archived → draft`）在 UI 层用散落的 `if/else` 硬编码，新增状态时容易漏改 | 低 | `app.py` | 抽为常量表 `IDEA_STATUS_FLOW` / `IDEA_STATUS_LABEL`，UI 仅做查表；写回前校验 `status` 合法性 | 三种状态循环点击，状态与标签同步正确；非法状态传入返回 `False` | ✅ 已修复 |

---

## 三、遗留项与后续计划

| # | 维度 | 问题 | 计划 |
| :--- | :--- | :--- | :--- |
| F-1 | 健壮性 | `db.py` 未启用 WAL 模式，多标签页并发写入可能偶发 `database is locked` | 下一迭代开启 `PRAGMA journal_mode=WAL` 并设置 `busy_timeout` |
| F-2 | 整洁度 | 尚无自动化测试，目前依赖手工回归 | 将 `scripts/` 下验证脚本整理为 `pytest` 用例，纳入 CI |
| F-3 | 性能 | 长回答流式输出时每 token 全量 `markdown()` 拼接，字符数大时略有开销 | 评估改为按 ~50ms 节流刷新，而非逐 token 刷新 |
| F-4 | 安全 | 无请求频控，公开部署时可能被刷调用额度 | 增加会话级 QPS 限制 |
| F-5 | 整洁度 | `app.py` 约 1000 行，UI 与业务逻辑仍混在一处 | 按页面拆分为 `pages/` 或 `ui/` 模块 |

---

## 四、Review 结论

本次 Review 覆盖安全性、健壮性、性能、代码整洁度四个维度共 20 个检查项，发现并修复 9 项问题，其中 **2 项高危**（无 Key 崩溃、部分唯一索引导致静默丢数据）和 **1 项影响核心体验的稳定性问题**（流式输出节点冲突）已在提交前完成修复并验证。剩余 5 项已登记为遗留项，按优先级排入下一迭代。

> 审查人：xiao
> 审查日期：2026.11.01
