// ============================================================================
// AgentLoop — the core agent loop orchestrating LLM calls and tool dispatch
// ============================================================================

import type {
  AgentEvent,
  ChatMessage,
  ThreadEvent,
  ThreadUsage,
  ToolCallThreadItem,
  ToolResult,
} from '@jarvis/shared';
import type { ToolRegistry, ToolRuntime } from '@jarvis/tools';
import type { SkillRegistry, SkillExecutor } from '@jarvis/skills';
import type { HookRegistry } from '@jarvis/hooks';
import { LLMProvider, type ModelConfig, type LLMMessage, FakeModelClient } from './model.js';
import { resolveContextWindow } from './model-catalog.js';
import type { FallbackLLMProvider } from './model-fallback.js';
import { TokenTracker } from './token-tracker.js';
import { AgentEventBus } from './events.js';
import { ContextBuilder, estimateTokens, type ContextConfig, type TurnContext, type ContextPack, type SessionStoreLike, type MemoryStoreLike, type SkillRegistryLike } from './context.js';
import { PromptBuilder, AGENT_SYSTEM_PROMPT } from './prompt-builder.js';
import type { PromptPartMeta } from './prompt-parts.js';
import { ResponseComposer } from './summary.js';
import { withRetry, type RetryConfig, ErrorClassifier, RetryPolicy as ToolRetryPolicy, FailureTracker, ReplanPolicy } from './retry.js';
import type { AgentMailbox } from './mailbox.js';
import { compact, setTokenEstimator, type CompactionMessage, type CompactionModelClient } from './compactor.js';
import { mapStopReasonToTurnState, type AgentTurnState } from './turn-state.js';

// Wire up CJK-aware token estimation for the compaction pipeline
setTokenEstimator(estimateTokens);

function formatMailboxContent(mail: {
  senderId: string;
  message: string;
  envelope?: { kind: string; summary: string; payload?: unknown };
}): string {
  if (!mail.envelope) {
    return [
      `<inter-agent-message from="${mail.senderId}">`,
      mail.message,
      '</inter-agent-message>',
      '',
      'The message above was sent to you by another agent using the talk_to tool.',
      `You can reply by calling talk_to(targetId="${mail.senderId}", message="your response").`,
    ].join('\n');
  }

  const serializedPayload = mail.envelope.payload === undefined
    ? ''
    : `\n\nPayload:\n${JSON.stringify(mail.envelope.payload, null, 2)}`;

  return [
    `<inter-agent-message from="${mail.senderId}" kind="${mail.envelope.kind}">`,
    `[${mail.envelope.kind}] ${mail.envelope.summary}${serializedPayload}`,
    '</inter-agent-message>',
    '',
    'Treat structured result and review payloads as coordination context from another agent.',
    `You can reply by calling talk_to(targetId="${mail.senderId}", message="your response").`,
  ].join('\n');
}

// ============================================================================
// Configuration
// ============================================================================

export interface AgentLoopConfig {
  model: ModelConfig;
  maxTurns?: number;
  tools?: ToolRegistry;
  toolRuntime?: ToolRuntime;
  systemPrompt?: string;
  eventBus?: AgentEventBus;
  context?: ContextConfig;
  provider?: LLMProvider | FallbackLLMProvider;
  skillRegistry?: SkillRegistry;
  skillExecutor?: SkillExecutor;
  hooks?: HookRegistry;
  maxSkills?: number;
  // Full-featured options
  projectRoot?: string;
  sessionStore?: SessionStoreLike;
  memoryStore?: MemoryStoreLike;
  contextStore?: { retrieveRecentContext(sessionId: string): Record<string, unknown> };
  permissionMode?: string;
  maxSteps?: number;
  timeoutS?: number;
  toolTimeoutS?: number;
  autoApprove?: boolean;
  /** Token tracker for accumulating usage across turns. */
  tokenTracker?: TokenTracker;
  /** Streaming token callback — each token is emitted as it arrives. */
  onToken?: (token: string) => void;
  /** Streaming reasoning/thinking callback. */
  onReasoningDelta?: (delta: string) => void;
  /** Called when a tool starts executing. */
  onToolStart?: (toolCallId: string, toolName: string, args: Record<string, unknown>) => void;
  /** Called when a tool finishes executing. */
  onToolEnd?: (toolCallId: string, toolName: string, result: ToolResult) => void;
  /** Codex-style thread event callback for timeline-driven UIs. */
  onThreadEvent?: (event: ThreadEvent) => void;
  /** Agent mailbox for inter-agent communication. */
  mailbox?: AgentMailbox;
}

export interface TurnResult {
  turnId: string;
  messages: ChatMessage[];
  answer: string;
  reasoning?: string;
  toolResults: ToolResult[];
  stopReason: string;
  turnState: AgentTurnState;
  turnsUsed: number;
}

export interface AgentRunResult {
  ok: boolean;
  sessionId: string;
  turnId: string;
  finalAnswer: string;
  reasoning?: string;
  events: AgentEvent[];
  summary: Record<string, unknown>;
  stopReason: string;
  turnState: AgentTurnState;
  toolCalls: Array<{ name: string; arguments: Record<string, unknown>; callId: string }>;
  toolResults: Record<string, unknown>[];
  status: string;
  outputType: string;
  availableSkills: string[];
  loadedSkills: string[];
  skillLoadsCount: number;
  skillsUsed: string[];
  skillCallsCount: number;
  skillResults: Record<string, unknown>[];
  modelBackend: string;
  modelProvider: string;
  modelName: string;
}

type CompareTaskTemplate = {
  fileA: string;
  fileB: string;
};

type CreateArtifactTaskTemplate = {
  targetHint: string;
};

function normalizeSkillName(value: string): string {
  return value
    .trim()
    .replace(/^["'`]+/, '')
    .replace(/["'`]+$/, '')
    .trim()
    .toLowerCase();
}

// ============================================================================
// AgentLoop
// ============================================================================

export class AgentLoop {
  private config: Required<Omit<AgentLoopConfig, 'tools' | 'toolRuntime' | 'eventBus' | 'provider' | 'skillRegistry' | 'skillExecutor' | 'hooks' | 'sessionStore' | 'memoryStore' | 'contextStore' | 'tokenTracker' | 'onToken' | 'onReasoningDelta' | 'onToolStart' | 'onToolEnd' | 'onThreadEvent' | 'mailbox'>> & {
    tools?: ToolRegistry;
    toolRuntime?: ToolRuntime;
    eventBus?: AgentEventBus;
    provider?: LLMProvider | FallbackLLMProvider;
    tokenTracker?: TokenTracker;
    onToken?: (token: string) => void;
    onReasoningDelta?: (delta: string) => void;
    onToolStart?: (callId: string, toolName: string, args: Record<string, unknown>) => void;
    onToolEnd?: (callId: string, toolName: string, result: ToolResult) => void;
    onThreadEvent?: (event: ThreadEvent) => void;
    skillRegistry?: SkillRegistry;
    skillExecutor?: SkillExecutor;
    hooks?: HookRegistry;
    sessionStore?: SessionStoreLike;
    memoryStore?: MemoryStoreLike;
    contextStore?: { retrieveRecentContext(sessionId: string): Record<string, unknown> };
    mailbox?: AgentMailbox;
  };
  private provider: LLMProvider | FakeModelClient | FallbackLLMProvider;
  private tools?: ToolRegistry;
  private toolRuntime?: ToolRuntime;
  private eventBus?: AgentEventBus;
  private contextBuilder: ContextBuilder;
  private promptBuilder: PromptBuilder;
  private skillRegistry?: SkillRegistry;
  private skillExecutor?: SkillExecutor;
  private hooks?: HookRegistry;
  private summaryComposer: ResponseComposer;
  private errorClassifier: ErrorClassifier;
  private toolRetryPolicy: ToolRetryPolicy;
  private replanPolicy: ReplanPolicy;
  private projectRoot: string;
  private permissionMode: string;
  private maxSteps: number;
  private timeoutS: number;
  private toolTimeoutS: number;
  private autoApprove: boolean;
  private modelInfo: Record<string, string>;
  readonly mailbox: AgentMailbox | undefined;

  // Lifecycle control (Codex AgentStatus + Hermes interrupt pattern)
  private _interrupted = false;
  private _paused = false;
  private _pausedResolve: (() => void) | null = null;
  private _activeToolAbortController: AbortController | null = null;
  private _llmAbortController: AbortController | null = null;

  /** Signal the agent to pause at the next step boundary. */
  get paused(): boolean { return this._paused; }

  /** Signal the agent to stop at the next step boundary. */
  get interrupted(): boolean { return this._interrupted; }

  /** Reset lifecycle control flags before starting a fresh run. */
  private resetLifecycleControl(): void {
    this._activeToolAbortController?.abort();
    this._activeToolAbortController = null;
    this._llmAbortController?.abort();
    this._llmAbortController = null;
    this._interrupted = false;
    this._paused = false;
    this._pausedResolve = null;
  }

  /**
   * Interrupt this agent — it will stop at the next step boundary.
   * Mirrors Codex's AgentControl.interrupt_agent().
   */
  interrupt(reason?: string): void {
    this._interrupted = true;
    this._activeToolAbortController?.abort();
    this._llmAbortController?.abort();
    if (this._pausedResolve) {
      // If agent is paused, resume it so it can notice the interrupt
      this._pausedResolve();
      this._pausedResolve = null;
    }
    this.eventBus?.emit('agent:interrupted', { reason: reason ?? 'interrupted' });
  }

  /**
   * Pause this agent — it will block at the next step boundary until resume() is called.
   */
  pause(): void {
    this._paused = true;
  }

  /**
   * Resume a paused agent.
   */
  resume(): void {
    this._paused = false;
    if (this._pausedResolve) {
      this._pausedResolve();
      this._pausedResolve = null;
    }
    this.eventBus?.emit('agent:resumed', {});
  }

  /**
   * Redirect this agent to a new task. Interrupts current work and queues a new goal.
   */
  redirect(newTask: string): void {
    this._interrupted = true;
    if (this._pausedResolve) {
      this._pausedResolve();
      this._pausedResolve = null;
    }
    this._paused = false;
    // Deliver new task via mailbox so it's picked up on next turn
    if (this.mailbox) {
      this.mailbox.deliver('supervisor', `[REDIRECT] Your task has changed. New task:\n\n${newTask}`, true);
    }
    this.eventBus?.emit('agent:redirected', { newTask });
  }

  constructor(config: AgentLoopConfig) {
    this.config = {
      model: config.model,
      maxTurns: config.maxTurns ?? 30,
      systemPrompt: config.systemPrompt ?? '',
      context: config.context ?? {},
      maxSkills: config.maxSkills ?? 5,
      projectRoot: config.projectRoot ?? process.cwd(),
      permissionMode: config.permissionMode ?? 'workspace_write',
      maxSteps: config.maxSteps ?? 50,
      timeoutS: config.timeoutS ?? 3600,
      toolTimeoutS: config.toolTimeoutS ?? 300,
      autoApprove: config.autoApprove ?? false,
      tools: config.tools,
      toolRuntime: config.toolRuntime,
      eventBus: config.eventBus,
      provider: config.provider,
      onThreadEvent: config.onThreadEvent,
      onToken: config.onToken,
      onReasoningDelta: config.onReasoningDelta,
      onToolStart: config.onToolStart,
      onToolEnd: config.onToolEnd,
      skillRegistry: config.skillRegistry,
      skillExecutor: config.skillExecutor,
      hooks: config.hooks,
      sessionStore: config.sessionStore,
      memoryStore: config.memoryStore,
      contextStore: config.contextStore,
      mailbox: config.mailbox,
    };

    this.provider = config.provider ?? new LLMProvider(config.model);
    this.tools = config.tools;
    this.toolRuntime = config.toolRuntime;
    this.eventBus = config.eventBus;
    this.projectRoot = this.config.projectRoot;
    this.permissionMode = this.config.permissionMode;
    this.maxSteps = this.config.maxSteps;
    this.timeoutS = this.config.timeoutS;
    this.toolTimeoutS = this.config.toolTimeoutS;
    this.autoApprove = this.config.autoApprove;
    this.skillRegistry = config.skillRegistry;
    this.skillExecutor = config.skillExecutor;
    this.hooks = config.hooks;

    this.mailbox = config.mailbox;

    this.modelInfo = this._getModelInfo();

    const contextWindow = resolveContextWindow(this.config.model.model);
    this.contextBuilder = new ContextBuilder(
      { maxTokens: contextWindow, ...config.context },
      {
        sessionStore: config.sessionStore,
        memoryStore: config.memoryStore,
        skillRegistry: config.skillRegistry as unknown as SkillRegistryLike,
        contextStore: config.contextStore,
        modelInfo: this.modelInfo as unknown as Record<string, unknown>,
        permissionMode: this.permissionMode,
      },
    );

    this.promptBuilder = new PromptBuilder();
    this.summaryComposer = new ResponseComposer();
    this.errorClassifier = new ErrorClassifier();
    this.toolRetryPolicy = new ToolRetryPolicy(2);
    this.replanPolicy = new ReplanPolicy(2);
  }

  private emitThreadEvent(event: ThreadEvent): void {
    this.config.onThreadEvent?.(event);
    this.eventBus?.emitThreadEvent(event);
  }

  private beginToolDispatch(): AbortSignal {
    this._activeToolAbortController?.abort();
    this._activeToolAbortController = new AbortController();
    return this._activeToolAbortController.signal;
  }

  private endToolDispatch(): void {
    this._activeToolAbortController = null;
  }

  private buildTurnUsage(): ThreadUsage | null {
    const snapshot = this.config.tokenTracker?.snapshot();
    if (!snapshot) return null;
    return {
      input_tokens: snapshot.inputTokens,
      cached_input_tokens: snapshot.cachedTokens,
      output_tokens: snapshot.outputTokens,
    };
  }

  // ========================================================================
  // Simple run() — legacy compat path, prefer runTurn() for new code
  // ========================================================================

  /** @deprecated Use runTurn() for new code. run() is kept for backward
   *  compatibility with existing tests and callers that don't need the
   *  richer AgentRunResult. Shared tool execution via executeToolCall()
   *  ensures consistent behavior with runTurn(). */
  async run(
    userMessage: string,
    history: ChatMessage[] = [],
  ): Promise<TurnResult> {
    this.resetLifecycleControl();
    const turnId = `turn_${crypto.randomUUID()}`;
    const inferredThreadId = `thread_${history[0]?.messageId?.slice(4) ?? turnId.slice(5)}`;
    let allMessages: ChatMessage[] = [...history];
    const allToolResults: ToolResult[] = [];
    let streamingReasoningText = '';
    let streamingReasoningItemId: string | null = null;
    let streamingReasoningCompleted = false;
    let streamingMessageText = '';
    let streamingMessageItemId: string | null = null;

    const userMsg: ChatMessage = {
      role: 'user',
      content: userMessage,
      messageId: `msg_${crypto.randomUUID()}`,
    };
    allMessages.push(userMsg);

    if (history.length === 0) {
      this.emitThreadEvent({
        type: 'thread.started',
        thread_id: inferredThreadId,
      });
    }
    this.emitThreadEvent({
      type: 'turn.started',
      turn_id: turnId,
    });
    this.eventBus?.emit('turn:start', { turnId, userMessage });

    // Match skills
    const modelName = this.config.model.model ?? 'unknown';
    let effectiveSystemPrompt = this.config.systemPrompt || AGENT_SYSTEM_PROMPT.replace('{model_name}', modelName);
    if (this.skillRegistry && this.skillExecutor) {
      try {
        const skillResult = this.skillExecutor.execute({
          taskText: userMessage,
          maxSkills: this.config.maxSkills,
        });
        if (skillResult.included.length > 0) {
          const skillNames = skillResult.included.map((s) => s.name).join(', ');
          effectiveSystemPrompt = [
            this.config.systemPrompt,
            skillResult.instructionBlock,
          ].filter(Boolean).join('\n\n');
          this.eventBus?.emit('skills:matched', {
            turnId,
            skills: skillResult.included.map((s) => ({ name: s.name, score: 0 })),
          });
        }
      } catch (err) {
        this.eventBus?.emit('info', {
          message: `Skill matching failed: ${err instanceof Error ? err.message : String(err)}`,
        });
      }
    }

    let turnsUsed = 0;
    let finalContent = '';
    let stopReason = 'unknown';
    let turnFailedMessage: string | null = null;
    let retryWithToolInstructionCount = 0;

    for (let turn = 0; turn < this.config.maxTurns; turn++) {
      turnsUsed = turn + 1;

      // Drain mailbox for inter-agent messages (Codex mailbox pattern)
      if (this.mailbox) {
        const mails = this.mailbox.drain();
        for (const mail of mails) {
          allMessages.push({
            role: 'user',
            content: formatMailboxContent(mail),
            messageId: `msg_${crypto.randomUUID()}`,
          });
        }
      }

      const llmMessages = this.contextBuilder.buildMessages(effectiveSystemPrompt, allMessages);

      // Compaction check — use full pipeline (truncation stages only, no LLM at pre-turn)
      const estimatedTokens = this.contextBuilder.estimateMessageTokens(allMessages);
      if (this.contextBuilder.shouldCompress(estimatedTokens)) {
        this.eventBus?.emit('context:compressing', {
          turnId,
          estimatedTokens,
          maxTokens: this.config.context.maxTokens ?? 128_000,
        });
        const compactable = allMessages.map((m) => ({
          role: m.role,
          content: m.content,
        })) as CompactionMessage[];
        const result = await compact(compactable, {
          contextWindow: this.config.context.maxTokens ?? 128_000,
        });
        allMessages = result.messages.map((m) => ({
          ...m,
          role: m.role as ChatMessage['role'],
        })) as ChatMessage[];
      }

      const toolDefs = this.tools ? this.tools.getDefinitions() : [];

      this.eventBus?.emit('llm:request', { turnId, turn, messageCount: llmMessages.length });

      let response: Awaited<ReturnType<LLMProvider['chat']>> | Awaited<ReturnType<LLMProvider['chatStream']>>;
      try {
        if (this.config.onToken) {
          // Streaming mode: no retry (partial tokens already emitted)
          response = await (this.provider as LLMProvider).chatStream(
            llmMessages,
            toolDefs,
            {
              onToken: (token) => {
                if (!streamingReasoningCompleted && streamingReasoningItemId) {
                  this.emitThreadEvent({
                    type: 'item.completed',
                    turn_id: turnId,
                    item: {
                      id: streamingReasoningItemId,
                      type: 'reasoning',
                      text: streamingReasoningText,
                    },
                  });
                  streamingReasoningCompleted = true;
                }
                streamingMessageText += token;
                if (!streamingMessageItemId) {
                  streamingMessageItemId = `item_agent_message_${crypto.randomUUID()}`;
                  this.emitThreadEvent({
                    type: 'item.started',
                    turn_id: turnId,
                    item: {
                      id: streamingMessageItemId,
                      type: 'agent_message',
                      text: streamingMessageText,
                    },
                  });
                } else {
                  this.emitThreadEvent({
                    type: 'item.updated',
                    turn_id: turnId,
                    item: {
                      id: streamingMessageItemId,
                      type: 'agent_message',
                      text: streamingMessageText,
                    },
                  });
                }
                this.config.onToken?.(token);
              },
              onReasoningDelta: (delta) => {
                streamingReasoningText += delta;
                if (!streamingReasoningItemId) {
                  streamingReasoningItemId = `item_reasoning_${crypto.randomUUID()}`;
                  this.emitThreadEvent({
                    type: 'item.started',
                    turn_id: turnId,
                    item: {
                      id: streamingReasoningItemId,
                      type: 'reasoning',
                      text: streamingReasoningText,
                    },
                  });
                } else {
                  this.emitThreadEvent({
                    type: 'item.updated',
                    turn_id: turnId,
                    item: {
                      id: streamingReasoningItemId,
                      type: 'reasoning',
                      text: streamingReasoningText,
                    },
                  });
                }
                this.config.onReasoningDelta?.(delta);
              },
            },
          );
        } else {
          response = await withRetry(
            () => (this.provider as LLMProvider).chat(llmMessages, toolDefs),
            {
              maxRetries: this.config.model.maxRetries ?? 3,
              baseDelay: 5_000,
              maxDelay: 120_000,
            },
          );
        }
      } catch (err) {
        const errMsg = err instanceof Error ? err.message : String(err);
        this.eventBus?.emit('llm:error', { turnId, turn, error: errMsg });
        stopReason = 'llm_error';
        finalContent = `Error calling LLM after retries: ${errMsg}`;
        turnFailedMessage = errMsg;
        break;
      }

      const { content, toolCalls, finishReason } = response;

      if (streamingReasoningItemId && !streamingReasoningCompleted) {
        this.emitThreadEvent({
          type: 'item.completed',
          turn_id: turnId,
          item: {
            id: streamingReasoningItemId,
            type: 'reasoning',
            text: streamingReasoningText,
          },
        });
        streamingReasoningCompleted = true;
      }
      if (content && !streamingMessageItemId) {
        streamingMessageItemId = `item_agent_message_${crypto.randomUUID()}`;
        this.emitThreadEvent({
          type: 'item.started',
          turn_id: turnId,
          item: {
            id: streamingMessageItemId,
            type: 'agent_message',
            text: content,
          },
        });
      }
      if (streamingMessageItemId) {
        this.emitThreadEvent({
          type: 'item.completed',
          turn_id: turnId,
          item: {
            id: streamingMessageItemId,
            type: 'agent_message',
            text: content || streamingMessageText,
          },
        });
        streamingMessageItemId = null;
        streamingMessageText = '';
      }
      streamingReasoningItemId = null;
      streamingReasoningText = '';
      streamingReasoningCompleted = false;

      this.eventBus?.emit('llm:response', {
        turnId,
        turn,
        finishReason,
        contentLength: content.length,
        toolCallCount: toolCalls.length,
      });

      const assistantMsg: ChatMessage = {
        role: 'assistant',
        content,
        messageId: `msg_${crypto.randomUUID()}`,
      };
      allMessages.push(assistantMsg);

      if (finishReason === 'stop') {
        finalContent = content;
        stopReason = 'stop';
        break;
      }

      if (finishReason === 'retry_with_tool_instruction') {
        retryWithToolInstructionCount++;
        if (retryWithToolInstructionCount >= 3) {
          this.eventBus?.emit('turn:warning', {
            turnId, turn,
            warning: 'retry_with_tool_instruction exhausted',
          });
          stopReason = 'retry_with_tool_instruction';
          break;
        }
        const nudge: ChatMessage = {
          role: 'user',
          content:
            'Your last response described what you intend to do ' +
            'but did NOT actually call any tool. You MUST call the ' +
            'appropriate tool function directly — do NOT just say ' +
            'what you will do. Use the tool now.',
          messageId: `msg_${crypto.randomUUID()}`,
        };
        allMessages.push(nudge);
        continue;
      }

      if (finishReason === 'tool_calls' && toolCalls.length > 0) {
        for (const tc of toolCalls) {
          const startedAt = Date.now();
          const toolItemBase: ToolCallThreadItem = {
            id: tc.callId,
            type: 'tool_call',
            tool_name: tc.name,
            arguments: tc.arguments,
            status: 'in_progress',
          };
          this.emitThreadEvent({
            type: 'item.started',
            turn_id: turnId,
            item: toolItemBase,
          });
          this.eventBus?.emit('tool:executing', {
            turnId, turn, toolName: tc.name, args: tc.arguments,
          });
          this.config.onToolStart?.(tc.callId, tc.name, tc.arguments);

          const signal = this.beginToolDispatch();
          let toolResult: ToolResult;
          try {
            toolResult = await this.executeToolCall(tc.name, tc.arguments, tc.callId, {
              signal,
            });
          } finally {
            this.endToolDispatch();
          }

          allToolResults.push(toolResult);

          const toolMsg: ChatMessage = {
            role: 'tool',
            content: toolResult.content,
            messageId: `msg_${crypto.randomUUID()}`,
            name: tc.name,
            toolCallId: tc.callId,
          };
          allMessages.push(toolMsg);

          this.eventBus?.emit('tool:result', {
            turnId, turn, toolName: tc.name,
            ok: toolResult.ok,
            contentLength: toolResult.content.length,
            durationMs: toolResult.durationMs,
          });
          this.emitThreadEvent({
            type: 'item.completed',
            turn_id: turnId,
            item: {
              ...toolItemBase,
              status: toolResult.ok ? 'completed' : 'failed',
              result: toolResult.content,
              error: toolResult.error,
              duration_ms: toolResult.durationMs,
            },
          });
          this.config.onToolEnd?.(tc.callId, tc.name, toolResult);
        }
        continue;
      }

      if (finishReason === 'length') {
        finalContent = content;
        stopReason = 'length';
        this.eventBus?.emit('turn:warning', { turnId, turn, warning: 'Response truncated due to length limit' });
        break;
      }

      if (finishReason === 'content_filter') {
        stopReason = 'content_filter';
        finalContent = content || 'Response blocked by content filter';
        break;
      }

      finalContent = content;
      stopReason = finishReason;
      break;
    }

    if (turnsUsed >= this.config.maxTurns && !finalContent) {
      stopReason = 'max_turns';
      finalContent = allMessages.filter((m) => m.role === 'assistant').pop()?.content ?? '';
    }

    this.eventBus?.emit('turn:complete', {
      turnId, turnsUsed, stopReason, answerLength: finalContent.length,
    });
    if (turnFailedMessage) {
      this.emitThreadEvent({
        type: 'turn.failed',
        turn_id: turnId,
        error: { message: turnFailedMessage },
      });
    } else {
      this.emitThreadEvent({
        type: 'turn.completed',
        turn_id: turnId,
        stop_reason: stopReason,
        usage: this.buildTurnUsage(),
      });
    }

    return {
      turnId,
      messages: allMessages,
      answer: finalContent,
      toolResults: allToolResults,
      stopReason,
      turnState: mapStopReasonToTurnState(stopReason),
      turnsUsed,
    }; // note: reasoning not captured in compressed path (no model call)
  }

  // ========================================================================
  // Full runTurn() — matches Python AgentLoop.run_turn()
  // ========================================================================

  async runTurn(userInput: string, opts?: {
    sessionId?: string;
    projectId?: string;
    cwd?: string;
  }): Promise<AgentRunResult> {
    this.resetLifecycleControl();
    const started = Date.now();
    const sessionId = opts?.sessionId ?? `session_${crypto.randomUUID()}`;
    const turnId = `turn_${crypto.randomUUID()}`;
    const cwd = opts?.cwd ?? this.projectRoot;
    const threadId = `thread_${sessionId.replace(/^session_/, '')}`;

    const events: AgentEvent[] = [];
    const toolCallsLog: Array<{ name: string; arguments: Record<string, unknown>; callId: string }> = [];
    const toolResultsLog: Record<string, unknown>[] = [];
    let stopReason = 'max_steps';
    let finalAnswer = '';
    let reasoning = '';
    let outputType = 'answer';
    const availableSkills: string[] = this.skillRegistry
      ? this.skillRegistry.listLoadable().map((s) => s.name)
      : [];
    const loadedSkills: string[] = [];
    let activeAllowedTools: string[] | undefined = undefined; // undefined = all tools allowed
    const skillResultsLog: Record<string, unknown>[] = [];
    const skillsUsed: string[] = [];

    this.emitThreadEvent({
      type: 'thread.started',
      thread_id: threadId,
    });
    this.emitThreadEvent({
      type: 'turn.started',
      turn_id: turnId,
    });

    // Build context
    const turnContext = await this.contextBuilder.buildContext({
      sessionId,
      turnId,
      userInput,
      cwd,
      projectId: opts?.projectId ?? undefined,
      runtimeState: {
        cwd,
        permission_mode: this.permissionMode,
        model_backend: this.modelInfo['model_backend'],
        model_provider: this.modelInfo['model_provider'],
        model_name: this.modelInfo['model_name'],
      },
    });

    const { messages } = this.contextBuilder.buildMessagesFromContext(turnContext, this.promptBuilder);
    const compareTaskTemplate = this._buildCompareTaskTemplate(userInput);
    const createArtifactTaskTemplate = compareTaskTemplate ? null : this._buildCreateArtifactTaskTemplate(userInput);
    let structuredFinalizeRetries = 0;
    const collectedReadPaths = new Set<string>();
    let sawDiffEvidence = false;
    let sawWorkspaceInspectionEvidence = false;
    let sawWriteEvidence = false;

    if (compareTaskTemplate) {
      messages.push({
        role: 'user',
        content: this._buildCompareTemplateInstruction(compareTaskTemplate),
      });
    } else if (createArtifactTaskTemplate) {
      messages.push({
        role: 'user',
        content: this._buildCreateArtifactTemplateInstruction(createArtifactTaskTemplate),
      });
    }

    // Obtain tool specs filtered by activeAllowedTools (updated dynamically per-step)
    const getToolSpecs = (): Record<string, unknown>[] => {
      if (forceNoToolsNextStep) return [];
      return this.tools
        ? this.tools.getDefinitions(
            activeAllowedTools
              ? [...new Set([...activeAllowedTools, 'skill.load'])]
              : undefined,
          )
        : [];
    };

    // Failure tracking + convergence state machine
    // maxRepeat=25: each tool can be called up to 25 times per turn.
    // Bumped from 3 — multi-URL reads and large refactors need many calls.
    const failureTracker = new FailureTracker(10, 8, 25);
    let noProgressCount = 0;
    let lastProgressMarker = '';
    const seenCalls = new Map<string, Array<{ argsFrozen: string; result: Record<string, unknown> }>>();
    let retryWithToolInstructionCount = 0;
    let retryWithLengthCount = 0;
    let forceNoToolsNextStep = false;
    let forcedSynthesisAttempted = false;
    let reasoningLenHighWaterMark = 0;
    let stagnationCount = 0;
    let finalizeAttempts = 0;
    let finalizeReason: 'stagnation' | 'rejections' | null = null;
    let phase: 'discover' | 'analyze' | 'finalize' = 'discover';
    const emitTurnPhase = (
      phaseName: 'discover' | 'analyze' | 'finalize',
      detail: string,
      extra: Record<string, unknown> = {},
    ): void => {
      this.eventBus?.emit('turn:phase', {
        turnId,
        phase: phaseName,
        detail,
        ...extra,
      });
    };

    const enterFinalize = (reason: 'stagnation' | 'rejections'): boolean => {
      if (compareTaskTemplate) {
        const evidenceCheck = this._checkCompareEvidence(
          compareTaskTemplate,
          collectedReadPaths,
          sawDiffEvidence,
        );
        if (!evidenceCheck.ok) {
          messages.push({
            role: 'user',
            content:
              `Evidence is incomplete. Before finalizing, gather missing evidence: ${evidenceCheck.missing.join('; ')}. ` +
              'Use tools now and then produce the final Markdown answer.',
          });
          return false;
        }
      }
      if (createArtifactTaskTemplate) {
        const evidenceCheck = this._checkCreateArtifactEvidence(
          createArtifactTaskTemplate,
          sawWorkspaceInspectionEvidence,
          sawWriteEvidence,
        );
        if (!evidenceCheck.ok) {
          messages.push({
            role: 'user',
            content:
              `Evidence is incomplete. Before finalizing, gather missing evidence: ${evidenceCheck.missing.join('; ')}. ` +
              'Use tools now and then produce the final Markdown answer.',
          });
          return false;
        }
      }
      if (phase !== 'finalize') {
        phase = 'finalize';
        finalizeReason = reason;
        finalizeAttempts = 0;
        forceNoToolsNextStep = true;
        this._emit(events, turnId, 'phase_changed', { phase, reason });
        emitTurnPhase('finalize', 'enter_finalize', { reason });
        this.eventBus?.emit('turn:warning', {
          warning: 'Finalizing answer from collected results',
        });
        messages.push({
          role: 'user',
          content:
            'Stop calling tools now. Use only the evidence already collected and produce the final answer in Markdown.',
        });
      }
      return true;
    };

    try {
      for (let step = 1; step <= this.maxSteps; step++) {
        finalAnswer = '';
        if (phase === 'discover' && step > 1) {
          phase = 'analyze';
          this._emit(events, turnId, 'phase_changed', { phase });
          emitTurnPhase('analyze', 'entered_analysis', { step });
        }

        if ((Date.now() - started) > this.timeoutS * 1000) {
          stopReason = 'timeout';
          break;
        }

        // Check for interrupt/pause (Codex AgentStatus + Hermes interrupt pattern)
        if (this._interrupted) {
          stopReason = 'interrupted';
          finalAnswer = 'Agent was interrupted.';
          break;
        }
        if (this._paused) {
          // Block until resumed or interrupted
          await new Promise<void>((resolve) => {
            this._pausedResolve = resolve;
          });
          this._pausedResolve = null;
          if (this._interrupted) {
            stopReason = 'interrupted';
            finalAnswer = 'Agent was interrupted while paused.';
            break;
          }
        }

        // Drain mailbox for inter-agent messages (Codex mailbox pattern)
        if (this.mailbox) {
          const mails = this.mailbox.drain();
          for (const mail of mails) {
            messages.push({
              role: 'user',
              content: formatMailboxContent(mail),
            });
          }
        }

        // Context window usage — estimate full context (messages + tools)
        const currentToolSpecs = getToolSpecs();
        const contextBreakdown = this._estimateContextBreakdown(
          messages as LLMMessage[],
          currentToolSpecs,
          this.config.context.maxTokens!,
        );
        const contextUsed = (contextBreakdown.estimated_total_tokens as number) ?? 0;
        const contextPct = this.config.context.maxTokens! > 0
          ? contextUsed / this.config.context.maxTokens!
          : 0;
        this._emit(events, turnId, 'context_window_usage', {
          used_tokens: contextUsed,
          context_window: this.config.context.maxTokens!,
          usage_pct: Math.round(contextPct * 1000) / 1000,
          message_count: messages.length,
        });
        this._emit(events, turnId, 'context_usage_breakdown', contextBreakdown);

        // Model call with retry
        this._emit(events, turnId, 'model_call_started', { step });
        const modelResp = await this._callModelWithRetry(
          events,
          turnId,
          step,
          messages as LLMMessage[],
          currentToolSpecs,
        );
        if (forceNoToolsNextStep) {
          forceNoToolsNextStep = false;
        }
        this._emit(events, turnId, 'model_call_completed', {
          step,
          finish_reason: modelResp.finishReason,
        });

        // Capture reasoning for TUI display (separate from finalAnswer)
        const stepReasoning = modelResp.reasoningSummary;
        if (stepReasoning && stepReasoning !== finalAnswer) {
          reasoning = stepReasoning;
        }

        // Handle length (truncated)
        if (modelResp.finishReason === 'length' && retryWithLengthCount < 1) {
          retryWithLengthCount++;
          this._emit(events, turnId, 'length_retry_started', { step });
          // Compact — trim older tool results
          const compacted = this.contextBuilder.compactToolResults(
            messages.map((m) => ({ role: m.role as ChatMessage['role'], content: m.content, messageId: '' })),
          );
          messages.length = 0;
          messages.push(...compacted.map((m) => ({ role: m.role, content: m.content })));
          continue;
        }

        if (modelResp.finalAnswer) {
          finalAnswer = modelResp.finalAnswer;
        } else if (modelResp.assistantText && modelResp.toolCalls.length === 0) {
          finalAnswer = modelResp.assistantText;
        }

        if (finalAnswer && modelResp.toolCalls.length === 0) {
          if (compareTaskTemplate) {
            const structCheck = this._validateStructuredCompareFinalAnswer(finalAnswer);
            if (!structCheck.ok && structuredFinalizeRetries < 2) {
              structuredFinalizeRetries++;
              if (finalizeReason === null) {
                enterFinalize('stagnation');
              }
              forceNoToolsNextStep = true;
              messages.push({
                role: 'user',
                content:
                  `Your answer is missing required structure: ${structCheck.missing.join(', ')}. ` +
                  'Rewrite now in Markdown with exactly these sections: 依据清单, 结论, 未确认点. ' +
                  'Use only collected evidence and do not call tools.',
              });
              continue;
            }
          }
          if (createArtifactTaskTemplate) {
            const evidenceCheck = this._checkCreateArtifactEvidence(
              createArtifactTaskTemplate,
              sawWorkspaceInspectionEvidence,
              sawWriteEvidence,
            );
            if (!evidenceCheck.ok) {
              messages.push({
                role: 'user',
                content:
                  `Evidence is incomplete. Before finalizing, gather missing evidence: ${evidenceCheck.missing.join('; ')}. ` +
                  'Use tools now and then produce the final Markdown answer.',
              });
              finalAnswer = '';
              continue;
            }
          }
          outputType = toolCallsLog.length > 0 ? 'tool_result' : 'answer';
          stopReason = finalizeReason !== null
            ? (finalizeReason === 'rejections' ? 'finalized_after_rejections' : 'finalized_after_stagnation')
            : 'completed';
          this._emit(events, turnId, 'final_answer_created', { step });
          break;
        }

        if (modelResp.toolCalls.length === 0 && !finalAnswer) {
          const finish = modelResp.finishReason;
          const assistantLower = (modelResp.assistantText || '').toLowerCase();

          if (assistantLower.includes('exit plan mode') || assistantLower.includes('not in plan mode')) {
            forceNoToolsNextStep = true;
            emitTurnPhase(phase, 'clearing_stale_plan_mode_state', { step });
            messages.push({
              role: 'user',
              content:
                'Plan mode is already finished for this task. Do not talk about exiting plan mode again. ' +
                'Either call the needed tool now or provide the final answer directly.',
            });
            continue;
          }

          if (createArtifactTaskTemplate && !sawWriteEvidence && !forceNoToolsNextStep) {
            retryWithToolInstructionCount++;
            if (retryWithToolInstructionCount <= 3) {
              messages.push({
                role: 'user',
                content:
                  `This task requires actually creating or updating ${createArtifactTaskTemplate.targetHint}. ` +
                  'Do not stop at describing the next step. Inspect the workspace if needed, then execute the required write/edit tool call now.',
              });
              continue;
            }
          }

          // Tool-intent retry (only before any tools have been called)
          if (finish === 'retry_with_tool_instruction') {
            if (finalizeReason !== null) {
              finalizeAttempts++;
              emitTurnPhase('finalize', 'retry_after_tool_intent_during_finalize', {
                step,
                finalizeReason,
                finalizeAttempts,
              });
              if (finalizeAttempts >= 2) {
                stopReason = 'finalize_timeout';
                outputType = 'partial';
                break;
              }
              forceNoToolsNextStep = true;
              emitTurnPhase('finalize', 'forcing_final_answer_no_tools', {
                step,
                finalizeReason,
                finalizeAttempts,
              });
              messages.push({
                role: 'user',
                content:
                  'Do not call tools. Provide the final Markdown deliverable now from the collected evidence.',
              });
              continue;
            }
            if (toolCallsLog.length === 0) {
              retryWithToolInstructionCount++;
              if (retryWithToolInstructionCount >= 3) {
                if (!forcedSynthesisAttempted) {
                  forcedSynthesisAttempted = true;
                  emitTurnPhase(phase, 'retry_with_tool_instruction_exhausted_force_choice', {
                    step,
                    retryWithToolInstructionCount,
                  });
                  messages.push({
                    role: 'user',
                    content:
                      'Your previous replies still did not execute the required tool. ' +
                      'In this reply, either call the appropriate tool directly or, if no tool is actually needed, provide the final answer now. ' +
                      'Do not explain what you plan to do.',
                  });
                  continue;
                }
                stopReason = 'retry_with_tool_instruction';
                break;
              }
              messages.push({
                role: 'user',
                content: [
                  'Your last response described what you intend to do but did NOT actually call any tool.',
                  'You MUST call the appropriate tool function directly - do NOT just say what you will do.',
                  'Use the tool now.',
                ].join('\n'),
              });
              continue;
            }
            if (!forcedSynthesisAttempted) {
              forcedSynthesisAttempted = true;
              forceNoToolsNextStep = true;
              emitTurnPhase('finalize', 'forced_synthesis_after_tool_collection', {
                step,
                toolCallsSoFar: toolCallsLog.length,
              });
              messages.push({
                role: 'user',
                content:
                  'Stop calling tools now. You already collected enough evidence. ' +
                  'Write the final answer directly in Markdown using only the results already gathered.',
              });
              continue;
            }
            if (finalizeReason === null && enterFinalize('stagnation')) {
              continue;
            }
            finalAnswer = modelResp.finalAnswer || modelResp.assistantText || '';
            if (!finalAnswer) {
              stopReason = finalizeReason !== null ? 'finalize_timeout' : (finish || 'no_progress');
              break;
            }
            if (compareTaskTemplate) {
              const structCheck = this._validateStructuredCompareFinalAnswer(finalAnswer);
              if (!structCheck.ok && structuredFinalizeRetries < 2) {
                structuredFinalizeRetries++;
                forceNoToolsNextStep = true;
                messages.push({
                  role: 'user',
                  content:
                    `Your answer is missing required structure: ${structCheck.missing.join(', ')}. ` +
                    'Rewrite now in Markdown with exactly these sections: 依据清单, 结论, 未确认点. ' +
                    'Do not call tools.',
                });
                continue;
              }
            }
            outputType = 'answer';
            stopReason = finalizeReason !== null
              ? (finalizeReason === 'rejections' ? 'finalized_after_rejections' : 'finalized_after_stagnation')
              : 'completed';
            break;
          }
          if (finalizeReason !== null) {
            finalizeAttempts++;
            emitTurnPhase('finalize', 'empty_step_during_finalize', {
              step,
              finalizeReason,
              finalizeAttempts,
            });
            if (finalizeAttempts >= 1) {
              stopReason = 'finalize_timeout';
              outputType = 'partial';
              break;
            }
            forceNoToolsNextStep = true;
            emitTurnPhase('finalize', 'forcing_markdown_answer', {
              step,
              finalizeReason,
              finalizeAttempts,
            });
            messages.push({
              role: 'user',
              content:
                'You must provide the final answer now in Markdown with no further tool calls.',
            });
            continue;
          }
          if (toolCallsLog.length > 0 && modelResp.assistantText && !forcedSynthesisAttempted) {
            forcedSynthesisAttempted = true;
            forceNoToolsNextStep = true;
            emitTurnPhase(phase, 'forcing_synthesis_after_tool_results', {
              step,
              toolCallsSoFar: toolCallsLog.length,
            });
            messages.push({
              role: 'user',
              content:
                'Use the evidence already collected and write the final Markdown answer now. ' +
                'Do not describe your next step and do not call more tools.',
            });
            continue;
          }
          stopReason = finish || 'no_progress';
          break;
        }

        // Build assistant message
        const assistantMsg: LLMMessage = {
          role: 'assistant',
          content: modelResp.reasoningSummary || modelResp.assistantText || '',
        };
        if (modelResp.toolCalls.length > 0) {
          assistantMsg.tool_calls = modelResp.toolCalls.map((tc) => ({
            id: tc.callId,
            type: 'function' as const,
            function: {
              name: tc.name,
              arguments: JSON.stringify(tc.arguments),
            },
          }));
        }
        messages.push(assistantMsg);

        if (finalizeReason !== null && modelResp.toolCalls.length > 0) {
          finalizeAttempts++;
          emitTurnPhase('finalize', 'tool_calls_emitted_during_finalize', {
            step,
            finalizeReason,
            finalizeAttempts,
            toolCallCount: modelResp.toolCalls.length,
          });
          if (finalizeAttempts >= 1) {
            stopReason = 'finalize_timeout';
            outputType = 'partial';
            break;
          }
          forceNoToolsNextStep = true;
          emitTurnPhase('finalize', 'rejecting_tool_calls_during_finalize', {
            step,
            finalizeReason,
            finalizeAttempts,
          });
          messages.push({
            role: 'user',
            content:
              'Finalization mode is active. Do not call tools. Output the final Markdown answer now.',
          });
          continue;
        }

        let anyOkThisStep = false;
        let requestForcedSynthesis = false;
        let newEvidenceThisStep = false;
        let lastConsecutiveFailureReason = '';

        // ── Phase 1: Pre-filter ──
        // Run fast checks (failure tracker, dedup) to determine which calls need execution.
        type PendingCall = {
          call: typeof modelResp.toolCalls[number];
          argsFrozen: string;
          toolItemBase: ToolCallThreadItem;
        };
        const pending: PendingCall[] = [];
        let earlyBreak = false;

        for (const call of modelResp.toolCalls) {
          const toolItemBase: ToolCallThreadItem = {
            id: call.callId,
            type: 'tool_call',
            tool_name: call.name,
            arguments: call.arguments,
            status: 'in_progress',
          };

          // FailureTracker check
          const reject = failureTracker.shouldRejectTool(call.name);
          if (reject.reject) {
            this._emit(events, turnId, 'tool_rejected', {
              step, tool_name: call.name, reason: reject.reason, kind: reject.kind,
            });
            if (reject.kind === 'repeat') {
              if (failureTracker.isRepeatHardStop(call.name)) {
                requestForcedSynthesis = enterFinalize('rejections');
                earlyBreak = true;
                break;
              }
              messages.push({
                role: 'user',
                content: `<rejected>You have called \`${call.name}\` too many times. Do NOT call it again. Synthesize your final answer NOW from the results you already have. Write the answer directly — no more tool calls.</rejected>`,
              });
              continue;
            }
            messages.push({
              role: 'user',
              content: `Tool \`${call.name}\` rejected: ${reject.reason}`,
            });
            continue;
          }

          // skill.load dedup
          if (call.name === 'skill.load') {
            const rawSkillName = String(
              call.arguments['name']
              ?? call.arguments['skill']
              ?? call.arguments['skill_name']
              ?? '',
            ).trim();
            const wantedSkillName = normalizeSkillName(rawSkillName);
            const alreadyLoaded = wantedSkillName
              ? loadedSkills.some((loaded) => normalizeSkillName(loaded) === wantedSkillName)
              : false;
            if (alreadyLoaded) {
              this._emit(events, turnId, 'skill_already_loaded', { step, skill_name: rawSkillName });
              messages.push({
                role: 'user',
                content:
                  `Skill \`${rawSkillName || 'this skill'}\` is already loaded in this turn. ` +
                  'Do NOT call skill.load again. Continue executing the loaded skill instructions now and complete the task.',
              });
              failureTracker.recordSuccess(call.name);
              continue;
            }
          }

          // Tool dedup
          const argsFrozen = JSON.stringify(Object.entries(call.arguments).sort());
          const reused = this._findSeenResult(seenCalls, call.name, argsFrozen);
          if (reused) {
            toolCallsLog.push({ name: call.name, arguments: call.arguments, callId: call.callId });
            toolResultsLog.push(reused);
            messages.push({
              role: 'tool',
              tool_call_id: call.callId,
              content: this._observationText({ content: reused['content'] as string ?? '', ok: !!reused['ok'], name: call.name }),
            });
            failureTracker.recordSuccess(call.name);
            anyOkThisStep = true;
            if (this._isWorkspaceInspectionToolCall(call.name, call.arguments)) sawWorkspaceInspectionEvidence = true;
            if (this._isWriteLikeToolCall(call.name, call.arguments, reused)) sawWriteEvidence = true;
            if (call.name === 'skill.load') {
              const sn = String((reused['metadata'] as Record<string, unknown>)?.['skill_name'] || call.arguments['name'] || '');
              if (sn && !loadedSkills.includes(sn)) loadedSkills.push(sn);
            }
            continue;
          }

          // Needs execution — add to pending
          toolCallsLog.push({ name: call.name, arguments: call.arguments, callId: call.callId });
          pending.push({ call, argsFrozen, toolItemBase });
        }

        // ── Phase 2: Parallel execution ──
        // Execute all pending tool calls concurrently.
        if (!earlyBreak && pending.length > 0) {
          // Emit start events for all pending calls
          for (const p of pending) {
            this._emit(events, turnId, 'tool_call_started', { step, tool_call: { name: p.call.name, arguments: p.call.arguments } });
            this.emitThreadEvent({ type: 'item.started', turn_id: turnId, item: p.toolItemBase });
            this.config.onToolStart?.(p.call.callId, p.call.name, p.call.arguments);
          }

          // Dispatch all tools in parallel
          const signal = this.beginToolDispatch();
          const results = await Promise.all(
            pending.map(async (p) => {
              try {
                const result = await this.executeToolCall(p.call.name, p.call.arguments, p.call.callId, {
                  sessionId, turnId, signal,
                });
                return { pending: p, result };
              } catch (error) {
                // Synthesize error result
                const errResult: ToolResult = {
                  ok: false,
                  name: p.call.name,
                  callId: p.call.callId,
                  content: error instanceof Error ? error.message : String(error),
                  error: error instanceof Error ? error.message : String(error),
                  durationMs: 0,
                };
                return { pending: p, result: errResult };
              }
            }),
          );
          this.endToolDispatch();

          // ── Phase 3: Sequential post-processing ──
          for (const { pending: p, result } of results) {
            const { call, argsFrozen, toolItemBase } = p;

            // Handle blocked-by-hook result
            if (!result.ok && result.error === 'denied') {
              const blockedDict = { ...result, content: result.content };
              toolResultsLog.push(blockedDict);
              this._emit(events, turnId, 'tool_call_completed', { step, tool_result: { ...result, ok: false } });
              this.emitThreadEvent({
                type: 'item.completed',
                turn_id: turnId,
                item: { ...toolItemBase, status: 'failed', result: result.content, error: result.error, duration_ms: result.durationMs },
              });
              messages.push({ role: 'tool', tool_call_id: call.callId, content: this._observationText(result) });
              failureTracker.recordFailure(result.name, 'blocked', result.error ?? '', step);
              continue;
            }

            const resultDict = { ...result, content: result.content };
            toolResultsLog.push(resultDict);
            newEvidenceThisStep = true;
            const evidencePath = this._extractReadPathFromToolCall(call.name, call.arguments);
            if (evidencePath) collectedReadPaths.add(evidencePath);
            if (this._isDiffLikeToolCall(call.name, call.arguments)) sawDiffEvidence = true;
            if (this._isWorkspaceInspectionToolCall(call.name, call.arguments)) sawWorkspaceInspectionEvidence = true;
            if (this._isWriteLikeToolCall(call.name, call.arguments, resultDict)) sawWriteEvidence = true;

            this._emit(events, turnId, 'tool_call_completed', { step, tool_result: resultDict });
            this.emitThreadEvent({
              type: 'item.completed',
              turn_id: turnId,
              item: { ...toolItemBase, status: result.ok ? 'completed' : 'failed', result: result.content, error: result.error, duration_ms: result.durationMs },
            });
            this.config.onToolEnd?.(call.callId, call.name, result);

            const interactiveStop = this._extractInteractiveStopFromToolResult(call.name, result.content);
            if (interactiveStop) {
              finalAnswer = interactiveStop.finalAnswer;
              stopReason = interactiveStop.stopReason;
              outputType = 'answer';
              failureTracker.recordSuccess(result.name);
              anyOkThisStep = true;
              const entry = seenCalls.get(call.name) || [];
              entry.push({ argsFrozen, result: resultDict });
              seenCalls.set(call.name, entry);
              messages.push({ role: 'tool', tool_call_id: call.callId, content: this._observationText(result) });
              break;
            }

            // skill.load / Skill handling
            if ((call.name === 'skill.load' || call.name === 'Skill') && result.ok) {
              const resultMeta = (result as unknown as { metadata?: Record<string, unknown> }).metadata;
              const skillName = String(resultMeta?.['skill_name'] || call.arguments['name'] || '').trim();
              if (skillName && !loadedSkills.includes(skillName)) loadedSkills.push(skillName);
              if (skillName && this.skillRegistry) {
                const skillSpec = this.skillRegistry.get(skillName);
                const skillAllowed = skillSpec?.allowedTools ?? [];
                if (skillAllowed.length > 0) {
                  activeAllowedTools = activeAllowedTools === undefined
                    ? [...skillAllowed]
                    : [...new Set([...activeAllowedTools, ...skillAllowed])];
                }
              }
              const skillBody = this._observationText(result);
              messages.push({
                role: 'tool',
                tool_call_id: call.callId,
                content: `<skill-context name="${skillName}">\n${skillBody}\n</skill-context>\n\nThese are the complete instructions for the \`${skillName}\` skill. Call the tools described above NOW to complete the user's task. Do NOT describe what you plan to do — use the tool functions directly.`,
              });
              failureTracker.recordSuccess(result.name);
              anyOkThisStep = true;
              const entry = seenCalls.get(call.name) || [];
              entry.push({ argsFrozen, result: resultDict });
              seenCalls.set(call.name, entry);
              continue;
            }

            if (result.ok) {
              failureTracker.recordSuccess(result.name);
              anyOkThisStep = true;
              const entry = seenCalls.get(call.name) || [];
              entry.push({ argsFrozen, result: resultDict });
              seenCalls.set(call.name, entry);
              messages.push({ role: 'tool', tool_call_id: call.callId, content: this._observationText(result) });
              continue;
            }

            // Tool failed
            const classification = this.errorClassifier.classify(result);
            failureTracker.recordFailure(result.name, classification.category, result.error ?? '', step);

            const shouldStop = failureTracker.shouldStop();
            if (shouldStop.stop) {
              messages.push({ role: 'tool', tool_call_id: call.callId, content: this._observationText(result) });
              stopReason = 'consecutive_failures';
              outputType = 'error';
              finalAnswer = shouldStop.reason;
              lastConsecutiveFailureReason = shouldStop.reason;
              break;
            }

            // Retry transient errors
            if (this.toolRetryPolicy.shouldRetry(
              { name: call.name, arguments: call.arguments, callId: call.callId, source: 'model' },
              classification,
            ) && this.tools) {
              this._emit(events, turnId, 'retry_started', { step, tool_name: result.name, reason: classification.reason });
              const retrySignal = this.beginToolDispatch();
              const retryResult = await this.executeToolCall(call.name, call.arguments, call.callId, {
                sessionId, turnId, signal: retrySignal,
              });
              this.endToolDispatch();
              toolResultsLog.push({ ...retryResult, content: retryResult.content });
              if (retryResult.ok) {
                failureTracker.recordSuccess(retryResult.name);
                anyOkThisStep = true;
                newEvidenceThisStep = true;
                messages.push({ role: 'tool', tool_call_id: call.callId, content: this._observationText(retryResult) });
                continue;
              }
              const retryClass = this.errorClassifier.classify(retryResult);
              failureTracker.recordFailure(retryResult.name, retryClass.category, retryResult.error ?? '', step);
              const shouldStop2 = failureTracker.shouldStop();
              if (shouldStop2.stop) {
                messages.push({
                  role: 'tool',
                  tool_call_id: call.callId,
                  content: `${this._observationText(result)}\n\n[Retry also failed]\n${this._observationText(retryResult)}`,
                });
                stopReason = 'consecutive_failures';
                outputType = 'error';
                finalAnswer = shouldStop2.reason;
                break;
              }
            }

            messages.push({ role: 'tool', tool_call_id: call.callId, content: this._observationText(result) });
          }
        }

        if (requestForcedSynthesis) {
          continue;
        }

        if (['waiting_for_plan_edits', 'plan_cancelled', 'question_cancelled'].includes(stopReason)) {
          break;
        }

        if (['approval_required', 'timeout', 'consecutive_rejections'].includes(stopReason)) {
          break;
        }
        // consecutive_failures: let the model see errors and retry with different approach
        if (stopReason === 'consecutive_failures') {
          this._emit(events, turnId, 'turn:warning', {
            warning: `Multiple tools failed: ${lastConsecutiveFailureReason || 'check results below'}`,
          });
          messages.push({
            role: 'user',
            content:
              'Multiple tools above failed. Read the error messages carefully and try a different approach — ' +
              'use different commands, different paths, or a different tool entirely.',
          });
          stopReason = ''; // clear so the loop continues
          continue;
        }

        // Mid-turn compaction with safety margin
        const midPct = (this.contextBuilder.estimateMessageTokens(
          messages.map((m) => ({ role: m.role as ChatMessage['role'], content: m.content, messageId: '' })),
        ) * ContextBuilder.SAFETY_MARGIN) / this.config.context.maxTokens!;
        if (midPct > 0.70) {
          const compactable = messages.map((m) => ({
            role: m.role,
            content: typeof m.content === 'string' ? m.content : JSON.stringify(m.content),
          })) as CompactionMessage[];
          const ctxWindow = this.config.context.maxTokens!;

          if (midPct > 0.85) {
            // Stage 4-5: full compaction pipeline with LLM summarization
            const modelClient: CompactionModelClient = {
              complete: async (opts) => {
                const resp = await (this.provider as LLMProvider).chat(
                  opts.messages.map((msg) => ({ role: msg.role as 'user' | 'system', content: msg.content })),
                  [],
                );
                return { content: resp.content, text: resp.content };
              },
            };
            const result = await compact(compactable, {
              modelClient,
              contextWindow: ctxWindow,
            });
            messages.length = 0;
            messages.push(...result.messages.map((m) => ({
              role: m.role as LLMMessage['role'],
              content: m.content,
            })));
            this._emit(events, turnId, 'context:compacting', {
              stage: result.report.stage,
              tokensBefore: result.report.tokensBefore,
              tokensAfter: result.report.tokensAfter,
              usagePct: midPct,
            });
          } else {
            // Stage 1-3: lightweight truncation (no LLM call)
            const result = await compact(compactable, { contextWindow: ctxWindow });
            messages.length = 0;
            messages.push(...result.messages.map((m) => ({
              role: m.role as LLMMessage['role'],
              content: m.content,
            })));
          }
        }

        // No-progress detection + phase-driven convergence
        const reasoningGrowth = Math.max(0, reasoning.length - reasoningLenHighWaterMark);
        reasoningLenHighWaterMark = Math.max(reasoningLenHighWaterMark, reasoning.length);

        let progressScore = 0;
        if (newEvidenceThisStep) progressScore += 2;
        if (reasoningGrowth >= 120) progressScore += 1;
        if (modelResp.toolCalls.length > 0 && !anyOkThisStep) progressScore -= 1;

        const marker = `${toolCallsLog.length}:${toolResultsLog.length}:${finalAnswer.slice(0, 60)}`;
        if (marker === lastProgressMarker && progressScore <= 0) {
          noProgressCount++;
        } else if (progressScore > 0) {
          noProgressCount = 0;
        } else {
          noProgressCount += 1;
        }
        lastProgressMarker = marker;

        if (finalizeReason === null) {
          if (progressScore <= 0) {
            stagnationCount++;
          } else {
            stagnationCount = 0;
          }
          if (stagnationCount >= 3) {
            if (!newEvidenceThisStep && !modelResp.assistantText && modelResp.toolCalls.length > 0) {
              emitTurnPhase(phase, 'no_progress_hard_stop', {
                step,
                noProgressCount,
                finalizeReason,
              });
              stopReason = 'no_progress';
              outputType = 'partial';
              break;
            }
            enterFinalize('stagnation');
            continue;
          }
        }

        if (noProgressCount >= 5) {
          emitTurnPhase(finalizeReason !== null ? 'finalize' : phase, 'no_progress_hard_stop', {
            step,
            noProgressCount,
            finalizeReason,
          });
          stopReason = finalizeReason !== null ? 'finalize_timeout' : 'no_progress';
          outputType = 'partial';
          break;
        }
      }

      // Fallback final answer
      if (!finalAnswer) {
        finalAnswer = this._fallbackFinalAnswer(toolResultsLog, stopReason);
      }
      if (outputType === 'answer' && ['timeout', 'approval_required', 'max_steps', 'no_progress'].includes(stopReason)) {
        outputType = 'partial';
      }

      // Summary
      const summary = this.summaryComposer.compose({
        finalAnswer,
        toolResults: toolResultsLog.map((r) => ({
          callId: r['callId'] as string ?? '',
          name: r['name'] as string ?? '',
          ok: r['ok'] as boolean ?? false,
          content: r['content'] as string ?? '',
          error: r['error'] as string | undefined,
          durationMs: r['durationMs'] as number ?? 0,
        })),
        stopReason,
        outputType,
        availableSkills,
        loadedSkills,
        skillLoadsCount: loadedSkills.length,
        skillsUsed,
        skillCallsCount: skillResultsLog.length,
        skillResults: skillResultsLog,
      });

      const status = finalAnswer && stopReason === 'completed'
        ? 'completed'
        : !finalAnswer ? 'failed' : 'partial';

      this._emit(events, turnId, status !== 'failed' ? 'turn_completed' : 'turn_failed', {
        status, stop_reason: stopReason,
      });
      if (status === 'failed') {
        this.emitThreadEvent({
          type: 'turn.failed',
          turn_id: turnId,
          error: { message: finalAnswer || stopReason },
        });
      } else {
        this.emitThreadEvent({
          type: 'turn.completed',
          turn_id: turnId,
          stop_reason: stopReason,
          usage: this.buildTurnUsage(),
        });
      }

      return {
        ok: status !== 'failed',
        sessionId,
        turnId,
        finalAnswer,
        reasoning: reasoning || undefined,
        events,
        summary,
        stopReason,
        turnState: mapStopReasonToTurnState(stopReason),
        toolCalls: toolCallsLog,
        toolResults: toolResultsLog,
        status,
        outputType: outputType === 'error' && status === 'failed' ? 'error' : outputType,
        availableSkills,
        loadedSkills,
        skillLoadsCount: loadedSkills.length,
        skillsUsed,
        skillCallsCount: skillResultsLog.length,
        skillResults: skillResultsLog,
        modelBackend: this.modelInfo['model_backend'] || '',
        modelProvider: this.modelInfo['model_provider'] || '',
        modelName: this.modelInfo['model_name'] || '',
      };
    } catch (exc) {
      const err = exc instanceof Error ? exc : new Error(String(exc));
      this._emit(events, turnId, 'turn_failed', { error: err.message, error_type: err.constructor.name });
      this.emitThreadEvent({
        type: 'turn.failed',
        turn_id: turnId,
        error: { message: err.message },
      });
      const mappedReason = this._mapProviderErrorStopReason(exc);
      const friendlyMsg = this._friendlyErrorMessage(exc);
      const summary = this.summaryComposer.compose({
        finalAnswer: friendlyMsg,
        toolResults: [],
        stopReason: mappedReason,
        outputType: 'error',
        availableSkills,
        loadedSkills,
        skillLoadsCount: loadedSkills.length,
      });
      return {
        ok: false,
        sessionId,
        turnId,
        finalAnswer: friendlyMsg,
        reasoning: reasoning || undefined,
        events,
        summary,
        stopReason: mappedReason,
        turnState: mapStopReasonToTurnState(mappedReason),
        toolCalls: toolCallsLog,
        toolResults: toolResultsLog,
        status: 'failed',
        outputType: 'error',
        availableSkills,
        loadedSkills,
        skillLoadsCount: loadedSkills.length,
        skillsUsed,
        skillCallsCount: skillResultsLog.length,
        skillResults: skillResultsLog,
        modelBackend: this.modelInfo['model_backend'] || '',
        modelProvider: this.modelInfo['model_provider'] || '',
        modelName: this.modelInfo['model_name'] || '',
      };
    }
  }

  // ========================================================================
  // Shared tool execution — single code path for both run() and runTurn()
  // ========================================================================

  /**
   * Execute a tool call through ToolRuntime (if configured) or direct registry dispatch.
   * Shared by both run() and runTurn() to ensure consistent hook ordering,
   * permission enforcement, and result formatting.
   */
  private async executeToolCall(
    name: string,
    args: Record<string, unknown>,
    callId: string,
    context: { sessionId?: string; turnId?: string; signal?: AbortSignal },
  ): Promise<ToolResult> {
    const startedAt = Date.now();
    const timeoutMs = Math.max(1, Math.round(this.toolTimeoutS * 1000));

    // pre_tool_use hook
    if (this.hooks) {
      const hookResult = await this.hooks.runPreToolUse({
        toolName: name,
        toolArgs: args,
        sessionId: context.sessionId ?? '',
        turnId: context.turnId ?? '',
      });
      if (!hookResult.allowed) {
        return {
          callId,
          name,
          ok: false,
          content: JSON.stringify({
            error: `Tool "${name}" blocked: ${hookResult.reason ?? hookResult.message ?? 'denied by hook'}`,
          }),
          error: hookResult.reason ?? 'denied',
          durationMs: Date.now() - startedAt,
        };
      }
    }

    const toolAbortController = new AbortController();
    const parentSignal = context.signal;
    const onParentAbort = () => {
      toolAbortController.abort(parentSignal?.reason ?? 'tool_interrupted');
    };
    if (parentSignal) {
      if (parentSignal.aborted) {
        toolAbortController.abort(parentSignal.reason ?? 'tool_interrupted');
      } else {
        parentSignal.addEventListener('abort', onParentAbort, { once: true });
      }
    }

    let timeoutHandle: ReturnType<typeof setTimeout> | null = null;
    const onForcedParentAbort = () => {
      if (timeoutHandle) {
        clearTimeout(timeoutHandle);
        timeoutHandle = null;
      }
    };
    const resolveInterruptedToolResult = (resolve: (value: ToolResult) => void) => {
      onForcedParentAbort();
      resolve({
        callId,
        name,
        ok: false,
        content: JSON.stringify({
          error: `Tool "${name}" interrupted`,
        }),
        error: `Tool "${name}" interrupted`,
        errorType: 'interrupted',
        durationMs: Date.now() - startedAt,
      });
    };

    const forcedToolResultPromise = new Promise<ToolResult>((resolve) => {
      timeoutHandle = setTimeout(() => {
        toolAbortController.abort('tool_timeout');
        resolve({
          callId,
          name,
          ok: false,
          content: JSON.stringify({
            error: `Tool "${name}" timed out after ${timeoutMs}ms`,
            timeout_ms: timeoutMs,
          }),
          error: `Tool "${name}" timed out after ${timeoutMs}ms`,
          errorType: 'tool_timeout',
          durationMs: Date.now() - startedAt,
        });
      }, timeoutMs);

      if (parentSignal) {
        parentSignal.addEventListener('abort', onForcedParentAbort, { once: true });
        parentSignal.addEventListener('abort', () => resolveInterruptedToolResult(resolve), { once: true });
      }
    });

    const executeToolPromise: Promise<ToolResult> = (async () => {
      try {
        if (this.toolRuntime) {
          return await this.toolRuntime.execute(name, args, {
            sessionId: context.sessionId,
            signal: toolAbortController.signal,
          });
        }

        if (this.tools) {
          let rawResult = '';
          try {
            rawResult = await this.tools.dispatch(name, args, {
              signal: toolAbortController.signal,
            });
          } catch {
            rawResult = JSON.stringify({ error: `Tool dispatch failed: ${name}` });
          }
          let parsed: Record<string, unknown> | null = null;
          try { parsed = JSON.parse(rawResult); } catch { /* not JSON */ }
          return {
            callId,
            name,
            ok: parsed === null || typeof parsed.error !== 'string',
            content: rawResult,
            error: parsed && typeof parsed.error === 'string' ? parsed.error : undefined,
            durationMs: 0,
          };
        }

        return {
          callId,
          name,
          ok: false,
          content: '',
          error: 'No tool registry or runtime configured',
          durationMs: 0,
        };
      } catch (error) {
        const message = error instanceof Error ? error.message : `Tool execution failed: ${name}`;
        return {
          callId,
          name,
          ok: false,
          content: JSON.stringify({ error: message }),
          error: message,
          errorType: toolAbortController.signal.aborted ? 'interrupted' : 'tool_error',
          durationMs: Date.now() - startedAt,
        };
      }
    })();

    // If a tool ignores abort, we still need the turn to move on.
    void executeToolPromise.catch(() => {});
    let toolResult = await Promise.race([executeToolPromise, forcedToolResultPromise]);

    if (timeoutHandle) {
      clearTimeout(timeoutHandle);
      timeoutHandle = null;
    }
    if (parentSignal) {
      parentSignal.removeEventListener('abort', onParentAbort);
      parentSignal.removeEventListener('abort', onForcedParentAbort);
    }

    toolResult.durationMs = Date.now() - startedAt;

    // post_tool_use hook (fire-and-forget, audit-only)
    if (this.hooks) {
      this.hooks.runPostToolUse({
        toolName: name,
        toolArgs: args,
        toolResult: toolResult.content,
        sessionId: context.sessionId ?? '',
        turnId: context.turnId ?? '',
      }).catch(() => {});
    }

    return toolResult;
  }

  // ========================================================================
  // Private helpers
  // ========================================================================

  private _getModelInfo(): Record<string, string> {
    if ('backendInfo' in this.provider && typeof (this.provider as FakeModelClient).backendInfo === 'function') {
      return (this.provider as FakeModelClient).backendInfo();
    }
    return {
      model_backend: 'real',
      model_provider: this.config.model.model || 'unknown',
      model_name: this.config.model.model || 'unknown',
    };
  }

  private _emit(
    collector: AgentEvent[],
    turnId: string,
    eventType: string,
    payload: Record<string, unknown>,
  ): void {
    collector.push(AgentEventBus.createEvent(eventType, turnId, payload));
    this.eventBus?.emit(eventType, { turnId, ...payload });
  }

  private _estimateTokensFromText(text: string | null | undefined): number {
    return estimateTokens(text);
  }

  private _estimateContextBreakdown(
    messages: LLMMessage[],
    toolSpecs: Record<string, unknown>[],
    contextWindow: number,
  ): Record<string, unknown> {
    let systemPromptTokens = 0;
    let projectContextTokens = 0;
    let skillsTokens = 0;
    let memoryTokens = 0;
    let conversationTokens = 0;

    for (const msg of messages) {
      const role = String(msg.role ?? '');
      const content = typeof msg.content === 'string' ? msg.content : '';
      let tokens = this._estimateTokensFromText(content);

      // Include tool_calls tokens (assistant messages with tool calls store
      // function name + arguments in tool_calls, not in content)
      if (Array.isArray(msg.tool_calls) && msg.tool_calls.length > 0) {
        for (const tc of msg.tool_calls) {
          tokens += this._estimateTokensFromText(tc.function?.name ?? '');
          tokens += this._estimateTokensFromText(tc.function?.arguments ?? '');
          tokens += 10; // overhead for id, type, structure
        }
      }

      if (tokens <= 0) continue;

      const promptPart = (msg as LLMMessage & { promptPart?: PromptPartMeta }).promptPart;

      if (promptPart?.bucket === 'system') {
        systemPromptTokens += tokens;
        continue;
      }

      if (promptPart?.bucket === 'project' || promptPart?.bucket === 'settings') {
        projectContextTokens += tokens;
      } else if (promptPart?.bucket === 'skills') {
        skillsTokens += tokens;
      } else if (promptPart?.bucket === 'memory') {
        memoryTokens += tokens;
      } else if (promptPart?.category === 'history' || promptPart?.bucket === 'intent') {
        conversationTokens += tokens;
      } else if (role === 'system') {
        systemPromptTokens += tokens;
      } else if (content.includes('<project-context>') || content.includes('<settings-update>')) {
        projectContextTokens += tokens;
      } else if (content.includes('<skills>') || content.includes('<skills_usage>')) {
        skillsTokens += tokens;
      } else if (content.includes('<memory-context>') || content.includes('<available-memory>')) {
        memoryTokens += tokens;
      } else {
        conversationTokens += tokens;
      }
    }

    const toolSchemasTokens = this._estimateTokensFromText(JSON.stringify(toolSpecs));
    const mcpToolsTokens = this._estimateTokensFromText(
      JSON.stringify(
        toolSpecs.filter((spec) => {
          const fn = (spec as { function?: { name?: string } }).function?.name ?? '';
          return fn.toLowerCase().includes('mcp');
        }),
      ),
    );

    const estimatedTotalTokens =
      systemPromptTokens
      + projectContextTokens
      + skillsTokens
      + memoryTokens
      + conversationTokens
      + toolSchemasTokens;

    return {
      context_window: contextWindow,
      system_prompt_tokens: systemPromptTokens,
      project_context_tokens: projectContextTokens,
      skills_tokens: skillsTokens,
      memory_tokens: memoryTokens,
      conversation_tokens: conversationTokens,
      tool_schemas_tokens: toolSchemasTokens,
      mcp_tools_tokens: mcpToolsTokens,
      estimated_total_tokens: estimatedTotalTokens,
    };
  }

  private _completeEarly(params: {
    sessionId: string;
    turnId: string;
    events: AgentEvent[];
    finalAnswer: string;
    stopReason: string;
    outputType: string;
    availableSkills: string[];
    loadedSkills: string[];
    skillResultsLog: Record<string, unknown>[];
    skillsUsed: string[];
    toolCallsLog: Array<{ name: string; arguments: Record<string, unknown>; callId: string }>;
    toolResultsLog: Record<string, unknown>[];
  }): AgentRunResult {
    const summary = this.summaryComposer.compose({
      finalAnswer: params.finalAnswer,
      toolResults: [],
      stopReason: params.stopReason,
      outputType: params.outputType,
      availableSkills: params.availableSkills,
      loadedSkills: params.loadedSkills,
    });

    return {
      ok: true,
      sessionId: params.sessionId,
      turnId: params.turnId,
      finalAnswer: params.finalAnswer,
      events: params.events,
      summary,
      stopReason: params.stopReason,
      turnState: mapStopReasonToTurnState(params.stopReason),
      toolCalls: params.toolCallsLog,
      toolResults: params.toolResultsLog,
      status: 'completed',
      outputType: params.outputType,
      availableSkills: params.availableSkills,
      loadedSkills: params.loadedSkills,
      skillLoadsCount: params.loadedSkills.length,
      skillsUsed: params.skillsUsed,
      skillCallsCount: params.skillResultsLog.length,
      skillResults: params.skillResultsLog,
      modelBackend: this.modelInfo['model_backend'] || '',
      modelProvider: this.modelInfo['model_provider'] || '',
      modelName: this.modelInfo['model_name'] || '',
    };
  }

  private _buildCompareTaskTemplate(userInput: string): CompareTaskTemplate | null {
    const asksCompare =
      /(compare|diff|difference|summari[sz]e|总结|对比|比较|差异)/i.test(userInput);
    if (!asksCompare) return null;

    const fileMatches = Array.from(
      userInput.matchAll(/([A-Za-z0-9_\-./\\\u4e00-\u9fa5]+\.[A-Za-z0-9]{1,8})/g),
    ).map((m) => m[1] ?? '');
    const normalized = Array.from(
      new Set(fileMatches.map((f) => this._normalizePathKey(f)).filter(Boolean)),
    );
    if (normalized.length < 2) return null;
    return {
      fileA: normalized[0]!,
      fileB: normalized[1]!,
    };
  }

  private _buildCompareTemplateInstruction(template: CompareTaskTemplate): string {
    return [
      'Follow this fixed workflow for this task:',
      `1) Read ${template.fileA}`,
      `2) Read ${template.fileB}`,
      '3) Compare differences (diff or equivalent)',
      '4) Produce final markdown summary',
      'Do not skip steps and do not finalize before evidence is complete.',
    ].join('\n');
  }

  private _buildCreateArtifactTaskTemplate(userInput: string): CreateArtifactTaskTemplate | null {
    const asksCreate =
      /(create|build|write|implement|scaffold|generate|add|make|修改|新建|创建|实现|生成|编写)/i.test(userInput);
    const artifactLike =
      /(tool|script|benchmark|utility|cli|program|file|markdown|md|py|ts|js|json|txt|工具|脚本|文件|程序)/i.test(userInput);
    if (!asksCreate || !artifactLike) return null;

    const fileMatches = Array.from(
      userInput.matchAll(/([A-Za-z0-9_\-./\\\u4e00-\u9fa5]+\.[A-Za-z0-9]{1,8})/g),
    ).map((m) => m[1] ?? '').filter(Boolean);
    const targetHint = fileMatches[0] || 'the requested artifact';
    return { targetHint };
  }

  private _buildCreateArtifactTemplateInstruction(template: CreateArtifactTaskTemplate): string {
    return [
      'Follow this fixed workflow for this task:',
      '1) Inspect the relevant workspace area or existing files first',
      `2) Create or update ${template.targetHint}`,
      '3) Verify the artifact contents or surrounding context',
      '4) Produce a concise final Markdown summary',
      'Do not stop at describing your next step. Actually execute the required tools before finalizing.',
    ].join('\n');
  }

  private _normalizePathKey(pathLike: string): string {
    return pathLike.replace(/\\/g, '/').replace(/^\.?\//, '').trim().toLowerCase();
  }

  private _extractReadPathFromToolCall(
    toolName: string,
    args: Record<string, unknown>,
  ): string | null {
    if (toolName !== 'read_file') return null;
    const raw =
      typeof args['path'] === 'string'
        ? args['path']
        : (typeof args['file'] === 'string' ? args['file'] : '');
    if (!raw) return null;
    return this._normalizePathKey(raw);
  }

  private _isDiffLikeToolCall(toolName: string, args: Record<string, unknown>): boolean {
    if (toolName !== 'bash') return false;
    const cmd = typeof args['command'] === 'string' ? args['command'].toLowerCase() : '';
    if (!cmd) return false;
    return /\bdiff\b|\bgit\s+diff\b|\bfc\b/.test(cmd);
  }

  private _isWorkspaceInspectionToolCall(toolName: string, args: Record<string, unknown>): boolean {
    if (toolName === 'read_file' || toolName === 'glob' || toolName === 'grep') return true;
    if (toolName !== 'bash') return false;
    const cmd = typeof args['command'] === 'string' ? args['command'].toLowerCase() : '';
    return /\b(ls|dir|find|rg|tree|pwd|cat|type)\b/.test(cmd);
  }

  private _isWriteLikeToolCall(
    toolName: string,
    args: Record<string, unknown>,
    result?: Record<string, unknown>,
  ): boolean {
    if (toolName === 'write_file' || toolName === 'edit_file') {
      return result ? Boolean(result['ok']) : true;
    }
    if (toolName !== 'bash') return false;
    const cmd = typeof args['command'] === 'string' ? args['command'].toLowerCase() : '';
    if (!cmd) return false;
    return /\b(echo|copy|move|ren|mkdir|touch|tee|out-file|set-content|add-content)\b/.test(cmd);
  }

  private _checkCompareEvidence(
    template: CompareTaskTemplate,
    readPaths: Set<string>,
    hasDiffEvidence: boolean,
  ): { ok: boolean; missing: string[] } {
    const missing: string[] = [];
    if (!readPaths.has(template.fileA)) {
      missing.push(`read ${template.fileA}`);
    }
    if (!readPaths.has(template.fileB)) {
      missing.push(`read ${template.fileB}`);
    }
    if (!hasDiffEvidence) {
      missing.push('run a diff between the two files');
    }
    return { ok: missing.length === 0, missing };
  }

  private _checkCreateArtifactEvidence(
    template: CreateArtifactTaskTemplate,
    sawInspectionEvidence: boolean,
    sawWriteEvidence: boolean,
  ): { ok: boolean; missing: string[] } {
    const missing: string[] = [];
    if (!sawInspectionEvidence) {
      missing.push('inspect the relevant workspace files or directories');
    }
    if (!sawWriteEvidence) {
      missing.push(`create or update ${template.targetHint}`);
    }
    return { ok: missing.length === 0, missing };
  }

  private _validateStructuredCompareFinalAnswer(answer: string): { ok: boolean; missing: string[] } {
    const checks = [
      { key: '依据清单', regex: /(依据清单|evidence)/i },
      { key: '结论', regex: /(结论|conclusion)/i },
      { key: '未确认点', regex: /(未确认点|uncertain|unknown|not confirmed)/i },
    ];
    const missing = checks.filter((c) => !c.regex.test(answer)).map((c) => c.key);
    return { ok: missing.length === 0, missing };
  }

  private async _callModelWithRetry(
    events: AgentEvent[],
    turnId: string,
    step: number,
    messages: LLMMessage[],
  toolSpecs: Record<string, unknown>[],
  ): Promise<{ assistantText: string; reasoningSummary?: string; toolCalls: Array<{ callId: string; name: string; arguments: Record<string, unknown> }>; finalAnswer: string; finishReason: string }> {
    let lastError: unknown;
    // Create a fresh LLM abort controller for this call so interrupt() can cancel the HTTP stream
    this._llmAbortController = new AbortController();
    const llmSignal = this._llmAbortController.signal;
    for (let attempt = 1; attempt <= 2; attempt++) {
      try {
        if ('complete' in this.provider && typeof this.provider.complete === 'function') {
          const resp = await (this.provider as FakeModelClient).complete(messages, toolSpecs, false, { step, attempt });
          if (resp.reasoningSummary) {
            const reasoningItemId = `item_reasoning_${crypto.randomUUID()}`;
            this.emitThreadEvent({
              type: 'item.started',
              turn_id: turnId,
              item: { id: reasoningItemId, type: 'reasoning', text: resp.reasoningSummary },
            });
            this.emitThreadEvent({
              type: 'item.completed',
              turn_id: turnId,
              item: { id: reasoningItemId, type: 'reasoning', text: resp.reasoningSummary },
            });
          }
          if (resp.assistantText) {
            const messageItemId = `item_agent_message_${crypto.randomUUID()}`;
            this.emitThreadEvent({
              type: 'item.started',
              turn_id: turnId,
              item: { id: messageItemId, type: 'agent_message', text: resp.assistantText },
            });
            this.emitThreadEvent({
              type: 'item.completed',
              turn_id: turnId,
              item: { id: messageItemId, type: 'agent_message', text: resp.assistantText },
            });
          }
          return {
            assistantText: resp.assistantText,
            reasoningSummary: resp.reasoningSummary,
            toolCalls: resp.toolCalls.map((tc) => ({
              callId: tc.callId,
              name: tc.name,
              arguments: tc.arguments,
            })),
            finalAnswer: resp.finalAnswer,
            finishReason: resp.finishReason,
          };
        }
        // Preferred path: use chatStream when a streaming consumer is attached.
        let streamingReasoningText = '';
        let streamingReasoningItemId: string | null = null;
        let streamingReasoningCompleted = false;
        let streamingMessageText = '';
        let streamingMessageItemId: string | null = null;

        const useStreaming =
          Boolean(this.config.onToken)
          || Boolean(this.config.onReasoningDelta);

        // Use type-erased access to support both LLMProvider and FallbackLLMProvider
        const prov = this.provider as { chat: typeof LLMProvider.prototype.chat; chatStream: typeof LLMProvider.prototype.chatStream };
        const chatResp = useStreaming
          ? await prov.chatStream(
              messages,
              toolSpecs,
              {
                onToken: (token) => {
                  if (!streamingReasoningCompleted && streamingReasoningItemId) {
                    this.emitThreadEvent({
                      type: 'item.completed',
                      turn_id: turnId,
                      item: {
                        id: streamingReasoningItemId,
                        type: 'reasoning',
                        text: streamingReasoningText,
                      },
                    });
                    streamingReasoningCompleted = true;
                  }
                  streamingMessageText += token;
                  if (!streamingMessageItemId) {
                    streamingMessageItemId = `item_agent_message_${crypto.randomUUID()}`;
                    this.emitThreadEvent({
                      type: 'item.started',
                      turn_id: turnId,
                      item: {
                        id: streamingMessageItemId,
                        type: 'agent_message',
                        text: streamingMessageText,
                      },
                    });
                  } else {
                    this.emitThreadEvent({
                      type: 'item.updated',
                      turn_id: turnId,
                      item: {
                        id: streamingMessageItemId,
                        type: 'agent_message',
                        text: streamingMessageText,
                      },
                    });
                  }
                  this.config.onToken?.(token);
                },
                onReasoningDelta: (delta) => {
                  streamingReasoningText += delta;
                  if (!streamingReasoningItemId) {
                    streamingReasoningItemId = `item_reasoning_${crypto.randomUUID()}`;
                    this.emitThreadEvent({
                      type: 'item.started',
                      turn_id: turnId,
                      item: {
                        id: streamingReasoningItemId,
                        type: 'reasoning',
                        text: streamingReasoningText,
                      },
                    });
                  } else {
                    this.emitThreadEvent({
                      type: 'item.updated',
                      turn_id: turnId,
                      item: {
                        id: streamingReasoningItemId,
                        type: 'reasoning',
                        text: streamingReasoningText,
                      },
                    });
                  }
                  this.config.onReasoningDelta?.(delta);
                },
              },
              llmSignal,
            )
          : await prov.chat(
              messages,
              toolSpecs,
              llmSignal,
            );
        if (this.config.tokenTracker) {
          if (chatResp.usage) {
            this.config.tokenTracker.record(chatResp.usage);
          } else {
            // Fallback: streaming may not return usage for some providers
            // (DeepSeek/Qwen via proxies). Estimate from context + output.
            const estimatedInput = this.contextBuilder.estimateMessageTokens(
              messages.map((m) => ({ role: m.role as ChatMessage['role'], content: m.content, messageId: '' })),
            );
            const estimatedOutput = Math.ceil(
              ((chatResp.content?.length ?? 0) + (chatResp.reasoningSummary?.length ?? 0)) / 4,
            );
            this.config.tokenTracker.record({
              promptTokens: estimatedInput,
              completionTokens: estimatedOutput,
              totalTokens: estimatedInput + estimatedOutput,
              cachedTokens: 0,
            });
          }
        }
        if (streamingReasoningItemId && !streamingReasoningCompleted) {
          this.emitThreadEvent({
            type: 'item.completed',
            turn_id: turnId,
            item: {
              id: streamingReasoningItemId,
              type: 'reasoning',
              text: streamingReasoningText,
            },
          });
          streamingReasoningCompleted = true;
        }
        if (chatResp.content && !streamingMessageItemId) {
          streamingMessageItemId = `item_agent_message_${crypto.randomUUID()}`;
          this.emitThreadEvent({
            type: 'item.started',
            turn_id: turnId,
            item: {
              id: streamingMessageItemId,
              type: 'agent_message',
              text: chatResp.content,
            },
          });
        }
        if (streamingMessageItemId) {
          this.emitThreadEvent({
            type: 'item.completed',
            turn_id: turnId,
            item: {
              id: streamingMessageItemId,
              type: 'agent_message',
              text: chatResp.content || streamingMessageText,
            },
          });
        }
        return {
          assistantText: chatResp.content,
          reasoningSummary: chatResp.reasoningSummary,
          toolCalls: chatResp.toolCalls.map((tc) => ({
            callId: tc.callId,
            name: tc.name,
            arguments: tc.arguments,
          })),
          finalAnswer: chatResp.content,
          finishReason: chatResp.finishReason,
        };
      } catch (exc) {
        lastError = exc;
        // Don't retry on abort — the user interrupted
        if (this._interrupted || (exc instanceof DOMException && exc.name === 'AbortError')) {
          throw exc;
        }
        if (attempt < 2) {
          this._emit(events, turnId, 'retry_started', {
            step, reason: 'model_call_error', attempt, error_type: (exc as Error).constructor?.name,
          });
          continue;
        }
        throw exc;
      }
    }
    throw lastError;
  }

  private _findSeenResult(
    seenCalls: Map<string, Array<{ argsFrozen: string; result: Record<string, unknown> }>>,
    toolName: string,
    argsFrozen: string,
  ): Record<string, unknown> | null {
    const entries = seenCalls.get(toolName);
    if (!entries) return null;
    for (const entry of entries) {
      if (entry.argsFrozen === argsFrozen) return entry.result;
    }
    return null;
  }

  private _observationText(result: { content: string; ok: boolean; name: string }): string {
    const limit = 50_000;
    const content = result.content;
    if (typeof content === 'string') return content.slice(0, limit);
    if (typeof content === 'object' && content !== null) {
      try {
        return JSON.stringify(content).slice(0, limit);
      } catch {
        return String(content).slice(0, limit);
      }
    }
    return String(content || '').slice(0, limit);
  }

  private _extractInteractiveStopFromToolResult(
    toolName: string,
    rawContent: string,
  ): { stopReason: string; finalAnswer: string } | null {
    let parsed: Record<string, unknown> | null = null;
    try {
      parsed = JSON.parse(rawContent);
    } catch {
      return null;
    }

    if (toolName === 'exit_plan_mode') {
      const status = typeof parsed?.['status'] === 'string' ? parsed['status'] : '';
      const message = typeof parsed?.['message'] === 'string' ? parsed['message'] : rawContent;
      if (status === 'needs_edit') {
        return {
          stopReason: 'waiting_for_plan_edits',
          finalAnswer: message,
        };
      }
      if (status === 'cancelled') {
        return {
          stopReason: 'plan_cancelled',
          finalAnswer: message,
        };
      }
    }

    if (toolName === 'ask_user_question') {
      const error = typeof parsed?.['error'] === 'string' ? parsed['error'] : '';
      if (error.toLowerCase().includes('question cancelled')) {
        return {
          stopReason: 'question_cancelled',
          finalAnswer: error,
        };
      }
    }

    return null;
  }

  private _fallbackFinalAnswer(
    toolResults: Record<string, unknown>[],
    stopReason: string,
  ): string {
    if (toolResults.length === 0) return '';
    const last = toolResults[toolResults.length - 1];
    if (last['ok']) {
      return `Completed tool execution with \`${last['name']}\`. The model did not provide a fuller summary before stop_reason=${stopReason}.`;
    }
    return `Tool execution did not complete (\`${last['name']}\`): ${last['error'] || 'unknown error'}. stop_reason=${stopReason}.`;
  }

  private _mapProviderErrorStopReason(exc: unknown): string {
    const lowered = `${(exc as Error).constructor?.name}: ${(exc as Error).message}`.toLowerCase();
    if (this._interrupted || (exc instanceof DOMException && exc.name === 'AbortError')) {
      return 'interrupted';
    }
    if (/winerror 10013|access socket|permission|connection|timed out|timeout|refused|reset|certificate/.test(lowered)) {
      return 'provider_network_error';
    }
    if (lowered.includes('401') || lowered.includes('unauthorized') || lowered.includes('auth')) {
      return 'provider_auth_error';
    }
    if (lowered.includes('403') || lowered.includes('forbidden') || lowered.includes('404') || lowered.includes('not found')) {
      return 'provider_http_error';
    }
    if (lowered.includes('provider unavailable') || lowered.includes('service unavailable')) {
      return 'provider_unavailable';
    }
    return 'model_call_failed';
  }

  private _friendlyErrorMessage(exc: unknown): string {
    const reason = this._mapProviderErrorStopReason(exc);
    if (reason === 'provider_network_error') {
      return 'Real LLM call failed because the network connection was blocked. Please verify API, proxy, or firewall settings.';
    }
    if (reason === 'provider_auth_error') {
      return 'LLM API authentication failed (401/Unauthorized). Please check whether the API key is valid and still active.';
    }
    if (reason === 'provider_http_error') {
      return 'The LLM provider returned an HTTP error (such as 403 or 404). Please check whether the base URL and provider config are correct.';
    }
    if (reason === 'provider_unavailable') {
      return 'The current LLM provider is unavailable. Please check the .env configuration or try again later.';
    }
    return `Model call failed: ${(exc as Error).constructor?.name} — ${(exc as Error).message}`;
  }
}
