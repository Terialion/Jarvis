// ============================================================================
// ContextEngine — life-cycle-oriented context management interface
// Pattern from OpenClaw src/context-engine/types.ts
// ============================================================================

import type { ChatMessage, ToolResult } from '@jarvis/shared';

// ============================================================================
// Core interface
// ============================================================================

export interface AssembleResult {
  messages: Array<{ role: string; content: string; tool_call_id?: string }>;
  estimatedTokens: number;
  systemPromptAddition?: string;
}

export interface CompactOpts {
  force?: boolean;
  trigger?: 'budget' | 'overflow' | 'manual' | 'model_downshift';
  compactionTarget?: 'budget' | 'aggressive';
}

export interface CompactResult {
  messages: Array<{ role: string; content: string }>;
  stage: string;
  tokensBefore: number;
  tokensAfter: number;
  messagesBefore: number;
  messagesAfter: number;
}

export interface ContextSnapshot {
  sessionId: string;
  turnId: string;
  messageCount: number;
}

export interface SubagentConfig {
  agentType: string;
  agentId: string;
  budgetSteps?: number;
}

export interface SubagentResult {
  agentId: string;
  status: string;
  answer?: string;
}

export interface TurnResult {
  turnId: string;
  sessionId: string;
  finalAnswer?: string;
  skillsUsed?: string[];
  outputType?: string;
  stopReason?: string;
  summary?: Record<string, unknown>;
}

export interface ContextEngine {
  /** Initialize engine state, import historical context from SessionStore. */
  bootstrap(sessionId: string): Promise<void>;

  /** Run transcript maintenance after bootstrap, turns, or compaction. */
  maintain(sessionId: string): Promise<void>;

  /** Store one or more messages for later context assembly. */
  ingest(sessionId: string, messages: Array<{ role: string; content: string; tool_call_id?: string }>): Promise<void>;

  /** Post-turn lifecycle hook — persist observations, update state. */
  afterTurn(sessionId: string, result: TurnResult): Promise<void>;

  /** Build the ordered message list to send to the LLM. */
  assemble(sessionId: string, userInput: string, opts?: {
    availableTools?: string[];
    model?: string;
  }): AssembleResult;

  /** Reduce context to fit within the token budget. */
  compact(sessionId: string, opts?: CompactOpts): Promise<CompactResult>;

  /** Prepare context for a subagent spawn — returns snapshot of current state. */
  prepareSubagentSpawn(config: SubagentConfig): ContextSnapshot;

  /** Handle subagent result — update parent session state. */
  onSubagentEnded(result: SubagentResult): void;

  /** Release resources. */
  dispose(): void;
}
