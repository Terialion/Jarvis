# Jarvis Current Tool/Command/Skill Architecture Inventory

## Executive Summary

Jarvis 已经有了丰富的 routing、command、skill 基础设施，但缺少 **统一的 ToolRuntime 执行链路**。
当前架构是"路由器 + 分散执行"模式，本轮需要升级为"注册 + 选择 + Runtime 统一执行"模式。

## 1. 当前 Command Registry

| 位置 | 类型 | 状态 |
|------|------|------|
| `jarvis/cli_command_map.py` | `CliCommandSpec` 静态列表 (30+ 命令) | ✅ 已有，CLI 专用 |
| `src/jarvis/core/commands/registry.py` | `CommandMetadata` 适配层，包装 `cli_command_map` | ✅ 已有，但只是薄包装 |
| `src/jarvis/core/commands/schema.py` | `CommandMetadata` dataclass | ✅ 已有 |
| `src/jarvis/core/routing/command_router.py` | `route_command(envelope)` | ✅ 已有，返回 `CommandRoute` |
| `jarvis/cli.py` `_handle_slash_command()` | 硬编码 `handlers = {}` 字典 | ⚠️ **CLI 与 registry 不同步** |

**问题**: CLI 里的 `handlers` 字典是硬编码的，和 `cli_command_map.py` / `CommandRegistry` 不是同一数据源。

## 2. 当前 Skill Registry

| 位置 | 类型 | 状态 |
|------|------|------|
| `src/jarvis/core/skill_harness/registry.py` | Skill discovery & snapshot | ✅ 已有 |
| `src/jarvis/core/skills/command_registry.py` | `SkillCommandMetadata` 动态 skill 命令 | ✅ 已有 |
| `src/jarvis/core/skills/metadata.py` | `SkillCommandMetadata` dataclass | ✅ 已有 |
| `src/jarvis/core/skills/schema.py` | 不存在 | ❌ 缺少 `SkillSpec` |
| `src/jarvis/core/skills/registry.py` | 不存在 | ❌ 缺少中央 `SkillRegistry` |
| `src/jarvis/core/skills/loader.py` | 不存在 | ❌ 缺少 progressive disclosure loader |
| `src/jarvis/core/skills/trust.py` | 不存在 | ❌ 缺少 trust boundary |

**问题**: 有 skill harness (discovery, telemetry, selector)，但缺少中央 `SkillRegistry`、`SkillSpec`、progressive disclosure、trust boundary。

## 3. 当前 Tool Registry

| 位置 | 类型 | 状态 |
|------|------|------|
| `jarvis/tools/registry.py` | `ToolRegistry` (BaseTool-based) | ✅ 已有，但 **不是本轮需要的** |
| `jarvis/tools/base.py` | `BaseTool`, `ToolResult`, `ToolMeta` | ✅ 已有，有 `to_prompt()` |
| `jarvis/tools/loader.py` | `load_builtin_tools()` | ✅ 已有 |
| `jarvis/tools/builtin/` | time_tools, web_tools | ✅ 已有 |
| `src/jarvis/core/tools/` | **不存在** | ❌ 需要新建 |

**问题**: 现有 `jarvis/tools/` 是 BaseTool 模式（面向对象的工具），但缺少：
- `ToolSpec` (name, description, input_schema, output_schema, risk_level, permissions)
- 没有 risk_level / permission / approval 语义
- LLM 只能看到 description + params，看不到 risk/permission
- `ToolResult` 和 `IntentRoute` 中的 `ToolResult` 不是同一 schema

## 4. 当前工具执行

**状态: 分散执行**

| 执行位置 | 方式 |
|----------|------|
| `jarvis/tools/registry.py` `call()` | 直接调用 `tool(**kwargs)` |
| `jarvis/cli.py` `_run_existing_task_flow()` | skill harness dry-run |
| `src/jarvis/core/coding_loop/` | 独立 orchestrator |
| `src/jarvis/core/repo_inspection/` | 独立 inspector |
| `jarvis/cli.py` `_shell_approve()` | 直接 subprocess.run |
| `src/jarvis/core/cli_response/dispatcher.py` | dispatch by response_mode, 调用各种 runner |

**问题**: 没有 **统一的 ToolRuntime**。每个模块自己执行，没有统一的安全/审批/沙箱边界。

## 5. 当前 Approval/Safety/Sandbox

| 位置 | 类型 | 状态 |
|------|------|------|
| `src/jarvis/core/policy/approval.py` | `ApprovalPolicy` dataclass | ✅ scaffold |
| `src/jarvis/core/policy/sandbox.py` | `SandboxPolicy` dataclass | ✅ scaffold |
| `src/jarvis/core/policy/exec_policy.py` | `ExecPolicy` dataclass | ✅ scaffold |
| `src/jarvis/core/policy/risk_matrix.py` | `ApprovalRiskMatrix` | ✅ 有实现，但有安全 allowlist 问题 |
| `src/jarvis/core/routing/safety_gate.py` | `apply_route_safety()` | ✅ 已有，基于关键词 |
| `src/jarvis/core/safety_guard.py` | 安全检查器 | ✅ 已有 |

**问题**:
- 没有 `PermissionMode` (read_only/workspace_write/danger_full_access)
- Sandbox 只是 dataclass，没有实际沙箱执行
- Approval 在 CLI 里是手动 `/approve` 按钮式，没有集成到 ToolRuntime
- `risk_matrix._is_safe_local_command()` 有不安全 allowlist (如 `cat` 在 Windows 可能读敏感文件)

## 6. 当前 Hooks

| 位置 | 类型 | 状态 |
|------|------|------|
| `src/jarvis/core/hooks/registry.py` | `HookRegistry` + `HookStageRegistry` | ✅ 已有 |
| `src/jarvis/core/hooks/schema.py` | `HookStage`, `HookResult` | ✅ 已有 |
| `src/jarvis/core/hooks/models.py` | `HookRegistration`, `HOOK_POINTS` | ✅ 已有 |
| `src/jarvis/core/hooks/executor.py` | `HookExecutor` | ✅ 已有 |

**问题**: Hooks 有 registry 和 executor，但没有集成到 ToolRuntime 的执行链路中。`HookStageRegistry` 的注释说 "No-op stage registry scaffold for future Claude/Hermes-style lifecycle hooks."

## 7. 当前 LLM 是否能看到工具 Schema

| 方面 | 状态 |
|------|------|
| `jarvis/tools/registry.py` `to_prompt()` | ✅ 生成工具描述文本 |
| `jarvis/tools/registry.py` `to_openai_functions()` | ✅ 生成 OpenAI function calling 格式 |
| `src/jarvis/core/llm/prompt_builder.py` | ⚠️ **不注入工具 schema** |

**问题**: Prompt builder 的 `build_intent_classification_prompt()` 只注入 response_mode 列表和 few-shot examples，**不注入工具 schema、工具风险、权限模式**。LLM 不知道有哪些工具可用。

## 8. 当前 Skill Metadata 是否能越权

| 方面 | 状态 |
|------|------|
| `src/jarvis/core/skills/command_registry.py` | 读取 metadata 但不验证权限 |
| `jarvis/cli.py` `_skill_body_has_policy_violation()` | ✅ 检查 SKILL.md 是否包含敏感内容 |
| `jarvis/cli.py` `_skill_request_is_sensitive()` | ✅ 检查 skill args 是否敏感 |

**问题**: 有基本检查，但没有 formal trust boundary。SKILL.md 的 `allowed_tools` 字段被读取但没有被 ToolRuntime 约束验证。没有 installed vs trusted 的区分。

## 9. 当前 CLI 和 Gateway 是否能共用命令注册

| 方面 | 状态 |
|------|------|
| `jarvis/cli_command_map.py` | CLI 专用但数据是 `CliCommandSpec`，理论上可复用 |
| `src/jarvis/core/commands/registry.py` | 适配层，理论上 gateway 可用 |
| `src/jarvis/core/gateway/` | 有 `control_http_adapter.py` 但未与 command registry 集成 |

**问题**: 数据结构可以共用，但 CLI 的 handler 是硬编码在 `cli.py` 里的，不是注册在 CommandRegistry 中。Gateway 无法直接复用。

## 10. 最大架构缺口

1. **没有 ToolRuntime** — 工具执行分散在各模块，没有统一的 safety/approval/sandbox/hook 链路
2. **没有 PermissionMode** — 没有 read_only/workspace_write/danger_full_access 的正式 permission 模型
3. **没有 AgentRequestRouter** — 没有明确的 chat vs work 判断层（current routing 是 intent/response_mode 分类，但没有 `is_work_request` / `required_tools` / `tool_plan`）
4. **没有 AgentToolLoop** — 没有 chat path vs work path 的分叉，没有 tool result 回填机制
5. **LLM 看不到工具 schema** — prompt builder 不注入工具信息
6. **CommandRegistry 没有中央化** — CLI 硬编码 handler，与 registry 不同步
7. **SkillRegistry 缺少 trust boundary** — 没有 SkillSpec、progressive disclosure、installed vs trusted
8. **Hooks 未集成到执行链路** — 有 registry 但没有在 ToolRuntime 中调用
