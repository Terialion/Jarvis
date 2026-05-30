// ============================================================================
// @jarvis/agent — Core agent loop, LLM provider, and context management
// ============================================================================

// mailbox
export { AgentMailbox } from './mailbox.js';
export type { MailItem } from './mailbox.js';

// model
export { FakeModelClient, LLMProvider } from './model.js';
export type {
  ModelConfig,
  ModelReasoningEffort,
  TokenUsage,
  LLMResponse,
  LLMMessage,
  StreamCallbacks,
  ModelResponse,
  ModelChunk,
} from './model.js';
export { MODEL_REASONING_EFFORTS } from './model.js';

// model catalog
export {
  KNOWN_MODELS,
  loadUserModels,
  saveUserModels,
  addUserModel,
  removeUserModel,
  getAllModels,
  parseModelName,
  findModel,
  resolveContextWindow,
  formatModelWithContext,
} from './model-catalog.js';
export type {
  ModelInfo,
  ParsedModelName,
} from './model-catalog.js';

// token tracker
export { TokenTracker, formatTokensCompact } from './token-tracker.js';
export type { TokenSnapshot } from './token-tracker.js';

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
export type { EventHandler, ThreadEventHandler } from './events.js';

// thread events
export type {
  ThreadUsage,
  ToolCallThreadItemStatus,
  AgentMessageThreadItem,
  ReasoningThreadItem,
  ToolCallThreadItem,
  TodoThreadItem,
  TodoListThreadItem,
  ErrorThreadItem,
  ThreadItem,
  ThreadStartedEvent,
  TurnStartedEvent,
  TurnCompletedEvent,
  TurnFailedEvent,
  ItemStartedEvent,
  ItemUpdatedEvent,
  ItemCompletedEvent,
  ThreadErrorEvent,
  ThreadEvent,
} from '@jarvis/shared';

// context
export { ContextBuilder, ContextUpdater, UserFactExtractor, estimateTokens, validateContextWindow } from './context.js';
export type { ContextWindowGuard } from './context.js';
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

// normalizer
export { normalizeMessages } from './normalizer.js';
export type { MessageRecord } from './normalizer.js';

// prompt-builder
export { AGENT_SYSTEM_PROMPT, PromptBuilder, buildSystemPrompt } from './prompt-builder.js';
export type { PromptMode } from './prompt-builder.js';

// cache-strategy
export { supportsPromptCaching, markCacheable, injectCacheBreakpoints } from './cache-strategy.js';

// fragment
export {
  SkillsIndexFragment,
  CompactionSummaryFragment,
  ConversationHistoryFragment,
  SkillContextFragment,
  CurrentRequestFragment,
  FragmentRegistry,
  BaseFragment,
} from './fragment.js';
export type { ContextualFragment } from './fragment.js';

// compactor
export {
  compact,
  shouldAutoCompact,
  microCompact,
  buildCompactionSummaryPrefix,
  buildSkillStateCompactionSummary,
  summarizeInStages,
  splitMessagesByTokenShare,
  chunkMessagesByMaxTokens,
  recomputeTokens,
  computeAdaptiveChunkRatio,
  removeOrphanToolResults,
  repairAllToolBoundaries,
  repairToolCallBoundaries,
  compactionReportToEvent,
} from './compactor.js';
export type {
  CompactionMessage,
  CompactionReport,
  CompactionEvent,
  CompactionModelClient,
} from './compactor.js';

// context-engine
export type {
  ContextEngine,
  AssembleResult,
  CompactOpts,
  CompactResult,
  ContextSnapshot,
} from './context-engine.js';

// memory-search
export {
  createMemorySearchHandler,
  createMemoryGetHandler,
  buildMemoryIndex,
  searchMemory,
  getMemoryByName,
  buildMemoryIndexSummary,
  computeDecayWeight,
  hashContent,
  invalidateMemoryIndex,
} from './memory-search.js';
export type {
  MemorySearchResult,
  MemoryIndex,
  IndexedMemoryEntry,
  MemoryStoreAdapter,
} from './memory-search.js';

// memory-extractor
export { MemoryExtractor } from './memory-extractor.js';
export type {
  MemoryExtractionConfig,
  RawMemory,
  ConsolidatedMemory,
} from './memory-extractor.js';

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
