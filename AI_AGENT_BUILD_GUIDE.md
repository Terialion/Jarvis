# AI Agent 从零实现完全指南

> 本文档基于 Jarvis（Just A Rather Very Intelligent System）的 TypeScript 实现源码分析编写。
> 目标是：读完本文档后，你能根据其中的代码片段和原理说明，用任意语言实现一个基本的 AI Agent。

---

## 目录

1. [整体架构](#1-整体架构)
2. [Agent 循环（ReAct Loop）](#2-agent-循环react-loop)
3. [LLM 提供者（Model/Provider）](#3-llm-提供者modelprovider)
4. [Tool 系统](#4-tool-系统)
5. [Context 管理](#5-context-管理)
6. [5 阶段压缩管线（Compaction）](#6-5-阶段压缩管线compaction)
7. [Skill 系统](#7-skill-系统)
8. [Session / Memory 持久化](#8-session--memory-持久化)
9. [MCP 集成](#9-mcp-集成)
10. [Sub-Agent / 多 Agent 系统](#10-sub-agent--多-agent-系统)
11. [CLI 入口](#11-cli-入口)
12. [从零实现一个 Minimal Agent](#12-从零实现一个-minimal-agent)

---

## 1. 整体架构

```
┌──────────────────────────────────────┐
│           CLI Entry (main.ts)         │
│  参数解析 · 环境加载 · 模块组装      │
└──────────────────┬───────────────────┘
                   │
┌──────────────────▼───────────────────┐
│          AgentLoop (loop.ts)          │
│  ReAct 循环 · Context 构建 · LLM 调用 │
│  Tool 分发 · 压缩 · 失败重试         │
└──────┬──────────────┬───────────────┘
       │              │
┌──────▼──────┐ ┌─────▼──────────────┐
│ LLMProvider │ │   ToolRuntime      │
│ (model.ts)  │ │  PermissionManager │
│ normalizer  │ │  ApprovalGate      │
└──────┬──────┘ └─────┬──────────────┘
       │              │
┌──────▼──────────────▼───────────────┐
│           Supporting Packages        │
│ Skills · Store/Memory · MCP · Hooks │
│ Subagents · Plugins · TUI           │
└─────────────────────────────────────┘
```

**核心接口约定：**

每个模块遵循"协议接口 + 具体实现"模式。`AgentLoop` 通过接口依赖注入获得所有能力：

```typescript
interface AgentDependencies {
  provider: LLMProvider         // 调用 LLM
  tools: ToolRegistry           // 工具定义
  toolRuntime: ToolRuntime      // 工具执行+权限
  skillRegistry: SkillRegistry  // 技能发现
  skillExecutor: SkillExecutor  // 技能匹配
  contextBuilder: ContextBuilder // 上下文组装
}
```

---

## 2. Agent 循环（ReAct Loop）

### 核心原理

Agent 循环是 **Reasoning → Action → Observation** 的迭代过程：

1. **Reasoning**: 把当前上下文（系统提示 + 对话历史 + 工具定义）发给 LLM
2. **Action**: LLM 返回文本回复或工具调用指令
3. **Observation**: 如果是工具调用，执行工具，把结果追加到对话
4. **Loop**: 继续下一次迭代，直到 LLM 给出最终回复

### 核心数据结构

```typescript
// 最重要的两个结构
interface ChatMessage {
  role: 'system' | 'user' | 'assistant' | 'tool';
  content: string;
  messageId: string;
  toolCallId?: string;   // tool 消息关联的调用 ID
  name?: string;         // tool 名称
}

interface TurnResult {
  turnId: string;
  messages: ChatMessage[];     // 本轮所有消息
  answer: string;              // 最终回复
  toolResults: ToolResult[];   // 所有工具执行结果
  stopReason: string;          // 停止原因
  turnsUsed: number;           // 实际轮数
}
```

### 循环逻辑（简化版）

```typescript
async function agentLoop(userMessage: string, maxTurns = 30) {
  const allMessages: ChatMessage[] = [];
  let finalContent = '';
  let stopReason = 'unknown';

  // 1. 添加用户消息
  allMessages.push({ role: 'user', content: userMessage, messageId: uuid() });

  for (let turn = 0; turn < maxTurns; turn++) {
    // 2. 构建 LLM 请求消息（系统提示 + 对话 + 工具定义）
    const llmMessages = buildLlmMessages(systemPrompt, allMessages);
    const toolDefs = toolRegistry.getDefinitions();

    // 3. 调用 LLM
    const response = await provider.chat(llmMessages, toolDefs);

    // 4. 添加 assistant 回复到历史
    allMessages.push({ role: 'assistant', content: response.content, messageId: uuid() });

    // 5. 判断停止条件
    if (response.finishReason === 'stop') {
      finalContent = response.content;
      stopReason = 'stop';
      break;
    }

    // 6. 执行工具调用
    if (response.finishReason === 'tool_calls' && response.toolCalls.length > 0) {
      for (const tc of response.toolCalls) {
        const result = await toolRuntime.execute(tc.name, tc.arguments);
        allMessages.push({
          role: 'tool',
          content: result.content,
          toolCallId: tc.callId,
          name: tc.name,
          messageId: uuid(),
        });
      }
      continue; // 继续下一轮
    }

    // 7. 其他停止条件
    if (response.finishReason === 'length') { /* 截断 */ break; }
    if (response.finishReason === 'content_filter') { /* 过滤 */ break; }
  }

  return { answer: finalContent, stopReason, messages: allMessages };
}
```

### 工具意图检测

当 LLM "描述" 了它想做什么而不是真正调用工具时，需要检测并重新提示：

```typescript
const TOOL_INTENT_MARKERS = [
  'tool_call', '让我试试', '让我来调用', '我来写',
  '好的，让我', 'let me', "i'll", 'i will',
];

function looksLikeToolIntentText(text: string): boolean {
  const lowered = text.toLowerCase();
  return TOOL_INTENT_MARKERS.some(m => lowered.includes(m));
}

// 如果检测到，插入 nudge 消息
if (finishReason === 'retry_with_tool_instruction') {
  allMessages.push({
    role: 'user',
    content: 'You MUST call the appropriate tool function directly — do NOT just say what you will do.',
  });
}
```

### 生命周期控制

Agent 支持中断、暂停、恢复和重定向：

```typescript
class AgentLoop {
  private _interrupted = false;
  private _paused = false;
  private _pausedResolve: (() => void) | null = null;

  // 在每步循环开头检查
  if (this._interrupted) break;
  if (this._paused) {
    await new Promise<void>(resolve => { this._pausedResolve = resolve; });
  }
}
```

---

## 3. LLM 提供者（Model/Provider）

### 核心原理

LLMProvider 封装一个 OpenAI-compatible 的 chat completions API，支持：

1. **流式和非流式** 两种调用模式
2. **Provider 特定消息规范化**（DeepSeek reasoner、Qwen 等）
3. **非原生工具调用模型**的降级（工具描述作为文本注入）
4. **工具名安全转义**（移除非法字符）
5. **指数退避重试**

### 消息规范化（Normalizer）

不同 LLM 提供商对消息格式有不同要求：

```typescript
// 1. 将所有 system 消息合并到最前面
// 2. Qwen: 不能有连续 user 消息
// 3. DeepSeek reasoner: system 内容合并到第一条 user 消息

function normalizeMessages(messages, opts) {
  let result = consolidateSystemMessages(messages);

  if (opts.provider === 'qwen') {
    result = mergeConsecutiveSameRole(result, new Set(['user']));
  }
  if (opts.provider === 'deepseek') {
    if (modelL.includes('reasoner')) {
      result = mergeSystemIntoFirstUser(result);
    }
    result = mergeConsecutiveSameRole(result, new Set(['user', 'assistant']));
  }
  return result;
}
```

### 非原生 Tool Calling

对于不支持原生 function calling 的模型，将工具定义作为文本注入：

```typescript
function injectToolDescriptions(messages, tools) {
  const toolText = tools.map(t =>
    `- ${t.function.name}: ${t.function.description}\n  Parameters: ${formatParams(t.function.parameters)}`
  ).join('\n');

  const systemMsg = messages.find(m => m.role === 'system');
  if (systemMsg) {
    systemMsg.content += `\n\n<tool_schemas>\n${toolText}\n</tool_schemas>`;
  }
  return messages;
}
```

### 流式处理

```typescript
async function chatStream(messages, tools, callbacks) {
  const stream = await openai.chat.completions.create({
    model: '...', messages, tools, stream: true,
  });

  let content = '';
  let reasoningContent = '';
  const toolCallAccumulators = new Map();

  for await (const chunk of stream) {
    const delta = chunk.choices?.[0]?.delta;

    // 文本 token
    if (delta?.content) {
      content += delta.content;
      callbacks?.onToken?.(delta.content);
    }

    // 推理内容（reasoner 模型）
    if (delta?.reasoning_content) {
      reasoningContent += delta.reasoning_content;
      callbacks?.onReasoningDelta?.(delta.reasoning_content);
    }

    // 工具调用（流式累加）
    if (delta?.tool_calls) {
      for (const tc of delta.tool_calls) {
        if (tc.id) toolCallAccumulators.set(tc.index, { id: tc.id, name: '', arguments: '' });
        const acc = toolCallAccumulators.get(tc.index);
        if (tc.function?.name) acc.name += tc.function.name;
        if (tc.function?.arguments) acc.arguments += tc.function.arguments;
      }
    }
  }

  // 组装工具调用
  const toolCalls = [...toolCallAccumulators.values()].map(acc => ({
    callId: acc.id,
    name: acc.name,
    arguments: JSON.parse(acc.arguments || '{}'),
  }));

  return { content, toolCalls, finishReason: 'stop' };
}
```

### Token 估算

使用 CJK-aware 的字符/4 近似法：

```typescript
function estimateTokens(text: string): number {
  if (!text) return 0;
  let total = 0;
  for (const ch of text) {
    const cp = ch.codePointAt(0) ?? 0;
    total += isCJK(cp) ? 1 : 0.25;  // CJK: 1 token/char, 拉丁: 1 token/4 chars
  }
  return Math.ceil(total);
}
```

---

## 4. Tool 系统

### 核心原理

Tool 系统分为四层：

```
ToolRegistry  →  注册/查找/分发工具
ToolRuntime   →  执行编排 + 权限 + 截断
PermissionManager → 三种权限模式
ApprovalGate  →  命令安全检查
```

### ToolRegistry

```typescript
interface ToolEntry {
  name: string;              // 唯一名称，如 "bash"
  toolset: string;           // 分组，如 "terminal", "file"
  schema: Record<string, unknown>;  // OpenAI-format JSON Schema
  handler: (args, context) => string | Promise<string>;  // 处理函数
  checkFn?: () => boolean;          // 可用性检查
  requiresEnv?: string[];           // 必需环境变量
  isAsync?: boolean;
  maxResultSizeChars?: number;      // 输出截断上限
}

class ToolRegistry {
  private tools = new Map<string, ToolEntry>();

  register(entry: ToolEntry): void {
    // MCP 工具可覆盖同名工具，其他情况抛异常
    this.tools.set(entry.name, entry);
  }

  async dispatch(name: string, args, context): Promise<string> {
    const entry = this.tools.get(name);
    if (!entry) return JSON.stringify({ error: `Tool not found: ${name}` });
    try {
      return entry.isAsync
        ? await entry.handler(args, context)
        : entry.handler(args, context);
    } catch (err) {
      return JSON.stringify({ error: `Tool execution failed: ${err.message}` });
    }
  }

  // 返回 OpenAI-format 工具定义（供 LLM 使用）
  getDefinitions(toolNames?: string[]): Record<string, unknown>[] {
    const filtered = toolNames
      ? toolNames.map(n => this.tools.get(n)).filter(Boolean)
      : [...this.tools.values()];
    return filtered.filter(e => this.isAvailable(e)).map(e => e.schema);
  }
}
```

### ToolRuntime

```typescript
class ToolRuntime {
  async execute(name: string, args, context): Promise<ToolResult> {
    // 1. Permission check
    const permissionCheck = this.permissionManager?.check(name, argsKey);
    if (permissionCheck && !permissionCheck.allowed) {
      if (permissionCheck.needsApproval && this.onApprovalNeeded) {
        const approved = await this.onApprovalNeeded({ toolName: name, args, reason, risk });
        if (!approved) return denyResult;
      } else {
        return blockResult;
      }
    }

    // 2. ApprovalGate check (bash commands only)
    if (name === 'bash' && this.approvalGate) {
      const approval = this.approvalGate.checkCommand(args.command);
      if (!approval.safe) return blockResult;
    }

    // 3. Execute
    const raw = await this.registry.dispatch(name, args, context);

    // 4. Truncation
    const maxSize = entry?.maxResultSizeChars ?? this.defaultMaxResultSize;
    if (content.length > maxSize) {
      content = `${content.slice(0, maxSize)}\n...[truncated]`;
    }

    return { callId, name, ok: !isError, content, error, durationMs };
  }
}
```

### PermissionManager（三种模式）

```typescript
type PermissionMode = 'bypass' | 'accept_edits' | 'default' | 'plan';

// 默认风险映射
const RISK_MAP = {
  read_file: 'read_only',  write_file: 'write_approval_required',
  edit_file: 'write_approval_required', bash: 'caution',
  web_search: 'network',   web_fetch: 'network',
  // ... 其他工具
};

class PermissionManager {
  check(toolName, argsKey): PermissionCheckResult {
    if (mode === 'bypass') return { allowed: true };  // 全部放行

    if (mode === 'plan') {  // 只读模式
      if (risk === 'read_only') return { allowed: true };
      return { allowed: false, reason: 'Blocked in plan mode' };
    }

    if (mode === 'accept_edits') {  // 自动批准编辑
      if (['read_only', 'write_approval_required', 'caution'].includes(risk))
        return { allowed: true };
      return { allowed: false, needsApproval: true };
    }

    // default: 只读自动批准，其他需要审批
    if (risk === 'read_only') return { allowed: true };
    return { allowed: false, needsApproval: true };
  }
}
```

### ApprovalGate（命令安全）

```typescript
// 始终阻止的模式
const BLOCKED_PATTERNS = [
  [/rm\s+-rf\s+\/\s*(?:$|[;&])/, 'removing root filesystem'],
  [/\bmkfs\b/, 'creating filesystems'],
  [/\bfork\s*bomb\b/i, 'fork bomb'],
];

// 需要审批的模式
const DANGEROUS_PATTERNS = [
  [/\bsudo\b/, 'privilege escalation'],
  [/\bcurl\b.+\|\s*(?:ba)?sh\b/i, 'curl piped to shell'],
  [/[|>]\s*\/dev\//, 'redirect to device file'],
];

class ApprovalGate {
  checkCommand(command): ApprovalResult {
    for (const [pattern, reason] of BLOCKED_PATTERNS) {
      if (pattern.test(command)) return { safe: false, reason };
    }
    for (const [pattern, reason] of DANGEROUS_PATTERNS) {
      if (pattern.test(command)) return { safe: false, reason: `requires approval: ${reason}` };
    }
    return { safe: true };
  }
}
```

---

## 5. Context 管理

### 核心原理

ContextBuilder 负责组装发送给 LLM 的完整上下文：

1. **Project Context**: CLAUDE.md、JARVIS.md 等指令文件的分层加载
2. **Conversation Context**: 从 SessionStore 加载历史对话
3. **Memory Context**: 用户/项目持久记忆
4. **Skill Context**: 可用技能索引
5. **Context Diff**: 稳定状态下只发送变更（节省 token）

### 分层指令加载

```typescript
class ContextBuilder {
  buildProjectContext(cwdPath, repoRoot, userText): ProjectContext {
    // 1. 全局指令 ~/.jarvis/JARVIS.md
    // 2. 从 cwd 到 repo root 的目录层级（最多 4 层）
    // 3. 用户消息中提到的目录
    const instructionFiles = ['CLAUDE.md', 'JARVIS.md', 'AGENTS.md', 'README.md'];
    // 按优先级合并，总字符上限 32KB
  }
}
```

### Context Diff（节省 Token）

```typescript
// 第一次：发送完整 context
// 后续：只发送变更（settings diff）
private computeContextDiff(turnContext): Record<string, string> | null {
  const diffs: Record<string, string> = {};
  if (turnContext.cwd !== this.referenceContextItem.cwd) {
    diffs['cwd'] = `Working directory changed to: ${turnContext.cwd}`;
  }
  if (turnContext.modelName !== this.referenceContextItem.modelName) {
    diffs['model'] = `Model switched to: ${turnContext.modelName}`;
  }
  return Object.keys(diffs).length > 0 ? diffs : null;
}
```

### 完整消息构建

```typescript
class PromptBuilder {
  buildMessages(turnContext): Array<{ role, content }> {
    const messages = [
      { role: 'system', content: systemPrompt },
    ];

    // 首次：注入项目指令
    if (turnContext.isFirstTurn) {
      messages.push({ role: 'user', content: `<project-context>${projectInstructions}</project-context>` });
    } else if (turnContext.settingsDiff) {
      messages.push({ role: 'user', content: `<settings-update>${diff}</settings-update>` });
    }

    // 技能索引（仅元数据）
    if (availableSkills.length > 0) {
      messages.push({ role: 'user', content: renderSkillsIndex(availableSkills) });
    }

    // 内存快照（首次冻结，持久缓存）
    if (turnContext.memorySnapshot) {
      messages.push({ role: 'user', content: turnContext.memorySnapshot });
    }

    // 压缩摘要（来自之前的窗口）
    if (conv.compactedSummary) {
      messages.push({ role: 'user', content: `<conversation-summary>${summary}</conversation-summary>` });
    }

    // 对话历史（最多 40 条）
    for (const msg of recentMessages.slice(-40)) {
      messages.push({ role: msg.role, content: msg.content });
    }

    // 当前请求
    messages.push({ role: 'user', content: `─── current request ───\n${userInput}` });

    return messages;
  }
}
```

### ContextStore（运行时状态）

```typescript
class ContextStore {
  private sessions = new Map<string, SessionContextState>();

  // 存储每轮结果、技能观察、研究观察
  appendTurn(sessionId, turn) { /* 最近 20 轮 */ }
  addSkillObservation(sessionId, observation) { /* 最近 20 条 */ }
  setActiveTask(sessionId, task) { /* 当前活跃任务 */ }
  setHandoffSummary(sessionId, handoff) { /* 交接摘要 */ }

  // 从 SessionStore 恢复状态（进程重启后）
  async hydrateThread(threadId, projectId) {
    // 恢复最近轮次、技能观察、研究观察、活跃任务、交接摘要
  }
}
```

---

## 6. 5 阶段压缩管线（Compaction）

### 核心原理

当上下文接近模型窗口上限时，逐步收紧压缩策略。5 个阶段依次触发：

```
阈值:        0%     60%     75%     85%     92%     100%
             |-------|-------|-------|-------|--------|
阶段:        1       2       3       4        5
             budget  snip    micro   collapse  LLM
                              compact          summarize
```

### 阶段详解

```typescript
async function compact(messages, opts) {
  const contextWindow = opts.contextWindow ?? 128000;
  const pct = estimateTokens(messages) / contextWindow;

  let result = messages;

  // Stage 1: Budget Reduction (always active, 0-60%)
  // 截断过长的 tool result 到 2000 chars
  result = compactStage1BudgetReduction(result);

  if (pct >= 0.60) {
    // Stage 2: Snip (60%-75%)
    // 保留前 4 条 + 最后 N 条（占 40% token budget），丢弃中间
    result = compactStage2Snip(result, contextWindow);
  }

  if (pct >= 0.75) {
    // Stage 3: Micro-Compact (75%-85%)
    // 将较早的 tool output 截断到 320 chars
    result = compactStage3MicroCompact(result, contextWindow);
  }

  if (pct >= 0.85) {
    // Stage 4: Context Collapse (85%-92%)
    // 将较早的所有消息内容截断到 400 chars
    result = compactStage4ContextCollapse(result, contextWindow);
  }

  if (pct >= 0.92) {
    // Stage 5: LLM Summarize (92%+)
    // 用 LLM 对中间消息进行摘要
    result = await compactStage5LlmSummarize(result, {
      modelClient: opts.modelClient,
    });
  }

  return result;
}
```

### 工具调用边界修复

压缩切分消息时必须保持 tool_call / tool_result 配对：

```typescript
function repairToolCallBoundaries(middle, tail) {
  // 如果 tail 中有 tool result 但其对应的 tool_call 在 middle 中，
  // 把该 tool_call 从 middle 移到 tail
  const tailToolResultIds = new Set(
    tail.filter(m => m.role === 'tool').map(m => m.tool_call_id)
  );

  const orphanedIndices = middle
    .filter((m, i) => m.role === 'assistant' && m.tool_calls?.some(tc => tailToolResultIds.has(tc.id)))
    .map((_, i) => i);

  if (orphanedIndices.length > 0) {
    const splitAt = Math.min(...orphanedIndices);
    return {
      middle: middle.slice(0, splitAt),
      tail: [...middle.slice(splitAt), ...tail],
    };
  }
  return { middle, tail };
}
```

### 孤儿 Tool Result 清理

```typescript
function removeOrphanToolResults(messages) {
  // 收集所有 assistant 消息中的 tool_call id
  const knownCallIds = new Set(
    messages
      .filter(m => m.role === 'assistant')
      .flatMap(m => m.tool_calls?.map(tc => tc.id) ?? [])
  );

  // 移除没有对应 tool_call 的 tool result
  return messages.filter(m => {
    if (m.role !== 'tool') return true;
    return knownCallIds.has(m.tool_call_id);
  });
}
```

---

## 7. Skill 系统

### 核心原理

Skill 系统让 Agent 通过可插拔的"技能"扩展能力：

1. **发现**: 扫描目录中的 `SKILL.md` 文件（YAML frontmatter + Markdown body）
2. **匹配**: 7 维评分（名称、描述、标签、能力、示例、使用场景、意图关键词）
3. **执行**: 将匹配的技能指令注入系统提示

### Skill 文件格式

```markdown
---
name: web-search
description: 通用网络搜索技能，支持多引擎搜索
tags: [search, web, 搜索]
capabilities: [search_web, fetch_web]
examples: ["搜索今天的新闻"]
when_to_use: ["用户需要搜索实时信息时"]
allowed_tools: [web_search, web_fetch]
risk_level: network
enabled: true
---

技能的具体指令内容...
```

### 7 维匹配评分

```typescript
const WEIGHTS = {
  name: 4.0,
  description: 2.5,
  tags: 2.0,
  capabilities: 2.5,
  examples: 1.5,
  when_to_use: 2.0,
};

class SkillMatcher {
  match(text, skills): SkillMatch[] {
    const candidates = [];

    for (const skill of activeSkills) {
      let score = 0;

      // 1. Name match (权重 4.0)
      // token 级别重叠
      if (nameOverlap.length > 0) {
        score += 4.0 * nameOverlap.length / max(nameTokens.length, 1);
      }
      if (loweredText.includes(skill.name.toLowerCase())) {
        score += 2.0;  // 直接名称提及加成
      }

      // 2. Description match (权重 2.5)
      // 3. Tags match (权重 2.0)
      // 4. Capabilities match (权重 2.5)
      // 5. Examples match (权重 1.5)
      // 6. When-to-use match (权重 2.0)
      // 7. Intent keyword bonus (中英文意图映射)
    }

    candidates.sort((a, b) => b.score - a.score);
    return candidates;
  }
}
```

### 中英文意图映射

```typescript
const INTENT_KEYWORDS = {
  search:   ['search', '搜索', '查找', '查询', '检索'],
  news:     ['news', '新闻', '最新'],
  summary:  ['summar', '总结', '摘要', '概括'],
  code:     ['code', '代码', '编程', 'programming'],
  browser:  ['browser', '浏览器', 'playwright'],
  email:    ['email', '邮件', 'qq邮箱'],
  // ... 更多
};
```

### 技能指令注入

```typescript
class SkillExecutor {
  execute(context: SkillExecutionContext): SkillExecutionResult {
    const matches = this.matcher.match(context.taskText, skills);
    const topMatches = matches.slice(0, maxSkills);

    let block = '';
    for (const match of topMatches) {
      const body = this.registry.loadBody(match.skill);
      block += `\n## Skill: ${match.skill.name}\n${body}\n`;
    }

    return { included: topMatches, instructionBlock: block };
  }
}
```

---

## 8. Session / Memory 持久化

### SessionStore（JSONL + Sidecar）

```
~/.jarvis/sessions/
├── session_xxx.jsonl   # 追加写入的 JSONL 转录（消息、工具调用、摘要等）
└── session_xxx.json    # Sidecar：可变元数据（标题、项目 ID 等）
```

```typescript
// JSONL 记录类型
type SessionRecordType =
  | 'turn' | 'message' | 'tool_call' | 'tool_result'
  | 'summary' | 'skill_obs' | 'research_obs'
  | 'approval' | 'task_plan' | 'compaction_checkpoint';

interface SessionRecord {
  type: SessionRecordType;
  timestamp: string;  // ISO-8601
  [key: string]: unknown;
}

// 侧边文件（可变元数据）
interface SessionSidecar {
  session_id: string;
  title: string | null;
  created_at: string;
  updated_at: string;
  project_id: string | null;
  cwd: string | null;
}
```

关键实现点：

```typescript
class SessionStore {
  // 使用 Mutex 序列化写入（防止异步交错）
  private async appendLine(sessionId, obj) {
    await this.writeLock.acquire();
    try {
      const line = JSON.stringify(obj) + '\n';
      await fs.appendFile(jsonlPath, line, 'utf-8');
      // 更新内存缓存
    } finally {
      this.writeLock.release();
    }
  }

  // 磁盘预算管理：超过 maxBytes 时删除最旧会话
  async enforceSessionDiskBudget(maxBytes: number) {
    // 按文件名排序（会话 ID 包含时间戳）
    // 删除最旧的直到总大小 < maxBytes * 0.8
  }

  // 压缩后截断 JSONL：删除 firstKeptMessageId 之前的消息行
  // 但保留 compaction_checkpoint、task_plan、approval 等非消息行
  async truncateAfterCompaction(sessionId, firstKeptMessageId) {
    const SURVIVING_TYPES = new Set([
      'compaction_checkpoint', 'task_plan', 'approval',
      'summary', 'skill_obs', 'research_obs',
    ]);
    // 保留存活类型行 + firstKeptMessageId 之后的消息行
  }
}
```

### MarkdownMemoryStore

每个 memory entry 是一个独立的 .md 文件，带 YAML frontmatter：

```markdown
---
name: user_preferences_python
description: Python 开发偏好
type: user
content_hash: a1b2c3d4e5f6g7h8
updated_at: 2025-01-15T10:30:00.000Z
---

用户偏好使用 Python 3.12+，偏好 async/await 模式，使用 ruff 作为 linter。
```

```typescript
class MarkdownMemoryStore {
  // 内容去重：通过 SHA-256 hash 检测重复
  async write(entry) {
    const hash = hashContent(entry.content);
    const existing = await this.findByHash(hash);
    if (existing) {
      // 只更新时间戳，不重写内容
      return existing;
    }
    // 写入新文件 + 更新 MEMORY.md 索引
  }

  // 时间衰减搜索排序
  async loadWithDecay() {
    const entries = await this.loadAll();
    return entries.map(e => ({
      ...e,
      decayWeight: Math.max(0.1, 1.0 - (daysSince / 14) * 0.9),
    })).sort((a, b) => b.decayWeight - a.decayWeight);
  }
}
```

---

## 9. MCP 集成

### 核心原理

MCP（Model Context Protocol）让 Agent 通过 stdio 或 HTTP 连接外部服务，获得额外的工具和资源。

**连接流程：**

```
1. StdioMCPTransport 启动子进程
2. 发送 jsonrpc initialize 握手
3. 发送 tools/list 发现工具
4. 发送 resources/list 发现资源
5. 将工具和资源注册到 Agent 的 ToolRegistry
```

```typescript
class MCPClient {
  async connect(transport: MCPTransport): Promise<MCPConnection> {
    // 1. Initialize handshake
    const init = await transport.send({
      jsonrpc: '2.0', id: 1, method: 'initialize',
      params: { protocolVersion: '2025-06-18', capabilities: {}, clientInfo: { name: 'jarvis', version: '0.1.0' } },
    });

    // 2. Discover tools
    const toolsResp = await transport.send({ jsonrpc: '2.0', id: 2, method: 'tools/list' });
    const tools = toolsResp.result.tools;

    // 3. Discover resources
    const resourcesResp = await transport.send({ jsonrpc: '2.0', id: 3, method: 'resources/list' });

    // 4. Discover prompts
    const promptsResp = await transport.send({ jsonrpc: '2.0', id: 4, method: 'prompts/list' });

    return { transport, serverInfo, tools, resources, prompts };
  }

  async callTool(connection, toolName, args) {
    const response = await connection.transport.send({
      jsonrpc: '2.0', method: 'tools/call',
      params: { name: toolName, arguments: args },
    });
    return response.result;
  }
}
```

### 连接管理器

```typescript
async function connectMcpServers(client, servers) {
  const statuses = [];
  for (const server of servers) {
    try {
      // 1. 平台适配：Windows 下 pnpm → npx fallback
      // 2. 环境变量过滤：移除非安全 env 变量
      // 3. 超时控制
      const transport = new StdioMCPTransport(command, args, cwd, safeEnv, id);
      const conn = await withTimeout(client.connect(transport), connectTimeoutMs);
      statuses.push({ id, state: 'ready', toolCount: conn.tools.length, ... });
    } catch (error) {
      // 自动重试：pnpm ENOENT → npx fallback
      statuses.push({ id, state: 'failed', error: error.message });
    }
  }
  return statuses;
}
```

---

## 10. Sub-Agent / 多 Agent 系统

### 核心原理

Sub-Agent 系统允许主 Agent 委托子任务给独立的 AgentLoop 实例：

```
主 Agent
├── spawn → SubAgent A (explore 类型: 只读工具)
├── spawn → SubAgent B (general 类型: 完整工具)
│   └── spawn → SubAgent C (plan 类型: 只读+任务工具)
└── 通过 Mailbox 接收结果
```

### 架构组件

```typescript
// 1. SubagentPool — 管理并发执行
class SubagentPool {
  private agents = new Map<string, SubagentHandle>();
  private mailboxes = new Map<string, AgentMailbox>();
  maxConcurrent = 4;    // 最大并发数
  maxDepth = 2;         // 最大嵌套深度

  submit(config: SubagentConfig): SubagentHandle {
    // 创建独立 mailbox
    const mailbox = new AgentMailbox();
    // 异步执行（受 maxConcurrent 限制）
    this.execute(config, handle, mailbox, resolve);
    return handle;
  }

  // 自动将结果投递到父 Agent 的 mailbox
  private async execute(config, handle, mailbox, resolve) {
    await this.acquireSlot();
    try {
      const result = await this.runner(config, mailbox);
      this.parentMailbox?.deliver(config.agentId, `[Subagent result] ${result.answer}`);
    } finally {
      this.releaseSlot();
    }
  }
}

// 2. AgentMailbox — 消息传递
class AgentMailbox {
  private pending: MailItem[] = [];

  deliver(senderId: string, message: string, triggerTurn = false): void {
    this.pending.push({ senderId, message, triggerTurn, timestamp: Date.now() });
    // 通知监听器
  }

  drain(): MailItem[] {
    const items = this.pending;
    this.pending = [];
    return items;  // 清空并返回所有消息
  }
}

// 3. SubagentRunner — 执行子任务
class SubagentRunner {
  async run(config: SubagentConfig, mailbox: AgentMailbox): Promise<SubagentResult> {
    // 深度检查
    if (config.depth > MAX_DEPTH) return fail('depth exceeded');

    // 工具白名单
    const allowedTools = config.tools ?? toolWhitelistForType(config.agentType);

    // 创建子 AgentLoop
    const loop = createAgentLoop({ agentId, task, allowedTools, maxSteps, depth, mailbox });

    const result = await loop.runTurn(taskPrompt);
    return { agentId, status: result.ok ? 'completed' : 'failed', answer: result.finalAnswer };
  }
}

// 4. Fork Context 模式
// 子 Agent 可以继承父 Agent 的对话上下文
if (config.forkContext && parentMessages) {
  taskPrompt = `<parent-context>
The following is the conversation history from the parent agent.
${parentMessages.slice(-20).map(m => `[${m.role}]: ${m.content}`).join('\n')}
</parent-context>
\n\n${config.task}`;
}
```

### 工具类型白名单

```typescript
// explore: 只读工具（搜索、阅读）
// plan: 只读 + 任务管理
// general: 全部工具

const EXPLORE_TOOLS = ['read_file', 'glob', 'grep', 'web_search', 'web_fetch', ...];
const PLAN_TOOLS = [...EXPLORE_TOOLS, 'task_create', 'task_update', 'task_list', ...];
const GENERAL_TOOLS = null;  // null = 全部放行
```

---

## 11. CLI 入口

### 核心流程

```typescript
async function main(argv) {
  // 1. 加载 .env
  loadProjectEnv();

  // 2. 解析命令行参数
  const options = parseCLIArgs(argv);

  // 3. 判断模式
  if (options.oneShot) {
    // 一次性模式：运行后退出
    const answer = await runOneShot(options);
    console.log(answer);
  } else if (options.configure) {
    // 配置模式：首次设置引导
    await runConfigure();
  } else {
    // 交互模式：启动 TUI
    await renderTUI(options);
  }
}
```

### Bootstrap（模块组装）

```typescript
function bootstrap(options): CLIContext {
  // 1. LLM Provider
  const provider = new LLMProvider({ model: options.model, apiKey, baseURL });

  // 2. Tool Registry — 注册所有内置工具
  const tools = new ToolRegistry();
  for (const tool of allBuiltinTools) tools.register(tool);
  registerWebTools(tools);

  // 3. Memory tools
  const memoryStore = new MarkdownMemoryStore();
  tools.register(memorySearchTool);
  tools.register(memoryGetTool);

  // 4. Skills
  const skills = createSkillRegistry();
  tools.register(createSkillLoadTool(skills));
  tools.register(createSkillTool(skills));

  // 5. MCP — 连接外部服务器
  const mcpClient = new MCPClient();
  if (mcpServers.length > 0) {
    connectMcpServers(mcpClient, mcpServers);
  }
  for (const mcpTool of createMcpToolEntries(mcpClient)) {
    tools.register(mcpTool);
  }

  // 6. Subagent pool
  const subagentPool = new SubagentPool();
  subagentPool.setRunner(async (config) => {
    const subTools = new ToolRegistry();
    // 根据 agentType 过滤工具
    for (const tool of allBuiltinTools) {
      if (!whitelist || whitelist.includes(tool.name)) subTools.register(tool);
    }
    const subLoop = new AgentLoop({ tools: subTools, provider, skillRegistry: skills, ... });
    return await subLoop.runTurn(config.task);
  });
  tools.register(createAgentTool(subagentPool));

  // 7. Runtime
  const runtime = createToolRuntime(tools, { permissionMode, sandbox, projectRoot });

  // 8. AgentLoop
  const loop = new AgentLoop({ model, tools, toolRuntime: runtime, provider, skills, ... });

  return { options, provider, tools, skills, loop, runtime, ... };
}
```

---

## 12. 从零实现一个 Minimal Agent

基于上述原理，以下是一个约 200 行的最小 Agent 实现，你可以用任何语言复现：

```typescript
// ============================================================
// MINIMAL AGENT — 核心逻辑约 200 行
// 依赖: HTTP 客户端 (fetch), JSON 解析
// ============================================================

// --- 类型定义 ---
interface ToolCall {
  callId: string;
  name: string;
  arguments: Record<string, unknown>;
}

interface ToolResult {
  ok: boolean;
  content: string;
  error?: string;
}

interface ChatMessage {
  role: 'system' | 'user' | 'assistant' | 'tool';
  content: string;
  toolCallId?: string;
  name?: string;
}

interface ToolDefinition {
  type: 'function';
  function: {
    name: string;
    description: string;
    parameters: Record<string, unknown>;
  };
}

// --- Tool 系统 ---
class ToolRegistry {
  private tools = new Map<string, (args: any) => string | Promise<string>>();

  register(name: string, handler: (args: any) => string | Promise<string>) {
    this.tools.set(name, handler);
  }

  getDefinitions(): ToolDefinition[] {
    // 返回给 LLM 的 schema
    return [];
  }

  async execute(name: string, args: any): Promise<ToolResult> {
    const handler = this.tools.get(name);
    if (!handler) return { ok: false, content: '', error: `Unknown tool: ${name}` };
    try {
      const result = await handler(args);
      return { ok: true, content: result };
    } catch (e) {
      return { ok: false, content: '', error: String(e) };
    }
  }
}

// --- LLM Provider ---
class LLMProvider {
  private apiKey: string;
  private baseURL: string;
  private model: string;

  constructor(config: { apiKey: string; baseURL: string; model: string }) {
    this.apiKey = config.apiKey;
    this.baseURL = config.baseURL;
    this.model = config.model;
  }

  async chat(
    messages: ChatMessage[],
    tools?: ToolDefinition[],
  ): Promise<{ content: string; toolCalls: ToolCall[]; finishReason: string }> {
    const response = await fetch(`${this.baseURL}/chat/completions`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${this.apiKey}`,
      },
      body: JSON.stringify({
        model: this.model,
        messages: messages.map(m => ({ role: m.role, content: m.content })),
        tools: tools?.length ? tools : undefined,
        stream: false,
      }),
    });

    const data = await response.json();
    const choice = data.choices[0];
    const message = choice.message;

    return {
      content: message.content || '',
      toolCalls: (message.tool_calls || []).map((tc: any) => ({
        callId: tc.id,
        name: tc.function.name,
        arguments: JSON.parse(tc.function.arguments || '{}'),
      })),
      finishReason: choice.finish_reason || 'stop',
    };
  }
}

// --- 重试逻辑 ---
async function withRetry<T>(fn: () => Promise<T>, maxRetries = 3): Promise<T> {
  for (let attempt = 0; attempt <= maxRetries; attempt++) {
    try {
      return await fn();
    } catch (e) {
      if (attempt >= maxRetries) throw e;
      // 指数退避 + 抖动
      const delay = Math.min(5000 * Math.pow(2, attempt), 120000) * (1 - 0.3 * Math.random());
      await new Promise(r => setTimeout(r, delay));
    }
  }
  throw new Error('Unreachable');
}

// --- Token 估算 ---
function isCJK(cp: number): boolean {
  return (cp >= 0x4E00 && cp <= 0x9FFF) || (cp >= 0x3040 && cp <= 0x30FF);
}

function estimateTokens(text: string): number {
  if (!text) return 0;
  let total = 0;
  for (const ch of text) {
    const cp = ch.codePointAt(0) ?? 0;
    total += isCJK(cp) ? 1 : 0.25;
  }
  return Math.ceil(total);
}

// --- Agent 循环 ---
class MinimalAgent {
  private provider: LLMProvider;
  private tools: ToolRegistry;
  private systemPrompt: string;
  private maxTurns: number = 30;

  constructor(config: {
    apiKey: string;
    baseURL?: string;
    model?: string;
    systemPrompt?: string;
  }) {
    this.provider = new LLMProvider({
      apiKey: config.apiKey,
      baseURL: config.baseURL || 'https://api.deepseek.com/v1',
      model: config.model || 'deepseek-chat',
    });
    this.tools = new ToolRegistry();
    this.systemPrompt = config.systemPrompt || this.defaultSystemPrompt();
    this.registerDefaultTools();
  }

  private defaultSystemPrompt(): string {
    return `<agent>
You are a local AI coding assistant. Use tools to fulfill the user's request.
Do NOT describe what you'll do — do it.
When your tools finish, deliver the result in 1-3 sentences.
</agent>`;
  }

  // 注册内置工具
  private registerDefaultTools() {
    this.tools.register('echo', async (args: { text: string }) => {
      return args.text;
    });
    // 实际使用时应注册: read_file, write_file, bash, glob, grep 等
  }

  // 获取给 LLM 的工具定义
  private getToolDefinitions(): ToolDefinition[] {
    // 返回 OpenAI-format 定义
    return [{
      type: 'function',
      function: {
        name: 'echo',
        description: 'Echo back the input text',
        parameters: {
          type: 'object',
          properties: {
            text: { type: 'string', description: 'Text to echo' },
          },
          required: ['text'],
        },
      },
    }];
  }

  // 简洁的上下文压缩
  private compressMessages(messages: ChatMessage[]): ChatMessage[] {
    const estimated = sum(messages.map(m => estimateTokens(m.content)));
    const threshold = 32000; // 32K tokens 开始压缩

    if (estimated < threshold * 0.75) return messages;

    // 保留前 4 条 + 后 6 条，丢弃中间
    if (messages.length > 10) {
      return [
        ...messages.slice(0, 4),
        { role: 'system', content: `[compaction: ${messages.length - 10} messages dropped]` },
        ...messages.slice(-6),
      ];
    }
    return messages;
  }

  // 主入口
  async run(userInput: string): Promise<string> {
    const messages: ChatMessage[] = [];
    let finalContent = '';

    messages.push({ role: 'user', content: userInput });

    for (let turn = 0; turn < this.maxTurns; turn++) {
      // 压缩检查
      const compressed = this.compressMessages(messages);
      // 构建 LLM 消息（system + 历史）
      const llmMessages = [{ role: 'system', content: this.systemPrompt }, ...compressed];

      // 调用 LLM（带重试）
      const response = await withRetry(() =>
        this.provider.chat(llmMessages, this.getToolDefinitions())
      );

      // 添加 assistant 回复
      messages.push({ role: 'assistant', content: response.content });

      if (response.finishReason === 'stop') {
        return response.content;
      }

      if (response.finishReason === 'tool_calls' && response.toolCalls.length > 0) {
        for (const tc of response.toolCalls) {
          const result = await this.tools.execute(tc.name, tc.arguments);
          messages.push({
            role: 'tool',
            content: result.content,
            toolCallId: tc.callId,
            name: tc.name,
          });
        }
        continue;
      }

      if (response.finishReason === 'length') {
        finalContent = response.content;
        break;
      }
    }

    return finalContent || 'Max turns reached without final answer.';
  }
}

// --- 使用示例 ---
async function main() {
  const agent = new MinimalAgent({
    apiKey: process.env.LLM_API_KEY!,
    baseURL: 'https://api.deepseek.com/v1',
    model: 'deepseek-chat',
  });

  const answer = await agent.run('Hello! What can you do?');
  console.log(answer);
}
```

---

## 总结：构建你自己的 Agent 的 10 步清单

1. **LLM Provider**: 封装 OpenAI-compatible API，支持流式和重试
2. **ToolRegistry**: 注册工具（名称 + handler + JSON Schema），支持按名称过滤
3. **ToolRuntime**: 执行编排、权限检查、结果截断
4. **Agent Loop**: ReAct 循环（LLM → Tool → LLM...），最大轮数控制
5. **ContextBuilder**: 组装系统提示 + 项目指令 + 对话历史
6. **Compaction**: 当上下文接近窗口上限时逐步压缩（budget → snip → micro → collapse → LLM）
7. **Skill System**: 发现 SKILL.md、多维匹配、指令注入
8. **Session Store**: JSONL 追加日志 + Sidecar 可变元数据
9. **Sub-Agent**: Mailbox 通信 + Pool 并发管理 + 工具白名单
10. **CLI/TUI**: 参数解析 + 一次性/交互模式切换

每个模块都可以独立实现和替换。从最小版本（~200 行）开始，逐步添加上述功能。