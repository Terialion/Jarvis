// ============================================================================
// @jarvis/tools — barrel exports
// ============================================================================

// Registry
export {
  ToolRegistry,
  type ToolEntry,
  type ToolHandler,
  type ToolContext,
} from './registry.js';

// Runtime
export {
  ToolRuntime,
  ApprovalGate,
  PermissionManager,
  mapUserPermissionMode,
  createToolRuntime,
  type ToolRuntimeOptions,
  type CreateToolRuntimeOptions,
  type ApprovalResult,
  type PermissionMode,
  type UserPermissionMode,
  type PermissionCheckResult,
  type ApprovalRequest,
} from './runtime.js';

// Sandbox policy
export {
  checkCommand,
  createSandboxPolicy,
  type SandboxPolicyConfig,
  type SandboxConfig,
  type CommandRisk,
  type CommandCheckResult,
} from './sandbox-policy.js';

// Builtin tools (individual entries + schemas)
export { bashTool, bashSchema } from './builtin/bash.js';
export { readFileTool, readFileSchema } from './builtin/file-read.js';
export { writeFileTool, writeFileSchema } from './builtin/file-write.js';
export { editFileTool, editFileSchema } from './builtin/file-edit.js';
export { globTool, globSchema } from './builtin/glob.js';
export { grepTool, grepSchema } from './builtin/grep.js';
export { webSearchTool, webSearchSchema, createWebSearchTool, createWebSearchHandler, DefaultWebSearchBackend, type WebSearchBackend, type WebSearchResult } from './builtin/web-search.js';
export { webFetchTool, webFetchSchema, createWebFetchHandler, type WebFetchBackend } from './builtin/web-fetch.js';
export { askUserQuestionTool, setAskUserQuestionBridge } from './builtin/ask-user-question.js';
export type { AskQuestionDef, AskUserQuestionCallback } from './builtin/ask-user-question.js';
export { taskCreateTool, taskUpdateTool, taskListTool, taskGetTool, taskOutputTool, taskStopTool, getBackgroundTaskRegistry } from './builtin/task.js';
export type { TaskItem, BackgroundTask } from './builtin/task.js';
export { enterPlanModeTool, exitPlanModeTool } from './builtin/plan-mode.js';
export { notebookEditTool, notebookEditSchema } from './builtin/notebook-edit.js';
export { cronCreateTool, cronDeleteTool, cronListTool, scheduleWakeupTool } from './builtin/cron.js';
export { CronScheduler, getCronScheduler } from './builtin/cron-scheduler.js';
export type { CronJob } from './builtin/cron-scheduler.js';
export { enterWorktreeTool, exitWorktreeTool } from './builtin/worktree.js';
export { createSkillLoadTool, createSkillLoadHandler, createSkillTool, createSkillHandler, type SkillSupplier } from './builtin/skill-load.js';
export { createAgentTool, createAgentHandler, type AgentPool } from './builtin/agent.js';
export { createListMcpResourcesTool, createReadMcpResourceTool, createMcpStatusTool, createMcpHealthcheckTool, type McpResourceClient } from './builtin/mcp-resource.js';
export { createMcpToolEntries, type McpToolClient } from './builtin/mcp-tools.js';
export { mcpBootstrapTool, mcpBootstrapSchema } from './builtin/mcp-setup.js';
export { pluginBootstrapTool, pluginBootstrapSchema } from './builtin/plugin-setup.js';
export { TavilySearchBackend, TavilyFetchBackend, tryCreateTavilySearch, tryCreateTavilyFetch, type TavilyOptions } from './builtin/tavily-backend.js';

import type { ToolEntry } from './registry.js';
import { bashTool } from './builtin/bash.js';
import { readFileTool } from './builtin/file-read.js';
import { writeFileTool } from './builtin/file-write.js';
import { editFileTool } from './builtin/file-edit.js';
import { globTool } from './builtin/glob.js';
import { grepTool } from './builtin/grep.js';
import { askUserQuestionTool } from './builtin/ask-user-question.js';
import { taskCreateTool, taskUpdateTool, taskListTool, taskGetTool, taskOutputTool, taskStopTool } from './builtin/task.js';
import { enterPlanModeTool, exitPlanModeTool } from './builtin/plan-mode.js';
import { notebookEditTool } from './builtin/notebook-edit.js';
import { cronCreateTool, cronDeleteTool, cronListTool, scheduleWakeupTool } from './builtin/cron.js';
import { enterWorktreeTool, exitWorktreeTool } from './builtin/worktree.js';
import { mcpBootstrapTool } from './builtin/mcp-setup.js';
import { pluginBootstrapTool } from './builtin/plugin-setup.js';

/** All builtin tool entries in one array. */
export const allBuiltinTools: ToolEntry[] = [
  bashTool,
  readFileTool,
  writeFileTool,
  editFileTool,
  globTool,
  grepTool,
  askUserQuestionTool,
  taskCreateTool,
  taskUpdateTool,
  taskListTool,
  taskGetTool,
  taskOutputTool,
  taskStopTool,
  enterPlanModeTool,
  exitPlanModeTool,
  notebookEditTool,
  cronCreateTool,
  cronDeleteTool,
  cronListTool,
  scheduleWakeupTool,
  enterWorktreeTool,
  exitWorktreeTool,
  mcpBootstrapTool,
  pluginBootstrapTool,
];
