// ============================================================================
// @jarvis/agent — Core agent loop, LLM provider, and context management
// ============================================================================

// model
export { FakeModelClient, LLMProvider } from './model.js';
export type {
  ModelConfig,
  TokenUsage,
  LLMResponse,
  LLMMessage,
  StreamCallbacks,
  ModelResponse,
  ModelChunk,
} from './model.js';

// retry
export {
  ErrorClassifier,
  FailureTracker,
  ReplanPolicy,
  RetryPolicy,
  jitteredBackoff,
  withRetry,
} from './retry.js';
export type { ErrorClassification, FailureRecord, RetryConfig } from './retry.js';

// events
export { AgentEventBus } from './events.js';
export type { EventHandler } from './events.js';

// context
export { ContextBuilder, ContextUpdater, UserFactExtractor } from './context.js';
export type {
  ContextConfig,
  ContextPack,
  ContextStoreLike,
  ConversationContext,
  MemoryContext,
  MemoryStoreLike,
  ProjectContext,
  RuntimeState,
  SessionStoreLike,
  SkillContext,
  SkillRegistryLike,
  TurnContext,
} from './context.js';

// context-store
export { ContextStore } from './context-store.js';
export type {
  SessionContextState,
  SkillObservation,
  ActiveTaskState,
  HandoffSummary,
  ResearchObservation,
} from './context-store.js';

// compactor
export {
  compact,
  shouldAutoCompact,
  microCompact,
  buildCompactionSummaryPrefix,
  buildSkillStateCompactionSummary,
} from './compactor.js';
export type {
  CompactionMessage,
  CompactionReport,
  CompactionModelClient,
} from './compactor.js';

// normalizer
export { normalizeMessages } from './normalizer.js';
export type { MessageRecord } from './normalizer.js';

// prompt-builder
export { AGENT_SYSTEM_PROMPT, PromptBuilder } from './prompt-builder.js';

// summary
export { ConversationSummarizer, ResponseComposer } from './summary.js';
export type {
  ComposeOptions,
  ConversationSummary,
  SummaryConfig,
} from './summary.js';

// loop
export { AgentLoop } from './loop.js';
export type { AgentLoopConfig, AgentRunResult, TurnResult } from './loop.js';
