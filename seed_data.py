# -*- coding: utf-8 -*-
"""云端演示数据（种子数据）。

仅在数据库为空时由 bootstrap.py 调用，用于 Streamlit Community Cloud
首次冷启动时快速填充内容（内存/网络受限，控制在小规模）。

设计说明：
  - COMPETITIONS：20 条竞赛，覆盖 6 大类别、国家级/省级、跨年场景
  - AWARDS：与上述竞赛一一对应的 20 条获奖作品（review_status=approved）
            Chroma 向量库索引的是 awards 表，因此必须有这份数据，
            否则"智能问答"页检索为空。
  - 字段严格对齐 schema.sql / schema_kb.sql，不写入 created_at 等
    DB 自动生成字段。
"""

# ---------------------------------------------------------------- 竞赛（20 条）
# 字段：name, category, reg_start_month, reg_end_month, reg_cross_year,
#       official_url, level, level_label, sort_order, intro
COMPETITIONS = [
    {
        "name": "中国国际大学生创新大赛",
        "category": "创新创业",
        "reg_start_month": 3, "reg_end_month": 5, "reg_cross_year": 0,
        "official_url": "https://cy.ncss.cn/",
        "level": "national", "level_label": "国家级", "sort_order": 1,
        "intro": "国内规格最高、参与面最广的大学生创新创业赛事，赛道覆盖高教、职教、国际与萌芽。",
    },
    {
        "name": "中国大学生计算机设计大赛",
        "category": "计算机",
        "reg_start_month": 2, "reg_end_month": 4, "reg_cross_year": 0,
        "official_url": "https://jsjds.blcu.edu.cn/",
        "level": "national", "level_label": "国家级", "sort_order": 2,
        "intro": "面向本科生的计算机类综合设计赛事，软件应用、数媒设计、AI 应用多赛道并行。",
    },
    {
        "name": "全国大学生软件创新大赛",
        "category": "软件服务",
        "reg_start_month": 9, "reg_end_month": 11, "reg_cross_year": 0,
        "official_url": "https://www.cnsoftbei.com/",
        "level": "national", "level_label": "国家级", "sort_order": 3,
        "intro": "以软件工程实践为核心的全国赛事，强调完整产品落地与工程规范。",
    },
    {
        "name": "中国高校计算机大赛-人工智能创意赛",
        "category": "人工智能",
        "reg_start_month": 4, "reg_end_month": 6, "reg_cross_year": 0,
        "official_url": "https://aic.ichina.cloud/",
        "level": "national", "level_label": "国家级", "sort_order": 4,
        "intro": "聚焦 AI 创意与应用落地的赛事，鼓励将大模型能力融入真实场景。",
    },
    {
        "name": "全国大学生数学建模竞赛",
        "category": "数学建模",
        "reg_start_month": 5, "reg_end_month": 9, "reg_cross_year": 0,
        "official_url": "https://www.mcm.edu.cn/",
        "level": "national", "level_label": "国家级", "sort_order": 5,
        "intro": "国内影响力最大的学科竞赛之一，三人组队、三天完成建模与论文。",
    },
    {
        "name": "美国大学生数学建模竞赛（MCM/ICM）",
        "category": "数学建模",
        "reg_start_month": 11, "reg_end_month": 2, "reg_cross_year": 1,
        "official_url": "https://www.comap.com/contests/mcm-icm",
        "level": "national", "level_label": "国家级", "sort_order": 6,
        "intro": "国际知名英文建模赛事，冬季开赛，适合有英文写作基础与建模经验的队伍。",
    },
    {
        "name": "全国大学生电子设计竞赛",
        "category": "电子信息",
        "reg_start_month": 3, "reg_end_month": 5, "reg_cross_year": 0,
        "official_url": "https://www.nuedc-training.com.cn/",
        "level": "national", "level_label": "国家级", "sort_order": 7,
        "intro": "电子信息类最高规格赛事，四天三夜封闭开发，硬件与嵌入式能力并重。",
    },
    {
        "name": "全国大学生信息安全竞赛",
        "category": "网络安全",
        "reg_start_month": 3, "reg_end_month": 6, "reg_cross_year": 0,
        "official_url": "https://www.ciscn.cn/",
        "level": "national", "level_label": "国家级", "sort_order": 8,
        "intro": "网络安全领域的国家级赛事，含作品赛与创新实践能力赛两条主线。",
    },
    {
        "name": "中国大学生服务外包创新创业大赛",
        "category": "创新创业/软件服务",
        "reg_start_month": 12, "reg_end_month": 4, "reg_cross_year": 1,
        "official_url": "https://www.fwwb.org.cn/",
        "level": "national", "level_label": "国家级", "sort_order": 9,
        "intro": "以企业真实命题驱动，跨年报名、次年春季决赛，产学研结合紧密。",
    },
    {
        "name": "中国高校计算机大赛-大数据挑战赛",
        "category": "大数据",
        "reg_start_month": 6, "reg_end_month": 8, "reg_cross_year": 0,
        "official_url": "https://www.heywhale.com/home/competition",
        "level": "national", "level_label": "国家级", "sort_order": 10,
        "intro": "面向数据挖掘与算法建模的实战赛事，线上赛 + 现场答辩双阶段。",
    },
    {
        "name": "全国大学生物联网设计竞赛",
        "category": "计算机",
        "reg_start_month": 3, "reg_end_month": 6, "reg_cross_year": 0,
        "official_url": "https://iotcompetition.cn/",
        "level": "national", "level_label": "国家级", "sort_order": 11,
        "intro": "围绕物联网系统设计，强调软硬件协同与真实场景部署。",
    },
    {
        "name": "蓝桥杯全国软件和信息技术专业人才大赛",
        "category": "计算机",
        "reg_start_month": 10, "reg_end_month": 12, "reg_cross_year": 0,
        "official_url": "https://dasai.lanqiao.cn/",
        "level": "national", "level_label": "国家级", "sort_order": 12,
        "intro": "参与人数众多的算法与软件类赛事，省赛 + 国赛两级晋级，适合入门练手。",
    },
    {
        "name": "ACM-ICPC 国际大学生程序设计竞赛（亚洲区预选赛）",
        "category": "计算机",
        "reg_start_month": 6, "reg_end_month": 9, "reg_cross_year": 0,
        "official_url": "https://icpc.global/",
        "level": "national", "level_label": "国家级", "sort_order": 13,
        "intro": "全球公认的算法竞技标杆，三人一机、五人组队，含金量极高。",
    },
    {
        "name": "全国大学生智能汽车竞赛",
        "category": "电子信息",
        "reg_start_month": 3, "reg_end_month": 5, "reg_cross_year": 0,
        "official_url": "https://www.smartcarrace.com/",
        "level": "national", "level_label": "国家级", "sort_order": 14,
        "intro": "以嵌入式控制与视觉感知为核心的工程赛事，分竞速与创意多组别。",
    },
    {
        "name": "中国机器人大赛暨 RoboCup 机器人世界杯中国赛",
        "category": "人工智能",
        "reg_start_month": 4, "reg_end_month": 6, "reg_cross_year": 0,
        "official_url": "https://www.robocup.org.cn/",
        "level": "national", "level_label": "国家级", "sort_order": 15,
        "intro": "机器人与智能体方向的老牌赛事，涵盖仿真、服务机器人、救援等多组别。",
    },
    {
        "name": "中国大学生计算机设计大赛（省赛）",
        "category": "计算机",
        "reg_start_month": 3, "reg_end_month": 5, "reg_cross_year": 0,
        "official_url": "https://jsjds.blcu.edu.cn/",
        "level": "provincial", "level_label": "省级", "sort_order": 16,
        "intro": "国赛的省级选拔通道，作品经省赛评审后择优推荐进入国赛。",
    },
    {
        "name": "长三角高校软件应用创新大赛",
        "category": "软件服务",
        "reg_start_month": 9, "reg_end_month": 11, "reg_cross_year": 0,
        "official_url": "https://csjr.example.edu.cn/",
        "level": "provincial", "level_label": "区域级", "sort_order": 17,
        "intro": "面向长三角区域高校的软件应用赛事，注重产品化与商业可行性。",
    },
    {
        "name": "全国大学生数学建模竞赛（省赛区）",
        "category": "数学建模",
        "reg_start_month": 5, "reg_end_month": 9, "reg_cross_year": 0,
        "official_url": "https://www.mcm.edu.cn/",
        "level": "provincial", "level_label": "省级", "sort_order": 18,
        "intro": "国赛的省级评奖通道，按赛区独立评审，成绩可直接计入国赛排名。",
    },
    {
        "name": "省级大学生创新创业训练计划项目赛",
        "category": "创新创业",
        "reg_start_month": 2, "reg_end_month": 4, "reg_cross_year": 0,
        "official_url": "https://cxcy.example.edu.cn/",
        "level": "provincial", "level_label": "省级", "sort_order": 19,
        "intro": "以大学生创新创业训练计划为依托的省级赛事，适合早期项目孵化。",
    },
    {
        "name": "粤港澳大湾区网络安全邀请赛",
        "category": "网络安全",
        "reg_start_month": 10, "reg_end_month": 12, "reg_cross_year": 0,
        "official_url": "https://csc.example.edu.cn/",
        "level": "provincial", "level_label": "区域级", "sort_order": 20,
        "intro": "面向大湾区高校的网络安全竞赛，含 CTF 与攻防对抗两类赛制。",
    },
]


# ---------------------------------------------------------------- 获奖作品（20 条）
# 字段对齐 schema_kb.sql 的 awards 表
# competition_name 用于回查 competitions.id（写入时自动关联）
AWARDS = [
    {
        "competition_name": "中国国际大学生创新大赛",
        "competition_raw": "中国国际大学生创新大赛",
        "category": "创新创业", "level": "national",
        "year": 2024, "session": "第10届", "title": "智农云眸——设施农业病害识别与决策平台",
        "team": "浙江某高校 · 智农团队", "award_grade": "金奖", "track": "高教主赛道",
        "summary": "面向设施农业的病害识别与种植决策平台。通过手机拍摄叶片图像识别病害类型，"
                   "结合温湿度传感器数据给出用药与通风建议，已在3个农业合作社试点使用。",
        "tech_stack": ["YOLOv8", "Flask", "Vue3", "MySQL"],
        "highlights": "模型在自建叶片数据集上病害识别准确率92%；轻量化后可在安卓端本地推理。",
        "source_url": "", "source_type": "manual", "confidence": 0.9,
    },
    {
        "competition_name": "中国大学生计算机设计大赛",
        "competition_raw": "中国大学生计算机设计大赛",
        "category": "计算机", "level": "national",
        "year": 2024, "session": "第17届", "title": "古籍修复辅助系统——残页拼合与文字补全",
        "team": "北京某高校 · 文脉工作室", "award_grade": "一等奖", "track": "软件应用与开发",
        "summary": "针对古籍扫描件开发的辅助修复系统。提供残页轮廓自动拼合、缺字候选补全与"
                   "修复进度管理三个模块，帮助修复师减少重复手工操作。",
        "tech_stack": ["PyTorch", "OpenCV", "FastAPI", "PostgreSQL"],
        "highlights": "残页拼合召回率85%；缺字补全采用字形相似度检索，给出候选而非直接替换。",
        "source_url": "", "source_type": "manual", "confidence": 0.88,
    },
    {
        "competition_name": "全国大学生软件创新大赛",
        "competition_raw": "全国大学生软件创新大赛",
        "category": "软件服务", "level": "national",
        "year": 2024, "session": "第17届", "title": "FlowBoard——面向敏捷小组的可视化协作看板",
        "team": "湖北某高校 · Flow 团队", "award_grade": "二等奖", "track": "创意赛道",
        "summary": "轻量级项目协作看板，支持任务拖拽、依赖关系连线与迭代燃尽图。强调离线可用与"
                   "低学习成本，适合5-15人的学生团队使用。",
        "tech_stack": ["React", "TypeScript", "Node.js", "SQLite"],
        "highlights": "基于 IndexedDB 实现离线优先同步；依赖冲突实时高亮提示。",
        "source_url": "", "source_type": "manual", "confidence": 0.85,
    },
    {
        "competition_name": "中国高校计算机大赛-人工智能创意赛",
        "competition_raw": "中国高校计算机大赛-人工智能创意赛",
        "category": "人工智能", "level": "national",
        "year": 2024, "session": "第7届", "title": "拾光——面向听障学生的课堂实时字幕助手",
        "team": "江苏某高校 · 拾光小队", "award_grade": "二等奖", "track": "AI 创意",
        "summary": "将课堂语音实时转写为字幕并同步显示在手机端，同时用大模型对专业术语做二次校正，"
                   "降低听障学生课堂信息获取难度。",
        "tech_stack": ["Whisper", "LLM API", "WebSocket", "Flutter"],
        "highlights": "术语纠错环节使专业词汇转写准确率从78%提升至91%。",
        "source_url": "", "source_type": "manual", "confidence": 0.9,
    },
    {
        "competition_name": "全国大学生数学建模竞赛",
        "competition_raw": "全国大学生数学建模竞赛",
        "category": "数学建模", "level": "national",
        "year": 2024, "session": "第33届", "title": "城市共享单车潮汐调度优化模型",
        "team": "陕西某高校 · 建模一队", "award_grade": "一等奖", "track": "本科组",
        "summary": "以某市一周骑行数据为基础，建立时空需求预测与车辆调度联合优化模型，"
                   "用混合整数规划求调度方案，并对早晚高峰潮汐现象做了分时段建模。",
        "tech_stack": ["Python", "Gurobi", "pandas", "Matplotlib"],
        "highlights": "相较原调度方案，平均缺车时长下降约23%，调度成本下降11%。",
        "source_url": "", "source_type": "manual", "confidence": 0.86,
    },
    {
        "competition_name": "美国大学生数学建模竞赛（MCM/ICM）",
        "competition_raw": "MCM/ICM",
        "category": "数学建模", "level": "national",
        "year": 2024, "session": "2024 MCM", "title": "基于多主体仿真的沿海城市洪涝疏散策略",
        "team": "上海某高校 · Team Phoenix", "award_grade": "Meritorious Winner", "track": "MCM",
        "summary": "针对沿海城市极端降雨情景，构建多主体疏散仿真模型，比较不同预警提前量与"
                   "避难所分配策略下的疏散效率与拥堵风险。",
        "tech_stack": ["Mesa", "NumPy", "GeoPandas", "LaTeX"],
        "highlights": "提出分区分时的分级预警策略，仿真显示整体疏散完成时间缩短约18%。",
        "source_url": "", "source_type": "manual", "confidence": 0.84,
    },
    {
        "competition_name": "全国大学生电子设计竞赛",
        "competition_raw": "全国大学生电子设计竞赛",
        "category": "电子信息", "level": "national",
        "year": 2023, "session": "2023届", "title": "基于视觉循迹的自主分拣小车",
        "team": "四川某高校 · 电设三队", "award_grade": "二等奖", "track": "控制类",
        "summary": "四天三夜完成的自主分拣小车，采用视觉识别目标颜色与形状，配合PID循迹算法"
                   "完成路径规划与定点抓取投放。",
        "tech_stack": ["STM32", "OpenMV", "C", "PID 控制"],
        "highlights": "在指定赛道上完成全流程分拣，单件平均处理时间约4.2秒。",
        "source_url": "", "source_type": "manual", "confidence": 0.83,
    },
    {
        "competition_name": "全国大学生信息安全竞赛",
        "competition_raw": "全国大学生信息安全竞赛",
        "category": "网络安全", "level": "national",
        "year": 2024, "session": "第17届", "title": "面向物联网固件的自动化漏洞挖掘工具",
        "team": "西安某高校 · SecKitten", "award_grade": "一等奖", "track": "作品赛",
        "summary": "针对物联网固件镜像的自动化分析工具，完成解包、二进制符号恢复与常见危险函数"
                   "污点追踪，输出可复现的漏洞报告。",
        "tech_stack": ["Python", "angr", "Ghidra", "Docker"],
        "highlights": "在公开固件数据集上发现并确认12处未公开漏洞；支持批量扫描与报告导出。",
        "source_url": "", "source_type": "manual", "confidence": 0.88,
    },
    {
        "competition_name": "中国大学生服务外包创新创业大赛",
        "competition_raw": "中国大学生服务外包创新创业大赛",
        "category": "创新创业/软件服务", "level": "national",
        "year": 2024, "session": "第15届", "title": "面向社区养老的用药提醒与家属协同服务",
        "team": "广东某高校 · 暖阳团队", "award_grade": "二等奖", "track": "企业命题",
        "summary": "围绕社区独居老人用药场景设计的小程序服务，提供定时提醒、服药打卡与异常未服药"
                   "自动通知家属三类功能，并配套简易的家属端看板。",
        "tech_stack": ["微信小程序", "Spring Boot", "MySQL", "Redis"],
        "highlights": "异常提醒链路支持电话+短信双通道兜底；在2个社区完成小规模试用。",
        "source_url": "", "source_type": "manual", "confidence": 0.85,
    },
    {
        "competition_name": "中国高校计算机大赛-大数据挑战赛",
        "competition_raw": "中国高校计算机大赛-大数据挑战赛",
        "category": "大数据", "level": "national",
        "year": 2024, "session": "2024届", "title": "电商用户复购预测与营销触达策略",
        "team": "浙江某高校 · 数据猎人", "award_grade": "三等奖", "track": "算法赛道",
        "summary": "基于用户行为序列构建复购概率预测模型，并在此基础上做营销预算约束下的"
                   "人群圈选与触达排序优化。",
        "tech_stack": ["LightGBM", "XGBoost", "Spark", "Python"],
        "highlights": "复购预测 AUC 达0.89；在固定预算下触达转化率提升约16%。",
        "source_url": "", "source_type": "manual", "confidence": 0.82,
    },
    {
        "competition_name": "全国大学生物联网设计竞赛",
        "competition_raw": "全国大学生物联网设计竞赛",
        "category": "计算机", "level": "national",
        "year": 2024, "session": "第11届", "title": "校园实验室环境安全监测系统",
        "team": "湖南某高校 · IoT 先锋", "award_grade": "二等奖", "track": "物联网应用",
        "summary": "在实验室内部署多类传感器，实时监测温湿度、烟雾与用电功率，异常时推送告警"
                   "并联动断电保护，同时提供历史数据回溯。",
        "tech_stack": ["ESP32", "MQTT", "InfluxDB", "Grafana"],
        "highlights": "告警平均延迟低于2秒；支持按实验室分组配置不同阈值策略。",
        "source_url": "", "source_type": "manual", "confidence": 0.84,
    },
    {
        "competition_name": "蓝桥杯全国软件和信息技术专业人才大赛",
        "competition_raw": "蓝桥杯",
        "category": "计算机", "level": "national",
        "year": 2024, "session": "第15届", "title": "基于图算法的校园路径导航小程序",
        "team": "山东某高校 · 个人参赛", "award_grade": "二等奖", "track": "软件类",
        "summary": "把校园路网抽象为带权无向图，实现最短路径、无障碍路径与多目标途经点路径规划，"
                   "并做成微信小程序供学生日常使用。",
        "tech_stack": ["Dijkstra", "微信小程序", "JavaScript"],
        "highlights": "支持无障碍模式路径；对300余个节点路网的单次查询耗时低于10毫秒。",
        "source_url": "", "source_type": "manual", "confidence": 0.8,
    },
    {
        "competition_name": "ACM-ICPC 国际大学生程序设计竞赛（亚洲区预选赛）",
        "competition_raw": "ICPC Asia Regional",
        "category": "计算机", "level": "national",
        "year": 2024, "session": "2024 Asia", "title": "ICPC 亚洲区赛题求解与算法训练体系总结",
        "team": "北京某高校 · 三人队", "award_grade": "银牌", "track": "ICPC",
        "summary": "参赛队伍对当年区域赛题目的完整解题思路整理，覆盖动态规划、网络流与计算几何"
                   "三类高频题型，并总结了一套队伍训练与赛内分工方法。",
        "tech_stack": ["C++", "算法", "STL"],
        "highlights": "区域赛现场通过6题；整理的题型模板被校内集训队沿用。",
        "source_url": "", "source_type": "manual", "confidence": 0.86,
    },
    {
        "competition_name": "全国大学生智能汽车竞赛",
        "competition_raw": "全国大学生智能汽车竞赛",
        "category": "电子信息", "level": "national",
        "year": 2023, "session": "第18届", "title": "摄像头组智能车的高速循迹控制优化",
        "team": "江苏某高校 · 追风车队", "award_grade": "一等奖", "track": "摄像头组",
        "summary": "通过改进图像二值化与边缘提取流程提升赛道中线稳定性，并结合速度分段PID与"
                   "预瞄控制改善弯道通过速度。",
        "tech_stack": ["C", "MT9V034", "PID", "边缘检测"],
        "highlights": "单圈成绩较上一版提升约1.8秒；弯道脱线率显著下降。",
        "source_url": "", "source_type": "manual", "confidence": 0.85,
    },
    {
        "competition_name": "中国机器人大赛暨 RoboCup 机器人世界杯中国赛",
        "competition_raw": "中国机器人大赛",
        "category": "人工智能", "level": "national",
        "year": 2024, "session": "2024届", "title": "仿真救援机器人路径规划与目标识别",
        "team": "天津某高校 · Rescue 小队", "award_grade": "二等奖", "track": "仿真组",
        "summary": "在仿真救援环境中实现探索式建图、路径规划与受害者目标识别，重点解决"
                   "未知环境下的探索效率与重复探测问题。",
        "tech_stack": ["ROS", "Gazebo", "SLAM", "YOLO"],
        "highlights": "在标准仿真地图上探索覆盖率提升至96%，重复探测率降低约30%。",
        "source_url": "", "source_type": "manual", "confidence": 0.83,
    },
    {
        "competition_name": "中国大学生计算机设计大赛（省赛）",
        "competition_raw": "中国大学生计算机设计大赛（省赛）",
        "category": "计算机", "level": "provincial",
        "year": 2024, "session": "省级赛", "title": "面向乡村小学的互动科普课件生成工具",
        "team": "河南某高校 · 星火小组", "award_grade": "一等奖", "track": "数媒设计",
        "summary": "为乡村教师设计的科普课件生成工具，输入知识点即可产出含插图与互动小测的"
                   "课件初稿，教师可在此基础上二次修改。",
        "tech_stack": ["Vue3", "LLM API", "Canvas"],
        "highlights": "课件初稿生成时间从数小时压缩到约5分钟；已在3所乡村小学试用。",
        "source_url": "", "source_type": "manual", "confidence": 0.82,
    },
    {
        "competition_name": "长三角高校软件应用创新大赛",
        "competition_raw": "长三角高校软件应用创新大赛",
        "category": "软件服务", "level": "provincial",
        "year": 2024, "session": "2024届", "title": "面向小微商户的轻量库存管理应用",
        "team": "上海某高校 · 小账本团队", "award_grade": "二等奖", "track": "应用创新",
        "summary": "针对小微商户的库存与进货管理应用，支持扫码入库、临期提醒与简单的销量趋势分析，"
                   "强调极简操作与低成本部署。",
        "tech_stack": ["Flutter", "SQLite", "Spring Boot"],
        "highlights": "全流程操作可在一屏内完成；单机模式无需服务器即可使用。",
        "source_url": "", "source_type": "manual", "confidence": 0.8,
    },
    {
        "competition_name": "全国大学生数学建模竞赛（省赛区）",
        "competition_raw": "全国大学生数学建模竞赛（省赛区）",
        "category": "数学建模", "level": "provincial",
        "year": 2024, "session": "第33届省赛区", "title": "区域光伏发电功率短期预测模型",
        "team": "安徽某高校 · 追光队", "award_grade": "二等奖", "track": "本科组",
        "summary": "融合气象预报数据与历史出力数据，构建短期光伏功率预测模型，比较了多种"
                   "时序模型在不同天气类型下的表现差异。",
        "tech_stack": ["Python", "LSTM", "XGBoost", "pandas"],
        "highlights": "晴天情景下预测 MAPE 约6.5%；阴雨天气下改用分类型模型后误差明显下降。",
        "source_url": "", "source_type": "manual", "confidence": 0.8,
    },
    {
        "competition_name": "省级大学生创新创业训练计划项目赛",
        "competition_raw": "大创项目赛",
        "category": "创新创业", "level": "provincial",
        "year": 2023, "session": "2023届", "title": "校园二手教材循环小程序",
        "team": "福建某高校 · 书循环团队", "award_grade": "三等奖", "track": "创业实践",
        "summary": "面向校内学生的二手教材流转小程序，按课程与专业建立教材对应关系，简化"
                   "学期初的教材匹配与线下自提流程。",
        "tech_stack": ["微信小程序", "Node.js", "MongoDB"],
        "highlights": "上线一学期促成约800次教材流转；按课程自动推荐可省去逐条搜索。",
        "source_url": "", "source_type": "manual", "confidence": 0.78,
    },
    {
        "competition_name": "粤港澳大湾区网络安全邀请赛",
        "competition_raw": "大湾区网络安全邀请赛",
        "category": "网络安全", "level": "provincial",
        "year": 2024, "session": "2024届", "title": "Web 常见漏洞自动化检测与修复建议系统",
        "team": "广东某高校 · 白帽子小队", "award_grade": "一等奖", "track": "CTF/攻防",
        "summary": "针对教学场景设计的 Web 漏洞检测工具，可在靶场环境中自动识别 SQL 注入、"
                   "XSS 等常见漏洞，并给出对应的代码级修复建议。",
        "tech_stack": ["Python", "requests", "SQLMap 思路", "Flask"],
        "highlights": "在自建靶场中覆盖12类常见漏洞；修复建议可定位到具体代码行。",
        "source_url": "", "source_type": "manual", "confidence": 0.82,
    },
]
