// ============================================================================
// Subagent tools index — unified exports
// ============================================================================

export { createSpawnAgentHandler, createSpawnAgentTool } from './spawn-agent.js';
export type { SpawnAgentDeps } from './spawn-agent.js';
export { createTalkToHandler, createTalkToTool } from './talk-to.js';
export type { TalkToDeps } from './talk-to.js';
export { createReportHandler, createReportTool } from './report.js';
export type { ReportDeps } from './report.js';
export { createListAgentsHandler, createListAgentsTool } from './list-agents.js';
export type { ListAgentsDeps } from './list-agents.js';
export { createPauseAgentHandler, createPauseAgentTool, createResumeAgentHandler, createResumeAgentTool } from './pause-agent.js';
export type { PauseResumeDeps } from './pause-agent.js';
export { createRedirectAgentHandler, createRedirectAgentTool } from './redirect-agent.js';
export type { RedirectDeps } from './redirect-agent.js';