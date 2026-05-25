// ============================================================================
// AgentLoop — the core agent loop orchestrating LLM calls and tool dispatch
// ============================================================================

import type { AgentEvent, ChatMessage, ToolResult } from '@jarvis/shared';
import type { ToolRegistry } from '@jarvis/tools';
import type { SkillRegistry, SkillExecutor } from '@jarvis/skills';
import type { HookRegistry } from '@jarvis/hooks';
import { LLMProvider, type ModelConfig, type LLMMessage, FakeModelClient } from './model.js';
import { TokenTracker } from './token-tracker.js';
import { AgentEventBus } from './events.js';
import { ContextBuilder, type ContextConfig, type TurnContext, type ContextPack, type SessionStoreLike, type MemoryStoreLike, type SkillRegistryLike } from './context.js';
import { PromptBuilder, AGENT_SYSTEM_PROMPT } from './prompt-builder.js';
import { ResponseComposer } from './summary.js';
import { withRetry, type RetryConfig, ErrorClassifier, RetryPolicy as ToolRetryPolicy, FailureTracker, ReplanPolicy } from './retry.js';

// ============================================================================
// Configuration
// ============================================================================

export interface AgentLoopConfig {
  model: ModelConfig;
  maxTurns?: number;
  tools?: ToolRegistry;
  systemPrompt?: string;
  eventBus?: AgentEventBus;
  context?: ContextConfig;
  provider?: LLMProvider;
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
}

export interface TurnResult {
  turnId: string;
  messages: ChatMessage[];
  answer: string;
  reasoning?: string;
  toolResults: ToolResult[];
  stopReason: string;
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

// ============================================================================
// AgentLoop
// ============================================================================

const SENSITIVE_MARKERS = [
  '.env', 'api key', 'api token', 'access token', 'bearer token',
  'auth token', 'password', 'id_rsa', 'client secret', 'api secret',
  'secret key', 'jarvis_llm_api_key',
];

export class AgentLoop {
  private config: Required<Omit<AgentLoopConfig, 'tools' | 'eventBus' | 'provider' | 'skillRegistry' | 'skillExecutor' | 'hooks' | 'sessionStore' | 'memoryStore' | 'contextStore'>> & {
    tools?: ToolRegistry;
    eventBus?: AgentEventBus;
    provider?: LLMProvider;
    skillRegistry?: SkillRegistry;
    skillExecutor?: SkillExecutor;
    hooks?: HookRegistry;
    sessionStore?: SessionStoreLike;
    memoryStore?: MemoryStoreLike;
    contextStore?: { retrieveRecentContext(sessionId: string): Record<string, unknown> };
  };
  private provider: LLMProvider | FakeModelClient;
  private tools?: ToolRegistry;
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

  constructor(config: AgentLoopConfig) {
    this.config = {
      model: config.model,
      maxTurns: config.maxTurns ?? 30,
      systemPrompt: config.systemPrompt ?? '',
      context: config.context ?? {},
      maxSkills: config.maxSkills ?? 5,
      projectRoot: config.projectRoot ?? process.cwd(),
      permissionMode: config.permissionMode ?? 'workspace_write',
      maxSteps: config.maxSteps ?? 20,
      timeoutS: config.timeoutS ?? 300,
      toolTimeoutS: config.toolTimeoutS ?? 60,
      autoApprove: config.autoApprove ?? false,
      tools: config.tools,
      eventBus: config.eventBus,
      provider: config.provider,
      skillRegistry: config.skillRegistry,
      skillExecutor: config.skillExecutor,
      sessionStore: config.sessionStore,
      memoryStore: config.memoryStore,
      contextStore: config.contextStore,
    };

    this.provider = config.provider ?? new LLMProvider(config.model);
    this.tools = config.tools;
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

    this.modelInfo = this._getModelInfo();

    this.contextBuilder = new ContextBuilder(config.context, {
      sessionStore: config.sessionStore,
      memoryStore: config.memoryStore,
      skillRegistry: config.skillRegistry as unknown as SkillRegistryLike,
      contextStore: config.contextStore,
      modelInfo: this.modelInfo as unknown as Record<string, unknown>,
      permissionMode: this.permissionMode,
    });

    this.promptBuilder = new PromptBuilder();
    this.summaryComposer = new ResponseComposer();
    this.errorClassifier = new ErrorClassifier();
    this.toolRetryPolicy = new ToolRetryPolicy(2);
    this.replanPolicy = new ReplanPolicy(2);
  }

  // ========================================================================
  // Simple run() — backward compat with existing tests
  // ========================================================================

  async run(
    userMessage: string,
    history: ChatMessage[] = [],
  ): Promise<TurnResult> {
    const turnId = `turn_${crypto.randomUUID()}`;
    let allMessages: ChatMessage[] = [...history];
    const allToolResults: ToolResult[] = [];

    const userMsg: ChatMessage = {
      role: 'user',
      content: userMessage,
      messageId: `msg_${crypto.randomUUID()}`,
    };
    allMessages.push(userMsg);

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
    let retryWithToolInstructionCount = 0;

    for (let turn = 0; turn < this.config.maxTurns; turn++) {
      turnsUsed = turn + 1;

      const llmMessages = this.contextBuilder.buildMessages(effectiveSystemPrompt, allMessages);

      // Compaction check
      const estimatedTokens = this.contextBuilder.estimateMessageTokens(allMessages);
      if (this.contextBuilder.shouldCompress(estimatedTokens)) {
        this.eventBus?.emit('context:compressing', {
          turnId,
          estimatedTokens,
          maxTokens: this.config.context.maxTokens ?? 128_000,
        });
        allMessages = this.contextBuilder.compactToolResults(allMessages);
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
              onToken: this.config.onToken,
              onReasoningDelta: this.config.onReasoningDelta,
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
        break;
      }

      const { content, toolCalls, finishReason } = response;

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
        if (retryWithToolInstructionCount >= 2) {
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
          this.eventBus?.emit('tool:executing', {
            turnId, turn, toolName: tc.name, args: tc.arguments,
          });

          let toolResult: ToolResult;
          if (this.tools) {
            const rawResult = await this.tools.dispatch(tc.name, tc.arguments);
            let parsed: Record<string, unknown> | null = null;
            try { parsed = JSON.parse(rawResult); } catch { /* not JSON */ }

            toolResult = {
              callId: tc.callId,
              name: tc.name,
              ok: parsed === null || typeof parsed.error !== 'string',
              content: rawResult,
              error: parsed && typeof parsed.error === 'string' ? parsed.error : undefined,
              durationMs: 0,
            };
          } else {
            toolResult = {
              callId: tc.callId,
              name: tc.name,
              ok: false,
              content: '',
              error: 'No tool registry configured',
              durationMs: 0,
            };
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

    return {
      turnId,
      messages: allMessages,
      answer: finalContent,
      toolResults: allToolResults,
      stopReason,
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
    const started = Date.now();
    const sessionId = opts?.sessionId ?? `session_${crypto.randomUUID()}`;
    const turnId = `turn_${crypto.randomUUID()}`;
    const cwd = opts?.cwd ?? this.projectRoot;

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

    // Safety check
    if (this._isSensitiveRequest(userInput)) {
      return this._completeEarly({
        sessionId, turnId, events, availableSkills, loadedSkills, skillResultsLog, skillsUsed,
        finalAnswer: "I can't print .env files or API keys because they may contain secrets.",
        stopReason: 'safety_refusal',
        outputType: 'refusal',
        toolCallsLog, toolResultsLog,
      });
    }

    // Build context
    const turnContext = this.contextBuilder.buildContext({
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

    // Obtain tool specs filtered by activeAllowedTools (updated dynamically per-step)
    const getToolSpecs = (): Record<string, unknown>[] => {
      return this.tools
        ? this.tools.getDefinitions(
            activeAllowedTools
              ? [...new Set([...activeAllowedTools, 'skill.load'])]
              : undefined,
          )
        : [];
    };

    // Failure tracking
    const failureTracker = new FailureTracker(5, 4, 3);
    let noProgressCount = 0;
    let lastProgressMarker = '';
    const seenCalls = new Map<string, Array<{ argsFrozen: string; result: Record<string, unknown> }>>();
    let retryWithToolInstructionCount = 0;
    let retryWithLengthCount = 0;

    try {
      for (let step = 1; step <= this.maxSteps; step++) {
        finalAnswer = '';

        if ((Date.now() - started) > this.timeoutS * 1000) {
          stopReason = 'timeout';
          break;
        }

        // Context window usage
        const contextUsed = this.contextBuilder.estimateMessageTokens(
          messages.map((m) => ({ role: m.role as ChatMessage['role'], content: m.content, messageId: '' })),
        );
        const contextPct = contextUsed / this.config.context.maxTokens!;
        this._emit(events, turnId, 'context_window_usage', {
          used_tokens: contextUsed,
          context_window: this.config.context.maxTokens!,
          usage_pct: Math.round(contextPct * 1000) / 1000,
          message_count: messages.length,
        });

        // Model call with retry
        this._emit(events, turnId, 'model_call_started', { step });
        const modelResp = await this._callModelWithRetry(events, turnId, step, messages as LLMMessage[], getToolSpecs());
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
          outputType = toolCallsLog.length > 0 ? 'tool_result' : 'answer';
          stopReason = 'completed';
          this._emit(events, turnId, 'final_answer_created', { step });
          break;
        }

        if (modelResp.toolCalls.length === 0 && !finalAnswer) {
          const finish = modelResp.finishReason;

          // Tool-intent retry (only before any tools have been called)
          if (finish === 'retry_with_tool_instruction') {
            if (toolCallsLog.length === 0) {
              retryWithToolInstructionCount++;
              if (retryWithToolInstructionCount >= 2) {
                stopReason = 'retry_with_tool_instruction';
                break;
              }
              messages.push({
                role: 'user',
                content: 'Your last response described what you intend to do but did NOT actually call any tool. You MUST call the appropriate tool function directly — do NOT just say what you will do. Use the tool now.',
              });
              continue;
            }
            finalAnswer = modelResp.finalAnswer || modelResp.assistantText || '';
            if (!finalAnswer) {
              stopReason = finish || 'no_progress';
              break;
            }
            outputType = 'answer';
            stopReason = 'completed';
            break;
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

        let anyOkThisStep = false;
        for (const call of modelResp.toolCalls) {
          // FailureTracker check
          const reject = failureTracker.shouldRejectTool(call.name);
          if (reject.reject) {
            this._emit(events, turnId, 'tool_rejected', {
              step, tool_name: call.name, reason: reject.reason, kind: reject.kind,
            });
            if (reject.kind === 'repeat') {
              if (failureTracker.isRepeatHardStop(call.name)) {
                stopReason = 'consecutive_rejections';
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
            const skillName = String(call.arguments['name'] ?? '').trim();
            if (skillName && loadedSkills.includes(skillName)) {
              this._emit(events, turnId, 'skill_already_loaded', { step, skill_name: skillName });
              messages.push({
                role: 'user',
                content: `Skill \`${skillName}\` is already loaded. Its instructions are in the context above. Do NOT call skill.load again — follow the skill instructions to complete the task.`,
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
            if (call.name === 'skill.load') {
              const sn = String((reused['metadata'] as Record<string, unknown>)?.['skill_name'] || call.arguments['name'] || '');
              if (sn && !loadedSkills.includes(sn)) loadedSkills.push(sn);
            }
            continue;
          }

          toolCallsLog.push({ name: call.name, arguments: call.arguments, callId: call.callId });
          this._emit(events, turnId, 'tool_call_started', { step, tool_call: { name: call.name, arguments: call.arguments } });

          // Execute tool
          let result: ToolResult;

          // Hooks: pre_tool_use gate
          if (this.hooks) {
            const hookResult = await this.hooks.runPreToolUse({
              toolName: call.name,
              toolArgs: call.arguments,
              sessionId,
              turnId,
            });
            if (!hookResult.allowed) {
              result = {
                callId: call.callId,
                name: call.name,
                ok: false,
                content: JSON.stringify({
                  error: `Tool "${call.name}" blocked: ${hookResult.reason ?? hookResult.message ?? 'denied by hook'}`,
                }),
                error: hookResult.reason ?? 'denied',
                durationMs: 0,
              };
              const blockedDict = { ...result, content: result.content };
              toolResultsLog.push(blockedDict);
              this._emit(events, turnId, 'tool_call_completed', { step, tool_result: { ...result, ok: false } });
              messages.push({
                role: 'tool',
                tool_call_id: call.callId,
                content: this._observationText(result),
              });
              failureTracker.recordFailure(result.name, 'blocked', result.error ?? '', step);
              continue;
            }
          }

          if (this.tools) {
            const rawResult = await this.tools.dispatch(call.name, call.arguments);
            let parsed: Record<string, unknown> | null = null;
            try { parsed = JSON.parse(rawResult); } catch { /* not JSON */ }
            result = {
              callId: call.callId,
              name: call.name,
              ok: !parsed || typeof parsed.error !== 'string',
              content: rawResult,
              error: parsed && typeof parsed.error === 'string' ? parsed.error : undefined,
              durationMs: 0,
            };
          } else {
            result = {
              callId: call.callId,
              name: call.name,
              ok: false,
              content: '',
              error: 'No tool registry configured',
              durationMs: 0,
            };
          }

          const resultDict = { ...result, content: result.content };
          toolResultsLog.push(resultDict);
          this._emit(events, turnId, 'tool_call_completed', { step, tool_result: resultDict });

          // Hooks: post_tool_use (fire-and-forget, audit-only)
          if (this.hooks) {
            this.hooks.runPostToolUse({
              toolName: call.name,
              toolArgs: call.arguments,
              toolResult: result.content,
              sessionId,
              turnId,
            }).catch(() => {});
          }

          // skill.load handling
          if (call.name === 'skill.load' && result.ok) {
            const resultMeta = (result as unknown as { metadata?: Record<string, unknown> }).metadata;
            const skillName = String(resultMeta?.['skill_name'] || call.arguments['name'] || '').trim();
            if (skillName && !loadedSkills.includes(skillName)) loadedSkills.push(skillName);
            // Merge allowed-tools from the loaded skill
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
            messages.push({
              role: 'tool',
              tool_call_id: call.callId,
              content: this._observationText(result),
            });
            continue;
          }

          // Tool failed
          const classification = this.errorClassifier.classify(result);
          failureTracker.recordFailure(result.name, classification.category, result.error ?? '', step);

          const shouldStop = failureTracker.shouldStop();
          if (shouldStop.stop) {
            messages.push({
              role: 'tool',
              tool_call_id: call.callId,
              content: this._observationText(result),
            });
            stopReason = 'consecutive_failures';
            outputType = 'error';
            finalAnswer = shouldStop.reason;
            break;
          }

          // Retry transient errors
          if (this.toolRetryPolicy.shouldRetry(
            { name: call.name, arguments: call.arguments, callId: call.callId, source: 'model' },
            classification,
          ) && this.tools) {
            this._emit(events, turnId, 'retry_started', { step, tool_name: result.name, reason: classification.reason });
            const retryRaw = await this.tools.dispatch(call.name, call.arguments);
            let retryParsed: Record<string, unknown> | null = null;
            try { retryParsed = JSON.parse(retryRaw); } catch { /* not JSON */ }
            const retryResult: ToolResult = {
              callId: call.callId,
              name: call.name,
              ok: !retryParsed || typeof retryParsed.error !== 'string',
              content: retryRaw,
              error: retryParsed && typeof retryParsed.error === 'string' ? retryParsed.error : undefined,
              durationMs: 0,
            };
            toolResultsLog.push({ ...retryResult, content: retryResult.content });
            if (retryResult.ok) {
              failureTracker.recordSuccess(retryResult.name);
              anyOkThisStep = true;
              messages.push({
                role: 'tool',
                tool_call_id: call.callId,
                content: this._observationText(retryResult),
              });
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

          messages.push({
            role: 'tool',
            tool_call_id: call.callId,
            content: this._observationText(result),
          });
        }

        if (['approval_required', 'timeout', 'consecutive_failures', 'consecutive_rejections'].includes(stopReason)) {
          break;
        }

        // Mid-turn compaction (70%)
        const midPct = this.contextBuilder.estimateMessageTokens(
          messages.map((m) => ({ role: m.role as ChatMessage['role'], content: m.content, messageId: '' })),
        ) / this.config.context.maxTokens!;
        if (midPct > 0.70) {
          const compacted = this.contextBuilder.compactToolResults(
            messages.map((m) => ({ role: m.role as ChatMessage['role'], content: m.content, messageId: '' })),
          );
          messages.length = 0;
          messages.push(...compacted.map((m) => ({ role: m.role, content: m.content })));
        }

        // No-progress detection
        const marker = `${toolCallsLog.length}:${toolResultsLog.length}:${finalAnswer.slice(0, 60)}`;
        if (marker === lastProgressMarker) {
          noProgressCount++;
        } else {
          noProgressCount = 0;
          lastProgressMarker = marker;
        }
        if (noProgressCount >= 4) {
          stopReason = 'no_progress';
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

      return {
        ok: status !== 'failed',
        sessionId,
        turnId,
        finalAnswer,
        reasoning: reasoning || undefined,
        events,
        summary,
        stopReason,
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
  }

  private _isSensitiveRequest(text: string): boolean {
    const lowered = text.toLowerCase();
    return SENSITIVE_MARKERS.some((m) => lowered.includes(m));
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

  private async _callModelWithRetry(
    events: AgentEvent[],
    turnId: string,
    step: number,
    messages: LLMMessage[],
    toolSpecs: Record<string, unknown>[],
  ): Promise<{ assistantText: string; reasoningSummary?: string; toolCalls: Array<{ callId: string; name: string; arguments: Record<string, unknown> }>; finalAnswer: string; finishReason: string }> {
    let lastError: unknown;
    for (let attempt = 1; attempt <= 2; attempt++) {
      try {
        if ('complete' in this.provider && typeof this.provider.complete === 'function') {
          const resp = await (this.provider as FakeModelClient).complete(messages, toolSpecs, false, { step, attempt });
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
        // Fallback: use LLMProvider.chat
        const chatResp = await (this.provider as LLMProvider).chat(
          messages,
          toolSpecs,
        );
        if (chatResp.usage && this.config.tokenTracker) {
          this.config.tokenTracker.record(chatResp.usage);
        }
        return {
          assistantText: chatResp.content,
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
