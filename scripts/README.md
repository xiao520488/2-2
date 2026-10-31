# scripts/ —— 运维与数据脚本

根目录只保留**应用运行必需**的模块（`app.py` / `db.py` / `kb.py` / `llm.py` /
`embedder.py` / `retriever.py` / `analyzer.py` 等）与**正式测试**（`test_*.py`）。
本目录存放低频但仍有价值的维护脚本，属于手工执行，不被应用 import。

> 所有脚本均依赖项目根目录的模块与环境，请**在项目根目录**执行，例如：
> ```bash
> python scripts/seed_awards.py
> ```

| 脚本 | 作用 | 使用时机 |
| --- | --- | --- |
| `seed_awards.py` | 批量生成 80 条模拟获奖作品（6 类别 × 2021–2025），已审核、待向量化，经 `kb.upsert_award` 幂等入库 | 演示 / 压测检索链路，或没有真实获奖数据时填充 |
| `warm_model.py` | 预热并本地缓存 `BAAI/bge-small-zh-v1.5` 向量模型（走 hf-mirror 国内镜像） | 首次部署、离线演示前，避免首屏加载卡顿 |
| `warm_download.py` | 仅做权重文件下载（不走 SentenceTransformer 加载），适合弱网环境分步排查 | `warm_model.py` 失败时的降级手段 |
| `test_retriever_real.py` | 对接真实向量库的检索回归脚本，打印召回结果与分数分布 | 调整 `KB_MIN_SCORE` / `KB_RECALL_MULT` 后人工比对效果 |
| `migrate_insights.py` | `insights` 表历史数据迁移（备份 → 改结构 → 回填） | 老库升级，执行前会自动备份到 `scripts/db_backups/` |
| `db_backups/` | 历次数据库备份快照（`*.db.bak_*`） | 出问题时可回滚；已被 `.gitignore` 忽略，不会入库 |

**注意**：本目录已被 `.gitignore` 中的 `*.bak_*` 规则覆盖备份文件；
`seed_awards.py` 会写入真实数据，请在测试库上操作或先备份 `competitions.db`。
