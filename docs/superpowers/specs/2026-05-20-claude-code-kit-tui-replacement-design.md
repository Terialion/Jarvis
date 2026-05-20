# Claude Code Kit TUI 替换设计

## 概述

将 Jarvis TUI 从标准 `ink` npm 包全量替换为 claude-code-kit 开源项目的
`packages/ink-renderer` + `packages/ui` 作为底层渲染引擎。采用自顶向下方式
（方式 2），直接使用 `packages/ui` 的成熟组件（REPL、MessageList、PromptInput 等），
将 JarvisBridge 的数据适配到这些组件的 props 上。

## 核心思路

claude-code-kit 的 `REPL` 组件已经是一个完整的 chat TUI 框架，接收以下 props:

- `onSubmit(prompt)` — 用户提交输入
- `messages: Message[]` — 已完成的消息列表
- `isLoading` — 是否正在 streaming
- `streamingContent` — 当前 streaming 增量文本
- `permissionRequest` — 权限请求
- `statusSegments` — 状态栏信息
- `commands` — 斜杠命令注册

工作就是把 `JarvisBridge` 的事件流适配到 `REPL` 的 props 上。

## 组件映射

| 旧 Jarvis 组件 | 替换方式 |
|---|---|
| `entry.tsx` (Ink render + alt screen) | `createRoot()` + `<AlternateScreen>` |
| `app.tsx` (状态管理 + 布局) | `<REPL>` 组件替代大部分逻辑 |
| `MessageList.tsx` | `packages/ui` 的 `MessageList` |
| `PromptInput.tsx` | `packages/ui` 的 `PromptInput` |
| `MarkdownRenderer.tsx` | `packages/ui` 的 `Markdown` |
| `StatusBar.tsx` | `REPL` 的 `statusSegments` prop |
| `Spinner.tsx` | `packages/ui` 的 `Spinner` |
| `ShimmerText.tsx` | `packages/ui` 的 `StreamingText` |
| `TextInput.tsx` | 删除（PromptInput 自带） |
| `AgentPanel.tsx` | 保留，后续迁移 |
| `DiffBlock.tsx` | 保留，后续换 `DiffView` |
| `ToggleBlock.tsx` | `packages/ui` 的键盘提示系统 |
| `terminal/scrollback.ts` | 删除（ScrollBox 虚拟滚动替代） |
| `terminal/viewport.ts` | 删除（ink-renderer 自带 viewport） |
| `bridge.ts` | **保留并适配** |
| `types.ts` | **保留并扩展** |

## 项目结构

```
jarvis_tui/
├── src/
│   ├── entry.tsx          ← createRoot + AlternateScreen + App
│   ├── app.tsx            ← REPL + JarvisBridge 适配逻辑
│   ├── bridge.ts          ← 保留，基本不变
│   ├── types.ts           ← 保留，扩展 Message 类型
│   ├── commands.ts        ← Jarvis 斜杠命令注册
│   ├── components/        ← 仅保留 DiffBlock、AgentPanel
│   │   ├── DiffBlock.tsx
│   │   └── AgentPanel.tsx
│   └── vendor/            ← 从 claude-code-kit 复制
│       ├── ink-renderer/  ← packages/ink-renderer/src/
│       ├── ui/            ← packages/ui/src/
│       └── shared/        ← packages/shared/src/
├── package.json           ← 更新依赖
└── tsconfig.json          ← 更新 paths
```

## 分阶段实施

### P1: 基础替换 — 能启动 TUI 看到界面

1. 复制 claude-code-kit 的 packages/ink-renderer、packages/ui、packages/shared 到 vendor/
2. 更新 package.json 依赖（去掉 ink，加 react-reconciler、yoga-layout 等）
3. 重写 entry.tsx：用 createRoot() + AlternateScreen
4. 重写 app.tsx：用 REPL 组件，空 props，先能看到界面框架
5. 确保 `npm run build` 和 `tsc --noEmit` 通过

验证: 启动后能看到 REPL 框架（StatusLine + PromptInput + 快捷键提示）

### P2: 数据适配 — Agent 对话流程跑通

1. 扩展 types.ts：对齐 claude-code-kit 的 Message 类型
2. 改造 app.tsx：
   - JarvisBridge 事件 → REPL props 映射
   - handleChunk → streamingContent 更新
   - handleDone → messages 追加
   - handleSubmit → onSubmit
3. 适配 commands.ts：注册 Jarvis 斜杠命令
4. 适配状态栏：模型名、延迟、token 数 → statusSegments

验证: 发送消息 → Python Agent 响应 → TUI 正确展示 thinking/工具/答案

### P3: 功能对齐 — 完整功能可用

1. 迁移 DiffBlock → DiffView（claude-code-kit 的 DiffView 组件）
2. 适配 AgentPanel（子 agent 状态展示）
3. 注册 Jarvis 自定义 keybindings（Ctrl+T/Ctrl+O/Ctrl+A/Shift+Tab）
4. 删除不再需要的旧组件文件
5. 清理 npm 依赖（去掉仅旧代码使用的包）

验证: 所有现有功能正常（thinking toggle、tools toggle、agent panel、diff 显示）

## 风险 & 回退

- **最大风险**: claude-code-kit 的 ink-renderer 是 Ink 的深度 fork，API 可能有差异
- **回退策略**: P1 在单独分支 `feature/claude-code-kit-tui` 上做，
  不影响 `feature/diff-display-and-plugin-packaging` 分支
- **验证节点**: P1 完成时就可以判断方案是否可行，不可行则放弃，代价很小
- **数据恢复**: vendor/ 目录可直接删除恢复，原有组件 git revert 即可

## Python → TypeScript 全栈迁移展望

TUI 替换完成后，后续可逐步将 Python Agent 后端迁移到 TypeScript：

### 迁移路线图

| 阶段 | 模块 | 工作量估计 | 说明 |
|------|------|-----------|------|
| **S1** | Agent Loop + Types | ~3K 行 | `loop.py` / `types.py` / `events.py` → TS |
| **S2** | 工具运行时 | ~5K 行 | `bash`/`glob`/`grep`/`file_read`/`file_write`/`file_edit`/`web_search`/`web_fetch` 用 Node.js 原生实现 |
| **S3** | Context 管理 | ~3K 行 | session/compaction/summary → TS |
| **S4** | Skills 系统 | ~3K 行 | skill discovery/matching/execution → TS |
| **S5** | Hooks 系统 | ~2K 行 | pre/post tool hooks → TS |
| **S6** | MCP + Plugins | ~4K 行 | MCP client + plugin registry → TS |
| **S7** | Subagents | ~3K 行 | spawn/wait/list/close agent pool → TS |
| **S8** | CLI 入口 + 配置 | ~7K 行 | `cli.py` → TS CLI entry |
| **S9** | 测试 + 清理 | ~5K 行 | 迁移测试用例，删除 Python 代码 |
| | **合计** | **~35K 行** | 预计 3-6 个月（取决于人力） |

### 关键设计决策（待细化）

- LLM Provider 层：继续用 OpenAI-compatible API 还是直接用 Anthropic SDK
- 插件系统：是否保持 Python 插件兼容（通过子进程调用）
- 数据库/存储：Python 的 SQLite 切换到 TypeScript 的 better-sqlite3
- 配置系统：TOML 配置解析用 Node.js 库替代

### S1 详细预览（最关键的 Agent Loop）

```
src/jarvis/agent/loop.py          →  jarvis_tui/src/agent/loop.ts
src/jarvis/agent/types.py         →  jarvis_tui/src/agent/types.ts
src/jarvis/agent/events.py        →  jarvis_tui/src/agent/events.ts
src/jarvis/agent/context.py       →  jarvis_tui/src/agent/context.ts
src/jarvis/agent/model.py         →  jarvis_tui/src/agent/model.ts
src/jarvis/agent/tools.py         →  jarvis_tui/src/agent/tools.ts
src/jarvis/agent/summary.py       →  jarvis_tui/src/agent/summary.ts
src/jarvis/agent/prompt_builder.py → jarvis_tui/src/agent/prompt_builder.ts
```

核心流程保持不变：`context build → model call → tool calls → tool results → final answer`，
只是从 Python async/await 变为 TypeScript async/await。Tool call 生命周期（begin/end/fail）
和 turn-scoped state discipline 保持一致。

### 迁移期间的双轨策略

在完全迁移完成前，两种语言可以共存：
1. 新 TypeScript Agent Loop 通过 `bridge.ts` 的反向模式调用 Python 工具
2. 或者 Python 工具逐步被 TypeScript 实现替代
3. 最终 Python 只保留在 CI/测试脚本中

## 相关文档

- [2026-05-19-multi-agent-tui-design.md](2026-05-19-multi-agent-tui-design.md) — 多 Agent TUI 设计
- [2026-05-20-diff-display-and-plugin-packaging-design.md](2026-05-20-diff-display-and-plugin-packaging-design.md) — Diff 显示和插件打包
- claude-code-kit 源码: `D:/agent/Jarvis/claude-code-kit-main.zip`
