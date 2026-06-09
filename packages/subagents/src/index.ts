// ============================================================================
// @jarvis/subagents — Subagent pool, runner, registry for multi-agent execution
// ============================================================================

export { SubagentPool } from './pool.js';
export { SubagentRunner, toolWhitelistForType, buildSubagentSystemPrompt } from './runner.js';
export type { RunnerDeps } from './runner.js';
export {
  EXPLORE_TOOLS,
  PLAN_TOOLS,
  REVIEW_TOOLS,
  GENERAL_TOOLS,
  MAX_DEPTH,
  MAX_BUDGET_STEPS,
} from './models.js';
export type {
  BuiltinAgentType,
  SubagentStatus,
  ReviewDecision,
  SubagentConfig,
  SubagentHandle,
  SubagentResult,
  StructuredSubagentPayload,
  ReviewFinding,
  WorkItem,
  TaskBundle,
  WaveResult,
  AgentIdentity,
  AgentLifecycleStatus,
} from './models.js';
export { buildStructuredPayload, mergeReviewIntoResult, buildReviewerTask } from './result.js';
export { AgentRegistry } from './registry.js';
export { discoverAgents, mergeAgentDirectories, type AgentDefinition } from './agent-registry.js';
