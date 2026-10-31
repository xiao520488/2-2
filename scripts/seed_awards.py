# -*- coding: utf-8 -*-
"""
选项B-①（修订版）：批量生成 80 条模拟获奖数据（awards）
- 覆盖 6 类别 × 2021-2025 五年
- review_status='approved'（已审核）；embedding_state='none'（待向量同步）
- 用 kb.upsert_award 入库（自动算 content_hash，幂等）
- 按映射关联已有 competitions.id
"""
import io, sys, random

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
import kb

random.seed(20251031)

CATEGORIES = ["人工智能", "机器人", "程序设计", "电子信息",
              "数学建模", "创新创业"]
YEARS = [2021, 2022, 2023, 2024, 2025]
TOTAL = 80

# 6 类别 -> competitions.category 的映射（把作品类别挂到真实竞赛上）
CAT_TO_COMP_CATS = {
    "人工智能":     ["安全与人工智能", "计算机综合与软件"],
    "机器人":       ["物联网/嵌入式/ICT", "计算机综合与软件"],
    "程序设计":     ["程序设计", "计算机综合与软件"],
    "电子信息":     ["物联网/嵌入式/ICT"],
    "数学建模":     ["计算机综合与软件"],
    "创新创业":     ["创新创业", "创新创业/软件服务"],
}

THEMES = {
    "人工智能": [
        ("面向工业质检的小样本缺陷检测系统", "小样本学习 + 视觉Transformer 实现少标注缺陷识别",
         ["PyTorch", "ViT", "Few-shot Learning", "OpenCV"]),
        ("多模态大模型驱动的校园智能助手", "融合文本/语音/图像的校园问答与办事代理",
         ["LLM", "RAG", "Whisper", "LangChain"]),
        ("基于强化学习的交通信号自适应调度平台", "多路口协同控制，仿真环境下通行效率提升 27%",
         ["DQN", "SUMO", "Gym", "Python"]),
        ("医疗影像肺结节智能筛查与随访系统", "3D CNN + 注意力机制，敏感度达 94%",
         ["3D-CNN", "MONAI", "PACS", "Flask"]),
        ("面向法律文书的要素抽取与类案推荐引擎", "BERT 序列标注 + 向量检索类案匹配",
         ["BERT", "CRF", "Faiss", "FastAPI"]),
    ],
    "机器人": [
        ("四足机器人复杂地形自主巡检系统", "MPC 步态规划 + 激光雷达建图，可越障爬坡",
         ["ROS2", "MPC", "SLAM", "C++"]),
        ("果蔬采摘双臂协作机器人", "视觉伺服定位 + 柔顺力控，采摘成功率 91%",
         ["ROS", "MoveIt", "YOLO", "阻抗控制"]),
        ("仓储 AGV 多机协同调度与避障系统", "分布式任务分配 + 动态窗口避障",
         ["A*", "DWA", "MQTT", "C++"]),
        ("面向独居老人的陪护机器人", "语音交互 + 跌倒检测 + 远程告警闭环",
         ["ASR", "OpenPose", "ROS", "WebSocket"]),
        ("水下机器人管道缺陷视觉检测平台", "浑浊水体图像增强 + 裂缝分割",
         ["GAN", "U-Net", "OpenCV", "嵌入式"]),
    ],
    "程序设计": [
        ("高并发在线判题系统", "沙箱隔离 + 消息队列削峰，支撑 5k QPS",
         ["Go", "Docker", "RabbitMQ", "Redis"]),
        ("分布式链路追踪与可观测平台", "OpenTelemetry 采集 + 拓扑图可视化定位慢调用",
         ["OpenTelemetry", "ClickHouse", "Grafana", "K8s"]),
        ("跨平台代码缺陷静态分析工具", "AST 分析 + 规则引擎，检出率优于基线 18%",
         ["AST", "Rust", "Tree-sitter", "CI"]),
        ("低代码表单引擎与流程编排平台", "可视化拖拽 + 动态表单渲染 + 审批流",
         ["Vue3", "Node.js", "JSONSchema", "BPMN"]),
        ("实时协同文档编辑系统", "CRDT 冲突消解 + 增量同步",
         ["CRDT", "WebSocket", "Yjs", "TypeScript"]),
    ],
    "电子信息": [
        ("低功耗物联网环境监测节点", "自研能量采集 + LoRa 组网，续航提升 3 倍",
         ["LoRa", "STM32", "能量采集", "PCB"]),
        ("基于 FPGA 的高速图像采集卡", "Camera Link 接口 + 实时预处理流水线",
         ["FPGA", "Verilog", "Camera Link", "DDR3"]),
        ("毫米波雷达生命体征监测系统", "非接触呼吸心跳检测，误差 < 3 bpm",
         ["FMCW", "DSP", "MATLAB", "嵌入式"]),
        ("柔性可穿戴心电监测贴片", "柔性电极 + 低噪声前端 + 蓝牙传输",
         ["AFE", "BLE", "柔性电子", "低功耗设计"]),
        ("智能电网边缘侧负荷预测终端", "边缘推理 + 轻量化 LSTM 模型",
         ["TinyML", "LSTM", "Modbus", "ARM"]),
    ],
    "数学建模": [
        ("城市共享单车潮汐调度优化模型", "时空聚类 + 混合整数规划，空车率下降 22%",
         ["整数规划", "聚类", "MATLAB", "Python"]),
        ("疫情传播动力学与防控策略仿真", "改进 SEIR + 参数反演，评估多情景干预",
         ["SEIR", "参数反演", "蒙特卡洛", "R"]),
        ("区域能源结构多目标优化模型", "碳排与经济成本双目标 Pareto 前沿分析",
         ["NSGA-II", "多目标优化", "Python", "熵权法"]),
        ("供应链中断风险传播建模", "复杂网络 + 级联失效分析关键节点",
         ["复杂网络", "级联失效", "NetworkX", "敏感性分析"]),
        ("光伏出力短期预测的组合模型", "EMD 分解 + LSTM/GRU 集成预测",
         ["EMD", "LSTM", "集成学习", "时间序列"]),
    ],
    "创新创业": [
        ("面向县域农业的 AI 病虫害诊断服务", "小程序 + 边缘识别，覆盖 12 种作物",
         ["小程序", "CNN", "边缘计算", "商业模式"]),
        ("实验室设备共享预约平台", "闲置设备撮合 + 信用积分体系",
         ["SaaS", "撮合算法", "Vue", "运营"]),
        ("银发群体智能用药提醒硬件", "药盒感知 + 子女端提醒 + 用药依从度分析",
         ["IoT", "App", "数据看板", "老龄化"]),
        ("高校科研成果转化对接平台", "技术画像 + 企业需求匹配推荐",
         ["NLP", "推荐系统", "图谱", "产学研"]),
        ("低碳校园碳积分激励系统", "行为识别 + 积分兑换闭环，试点减排 15%",
         ["碳核算", "行为激励", "小程序", "数据分析"]),
    ],
}

GRADES = ["一等奖", "二等奖", "三等奖", "特等奖", "金奖", "银奖"]
SESSIONS = ["初赛", "决赛", "全国总决赛", "省赛", "区域赛"]

comps = kb.query("SELECT id, name, category, level FROM competitions")
by_cat = {}
for c in comps:
    by_cat.setdefault((c["category"] or "").strip(), []).append(c)
print("competitions by category:", {k: len(v) for k, v in by_cat.items()})

rows = []
i = 0
while len(rows) < TOTAL:
    ci = i % len(CATEGORIES)
    cat = CATEGORIES[ci]
    year = YEARS[(i // len(CATEGORIES)) % len(YEARS)]
    pool = THEMES[cat]
    theme_idx = (i // (len(CATEGORIES) * len(YEARS))) % len(pool)
    base_title, summary, stack = pool[theme_idx]

    title = base_title if i < len(CATEGORIES) * len(YEARS) else f"{base_title}（{year}届改进版）"
    team = f"{cat}方向第{len(rows) % 9 + 1}组"
    level = "national" if (i % 3 != 2) else "provincial"

    # 关联到映射后的真实竞赛
    cands = []
    for cc in CAT_TO_COMP_CATS[cat]:
        cands.extend(by_cat.get(cc, []))
    comp = cands[i % len(cands)] if cands else None

    rows.append({
        "competition_id": comp["id"] if comp else None,
        "competition_raw": comp["name"] if comp else f"{cat}类竞赛",
        "category": cat,
        "level": level,
        "year": year,
        "session": f"{SESSIONS[i % len(SESSIONS)]}",
        "title": title,
        "team": team,
        "award_grade": GRADES[i % len(GRADES)],
        "track": f"{cat}赛道",
        "summary": summary,
        "tech_stack": stack,
        "highlights": f"亮点：{summary}；在同类作品中具备工程完整度与可复现性。",
        "source_type": "mock",
        "confidence": round(random.uniform(0.82, 0.99), 2),
        "review_status": "approved",
        "embedding_state": "none",
    })
    i += 1

stat = {"inserted": 0, "updated": 0, "skipped": 0}
for r in rows:
    _, action = kb.upsert_award(r)
    stat[action] += 1

print("=== upsert 结果 ===", stat)
print("awards 总数:", kb.query("SELECT COUNT(*) c FROM awards")[0]["c"])

print("\n=== 按类别 × 年份分布 ===")
for r in kb.query("""SELECT category, year, COUNT(*) c FROM awards
                     GROUP BY category, year ORDER BY category, year"""):
    print(f"  {r['category']:<6} {r['year']}  {r['c']}")

print("\n=== 状态分布 ===")
for r in kb.query("""SELECT review_status, embedding_state, COUNT(*) c FROM awards
                     GROUP BY review_status, embedding_state"""):
    print("  ", r["review_status"], r["embedding_state"], r["c"])

linked = kb.query("SELECT COUNT(*) c FROM awards WHERE competition_id IS NOT NULL")[0]["c"]
print("\n已关联 competition_id 的条数:", linked)
print("\nSEED_DONE")
