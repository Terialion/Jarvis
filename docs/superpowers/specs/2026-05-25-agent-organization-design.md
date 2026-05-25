# Agent Organization — 层级组织多 Agent 架构设计

**日期**: 2026-05-25
**状态**: draft

## 1. 概述

将 Jarvis 的单 Agent 模型升级为**层级组织 Agent 架构**（Organizational Agent Hierarchy），模拟公司组织架构：主管（CEO）派发任务给团队，团队成员之间可以自主通信讨论，主管拥有全权控制（暂停/重定向/替换）。

参考系统：

| 维度 | Claude Code | Codex | OpenClaw | Hermes-Agent |
|------|------------|-------|----------|--------------|
| 多Agent模型 | Agent tool + subagent_type | spawn/wait/list/close + agent_jobs | sessions_spawn/send (A2A) | delegatetask (ThreadPool) |
| Agent间通信 | 通过父Agent | mailbox 模式 | sessions_send | heartbeat + callback |
| 深度控制 | subagent_type + depth | agent_max_depth | 无 | max_spawn_depth=3 |
| 并发模型 | 异步 spawn | tokio async | Promise.all | ThreadPoolExecutor |
| 沙箱 | git worktree | read-only/workspace-write | 无 | Docker/SSH/Daytona等 |

**Jarvis 的选择**：层级组织树 + Agent 自治通信 + 主管全权控制，这是四个竞品都没有完整覆盖的模式。

## 2. 核心模型

### 2.1 组织架构

```
                     ┌──────────────┐
                     │  Supervisor  │  ← Lv.N (最高层)
                     │  (CEO Agent) │
                     └──────┬───────┘
                            │ spawn_agent
              ┌─────────────┼─────────────┐
              ▼             ▼             ▼
        ┌──────────┐ ┌──────────┐ ┌──────────┐
        │ Dept A   │ │ Dept B   │ │ Dept C   │  ← Lv.N-1 (部门负责人)
        │ (研发主管) │ │ (测试主管) │ │ (架构主管) │
        └────┬─────┘ └────┬─────┘ └────┬─────┘
             │            │            │
      ┌──────┼──────┐     │            │
      ▼      ▼      ▼     ▼            ▼
    ┌────┐┌────┐┌────┐┌────┐     ┌────┐
    │dev1││dev2││dev3││QA1 │     │arch│    ← Lv.1 (执行者)
    └────┘└────┘└────┘└────┘     └────┘
```

### 2.2 Agent 身份

```typescript
interface AgentIdentity {
  agentId: string;          // 唯一标识
  role: string;             // 角色名（developer, qa, architect...）
  department: string;       // 所属部门/团队
  level: number;            // 层级（0 = 顶层主管）
  parentId: string | null;  // 上级 Agent ID
  capabilities: string[];   // 能力标签
  peers: string[];          // 同级 Agent ID 列表
}
```

### 2.3 通信规则

| 规则 | 说明 |
|------|------|
| **纵向汇报** | 下级完成任务 → `report(message)` → 直属上级 |
| **横向协作** | 同级 Agent 可以 `talk_to(targetId, request)` |
| **跨部门协作** | 通过上级协调 → 上级收到请求后转发给目标部门 |
| **逐级上报** | 同级解决不了 → `escalate(message)` → 上级 |
| **主管干预** | 上级随时 `pause(id)` / `resume(id)` / `redirect(id, task)` / `replace(id, config)` |

### 2.4 Agent 生命周期

```
  pending ──► running ──► completed
                 │
                 ├──► paused ──► running (resume)
                 │
                 ├──► redirected ──► running (新任务)
                 │
                 └──► replaced ──► 新 Agent 接管
                 │
                 └──► failed
```

## 3. 现有基础设施审计

### 3.1 已具备

| 模块 | 状态 | 说明 |
|------|------|------|
| packages/agent | 就绪 | AgentLoop 完整（LLM调用、tool dispatch、retry、context compaction、skill匹配） |
| packages/tools | 就绪 | 15个工具（bash/file/glob/grep/web/task/skill等） |
| packages/shared | 就绪 | 共享类型和工具 |
| packages/store | 就绪 | JSONL session + Markdown memory |
| packages/skills | 就绪 | Skill 加载/匹配/执行 |
| packages/hooks | 就绪 | Hook 注册和执行 |
| packages/cli | 就绪 | CLI 入口 |
| packages/tui | 基础 | Claude Code Kit TUI 基础渲染 |
| packages/subagents | 骨架 | SubagentPool/Runner 模型定义，但未接入 AgentLoop |

### 3.2 欠缺（需要先实现）

| 缺失项 | 影响 | 优先级 |
|--------|------|--------|
| **AgentRegistry** — Agent 身份注册与发现 | Agent 无法知道"组织中有谁" | **Phase 0** |
| **AgentMailbox** — 每个 Agent 的收件箱 | Agent 无法接收其他 Agent 的消息 | **Phase 0** |
| **Persistent AgentLoop** — Subagent 的独立 AgentLoop 实例 | 子 Agent 只有单次 runTurn，无法持续工作 | **Phase 0** |
| **Agent-to-Agent 通信工具** (talk_to, report, escalate) | Agent 无法"讨论" | **Phase 0** |
| **Supervisor 控制工具** (pause/resume/redirect/replace) | 主管无法干预 | **Phase 0** |
| **Organization Builder** — 声明式组织构建 | 每次手动拼配置 | **Phase 1** |
| **真实并发** — 移除 SubagentPool 的序列化锁 | spawn 多个 Agent 实际串行 | **Phase 1** |
| **Blackboard** — 共享工作区 | 同团队 Agent 需要一个轻量共享上下文 | **Phase 1** |
| **TUI 仪表盘** — 多 Agent 状态面板 | 主管看不到全局状态 | **Phase 2** |

## 4. 架构设计

### 4.1 模块结构

```
packages/
├── agent/          # AgentLoop（不变，作为每个 Agent 的核心运行时）
├── organization/   # NEW: 组织编排层
│   ├── src/
│   │   ├── org-builder.ts    # 声明式组织构建器
│   │   ├── registry.ts       # AgentRegistry — 身份注册与发现
│   │   ├── mailbox.ts        # AgentMailbox — 消息收件箱
│   │   ├── supervisor.ts     # Supervisor — 主管控制逻辑
│   │   ├── blackboard.ts     # Blackboard — 团队共享工作区
│   │   ├── lifecycle.ts     # 生命周期事件(paused/resumed/redirected...)
│   │   ├── tools/
│   │   │   ├── spawn-agent.ts   # 派发子Agent
│   │   │   ├── talk-to.ts# Agent间通信
│   │   │   ├── report.ts# 向上级汇报
│   │   │── escalate.ts # 逐级上报
│   │   │   ├── pause-agent.ts # 暂停Agent
│   │   │   ├── resume-agent.ts
│   │   │   ├── redirect-agent.ts
│   │   │── replace-agent.ts
│   │   │   └── list-agents.ts   # 列出组织成员
│   │   │── index.ts
│   └─ package.json
├── subagents/ # 重构为轻量 runner
│   ├─ src/
│   │   ├── runner.ts# 简化：只负责启动独立的 AgentLoop
│   │   └── index.ts
│   └─ package.json
└── tui/ # 更新
```

### 4.2 核心数据流

```
1. Supervisor 启动 → AgentLoop.run() + Organization 上下文
                   ├── AgentRegistry 注册（role='supervisor', level=0）
                   └── TUI dashboard 初始化

2. Supervisor 派发任务 → spawn_agent({ role: 'developer', task: '...' })
                   ├── OrgBuilder 从配置创建子 Agent 的 AgentLoop
                   ├── AgentRegistry 注册子 Agent
                   ├── 子 AgentLoop.run() 在独立上下文启动
                   └── 返回 agentId + 初始状态给 Supervisor

3. Worker Agent 收到任务 → 自主推理 + 执行
                          ├── 需要讨论 → talk_to('qa-1', '这个模块的测试怎么设计?')
│                                    ├── AgentMailbox.deliver(qa-1, message)
│                                    └── qa-1 AgentLoop 收到消息（作为 user message 注入）
                          ├── 需要上报 → report('任务完成，结果如下...')
                          └── 自己搞不定 → escalate('这个问题超出我的工具范围')

4. 主管干预 → pause_agent('dev-1')
              ├── Supervisor 调用 agent.pause()
              ├── Agent 暂停当前执行
              ├── AgentRegistry 状态更新
              └── Supervisor 可以 redirect/replace/resume
```

### 4.3 AgentMailbox 设计

每个 Agent 有一个收件箱，其他 Agent 的 talkto 消息投递到这个收件箱。AgentLoop 在每个 turn 开始时检查收件箱，有新消息则注入为 user message。

```typescript
interface AgentMailbox {
  deliver(senderId: string, message: string): void;
  poll(): Array<{ senderId: string; message: string; timestamp: number }>;
  clear(): void;
}

// AgentLoop 每轮开始时:
const incoming = this.mailbox.poll();
for (const msg of incoming) {
  messages.push({
    role: 'user',
    content: `[Message from ${msg.senderId}]: ${msg.message}\n\n(You can reply with talk_to('${msg.senderId}', your_response))`
  });
}
```

### 4.4 AgentRegistry 设计

```typescript
interface AgentRegistry {
  register(identity: AgentIdentity): void;
  unregister(agentId: string): void;
  update(agentId: string, partial: Partial<AgentIdentity>): void;
  get(agentId: string): AgentIdentity | null;
  listByDepartment(department: string): AgentIdentity[];
  listByLevel(level: number): AgentIdentity[];
  listPeers(agentId: string): AgentIdentity[];     // 同级同部门
  listSubordinates(agentId: string): AgentIdentity[];
  getSupervisor(agentId: string): AgentIdentity | null;
}
```

### 4.5 Organization Builder (声明式)

```typescript
const org = new OrgBuilder()
  .supervisor({
    model: { provider: 'anthropic', model: 'claude-sonnet-4-6' },
    tools: ['spawn_agent', 'pause_agent', 'resume_agent', 'redirect_agent', 'replace_agent', 'list_agents', 'talk_to'],
    systemPrompt: '你是技术总监。分配任务、监督进度、解决跨团队协调问题。',
  })
  .team({
    name: '研发部',
    supervisor: {
      model: { provider: 'anthropic', model: 'claude-haiku-4-5' },
      tools: ['spawn_agent', 'talk_to', 'report'],
    },
members: [
      {
        role: 'frontend-dev',
        model: { provider: 'deepseek', model: 'deepseek-v4' },
        tools: ['bash', 'file_read', 'file_write', 'file_edit', 'glob', 'grep'],
      },
      { role: 'backend-dev', ... },
    ],
  })
  .team({ name: '测试部', ... })
  .build();

// build() 返回:
// {
//   agents: Map<string, AgentInstance>,
//   registry: AgentRegistry,
//   topology: OrganizationTopology,
// }
//
// 不自动启动 — 由调用方决定何时 .run()
```

### 4.6 Organization Topology（拓扑快照）

```typescript
interface OrganizationTopology {
  root: string;                              // supervisor agentId
  tree: Map<string, string[]>;                // parentId → [childIds]
  departments: Map<string, string[]>;          // dept名 → [agentIds]
  agentRecords: Map<string, AgentIdentity>;    // agentId → identity
}
```

## 5. Supervisor 的"仪表盘"(Dashboard)

主管的 TUI 视图不是流式 token 输出，而是结构化状态面板：

```
┌─ Organization: MyProject ──────────────────────────────────┐
│ Supervisor ○ monitoring                                    │
├─ 研发部 ──────────────────────────────────────────────────┤
│  dev-1  ● running  "正在实现认证模块..."        [turn 3/10]  │
│  dev-2  ● running  "正在写数据库迁移..."        [turn 2/8]   │
│  dev-3  ○ idle                                              │
│  主管    ○ monitoring                                       │
├─ 测试部 ──────────────────────────────────────────────────┤
│  qa-1   ◐ paused   "等待 dev-1 完成..."                     │
├─ 最近通信 ────────────────────────────────────────────────┤
│  [14:32] dev-1 → qa-1: "认证模块测试用例你写还是我写？"      │
│  [14:33] qa-1 → dev-1:  "你写单元测试，我写集成测试"         │
│  [14:35] dev-1 → supervisor: "report: 认证模块完成"          │
├─ Blackboard: 研发部 ──────────────────────────────────────┤
│  auth_module/tests:   ✅ 已完成                            │
│  db_migation/status:  🔄 进行中                            │
│  api_spec/endpoints:  📋 [/auth/login, /auth/refresh...]   │
└────────────────────────────────────────────────────────────┘
```

主管可以：
- `Ctrl+P` — 选择一个 Agent，pause
- `Ctrl+R` — 选择一个 Agent，redirect（输入新任务）
- `Ctrl+X` — 选择一个 Agent，replace（选择新配置）
- 鼠标/键盘选择通信条目查看详情

## 6. 黑（Blackboard）

同团队 Agent 共享一个 Key-Value 存储，而非共享 LLM 上下文：

```typescript
interface Blackboard {
  read(key: string): string | null;
  write(key: string, value: string, agentId: string): void;
  list(prefix?: string): Record<string, string>;
  watch(callback: (key: string, value: string, agentId: string) => void): void;
}
```

Agent 通过工具读写黑板。黑板写入时通知同团队其他 Agent（作为上下文注入）。

**设计选择：不共享 LLM 上下文**。如果 5 个 Agent 各自有 20K token 的对话历史，全部共享给每个 Agent 会导致上下文爆炸。黑板提供最小化的共享状态，Agent 各自维护自己的上下文。

## 7. 实施阶段

### Phase 0: Agent 基础设施（优先级最高）

**目标**：让一个 Agent 能"知道组织中有谁"并能通信。

| 任务 | 说明 |
|------|------|
| AgentIdentity + AgentRegistry | 身份注册、发现、查询 |
| AgentMailbox | 每个 Agent 的消息收件箱 |
| AgentLoop 集成 Mailbox | 每 turn 开始时 poll 收件箱 |
| talk_to 工具 | Agent 间点对点通信 |
| report 工具 | 向上级汇报 |
| escalate 工具 | 逐级上报 |
| list_agents 工具| 查看组织成员 |
| Persistent Subagent AgentLoop | SubagentRunner 使用独立 AgentLoop 实例而非单次 runTurn |
| spawn_agent 工具 | 派发子 Agent（替换当前空壳设计） |
| 移除 SubagentPool 序列化锁 | 真正并发 |

**验证**：Supervisor + 2 个 Worker 能互相发现、通信、汇报。

### Phase 1：主管控制 + 组织构建

| 任务 | 说明 |
|------|------|
| Organization Builder | 声明式构建组织 |
| Superisor 控制工具 | pause/resume/redirect/replace |
| Agent 生命周期事件 | paused/resumed/redirected/replaced 状态变更 |
| Blackboard | 团队共享工作区 |
| Organization Topology | 组织结构快照 |

**验证**：主管可暂停/重定向/替换任何 Worker。

### Phase 2: TUI 仪表盘

| 任务 | 说明 |
|------|------|
| 多 Agent 状态面板 | 层次化 Agent 列表 + 状态 |
| 通信日志面板 | 最近通信历史 |
| Blackboard 面板 | 团队共享状态可视化 |
| Supervisor 快捷键 | Ctrl+P/R/X 等控制操作 |

**验证**：TUI 中可看到完整组织状态并执行控制操作。

## 8. 关键设计决策

### 8.1 为什么每个 Agent 是独立 AgentLoop 而非单次 runTurn

当前 SubagentRunner 调用 `runTurn(task)` 一次性执行。这在组织模型中不够——Agent 需要：
- 多轮推理（执行任务 → 找人讨论 → 根据讨论结果调整 → 继续执行）
- 等待其他 Agent 回复后继续
- 被主管暂停后恢复

### 8.2 为什么 Mailbox 而非直接注入 message

Agent 不应该被随时打断。Mailbox 模式让 Agent 在每轮开始时检查新消息，保证当前回合的思维链条不被中断。来自 Codex 的 mailbox 模式。

### 8.3 为什么 Blackboard 而非共享上下文

如果一个组织有 5 个 Agent，每个的对话历史 20K tokens，共享会导致 100K tokens 的超长上下文。Blackboard 提供最少数共享状态（~500 bytes），Agent 自己决定何时读取。

### 8.4 为什么 synchronized agent starts 需要移除

当前 SubagentPool._execute() 有一个 `this.lock` 序列化所有 Agent 启动。这意味着 spawn 3 个 Agent 实际上是串行的。在组织模型中，多个 Worker 必须真正同时工作。

## 9. 成功标准

- [ ] Supervisor 可以派发 3 个 Worker Agent，3 个同时运行
- [ ] Worker A可以 talkto Worker B，B 收到并回复
- [ ] Supervisor 可以 pause/rEsume/redirect/replace 任何 Worker
- [ ] Worker 可以 report 给 Supervisor
- [ ] Worker 可以 escalate 超出能力范围的问题
- [ ] 组织拓扑在 AgentRegistry 中是一致且可查询的
- [ ] TUI 显示组织状态面板（Phase 2）
- [ ] 所有现有测试通过（无回归）

## 10. 不在范围内

- 3 层以上的深层嵌套（Phase 0-1 只做 2 层）
- 跨进程/跨网络 Agent 通信（单进程优先）
- Docker/OS 沙箱（Codex 模型，后续）
- Agent 持久化/重启恢复（后续）
- Agent Worktree 隔离（Claude Code 模式，后续）
- CSV 批量 spawning（CoDex agent_jobs 模式，后续）
- 自学习/技能自创建（Hermes-Agent 模式，后续）