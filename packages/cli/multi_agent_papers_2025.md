# 多 Agent 系统最新论文 (2024-2026)

> 搜索来源: arxiv cs.MA (Multiagent Systems) + 交叉列表
> 搜索时间: 2026-06-03

---

## 1. Economy of Minds: Emerging Multi-Agent Intelligence with Economic Interactions

- **链接**: https://arxiv.org/abs/2606.02859
- **作者**: Zhenting Qi, Huangyuan Su, Ao Qu, Chenyu Wang, et al. (15 authors)
- **日期**: Jun 2026
- **摘要**: 受 Hayek 经济理论启发，提出 agent 经济系统：agents 通过拍卖竞争行动权、交换支付、从环境奖励中积累财富。经济信号实现去中心化信用分配，无需全局编排或显式通信协议。群体通过经济选择进化——高效 agent 积累财富并通过 exploitation 变异，低效 agent 破产并被 exploration 替代。在数学推理、金融研究、科学研究等 5 个任务上超越强 monolithic 基线。**核心贡献**: 证明可以设计去中心化激励结构自动涌现多 agent 协作，而非人为工程协调。
- **方向**: 多 agent 协作、去中心化协调、涌现智能

---

## 2. The Ringelmann Effect in Multi-Agent LLM Systems: A Scaling Law for Effective Team Size

- **链接**: https://arxiv.org/abs/2606.02646
- **作者**: Blaž Bertalanič, Carolina Fortuna
- **日期**: May 2026
- **摘要**: 推导两参数标度律 $R(N) = N_{eff}/N = 1/(1+c(N-1)N^{-\beta})$，将多 agent LLM 配置分为三种渐近体制：hard-ceiling ($\beta=0$)、sublinear ($0<\beta<1$)、linear ($\beta\ge1$)。均场定理预测 peer 数量 $k$ 与辩论轮次 $\tau$ 仅通过乘积 $k\tau$ 影响动力学。在 44 个 (model × task × condition) 单元上验证 $R^2>0.99$。**关键发现**: (1) 30 个密集辩论 agent 在 MMLU-Hard 上的答案多样性不高于单个 agent；(2) 噪声安慰剂与自我纠正在自由形式数学上效果相当——同质团队中"辩论"的增益来自重新评估而非 peer 内容；(3) 仅架构多样性（异质团队）能降低 $c$ 并逃逸 hard-ceiling 体制，通信模式干预无效。
- **方向**: 多 agent 辩论、标度律、团队组成、涌现协作

---

## 3. Capability Advertisement as a Market for Lemons: A Trust Layer for Heterogeneous Agent Networks

- **链接**: https://arxiv.org/abs/2606.03034
- **作者**: Gaurav Naresh Mittal
- **日期**: Jun 2026
- **摘要**: 分析多 agent 通信协议（MCP、A2A）中的根本问题：agent 声称的能力不是静态事实——其能力是概率性的、随输入变化、随模型更新漂移，且 LLM agent 可以用完全自信的方式描述自己但错误。将这建模为"柠檬市场"（market for lemons）：当质量隐藏且声明廉价时，好坏提供者无法区分。提出 Trust Layer——一个协议无关的薄层，增加概率能力描述符、筛选（screening）和声誉（reputation），当维持过度声明的成本超过其收益时实现分离均衡（separating equilibrium）。设计无需模型重训练，在信任锚缺失时优雅降级。
- **方向**: 多 agent 通信协议、信任机制、异构 agent 网络

---

## 4. OpenAgenet/OAN: Technical Architecture for Trust-Governed Agent Identity and Discovery

- **链接**: https://arxiv.org/abs/2606.03163
- **作者**: Jinliang Xu
- **日期**: Jun 2026
- **摘要**: OAN 是一个协议中立的多 agent 互联信任层，定义角色架构、身份对象、注册工作流、Root 治理生命周期、Root 验证包模型、授权感知发现、签名可信调用、验证需求等。设计支持异构 agent 框架和交互协议（MCP、A2A、ANP 等）。OAN 不定义 agent 间的完整业务对话，而是定义 agent 身份如何变得可接受、可发现、可验证，在协议特定交互开始之前确保安全。
- **方向**: 多 agent 通信协议、身份发现、信任治理

---

## 5. SPOQ: Specialist Orchestrated Queuing for Multi-Agent Software Engineering

- **链接**: https://arxiv.org/abs/2606.03115
- **作者**: Royce Carbowitz, Dheeraj Kumar
- **日期**: Jun 2026
- **摘要**: 提出 SPOQ 方法论，包含三大创新：(1) 基于波形的拓扑调度——从任务依赖图计算并行执行波形；(2) 双验证门——执行前（规划验证）和执行后（代码验证）应用质量度量以减少返工；(3) Human-as-an-Agent (HaaA) 集成——人类专家参与分解并可被咨询。使用三层 agent 层级（Opus worker、Sonnet reviewer、Haiku investigator）优化成本-质量权衡。实验表明：波形调度接近关键路径下界（ratio 1.03-1.11，加速最多 14.3x）；双验证将缺陷从 0.34 降至 0.20/任务，测试通过率从 91.25% 升至 99.75%。在 17 个仓库、8,589 次提交、1,822 个任务上验证。
- **方向**: 多 agent 任务分配、编排、软件工程

---

## 6. FORGE: Multi-Agent Graduated Exploitation and Detection Engineering

- **链接**: https://arxiv.org/abs/2606.03453
- **作者**: Farooq Shaikh
- **日期**: Jun 2026
- **摘要**: FORGE 是一个多 agent 系统，桥接漏洞利用生成、优先级排序和检测规则工程三个孤立领域。五个专门 agent（Intel、Generator、Planner、Exploit、Detector）在固定流水线中执行：(1) 从 CVE 元数据生成目标漏洞应用；(2) 进行多轮利用评估（L0-L3 四级）；(3) 基于 OpenTelemetry 利用跟踪生成 Sigma 和 Snort 检测规则。在 603 个 CVE 上评估，67.8% 端到端 L1+ 利用，每个 CVE 仅 USD 1.50。L2+ 利用的检测规则比 L1 规则显著更高（p=0.035），93.4% 的 Snort 规则零误报。
- **方向**: 多 agent 流水线、专业 agent 分工、协作

---

## 7. When Helping Hurts and How to Fix It: Multi-Agent Debate for Data Cleaning

- **链接**: https://arxiv.org/abs/2606.02866
- **作者**: Chirag Parmar, Akshat Mehta, Henglin Wu, et al.
- **日期**: Jun 2026
- **摘要**: 系统研究多 agent 辩论在数据清洗中的效果——在 3 个基准、4 个模型家族、6000+ task-condition 对上发现辩论效果符号反转：在生成任务上退化了 -1.6~-15.5pp（因为 Critic 幻觉反馈被 Generator 无条件接受），但在错误检测上提升了 +27.4pp F1。推导出辩论收益条件：拯救错误输出概率 > 破坏正确输出概率。证明对抗性分离至关重要——使用不同工具的自验证失败，而具有代码执行接地和证据门控生成的独立 Critic 首次在生成任务上显著超越单 agent（+5.3pp, p<0.05）。
- **方向**: 多 agent 辩论、协作边界、Critic-Generator 框架

---

## 8. A Game-Theoretic Decision Framework for Optimal Selection of Coordination Detection Methods in Multi-UAV Fleet Operations

- **链接**: https://arxiv.org/abs/2606.02383
- **作者**: Christian Manasseh
- **日期**: Jun 2026
- **摘要**: 将多 UAV 机群协调检测方法选择建模为双人零和博弈（Monitor vs. Nature）。构建从轨迹监控数据到 8 个候选检测算法的端到端流水线，蒙特卡洛敏感性分析刻画随机性能，多目标优化层识别 Pareto 最优方法组合。实验发现框架根据操作优先级推荐不同方法组合：Koopman Phase 在均衡（70.6%）和速度优先（79.7%）配置中占优，CRQA 在路径识别优先时占优（47.4%）。
- **方向**: 多 agent 协调检测、博弈论、无人机群

---

## 9. Solipsistic Superintelligence is Unlikely to be Cooperative

- **链接**: https://arxiv.org/abs/2606.03237
- **作者**: Rakshit S Trivedi, Natasha Jaques, Logan Cross, et al.
- **日期**: Jun 2026
- **摘要**: 被 ICML 2026 接收。论证当前 AI 研究的唯我论范式（将世界视为外生静态反馈源）产生的超级智能不可能合作。部署 AI 系统引发内生非平稳性，造成训练-测试-部署差距。提出非唯我论研究范式：将相互依赖视为核心设计原则而非待解决的任务，包括构建动态评估测试平台、将制度视为设计原语、保留人类能动性作为结构性特征。
- **方向**: 多 agent 合作理论、AI 安全、制度设计

---

## 10. Epi-LLM Framework: Probing LLM Behavioral Priors Through Epidemiological Agent-Based Models

- **链接**: https://arxiv.org/abs/2606.02867
- **作者**: Petra Ferenz, Ava Keeling, Tobias O'Keefe, et al.
- **日期**: Jun 2026
- **摘要**: 将 agent-based 建模与 LLM 结合的 Epi-LLM 框架，合成 agent 社会在疫情接触网络上推理和动态适应。LLM agent 将峰值活跃感染降低，隔离合规在模拟第 6 天达 58-65%。感知健康严重性是隔离行为最强预测因子（$\beta=0.33, p=0.002$）。低方差 LLM 架构提供更高内部效度，高方差模型更好代表真实世界决策。
- **方向**: 基于 agent 的建模、LLM 驱动的多 agent 仿真

---

## 总结与建议

| 论文 | Agent 协作 | 通信协议 | 任务分配 | Swarm |
|------|:----------:|:--------:|:--------:|:-----:|
| 1. Economy of Minds | ★★★★★ 经济涌现 | ★★★ 拍卖信号 | ★★★★ 去中心化 | ★★★ |
| 2. Ringelmann Effect | ★★★★★ 辩论标度律 | ★★★ 通信效果 | ★★ | ★★ |
| 3. Market for Lemons | ★★★★ | ★★★★★ 信任层 | ★★★ | ★ |
| 4. OAN | ★★ | ★★★★★ 身份协议 | ★ | ★ |
| 5. SPOQ | ★★★★ | ★★★ | ★★★★★ 波形调度 | ★ |
| 6. FORGE | ★★★★ 流水线 | ★ | ★★★★ 专业分工 | ★ |
| 7. Debate for Data Clean | ★★★★★ 辩论条件 | ★★ | ★ | ★ |
| 8. Multi-UAV | ★★★★ | ★★ | ★★★ 博弈论 | ★★★★★ |
| 9. Solipsistic Superintel | ★★★★★ 合作理论 | ★ | ★ | ★ |
| 10. Epi-LLM | ★★★★ 仿真 | ★★ | ★★ | ★★★ |