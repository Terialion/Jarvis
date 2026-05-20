# Jarvis TypeScript 全栈迁移设计

## 概述

将 Jarvis 后端从 Python（~44K 行，250 文件）全量迁移到 TypeScript，前端 TUI 同步替换为
claude-code-kit（Ink fork + React 组件库）。最终形成纯 TypeScript 单体仓库
（pnpm workspace），消除 Python 依赖和跨语言 bridge。

对标架构：Claude Code / Gemini CLI（全栈 TypeScript）。

## 核心决策

| 决策 | 选型 | 理由 |
|------|------|------|
| 语言 | 纯 TypeScript | 对标 Claude Code，单语言栈无 IPC 开销 |
| TUI 引擎 | claude-code-kit (ink-renderer) | 成熟开源 Ink fork，cell 级 diff + 鼠标 + 搜索 |
| 项目结构 | pnpm monorepo | 模块独立、可持久化、可独立发布 |
| LLM Provider | OpenAI-compatible SDK | 用 `openai` npm 包，兼容 DeepSeek/Qwen/OpenAI |
| 存储 | JSONL + Markdown 文件 | 与 Python 版兼容，无需迁移数据 |
| 子进程 | Node.js `child_process` | 替代 Python `subprocess.run` |
| 插件系统 | 纯 TS 实现 | 原 Python 插件需重写，TS 插件可动态 import |

## 项目结构

```
jarvis/
├── pnpm-workspace.yaml
├── package.json              # root: scripts, devDependencies
├── tsconfig.base.json        # shared TS config
├── turbo.json                # build orchestration
│
├── packages/
│   ├── shared/               # 共享类型和工具（无运行时依赖）
│   │   ├── src/
│   │   │   ├── types.ts      # AgentEvent, ToolCall, TurnContext, Message...
│   │   │   ├── schemas.ts    # JSON Schema 定义
│   │   │   ├── env.ts        # 环境检测
│   │   │   └── index.ts
│   │   └── package.json
│   │
│   ├── agent/                # Agent 核心循环 + LLM 调用
│   │   ├── src/
│   │   │   ├── loop.ts       # AgentLoop（从 loop.py 迁移）
│   │   │   ├── model.ts      # LLM Provider 抽象
│   │   │   ├── context.ts    # Context 构建 + token 预算
│   │   │   ├── summary.ts    # 回复摘要
│   │   │   ├── retry.ts      # 重试/回退策略
│   │   │   ├── events.ts     # 事件系统
│   │   │   └── index.ts
│   │   └── package.json
│   │
│   ├── tools/                # 工具注册 + 执行
│   │   ├── src/
│   │   │   ├── registry.ts   # ToolRegistry
│   │   │   ├── runtime.ts    # ToolRuntime + ApprovalGate
│   │   │   ├── builtin/
│   │   │   │   ├── bash.ts
│   │   │   │   ├── file-read.ts
│   │   │   │   ├── file-write.ts
│   │   │   │   ├── file-edit.ts
│   │   │   │   ├── glob.ts
│   │   │   │   ├── grep.ts
│   │   │   │   ├── web-search.ts
│   │   │   │   └── web-fetch.ts
│   │   │   └── index.ts
│   │   └── package.json
│   │
│   ├── skills/               # Skill 系统
│   │   ├── src/
│   │   │   ├── registry.ts
│   │   │   ├── loader.ts
│   │   │   ├── matcher.ts
│   │   │   ├── executor.ts
│   │   │   ├── lifecycle.ts
│   │   │   └── index.ts
│   │   └── package.json
│   │
│   ├── hooks/                # Hook 系统
│   │   ├── src/
│   │   │   ├── registry.ts
│   │   │   ├── executor.ts
│   │   │   └── index.ts
│   │   └── package.json
│   │
│   ├── store/                # 存储层
│   │   ├── src/
│   │   │   ├── session.ts    # JSONL session store
│   │   │   ├── memory.ts     # Markdown memory store
│   │   │   └── index.ts
│   │   └── package.json
│   │
│   ├── mcp/                  # MCP 协议
│   │   ├── src/
│   │   │   ├── client.ts
│   │   │   ├── server.ts
│   │   │   ├── transport.ts
│   │   │   └── index.ts
│   │   └── package.json
│   │
│   ├── plugins/              # 插件系统
│   │   ├── src/
│   │   │   ├── registry.ts
│   │   │   ├── loader.ts
│   │   │   └── index.ts
│   │   └── package.json
│   │
│   ├── subagents/            # 子 Agent 池
│   │   ├── src/
│   │   │   ├── pool.ts
│   │   │   ├── runner.ts
│   │   │   └── index.ts
│   │   └── package.json
│   │
│   ├── cli/                  # CLI 入口
│   │   ├── src/
│   │   │   ├── main.ts       # CLI 参数解析 + 路由
│   │   │   ├── commands.ts   # 斜杠命令注册
│   │   │   └── index.ts
│   │   └── package.json
│   │
│   └── tui/                  # Claude Code Kit TUI
│       ├── src/
│       │   ├── entry.tsx
│       │   ├── app.tsx
│       │   ├── vendor/       # 从 claude-code-kit 复制
│       │   │   ├── ink-renderer/
│       │   │   ├── ui/
│       │   │   └── shared/
│       │   └── index.ts
│       └── package.json
│
├── tests/                    # 集成测试
│   ├── agent/
│   ├── tools/
│   └── cli/
│
└── skills/                   # 内置 Skill 文件 (*.md)
```

## 依赖图

```
          shared  ←── 所有包的公共类型
            ↑
    ┌───────┼───────────────┐
    ↑       ↑       ↑       ↑
  store   tools   hooks   mcp
    ↑       ↑       ↑       ↑
    └───────┴───────┴───────┤
            ↑               ↑
          agent ←── skills──┤
            ↑               ↑
    ┌───────┴───────┐       ↑
  subagents       plugins    ↑
    ↑               ↑       ↑
    └───────────────┴───────┤
            ↑               ↑
           cli ─────────────┘
            ↑
           tui (UI 层，只依赖 cli)
```

## Python → TypeScript 模块映射

| Python (~44K 行) | TypeScript (~35K 行) | 说明 |
|---|---|---|
| `agent/loop.py` (1.8K) | `packages/agent/loop.ts` | Agent 循环核心 |
| `agent/tools.py` (2.7K) | `packages/agent/` + `packages/tools/` | 拆分为工具适配器 + 工具运行时 |
| `agent/model.py` (716) | `packages/agent/model.ts` | LLM Provider |
| `agent/context.py` (526) | `packages/agent/context.ts` | Context 构建 |
| `core/tools/` (1.4K) | `packages/tools/` | 工具注册表 |
| `core/routing/` (2.7K) | **删除** | Python 路由层，TS 不需要 |
| `core/policy/` (1.1K) | `packages/tools/` | 合并到 ApprovalGate |
| `core/hooks/` (384) | `packages/hooks/` | 独立 Hook 包 |
| `core/plugins/` (436) | `packages/plugins/` | 独立 Plugin 包 |
| `core/subagents/` (565) | `packages/subagents/` | 独立 Subagent 包 |
| `core/react_readiness/` (1.1K) | `packages/agent/retry.ts` | 合并到重试逻辑 |
| `core/llm/` (1.4K) | `packages/agent/model.ts` | 合并到 Provider 层 |
| `core/command_runner.py` (147) | `packages/tools/builtin/bash.ts` | child_process 替代 |
| `core/file_editor.py` (250) | `packages/tools/builtin/file-*.ts` | fs 替代 |
| `core/tokens.py` (120) | `packages/agent/context.ts` | tiktoken → js-tiktoken |
| `core/skill_harness/` (1.8K) | `packages/skills/` | 重写为 TS |
| `gateway/mcp.py` (472) | `packages/mcp/` | 独立 MCP 包 |
| `store/session_store.py` (890) | `packages/store/session.ts` | JSONL → TS |
| `store/memory_store.py` (184) | `packages/store/memory.ts` | Markdown → TS |
| `web/` (2.6K) | `packages/tools/builtin/web-*.ts` | Web 搜索/抓取 |
| `coding/` (1.2K) | `packages/cli/` | 合并到 CLI 命令 |
| `config/` (934) | `packages/cli/` | 配置系统归入 CLI |
| `skills/` (3.2K) | `packages/skills/` | Skill 系统 |
| `cli.py` (4.9K) | `packages/cli/main.ts` | CLI 入口 |
| `cli_ui/` (2.6K) | `packages/tui/` | Claude Code Kit 替代 |

## 分阶段实施

### Phase 0: 基础设施搭建

建立 monorepo 骨架：pnpm workspace、tsconfig、turbo、CI。

### Phase 1-4: 自底向上，从基础设施到 TUI

| Phase | 内容 | 依赖 | 验证标准 |
|---|---|---|---|
| **P1** | `shared` + `store` + `tools` | 无 | 类型编译通过 + session/memory 读写测试通过 + bash/file/glob/grep 工具测试通过 |
| **P2** | `agent` (loop/model/context/retry/events) | P1 | AgentLoop 能独立完成一轮对话（mock LLM） |
| **P3** | `skills` + `hooks` + `mcp` + `plugins` + `subagents` | P2 | Skill 加载/匹配/执行测试通过 |
| **P4** | `cli` + `tui` (claude-code-kit) | P3 | 完整 `jarvis` CLI 命令可运行 + TUI 显示正确 |

### 迁移策略

**双轨运行**：Python 旧版和 TS 新版可以共存（cli.py 保留，TS CLI 作为新入口）。
两个版本共享相同的 JSONL session 格式和 MEMORY.md 文件格式。
当 TS 版功能完整后，删除 Python 代码。

## 风险 & 回退

- **最大风险**: P2 Agent 循环是核心，如果 LLM 行为与 Python 版不一致需要大量调试
- **回退策略**: 每 Phase 独立可测，Python 版始终保留可用，TS 版不替换而是并行
- **数据兼容**: 存储格式保持不变（JSONL + Markdown），可在两个实现间切换

## 相关文档

- [2026-05-20-claude-code-kit-tui-replacement-design.md](2026-05-20-claude-code-kit-tui-replacement-design.md) — TUI 替换原始设计
- [2026-05-19-multi-agent-tui-design.md](2026-05-19-multi-agent-tui-design.md) — 多 Agent TUI 设计
- claude-code-kit 源码: `D:/agent/Jarvis/claude-code-kit-main.zip`
- Python 后端分析: 见 exploration agent 报告（44,166 行，250 文件）
